from __future__ import annotations

import shutil
import sqlite3
import re
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.config import IMPORT_COPY_ROOT
from app.database import Database
from app.utils.cover_generator import render_name_author_cover, store_cover_image
from app.utils.image_files import file_sha1, list_images_sorted, natural_sort_key

StorageMode = Literal["reference", "copy"]
CoverSource = Literal["none", "first_image", "custom_image", "name_author"]
DuplicatePolicy = Literal["error", "skip", "allow"]
_EPISODE_PATTERN = re.compile(
    r"(?:第\s*(\d+)\s*[话集卷]|(?:ep|e)\s*\.?\s*(\d+)|\[(\d+)\]|\((\d+)\)|\b(\d{1,5})\b)",
    re.IGNORECASE,
)


@dataclass
class ImportMetadata:
    name: str
    author: str
    episode_number: int
    tags: str
    storage_mode: StorageMode
    cover_source: CoverSource
    custom_cover_path: str | None = None


@dataclass
class ImportResult:
    imported: bool
    series_id: int
    episode_number: int
    message: str


@dataclass
class BatchImportRequest:
    parent_folder: Path
    name: str
    author: str
    start_episode: int
    tags: str
    storage_mode: StorageMode
    cover_source: CoverSource
    hash_check: bool
    duplicate_policy: DuplicatePolicy


class ImportService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def import_folder(
        self,
        folder: Path,
        metadata: ImportMetadata,
        hash_check: bool,
        duplicate_policy: DuplicatePolicy = "error",
    ) -> ImportResult:
        if not folder.exists() or not folder.is_dir():
            raise ValueError("导入路径不存在或不是文件夹")

        images = list_images_sorted(folder)
        if not images:
            raise ValueError("导入文件夹中没有可用图片")

        incoming_hashes = self._build_hashes(images) if hash_check else None

        with self.db.transaction() as conn:
            series_id = self._get_or_create_series(conn, metadata)
            self._update_total_episodes(conn, series_id, metadata.episode_number)

            duplicate_episode = conn.execute(
                """
                SELECT id FROM episodes
                WHERE series_id = ? AND episode_number = ?
                """,
                (series_id, metadata.episode_number),
            ).fetchone()
            if duplicate_episode:
                if duplicate_policy == "skip":
                    return ImportResult(False, series_id, metadata.episode_number, "同集数已存在，已跳过")
                raise ValueError("该漫画集数已存在，请修改集数或先删除旧数据")

            if hash_check and incoming_hashes:
                duplicate_ep_no = self._find_duplicate_episode_by_hash(conn, series_id, incoming_hashes)
                if duplicate_ep_no is not None:
                    msg = f"检测到重复内容，与第{duplicate_ep_no}集一致"
                    if duplicate_policy == "skip":
                        return ImportResult(False, series_id, metadata.episode_number, f"{msg}，已跳过")
                    if duplicate_policy == "error":
                        raise ValueError(msg)

            episode_id = self._create_episode(conn, folder, metadata, series_id, len(images))
            self._insert_images(conn, episode_id, images, metadata.storage_mode, incoming_hashes)
            self._update_cover(conn, series_id, episode_id, metadata, images)

        return ImportResult(True, series_id, metadata.episode_number, "导入成功")

    def import_auto_folder(
        self,
        folder: Path,
        author: str,
        tags: str,
        hash_check: bool,
        duplicate_policy: DuplicatePolicy = "skip",
        custom_name: str = "",
    ) -> list[ImportResult]:
        if not folder.exists() or not folder.is_dir():
            raise ValueError("导入路径不存在或不是文件夹")

        direct_images = list_images_sorted(folder)
        child_folders = [p for p in folder.iterdir() if p.is_dir()]
        child_folders.sort(key=lambda p: natural_sort_key(p.name))
        episode_folders = [p for p in child_folders if list_images_sorted(p)]

        if direct_images and not episode_folders:
            name = custom_name or self._guess_name_and_episode(folder.name)[0]
            _, guessed_episode = self._guess_name_and_episode(folder.name)
            metadata = ImportMetadata(
                name=name,
                author=author.strip(),
                episode_number=guessed_episode or 1,
                tags=tags.strip(),
                storage_mode="copy",
                cover_source="first_image",
            )
            return [
                self.import_folder(
                    folder=folder,
                    metadata=metadata,
                    hash_check=hash_check,
                    duplicate_policy=duplicate_policy,
                )
            ]

        if episode_folders:
            series_name = custom_name or self._guess_series_name_for_batch(folder.name)
            results: list[ImportResult] = []
            fallback_episode = 1

            for ep_folder in episode_folders:
                _, guessed_episode = self._guess_name_and_episode(ep_folder.name)
                episode_number = guessed_episode or fallback_episode
                fallback_episode = max(fallback_episode + 1, episode_number + 1)

                metadata = ImportMetadata(
                    name=series_name,
                    author=author.strip(),
                    episode_number=episode_number,
                    tags=tags.strip(),
                    storage_mode="copy",
                    cover_source="first_image",
                )

                try:
                    results.append(
                        self.import_folder(
                            folder=ep_folder,
                            metadata=metadata,
                            hash_check=hash_check,
                            duplicate_policy=duplicate_policy,
                        )
                    )
                except Exception as exc:
                    results.append(ImportResult(False, -1, episode_number, f"{ep_folder.name}: {exc}"))

            return results

        raise ValueError("未检测到可导入图片。请直接选择单集图片目录，或选择包含多集子目录的漫画目录")

    def import_parent_folder(self, request: BatchImportRequest) -> list[ImportResult]:
        if not request.parent_folder.exists() or not request.parent_folder.is_dir():
            raise ValueError("批量导入父目录不存在")

        folders = [p for p in request.parent_folder.iterdir() if p.is_dir()]
        folders.sort(key=lambda p: natural_sort_key(p.name))
        if not folders:
            raise ValueError("批量导入目录下没有子文件夹")

        results: list[ImportResult] = []
        for idx, folder in enumerate(folders):
            metadata = ImportMetadata(
                name=request.name,
                author=request.author,
                episode_number=request.start_episode + idx,
                tags=request.tags,
                storage_mode=request.storage_mode,
                cover_source=request.cover_source,
            )
            try:
                results.append(
                    self.import_folder(
                        folder=folder,
                        metadata=metadata,
                        hash_check=request.hash_check,
                        duplicate_policy=request.duplicate_policy,
                    )
                )
            except Exception as exc:
                results.append(
                    ImportResult(False, -1, metadata.episode_number, f"{folder.name}: {exc}")
                )

        return results

    def _build_hashes(self, images: list[Path]) -> list[str]:
        return [file_sha1(p) for p in images]

    def _guess_name_and_episode(self, folder_name: str) -> tuple[str, int | None]:
        match = _EPISODE_PATTERN.search(folder_name)
        episode: int | None = None
        if match:
            for g in match.groups():
                if g and g.isdigit():
                    episode = int(g)
                    break

        name = folder_name
        if match:
            name = name.replace(match.group(0), " ")
        name = re.sub(r"[\[\](){}._\-]+", " ", name)
        name = re.sub(r"\s+", " ", name).strip()
        return (name or folder_name), episode

    def _guess_series_name_for_batch(self, folder_name: str) -> str:
        name, _ = self._guess_name_and_episode(folder_name)
        return name

    def _find_duplicate_episode_by_hash(
        self,
        conn: sqlite3.Connection,
        series_id: int,
        incoming_hashes: list[str],
    ) -> int | None:
        candidates = conn.execute(
            """
            SELECT id, episode_number
            FROM episodes
            WHERE series_id = ? AND image_count = ?
            """,
            (series_id, len(incoming_hashes)),
        ).fetchall()

        for row in candidates:
            episode_id = int(row["id"])
            hashes = [
                r["file_hash"]
                for r in conn.execute(
                    "SELECT file_hash FROM images WHERE episode_id = ? ORDER BY sort_order ASC",
                    (episode_id,),
                ).fetchall()
            ]
            if any(h is None for h in hashes):
                continue
            if hashes == incoming_hashes:
                return int(row["episode_number"])
        return None

    def _get_or_create_series(self, conn: sqlite3.Connection, metadata: ImportMetadata) -> int:
        row = conn.execute(
            "SELECT id FROM series WHERE name = ? AND author = ?",
            (metadata.name.strip(), metadata.author.strip()),
        ).fetchone()
        if row:
            return int(row["id"])

        cur = conn.execute(
            """
            INSERT INTO series(name, author, total_episodes, tags)
            VALUES(?, ?, 1, ?)
            """,
            (metadata.name.strip(), metadata.author.strip(), metadata.tags.strip()),
        )
        return int(cur.lastrowid)

    def _update_total_episodes(self, conn: sqlite3.Connection, series_id: int, episode_number: int) -> None:
        conn.execute(
            """
            UPDATE series
            SET total_episodes = CASE
                WHEN total_episodes < ? THEN ?
                ELSE total_episodes
            END,
            updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (episode_number, episode_number, series_id),
        )

    def _create_episode(
        self,
        conn: sqlite3.Connection,
        folder: Path,
        metadata: ImportMetadata,
        series_id: int,
        image_count: int,
    ) -> int:
        target_dir = IMPORT_COPY_ROOT / self._build_import_dir_name(series_id, metadata.episode_number, folder)
        target_dir.mkdir(parents=True, exist_ok=True)
        data_path: str | None = str(target_dir)

        cur = conn.execute(
            """
            INSERT INTO episodes(series_id, episode_number, folder_path, storage_mode, data_path, image_count)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (series_id, metadata.episode_number, str(folder), "copy", data_path, image_count),
        )
        return int(cur.lastrowid)

    def _build_import_dir_name(self, series_id: int, episode_number: int, source_folder: Path) -> str:
        # 用导入时刻 + 来源路径生成稳定长度哈希，避免目录名冲突并减轻目录层级压力。
        raw = f"{time.time_ns()}|{series_id}|{episode_number}|{source_folder.resolve()}"
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        return f"import_{digest}"

    def _insert_images(
        self,
        conn: sqlite3.Connection,
        episode_id: int,
        images: list[Path],
        storage_mode: StorageMode,
        incoming_hashes: list[str] | None,
    ) -> None:
        episode_data_path: Path | None = None
        row = conn.execute("SELECT data_path FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if row and row[0]:
            episode_data_path = Path(str(row[0]))

        for idx, src in enumerate(images):
            if episode_data_path is not None:
                dst = episode_data_path / src.name
                shutil.copy2(src, dst)
                resolved_path = dst
            else:
                resolved_path = src

            file_hash = incoming_hashes[idx] if incoming_hashes is not None else None
            conn.execute(
                """
                INSERT INTO images(episode_id, file_name, file_path, file_hash, sort_order)
                VALUES(?, ?, ?, ?, ?)
                """,
                (episode_id, src.name, str(resolved_path), file_hash, idx),
            )

    def _update_cover(
        self,
        conn: sqlite3.Connection,
        series_id: int,
        episode_id: int,
        metadata: ImportMetadata,
        images: list[Path],
    ) -> None:
        if metadata.cover_source == "none":
            cover_path = None
        elif metadata.cover_source == "custom_image" and metadata.custom_cover_path:
            custom_path = Path(metadata.custom_cover_path)
            cover_path = str(store_cover_image(series_id, custom_path)) if custom_path.exists() else None
        elif metadata.cover_source == "first_image":
            row = conn.execute(
                "SELECT file_path FROM images WHERE episode_id = ? ORDER BY sort_order ASC LIMIT 1",
                (episode_id,),
            ).fetchone()
            cover_path = str(row[0]) if row else str(images[0])
        elif metadata.cover_source == "name_author":
            cover_path = str(render_name_author_cover(series_id, metadata.name, metadata.author))
        else:
            cover_path = None

        if cover_path is not None:
            conn.execute(
                "UPDATE series SET cover_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (cover_path, series_id),
            )
