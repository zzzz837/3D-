"""
3D拟物Layout编辑器 v1.0
PyQt5 + QWebEngineView + Three.js (本地HTTP服务器)
"""
import sys, os, json, base64, zipfile, subprocess
from pathlib import Path
from urllib.parse import quote
from datetime import datetime

from PyQt5.QtCore import QUrl, QObject, pyqtSignal, QSettings, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QFrame, QMessageBox, QDialog,
    QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox, QDialogButtonBox,
    QAction
)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage

APP = "3D拟物Layout编辑器"
VER = "1.0.0"
ORG = "TactileSense"
MAX_RECENT = 5

BTN = (
    "QPushButton{background:#3a3a3a;border:1px solid #555;color:#ddd;"
    "padding:4px 10px;border-radius:3px;font-size:11px}"
    "QPushButton:hover{background:#4a4a4a}"
    "QPushButton:disabled{color:#666}"
)


class Bridge(QObject):
    statusMsg = pyqtSignal(str)
    exportReady = pyqtSignal(str)
    menuAction = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent); self._wv = None; self._total = 0
    def set_wv(self, wv): self._wv = wv
    def cmd(self, name, data=None):
        if self._wv:
            payload = json.dumps(data or {}, ensure_ascii=False)
            self._wv.page().runJavaScript(
                f'window.pyCommand("{name}",{payload})'
            )
    def handle(self, msg):
        try:
            o = json.loads(msg); e = o.get("e",""); d = o.get("d",{})
            if e == "ready":
                self.statusMsg.emit("引擎就绪 | 点击「新建」导入STL模型")
            elif e == "state":
                landed = d.get("landed",0); total = d.get("max",landed+d.get("unlanded",0))
                self._total = max(total,1); ov = d.get("overlap",0)
                self.statusMsg.emit(f"已落地:{landed}/{self._total} | {'重叠:'+str(ov) if ov else '无重叠'}")
            elif e == "exportCells":
                self.exportReady.emit(json.dumps(d))
            elif e == "screenshotData":
                # JS发回截图base64 PNG
                path = d.get("path","")
                b64 = d.get("data","")
                if path and b64:
                    try:
                        import base64
                        Path(path).write_bytes(base64.b64decode(b64))
                        self.statusMsg.emit(f"截图已保存: {Path(path).name}")
                    except Exception as ex:
                        self.statusMsg.emit(f"截图失败: {ex}")
            elif e == "error":
                print(f"[JS Error] {d.get('msg','?')}", flush=True)
            elif e == "modelLoaded":
                rec = d.get("recommendedChannels",0)
                self.statusMsg.emit(
                    f"模型加载完成 | 面:{d.get('faces',0)} | 面积:{d.get('surfaceArea','?')}mm²"
                    + (f" | 建议通道:{rec}" if rec else "")
                )
            elif e == "menuAction":
                self.menuAction.emit(d.get("action",""))
        except Exception: pass
    @property
    def total_channels(self): return max(self._total, 1)


class BridgePage(QWebEnginePage):
    def __init__(self, bridge, parent=None):
        super().__init__(parent); self._bridge = bridge
    def javaScriptConsoleMessage(self, level, msg, line, src):
        try:
            text = str(msg)
            if text.startswith("BRIDGE:"):
                self._bridge.handle(text[7:])
            else:
                level_name = {0:"INFO",1:"WARN",2:"ERROR"}.get(level,"?")
                print(f"[JS {level_name}] L{line}: {text}", flush=True)
        except Exception: pass


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

        self.unit_spin = QDoubleSpinBox()
        self.unit_spin.setRange(0.001, 100000.0)
        self.unit_spin.setValue(1.0)
        self.unit_spin.setDecimals(3)
        self.unit_spin.setToolTip("1个模型单位 = 多少mm。导入后自动检测，可手动覆盖")
        layout.addRow("单位比例\n(mm/单位):", self.unit_spin)

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
            "unit_mm": self.unit_spin.value(),
        }


def find_root():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return str(Path(__file__).resolve().parent.parent)


def start_server(root_dir):
    """启动本地HTTP服务器，返回端口号"""
    import threading, http.server, socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            # 关键: directory=必须传给父类__init__，类属性会被覆盖
            super().__init__(*args, directory=root_dir, **kwargs)
        def log_message(self, *args): pass

    server = http.server.HTTPServer(('127.0.0.1', port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return port


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP} v{VER}")
        self.resize(1440, 900); self.setMinimumSize(1024, 700)
        self.setStyleSheet("QMainWindow{background:#1e1e1e}")
        # 设置窗口图标
        icon_path = os.path.join(find_root(), "download.png")
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._profile = None; self._current_file = None; self._dirty = False
        self._recent_files = QSettings(ORG, APP).value("recentFiles", []) or []
        self._project_info = {}  # 当前项目元信息

        self.bridge = Bridge()
        self.bridge.exportReady.connect(self._on_export)
        self.bridge.statusMsg.connect(lambda m: self._sl.setText(m))
        self.bridge.menuAction.connect(self._on_menu_action)

        self._init_toolbar()
        self._init_webview()
        self._init_statusbar()
        self._init_shortcuts()

    def _init_toolbar(self):
        top = QFrame(); top.setFixedHeight(34)
        top.setStyleSheet("QFrame{background:#2d2d2d;border-bottom:1px solid #3a3a3a}")
        hl = QHBoxLayout(top); hl.setContentsMargins(6,3,6,3); hl.setSpacing(3)
        for label, cb in [
            ("新建", self._new_project), ("打开", self._open_profile),
            ("保存", self._save_direct), ("另存为", self._save_as),
            (None,None), ("截图PNG", self._screenshot),
        ]:
            if label is None: hl.addSpacing(8); continue
            btn = QPushButton(label); btn.setStyleSheet(BTN); btn.setFixedHeight(26)
            btn.clicked.connect(cb); hl.addWidget(btn)
        hl.addStretch(); self.setMenuWidget(top)

    def _init_webview(self):
        self.webview = QWebEngineView()
        self.webview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        root = find_root()
        print(f"[init] find_root() = {root}", flush=True)
        html_path = os.path.join(root, "src", "3D编辑器原型.html")
        print(f"[init] html_path = {html_path}", flush=True)
        if not os.path.isfile(html_path):
            QMessageBox.critical(self, "错误", f"找不到:\n{html_path}"); return

        page = BridgePage(self.bridge, self.webview)
        self.webview.setPage(page); self.bridge.set_wv(self.webview)

        port = start_server(root)
        print(f"[init] HTTP port = {port}", flush=True)

        import urllib.parse as _up
        url_path = _up.quote("src/3D编辑器原型.html")
        url = f"http://127.0.0.1:{port}/{url_path}"
        print(f"[init] loading URL = {url}", flush=True)

        self._load_retries = 0
        def on_load_finished(ok):
            if ok:
                print("[init] WebEngine load succeeded", flush=True)
            else:
                self._load_retries += 1
                print(f"[init] WebEngine load FAILED (attempt {self._load_retries}/3)", flush=True)
                if self._load_retries <= 3:
                    QTimer.singleShot(1000, lambda: self.webview.load(QUrl(url)))

        self.webview.loadFinished.connect(on_load_finished)
        self.webview.load(QUrl(url))

        cw = QWidget(); cv = QVBoxLayout(cw)
        cv.setContentsMargins(0,0,0,0); cv.setSpacing(0)
        cv.addWidget(self.webview, 1); self.setCentralWidget(cw)

    def _init_statusbar(self):
        sb = self.statusBar()
        sb.setStyleSheet("QStatusBar{background:#007acc;color:#fff;font-size:11px;padding:2px 10px}")
        self._sl = QLabel("就绪 — 点击「新建」导入STL | Ctrl+Click放置Cell")
        sb.addWidget(self._sl)

    def _init_shortcuts(self):
        for key, func in [
            ("Ctrl+N", self._new_project), ("Ctrl+O", self._open_profile),
            ("Ctrl+S", self._save_direct), ("Ctrl+Shift+S", self._save_as),
            ("Ctrl+Z", lambda: self.bridge.cmd("undo")),
            ("Ctrl+Y", lambda: self.bridge.cmd("redo")),
            ("Delete", lambda: self.bridge.cmd("deleteCell")),
            ("Escape", lambda: self.bridge.cmd("escape")),
            ("Tab", lambda: self.bridge.cmd("toggleEdit")),
        ]:
            a = QAction(self); a.setShortcut(key)
            a.triggered.connect(func); self.addAction(a)

    def _on_export(self, json_str):
        data = json.loads(json_str)
        cells = data.get("cells", [])
        total = data.get("total_points", 0)
        path = getattr(self, '_pending_save_path', None)
        if not path:
            return
        cells_json = []
        for c in cells:
            cells_json.append({
                "id": c.get("id", 0),
                "center_3d": c.get("center_3d", {"x": c.get("x",0), "y": c.get("y",0), "z": c.get("z",0)}),
                "normal": c.get("normal", {"x": c.get("nx",0), "y": c.get("ny",0), "z": c.get("nz",1)}),
                "radius_mm": c.get("radius_mm", c.get("radius", c.get("width_mm", 10.0)/2)),
                "width_mm": c.get("width_mm", c.get("radius_mm", 10.0)*2),
                "height_mm": c.get("height_mm", c.get("radius_mm", 10.0)*2),
                "rotation_deg": c.get("rotation_deg", c.get("rot", 0.0)),
                "label": c.get("label", ""),
            })
        project = {
            "version": "2.0",
            "project_name": self._project_info.get("name", ""),
            "created_at": self._project_info.get("created_at", datetime.now().isoformat()),
            "total_points": total or len(cells_json),
            "unit_mm": self._project_info.get("unit_mm", 1.0),
            "surface_model": {
                "format": getattr(self, '_model_format', 'stl'),
                "file_name": getattr(self, '_model_name', 'model.stl'),
            },
            "cells": cells_json,
        }
        try:
            if path.endswith('.3dlp'):
                self._save_package(path, project)
            else:
                # Legacy JSON: embed base64 from cache file for backward compat
                cache_path = getattr(self, '_model_cache_path', None)
                if cache_path and os.path.isfile(cache_path):
                    project["surface_model"]["data_base64"] = base64.b64encode(
                        Path(cache_path).read_bytes()
                    ).decode()
                Path(path).write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
            self._pending_save_path = None
            self._current_file = path
            self._sl.setText(f"已保存: {Path(path).name} ({len(cells_json)}个Cell)")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))

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
            project_copy.pop("surface_model", None)
            project_copy["model_file"] = model_name
            zf.writestr("project.json", json.dumps(project_copy, indent=2, ensure_ascii=False))
            zf.writestr(model_name, raw_model)
        self._current_file = path

    def _new_project(self):
        if not self._confirm_discard(): return
        dlg = NewProjectDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        info = dlg.get_project_info()
        path = info["model_path"]
        fmt = Path(path).suffix.lstrip('.').lower()
        if fmt in ('stp', 'step'):
            self._sl.setText("正在转换STEP格式...")
            try:
                # 在 frozen 模式，stp_converter.py 在 _internal/src/ 下
                if getattr(sys, 'frozen', False):
                    converter = os.path.join(find_root(), "src", "stp_converter.py")
                else:
                    converter = os.path.join(os.path.dirname(__file__), "stp_converter.py")
                result = subprocess.run(
                    [sys.executable, converter, path],
                    capture_output=True, text=False, timeout=300
                )
                if result.returncode != 0:
                    err = result.stderr.decode('utf-8', errors='replace') if result.stderr else "未知错误"
                    raise RuntimeError(err)
                raw = result.stdout
                fmt = 'stl'
            except FileNotFoundError:
                QMessageBox.warning(self, "STEP转换失败",
                    "未找到 stp_converter.py，请确保已安装 pythonocc-core\n"
                    "运行: pip install pythonocc-core")
                return
            except Exception as e:
                QMessageBox.warning(self, "STEP转换失败",
                    f"无法转换STEP文件。请确保已安装 pythonocc-core。\n\n{str(e)}")
                return
        else:
            raw = Path(path).read_bytes()
        model_name = Path(path).stem + ".stl" if fmt == 'stl' and path.endswith(('.stp', '.step')) else Path(path).name
        self._model_name = model_name
        self._model_format = fmt
        self._model_b64 = None  # 不再用base64传大数据，改用HTTP URL
        self._project_info = info

        # 写入HTTP可访问的缓存目录，避免runJavaScript传超大base64导致崩溃
        cache_dir = os.path.join(find_root(), "src", "_model_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, model_name)
        Path(cache_path).write_bytes(raw)
        self._model_cache_path = cache_path

        self.bridge.cmd("loadStl", {
            "url": f"/src/_model_cache/{model_name}",
            "name": model_name,
            "format": fmt,
            "total_points": info["channels"],
        })
        if info["unit_mm"] != 1.0:
            self.bridge.cmd("setUnit", {"unit": info["unit_mm"]})
        self._current_file = None
        self._dirty = False
        self._sl.setText(f"项目: {info['name']} | 模型: {model_name} | 通道: {info['channels']}")

    def _open_profile(self):
        if not self._confirm_discard(): return
        path, _ = QFileDialog.getOpenFileName(
            self, "打开项目", "",
            "3D Layout Package (*.3dlp);;JSON (*.json);;All (*.*)"
        )
        if not path: return
        try:
            if path.endswith('.3dlp'):
                self._open_package(path)
            else:
                self._open_legacy_json(path)
            self._current_file = path
            self._dirty = False
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))

    def _open_package(self, path):
        with zipfile.ZipFile(path, 'r') as zf:
            project_data = json.loads(zf.read("project.json").decode("utf-8"))
            model_name = project_data.get("model_file", "model.stl")
            if model_name in zf.namelist():
                raw = zf.read(model_name)
            else:
                raise FileNotFoundError(f"模型文件 {model_name} 在包中未找到")
        self._model_name = model_name
        self._model_format = Path(model_name).suffix.lstrip('.').lower()
        self._model_b64 = None
        self._project_info = {
            "name": project_data.get("project_name", ""),
            "created_at": project_data.get("created_at", ""),
            "unit_mm": project_data.get("unit_mm", 1.0),
            "channels": project_data.get("total_points", 200),
        }
        cells = project_data.get("cells", [])
        total = project_data.get("total_points", len(cells))

        # 写入HTTP缓存目录
        cache_dir = os.path.join(find_root(), "src", "_model_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, model_name)
        Path(cache_path).write_bytes(raw)
        self._model_cache_path = cache_path

        self.bridge.cmd("loadStl", {
            "url": f"/src/_model_cache/{model_name}",
            "name": model_name,
            "cells": cells,
            "total_points": total,
            "format": self._model_format
        })
        if self._project_info.get("unit_mm", 1.0) != 1.0:
            self.bridge.cmd("setUnit", {"unit": self._project_info["unit_mm"]})
        self._sl.setText(
            f"已打开: {Path(path).name} | "
            f"项目: {self._project_info.get('name','')} | "
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
            "channels": data.get("total_points", 200),
        }
        total = data.get("total_points", len(cells))

        # 写入HTTP缓存目录
        cache_dir = os.path.join(find_root(), "src", "_model_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, model_name)

        if model_b64:
            Path(cache_path).write_bytes(base64.b64decode(model_b64))
            self._model_cache_path = cache_path
            self.bridge.cmd("loadStl", {
                "url": f"/src/_model_cache/{model_name}",
                "name": model_name,
                "cells": cells,
                "total_points": total,
                "format": self._model_format
            })
            self._sl.setText(f"已打开: {Path(path).name} (v{version}) [模型:{model_name}]")
        else:
            self.bridge.cmd("loadJsonCells", cells)
            self._sl.setText(f"已打开: {Path(path).name} (v{version}) [无3D模型]")

    def _save_direct(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存项目", "project.3dlp",
            "3D Layout Package (*.3dlp);;JSON (*.json)"
        )
        if not path: return
        if not (path.endswith('.3dlp') or path.endswith('.json')):
            path += '.3dlp'
        self._pending_save_path = path
        self.bridge.cmd("exportCells")

    def _save_as(self):
        self._save_direct()

    def _on_menu_action(self, action):
        if action == 'new': self._new_project()
        elif action == 'open': self._open_profile()
        elif action == 'save': self._save_direct()
        elif action == 'saveAs': self._save_as()

    def _screenshot(self):
        """导出当前3D视图为PNG截图"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出截图", "screenshot.png", "PNG (*.png)"
        )
        if not path:
            return
        # 让JS生成截图dataURL并通过Bridge发回
        self.bridge.cmd("screenshot", {"path": path})

    def _confirm_discard(self):
        if self._dirty:
            r = QMessageBox.question(self,"未保存更改","保存？",
                QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Save: self._save_direct(); return True
            elif r == QMessageBox.StandardButton.Discard: return True
            return False
        return True

    def closeEvent(self, event):
        if self._confirm_discard(): event.accept()
        else: event.ignore()


def main():
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--no-sandbox --ignore-gpu-blocklist --enable-webgl'
    app = QApplication(sys.argv); win = MainWindow(); win.show(); return app.exec()

if __name__ == "__main__":
    sys.exit(main())
