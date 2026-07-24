import os
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox,
    QDialogButtonBox, QPushButton, QWidget, QHBoxLayout,
    QFileDialog, QMessageBox,
)


class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建项目")
        self.setMinimumWidth(480)
        self.setStyleSheet("""
            QDialog{background:#2d2d2d;color:#ddd}
            QLabel{color:#ccc;font-size:12px}
            QLineEdit,QSpinBox,QDoubleSpinBox{
                background:#1e1e1e;border:1px solid #555;color:#ddd;
                padding:4px 8px;border-radius:3px;font-size:12px
            }
            QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus{
                border-color:#0e639c
            }
            QPushButton{
                background:#3a3a3a;border:1px solid #555;color:#ddd;
                padding:5px 14px;border-radius:3px;font-size:12px
            }
            QPushButton:hover{background:#4a4a4a}
            QPushButton#okBtn{background:#0e639c;border-color:#1177bb;font-weight:bold}
            QPushButton#okBtn:hover{background:#1177bb}
            QPushButton#browseBtn{background:#0e639c;border-color:#1177bb;padding:4px 12px}
            QPushButton#browseBtn:hover{background:#1177bb}
        """)

        layout = QFormLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 16, 20, 16)

        self.name_edit = QLineEdit("未命名项目")
        self.name_edit.setPlaceholderText("输入项目名称")
        layout.addRow("项目名称:", self.name_edit)

        self.channels_spin = QSpinBox()
        self.channels_spin.setRange(1, 999999)
        self.channels_spin.setValue(200)
        self.channels_spin.setToolTip("传感器通道数（≥1，无上限）")
        layout.addRow("传感器通道数:", self.channels_spin)

        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0.01, 100.0)
        self.radius_spin.setValue(1.0)
        self.radius_spin.setDecimals(2)
        self.radius_spin.setSuffix(" cm")
        self.radius_spin.setToolTip("Cell 圆形触点的半径")
        layout.addRow("Cell 半径:", self.radius_spin)

        model_row = QWidget()
        model_hl = QHBoxLayout(model_row)
        model_hl.setContentsMargins(0, 0, 0, 0)
        model_hl.setSpacing(6)
        self.model_edit = QLineEdit()
        self.model_edit.setReadOnly(True)
        self.model_edit.setPlaceholderText("选择3D模型文件...")
        browse_btn = QPushButton("浏览...")
        browse_btn.setObjectName("browseBtn")
        browse_btn.clicked.connect(self._browse_model)
        model_hl.addWidget(self.model_edit, 1)
        model_hl.addWidget(browse_btn)
        layout.addRow("模型文件:", model_row)

        self.real_height = QDoubleSpinBox()
        self.real_height.setRange(0, 10000.0)
        self.real_height.setValue(0)
        self.real_height.setDecimals(1)
        self.real_height.setSuffix(" cm")
        self.real_height.setToolTip("模型最长边的真实长度。填0=自动判断，填数值=按此缩放整个模型和Cell")
        layout.addRow("模型最长边:", self.real_height)

        btn_box = QDialogButtonBox()
        ok_btn = QPushButton("确定")
        ok_btn.setObjectName("okBtn")
        cancel_btn = QPushButton("取消")
        btn_box.addButton(ok_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        btn_box.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)
        btn_box.accepted.connect(self._validate_and_accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

        self._model_path = ""

    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择3D模型", "",
            "3D模型 (*.stl *.stp *.step *.obj *.glb *.gltf);;"
            "STL (*.stl);;STEP (*.stp *.step);;OBJ (*.obj);;"
            "GLB/GLTF (*.glb *.gltf);;All (*.*)"
        )
        if path:
            self._model_path = path
            self.model_edit.setText(Path(path).name)

    def _validate_and_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "验证失败", "请输入项目名称")
            return
        if not self._model_path or not os.path.isfile(self._model_path):
            QMessageBox.warning(self, "验证失败", "请选择有效的3D模型文件")
            return
        if self.channels_spin.value() < 1:
            QMessageBox.warning(self, "验证失败", "通道数必须至少为1")
            return
        self.accept()

    def get_project_info(self):
        return {
            "name": self.name_edit.text().strip(),
            "channels": self.channels_spin.value(),
            "model_path": self._model_path,
            "real_height": self.real_height.value() * 10,
            "cell_radius": self.radius_spin.value() * 10,
        }
