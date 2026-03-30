from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Callable

from app.database import Database
from app.config import DATA_DIR


class ExportService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def backup_all_data(
        self,
        output_path: Path | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path:
        """备份所有数据为zip文件
        
        Args:
            output_path: 输出路径。如果为None，将在数据目录的上级创建backup文件夹
        
        Returns:
            备份文件的路径
        """
        if output_path is None:
            backup_dir = DATA_DIR.parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = backup_dir / f"manga_backup_{timestamp}.zip"
        
        files = [item for item in DATA_DIR.rglob('*') if item.is_file()]
        total = len(files)

        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for idx, item in enumerate(files, start=1):
                arcname = item.relative_to(DATA_DIR.parent)
                zf.write(item, arcname)
                if progress_callback is not None:
                    progress_callback(idx, total)

        if progress_callback is not None and total == 0:
            progress_callback(1, 1)
        
        return output_path

    def export_series_metadata(self, series_id: int, output_path: Path) -> None:
        """导出单部漫画的元数据为JSON文件"""
        row = self.db.conn.execute(
            "SELECT id, name, author, tags, total_episodes FROM series WHERE id = ?",
            (series_id,),
        ).fetchone()
        
        if row is None:
            raise ValueError(f"漫画ID {series_id} 不存在")
        
        episodes = self.db.conn.execute(
            """
            SELECT episode_number, episode_name, episode_order, image_count
            FROM episodes
            WHERE series_id = ?
            ORDER BY episode_order ASC, id ASC
            """,
            (series_id,),
        ).fetchall()
        
        export_data = {
            "name": str(row["name"]),
            "author": str(row["author"]),
            "tags": str(row["tags"]),
            "total_episodes": int(row["total_episodes"]),
            "episodes": [
                {
                    "number": int(ep["episode_number"]),
                    "name": str(ep["episode_name"] or f"第{int(ep['episode_number'])}集"),
                    "order": int(ep["episode_order"]),
                    "image_count": int(ep["image_count"]),
                }
                for ep in episodes
            ],
            "export_time": datetime.now().isoformat(),
        }
        
        with output_path.open('w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

    def export_series_data(self, series_id: int, output_dir: Path, copy_files: bool = True) -> None:
        """导出单部漫画的完整数据（包括文件）
        
        Args:
            series_id: 漫画ID
            output_dir: 输出目录
            copy_files: 是否复制漫画文件
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 导出元数据
        metadata_file = output_dir / "metadata.json"
        self.export_series_metadata(series_id, metadata_file)
        
        if not copy_files:
            return
        
        # 复制漫画文件
        rows = self.db.conn.execute(
            "SELECT data_path FROM episodes WHERE series_id = ?",
            (series_id,),
        ).fetchall()
        
        data_dir = output_dir / "data"
        for row in rows:
            data_path = row["data_path"]
            if data_path:
                src = Path(str(data_path))
                if src.exists() and src.is_dir():
                    # 复制整个目录结构
                    dest = data_dir / src.name
                    shutil.copytree(src, dest, dirs_exist_ok=True)

    def export_series_pretty(
        self,
        series_id: int,
        output_root: Path,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path:
        row = self.db.conn.execute(
            "SELECT id, name FROM series WHERE id = ?",
            (series_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"漫画ID {series_id} 不存在")

        output_root.mkdir(parents=True, exist_ok=True)
        series_name = self._safe_name(str(row["name"]).strip() or f"series_{series_id}")
        series_dir = output_root / series_name
        if series_dir.exists():
            series_dir = output_root / f"{series_name}_{series_id}"
        series_dir.mkdir(parents=True, exist_ok=True)

        episodes = self.db.conn.execute(
            """
            SELECT id, episode_number, episode_name, episode_order
            FROM episodes
            WHERE series_id = ?
            ORDER BY episode_order ASC, id ASC
            """,
            (series_id,),
        ).fetchall()

        image_counts = self.db.conn.execute(
            """
            SELECT COALESCE(SUM(image_count), 0) AS total
            FROM episodes
            WHERE series_id = ?
            """,
            (series_id,),
        ).fetchone()
        total_images = int(image_counts["total"]) if image_counts is not None else 0
        done_images = 0

        used_episode_names: set[str] = set()
        for ep in episodes:
            ep_id = int(ep["id"])
            episode_name = str(ep["episode_name"] or f"第{int(ep['episode_number'])}集").strip()
            safe_episode_name = self._safe_name(episode_name)
            if safe_episode_name in used_episode_names:
                safe_episode_name = f"{safe_episode_name}_{int(ep['episode_number'])}"
            used_episode_names.add(safe_episode_name)

            episode_dir = series_dir / safe_episode_name
            episode_dir.mkdir(parents=True, exist_ok=True)

            images = self.db.conn.execute(
                """
                SELECT file_name, file_path
                FROM images
                WHERE episode_id = ?
                ORDER BY sort_order ASC, id ASC
                """,
                (ep_id,),
            ).fetchall()

            for img in images:
                src = Path(str(img["file_path"]))
                if not src.exists() or not src.is_file():
                    continue
                internal_name = Path(str(img["file_name"])).name
                target = episode_dir / internal_name
                shutil.copy2(src, target)
                done_images += 1
                if progress_callback is not None and total_images > 0:
                    progress_callback(done_images, total_images)

        metadata_file = series_dir / "metadata.json"
        self.export_series_metadata(series_id, metadata_file)
        if progress_callback is not None and total_images == 0:
            progress_callback(1, 1)
        return series_dir

    def export_group_pretty(self, group_id: int | None, output_root: Path) -> list[Path]:
        if group_id is None:
            rows = self._list_series_ids_by_category("all")
        else:
            rows = self._list_series_ids_by_group(group_id)

        exported: list[Path] = []
        for row in rows:
            exported.append(self.export_series_pretty(int(row["id"]), output_root))
        return exported

    def export_category_pretty(self, category: str, output_root: Path) -> list[Path]:
        rows = self._list_series_ids_by_category(category)
        exported: list[Path] = []
        for row in rows:
            exported.append(self.export_series_pretty(int(row["id"]), output_root))
        return exported

    def _list_series_ids_by_group(self, group_id: int) -> list:
        return self.db.conn.execute(
            """
            SELECT s.id
            FROM series s
            JOIN series_groups sg ON sg.series_id = s.id
            WHERE sg.group_id = ?
            ORDER BY s.updated_at DESC
            """,
            (group_id,),
        ).fetchall()

    def _list_series_ids_by_category(self, category: str) -> list:
        if category == "favorite":
            return self.db.conn.execute(
                "SELECT id FROM series WHERE is_favorite = 1 ORDER BY updated_at DESC"
            ).fetchall()
        if category == "unread":
            return self.db.conn.execute(
                """
                SELECT s.id
                FROM series s
                LEFT JOIN reading_progress rp ON rp.series_id = s.id
                WHERE rp.series_id IS NULL
                ORDER BY s.updated_at DESC
                """
            ).fetchall()
        if category == "read":
            return self.db.conn.execute(
                """
                SELECT s.id
                FROM series s
                JOIN reading_progress rp ON rp.series_id = s.id
                JOIN episodes last_ep ON last_ep.id = rp.current_episode_id
                JOIN (
                    SELECT series_id, MAX(episode_order) AS max_order
                    FROM episodes
                    GROUP BY series_id
                ) max_ep ON max_ep.series_id = s.id
                WHERE last_ep.episode_order >= max_ep.max_order
                ORDER BY s.updated_at DESC
                """
            ).fetchall()
        return self.db.conn.execute("SELECT id FROM series ORDER BY updated_at DESC").fetchall()

    def _safe_name(self, value: str) -> str:
        cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value).strip().strip(".")
        return cleaned or "untitled"
