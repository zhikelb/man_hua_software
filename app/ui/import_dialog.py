from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt
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
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QScrollArea,
    QWidget,
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


@dataclass
class EpisodeImportInfo:
    """多集导入的集数信息"""
    folder_name: str
    guessed_number: int | None
    image_count: int


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
        self.resize(700, 600)
        self.selected_folder: Path | None = None
        self.episode_spins: dict[int, QSpinBox] = {}  # row -> QSpinBox
        self.episode_infos: list[EpisodeImportInfo] = []

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

        # 多集导入时的集数详细信息表
        self.episode_table_label = QLabel("各集详细信息（多集导入时）：")
        self.episode_table_label.setVisible(False)
        root.addWidget(self.episode_table_label)
        
        self.episode_table = QTableWidget()
        self.episode_table.setColumnCount(3)
        self.episode_table.setHorizontalHeaderLabels(["文件夹名", "自动识别集数", "修改集数"])
        self.episode_table.setVisible(False)
        self.episode_table.setMaximumHeight(250)
        root.addWidget(self.episode_table)

        hint = QLabel("说明：软件会自动判断是单集导入还是多集导入，并自动识别漫画名与集数。多集导入时可在下方表格修改各集的集数。")
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
        child_folders.sort(key=lambda p: p.name)
        child_episode_folders = [p for p in child_folders if list_images_sorted(p)]

        if direct_images and not child_episode_folders:
            guessed_name, guessed_episode = _guess_name_and_episode(folder.name)
            self.detected_type_label.setText("单集导入")
            self.detected_name_label.setText(guessed_name)
            self.name_edit.setText(guessed_name)
            self.detected_episode_label.setText(str(guessed_episode or 1))
            self.image_count_label.setText(f"{len(direct_images)} 张")
            self.episode_table.setVisible(False)
            self.episode_table_label.setVisible(False)
            return

        if child_episode_folders:
            self.detected_type_label.setText("多集导入")
            self.detected_name_label.setText(folder.name)
            self.name_edit.setText(folder.name)
            
            # 分析每一集的信息
            self.episode_infos = []
            total_images = 0
            for ep_folder in child_episode_folders:
                images = list_images_sorted(ep_folder)
                _, guessed_ep_num = _guess_name_and_episode(ep_folder.name)
                self.episode_infos.append(
                    EpisodeImportInfo(
                        folder_name=ep_folder.name,
                        guessed_number=guessed_ep_num,
                        image_count=len(images),
                    )
                )
                total_images += len(images)
            
            self.detected_episode_label.setText(f"共 {len(child_episode_folders)} 集")
            self.image_count_label.setText(f"{total_images} 张")
            
            # 构建集数详细信息表
            self._populate_episode_table()
            self.episode_table.setVisible(True)
            self.episode_table_label.setVisible(True)
            return

        self.detected_type_label.setText("未识别")
        self.detected_name_label.setText("-")
        self.name_edit.clear()
        self.detected_episode_label.setText("-")
        self.image_count_label.setText("0 张")
        self.episode_table.setVisible(False)
        self.episode_table_label.setVisible(False)

    def _populate_episode_table(self) -> None:
        """填充集数信息表"""
        self.episode_table.setRowCount(0)
        self.episode_spins.clear()
        
        for idx, ep_info in enumerate(self.episode_infos):
            self.episode_table.insertRow(idx)
            
            # 文件夹名
            folder_item = QTableWidgetItem(ep_info.folder_name)
            folder_item.setFlags(folder_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.episode_table.setItem(idx, 0, folder_item)
            
            # 自动识别的集数
            guessed_num = ep_info.guessed_number or (idx + 1)
            guessed_item = QTableWidgetItem(str(guessed_num))
            guessed_item.setFlags(guessed_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.episode_table.setItem(idx, 1, guessed_item)
            
            # 集数修改输入框
            spin = QSpinBox()
            spin.setMinimum(1)
            spin.setMaximum(999)
            spin.setValue(guessed_num)
            self.episode_table.setCellWidget(idx, 2, spin)
            self.episode_spins[idx] = spin

    def get_episode_numbers(self) -> list[int]:
        """获取用户修改后的各集集数"""
        if not self.episode_spins:
            return []
        
        result = []
        for idx in sorted(self.episode_spins.keys()):
            spin = self.episode_spins[idx]
            result.append(spin.value())
        return result

    def accept_with_validate(self) -> None:
        if self.selected_folder is None:
            QMessageBox.warning(self, "提示", "请选择导入目录")
            return
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "提示", "请输入漫画名称")
            return
        
        # 检查多集导入时的集数是否有重复
        if self.episode_spins:
            ep_numbers = self.get_episode_numbers()
            if len(ep_numbers) != len(set(ep_numbers)):
                QMessageBox.warning(self, "提示", "各集的集数不能重复，请修改")
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
