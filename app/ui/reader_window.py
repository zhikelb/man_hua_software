from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QKeyEvent, QKeySequence, QPixmap
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
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.services.reader_service import ReaderService


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

    def __init__(
        self,
        reader_service: ReaderService,
        series_id: int,
        series_name: str,
        reader_config: dict[str, Any],
    ) -> None:
        super().__init__()
        self.reader_service = reader_service
        self.series_id = series_id
        self.series_name = series_name
        self.reader_config = reader_config
        self.current_pixmap = QPixmap()
        self._finished_prompt_shown = False

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
        
        top.addWidget(QLabel("缩放"))
        top.addWidget(self.zoom_combo)
        root.addLayout(top)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.installEventFilter(self)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.image_label)
        self.scroll.viewport().installEventFilter(self)
        root.addWidget(self.scroll)

        pix, text = self.reader_service.open_series(series_id)
        self.current_pixmap = pix
        self.position_label.setText(text)
        self.refresh_view()
        self.setFocus()

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
        self.position_label.setText(text)
        self.refresh_view()
        self.progress_changed.emit(self.series_id)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Wheel:
            angle = event.angleDelta().y()
            if angle < 0:
                self._go_next()
            elif angle > 0:
                self._go_previous()
            return True

        if event.type() == QEvent.Type.MouseButtonPress:
            button = event.button()
            if button == Qt.MouseButton.LeftButton:
                self._go_next()
                return True
            if button == Qt.MouseButton.RightButton:
                self._go_previous()
                return True

        return super().eventFilter(watched, event)

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
        self.refresh_view()

    def refresh_view(self) -> None:
        if self.current_pixmap.isNull():
            return

        zoom_mode = self.zoom_combo.currentData()
        if zoom_mode == "fill":
            target = self.scroll.viewport().size()
            scaled = self.current_pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        elif zoom_mode == "fit":
            target = self.scroll.viewport().size()
            scaled = self.current_pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            factor = int(zoom_mode) / 100.0
            target_size = self.current_pixmap.size() * factor
            scaled = self.current_pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        self.image_label.setPixmap(scaled)

    def _go_next(self) -> None:
        pix, text, finished = self.reader_service.next_image()
        self.current_pixmap = pix
        self.position_label.setText(text)
        self.refresh_view()
        self.progress_changed.emit(self.series_id)
        if finished and not self._finished_prompt_shown:
            self._finished_prompt_shown = True
            box = QMessageBox(self)
            box.setWindowTitle("提示")
            box.setText("阅读完毕")
            box.setIcon(QMessageBox.Icon.Information)
            box.setStandardButtons(QMessageBox.StandardButton.Close)
            box.exec()

    def _go_previous(self) -> None:
        pix, text = self.reader_service.previous_image()
        self.current_pixmap = pix
        self.position_label.setText(text)
        self.refresh_view()
        self.progress_changed.emit(self.series_id)

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
        ep_spin.setMaximum(1000)
        ep_spin.setValue(1)
        
        page_spin = QSpinBox()
        page_spin.setMinimum(1)
        page_spin.setMaximum(1000)
        page_spin.setValue(1)
        
        form.addRow("集数", ep_spin)
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
            episode = ep_spin.value()
            page = page_spin.value()
            if self.reader_service.jump_to_position(episode, page):
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
