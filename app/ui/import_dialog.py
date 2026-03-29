from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.utils.image_files import list_images_sorted

_EPISODE_PATTERN = re.compile(
    r"(?:第\s*(\d+)\s*[话集卷]|(?:ep|e)\s*\.?\s*(\d+)|\[(\d+)\]|\((\d+)\)|\b(\d{1,5})\b)",
    re.IGNORECASE,
)


@dataclass
class AutoImportRequest:
    folder: Path
    author: str
    tags: str
    custom_name: str = ""


def _guess_name_and_episode(folder_name: str) -> tuple[str, int | None]:
    match = _EPISODE_PATTERN.search(folder_name)
    episode: int | None = None
    if match:
        for g in match.groups():
            if g and g.isdigit():
                episode = int(g)
                break

    guessed_name = folder_name
    if match:
        guessed_name = folder_name.replace(match.group(0), " ")
    guessed_name = re.sub(r"[\[\](){}._\-]+", " ", guessed_name)
    guessed_name = re.sub(r"\s+", " ", guessed_name).strip()
    return guessed_name or folder_name, episode


class ImportDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("导入漫画")
        self.resize(540, 260)
        self.selected_folder: Path | None = None

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)

        self.folder_label = QLabel("未选择")
        browse_button = QPushButton("选择文件夹")
        browse_button.clicked.connect(self.choose_folder)

        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_label)
        folder_row.addWidget(browse_button)
        form.addRow("导入目录", folder_row)

        self.detected_type_label = QLabel("未检测")
        self.detected_name_label = QLabel("-")
        self.detected_episode_label = QLabel("-")
        self.image_count_label = QLabel("0 张")

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入或修改漫画名称")
        self.author_edit = QLineEdit()
        self.author_edit.setPlaceholderText("可选")
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("可选")

        form.addRow("识别类型", self.detected_type_label)
        form.addRow("识别漫画", self.detected_name_label)
        form.addRow("漫画名称", self.name_edit)
        form.addRow("识别集数", self.detected_episode_label)
        form.addRow("检测图片数", self.image_count_label)
        form.addRow("作者(可选)", self.author_edit)
        form.addRow("标签(可选)", self.tags_edit)

        hint = QLabel("说明：软件会自动判断是单集导入还是多集导入，并自动识别漫画名与集数。")
        hint.setWordWrap(True)
        root.addWidget(hint)

        action_row = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        confirm_btn = QPushButton("导入")
        cancel_btn.clicked.connect(self.reject)
        confirm_btn.clicked.connect(self.accept_with_validate)
        action_row.addStretch(1)
        action_row.addWidget(cancel_btn)
        action_row.addWidget(confirm_btn)
        root.addLayout(action_row)

    def choose_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择漫画目录")
        if directory:
            self.selected_folder = Path(directory)
            self.folder_label.setText(directory)
            self._apply_auto_detect(self.selected_folder)

    def _apply_auto_detect(self, folder: Path) -> None:
        direct_images = list_images_sorted(folder)
        child_folders = [p for p in folder.iterdir() if p.is_dir()]
        child_episode_folders = [p for p in child_folders if list_images_sorted(p)]

        if direct_images and not child_episode_folders:
            guessed_name, guessed_episode = _guess_name_and_episode(folder.name)
            self.detected_type_label.setText("单集导入")
            self.detected_name_label.setText(guessed_name)
            self.name_edit.setText(guessed_name)
            self.detected_episode_label.setText(str(guessed_episode or 1))
            self.image_count_label.setText(f"{len(direct_images)} 张")
            return

        if child_episode_folders:
            self.detected_type_label.setText("多集导入")
            self.detected_name_label.setText(folder.name)
            self.name_edit.setText(folder.name)
            self.detected_episode_label.setText(f"共 {len(child_episode_folders)} 集")
            total_images = sum(len(list_images_sorted(p)) for p in child_episode_folders)
            self.image_count_label.setText(f"{total_images} 张")
            return

        self.detected_type_label.setText("未识别")
        self.detected_name_label.setText("-")
        self.name_edit.clear()
        self.detected_episode_label.setText("-")
        self.image_count_label.setText("0 张")

    def accept_with_validate(self) -> None:
        if self.selected_folder is None:
            QMessageBox.warning(self, "提示", "请选择导入目录")
            return
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "提示", "请输入漫画名称")
            return
        self.accept()

    def build_request(self) -> AutoImportRequest:
        assert self.selected_folder is not None
        return AutoImportRequest(
            folder=self.selected_folder,
            author=self.author_edit.text().strip(),
            tags=self.tags_edit.text().strip(),
            custom_name=self.name_edit.text().strip(),
        )
