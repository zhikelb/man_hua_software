from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

from PyQt6.QtGui import QImage, QPixmap

from app.database import Database


class ReaderService:
    def __init__(self, db: Database, max_cache_size: int = 20, preload_count: int = 2) -> None:
        self.db = db
        self.max_cache_size = max_cache_size
        self.preload_count = preload_count
        self.cache: OrderedDict[str, QImage] = OrderedDict()
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.cache_lock = Lock()
        self.current_series_id: int | None = None
        self.image_rows: list[dict] = []
        self.current_index = 0

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=True)

    def open_series(self, series_id: int) -> tuple[QPixmap, str]:
        self.current_series_id = series_id
        self.image_rows = self._load_series_images(series_id)
        if not self.image_rows:
            raise ValueError("该漫画没有可阅读图片")

        resume_image_id = self._get_resume_image_id(series_id)
        if resume_image_id is not None:
            index = next((i for i, row in enumerate(self.image_rows) if row["image_id"] == resume_image_id), 0)
            self.current_index = index
        else:
            self.current_index = 0

        pixmap = self._get_pixmap(self.image_rows[self.current_index]["file_path"])
        self._preload_neighbors()
        return pixmap, self._position_text()

    def next_image(self) -> tuple[QPixmap, str, bool]:
        if self.current_index + 1 < len(self.image_rows):
            self.current_index += 1
            pixmap = self._get_pixmap(self.image_rows[self.current_index]["file_path"])
            self._save_progress()
            self._preload_neighbors()
            return pixmap, self._position_text(), False

        moved = self._jump_to_next_episode()
        if moved:
            pixmap = self._get_pixmap(self.image_rows[self.current_index]["file_path"])
            self._save_progress()
            self._preload_neighbors()
            return pixmap, self._position_text(), False

        return self._get_pixmap(self.image_rows[self.current_index]["file_path"]), self._position_text(), True

    def previous_image(self) -> tuple[QPixmap, str]:
        if self.current_index > 0:
            self.current_index -= 1
            pixmap = self._get_pixmap(self.image_rows[self.current_index]["file_path"])
            self._save_progress()
            self._preload_neighbors()
            return pixmap, self._position_text()

        return self._get_pixmap(self.image_rows[self.current_index]["file_path"]), self._position_text()

    def _load_series_images(self, series_id: int) -> list[dict]:
        rows = self.db.conn.execute(
            """
            SELECT img.id AS image_id, img.file_path, img.sort_order, ep.id AS episode_id, ep.episode_number
            FROM episodes ep
            JOIN images img ON img.episode_id = ep.id
            WHERE ep.series_id = ?
            ORDER BY ep.episode_number ASC, img.sort_order ASC
            """,
            (series_id,),
        ).fetchall()
        return [
            {
                "image_id": int(r["image_id"]),
                "file_path": str(r["file_path"]),
                "sort_order": int(r["sort_order"]),
                "episode_id": int(r["episode_id"]),
                "episode_number": int(r["episode_number"]),
            }
            for r in rows
        ]

    def _get_resume_image_id(self, series_id: int) -> int | None:
        row = self.db.conn.execute(
            "SELECT current_image_id FROM reading_progress WHERE series_id = ?",
            (series_id,),
        ).fetchone()
        return int(row["current_image_id"]) if row else None

    def _load_image(self, file_path: str) -> QImage:
        with self.cache_lock:
            if file_path in self.cache:
                image = self.cache.pop(file_path)
                self.cache[file_path] = image
                return image

        image = QImage(file_path)
        if image.isNull():
            # 损坏或缺失图片时，返回最小占位图，避免阅读器崩溃。
            image = QImage(1, 1, QImage.Format.Format_RGB32)

        with self.cache_lock:
            self.cache[file_path] = image
            while len(self.cache) > self.max_cache_size:
                self.cache.popitem(last=False)
        return image

    def _get_pixmap(self, file_path: str) -> QPixmap:
        image = self._load_image(file_path)
        return QPixmap.fromImage(image)

    def _preload_neighbors(self) -> None:
        futures: list[Future] = []
        for offset in range(1, self.preload_count + 1):
            for idx in (self.current_index + offset, self.current_index - offset):
                if 0 <= idx < len(self.image_rows):
                    path = self.image_rows[idx]["file_path"]
                    with self.cache_lock:
                        exists = path in self.cache
                    if not exists:
                        futures.append(self.executor.submit(self._load_image, path))

        for future in futures:
            future.add_done_callback(lambda _: None)

    def _position_text(self) -> str:
        row = self.image_rows[self.current_index]
        ep = row["episode_number"]
        page = row["sort_order"] + 1
        return f"第{ep}集 · 第{page}页"

    def _save_progress(self) -> None:
        if self.current_series_id is None:
            return

        current = self.image_rows[self.current_index]
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
                (self.current_series_id, current["episode_id"], current["image_id"]),
            )

    def _jump_to_next_episode(self) -> bool:
        if not self.image_rows:
            return False

        current_episode = self.image_rows[self.current_index]["episode_number"]
        next_idx = next(
            (
                i
                for i, row in enumerate(self.image_rows)
                if row["episode_number"] == current_episode + 1 and row["sort_order"] == 0
            ),
            None,
        )
        if next_idx is None:
            return False
        self.current_index = next_idx
        return True

    def get_current_view(self) -> tuple[QPixmap, str]:
        if not self.image_rows:
            raise ValueError("当前未打开漫画")
        current = self.image_rows[self.current_index]
        return self._get_pixmap(current["file_path"]), self._position_text()

    def add_bookmark(self, name: str = "书签") -> None:
        """添加书签"""
        if self.current_series_id is None:
            return
        
        current = self.image_rows[self.current_index]
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO bookmarks(series_id, episode_id, image_id, name)
                   VALUES(?, ?, ?, ?)""",
                (self.current_series_id, current["episode_id"], current["image_id"], name),
            )

    def get_bookmarks(self, series_id: int) -> list[dict]:
        """获取书签列表"""
        rows = self.db.conn.execute(
            """SELECT b.id AS id, b.name AS name, e.episode_number AS episode_number, (img.sort_order + 1) AS page
               FROM bookmarks b
               JOIN episodes e ON b.episode_id = e.id
               JOIN images img ON b.image_id = img.id
               WHERE b.series_id = ?
               ORDER BY b.created_at DESC""",
            (series_id,),
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "name": str(row["name"]),
                "episode": int(row["episode_number"]),
                "page": int(row["page"]),
            }
            for row in rows
        ]

    def delete_bookmark(self, bookmark_id: int) -> None:
        """删除书签"""
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))

    def jump_to_bookmark(self, bookmark_id: int) -> bool:
        """跳转到书签位置"""
        if self.current_series_id is None or not self.image_rows:
            return False

        row = self.db.conn.execute(
            "SELECT image_id FROM bookmarks WHERE id = ? AND series_id = ?",
            (bookmark_id, self.current_series_id),
        ).fetchone()
        if row is None:
            return False

        target_image_id = int(row["image_id"])
        next_idx = next(
            (i for i, image in enumerate(self.image_rows) if image["image_id"] == target_image_id),
            None,
        )
        if next_idx is None:
            return False

        self.current_index = next_idx
        self._save_progress()
        self._preload_neighbors()
        return True

    def jump_to_position(self, episode_number: int, page: int | None = None) -> bool:
        """跳转到特定位置
        
        Args:
            episode_number: 集数
            page: 页码（从1开始），如果为None则跳转到该集的第一页
        
        Returns:
            是否跳转成功
        """
        if not self.image_rows:
            return False
        
        target_sort_order = (page - 1) if page else 0
        next_idx = next(
            (
                i
                for i, row in enumerate(self.image_rows)
                if row["episode_number"] == episode_number and row["sort_order"] == target_sort_order
            ),
            None,
        )
        
        if next_idx is None:
            return False
        
        self.current_index = next_idx
        self._save_progress()
        self._preload_neighbors()
        return True
