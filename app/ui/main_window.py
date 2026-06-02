from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QMimeData, QPoint, QSize, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QCloseEvent, QDrag, QIcon, QKeyEvent, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QKeySequenceEdit,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.config import save_config
from app.services.import_service import ImportService
from app.services.library_service import LibraryService, SeriesItem
from app.services.reader_service import ReaderService
from app.services.export_service import ExportService
from app.services.import_service import ImportMetadata
from app.ui.import_dialog import ImportDialog
from app.ui.edit_series_dialog import EditSeriesDialog
from app.ui.reader_window import ReaderWindow
from app.utils.cover_generator import get_library_cover_cache_path, store_cover_image
from app.utils.global_hotkey import WindowsGlobalHotkeyManager


class DragDropArea(QWidget):
    """支持拖放导入的区域"""
    folder_dropped = pyqtSignal(Path)
    
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setStyleSheet(
            """
            DragDropArea {
                border: 2px dashed #999;
                border-radius: 5px;
                background-color: #f5f5f5;
            }
            DragDropArea:hover {
                background-color: #e0e0e0;
            }
            """
        )
        
        layout = QVBoxLayout(self)
        label = QLabel("拖入文件夹导入漫画\n或点击下方\"导入漫画\"按钮")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(label)
        self.setMinimumHeight(60)
    
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dropEvent(self, event) -> None:
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                self.folder_dropped.emit(path)
                event.acceptProposedAction()
                return
        
        event.ignore()


class GroupListWidget(QListWidget):
    series_dropped_to_category = pyqtSignal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragEnabled(False)
        self.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.setDefaultDropAction(Qt.DropAction.IgnoreAction)

    def dragEnterEvent(self, event) -> None:
        mime = event.mimeData()
        if mime and mime.hasText() and mime.text().startswith("series:"):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        mime = event.mimeData()
        if mime and mime.hasText() and mime.text().startswith("series:"):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:
        mime = event.mimeData()
        if not (mime and mime.hasText() and mime.text().startswith("series:")):
            event.ignore()
            return

        payload = mime.text().split(":", 1)
        if len(payload) != 2 or not payload[1].isdigit():
            event.ignore()
            return

        target_item = self.itemAt(event.position().toPoint())
        if target_item is None:
            event.ignore()
            return

        row = self.row(target_item)
        target_code = 0
        if row <= 3:
            target_code = -(row + 1)
        else:
            group_id = target_item.data(Qt.ItemDataRole.UserRole)
            if group_id is None:
                event.ignore()
                return
            target_code = int(group_id)

        self.series_dropped_to_category.emit(int(payload[1]), target_code)
        event.acceptProposedAction()


class SeriesListWidget(QListWidget):
    def __init__(self) -> None:
        super().__init__()
        self._drag_start_pos: QPoint | None = None
        self._drag_series_id: int | None = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            item = self.itemAt(event.pos())
            if item is not None:
                series_id = item.data(Qt.ItemDataRole.UserRole)
                if series_id is not None:
                    self._drag_start_pos = event.pos()
                    self._drag_series_id = int(series_id)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            event.buttons() & Qt.MouseButton.RightButton
            and self._drag_start_pos is not None
            and self._drag_series_id is not None
        ):
            distance = (event.pos() - self._drag_start_pos).manhattanLength()
            if distance >= QApplication.startDragDistance():
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(f"series:{self._drag_series_id}")
                drag.setMimeData(mime)
                drag.exec(Qt.DropAction.CopyAction)
                self._drag_start_pos = None
                self._drag_series_id = None
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._drag_start_pos = None
            self._drag_series_id = None
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    def __init__(
        self,
        import_service: ImportService,
        library_service: LibraryService,
        reader_service: ReaderService,
        export_service: ExportService,
        hash_check: bool,
        duplicate_policy: str,
        config: dict[str, Any],
    ) -> None:
        super().__init__()
        self.import_service = import_service
        self.library_service = library_service
        self.reader_service = reader_service
        self.export_service = export_service
        self.hash_check = hash_check
        self.duplicate_policy = duplicate_policy
        self.config = config
        self.reader_windows: list[ReaderWindow] = []
        self.global_hotkey_manager: WindowsGlobalHotkeyManager | None = None
        self._last_prune_check_at = monotonic()
        self._prune_interval_seconds = 45.0
        self._cover_icon_cache: dict[tuple[str, int, int, float], QIcon] = {}
        self._fallback_icon_cache: dict[tuple[int, int], QIcon] = {}
        self._cover_fill_rows: list[int] = []
        self._cover_fill_index = 0
        self._lazy_cover_fill_on_next_reload = True
        self._cover_fill_timer = QTimer(self)
        self._cover_fill_timer.setSingleShot(True)
        self._cover_fill_timer.timeout.connect(self._process_cover_fill_batch)

        self.setWindowTitle("漫画软件 MVP")
        self.resize(1200, 800)

        self.current_category = "all"
        self.current_custom_group_id: int | None = None

        self._setup_ui()
        self._setup_global_hotkeys()
        QTimer.singleShot(0, self._initial_load)

    def _initial_load(self) -> None:
        migrated = self.library_service.migrate_legacy_cover_paths()
        if migrated > 0:
            self.statusBar().showMessage(f"已迁移 {migrated} 条旧封面索引到 imports 源图", 5000)
        self.reload_library()

    def _event_to_shortcut(self, event: QKeyEvent) -> str:
        if event.key() in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            return ""
        seq = QKeySequence(event.keyCombination())
        return seq.toString(QKeySequence.SequenceFormat.PortableText)

    def _show_main_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _toggle_main_window(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self._show_main_window()

    def _setup_global_hotkeys(self) -> bool:
        reader_cfg = self.config.setdefault("reader", {})
        key_cfg = reader_cfg.setdefault("key_bindings", {})
        seq = str(
            (
                key_cfg.get("global_toggle_window", key_cfg.get("global_show_window", ["Ctrl+Alt+M"]))
                or ["Ctrl+Alt+M"]
            )[0]
        )

        if self.global_hotkey_manager is None:
            self.global_hotkey_manager = WindowsGlobalHotkeyManager()
        else:
            self.global_hotkey_manager.unregister_all()

        ok = self.global_hotkey_manager.register_shortcut(seq, self._toggle_main_window)
        if not ok:
            self.statusBar().showMessage("全局快捷键注册失败，可能已被占用", 5000)
            return False
        return True

    def _normalized_shortcuts(self, key_cfg: dict[str, Any], key: str, default_keys: list[str]) -> set[str]:
        raw = key_cfg.get(key, default_keys)
        if isinstance(raw, str):
            values = [raw]
        elif isinstance(raw, list):
            values = [str(v) for v in raw]
        else:
            values = default_keys
        return {v.strip() for v in values if v and v.strip()}

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key_cfg = self.config.setdefault("reader", {}).setdefault("key_bindings", {})
        toggle_shortcuts = self._normalized_shortcuts(
            key_cfg,
            "toggle_window",
            key_cfg.get("show_window", ["Ctrl+Shift+S"]),
        )

        pressed = self._event_to_shortcut(event)
        if pressed in toggle_shortcuts:
            self._toggle_main_window()
            return

        super().keyPressEvent(event)

    def _apply_series_grid_metrics(self) -> None:
        ui_cfg = self.config.setdefault("ui", {})
        icon_width = int(ui_cfg.get("icon_size", 140))
        icon_height = int(icon_width * 1.357)
        grid_width = int(ui_cfg.get("grid_cell_width", max(icon_width + 24, 168)))
        grid_height = int(ui_cfg.get("grid_cell_height", icon_height + 90))

        self.series_list.setIconSize(QSize(icon_width, icon_height))
        self.series_list.setGridSize(QSize(grid_width, grid_height))
        self._cover_icon_cache.clear()
        self._fallback_icon_cache.clear()

    def _setup_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)

        splitter = QSplitter()
        layout.addWidget(splitter)

        side = QWidget()
        side_layout = QVBoxLayout(side)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索漫画/作者/标签...")
        self.search_edit.textChanged.connect(self.reload_library)

        self.import_button = QPushButton("导入漫画")
        self.import_button.clicked.connect(self.open_import_dialog)

        add_group_button = QPushButton("新建分组")
        add_group_button.clicked.connect(self.add_group)

        manage_group_button = QPushButton("管理分组")
        manage_group_button.clicked.connect(self.open_group_manager_dialog)

        self.category_list = GroupListWidget()
        self.category_list.addItem("全部")
        self.category_list.addItem("最喜欢")
        self.category_list.addItem("未读")
        self.category_list.addItem("已读")
        self.category_list.currentRowChanged.connect(self.on_category_changed)
        self.category_list.series_dropped_to_category.connect(self.on_series_dropped_to_category)

        side_layout.addWidget(self.search_edit)
        side_layout.addWidget(self.import_button)
        side_layout.addWidget(add_group_button)
        side_layout.addWidget(manage_group_button)
        side_layout.addWidget(QLabel("分类"))
        side_layout.addWidget(self.category_list)

        center = QWidget()
        center_layout = QVBoxLayout(center)

        # 添加拖放导入区域
        self.drag_drop_area = DragDropArea()
        self.drag_drop_area.folder_dropped.connect(self.on_folder_dropped)
        center_layout.addWidget(self.drag_drop_area)

        self.series_list = SeriesListWidget()
        self.series_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.series_list.setMovement(QListWidget.Movement.Static)
        self.series_list.setWrapping(True)
        self.series_list.setWordWrap(True)
        self.series_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.series_list.setSpacing(14)
        self._apply_series_grid_metrics()
        self.series_list.itemClicked.connect(self.open_reader_for_item)
        self.series_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.series_list.customContextMenuRequested.connect(self.show_series_context_menu)

        center_layout.addWidget(self.series_list)

        splitter.addWidget(side)
        splitter.addWidget(center)
        splitter.setSizes([260, 900])

        self.statusBar().showMessage("就绪")
        self._setup_menus()

    def _set_import_controls_enabled(self, enabled: bool) -> None:
        self.import_button.setEnabled(enabled)
        self.drag_drop_area.setEnabled(enabled)

    def _setup_menus(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("文件")
        import_action = QAction("导入漫画", self)
        import_action.triggered.connect(self.open_import_dialog)
        file_menu.addAction(import_action)

        file_menu.addSeparator()
        backup_action = QAction("备份所有数据", self)
        backup_action.triggered.connect(self.backup_all_data)
        file_menu.addAction(backup_action)

        import_backup_action = QAction("导入备份数据", self)
        import_backup_action.triggered.connect(self.import_backup_data)
        file_menu.addAction(import_backup_action)

        export_series_action = QAction("导出当前漫画", self)
        export_series_action.triggered.connect(self.export_selected_series)
        file_menu.addAction(export_series_action)

        file_menu.addSeparator()
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        settings_menu = menu_bar.addMenu("设置")
        import_settings_action = QAction("导入设置", self)
        import_settings_action.triggered.connect(self.open_import_settings_dialog)
        settings_menu.addAction(import_settings_action)

        reader_key_action = QAction("阅读按键设置", self)
        reader_key_action.triggered.connect(self.open_reader_key_settings_dialog)
        settings_menu.addAction(reader_key_action)

        ui_settings_action = QAction("界面设置", self)
        ui_settings_action.triggered.connect(self.open_ui_settings_dialog)
        settings_menu.addAction(ui_settings_action)

        group_manage_action = QAction("分组管理", self)
        group_manage_action.triggered.connect(self.open_group_manager_dialog)
        settings_menu.addAction(group_manage_action)

    def backup_all_data(self) -> None:
        """备份所有数据"""
        try:
            def on_progress(done: int, total: int) -> None:
                percent = int((done / total) * 100) if total > 0 else 100
                self.statusBar().showMessage(f"备份中... {done}/{total} ({percent}%)", 0)
                QApplication.processEvents()

            self.statusBar().showMessage("备份中...", 0)
            QApplication.processEvents()
            backup_path = self.export_service.backup_all_data(progress_callback=on_progress)
            QMessageBox.information(
                self,
                "备份完成",
                f"所有数据已备份到:\n{backup_path}",
                QMessageBox.StandardButton.Ok,
            )
            self.statusBar().showMessage("备份完成", 3000)
        except Exception as exc:
            self._show_error("备份失败", str(exc))

    def export_selected_series(self) -> None:
        """导出漫画或分组"""
        dialog = QDialog(self)
        dialog.setWindowTitle("导出当前漫画")
        dialog.resize(560, 460)
        layout = QVBoxLayout(dialog)

        mode_combo = QComboBox()
        mode_combo.addItem("导出单部漫画", "series")
        mode_combo.addItem("导出分组", "group")
        layout.addWidget(QLabel("导出类型"))
        layout.addWidget(mode_combo)

        series_list = QListWidget()
        series_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for idx in range(self.series_list.count()):
            src_item = self.series_list.item(idx)
            series_id = src_item.data(Qt.ItemDataRole.UserRole)
            series_name = str(src_item.data(Qt.ItemDataRole.UserRole + 1) or "").strip()
            series_author = str(src_item.data(Qt.ItemDataRole.UserRole + 2) or "").strip()
            if series_id is None:
                continue
            item = QListWidgetItem(f"{series_name}  (作者: {series_author or '未知'})")
            item.setData(Qt.ItemDataRole.UserRole, int(series_id))
            series_list.addItem(item)

        group_list = QListWidget()
        group_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        all_item = QListWidgetItem("全部漫画")
        all_item.setData(Qt.ItemDataRole.UserRole, ("category", "all"))
        group_list.addItem(all_item)

        fav_item = QListWidgetItem("最喜欢")
        fav_item.setData(Qt.ItemDataRole.UserRole, ("category", "favorite"))
        group_list.addItem(fav_item)

        unread_item = QListWidgetItem("未读")
        unread_item.setData(Qt.ItemDataRole.UserRole, ("category", "unread"))
        group_list.addItem(unread_item)

        read_item = QListWidgetItem("已读")
        read_item.setData(Qt.ItemDataRole.UserRole, ("category", "read"))
        group_list.addItem(read_item)

        for group in self.library_service.list_custom_groups():
            item = QListWidgetItem(f"分组: {group['name']}")
            item.setData(Qt.ItemDataRole.UserRole, ("group", int(group["id"])))
            group_list.addItem(item)
        group_list.setCurrentRow(0)

        layout.addWidget(QLabel("漫画列表"))
        layout.addWidget(series_list)
        layout.addWidget(QLabel("分组列表"))
        layout.addWidget(group_list)

        def sync_visibility() -> None:
            mode = str(mode_combo.currentData())
            is_series = mode == "series"
            series_list.setVisible(is_series)
            group_list.setVisible(not is_series)

        mode_combo.currentIndexChanged.connect(sync_visibility)
        sync_visibility()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        export_dir = QFileDialog.getExistingDirectory(
            self,
            "选择导出目录",
            str(Path.home()),
        )

        if not export_dir:
            return

        try:
            mode = str(mode_combo.currentData())
            output_root = Path(export_dir)
            if mode == "series":
                selected_items = series_list.selectedItems()
                if not selected_items:
                    QMessageBox.warning(self, "提示", "请至少选择一部漫画")
                    return
                total = len(selected_items)
                exported_paths: list[Path] = []
                for idx, selected in enumerate(selected_items, start=1):
                    series_id = int(selected.data(Qt.ItemDataRole.UserRole))
                    self.statusBar().showMessage(f"导出中... {idx}/{total}", 0)
                    QApplication.processEvents()

                    def on_progress(done: int, count: int) -> None:
                        self.statusBar().showMessage(
                            f"导出中... {idx}/{total} · 图片 {done}/{count}",
                            0,
                        )
                        QApplication.processEvents()

                    exported_paths.append(
                        self.export_service.export_series_pretty(series_id, output_root, progress_callback=on_progress)
                    )
                msg = f"导出完成，共导出 {len(exported_paths)} 部漫画\n目录: {output_root}"
            else:
                selected = group_list.currentItem()
                if selected is None:
                    QMessageBox.warning(self, "提示", "请选择要导出的分组")
                    return

                selected_data = selected.data(Qt.ItemDataRole.UserRole)
                exported_paths: list[Path]
                if isinstance(selected_data, tuple) and len(selected_data) == 2:
                    kind, value = selected_data
                    if kind == "group":
                        exported_paths = self.export_service.export_group_pretty(int(value), output_root)
                    else:
                        exported_paths = self.export_service.export_category_pretty(str(value), output_root)
                else:
                    exported_paths = self.export_service.export_category_pretty("all", output_root)
                msg = f"导出完成，共导出 {len(exported_paths)} 部漫画\n目录: {output_root}"

            QMessageBox.information(
                self,
                "导出完成",
                msg,
                QMessageBox.StandardButton.Ok,
            )
            self.statusBar().showMessage("导出完成", 3000)
        except Exception as exc:
            self._show_error("导出失败", str(exc))

    def import_backup_data(self) -> None:
        zip_file, _ = QFileDialog.getOpenFileName(
            self,
            "选择备份文件(可选)",
            str(Path.home()),
            "备份压缩包 (*.zip);;所有文件 (*.*)",
        )

        source_path: Path | None = None
        if zip_file:
            source_path = Path(zip_file)
        else:
            folder = QFileDialog.getExistingDirectory(self, "选择备份目录(可选)", str(Path.home()))
            if folder:
                source_path = Path(folder)

        if source_path is None:
            return

        try:
            self._set_import_controls_enabled(False)
            self.statusBar().showMessage("导入备份数据中...", 0)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            QApplication.processEvents()

            results = self.import_service.import_backup_data(
                source=source_path,
                hash_check=self.hash_check,
                duplicate_policy="skip",
                progress_callback=lambda d, t: (self.statusBar().showMessage(f"导入备份数据中... {d}/{t}", 0), QApplication.processEvents()),
            )
            self.reload_library()

            imported_count = sum(1 for r in results if r.imported)
            failed_count = sum(1 for r in results if not r.imported)
            log_file = self.import_service.generate_error_log(results, Path.home()) if failed_count > 0 else None

            msg = f"备份导入完成：成功 {imported_count} 集，失败/跳过 {failed_count} 集"
            if log_file:
                msg += f"\n\n错误报告：\n{log_file}"
            QMessageBox.information(self, "导入备份数据", msg)
            self.statusBar().showMessage(msg, 5000)
        except Exception as exc:
            self._show_error("导入备份失败", str(exc))
        finally:
            QApplication.restoreOverrideCursor()
            self._set_import_controls_enabled(True)

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def open_import_dialog(self) -> None:
        dialog = ImportDialog(self)
        if dialog.exec() != ImportDialog.DialogCode.Accepted:
            return

        request = dialog.build_request()

        try:
            self._set_import_controls_enabled(False)
            self.statusBar().showMessage("导入中...", 0)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
            results = self.import_service.import_auto_folder(
                request.folder,
                author=request.author,
                tags=request.tags,
                hash_check=self.hash_check,
                duplicate_policy=self.duplicate_policy,
                custom_name=request.custom_name,
                progress_callback=lambda d, t: (self.statusBar().showMessage(f"导入中... {d}/{t}", 0), QApplication.processEvents()),
            )

            self.reload_library()

            imported_count = sum(1 for r in results if r.imported)
            failed_count = sum(1 for r in results if not r.imported)
            
            # 如果有失败的导入，生成错误日志
            if failed_count > 0:
                log_file = self.import_service.generate_error_log(results, request.folder)
                message = f"导入完成：成功 {imported_count} 集，跳过/失败 {failed_count} 集"
                if log_file:
                    message += f"\n\n错误日志已生成：\n{log_file}"
                    self.statusBar().showMessage(f"{message}", 5000)
                    QMessageBox.information(self, "导入完成", message)
                else:
                    self.statusBar().showMessage(message, 4500)
            else:
                self.statusBar().showMessage(f"导入完成：成功 {imported_count} 集", 3500)
        except Exception as exc:
            self._show_error("导入失败", str(exc))
        finally:
            QApplication.restoreOverrideCursor()
            self._set_import_controls_enabled(True)

    def open_import_settings_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("导入设置")
        layout = QVBoxLayout(dialog)

        form = QFormLayout()
        hash_check = QCheckBox("启用重复内容哈希检测")
        hash_check.setChecked(self.hash_check)

        duplicate_policy = QComboBox()
        duplicate_policy.addItem("重复内容跳过", "skip")
        duplicate_policy.addItem("重复内容报错", "error")
        duplicate_policy.addItem("允许重复内容", "allow")
        idx = duplicate_policy.findData(self.duplicate_policy)
        if idx >= 0:
            duplicate_policy.setCurrentIndex(idx)

        form.addRow("哈希检测", hash_check)
        form.addRow("重复策略", duplicate_policy)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.hash_check = hash_check.isChecked()
        self.duplicate_policy = str(duplicate_policy.currentData())

        import_cfg = self.config.setdefault("import", {})
        import_cfg["hash_check_on_duplicate"] = self.hash_check
        import_cfg["duplicate_content_policy"] = self.duplicate_policy
        save_config(self.config)

    def open_ui_settings_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("界面设置")
        dialog.resize(400, 250)
        layout = QVBoxLayout(dialog)

        form = QFormLayout()

        # 图标大小设置
        icon_size_spin = QSpinBox()
        icon_size_spin.setMinimum(80)
        icon_size_spin.setMaximum(300)
        icon_size_spin.setValue(int(self.config["ui"].get("icon_size", 140)))
        icon_size_spin.setToolTip("漫画表示图标的宽度 (像素)")

        grid_width_spin = QSpinBox()
        grid_width_spin.setMinimum(140)
        grid_width_spin.setMaximum(500)
        grid_width_spin.setValue(int(self.config["ui"].get("grid_cell_width", 180)))

        grid_height_spin = QSpinBox()
        grid_height_spin.setMinimum(180)
        grid_height_spin.setMaximum(700)
        grid_height_spin.setValue(int(self.config["ui"].get("grid_cell_height", 290)))
        
        # 排序方式设置
        sort_by_combo = QComboBox()
        sort_by_combo.addItem("最近更新", "updated_at")
        sort_by_combo.addItem("漫画名称", "name")
        sort_by_combo.addItem("作者", "author")
        sort_by_combo.addItem("集数", "episodes")
        
        current_sort = str(self.config["ui"].get("sort_by", "updated_at"))
        idx = sort_by_combo.findData(current_sort)
        if idx >= 0:
            sort_by_combo.setCurrentIndex(idx)
        
        # 排序顺序设置
        sort_order_combo = QComboBox()
        sort_order_combo.addItem("降序 (从新到旧)", "desc")
        sort_order_combo.addItem("升序 (从旧到新)", "asc")
        
        current_order = str(self.config["ui"].get("sort_order", "desc"))
        idx = sort_order_combo.findData(current_order)
        if idx >= 0:
            sort_order_combo.setCurrentIndex(idx)
        
        form.addRow("图标大小(宽度)", icon_size_spin)
        form.addRow("网格单元宽度", grid_width_spin)
        form.addRow("网格单元高度", grid_height_spin)
        form.addRow("排序方式", sort_by_combo)
        form.addRow("排序顺序", sort_order_combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        ui_cfg = self.config.setdefault("ui", {})
        ui_cfg["icon_size"] = icon_size_spin.value()
        ui_cfg["grid_cell_width"] = grid_width_spin.value()
        ui_cfg["grid_cell_height"] = grid_height_spin.value()
        ui_cfg["sort_by"] = sort_by_combo.currentData()
        ui_cfg["sort_order"] = sort_order_combo.currentData()
        save_config(self.config)

        self._apply_series_grid_metrics()
        self.reload_library()
        self.statusBar().showMessage("界面设置已更新", 3000)

    def open_reader_key_settings_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("快捷键设置")
        dialog.resize(500, 300)
        layout = QVBoxLayout(dialog)

        form = QFormLayout()
        reader_cfg = self.config.setdefault("reader", {})
        key_cfg = reader_cfg.setdefault("key_bindings", {})

        hide_window_edit = QKeySequenceEdit()
        hide_window_edit.setKeySequence(
            QKeySequence(
                str(
                    (
                        key_cfg.get("toggle_window", key_cfg.get("show_window", ["Ctrl+Shift+S"]))
                        or ["Ctrl+Shift+S"]
                    )[0]
                )
            )
        )

        fullscreen_edit = QKeySequenceEdit()
        fullscreen_edit.setKeySequence(
            QKeySequence(
                str(
                    (
                        key_cfg.get("reader_toggle_fullscreen", key_cfg.get("reader_fullscreen", ["F"]))
                        or ["F"]
                    )[0]
                )
            )
        )

        note = QLabel("说明：方向键与 PgUp/PgDn 默认翻页且不可更改。点击输入框后直接按下按键/组合键即可记录。")
        note.setWordWrap(True)

        global_show_edit = QKeySequenceEdit()
        global_show_edit.setKeySequence(
            QKeySequence(
                str(
                    (
                        key_cfg.get("global_toggle_window", key_cfg.get("global_show_window", ["Ctrl+Alt+M"]))
                        or ["Ctrl+Alt+M"]
                    )[0]
                )
            )
        )

        form.addRow("软件显示/隐藏(应用内切换)", hide_window_edit)
        form.addRow("软件显示/隐藏(全局切换)", global_show_edit)
        form.addRow("阅读窗口最大化/窗口化", fullscreen_edit)
        layout.addWidget(note)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        toggle_seq = hide_window_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        global_show_seq = global_show_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        fullscreen_seq = fullscreen_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)

        toggle_seq = toggle_seq or "Ctrl+Shift+S"
        global_show_seq = global_show_seq or "Ctrl+Alt+M"
        fullscreen_seq = fullscreen_seq or "F"

        fixed_reader_keys = {
            "Right",
            "Left",
            "Up",
            "Down",
            "PgUp",
            "PgDown",
            "PageUp",
            "PageDown",
            "Space",
        }
        if fullscreen_seq in fixed_reader_keys:
            QMessageBox.warning(self, "按键冲突", "阅读窗口切换键与固定翻页键冲突，请更换按键")
            return

        if len({toggle_seq, global_show_seq, fullscreen_seq}) < 3:
            QMessageBox.warning(self, "按键冲突", "快捷键之间存在冲突，请设置为不同按键")
            return

        key_cfg["toggle_window"] = [toggle_seq]
        key_cfg["global_toggle_window"] = [global_show_seq]
        key_cfg["reader_toggle_fullscreen"] = [fullscreen_seq]

        # 兼容旧配置字段，统一同步为单键切换模型。
        key_cfg["hide_window"] = [toggle_seq]
        key_cfg["show_window"] = [toggle_seq]
        key_cfg["global_show_window"] = [global_show_seq]
        key_cfg["reader_fullscreen"] = [fullscreen_seq]
        key_cfg["reader_windowed"] = [fullscreen_seq]

        save_config(self.config)
        if not self._setup_global_hotkeys():
            QMessageBox.warning(self, "全局快捷键冲突", "全局快捷键注册失败，可能被其他软件占用")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.global_hotkey_manager is not None:
            self.global_hotkey_manager.unregister_all()
        super().closeEvent(event)

    def reload_library(self) -> None:
        now = monotonic()
        if now - self._last_prune_check_at >= self._prune_interval_seconds:
            removed = self.library_service.prune_missing_series()
            self._last_prune_check_at = now
            if removed > 0:
                self.statusBar().showMessage(f"检测到 {removed} 部漫画源文件已丢失，已自动移除", 5000)

        self._reload_custom_groups()
        keyword = self.search_edit.text().strip()
        
        sort_by = str(self.config["ui"].get("sort_by", "updated_at"))
        sort_order = str(self.config["ui"].get("sort_order", "desc"))

        if self.current_category == "group" and self.current_custom_group_id is not None:
            items = self.library_service.list_series_by_group(self.current_custom_group_id)
        else:
            items = self.library_service.list_series(self.current_category, keyword, sort_by, sort_order)

        series_ids = [item.id for item in items]
        progress_map = self.library_service.get_reading_progress_map(series_ids)

        self.series_list.clear()
        use_lazy_fill = self._lazy_cover_fill_on_next_reload
        for item in items:
            self.series_list.addItem(self._build_series_item(item, progress_map.get(item.id), use_lazy_fill))

        if use_lazy_fill:
            self._schedule_cover_fill(items)
        else:
            self.series_list.viewport().update()

    def _schedule_cover_fill(self, _items: list[SeriesItem]) -> None:
        if self._cover_fill_timer.isActive():
            self._cover_fill_timer.stop()
        self._cover_fill_rows = list(range(self.series_list.count()))
        self._cover_fill_index = 0
        if self._cover_fill_rows:
            self._cover_fill_timer.start(0)

    def _process_cover_fill_batch(self) -> None:
        if not self._cover_fill_rows:
            return

        batch_size = 8
        count = self.series_list.count()
        end_index = min(self._cover_fill_index + batch_size, len(self._cover_fill_rows))
        for idx in range(self._cover_fill_index, end_index):
            row = self._cover_fill_rows[idx]
            if row >= count:
                continue
            item = self.series_list.item(row)
            if item is None:
                continue
            cover_path = str(item.data(Qt.ItemDataRole.UserRole + 5) or "").strip()
            if not cover_path:
                continue
            item.setIcon(self._build_cover_icon(cover_path))

        self._cover_fill_index = end_index
        if self._cover_fill_index < len(self._cover_fill_rows):
            self._cover_fill_timer.start(12)
        else:
            self._lazy_cover_fill_on_next_reload = False
            self.series_list.viewport().update()

    def _build_series_item(
        self,
        series: SeriesItem,
        progress: tuple[int, int] | None,
        lazy_icon: bool,
    ) -> QListWidgetItem:
        title = self._compose_series_title(
            name=series.name,
            author=series.author,
            total_episodes=series.total_episodes,
            is_favorite=series.is_favorite,
            progress=progress,
        )

        list_item = QListWidgetItem(title)
        list_item.setData(Qt.ItemDataRole.UserRole, series.id)
        list_item.setData(Qt.ItemDataRole.UserRole + 1, series.name)
        list_item.setData(Qt.ItemDataRole.UserRole + 2, series.author)
        list_item.setData(Qt.ItemDataRole.UserRole + 3, series.total_episodes)
        list_item.setData(Qt.ItemDataRole.UserRole + 4, series.is_favorite)
        list_item.setData(Qt.ItemDataRole.UserRole + 5, series.cover_path or "")

        if lazy_icon:
            list_item.setIcon(self._build_cover_icon(None))
        else:
            list_item.setIcon(self._build_cover_icon(series.cover_path))
        return list_item

    def _compose_series_title(
        self,
        name: str,
        author: str,
        total_episodes: int,
        is_favorite: bool,
        progress: tuple[int, int] | None,
    ) -> str:
        title = f"{name}\n作者: {author or '未知'}\n共{total_episodes}集"
        if progress:
            read_images, total_images = progress
            percentage = int((read_images / total_images) * 100) if total_images > 0 else 0
            title += f"\n已读{percentage}%"
        if is_favorite:
            title = f"★ {title}"
        return title

    def _build_cover_icon(self, cover_path: str | None) -> QIcon:
        icon_width = int(self.config.setdefault("ui", {}).get("icon_size", 140))
        icon_height = int(icon_width * 1.357)
        if cover_path and Path(cover_path).exists():
            path = Path(cover_path)
            render_path = path
            try:
                render_path = get_library_cover_cache_path(path, max_width=min(icon_width, 199))
            except Exception:
                render_path = path
            mtime = path.stat().st_mtime
            key = (str(path), icon_width, icon_height, mtime)
            cached_icon = self._cover_icon_cache.get(key)
            if cached_icon is not None:
                return cached_icon

            pix = QPixmap(str(render_path))
            if not pix.isNull():
                scaled = pix.scaled(
                    icon_width,
                    icon_height,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                icon = QIcon(scaled)
                self._cover_icon_cache[key] = icon
                return icon

        fallback_key = (icon_width, icon_height)
        fallback_icon = self._fallback_icon_cache.get(fallback_key)
        if fallback_icon is not None:
            return fallback_icon

        fallback = QPixmap(icon_width, icon_height)
        fallback.fill(Qt.GlobalColor.lightGray)
        icon = QIcon(fallback)
        self._fallback_icon_cache[fallback_key] = icon
        return icon

    def open_reader_for_item(self, item: QListWidgetItem) -> None:
        series_id = int(item.data(Qt.ItemDataRole.UserRole))
        series_name = str(item.data(Qt.ItemDataRole.UserRole + 1) or "").strip() or item.text().split("\n", 1)[0].replace("★ ", "")
        try:
            window = ReaderWindow(
                self.reader_service,
                self.library_service,
                series_id,
                series_name,
                self.config.get("reader", {}),
            )
            window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            window.progress_changed.connect(self.on_reader_progress_changed)
            window.cover_changed.connect(self.on_reader_cover_changed)
            window.destroyed.connect(self._cleanup_reader_windows)
            window.show()
            self.reader_windows.append(window)
        except Exception as exc:
            self._show_error("无法打开阅读器", str(exc))

    def _cleanup_reader_windows(self, *_args) -> None:
        alive_windows: list[ReaderWindow] = []
        for window in self.reader_windows:
            if window is None:
                continue
            try:
                if sip.isdeleted(window):
                    continue
                alive_windows.append(window)
            except RuntimeError:
                continue
        self.reader_windows = alive_windows

    def on_reader_progress_changed(self, series_id: int) -> None:
        # 关闭阅读窗口后优先做轻量更新，避免大库全量重载导致UI卡顿。
        QTimer.singleShot(0, lambda sid=series_id: self._update_single_series_progress(sid))

    def on_reader_cover_changed(self, series_id: int) -> None:
        self._cover_icon_cache.clear()
        self._refresh_single_series_cover(series_id)

    def _refresh_single_series_cover(self, series_id: int) -> None:
        for row in range(self.series_list.count()):
            item = self.series_list.item(row)
            item_series_id = item.data(Qt.ItemDataRole.UserRole)
            if item_series_id is None or int(item_series_id) != series_id:
                continue
            details = self.library_service.get_series_details(series_id)
            if details is None:
                return
            cover_path = details.get("cover_path")
            item.setData(Qt.ItemDataRole.UserRole + 5, str(cover_path) if cover_path else "")
            item.setIcon(self._build_cover_icon(str(cover_path) if cover_path else None))
            return

    def _update_single_series_progress(self, series_id: int) -> None:
        for row in range(self.series_list.count()):
            item = self.series_list.item(row)
            item_series_id = item.data(Qt.ItemDataRole.UserRole)
            if item_series_id is None or int(item_series_id) != series_id:
                continue

            progress = self.library_service.get_reading_progress(series_id)
            has_progress = progress is not None
            if self.current_category == "unread" and has_progress:
                self.series_list.takeItem(row)
                return
            if self.current_category == "read" and not self.library_service.is_series_fully_read(series_id):
                self.series_list.takeItem(row)
                return

            name = str(item.data(Qt.ItemDataRole.UserRole + 1) or "")
            author = str(item.data(Qt.ItemDataRole.UserRole + 2) or "")
            total_episodes = int(item.data(Qt.ItemDataRole.UserRole + 3) or 0)
            is_favorite = bool(item.data(Qt.ItemDataRole.UserRole + 4) or False)

            details = self.library_service.get_series_details(series_id)
            if details is not None:
                name = str(details.get("name") or name)
                author = str(details.get("author") or author)
                item.setData(Qt.ItemDataRole.UserRole + 1, name)
                item.setData(Qt.ItemDataRole.UserRole + 2, author)
                cover_path = details.get("cover_path")
                item.setData(Qt.ItemDataRole.UserRole + 5, str(cover_path) if cover_path else "")
                item.setIcon(self._build_cover_icon(str(cover_path) if cover_path else None))

            item.setText(
                self._compose_series_title(
                    name=name,
                    author=author,
                    total_episodes=total_episodes,
                    is_favorite=is_favorite,
                    progress=progress,
                )
            )
            return

    def show_series_context_menu(self, pos: QPoint) -> None:
        item = self.series_list.itemAt(pos)
        if item is None:
            return

        self.series_list.setCurrentItem(item)
        menu = QMenu(self)

        edit_action = QAction("编辑属性", self)
        edit_action.triggered.connect(self.edit_selected_series)
        menu.addAction(edit_action)

        favorite_action = QAction("切换收藏状态", self)
        favorite_action.triggered.connect(self.toggle_selected_favorite)
        menu.addAction(favorite_action)

        mark_read_action = QAction("标记为已读", self)
        mark_read_action.triggered.connect(self.mark_selected_series_as_read)
        menu.addAction(mark_read_action)

        mark_unread_action = QAction("标记为未读", self)
        mark_unread_action.triggered.connect(self.mark_selected_series_as_unread)
        menu.addAction(mark_unread_action)

        groups = self.library_service.list_custom_groups()
        if groups:
            move_menu = menu.addMenu("移动到分组")
            for row in groups:
                group_id = int(row["id"])
                group_name = str(row["name"])
                action = QAction(group_name, self)
                action.triggered.connect(
                    lambda checked=False, gid=group_id: self.move_selected_series_to_group(gid)
                )
                move_menu.addAction(action)

        menu.addSeparator()
        delete_action = QAction("删除漫画", self)
        delete_action.triggered.connect(self.delete_selected_series)
        menu.addAction(delete_action)

        menu.exec(self.series_list.mapToGlobal(pos))

    def edit_selected_series(self) -> None:
        item = self.series_list.currentItem()
        if item is None:
            return

        series_id = int(item.data(Qt.ItemDataRole.UserRole))
        details = self.library_service.get_series_details(series_id)
        if details is None:
            return

        groups = [
            (int(row["id"]), str(row["name"]))
            for row in self.library_service.list_custom_groups()
        ]
        
        # 获取集数列表
        episodes = self.library_service.list_episodes(series_id)

        dialog = EditSeriesDialog(
            series_id,
            details["name"],
            details["author"],
            details["tags"],
            groups,
            details.get("group_id"),
            episodes=episodes,
            current_cover_path=details.get("cover_path"),
            parent=self,
        )
        if dialog.exec() != EditSeriesDialog.DialogCode.Accepted:
            return

        original_cover_path = details.get("cover_path")
        name, author, tags, group_id, cover_path, episode_updates, deleted_episode_ids, new_episode_folders = dialog.get_edited_data()
        try:
            self.library_service.edit_series(series_id, name, author, tags)
            
            # 处理分组更新
            if group_id is None:
                self.library_service.clear_series_group(series_id)
            else:
                self.library_service.move_series_to_group(series_id, int(group_id))
            
            if deleted_episode_ids:
                self.library_service.delete_episodes(series_id, deleted_episode_ids)

            # 处理每集集名和顺序更新
            if episode_updates:
                self.library_service.update_episodes_metadata(series_id, episode_updates)

            if new_episode_folders:
                current_eps = self.library_service.list_episodes(series_id)
                next_episode_number = max((int(ep["episode_number"]) for ep in current_eps), default=0) + 1
                next_episode_order = max((int(ep["episode_order"]) for ep in current_eps), default=0) + 1

                for idx, folder_text in enumerate(new_episode_folders):
                    folder = Path(folder_text)
                    metadata = ImportMetadata(
                        name=name,
                        author=author,
                        episode_number=next_episode_number + idx,
                        episode_name=folder.name,
                        episode_order=next_episode_order + idx,
                        tags=tags,
                        cover_source="none",
                    )
                    self.import_service.import_folder(
                        folder=folder,
                        metadata=metadata,
                        hash_check=self.hash_check,
                        duplicate_policy=self.duplicate_policy,
                    )
            
            # 处理封面更新
            if cover_path != original_cover_path:
                # 选择了新封面时，统一走封面存储工具（哈希命名）。
                if cover_path:
                    if not Path(cover_path).exists():
                        raise ValueError("所选封面文件不存在")
                    new_cover_path = store_cover_image(series_id, Path(cover_path))
                    self.library_service.update_series_cover(series_id, str(new_cover_path))
                else:
                    # 清空封面
                    self.library_service.update_series_cover(series_id, None)
             
            self.reload_library()
            message_parts = ["漫画属性已更新"]
            if deleted_episode_ids:
                message_parts.append(f"删除 {len(deleted_episode_ids)} 集")
            if new_episode_folders:
                message_parts.append(f"新增 {len(new_episode_folders)} 集")
            self.statusBar().showMessage("，".join(message_parts), 4000)
        except Exception as exc:
            self._show_error("更新失败", str(exc))

    def mark_selected_series_as_read(self) -> None:
        item = self.series_list.currentItem()
        if item is None:
            return

        series_id = int(item.data(Qt.ItemDataRole.UserRole))
        try:
            self.library_service.mark_series_as_read(series_id)
            self.reload_library()
            self.statusBar().showMessage("已标记为已读", 3000)
        except Exception as exc:
            self._show_error("标记失败", str(exc))

    def mark_selected_series_as_unread(self) -> None:
        item = self.series_list.currentItem()
        if item is None:
            return

        series_id = int(item.data(Qt.ItemDataRole.UserRole))
        try:
            self.library_service.mark_series_as_unread(series_id)
            self.reload_library()
            self.statusBar().showMessage("已标记为未读", 3000)
        except Exception as exc:
            self._show_error("标记失败", str(exc))

    def delete_selected_series(self) -> None:
        item = self.series_list.currentItem()
        if item is None:
            return

        series_id = int(item.data(Qt.ItemDataRole.UserRole))
        series_name = item.text().split("\n", 1)[0].replace("★ ", "")
        resp = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除漫画《{series_name}》及其所有集数和阅读记录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        self.library_service.delete_series(series_id)
        self.reload_library()
        self.statusBar().showMessage("已删除漫画", 3000)

    def move_selected_series_to_group(self, group_id: int) -> None:
        item = self.series_list.currentItem()
        if item is None:
            return
        series_id = int(item.data(Qt.ItemDataRole.UserRole))
        self.library_service.move_series_to_group(series_id, group_id)
        self.reload_library()

    def on_series_dropped_to_category(self, series_id: int, target_code: int) -> None:
        if target_code == -1:
            return
        if target_code == -2:
            self.library_service.set_favorite(series_id, True)
        elif target_code == -3:
            self.library_service.clear_reading_progress(series_id)
        elif target_code == -4:
            self.library_service.mark_series_as_read(series_id)
        elif target_code > 0:
            self.library_service.move_series_to_group(series_id, target_code)
        self.reload_library()

    def on_folder_dropped(self, folder_path: Path) -> None:
        """处理拖放导入的文件夹"""
        # 创建一个简化的导入对话框，只需要输入作者和标签
        dialog = QDialog(self)
        dialog.setWindowTitle("快速导入")
        dialog.resize(400, 200)
        
        layout = QVBoxLayout(dialog)
        
        folder_label = QLabel(f"导入目录: {folder_path.name}")
        
        author_edit = QLineEdit()
        author_edit.setPlaceholderText("可选")
        author_edit.setToolTip("漫画作者")
        
        tags_edit = QLineEdit()
        tags_edit.setPlaceholderText("可选")
        tags_edit.setToolTip("漫画标签，多个标签用空格分隔")
        
        form = QFormLayout()
        form.addRow("导入目录", folder_label)
        form.addRow("作者(可选)", author_edit)
        form.addRow("标签(可选)", tags_edit)
        
        layout.addLayout(form)
        
        hint = QLabel("提示：漫画名称和集数将自动识别")
        hint.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(hint)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        # 执行导入
        try:
            self._set_import_controls_enabled(False)
            self.statusBar().showMessage("导入中...", 0)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
            results = self.import_service.import_auto_folder(
                folder_path,
                author=author_edit.text().strip(),
                tags=tags_edit.text().strip(),
                hash_check=self.hash_check,
                duplicate_policy=self.duplicate_policy,
                custom_name="",
                progress_callback=lambda d, t: (self.statusBar().showMessage(f"导入中... {d}/{t}", 0), QApplication.processEvents()),
            )
            self.reload_library()
            
            imported_count = sum(1 for r in results if r.imported)
            failed_count = sum(1 for r in results if not r.imported)
            
            # 如果有失败的导入，生成错误日志
            if failed_count > 0:
                log_file = self.import_service.generate_error_log(results, folder_path)
                message = f"导入完成：成功 {imported_count} 集，跳过/失败 {failed_count} 集"
                if log_file:
                    message += f"\n\n错误日志已生成：\n{log_file}"
                    QMessageBox.information(self, "导入完成", message)
                self.statusBar().showMessage(message, 5000)
            else:
                self.statusBar().showMessage(f"导入完成：成功 {imported_count} 集", 3500)
        except Exception as exc:
            self._show_error("导入失败", str(exc))
        finally:
            QApplication.restoreOverrideCursor()
            self._set_import_controls_enabled(True)

    def toggle_selected_favorite(self) -> None:
        item = self.series_list.currentItem()
        if item is None:
            return
        series_id = int(item.data(Qt.ItemDataRole.UserRole))
        is_fav = item.text().startswith("★")
        self.library_service.set_favorite(series_id, not is_fav)
        self.reload_library()

    def on_category_changed(self, row: int) -> None:
        if row < 0:
            return

        self._sync_category_state_from_row(row)
        self.reload_library()

    def _sync_category_state_from_row(self, row: int) -> None:
        if row == 0:
            self.current_category = "all"
            self.current_custom_group_id = None
            return
        if row == 1:
            self.current_category = "favorite"
            self.current_custom_group_id = None
            return
        if row == 2:
            self.current_category = "unread"
            self.current_custom_group_id = None
            return
        if row == 3:
            self.current_category = "read"
            self.current_custom_group_id = None
            return

        item = self.category_list.item(row)
        if item is None:
            self.current_category = "all"
            self.current_custom_group_id = None
            return
        group_id = item.data(Qt.ItemDataRole.UserRole)
        if group_id is None:
            self.current_category = "all"
            self.current_custom_group_id = None
            return
        self.current_category = "group"
        self.current_custom_group_id = int(group_id)

    def add_group(self) -> None:
        name, ok = QInputDialog.getText(self, "新建分组", "分组名")
        if not ok or not name.strip():
            return
        self.library_service.create_group(name)
        self._reload_custom_groups()

    def open_group_manager_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("分组管理")
        dialog.resize(420, 360)

        layout = QVBoxLayout(dialog)
        group_list = QListWidget()
        layout.addWidget(group_list)

        row = QHBoxLayout()
        add_btn = QPushButton("新建")
        rename_btn = QPushButton("重命名")
        delete_btn = QPushButton("删除")
        close_btn = QPushButton("关闭")
        row.addWidget(add_btn)
        row.addWidget(rename_btn)
        row.addWidget(delete_btn)
        row.addStretch(1)
        row.addWidget(close_btn)
        layout.addLayout(row)

        def selected_group() -> tuple[int, str] | None:
            item = group_list.currentItem()
            if item is None:
                return None
            gid = item.data(Qt.ItemDataRole.UserRole)
            if gid is None:
                return None
            return int(gid), item.text()

        def refresh() -> None:
            group_list.clear()
            for group in self.library_service.list_custom_groups():
                item = QListWidgetItem(str(group["name"]))
                item.setData(Qt.ItemDataRole.UserRole, int(group["id"]))
                group_list.addItem(item)

        def do_add() -> None:
            name, ok = QInputDialog.getText(dialog, "新建分组", "分组名")
            if not ok or not name.strip():
                return
            self.library_service.create_group(name)
            refresh()

        def do_rename() -> None:
            selected = selected_group()
            if selected is None:
                QMessageBox.information(dialog, "提示", "请先选择分组")
                return
            gid, old_name = selected
            name, ok = QInputDialog.getText(dialog, "重命名分组", "新名称", text=old_name)
            if not ok or not name.strip():
                return
            self.library_service.rename_group(gid, name)
            refresh()

        def do_delete() -> None:
            selected = selected_group()
            if selected is None:
                QMessageBox.information(dialog, "提示", "请先选择分组")
                return
            gid, name = selected
            resp = QMessageBox.question(
                dialog,
                "确认删除",
                f"确定删除分组“{name}”？\n已归属该分组的漫画会变为未分组。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
            self.library_service.delete_group(gid)
            refresh()

        add_btn.clicked.connect(do_add)
        rename_btn.clicked.connect(do_rename)
        delete_btn.clicked.connect(do_delete)
        close_btn.clicked.connect(dialog.accept)

        refresh()
        dialog.exec()
        self.reload_library()

    def _reload_custom_groups(self) -> None:
        prev_row = self.category_list.currentRow()
        prev_group_id = self.current_custom_group_id if self.current_category == "group" else None

        self.category_list.blockSignals(True)
        while self.category_list.count() > 4:
            self.category_list.takeItem(4)

        selected_row = prev_row if 0 <= prev_row <= 3 else 0
        for idx, row in enumerate(self.library_service.list_custom_groups(), start=4):
            item = QListWidgetItem(f"分组: {row['name']}")
            item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
            self.category_list.addItem(item)
            if prev_group_id is not None and int(row["id"]) == prev_group_id:
                selected_row = idx

        self.category_list.setCurrentRow(selected_row)
        self._sync_category_state_from_row(selected_row)
        self.category_list.blockSignals(False)
