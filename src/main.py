"""
3D拟物Layout编辑器 v1.0
PyQt5 + QWebEngineView + Three.js (本地HTTP服务器)
"""
import sys
import os
import json
import base64
import zipfile
import uuid
import time as _time
from pathlib import Path
from urllib.parse import quote
from datetime import datetime

from PyQt5.QtCore import QUrl, QSettings, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QFrame, QMessageBox, QAction, QDialog,
)
from PyQt5.QtWebEngineWidgets import QWebEngineView

from core.bridge import Bridge, BridgePage
from core.exceptions import STPConversionError
from ui.dialogs import NewProjectDialog
from render.model_importer import start_server, convert_step_to_stl_bytes, decimate_stl

APP = "3D拟物Layout编辑器"
VER = "1.0.0"
ORG = "TactileSense"

BTN = (
    "QPushButton{background:#3a3a3a;border:1px solid #555;color:#ddd;"
    "padding:4px 10px;border-radius:3px;font-size:11px}"
    "QPushButton:hover{background:#4a4a4a}"
    "QPushButton:disabled{color:#666}"
)


def find_root():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return str(Path(__file__).resolve().parent.parent)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        import logging as _logging
        log_dir = os.path.join(find_root(), "src", "log")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(
            log_dir,
            datetime.now().strftime("app_%Y%m%d_%H%M%S.log")
        )
        self._log_fp = open(log_file, 'w', encoding='utf-8')
        self._log_fp.write(f"=== 3D拟物Layout编辑器 v{VER} ===\n")
        self._log_fp.write(f"启动: {datetime.now().isoformat()}\n\n")
        self._log_fp.flush()

        def log_op(msg):
            ts = datetime.now().strftime("%H:%M:%S")
            self._log_fp.write(f"[{ts}] {msg}\n")
            self._log_fp.flush()

        self._log_op = log_op
        self.setWindowTitle(f"{APP} v{VER}")
        self.resize(1440, 900)
        self.setMinimumSize(1024, 700)
        self.setStyleSheet("QMainWindow{background:#1e1e1e}")

        icon_path = os.path.join(find_root(), "download.png")
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._profile = None
        self._current_file = None
        self._dirty = False
        self._model_loaded = False
        self._loading = False
        self._close_after_save = False
        self._recent_files = QSettings(ORG, APP).value("recentFiles", []) or []
        self._project_info = {}

        self.bridge = Bridge()
        self.bridge.exportReady.connect(self._on_export)
        self.bridge.statusMsg.connect(lambda m: self._sl.setText(m))
        self.bridge.menuAction.connect(self._on_menu_action)
        self.bridge.recordData.connect(self._on_record_data)

        self._init_toolbar()
        self._init_webview()
        self._init_statusbar()
        self._init_shortcuts()

    def _init_toolbar(self):
        top = QFrame()
        top.setFixedHeight(34)
        top.setStyleSheet(
            "QFrame{background:#2d2d2d;border-bottom:1px solid #3a3a3a}"
        )
        hl = QHBoxLayout(top)
        hl.setContentsMargins(6, 3, 6, 3)
        hl.setSpacing(3)
        for label, cb in [
            ("新建", self._new_project),
            ("打开", self._open_profile),
            ("保存", self._save_direct),
            ("另存为", self._save_as),
            (None, None),
            ("截图PNG", self._screenshot),
        ]:
            if label is None:
                hl.addSpacing(8)
                continue
            btn = QPushButton(label)
            btn.setStyleSheet(BTN)
            btn.setFixedHeight(26)
            btn.clicked.connect(cb)
            hl.addWidget(btn)
        hl.addStretch()
        self.setMenuWidget(top)

    def _init_webview(self):
        self.webview = QWebEngineView()
        self.webview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        root = find_root()
        html_path = os.path.join(root, "src", "3D编辑器原型.html")
        if not os.path.isfile(html_path):
            QMessageBox.critical(self, "错误", f"找不到:\n{html_path}")
            return

        page = BridgePage(self.bridge, self.webview)
        self.webview.setPage(page)
        self.bridge.set_wv(self.webview)

        port = start_server(root)

        import urllib.parse as _up
        url_path = _up.quote("src/3D编辑器原型.html")
        url = f"http://127.0.0.1:{port}/{url_path}"

        self._load_retries = 0

        def on_load_finished(ok):
            if ok:
                pass
            else:
                self._load_retries += 1
                if self._load_retries <= 3:
                    QTimer.singleShot(
                        1000, lambda: self.webview.load(QUrl(url))
                    )

        self.webview.loadFinished.connect(on_load_finished)
        self.webview.load(QUrl(url))

        cw = QWidget()
        cv = QVBoxLayout(cw)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        cv.addWidget(self.webview, 1)
        self.setCentralWidget(cw)

    def _init_statusbar(self):
        sb = self.statusBar()
        sb.setStyleSheet(
            "QStatusBar{background:#007acc;color:#fff;font-size:11px;padding:2px 10px}"
        )
        self._sl = QLabel("就绪 — 点击「新建」导入STL | Ctrl+Click放置Cell")
        sb.addWidget(self._sl)

    def _init_shortcuts(self):
        for key, func in [
            ("Ctrl+N", self._new_project),
            ("Ctrl+O", self._open_profile),
            ("Ctrl+S", self._save_direct),
            ("Ctrl+Shift+S", self._save_as),
            ("Ctrl+Z", lambda: self.bridge.cmd("undo")),
            ("Ctrl+Y", lambda: self.bridge.cmd("redo")),
            ("Delete", lambda: self.bridge.cmd("deleteCell")),
            ("Escape", lambda: self.bridge.cmd("escape")),
            ("Tab", lambda: self.bridge.cmd("toggleEdit")),
        ]:
            a = QAction(self)
            a.setShortcut(key)
            a.triggered.connect(func)
            self.addAction(a)

    # ── 保存/导出 ──

    def _on_export(self, json_str):
        data = json.loads(json_str)
        cells = data.get("cells", [])
        total = data.get("total_points", 0)
        path = getattr(self, '_pending_save_path', None)
        if not path:
            return
        unit_mm = data.get("unit_mm") or self._project_info.get("unit_mm", 1.0)
        cell_radius = data.get("cell_radius") or 10.0
        self._project_info["unit_mm"] = unit_mm
        self._project_info["cell_radius"] = cell_radius

        cells_json = []
        for c in cells:
            center = (
                c.get("center_mm")
                or c.get("center_3d")
                or {"x": 0, "y": 0, "z": 0}
            )
            cells_json.append({
                "id": c.get("id", 0),
                "center_mm": {
                    "x": center.get("x", 0),
                    "y": center.get("y", 0),
                    "z": center.get("z", 0),
                },
                "normal": c.get("normal", {"x": 0, "y": 0, "z": 1}),
                "radius_mm": c.get("radius_mm", 10.0),
                "rotation_deg": c.get("rotation_deg", c.get("rot", 0.0)),
                "label": c.get("label", ""),
                "pressure": c.get("pressure", 0),
            })

        render_config = data.get("renderConfig", {})
        project = {
            "version": "2.1",
            "schema_version": 1,
            "coordinate_space": "model_local_mm",
            "project_name": self._project_info.get("name", ""),
            "created_at": self._project_info.get(
                "created_at", datetime.now().isoformat()
            ),
            "total_points": total or len(cells_json),
            "unit_mm": unit_mm,
            "cell_radius": cell_radius,
            "surface_model": {
                "format": getattr(self, '_model_format', 'stl'),
                "file_name": getattr(self, '_model_name', 'model.stl'),
            },
            "cells": cells_json,
        }
        if render_config:
            project["renderConfig"] = render_config
        try:
            if path.endswith('.3dlp'):
                self._save_package(path, project)
            else:
                cache_path = getattr(self, '_model_cache_path', None)
                if cache_path and os.path.isfile(cache_path):
                    project["surface_model"]["data_base64"] = (
                        base64.b64encode(Path(cache_path).read_bytes()).decode()
                    )
                Path(path).write_text(
                    json.dumps(project, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            self._pending_save_path = None
            self._current_file = path
            self._dirty = False
            self._sl.setText(
                f"已保存: {Path(path).name} ({len(cells_json)}个Cell)"
            )
            self._log_op(
                f"保存项目: {Path(path).name} | {len(cells_json)}个Cell"
            )
            if self._close_after_save:
                self.close()
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_record_data(self, b64_data, size):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存录制", "recording.webm", "WebM (*.webm)"
        )
        if path:
            try:
                Path(path).write_bytes(base64.b64decode(b64_data))
                self._sl.setText(f"录制已保存: {Path(path).name}")
            except Exception as ex:
                QMessageBox.warning(self, "保存失败", str(ex))

    def _save_package(self, path, project):
        model_name = project["surface_model"]["file_name"]
        cache_path = getattr(self, '_model_cache_path', None)
        if cache_path and os.path.isfile(cache_path):
            raw_model = Path(cache_path).read_bytes()
        else:
            QMessageBox.warning(self, "保存失败", "模型缓存数据为空")
            return
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
            project_copy = json.loads(json.dumps(project))
            fmt = project_copy.pop("surface_model", {}).get("format", "stl")
            project_copy["model_file"] = model_name
            project_copy["model_format"] = fmt
            zf.writestr(
                "project.json",
                json.dumps(project_copy, indent=2, ensure_ascii=False),
            )
            zf.writestr(model_name, raw_model)
        self._current_file = path

    # ── 新建项目 ──

    def _new_project(self):
        if not self._confirm_discard():
            return
        dlg = NewProjectDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        info = dlg.get_project_info()
        path = info["model_path"]
        fmt = Path(path).suffix.lstrip('.').lower()
        self._log_op(
            f"新建项目: {info['name']} | 模型: {Path(path).name} | 格式: {fmt}"
        )

        # ── 步骤1: 准备模型数据 (STEP转换 或 直接读取) ──
        model_name = Path(path).stem + ".stl" \
            if path.endswith(('.stp', '.step')) else Path(path).name
        self._model_name = model_name
        self._model_format = 'stl' if path.endswith(('.stp', '.step')) else fmt
        self._model_b64 = None
        self._project_info = info

        root = find_root()
        converter = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "stp_converter.py"
        )
        if getattr(sys, 'frozen', False):
            converter = os.path.join(root, "src", "stp_converter.py")

        try:
            if fmt in ('stp', 'step'):
                self._sl.setText("正在转换STEP格式...")
                raw, face_count = convert_step_to_stl_bytes(
                    path, converter, log_cb=lambda m: print(m, flush=True)
                )
                self._log_op(f"STP转换成功: {face_count}面")
            else:
                raw = Path(path).read_bytes()
        except FileNotFoundError as e:
            QMessageBox.warning(self, "STEP转换失败", str(e))
            return
        except STPConversionError as e:
            QMessageBox.warning(self, "STEP转换失败", str(e))
            return
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(
                self, "STEP转换失败", f"{type(e).__name__}: {str(e)[:500]}"
            )
            return

        # ── 步骤2: 大模型降采样 (仅 STL) ──
        cache_dir = os.path.join(root, "src", "_model_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, model_name)

        decimated = False; original_faces = 0; actual_faces = 0
        if self._model_format == 'stl':
            raw, decimated, original_faces, actual_faces = decimate_stl(
                raw, log_cb=lambda m: self._sl.setText(m)
            )
        if decimated:
            msg = f"降采样成功: {original_faces}→{actual_faces}面"
            self._sl.setText(msg)
            self._log_op(msg)

        Path(cache_path).write_bytes(raw)
        self._model_cache_path = cache_path

        # ── 步骤3: 发送给JS渲染引擎 ──
        self._loading = True
        self.bridge.cmd("loadStl", {
            "url": f"/src/_model_cache/{quote(model_name)}",
            "name": model_name,
            "format": self._model_format,
            "total_points": info["channels"],
            "real_height": info.get("real_height", 0),
            "cell_radius": info.get("cell_radius", 10.0),
            "decimated": decimated,
            "original_faces": original_faces,
            "actual_faces": actual_faces,
        })
        self._current_file = None
        self._sl.setText(
            f"项目: {info['name']} | 模型: {model_name} | 通道: {info['channels']}"
        )

    # ── 打开项目 ──

    def _open_profile(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "打开项目", "",
            "3D Layout Package (*.3dlp);;JSON (*.json);;All (*.*)"
        )
        if not path:
            return
        try:
            if path.endswith('.3dlp'):
                self._loading = True
                self._open_package(path)
            else:
                self._open_legacy_json(path)
            self._current_file = path
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))

    def _open_package(self, path):
        self._log_op(f"打开工程: {Path(path).name}")
        with zipfile.ZipFile(path, 'r') as zf:
            names = zf.namelist()
            project_data = json.loads(zf.read("project.json").decode("utf-8"))
            model_name = project_data.get("model_file", "model.stl")
            if model_name in zf.namelist():
                raw = zf.read(model_name)
            else:
                raise FileNotFoundError(f"模型文件 {model_name} 在包中未找到")

        self._model_name = model_name
        self._model_format = (
            project_data.get("model_format")
            or Path(model_name).suffix.lstrip('.').lower()
        )

        # 打开工程也进行降采样
        decimated = False
        original_faces = 0
        actual_faces = 0
        if self._model_format == 'stl' and len(raw) > 84:
            raw, decimated, original_faces, actual_faces = decimate_stl(
                raw, log_cb=lambda m: print(m, flush=True)
            )

        self._model_b64 = None
        self._project_info = {
            "name": project_data.get("project_name", ""),
            "created_at": project_data.get("created_at", ""),
            "unit_mm": project_data.get("unit_mm", 1.0),
            "cell_radius": project_data.get("cell_radius", 10.0),
            "channels": project_data.get("total_points", 200),
        }
        cells = project_data.get("cells", [])
        total = project_data.get("total_points", len(cells))

        coord_space = project_data.get("coordinate_space") or ""
        if not coord_space:
            has_c3 = any("center_3d" in c for c in cells[:1]) if cells else False
            coord_space = "model_local_mm_legacy" if has_c3 else ""

        root = find_root()
        cache_dir = os.path.join(root, "src", "_model_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_name = f"opened_{uuid.uuid4().hex[:8]}_{model_name}"
        cache_path = os.path.join(cache_dir, cache_name)
        Path(cache_path).write_bytes(raw)
        self._model_cache_path = cache_path

        actual_size = Path(cache_path).stat().st_size
        if actual_size != len(raw):
            QMessageBox.warning(
                self, "文件错误",
                f"模型缓存写入不完整: {actual_size} vs {len(raw)}"
            )
            return

        url = (
            f"/src/_model_cache/{quote(cache_name)}"
            f"?v={int(_time.time() * 1000)}"
        )
        self.bridge.cmd("loadStl", {
            "url": url,
            "name": model_name,
            "cells": cells,
            "total_points": total,
            "format": self._model_format,
            "unit_mm": self._project_info.get("unit_mm", 1.0),
            "cell_radius": self._project_info.get("cell_radius", 10.0),
            "schema_version": project_data.get("schema_version", 0),
            "coordinate_space": coord_space,
            "decimated": decimated,
            "original_faces": original_faces,
            "actual_faces": actual_faces,
        })
        self._sl.setText(
            f"已打开: {Path(path).name} | "
            f"项目: {self._project_info.get('name', '')} | "
            f"模型: {model_name} | "
            f"Cell: {len(cells)}"
        )

    def _open_legacy_json(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        version = data.get("version", "2.0")
        cells = data.get("cells", [])
        sm = data.get("surface_model", {})
        model_b64 = sm.get("data_base64", "")
        model_name = sm.get("file_name", "model.stl")
        self._model_name = model_name
        self._model_format = sm.get("format", "stl")
        self._model_b64 = None
        self._project_info = {
            "name": data.get("project_name", data.get("display_name", "")),
            "created_at": data.get("created_at", ""),
            "unit_mm": data.get("unit_mm", 1.0),
            "cell_radius": data.get("cell_radius", 10.0),
            "channels": data.get("total_points", 200),
        }
        total = data.get("total_points", len(cells))

        root = find_root()
        cache_dir = os.path.join(root, "src", "_model_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, model_name)

        if model_b64:
            Path(cache_path).write_bytes(base64.b64decode(model_b64))
            self._model_cache_path = cache_path
            self.bridge.cmd("loadStl", {
                "url": f"/src/_model_cache/{quote(model_name)}",
                "name": model_name,
                "cells": cells,
                "total_points": total,
                "format": self._model_format,
            })
            self._sl.setText(
                f"已打开: {Path(path).name} (v{version}) [模型:{model_name}]"
            )
        else:
            self.bridge.cmd("loadJsonCells", cells)
            self._sl.setText(
                f"已打开: {Path(path).name} (v{version}) [无3D模型]"
            )

    # ── 保存 ──

    def _save_direct(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存项目", "project.3dlp",
            "3D Layout Package (*.3dlp);;JSON (*.json)"
        )
        if not path:
            return
        if not (path.endswith('.3dlp') or path.endswith('.json')):
            path += '.3dlp'
        self._pending_save_path = path
        self.bridge.cmd("exportCells")

    def _save_as(self):
        self._save_direct()

    def _on_menu_action(self, action):
        if action == 'new':
            self._new_project()
        elif action == 'open':
            self._open_profile()
        elif action == 'save':
            self._save_direct()
        elif action == 'saveAs':
            self._save_as()

    def _screenshot(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出截图", "screenshot.png", "PNG (*.png)"
        )
        if not path:
            return
        self.bridge.cmd("screenshot", {"path": path})

    # ── 关闭/丢弃 ──

    def _has_open_project(self):
        return bool(
            getattr(self, '_model_cache_path', None)
            or self._current_file
            or self._project_info.get('name')
            or self._model_loaded
        )

    def _confirm_discard(self):
        has_project = self._has_open_project()
        if not has_project:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("关闭前保存")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("当前项目将被关闭")
        box.setInformativeText(
            "要先保存当前项目吗？" if self._dirty
            else "当前项目已加载，是否先保存再关闭？"
        )
        save_btn = box.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
        discard_btn = box.addButton("不保存", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_btn:
            self._close_after_save = True
            self._save_direct()
            if not getattr(self, '_pending_save_path', None):
                self._close_after_save = False
            return False
        if clicked is discard_btn:
            return True
        return False

    def closeEvent(self, event):
        if self._close_after_save:
            self._close_after_save = False
            self._model_loaded = False
            if hasattr(self, '_log_fp'):
                try:
                    self._log_fp.close()
                except Exception:
                    pass
            event.accept()
            return
        if self._confirm_discard():
            if hasattr(self, '_log_fp'):
                try:
                    self._log_fp.close()
                except Exception:
                    pass
            event.accept()
        else:
            event.ignore()


def main():
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = (
        '--no-sandbox --ignore-gpu-blocklist --enable-webgl'
    )
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
