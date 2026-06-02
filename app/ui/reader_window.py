from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from PyQt6.QtCore import QEvent, QTimer, Qt
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeyEvent, QKeySequence, QPixmap, QShowEvent
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QMenu,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.services.library_service import LibraryService
from app.services.reader_service import ReaderService

if TYPE_CHECKING:
    from PyQt6.QtCore import QObject


_KEY_NAME_TO_QT: dict[str, Qt.Key] = {
    "right": Qt.Key.Key_Right,
    "left": Qt.Key.Key_Left,
    "up": Qt.Key.Key_Up,
    "down": Qt.Key.Key_Down,
    "space": Qt.Key.Key_Space,
    "pgup": Qt.Key.Key_PageUp,
    "pageup": Qt.Key.Key_PageUp,
    "pgdn": Qt.Key.Key_PageDown,
    "pagedown": Qt.Key.Key_PageDown,
    "escape": Qt.Key.Key_Escape,
    "f": Qt.Key.Key_F,
}


class ReaderWindow(QWidget):
    progress_changed = pyqtSignal(int)
    cover_changed = pyqtSignal(int)

    def __init__(
        self,
        reader_service: ReaderService,
        library_service: LibraryService,
        series_id: int,
        series_name: str,
        reader_config: dict[str, Any],
    ) -> None:
        super().__init__()
        self.reader_service = reader_service
        self.library_service = library_service
        self.series_id = series_id
        self.series_name = series_name
        self.reader_config = reader_config
        self.current_pixmap = QPixmap()
        self._finished_prompt_shown = False
        self._scaled_cache: OrderedDict[tuple[int, str, int, int], QPixmap] = OrderedDict()
        self._scaled_cache_limit = 8

        key_cfg = self.reader_config.get("key_bindings", {})
        hide_names = [str(k) for k in key_cfg.get("hide_window", ["Escape"])]
        toggle_fullscreen_names = [
            str(k)
            for k in key_cfg.get(
                "reader_toggle_fullscreen",
                key_cfg.get("reader_fullscreen", ["F"]),
            )
        ]

        # 翻页键固定，不允许用户更改。
        self.next_keys = {
            int(Qt.Key.Key_Right),
            int(Qt.Key.Key_Down),
            int(Qt.Key.Key_Space),
            int(Qt.Key.Key_PageDown),
        }
        self.prev_keys = {
            int(Qt.Key.Key_Left),
            int(Qt.Key.Key_Up),
            int(Qt.Key.Key_PageUp),
        }

        self.hide_shortcuts = self._parse_shortcut_list(hide_names)
        self.toggle_fullscreen_shortcuts = self._parse_shortcut_list(toggle_fullscreen_names)

        self.setWindowTitle(f"阅读 - {series_name}")
        self.resize(1100, 760)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        root = QVBoxLayout(self)
        top = QHBoxLayout()

        self.position_label = QLabel("")
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItem("填充以适应", "fill")
        self.zoom_combo.addItem("适应窗口", "fit")
        for value in (50, 75, 100, 125, 150, 200):
            self.zoom_combo.addItem(f"{value}%", value)
        self.zoom_combo.currentIndexChanged.connect(self.refresh_view)

        default_zoom = str(self.reader_config.get("default_zoom", "fill")).strip().lower()
        zoom_idx = self.zoom_combo.findData(default_zoom)
        if zoom_idx < 0:
            zoom_idx = self.zoom_combo.findData("fit")
        if zoom_idx >= 0:
            self.zoom_combo.setCurrentIndex(zoom_idx)

        top.addWidget(self.position_label)
        top.addStretch(1)
        
        # 书签按钮
        bookmark_btn = QPushButton("添加书签")
        bookmark_btn.clicked.connect(self.add_bookmark)
        top.addWidget(bookmark_btn)

        bookmark_manage_btn = QPushButton("书签管理")
        bookmark_manage_btn.clicked.connect(self.show_bookmark_manager)
        top.addWidget(bookmark_manage_btn)
        
        # 跳转按钮
        jump_btn = QPushButton("跳转...")
        jump_btn.clicked.connect(self.show_jump_dialog)
        top.addWidget(jump_btn)

        self.render_mode_combo = QComboBox()
        self.render_mode_combo.addItem("高质量", "high")
        self.render_mode_combo.addItem("性能模式", "performance")
        default_render_mode = str(self.reader_config.get("render_mode", "high")).strip().lower()
        render_idx = self.render_mode_combo.findData(default_render_mode)
        if render_idx < 0:
            render_idx = self.render_mode_combo.findData("high")
        if render_idx >= 0:
            self.render_mode_combo.setCurrentIndex(render_idx)
        self.render_mode_combo.currentIndexChanged.connect(self._on_render_mode_changed)
        
        top.addWidget(QLabel("缩放"))
        top.addWidget(self.zoom_combo)
        top.addWidget(QLabel("渲染"))
        top.addWidget(self.render_mode_combo)
        root.addLayout(top)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.installEventFilter(self)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.image_label)
        self.scroll.viewport().installEventFilter(self)

        root.addWidget(self.scroll)

        self.prev_button = QPushButton("◀", self.scroll.viewport())
        self.prev_button.setToolTip("上一页")
        self.prev_button.setFixedSize(44, 80)
        self.prev_button.setStyleSheet("background-color: rgba(30, 30, 30, 120); color: white; border-radius: 6px;")
        self.prev_button.clicked.connect(self._go_previous)

        self.next_button = QPushButton("▶", self.scroll.viewport())
        self.next_button.setToolTip("下一页")
        self.next_button.setFixedSize(44, 80)
        self.next_button.setStyleSheet("background-color: rgba(30, 30, 30, 120); color: white; border-radius: 6px;")
        self.next_button.clicked.connect(self._go_next)

        pix, text = self.reader_service.open_series(series_id)
        self.current_pixmap = pix
        self.position_label.setText(text)
        self.refresh_view()
        self._relayout_page_buttons()
        QTimer.singleShot(0, self._on_first_layout_ready)
        self.setFocus()

    def _on_first_layout_ready(self) -> None:
        self._relayout_page_buttons()
        self._scaled_cache.clear()
        self.refresh_view()

    def _parse_shortcut_list(self, names: list[str]) -> set[str]:
        shortcuts: set[str] = set()
        for name in names:
            text = name.strip()
            if not text:
                continue

            qt_key = _KEY_NAME_TO_QT.get(text.lower())
            if qt_key is not None:
                seq = QKeySequence(int(qt_key)).toString(QKeySequence.SequenceFormat.PortableText)
                if seq:
                    shortcuts.add(seq)
                continue

            seq = QKeySequence(text).toString(QKeySequence.SequenceFormat.PortableText)
            if seq:
                shortcuts.add(seq)

        return shortcuts

    def _event_sequence_text(self, event: QKeyEvent) -> str:
        if event.key() in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            return ""
        seq = QKeySequence(event.keyCombination())
        return seq.toString(QKeySequence.SequenceFormat.PortableText)

    def _sync_current_view(self) -> None:
        pix, text = self.reader_service.get_current_view()
        self.current_pixmap = pix
        self._scaled_cache.clear()
        self.position_label.setText(text)
        self.refresh_view()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel:
            angle = event.angleDelta().y()
            if angle < 0:
                self._go_next()
            elif angle > 0:
                self._go_previous()
            return True

        if event.type() == QEvent.Type.MouseButtonPress and watched in (self.image_label, self.scroll.viewport()):
            button = event.button()
            if button == Qt.MouseButton.RightButton:
                global_pos = event.globalPosition().toPoint()
                self._show_image_context_menu(global_pos)
                return True

        return super().eventFilter(watched, event)

    def _show_image_context_menu(self, global_pos) -> None:
        menu = QMenu(self)

        set_cover_action = QAction("添加为漫画封面", self)
        set_cover_action.triggered.connect(self._set_current_image_as_cover)
        menu.addAction(set_cover_action)

        open_folder_action = QAction("跳转到文件所在位置", self)
        open_folder_action.triggered.connect(self._open_current_image_folder)
        menu.addAction(open_folder_action)

        menu.exec(global_pos)

    def _set_current_image_as_cover(self) -> None:
        if not self.reader_service.image_rows:
            return
        try:
            row = self.reader_service.image_rows[self.reader_service.current_index]
            image_path = Path(str(row["file_path"]))
            if not image_path.exists():
                raise ValueError("当前图片文件不存在")
            self.library_service.update_series_cover(self.series_id, str(image_path))
            self.cover_changed.emit(self.series_id)
            QMessageBox.information(self, "提示", "已设置为漫画封面", QMessageBox.StandardButton.Ok)
        except Exception as exc:
            QMessageBox.warning(self, "失败", str(exc), QMessageBox.StandardButton.Ok)

    def _open_current_image_folder(self) -> None:
        if not self.reader_service.image_rows:
            return
        row = self.reader_service.image_rows[self.reader_service.current_index]
        image_path = Path(str(row["file_path"]))
        if image_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(image_path.parent)))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = int(event.key())
        pressed = self._event_sequence_text(event)

        if key in self.next_keys:
            self._go_next()
            return

        if key in self.prev_keys:
            self._go_previous()
            return

        if pressed in self.hide_shortcuts:
            self.hide()
            return

        if pressed in self.toggle_fullscreen_shortcuts:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            return

        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout_page_buttons()
        self.refresh_view()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._relayout_page_buttons()
        self._scaled_cache.clear()
        self.refresh_view()

    def _relayout_page_buttons(self) -> None:
        viewport = self.scroll.viewport()
        width = viewport.width()
        height = viewport.height()
        button_w = self.prev_button.width()
        button_h = self.prev_button.height()
        y = max(8, (height - button_h) // 2)
        margin = 10
        self.prev_button.move(margin, y)
        self.next_button.move(max(margin, width - button_w - margin), y)
        self.prev_button.raise_()
        self.next_button.raise_()

    def refresh_view(self) -> None:
        if self.current_pixmap.isNull():
            return

        zoom_mode = self.zoom_combo.currentData()
        render_mode = str(self.render_mode_combo.currentData() or "high")
        viewport_size = self.scroll.viewport().size()
        cache_key = (
            int(self.current_pixmap.cacheKey()),
            str(zoom_mode),
            render_mode,
            viewport_size.width(),
            viewport_size.height(),
        )
        cached = self._scaled_cache.get(cache_key)
        if cached is not None:
            self.image_label.setPixmap(cached)
            self._scaled_cache.move_to_end(cache_key)
            return

        transform_mode = (
            Qt.TransformationMode.SmoothTransformation
            if render_mode == "high"
            else Qt.TransformationMode.FastTransformation
        )

        if zoom_mode == "fill":
            scaled = self.current_pixmap.scaled(
                viewport_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                transform_mode,
            )
        elif zoom_mode == "fit":
            scaled = self.current_pixmap.scaled(
                viewport_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                transform_mode,
            )
        else:
            factor = int(zoom_mode) / 100.0
            target_size = self.current_pixmap.size() * factor
            scaled = self.current_pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                transform_mode,
            )

        self._scaled_cache[cache_key] = scaled
        while len(self._scaled_cache) > self._scaled_cache_limit:
            self._scaled_cache.popitem(last=False)
        self.image_label.setPixmap(scaled)

    def _go_next(self) -> None:
        pix, text, finished = self.reader_service.next_image()
        self.current_pixmap = pix
        self._scaled_cache.clear()
        self.position_label.setText(text)
        self.refresh_view()

        if finished and not self._finished_prompt_shown:
            self._finished_prompt_shown = True
            box = QMessageBox(self)
            box.setWindowTitle("提示")
            box.setText("阅读完毕")
            box.setIcon(QMessageBox.Icon.Information)
            box.setStandardButtons(QMessageBox.StandardButton.Close)
            box.exec()

    def _on_render_mode_changed(self) -> None:
        self._scaled_cache.clear()
        self.refresh_view()

    def _go_previous(self) -> None:
        pix, text = self.reader_service.previous_image()
        self.current_pixmap = pix
        self._scaled_cache.clear()
        self.position_label.setText(text)
        self.refresh_view()

    def closeEvent(self, event: QCloseEvent) -> None:
        super().closeEvent(event)
        series_id = self.series_id
        QTimer.singleShot(0, lambda sid=series_id: self.progress_changed.emit(sid))

    def add_bookmark(self) -> None:
        """添加书签"""
        try:
            self.reader_service.add_bookmark("书签")
            QMessageBox.information(self, "提示", "书签已保存", QMessageBox.StandardButton.Ok)
        except Exception as exc:
            QMessageBox.warning(self, "失败", str(exc), QMessageBox.StandardButton.Ok)

    def show_jump_dialog(self) -> None:
        """显示跳转对话框"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QSpinBox, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("跳转到...")
        dialog.resize(300, 150)
        
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        
        ep_spin = QSpinBox()
        ep_spin.setMinimum(1)
        max_order = max((int(row.get("episode_order", 1)) for row in self.reader_service.image_rows), default=1)
        ep_spin.setMaximum(max(max_order, 1))
        current_order = int(self.reader_service.image_rows[self.reader_service.current_index].get("episode_order", 1))
        ep_spin.setValue(current_order)
        
        page_spin = QSpinBox()
        page_spin.setMinimum(1)
        page_spin.setMaximum(1000)
        page_spin.setValue(1)
        
        form.addRow("顺序", ep_spin)
        form.addRow("页码", page_spin)
        layout.addLayout(form)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        try:
            episode_order = ep_spin.value()
            page = page_spin.value()
            if self.reader_service.jump_to_position(episode_order, page):
                self._sync_current_view()
            else:
                QMessageBox.warning(self, "跳转失败", "该位置不存在", QMessageBox.StandardButton.Ok)
        except Exception as exc:
            QMessageBox.warning(self, "跳转失败", str(exc), QMessageBox.StandardButton.Ok)

    def show_bookmark_manager(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("书签管理")
        dialog.resize(420, 360)

        layout = QVBoxLayout(dialog)
        bookmark_list = QListWidget()
        layout.addWidget(bookmark_list)

        button_row = QHBoxLayout()
        jump_btn = QPushButton("跳转")
        delete_btn = QPushButton("删除")
        close_btn = QPushButton("关闭")
        button_row.addWidget(jump_btn)
        button_row.addWidget(delete_btn)
        button_row.addStretch(1)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        def reload_bookmarks() -> None:
            bookmark_list.clear()
            bookmarks = self.reader_service.get_bookmarks(self.series_id)
            for bookmark in bookmarks:
                text = f"{bookmark['name']} · 第{bookmark['episode']}集 第{bookmark['page']}页"
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, int(bookmark["id"]))
                bookmark_list.addItem(item)

        def get_selected_bookmark_id() -> int | None:
            item = bookmark_list.currentItem()
            if item is None:
                return None
            data = item.data(Qt.ItemDataRole.UserRole)
            return int(data) if data is not None else None

        def do_jump() -> None:
            bookmark_id = get_selected_bookmark_id()
            if bookmark_id is None:
                QMessageBox.information(dialog, "提示", "请先选择书签", QMessageBox.StandardButton.Ok)
                return
            if not self.reader_service.jump_to_bookmark(bookmark_id):
                QMessageBox.warning(dialog, "失败", "跳转失败，书签可能已失效", QMessageBox.StandardButton.Ok)
                reload_bookmarks()
                return
            self._sync_current_view()
            dialog.accept()

        def do_delete() -> None:
            bookmark_id = get_selected_bookmark_id()
            if bookmark_id is None:
                QMessageBox.information(dialog, "提示", "请先选择书签", QMessageBox.StandardButton.Ok)
                return
            self.reader_service.delete_bookmark(bookmark_id)
            reload_bookmarks()

        jump_btn.clicked.connect(do_jump)
        delete_btn.clicked.connect(do_delete)
        close_btn.clicked.connect(dialog.reject)
        bookmark_list.itemDoubleClicked.connect(lambda _: do_jump())

        reload_bookmarks()
        dialog.exec()
