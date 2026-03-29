from __future__ import annotations

from pathlib import Path
import shutil
import sqlite3
from dataclasses import dataclass

from app.database import Database
from app.config import IMPORT_COPY_ROOT


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
                   last_ep.episode_number AS last_read_episode,
                   max_ep.max_episode AS max_episode
            FROM series s
            LEFT JOIN reading_progress rp ON rp.series_id = s.id
            LEFT JOIN episodes e ON e.id = rp.current_episode_id
            LEFT JOIN episodes last_ep ON last_ep.id = rp.current_episode_id
            LEFT JOIN (
                SELECT series_id, MAX(episode_number) AS max_episode
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
            sql += " AND rp.series_id IS NOT NULL AND last_read_episode >= max_episode"

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
                if cover_path.exists():
                    cover_path.unlink()
            except Exception:
                pass  # 忽略删除文件时的错误
        
        # 从数据库删除记录（级联删除会自动删除episodes、images等）
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM series WHERE id = ?", (series_id,))

    def get_series_details(self, series_id: int) -> dict | None:
        """获取漫画的详细属性"""
        row = self.db.conn.execute(
            "SELECT id, name, author, tags FROM series WHERE id = ?",
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
                (SELECT COUNT(*) FROM images WHERE episode_id IN 
                    (SELECT id FROM episodes WHERE series_id = ? AND episode_number <= 
                        (SELECT episode_number FROM episodes WHERE id = 
                            (SELECT current_episode_id FROM reading_progress WHERE series_id = ?)
                        )
                    ) AND sort_order <= 
                        (SELECT sort_order FROM images WHERE id = 
                            (SELECT current_image_id FROM reading_progress WHERE series_id = ?)
                        )
                ) AS read_images,
                (SELECT current_episode_id FROM reading_progress WHERE series_id = ?)
            """,
            (series_id, series_id, series_id, series_id, series_id),
        ).fetchone()

        if result is None or result[0] is None:
            return None

        total_images = int(result[0])
        read_images = int(result[1]) if result[1] else 0
        has_progress = result[2] is not None

        if not has_progress or total_images == 0:
            return None

        return (read_images, total_images)

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
            ORDER BY ep.episode_number DESC, img.sort_order DESC
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
            SELECT DISTINCT s.id AS series_id, ep.folder_path, ep.data_path, img.file_path
            FROM series s
            JOIN episodes ep ON ep.series_id = s.id
            LEFT JOIN images img ON img.episode_id = ep.id
            """
        ).fetchall()

        missing_ids: set[int] = set()
        for row in rows:
            series_id = int(row["series_id"])

            folder_path = str(row["folder_path"] or "")
            if folder_path and not Path(folder_path).exists():
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
