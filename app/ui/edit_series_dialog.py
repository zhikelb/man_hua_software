from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.utils.image_files import list_images_sorted


class CoverSelector(QWidget):
    def __init__(self, current_cover_path: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.selected_cover_path: str | None = current_cover_path

        layout = QVBoxLayout(self)

        self.cover_label = QLabel()
        self.cover_label.setMinimumSize(140, 190)
        self.cover_label.setMaximumSize(140, 190)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet("border: 1px solid #ccc; background-color: #f0f0f0;")
        self._update_cover_display()

        button_layout = QHBoxLayout()
        select_btn = QPushButton("选择新封面")
        select_btn.clicked.connect(self.select_cover)
        clear_btn = QPushButton("清空封面")
        clear_btn.clicked.connect(self.clear_cover)

        button_layout.addWidget(select_btn)
        button_layout.addWidget(clear_btn)

        layout.addWidget(QLabel("当前封面："))
        layout.addWidget(self.cover_label)
        layout.addLayout(button_layout)
        layout.addStretch()

    def _update_cover_display(self) -> None:
        if self.selected_cover_path and Path(self.selected_cover_path).exists():
            pixmap = QPixmap(self.selected_cover_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    140,
                    190,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.cover_label.setPixmap(scaled)
                return

        placeholder = QPixmap(140, 190)
        placeholder.fill(Qt.GlobalColor.lightGray)
        self.cover_label.setPixmap(placeholder)

    def select_cover(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择封面图片",
            str(Path.home()),
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif);;所有文件 (*.*)",
        )
        if file_path:
            self.selected_cover_path = file_path
            self._update_cover_display()

    def clear_cover(self) -> None:
        self.selected_cover_path = ""
        self._update_cover_display()

    def get_selected_cover_path(self) -> str | None:
        return self.selected_cover_path


class EpisodeOrderSpinBox(QSpinBox):
    def __init__(self, editor: "EpisodeEditorWidget", episode_id: int, parent=None) -> None:
        super().__init__(parent)
        self.editor = editor
        self.episode_id = episode_id
        self.setReadOnly(True)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lineEdit().setReadOnly(True)

    def stepBy(self, steps: int) -> None:
        if steps > 0:
            self.editor.move_episode_by_id(self.episode_id, 1)
        elif steps < 0:
            self.editor.move_episode_by_id(self.episode_id, -1)

    def stepEnabled(self) -> QAbstractSpinBox.StepEnabled:
        enabled = QAbstractSpinBox.StepEnabledFlag.StepNone
        if self.editor.can_move_episode(self.episode_id, -1):
            enabled |= QAbstractSpinBox.StepEnabledFlag.StepDownEnabled
        if self.editor.can_move_episode(self.episode_id, 1):
            enabled |= QAbstractSpinBox.StepEnabledFlag.StepUpEnabled
        return enabled

    def wheelEvent(self, event) -> None:
        event.ignore()


class EpisodeEditorWidget(QWidget):
    def __init__(self, episodes: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.episodes = [dict(ep) for ep in episodes]
        self.order_spins: dict[int, EpisodeOrderSpinBox] = {}
        self.name_edits: dict[int, QLineEdit] = {}
        self.deleted_episode_ids: list[int] = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("可修改每一集的集名，并使用顺序列右侧箭头调整集顺序。"))

        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["原顺序", "集名", "顺序", "图片数"])
        self.table.setRowCount(len(episodes))
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        max_order = max((int(ep["episode_order"]) for ep in episodes), default=1)

        for row_idx, ep in enumerate(episodes):
            ep_id = int(ep["id"])

            old_order_item = QTableWidgetItem(str(int(ep["episode_order"])))
            old_order_item.setFlags(old_order_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_idx, 0, old_order_item)

            name_edit = QLineEdit(str(ep.get("episode_name") or "").strip())
            if not name_edit.text().strip():
                name_edit.setText(f"第{int(ep['episode_number'])}集")
            self.table.setCellWidget(row_idx, 1, name_edit)
            self.name_edits[ep_id] = name_edit

            order_spin = EpisodeOrderSpinBox(self, ep_id)
            order_spin.setMinimum(1)
            order_spin.setMaximum(max(max_order, len(episodes), 1))
            order_spin.setValue(int(ep["episode_order"]))
            self.table.setCellWidget(row_idx, 2, order_spin)
            self.order_spins[ep_id] = order_spin

            img_item = QTableWidgetItem(str(int(ep["image_count"])))
            img_item.setFlags(img_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_idx, 3, img_item)

        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)

        action_row = QHBoxLayout()
        self.delete_episode_btn = QPushButton("删除选中单集")
        self.delete_episode_btn.clicked.connect(self.delete_selected_episode)
        action_row.addWidget(self.delete_episode_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.table.itemSelectionChanged.connect(self._refresh_action_buttons)

        if episodes:
            self.table.selectRow(0)
            self.table.setCurrentCell(0, 1)

        self._refresh_action_buttons()

    def _current_row(self) -> int | None:
        row = self.table.currentRow()
        if row >= 0:
            return row
        if self.table.rowCount() > 0:
            self.table.selectRow(0)
            return 0
        return None

    def _row_to_episode_id(self, row: int) -> int:
        return int(self.episodes[row]["id"])

    def _sorted_rows_by_order(self) -> list[int]:
        rows = list(range(self.table.rowCount()))
        rows.sort(
            key=lambda r: (
                int(self.order_spins[int(self.episodes[r]["id"])].value()),
                r,
            )
        )
        return rows

    def _row_for_episode_id(self, episode_id: int) -> int | None:
        for row_idx, ep in enumerate(self.episodes):
            if int(ep["id"]) == episode_id:
                return row_idx
        return None

    def _refresh_order_controls(self) -> None:
        for spin in self.order_spins.values():
            spin.update()

    def _refresh_action_buttons(self) -> None:
        current_row = self.table.currentRow()
        self.delete_episode_btn.setEnabled(current_row >= 0 and self.table.rowCount() > 1)

    def _renumber_orders(self) -> None:
        for new_order, row in enumerate(self._sorted_rows_by_order(), start=1):
            ep_id = self._row_to_episode_id(row)
            self.order_spins[ep_id].setValue(new_order)
        self._refresh_order_controls()

    def _swap_row_order(self, row_a: int, row_b: int) -> None:
        ep_id_a = self._row_to_episode_id(row_a)
        ep_id_b = self._row_to_episode_id(row_b)
        spin_a = self.order_spins[ep_id_a]
        spin_b = self.order_spins[ep_id_b]
        value_a = int(spin_a.value())
        value_b = int(spin_b.value())
        spin_a.setValue(value_b)
        spin_b.setValue(value_a)

    def can_move_episode(self, episode_id: int, direction: int) -> bool:
        row = self._row_for_episode_id(episode_id)
        if row is None:
            return False
        ordered_rows = self._sorted_rows_by_order()
        try:
            idx = ordered_rows.index(row)
        except ValueError:
            return False
        target_idx = idx + direction
        return 0 <= target_idx < len(ordered_rows)

    def move_episode_by_id(self, episode_id: int, direction: int) -> None:
        row = self._row_for_episode_id(episode_id)
        if row is None:
            return

        ordered_rows = self._sorted_rows_by_order()
        try:
            idx = ordered_rows.index(row)
        except ValueError:
            return

        target_idx = idx + direction
        if target_idx < 0 or target_idx >= len(ordered_rows):
            return

        self._swap_row_order(row, ordered_rows[target_idx])
        self._refresh_order_controls()
        # 保持选中同一集名所在行，持续调整同一集的顺序。
        self.table.selectRow(row)
        self.table.setCurrentCell(row, 1)
        self._refresh_action_buttons()

    def delete_selected_episode(self) -> None:
        row = self._current_row()
        if row is None:
            return
        if self.table.rowCount() <= 1:
            QMessageBox.information(self, "提示", "至少保留一集，如需全部删除请直接删除漫画。")
            return

        episode = self.episodes[row]
        episode_name = str(episode.get("episode_name") or f"第{int(episode['episode_number'])}集").strip()
        response = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除单集《{episode_name}》吗？\n该操作会在保存后生效。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        ep_id = int(episode["id"])
        self.deleted_episode_ids.append(ep_id)
        self.episodes.pop(row)
        self.order_spins.pop(ep_id, None)
        self.name_edits.pop(ep_id, None)
        self.table.removeRow(row)
        self._renumber_orders()

        if self.table.rowCount() > 0:
            next_row = min(row, self.table.rowCount() - 1)
            self.table.selectRow(next_row)
            self.table.setCurrentCell(next_row, 1)
        self._refresh_action_buttons()

    def get_episode_updates(self) -> list[dict]:
        updates: list[dict] = []
        for ep in self.episodes:
            ep_id = int(ep["id"])
            name = self.name_edits[ep_id].text().strip()
            order = int(self.order_spins[ep_id].value())
            updates.append(
                {
                    "id": ep_id,
                    "episode_number": int(ep["episode_number"]),
                    "episode_name": name or f"第{int(ep['episode_number'])}集",
                    "episode_order": order,
                }
            )
        return updates

    def get_deleted_episode_ids(self) -> list[int]:
        return self.deleted_episode_ids.copy()


class EditSeriesDialog(QDialog):
    def __init__(
        self,
        series_id: int,
        name: str,
        author: str,
        tags: str,
        groups: list[tuple[int, str]],
        selected_group_id: int | None,
        episodes: list[dict] | None = None,
        current_cover_path: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.series_id = series_id
        self.episodes = episodes or []
        self.new_episode_folders: list[str] = []
        self.setWindowTitle(f"编辑漫画《{name}》")
        self.resize(700, 560)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        basic_widget = QWidget()
        basic_layout = QVBoxLayout(basic_widget)
        basic_form = QFormLayout()

        self.name_edit = QLineEdit(name)
        self.author_edit = QLineEdit(author)
        self.tags_edit = QLineEdit(tags)
        self.tags_edit.setPlaceholderText("多个标签用空格分隔")

        self.group_combo = QComboBox()
        self.group_combo.addItem("未分组", None)
        for group_id, group_name in groups:
            self.group_combo.addItem(group_name, group_id)

        if selected_group_id is not None:
            idx = self.group_combo.findData(selected_group_id)
            if idx >= 0:
                self.group_combo.setCurrentIndex(idx)

        basic_form.addRow("漫画名称", self.name_edit)
        basic_form.addRow("作者", self.author_edit)
        basic_form.addRow("标签", self.tags_edit)
        basic_form.addRow("所属分组", self.group_combo)
        basic_layout.addLayout(basic_form)
        basic_layout.addStretch()
        tabs.addTab(basic_widget, "基本属性")

        self.cover_selector = CoverSelector(current_cover_path)
        tabs.addTab(self.cover_selector, "封面管理")

        self.episode_widget: EpisodeEditorWidget | None = None
        if self.episodes:
            self.episode_widget = EpisodeEditorWidget(self.episodes)
            tabs.addTab(self.episode_widget, f"集信息（{len(self.episodes)}集）")

        append_widget = QWidget()
        append_layout = QVBoxLayout(append_widget)
        append_layout.addWidget(QLabel("为当前漫画追加新集（从图片目录导入，集号自动顺延）"))

        self.new_episode_list = QListWidget()
        append_layout.addWidget(self.new_episode_list)

        append_btn_row = QHBoxLayout()
        add_episode_btn = QPushButton("添加新集目录")
        remove_episode_btn = QPushButton("移除选中")
        add_episode_btn.clicked.connect(self._add_new_episode_folder)
        remove_episode_btn.clicked.connect(self._remove_selected_new_episode_folder)
        append_btn_row.addWidget(add_episode_btn)
        append_btn_row.addWidget(remove_episode_btn)
        append_btn_row.addStretch()
        append_layout.addLayout(append_btn_row)

        tabs.addTab(append_widget, "添加新集")

        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept_with_validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_new_episode_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择新集图片目录", str(Path.home()))
        if not folder:
            return

        folder_path = Path(folder)
        images = list_images_sorted(folder_path)
        if not images:
            QMessageBox.warning(self, "提示", "所选目录没有可用图片")
            return

        folder_text = str(folder_path)
        if folder_text in self.new_episode_folders:
            QMessageBox.information(self, "提示", "该目录已添加")
            return

        self.new_episode_folders.append(folder_text)
        self.new_episode_list.addItem(QListWidgetItem(f"{folder_path.name} ({len(images)} 张)"))

    def _remove_selected_new_episode_folder(self) -> None:
        row = self.new_episode_list.currentRow()
        if row < 0:
            return
        self.new_episode_list.takeItem(row)
        if row < len(self.new_episode_folders):
            self.new_episode_folders.pop(row)

    def accept_with_validate(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "提示", "漫画名称不能为空")
            return

        if self.episode_widget is not None:
            updates = self.episode_widget.get_episode_updates()
            orders = [item["episode_order"] for item in updates]
            if len(orders) != len(set(orders)):
                QMessageBox.warning(self, "提示", "各集顺序不能重复")
                return
            if any(not str(item["episode_name"]).strip() for item in updates):
                QMessageBox.warning(self, "提示", "集名不能为空")
                return

        self.accept()

    def get_edited_data(self) -> tuple[str, str, str, int | None, str | None, list[dict], list[int], list[str]]:
        episode_updates: list[dict] = []
        deleted_episode_ids: list[int] = []
        if self.episode_widget is not None:
            episode_updates = self.episode_widget.get_episode_updates()
            deleted_episode_ids = self.episode_widget.get_deleted_episode_ids()

        return (
            self.name_edit.text().strip(),
            self.author_edit.text().strip(),
            self.tags_edit.text().strip(),
            self.group_combo.currentData(),
            self.cover_selector.get_selected_cover_path(),
            episode_updates,
            deleted_episode_ids,
            self.new_episode_folders.copy(),
        )
