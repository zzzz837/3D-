"""
3D拟物Layout编辑器 v1.0
PySide6 + QWebEngineView + Three.js (本地HTTP服务器)
"""
import sys, os, json, base64
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QUrl, QObject, Signal, QSettings
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QFrame, QMessageBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage

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
    statusMsg = Signal(str)
    exportReady = Signal(str)
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
                # 隐藏独立模式的按钮
                self._wv.page().runJavaScript(
                    "try{D('tbLoadStl')&&(D('tbLoadStl').style.display='none');D('tbSaveFile')&&(D('tbSaveFile').style.display='none');D('tbOpenFile')&&(D('tbOpenFile').style.display='none');}catch(e){}"
                )
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
            elif "rror" in text:
                print(f"[JS Console] L{line}: {text}", flush=True)
        except Exception: pass


def find_root():
    if getattr(sys, 'frozen', False):
        d = Path(sys.executable).parent; i = d / "_internal"
        return str(i if i.is_dir() else d)
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

        self.bridge = Bridge()
        self.bridge.exportReady.connect(self._on_export)
        self.bridge.statusMsg.connect(lambda m: self._sl.setText(m))

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
            (None,None), ("撤销", lambda: self.bridge.cmd("undo")),
            ("重做", lambda: self.bridge.cmd("redo")), (None,None),
            ("3D预览", lambda: self.bridge.cmd("togglePreview")),
            ("截图PNG", self._screenshot),
            ("放置", lambda: self.bridge.cmd("togglePlace")),
            ("线框", lambda: self.bridge.cmd("wire")),
            ("重置", lambda: self.bridge.cmd("reset")),
        ]:
            if label is None: hl.addSpacing(8); continue
            btn = QPushButton(label); btn.setStyleSheet(BTN); btn.setFixedHeight(26)
            btn.clicked.connect(cb); hl.addWidget(btn)
        hl.addStretch(); self.setMenuWidget(top)

    def _init_webview(self):
        self.webview = QWebEngineView()
        self.webview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        root = find_root()
        html_path = os.path.join(root, "3D编辑器原型.html")
        if not os.path.isfile(html_path):
            QMessageBox.critical(self, "错误", f"找不到:\n{html_path}"); return

        page = BridgePage(self.bridge, self.webview)
        self.webview.setPage(page); self.bridge.set_wv(self.webview)

        # HTTP服务器解决 ES 模块 file:// CORS
        port = start_server(root)
        enc = quote("3D编辑器原型.html")
        url = f"http://127.0.0.1:{port}/{enc}"
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
        """接收JS发来的cells数据，直接保存JSON"""
        data = json.loads(json_str)
        cells = data.get("cells", [])
        total = data.get("total_points", 0)
        path = getattr(self, '_pending_save_path', None)
        if not path:
            return
        # 直接构建JSON写入，不经过DeviceLayoutProfile3D
        cells_json = []
        for c in cells:
            cells_json.append({
                "id": c.get("id", 0),
                "center_3d": c.get("center_3d", {"x": c.get("x",0), "y": c.get("y",0), "z": c.get("z",0)}),
                "normal": c.get("normal", {"x": c.get("nx",0), "y": c.get("ny",0), "z": c.get("nz",1)}),
                "width_mm": c.get("width_mm", c.get("side", 10.0)),
                "height_mm": c.get("height_mm", c.get("side", 10.0)),
                "rotation_deg": c.get("rotation_deg", c.get("rot", 0.0)),
            })
        profile = {
            "version": "2.0",
            "device_model": "Glove",
            "display_name": "",
            "total_points": total or len(cells_json),
            "surface_model": {
                "format": getattr(self, '_model_format', 'stl'),
                "file_name": getattr(self, '_model_name', 'model.stl'),
                "data_base64": getattr(self, '_model_b64', ''),
            },
            "cells": cells_json,
        }
        try:
            Path(path).write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
            self._pending_save_path = None
            self._sl.setText(f"已保存: {Path(path).name} ({len(cells_json)}个Cell)")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _new_project(self):
        if not self._confirm_discard(): return
        path, _ = QFileDialog.getOpenFileName(self, "选择3D模型", "",
            "3D模型 (*.stl *.obj *.glb *.gltf);;STL (*.stl);;OBJ (*.obj);;GLB/GLTF (*.glb *.gltf);;All (*.*)")
        if path:
            b64 = base64.b64encode(Path(path).read_bytes()).decode()
            # 存储模型数据以便保存时嵌入JSON
            self._model_b64 = b64
            self._model_name = Path(path).name
            self._model_format = Path(path).suffix.lstrip('.').lower()
            self.bridge.cmd("loadStl", {"b64":b64,"name":Path(path).name})
            self._current_file = None; self._dirty = False
            self._sl.setText(f"已加载: {Path(path).name}")

    def _open_profile(self):
        if not self._confirm_discard(): return
        path, _ = QFileDialog.getOpenFileName(self, "打开配置文件", "", "JSON (*.json)")
        if not path: return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            version = data.get("version","2.0"); cells = data.get("cells",[])
            # 恢复3D模型
            sm = data.get("surface_model", {})
            model_b64 = sm.get("data_base64","")
            model_name = sm.get("file_name","model.stl")
            if model_b64:
                # 恢复模型数据存储
                self._model_b64 = model_b64
                self._model_name = model_name
                self._model_format = sm.get("format","stl")
                # 加载模型+Cell (传入cells和total_points)
                total = data.get("total_points", len(cells))
                self.bridge.cmd("loadStl", {"b64":model_b64,"name":model_name,"cells":cells,"total_points":total})
                self._sl.setText(f"已打开: {Path(path).name} (v{version}) [模型:{model_name}]")
            else:
                self.bridge.cmd("loadJsonCells", cells)
                self._sl.setText(f"已打开: {Path(path).name} (v{version}) [无3D模型]")
            self._current_file = path; self._dirty = False
        except Exception as e: QMessageBox.warning(self,"打开失败",str(e))

    def _save_direct(self):
        """保存: 直接弹出对话框"""
        path, _ = QFileDialog.getSaveFileName(
            self, "保存布局配置", "layout_profile.json", "JSON (*.json)"
        )
        if not path: return
        if not path.endswith('.json'): path += '.json'
        self._pending_save_path = path
        self.bridge.cmd("exportCells")

    def _save_as(self):
        """另存为: 同保存"""
        self._save_direct()

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
    if getattr(sys, 'frozen', False):
        r = find_root()
        os.environ["QML2_IMPORT_PATH"] = os.path.join(r, "qml_plugins")
        os.environ["QT_PLUGIN_PATH"] = os.path.join(r, "plugins")
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(r, "plugins", "platforms")
    app = QApplication(sys.argv); win = MainWindow(); win.show(); return app.exec()

if __name__ == "__main__":
    sys.exit(main())
