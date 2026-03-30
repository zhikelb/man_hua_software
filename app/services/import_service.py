from __future__ import annotations

import shutil
import sqlite3
import re
import hashlib
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from app.config import IMPORT_COPY_ROOT
from app.database import Database
from app.utils.cover_generator import render_name_author_cover, store_cover_image
from app.utils.image_files import file_sha1, list_images_sorted, natural_sort_key

StorageMode = Literal["copy"]
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
    episode_name: str
    episode_order: int
    tags: str
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
            self._insert_images(conn, episode_id, images, incoming_hashes)
            self._update_cover(conn, series_id, episode_id, metadata, images)

        return ImportResult(True, series_id, metadata.episode_number, "导入成功")

    def import_backup_data(
        self,
        source: Path,
        hash_check: bool,
        duplicate_policy: DuplicatePolicy = "skip",
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[ImportResult]:
        if not source.exists():
            raise ValueError("备份路径不存在")

        if source.is_file() and source.suffix.lower() == ".zip":
            import zipfile

            with tempfile.TemporaryDirectory(prefix="manga_backup_import_") as tmp:
                temp_root = Path(tmp)
                with zipfile.ZipFile(source, "r") as zf:
                    zf.extractall(temp_root)
                backup_data_dir = self._find_backup_data_dir(temp_root)
                if backup_data_dir is None:
                    raise ValueError("无法识别备份包结构，未找到 data/manga.db 与 data/imports")
                return self._import_from_backup_data_dir(
                    backup_data_dir=backup_data_dir,
                    hash_check=hash_check,
                    duplicate_policy=duplicate_policy,
                    progress_callback=progress_callback,
                )

        if source.is_dir():
            backup_data_dir = self._find_backup_data_dir(source)
            if backup_data_dir is None:
                raise ValueError("无法识别备份目录结构，未找到 data/manga.db 与 data/imports")
            return self._import_from_backup_data_dir(
                backup_data_dir=backup_data_dir,
                hash_check=hash_check,
                duplicate_policy=duplicate_policy,
                progress_callback=progress_callback,
            )

        raise ValueError("仅支持zip备份文件或备份目录")

    def import_auto_folder(
        self,
        folder: Path,
        author: str,
        tags: str,
        hash_check: bool,
        duplicate_policy: DuplicatePolicy = "skip",
        custom_name: str = "",
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[ImportResult]:
        if not folder.exists() or not folder.is_dir():
            raise ValueError("导入路径不存在或不是文件夹")

        backup_data_dir = self._resolve_backup_data_dir(folder)
        if backup_data_dir is not None:
            return self._import_from_backup_data_dir(
                backup_data_dir=backup_data_dir,
                hash_check=hash_check,
                duplicate_policy=duplicate_policy,
                progress_callback=progress_callback,
            )

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
                episode_name=folder.name,
                episode_order=1,
                tags=tags.strip(),
                cover_source="first_image",
            )
            single_result = self.import_folder(
                    folder=folder,
                    metadata=metadata,
                    hash_check=hash_check,
                    duplicate_policy=duplicate_policy,
                )
            if progress_callback is not None:
                progress_callback(1, 1)
            return [single_result]

        if episode_folders:
            series_name = custom_name or self._guess_series_name_for_batch(folder.name)
            results: list[ImportResult] = []
            start_episode_number, start_episode_order = self._get_series_start_values(
                series_name,
                author.strip(),
            )

            for idx, ep_folder in enumerate(episode_folders, start=1):
                episode_number = start_episode_number + idx - 1

                metadata = ImportMetadata(
                    name=series_name,
                    author=author.strip(),
                    episode_number=episode_number,
                    episode_name=ep_folder.name,
                    episode_order=start_episode_order + idx - 1,
                    tags=tags.strip(),
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
                finally:
                    if progress_callback is not None:
                        progress_callback(idx, len(episode_folders))

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
                episode_name=folder.name,
                episode_order=idx + 1,
                tags=request.tags,
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

    def _get_series_start_values(self, name: str, author: str) -> tuple[int, int]:
        row = self.db.conn.execute(
            "SELECT id FROM series WHERE name = ? AND author = ?",
            (name.strip(), author.strip()),
        ).fetchone()
        if row is None:
            return 1, 1

        series_id = int(row["id"])
        max_row = self.db.conn.execute(
            """
            SELECT
                COALESCE(MAX(episode_number), 0) AS max_episode_number,
                COALESCE(MAX(episode_order), 0) AS max_episode_order
            FROM episodes
            WHERE series_id = ?
            """,
            (series_id,),
        ).fetchone()
        if max_row is None:
            return 1, 1
        return int(max_row["max_episode_number"]) + 1, int(max_row["max_episode_order"]) + 1

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
            INSERT INTO episodes(
                series_id, episode_number, episode_name, episode_order,
                folder_path, storage_mode, data_path, image_count
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                series_id,
                metadata.episode_number,
                metadata.episode_name.strip() or f"第{metadata.episode_number}集",
                metadata.episode_order,
                str(folder),
                "copy",
                data_path,
                image_count,
            ),
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
        incoming_hashes: list[str] | None,
    ) -> None:
        episode_data_path: Path | None = None
        row = conn.execute("SELECT data_path FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if row and row[0]:
            episode_data_path = Path(str(row[0]))

        pad_width = max(3, len(str(len(images))))

        for idx, src in enumerate(images, start=1):
            new_file_name = f"{idx:0{pad_width}d}{src.suffix.lower()}"
            if episode_data_path is not None:
                dst = episode_data_path / new_file_name
                shutil.copy2(src, dst)
                resolved_path = dst
                stored_name = new_file_name
            else:
                resolved_path = src
                stored_name = src.name

            file_hash = incoming_hashes[idx - 1] if incoming_hashes is not None else None
            conn.execute(
                """
                INSERT INTO images(episode_id, file_name, file_path, file_hash, sort_order)
                VALUES(?, ?, ?, ?, ?)
                """,
                (episode_id, stored_name, str(resolved_path), file_hash, idx - 1),
            )

    def _resolve_backup_data_dir(self, folder: Path) -> Path | None:
        candidates = [folder, folder / "data"]
        for candidate in candidates:
            if (candidate / "manga.db").exists() and (candidate / "imports").exists():
                return candidate
        return None

    def _find_backup_data_dir(self, root: Path) -> Path | None:
        direct = self._resolve_backup_data_dir(root)
        if direct is not None:
            return direct

        for db_file in root.rglob("manga.db"):
            parent = db_file.parent
            if (parent / "imports").exists() and (parent / "imports").is_dir():
                return parent
        return None

    def _import_from_backup_data_dir(
        self,
        backup_data_dir: Path,
        hash_check: bool,
        duplicate_policy: DuplicatePolicy,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[ImportResult]:
        backup_db_path = backup_data_dir / "manga.db"
        source_conn = sqlite3.connect(str(backup_db_path))
        source_conn.row_factory = sqlite3.Row

        results: list[ImportResult] = []
        series_rows = source_conn.execute(
            "SELECT id, name, author, tags, cover_path FROM series ORDER BY id"
        ).fetchall()
        series_id_map: dict[int, int] = {}

        total_episodes = int(
            source_conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        )
        done_episodes = 0

        try:
            for series_row in series_rows:
                old_series_id = int(series_row["id"])
                episodes = source_conn.execute(
                    """
                    SELECT episode_number, episode_name, episode_order, data_path
                    FROM episodes
                    WHERE series_id = ?
                    ORDER BY episode_order ASC, id ASC
                    """,
                    (old_series_id,),
                ).fetchall()

                for episode_row in episodes:
                    data_path = str(episode_row["data_path"] or "")
                    source_dir = self._resolve_backup_episode_dir(backup_data_dir, data_path)
                    if source_dir is None:
                        results.append(
                            ImportResult(
                                imported=False,
                                series_id=-1,
                                episode_number=int(episode_row["episode_number"]),
                                message=f"备份数据缺失，找不到目录: {data_path}",
                            )
                        )
                        done_episodes += 1
                        if progress_callback is not None:
                            progress_callback(done_episodes, max(total_episodes, 1))
                        continue

                    metadata = ImportMetadata(
                        name=str(series_row["name"]),
                        author=str(series_row["author"] or ""),
                        episode_number=int(episode_row["episode_number"]),
                        episode_name=str(episode_row["episode_name"] or ""),
                        episode_order=int(episode_row["episode_order"]),
                        tags=str(series_row["tags"] or ""),
                        cover_source="none",
                    )

                    try:
                        result = self.import_folder(
                            folder=source_dir,
                            metadata=metadata,
                            hash_check=hash_check,
                            duplicate_policy=duplicate_policy,
                        )
                        results.append(result)
                        series_id_map.setdefault(old_series_id, int(result.series_id))
                    except Exception as exc:
                        results.append(
                            ImportResult(
                                imported=False,
                                series_id=-1,
                                episode_number=int(episode_row["episode_number"]),
                                message=f"{metadata.name}-{metadata.episode_name}: {exc}",
                            )
                        )
                    finally:
                        done_episodes += 1
                        if progress_callback is not None:
                            progress_callback(done_episodes, max(total_episodes, 1))

            for series_row in series_rows:
                old_series_id = int(series_row["id"])
                new_series_id = series_id_map.get(old_series_id)
                if new_series_id is None:
                    continue
                self._restore_backup_cover(
                    backup_data_dir,
                    new_series_id,
                    str(series_row["cover_path"] or ""),
                )
            if progress_callback is not None and total_episodes == 0:
                progress_callback(1, 1)
        finally:
            source_conn.close()

        if not results:
            raise ValueError("备份包中未找到可导入的漫画内容")
        return results

    def _resolve_backup_episode_dir(self, backup_data_dir: Path, data_path: str) -> Path | None:
        if not data_path:
            return None

        raw_path = Path(data_path)
        if raw_path.exists() and raw_path.is_dir():
            return raw_path

        imports_root = backup_data_dir / "imports"
        by_name = imports_root / raw_path.name
        if by_name.exists() and by_name.is_dir():
            return by_name

        parts = [part for part in raw_path.parts if part and part not in (".", "..")]
        if "imports" in parts:
            idx = parts.index("imports")
            tail = parts[idx + 1 :]
            if tail:
                by_tail = imports_root.joinpath(*tail)
                if by_tail.exists() and by_tail.is_dir():
                    return by_tail

        return None

    def _restore_backup_cover(self, backup_data_dir: Path, series_id: int, cover_path: str) -> None:
        if not cover_path:
            self._set_series_cover_from_first_image(series_id)
            return
        candidate = backup_data_dir / "covers" / Path(cover_path).name
        if candidate.exists():
            new_cover = store_cover_image(series_id, candidate)
            with self.db.transaction() as conn:
                conn.execute(
                    "UPDATE series SET cover_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (str(new_cover), series_id),
                )
            return
        mapped = self._resolve_backup_episode_dir(backup_data_dir, cover_path)
        if mapped is not None:
            images = list_images_sorted(mapped)
            if images:
                new_cover = store_cover_image(series_id, images[0])
                with self.db.transaction() as conn:
                    conn.execute(
                        "UPDATE series SET cover_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (str(new_cover), series_id),
                    )
                return
        self._set_series_cover_from_first_image(series_id)

    def _set_series_cover_from_first_image(self, series_id: int) -> None:
        row = self.db.conn.execute(
            """
            SELECT img.file_path
            FROM episodes ep
            JOIN images img ON img.episode_id = ep.id
            WHERE ep.series_id = ?
            ORDER BY ep.episode_order ASC, ep.id ASC, img.sort_order ASC
            LIMIT 1
            """,
            (series_id,),
        ).fetchone()
        if row is None:
            return
        path = Path(str(row["file_path"]))
        if not path.exists():
            return
        new_cover = store_cover_image(series_id, path)
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE series SET cover_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (str(new_cover), series_id),
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
            source_cover = Path(str(row[0])) if row and row[0] else images[0]
            cover_path = str(store_cover_image(series_id, source_cover))
        elif metadata.cover_source == "name_author":
            cover_path = str(render_name_author_cover(series_id, metadata.name, metadata.author))
        else:
            cover_path = None

        if cover_path is not None:
            conn.execute(
                "UPDATE series SET cover_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (cover_path, series_id),
            )

    def generate_error_log(self, results: list[ImportResult], output_dir: Path | None = None) -> Path | None:
        """生成导入错误日志
        
        Args:
            results: 导入结果列表
            output_dir: 输出目录，如果为None则使用导入根目录
        
        Returns:
            日志文件路径，如果没有错误则返回None
        """
        # 收集失败的导入
        failed_results = [r for r in results if not r.imported]
        if not failed_results:
            return None
        
        # 确定输出目录
        if output_dir is None:
            output_dir = IMPORT_COPY_ROOT
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成日志文件
        log_file = output_dir / f"error_{int(time.time())}.log"
        
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("漫画导入错误日志\n")
            f.write("=" * 60 + "\n\n")
            
            for result in failed_results:
                f.write(f"集数: {result.episode_number}\n")
                f.write(f"漫画ID: {result.series_id}\n")
                f.write(f"错误信息: {result.message}\n")
                f.write("-" * 60 + "\n")
        
        return log_file
