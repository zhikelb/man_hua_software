from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from app.config import DB_PATH, ensure_data_dirs, load_config
from app.database import Database
from app.services.import_service import ImportService
from app.services.library_service import LibraryService
from app.services.reader_service import ReaderService
from app.services.export_service import ExportService
from app.ui.main_window import MainWindow


def main() -> int:
    ensure_data_dirs()
    config = load_config()

    db = Database(DB_PATH)
    import_service = ImportService(db)
    library_service = LibraryService(db)
    reader_service = ReaderService(db, preload_count=int(config["reader"].get("preload_count", 2)))
    export_service = ExportService(db)

    app = QApplication(sys.argv)
    window = MainWindow(
        import_service=import_service,
        library_service=library_service,
        reader_service=reader_service,
        export_service=export_service,
        hash_check=bool(config["import"].get("hash_check_on_duplicate", True)),
        duplicate_policy=str(config["import"].get("duplicate_content_policy", "skip")),
        config=config,
    )
    window.show()

    code = app.exec()
    reader_service.close()
    db.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
