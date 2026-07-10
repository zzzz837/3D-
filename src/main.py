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
                if not getattr(self, '_loading', False):
                    self._dirty = True
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
                QMessageBox.warning(None, "模型加载错误", d.get('msg','未知错误'))
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
        # 日志: 同时输出到终端和 src/log/ 文件
        import logging, datetime
        log_dir = os.path.join(find_root(), "src", "log")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, datetime.datetime.now().strftime("app_%Y%m%d_%H%M%S.log"))
        self._log_fp = open(log_file, 'w', encoding='utf-8')
        self._log_fp.write(f"=== 3D拟物Layout编辑器 v{VER} ===\n")
        self._log_fp.write(f"启动: {datetime.datetime.now().isoformat()}\n")
        self._log_fp.flush()
        _orig_print = print
        def _tee_print(*args, **kwargs):
            _orig_print(*args, **kwargs)
            try:
                msg = ' '.join(str(a) for a in args)
                if 'flush' in kwargs: del kwargs['flush']
                self._log_fp.write(msg + '\n')
                self._log_fp.flush()
            except: pass
        import builtins; builtins.print = _tee_print
        print(f"[log] 日志文件: {log_file}")
        self.setWindowTitle(f"{APP} v{VER}")
        self.resize(1440, 900); self.setMinimumSize(1024, 700)
        self.setStyleSheet("QMainWindow{background:#1e1e1e}")
        # 设置窗口图标
        icon_path = os.path.join(find_root(), "download.png")
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._profile = None; self._current_file = None; self._dirty = False
        self._loading = False
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
        # 使用JS端实际unitMM, 不再依赖初始化值
        unit_mm = data.get("unit_mm") or self._project_info.get("unit_mm", 1.0)
        self._project_info["unit_mm"] = unit_mm
        cells_json = []
        for c in cells:
            center = c.get("center_mm") or c.get("center_3d") or {"x": 0, "y": 0, "z": 0}
            cells_json.append({
                "id": c.get("id", 0),
                "center_mm": {"x": center.get("x", 0), "y": center.get("y", 0), "z": center.get("z", 0)},
                "normal": c.get("normal", {"x": 0, "y": 0, "z": 1}),
                "radius_mm": c.get("radius_mm", 10.0),
                "rotation_deg": c.get("rotation_deg", c.get("rot", 0.0)),
                "label": c.get("label", ""),
                "pressure": c.get("pressure", 0),
            })
        project = {
            "version": "2.1",
            "schema_version": 1,
            "coordinate_space": "model_local_mm",
            "project_name": self._project_info.get("name", ""),
            "created_at": self._project_info.get("created_at", datetime.now().isoformat()),
            "total_points": total or len(cells_json),
            "unit_mm": unit_mm,
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
            self._dirty = False
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
            fmt = project_copy.pop("surface_model", {}).get("format", "stl")
            project_copy["model_file"] = model_name
            project_copy["model_format"] = fmt
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
            print(f"[stp] === STP转换开始: {path} ===", flush=True)
            self._sl.setText("正在转换STEP格式...")
            try:
                import tempfile as _tmp
                tmp_out = os.path.join(_tmp.gettempdir(), f"_stp_convert_{os.getpid()}.stl")
                converter = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stp_converter.py")
                if getattr(sys, 'frozen', False):
                    converter = os.path.join(find_root(), "src", "stp_converter.py")
                print(f"[stp] converter={converter} exists={os.path.isfile(converter)}", flush=True)
                if not os.path.isfile(converter):
                    raise FileNotFoundError(f"找不到转换器: {converter}")
                print(f"[stp] input={path} tmp_out={tmp_out}", flush=True)

                converted = False
                # 尝试 in-process
                try:
                    _conv_dir = os.path.dirname(converter)
                    if _conv_dir not in sys.path:
                        sys.path.insert(0, _conv_dir)
                    from stp_converter import convert_step_to_stl
                    print(f"[stp] in-process convert started", flush=True)
                    convert_step_to_stl(path, tmp_out)
                    converted = True
                    print(f"[stp] in-process convert done", flush=True)
                except ImportError as e:
                    print(f"[stp] in-process ImportError: {e}, trying subprocess", flush=True)
                except Exception as e:
                    print(f"[stp] in-process failed: {type(e).__name__}: {e}, trying subprocess fallback", flush=True)

                if not converted:
                    python_exe = None
                    conda_prefix = os.environ.get('CONDA_PREFIX', '')
                    if conda_prefix:
                        candidate = os.path.join(conda_prefix, 'python.exe')
                        if os.path.isfile(candidate): python_exe = candidate
                    if not python_exe:
                        candidate = r'D:\Anaconda\envs\3d-editor\python.exe'
                        if os.path.isfile(candidate): python_exe = candidate
                    if not python_exe:
                        candidate = r'D:\Anaconda\python.exe'
                        if os.path.isfile(candidate): python_exe = candidate
                    if not python_exe:
                        raise RuntimeError("未找到可用的 Python 解释器 (需 pythonocc-core)")
                    print(f"[stp] subprocess python={python_exe}", flush=True)
                    result = subprocess.run([python_exe, converter, path, tmp_out],
                        capture_output=True, text=True, timeout=300)
                    print(f"[stp] returncode={result.returncode}", flush=True)
                    if result.stdout: print(f"[stp] stdout: {result.stdout[:500]}", flush=True)
                    if result.stderr: print(f"[stp] stderr: {result.stderr[:500]}", flush=True)
                    if result.returncode != 0:
                        raise RuntimeError(f"转换失败 (rc={result.returncode}): {result.stderr.strip() or result.stdout.strip() or '?'}")

                # 校验输出STL
                print(f"[stp] tmp_out exists={os.path.isfile(tmp_out)} size={os.path.getsize(tmp_out) if os.path.isfile(tmp_out) else 0}", flush=True)
                raw = Path(tmp_out).read_bytes()
                try: os.unlink(tmp_out)
                except: pass
                if not raw or len(raw) < 84:
                    raise RuntimeError(f"转换结果为空或无效STL (size={len(raw)})")
                face_count = int.from_bytes(raw[80:84], 'little')
                print(f"[stp] output STL: {len(raw)} bytes, {face_count} faces", flush=True)
                if face_count == 0:
                    raise RuntimeError("转换结果STL面数为0")
                fmt = 'stl'
                print(f"[stp] === STP转换成功: {face_count} faces, 进入loadStl流程 ===", flush=True)
            except FileNotFoundError as e:
                print(f"[stp] FATAL: {e}", flush=True)
                QMessageBox.warning(self, "STEP转换失败", str(e))
                return
            except Exception as e:
                import traceback; traceback.print_exc()
                print(f"[stp] FATAL: {type(e).__name__}: {e}", flush=True)
                QMessageBox.warning(self, "STEP转换失败", f"{type(e).__name__}: {str(e)[:500]}")
                return
        else:
            raw = Path(path).read_bytes()
            print(f"[stp] === 非STP直接加载: {path} ===", flush=True)
        model_name = Path(path).stem + ".stl" if fmt == 'stl' and path.endswith(('.stp', '.step')) else Path(path).name
        self._model_name = model_name
        self._model_format = fmt
        self._model_b64 = None
        self._project_info = info

        # L1: 大模型降采样 (trimesh decimation)
        cache_dir = os.path.join(find_root(), "src", "_model_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, model_name)
        decimated = False; original_faces = 0; actual_faces = 0
        if fmt == 'stl' and len(raw) > 84:
            original_faces = int.from_bytes(raw[80:84], 'little')
            if original_faces > 200000:
                self._sl.setText(f"正在优化大模型 ({original_faces}面)...")
                before_bytes = len(raw)
                target = 300000
                reduction = 1.0 - (target / original_faces)
                try:
                    import trimesh
                    mesh = trimesh.load(trimesh.util.wrap_as_stream(raw), file_type='stl')
                    if mesh.faces.shape[0] > 200000 and 0 < reduction < 1:
                        simplified = None; sim_ok = False
                        try:
                            simplified = mesh.simplify_quadric_decimation(reduction)
                            sim_ok = simplified is not None and simplified.faces.shape[0] > 0
                        except ImportError:
                            print(f"[decimate] 缺少 fast_simplification 模块, 无法降采样", flush=True)
                        except ValueError as ve:
                            print(f"[decimate] 参数错误 (reduction={reduction:.4f}): {ve}", flush=True)
                        except Exception as se:
                            print(f"[decimate] 降采样异常: {type(se).__name__}: {se}", flush=True)
                        if sim_ok:
                            actual_faces = simplified.faces.shape[0]
                            raw = simplified.export(file_type='stl')
                            if raw and len(raw) > 84 and actual_faces < original_faces:
                                decimated = True
                                after_bytes = len(raw)
                                msg = f"降采样成功: {original_faces}→{actual_faces}面 | {before_bytes}→{after_bytes}bytes"
                            else:
                                actual_faces = 0
                                msg = f"降采样STL导出无效, 使用原模型 ({original_faces}面)"
                        else:
                            msg = f"降采样未执行: 使用原模型 ({original_faces}面)"
                    else:
                        msg = f"跳过降采样 (reduction={reduction:.4f})"
                except Exception as e:
                    msg = f"降采样失败: {type(e).__name__}, 使用原模型 ({original_faces}面)"
                    print(f"[decimate] {msg}: {e}", flush=True)
                self._sl.setText(msg)
                print(f"[decimate] {msg}", flush=True)
        Path(cache_path).write_bytes(raw)
        self._model_cache_path = cache_path

        self._loading = True
        self.bridge.cmd("loadStl", {
            "url": f"/src/_model_cache/{quote(model_name)}",
            "name": model_name,
            "format": fmt,
            "total_points": info["channels"],
            "unit_mm": info.get("unit_mm", 1.0),
            "decimated": decimated,
            "original_faces": original_faces,
            "actual_faces": actual_faces,
        })
        QTimer.singleShot(3000, lambda: setattr(self, '_loading', False))
        QTimer.singleShot(3500, lambda: setattr(self, '_dirty', False))
        self._current_file = None
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
                self._loading = True
                self._open_package(path)
                QTimer.singleShot(3000, lambda: setattr(self, '_loading', False))
                QTimer.singleShot(3500, lambda: setattr(self, '_dirty', False))
            else:
                self._open_legacy_json(path)
            self._current_file = path
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))

    def _open_package(self, path):
        print(f"[open] reading {path}", flush=True)
        with zipfile.ZipFile(path, 'r') as zf:
            names = zf.namelist()
            print(f"[open] zip contents: {names}", flush=True)
            project_data = json.loads(zf.read("project.json").decode("utf-8"))
            model_name = project_data.get("model_file", "model.stl")
            print(f"[open] model_file={model_name} model_format={project_data.get('model_format','?')}", flush=True)
            if model_name in zf.namelist():
                raw = zf.read(model_name)
                print(f"[open] model raw size={len(raw)} bytes", flush=True)
            else:
                raise FileNotFoundError(f"模型文件 {model_name} 在包中未找到")
        self._model_name = model_name
        self._model_format = project_data.get("model_format") or Path(model_name).suffix.lstrip('.').lower()
        print(f"[open] resolved format={self._model_format}", flush=True)
        # 打开工程也进行降采样
        decimated = False; original_faces = 0; actual_faces = 0
        if self._model_format == 'stl' and len(raw) > 84:
            original_faces = int.from_bytes(raw[80:84], 'little')
            if original_faces > 200000:
                print(f"[open] 大模型 ({original_faces}面) 正在降采样...", flush=True)
                try:
                    import trimesh
                    mesh = trimesh.load(trimesh.util.wrap_as_stream(raw), file_type='stl')
                    if mesh.faces.shape[0] > 200000:
                        target = 300000; reduction = 1.0 - (target / mesh.faces.shape[0])
                        if 0 < reduction < 1:
                            try:
                                simplified = mesh.simplify_quadric_decimation(reduction)
                                if simplified and simplified.faces.shape[0] > 0:
                                    raw = simplified.export(file_type='stl')
                                    if len(raw) > 84:
                                        actual_faces = simplified.faces.shape[0]
                                        decimated = True
                                        print(f"[open] 降采样成功: {original_faces}→{actual_faces}面", flush=True)
                            except Exception as se:
                                print(f"[open] 降采样跳过: {se}", flush=True)
                except Exception as e:
                    print(f"[open] 降采样失败: {e}", flush=True)
        self._model_b64 = None
        self._project_info = {
            "name": project_data.get("project_name", ""),
            "created_at": project_data.get("created_at", ""),
            "unit_mm": project_data.get("unit_mm", 1.0),
            "channels": project_data.get("total_points", 200),
        }
        cells = project_data.get("cells", [])
        total = project_data.get("total_points", len(cells))
        # 保留原始字段, 不重写center_3d→center_mm
        coord_space = project_data.get("coordinate_space") or ""
        if not coord_space:
            # 历史工程: center_3d实际存储的是u2mm毫米值, 不是model_local_unit
            has_c3 = any("center_3d" in c for c in cells[:1]) if cells else False
            coord_space = "model_local_mm_legacy" if has_c3 else ""
        print(f"[open] cells={len(cells)} total_points={total} coord_space={coord_space} unit_mm={self._project_info['unit_mm']}", flush=True)

        cache_dir = os.path.join(find_root(), "src", "_model_cache")
        os.makedirs(cache_dir, exist_ok=True)
        # Q25: UUID缓存名避免旧缓存污染
        import uuid, time
        cache_name = f"opened_{uuid.uuid4().hex[:8]}_{model_name}"
        cache_path = os.path.join(cache_dir, cache_name)
        Path(cache_path).write_bytes(raw)
        self._model_cache_path = cache_path
        print(f"[open] cache_path={cache_path}", flush=True)

        actual_size = Path(cache_path).stat().st_size
        print(f"[open] cache_size={actual_size} (raw={len(raw)})", flush=True)
        if actual_size != len(raw):
            QMessageBox.warning(self, "文件错误", f"模型缓存写入不完整: {actual_size} vs {len(raw)}")
            return

        url = f"/src/_model_cache/{quote(cache_name)}?v={int(time.time()*1000)}"
        print(f"[open] loadStl URL={url} format={self._model_format} cells={len(cells)}", flush=True)
        self.bridge.cmd("loadStl", {
            "url": url,
            "name": model_name,
            "cells": cells,
            "total_points": total,
            "format": self._model_format,
            "unit_mm": self._project_info.get("unit_mm", 1.0),
            "schema_version": project_data.get("schema_version", 0),
            "coordinate_space": coord_space,
            "decimated": decimated,
            "original_faces": original_faces,
            "actual_faces": actual_faces,
        })
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
                "url": f"/src/_model_cache/{quote(model_name)}",
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
        if self._confirm_discard():
            if hasattr(self, '_log_fp'):
                try: self._log_fp.close()
                except: pass
            event.accept()
        else: event.ignore()


def main():
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--no-sandbox --ignore-gpu-blocklist --enable-webgl'
    app = QApplication(sys.argv); win = MainWindow(); win.show(); return app.exec()

if __name__ == "__main__":
    sys.exit(main())
