from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QMessageBox,
)


class EditSeriesDialog(QDialog):
    def __init__(
        self,
        series_id: int,
        name: str,
        author: str,
        tags: str,
        groups: list[tuple[int, str]],
        selected_group_id: int | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.series_id = series_id
        self.setWindowTitle(f"编辑漫画《{name}》")
        self.resize(500, 290)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setText(name)
        self.author_edit = QLineEdit()
        self.author_edit.setText(author)
        self.tags_edit = QLineEdit()
        self.tags_edit.setText(tags)
        self.tags_edit.setPlaceholderText("多个标签用空格分隔")

        self.group_combo = QComboBox()
        self.group_combo.addItem("未分组", None)
        for group_id, group_name in groups:
            self.group_combo.addItem(group_name, group_id)

        if selected_group_id is not None:
            idx = self.group_combo.findData(selected_group_id)
            if idx >= 0:
                self.group_combo.setCurrentIndex(idx)

        form.addRow("漫画名称", self.name_edit)
        form.addRow("作者", self.author_edit)
        form.addRow("标签", self.tags_edit)
        form.addRow("所属分组", self.group_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept_with_validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept_with_validate(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "提示", "漫画名称不能为空")
            return
        self.accept()

    def get_edited_data(self) -> tuple[str, str, str, int | None]:
        """返回编辑后的 (name, author, tags, group_id)"""
        return (
            self.name_edit.text().strip(),
            self.author_edit.text().strip(),
            self.tags_edit.text().strip(),
            self.group_combo.currentData(),
        )
