from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

from app.database import Database
from app.config import DATA_DIR


class ExportService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def backup_all_data(self, output_path: Path | None = None) -> Path:
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
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for item in DATA_DIR.rglob('*'):
                if item.is_file():
                    arcname = item.relative_to(DATA_DIR.parent)
                    zf.write(item, arcname)
        
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
            "SELECT episode_number, image_count FROM episodes WHERE series_id = ? ORDER BY episode_number",
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
