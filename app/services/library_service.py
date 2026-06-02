from __future__ import annotations

from pathlib import Path
import shutil
import sqlite3
from dataclasses import dataclass

from app.database import Database
from app.config import COVER_ROOT, IMPORT_COPY_ROOT
from app.utils.cover_generator import (
    SOURCE_CACHE_ROOT,
    DISPLAY_CACHE_ROOT,
    clear_cover_display_cache_for_source,
    delete_managed_cover_source,
    get_cover_source_token,
)


@dataclass
class SeriesItem:
    id: int
    name: str
    author: str
    total_episodes: int
    cover_path: str | None
    is_favorite: bool


class LibraryService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list_series(self, category: str = "all", keyword: str = "", sort_by: str = "updated_at", sort_order: str = "desc") -> list[SeriesItem]:
        sql = """
            SELECT s.id, s.name, s.author, s.total_episodes, s.cover_path, s.is_favorite,
                   rp.series_id AS progress_exists,
                   last_ep.episode_order AS last_read_order,
                   max_ep.max_order AS max_order
            FROM series s
            LEFT JOIN reading_progress rp ON rp.series_id = s.id
            LEFT JOIN episodes e ON e.id = rp.current_episode_id
            LEFT JOIN episodes last_ep ON last_ep.id = rp.current_episode_id
            LEFT JOIN (
                SELECT series_id, MAX(episode_order) AS max_order
                FROM episodes
                GROUP BY series_id
            ) max_ep ON max_ep.series_id = s.id
            WHERE 1=1
        """
        params: list[object] = []

        if keyword.strip():
            sql += " AND (s.name LIKE ? OR s.author LIKE ? OR s.tags LIKE ?)"
            like = f"%{keyword.strip()}%"
            params.extend([like, like, like])

        if category == "favorite":
            sql += " AND s.is_favorite = 1"
        elif category == "unread":
            sql += " AND rp.series_id IS NULL"
        elif category == "read":
            sql += " AND rp.series_id IS NOT NULL AND last_read_order >= max_order"

        # 根据排序选项构建ORDER BY子句
        order_col = "s.updated_at"
        if sort_by == "name":
            order_col = "s.name"
        elif sort_by == "author":
            order_col = "s.author"
        elif sort_by == "episodes":
            order_col = "s.total_episodes"
        
        order_dir = "ASC" if sort_order == "asc" else "DESC"
        sql += f" ORDER BY {order_col} {order_dir}"

        rows = self.db.conn.execute(sql, params).fetchall()
        return [
            SeriesItem(
                id=int(r["id"]),
                name=str(r["name"]),
                author=str(r["author"]),
                total_episodes=int(r["total_episodes"]),
                cover_path=r["cover_path"],
                is_favorite=bool(r["is_favorite"]),
            )
            for r in rows
        ]

    def set_favorite(self, series_id: int, is_favorite: bool) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE series SET is_favorite = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (1 if is_favorite else 0, series_id),
            )

    def is_series_fully_read(self, series_id: int) -> bool:
        row = self.db.conn.execute(
            """
            SELECT rp.series_id AS progress_exists,
                   last_ep.episode_order AS last_read_order,
                   max_ep.max_order AS max_order
            FROM series s
            LEFT JOIN reading_progress rp ON rp.series_id = s.id
            LEFT JOIN episodes last_ep ON last_ep.id = rp.current_episode_id
            LEFT JOIN (
                SELECT series_id, MAX(episode_order) AS max_order
                FROM episodes
                GROUP BY series_id
            ) max_ep ON max_ep.series_id = s.id
            WHERE s.id = ?
            """,
            (series_id,),
        ).fetchone()
        if row is None:
            return False
        if row["progress_exists"] is None:
            return False
        return int(row["last_read_order"] or 0) >= int(row["max_order"] or 0)

    def list_custom_groups(self) -> list[sqlite3.Row]:
        return self.db.conn.execute("SELECT id, name FROM user_groups ORDER BY sort_order, id").fetchall()

    def rename_group(self, group_id: int, name: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE user_groups SET name = ? WHERE id = ?",
                (name.strip(), group_id),
            )

    def delete_group(self, group_id: int) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM user_groups WHERE id = ?", (group_id,))

    def list_series_by_group(self, group_id: int) -> list[SeriesItem]:
        rows = self.db.conn.execute(
            """
            SELECT s.id, s.name, s.author, s.total_episodes, s.cover_path, s.is_favorite
            FROM series s
            JOIN series_groups sg ON sg.series_id = s.id
            WHERE sg.group_id = ?
            ORDER BY s.updated_at DESC
            """,
            (group_id,),
        ).fetchall()
        return [
            SeriesItem(
                id=int(r["id"]),
                name=str(r["name"]),
                author=str(r["author"]),
                total_episodes=int(r["total_episodes"]),
                cover_path=r["cover_path"],
                is_favorite=bool(r["is_favorite"]),
            )
            for r in rows
        ]

    def create_group(self, name: str) -> None:
        with self.db.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO user_groups(name) VALUES(?)", (name.strip(),))

    def add_series_to_group(self, series_id: int, group_id: int) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO series_groups(series_id, group_id) VALUES(?, ?)",
                (series_id, group_id),
            )

    def move_series_to_group(self, series_id: int, group_id: int) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM series_groups WHERE series_id = ?", (series_id,))
            conn.execute(
                "INSERT OR IGNORE INTO series_groups(series_id, group_id) VALUES(?, ?)",
                (series_id, group_id),
            )

    def clear_series_group(self, series_id: int) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM series_groups WHERE series_id = ?", (series_id,))

    def get_series_group_id(self, series_id: int) -> int | None:
        row = self.db.conn.execute(
            "SELECT group_id FROM series_groups WHERE series_id = ? ORDER BY added_at DESC LIMIT 1",
            (series_id,),
        ).fetchone()
        if row is None:
            return None
        return int(row["group_id"])

    def migrate_legacy_cover_paths(self) -> int:
        """将旧版 data/covers/cover_*.png 封面索引增量迁移到 data/imports 源图。"""
        rows = self.db.conn.execute(
            "SELECT id, cover_path FROM series WHERE cover_path IS NOT NULL"
        ).fetchall()

        updated = 0
        try:
            cover_root = COVER_ROOT.resolve()
        except Exception:
            cover_root = COVER_ROOT

        with self.db.transaction() as conn:
            for row in rows:
                series_id = int(row["id"])
                raw_cover = str(row["cover_path"] or "").strip()
                if not raw_cover:
                    continue

                path = Path(raw_cover)
                try:
                    resolved = path.resolve()
                except Exception:
                    continue

                try:
                    is_legacy_cover = resolved.is_relative_to(cover_root) and path.name.startswith("cover_")
                except Exception:
                    is_legacy_cover = False
                if not is_legacy_cover:
                    continue

                source = self._find_cover_source_from_imports(series_id)
                if source is None:
                    continue

                conn.execute(
                    "UPDATE series SET cover_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (str(source), series_id),
                )
                updated += 1

        if updated > 0:
            self.cleanup_unused_cover_files()
        return updated

    def _find_cover_source_from_imports(self, series_id: int) -> Path | None:
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
            return None

        path = Path(str(row["file_path"] or "")).resolve()
        try:
            imports_root = IMPORT_COPY_ROOT.resolve()
            if path.is_relative_to(imports_root) and path.exists() and path.is_file():
                return path
        except Exception:
            return None
        return None

    def delete_series(self, series_id: int) -> None:
        """删除漫画及其所有数据
        
        这会清理：
        1. 数据库中的漫画记录、集数、图片
        2. 导入目录中的漫画文件
        3. 封面文件
        """
        # 获取所有相关文件路径
        rows = self.db.conn.execute(
            """
            SELECT ep.data_path, s.cover_path
            FROM episodes ep
            LEFT JOIN series s ON s.id = ep.series_id
            WHERE ep.series_id = ?
            """,
            (series_id,),
        ).fetchall()
        
        # 删除导入的漫画文件
        deleted_paths: list[Path] = []
        for row in rows:
            data_path = row["data_path"]
            if data_path:
                try:
                    path = Path(str(data_path))
                    if path.exists() and path.is_dir():
                        shutil.rmtree(path)
                        deleted_paths.append(path)
                except Exception:
                    pass  # 忽略删除文件时的错误

        # 清理导入根目录下可能遗留的空目录，保持数据目录整洁。
        for deleted in deleted_paths:
            parent = deleted.parent
            while parent != IMPORT_COPY_ROOT and parent.exists() and parent.is_dir():
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        
        # 删除封面文件
        cover_path_result = self.db.conn.execute(
            "SELECT cover_path FROM series WHERE id = ?",
            (series_id,),
        ).fetchone()
        
        if cover_path_result and cover_path_result["cover_path"]:
            try:
                cover_path = Path(str(cover_path_result["cover_path"]))
                clear_cover_display_cache_for_source(cover_path)
                delete_managed_cover_source(cover_path)
            except Exception:
                pass  # 忽略删除文件时的错误
        
        # 从数据库删除记录（级联删除会自动删除episodes、images等）
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM series WHERE id = ?", (series_id,))

        # 删除后清理未使用封面，兼容旧 data 目录中的历史遗留封面。
        self.cleanup_unused_cover_files()

    def get_series_details(self, series_id: int) -> dict | None:
        """获取漫画的详细属性"""
        row = self.db.conn.execute(
            "SELECT id, name, author, tags, cover_path FROM series WHERE id = ?",
            (series_id,),
        ).fetchone()
        if row is None:
            return None
        group_id = self.get_series_group_id(series_id)
        return {
            "id": int(row["id"]),
            "name": str(row["name"]),
            "author": str(row["author"]),
            "tags": str(row["tags"]),
            "cover_path": row["cover_path"],
            "group_id": group_id,
        }

    def edit_series(self, series_id: int, name: str, author: str, tags: str) -> None:
        """编辑漫画属性"""
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE series SET name = ?, author = ?, tags = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (name.strip(), author.strip(), tags.strip(), series_id),
            )

    def get_reading_progress(self, series_id: int) -> tuple[int, int] | None:
        """获取阅读进度 (已读图片数, 总图片数) 或 None 如果未开始阅读"""
        result = self.db.conn.execute(
            """
            SELECT
                (SELECT SUM(image_count) FROM episodes WHERE series_id = ?) AS total_images,
                (
                    SELECT COUNT(*)
                    FROM images img
                    JOIN episodes ep ON ep.id = img.episode_id
                    WHERE ep.series_id = ?
                      AND (
                        ep.episode_order < (
                            SELECT cep.episode_order
                            FROM episodes cep
                            WHERE cep.id = (SELECT current_episode_id FROM reading_progress WHERE series_id = ?)
                        )
                        OR (
                            ep.episode_order = (
                                SELECT cep.episode_order
                                FROM episodes cep
                                WHERE cep.id = (SELECT current_episode_id FROM reading_progress WHERE series_id = ?)
                            )
                            AND img.sort_order <= (
                                SELECT cimg.sort_order
                                FROM images cimg
                                WHERE cimg.id = (SELECT current_image_id FROM reading_progress WHERE series_id = ?)
                            )
                        )
                      )
                ) AS read_images,
                (SELECT current_episode_id FROM reading_progress WHERE series_id = ?)
            """,
            (series_id, series_id, series_id, series_id, series_id, series_id),
        ).fetchone()

        if result is None or result[0] is None:
            return None

        total_images = int(result[0])
        read_images = int(result[1]) if result[1] else 0
        has_progress = result[2] is not None

        if not has_progress or total_images == 0:
            return None

        return (read_images, total_images)

    def get_reading_progress_map(self, series_ids: list[int]) -> dict[int, tuple[int, int] | None]:
        """批量获取阅读进度，减少列表刷新时的数据库查询次数。"""
        if not series_ids:
            return {}

        placeholders = ",".join("?" for _ in series_ids)
        sql = f"""
            WITH target AS (
                SELECT id AS series_id
                FROM series
                WHERE id IN ({placeholders})
            ),
            totals AS (
                SELECT ep.series_id, COALESCE(SUM(ep.image_count), 0) AS total_images
                FROM episodes ep
                WHERE ep.series_id IN ({placeholders})
                GROUP BY ep.series_id
            ),
            rp AS (
                SELECT
                    rp.series_id,
                    cep.episode_order AS current_episode_order,
                    cimg.sort_order AS current_sort_order
                FROM reading_progress rp
                JOIN episodes cep ON cep.id = rp.current_episode_id
                JOIN images cimg ON cimg.id = rp.current_image_id
                WHERE rp.series_id IN ({placeholders})
            ),
            reads AS (
                SELECT ep.series_id, COUNT(*) AS read_images
                FROM episodes ep
                JOIN images img ON img.episode_id = ep.id
                JOIN rp ON rp.series_id = ep.series_id
                WHERE ep.series_id IN ({placeholders})
                  AND (
                    ep.episode_order < rp.current_episode_order
                    OR (
                        ep.episode_order = rp.current_episode_order
                        AND img.sort_order <= rp.current_sort_order
                    )
                  )
                GROUP BY ep.series_id
            )
            SELECT
                t.series_id,
                COALESCE(totals.total_images, 0) AS total_images,
                CASE WHEN rp.series_id IS NULL THEN 0 ELSE 1 END AS has_progress,
                COALESCE(reads.read_images, 0) AS read_images
            FROM target t
            LEFT JOIN totals ON totals.series_id = t.series_id
            LEFT JOIN rp ON rp.series_id = t.series_id
            LEFT JOIN reads ON reads.series_id = t.series_id
        """
        params = series_ids + series_ids + series_ids + series_ids
        rows = self.db.conn.execute(sql, params).fetchall()

        result: dict[int, tuple[int, int] | None] = {sid: None for sid in series_ids}
        for row in rows:
            sid = int(row["series_id"])
            total_images = int(row["total_images"] or 0)
            has_progress = bool(int(row["has_progress"] or 0))
            read_images = int(row["read_images"] or 0)
            if has_progress and total_images > 0:
                result[sid] = (read_images, total_images)
            else:
                result[sid] = None
        return result

    def clear_reading_progress(self, series_id: int) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM reading_progress WHERE series_id = ?", (series_id,))

    def mark_series_as_read(self, series_id: int) -> None:
        row = self.db.conn.execute(
            """
            SELECT img.id AS image_id, ep.id AS episode_id
            FROM episodes ep
            JOIN images img ON img.episode_id = ep.id
            WHERE ep.series_id = ?
            ORDER BY ep.episode_order DESC, ep.episode_number DESC, img.sort_order DESC
            LIMIT 1
            """,
            (series_id,),
        ).fetchone()
        if row is None:
            return

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO reading_progress(series_id, current_episode_id, current_image_id, last_read_at)
                VALUES(?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(series_id) DO UPDATE SET
                    current_episode_id = excluded.current_episode_id,
                    current_image_id = excluded.current_image_id,
                    last_read_at = CURRENT_TIMESTAMP
                """,
                (series_id, int(row["episode_id"]), int(row["image_id"])),
            )

    def mark_series_as_unread(self, series_id: int) -> None:
        """标记漫画为未读（清空阅读进度）"""
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM reading_progress WHERE series_id = ?", (series_id,))

    def prune_missing_series(self) -> int:
        rows = self.db.conn.execute(
            """
            SELECT DISTINCT s.id AS series_id, ep.folder_path, ep.data_path, ep.storage_mode, img.file_path
            FROM series s
            JOIN episodes ep ON ep.series_id = s.id
            LEFT JOIN images img ON img.episode_id = ep.id
            """
        ).fetchall()

        missing_ids: set[int] = set()
        for row in rows:
            series_id = int(row["series_id"])
            storage_mode = str(row["storage_mode"] or "copy")

            folder_path = str(row["folder_path"] or "")
            # 引用模式必须依赖原路径；复制模式不要求原路径仍存在。
            if storage_mode == "reference" and folder_path and not Path(folder_path).exists():
                missing_ids.add(series_id)
                continue

            data_path = row["data_path"]
            if data_path and not Path(str(data_path)).exists():
                missing_ids.add(series_id)
                continue

            file_path = row["file_path"]
            if file_path and not Path(str(file_path)).exists():
                missing_ids.add(series_id)

        if not missing_ids:
            return 0

        with self.db.transaction() as conn:
            for series_id in missing_ids:
                conn.execute("DELETE FROM series WHERE id = ?", (series_id,))

        return len(missing_ids)

    def list_episodes(self, series_id: int) -> list[dict]:
        """获取漫画的所有集数列表"""
        rows = self.db.conn.execute(
            """
            SELECT id, episode_number, episode_name, episode_order, image_count, folder_path
            FROM episodes
            WHERE series_id = ?
            ORDER BY episode_order ASC, id ASC
            """,
            (series_id,),
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "episode_number": int(row["episode_number"]),
                "episode_name": str(row["episode_name"] or f"第{int(row['episode_number'])}集"),
                "episode_order": int(row["episode_order"]),
                "image_count": int(row["image_count"]),
                "folder_path": str(row["folder_path"]),
            }
            for row in rows
        ]

    def update_episodes_metadata(self, series_id: int, updates: list[dict]) -> None:
        """批量更新每一集的集名和顺序"""
        if not updates:
            return

        new_orders = [int(item["episode_order"]) for item in updates]
        if len(new_orders) != len(set(new_orders)):
            raise ValueError("顺序不能重复")

        with self.db.transaction() as conn:
            existing_ids = {
                int(row["id"])
                for row in conn.execute(
                    "SELECT id FROM episodes WHERE series_id = ?",
                    (series_id,),
                ).fetchall()
            }

            for item in updates:
                ep_id = int(item["id"])
                if ep_id not in existing_ids:
                    raise ValueError(f"集记录不存在: {ep_id}")

                conn.execute(
                    """
                    UPDATE episodes
                    SET episode_name = ?, episode_order = ?
                    WHERE id = ? AND series_id = ?
                    """,
                    (
                        str(item["episode_name"]).strip() or f"第{int(item['episode_number'])}集",
                        int(item["episode_order"]),
                        ep_id,
                        series_id,
                    ),
                )

    def update_series_cover(self, series_id: int, cover_path: str | None) -> None:
        """更新漫画封面
        
        Args:
            series_id: 漫画ID
            cover_path: 新封面路径，如果为None则清空封面
        """
        old_path_text = ""
        with self.db.transaction() as conn:
            old_cover = conn.execute(
                "SELECT cover_path FROM series WHERE id = ?",
                (series_id,),
            ).fetchone()
            old_path_text = str(old_cover["cover_path"] or "").strip() if old_cover else ""

            if cover_path:
                new_path = Path(str(cover_path))
                conn.execute(
                    "UPDATE series SET cover_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (cover_path, series_id),
                )
            else:
                conn.execute(
                    "UPDATE series SET cover_path = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (series_id,),
                )

        if old_path_text:
            old_path = Path(old_path_text)
            if not cover_path or str(new_path) != old_path_text:
                clear_cover_display_cache_for_source(old_path)
                delete_managed_cover_source(old_path)

        # 每次封面变更后进行一次轻量清理，防止旧封面持续堆积。
        self.cleanup_unused_cover_files()

    def set_series_cover_index(self, series_id: int, cover_path: str) -> None:
        """轻量更新封面索引路径，不触发封面文件清理。"""
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE series SET cover_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (cover_path, series_id),
            )

    def cleanup_unused_cover_files(self) -> int:
        used_internal_paths: set[Path] = set()
        used_source_tokens: set[str] = set()
        try:
            cover_root = COVER_ROOT.resolve()
        except Exception:
            cover_root = COVER_ROOT

        rows = self.db.conn.execute("SELECT cover_path FROM series WHERE cover_path IS NOT NULL").fetchall()
        for row in rows:
            raw = str(row["cover_path"] or "").strip()
            if not raw:
                continue
            path = Path(raw)
            try:
                resolved = path.resolve()
            except Exception:
                continue
            used_source_tokens.add(get_cover_source_token(resolved))
            try:
                if resolved.is_relative_to(cover_root):
                    used_internal_paths.add(resolved)
            except Exception:
                continue

        removed = 0
        removed_cover_sources: list[Path] = []
        managed_candidates: list[Path] = []
        if SOURCE_CACHE_ROOT.exists():
            managed_candidates.extend(SOURCE_CACHE_ROOT.glob("source_*.png"))
            managed_candidates.extend(SOURCE_CACHE_ROOT.glob("source_name_author_*.png"))
        # 兼容旧版 data/covers/cover_*.png：增量清理历史文件。
        if COVER_ROOT.exists():
            managed_candidates.extend(COVER_ROOT.glob("cover_*.png"))

        for file in managed_candidates:
            try:
                if not file.is_file():
                    continue
                resolved = file.resolve()
                if resolved in used_internal_paths:
                    continue
                file.unlink()
                removed_cover_sources.append(file)
                removed += 1
            except Exception:
                continue

        if removed_cover_sources:
            # 定向清理对应封面的展示缓存，避免全量缓存清空导致大库抖动。
            for source in removed_cover_sources:
                try:
                    clear_cover_display_cache_for_source(source)
                except Exception:
                    continue

        # 清理 _scaled 下不再被引用的展示缓存文件，防止旧版本升级后堆积。
        used_scaled_files: set[Path] = set()
        for path in used_internal_paths:
            try:
                if path.is_file() and path.resolve().is_relative_to(DISPLAY_CACHE_ROOT.resolve()):
                    used_scaled_files.add(path.resolve())
            except Exception:
                continue

        if DISPLAY_CACHE_ROOT.exists():
            for cached in DISPLAY_CACHE_ROOT.rglob("cover_*.png"):
                try:
                    if not cached.is_file():
                        continue
                    resolved = cached.resolve()
                    if resolved in used_scaled_files:
                        continue
                    stem_parts = cached.stem.split("_")
                    if len(stem_parts) >= 3 and stem_parts[1] in used_source_tokens:
                        continue
                    cached.unlink()
                    removed += 1
                except Exception:
                    continue

        return removed
