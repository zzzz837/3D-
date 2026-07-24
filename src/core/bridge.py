import json
import base64
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtWebEngineWidgets import QWebEnginePage


class Bridge(QObject):
    statusMsg = pyqtSignal(str)
    exportReady = pyqtSignal(str)
    menuAction = pyqtSignal(str)
    recordData = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wv = None
        self._total = 0
        self._loading = False
        self._dirty = False
        self._model_loaded = False

    def set_wv(self, wv):
        self._wv = wv

    def cmd(self, name, data=None):
        if self._wv:
            payload = json.dumps(data or {}, ensure_ascii=False)
            self._wv.page().runJavaScript(
                f'window.pyCommand("{name}",{payload})'
            )

    def handle(self, msg):
        try:
            o = json.loads(msg)
            e = o.get("e", "")
            d = o.get("d", {})
            if e == "ready":
                self.statusMsg.emit("引擎就绪 | 点击「新建」导入STL模型")
            elif e == "state":
                landed = d.get("landed", 0)
                total = d.get("max", landed + d.get("unlanded", 0))
                self._total = max(total, 1)
                ov = d.get("overlap", 0)
                self.statusMsg.emit(
                    f"已落地:{landed}/{self._total} | {'重叠:' + str(ov) if ov else '无重叠'}"
                )
                self._model_loaded = True
                if not self._loading:
                    self._dirty = True
            elif e == "exportCells":
                self.exportReady.emit(json.dumps(d))
            elif e == "screenshotData":
                path = d.get("path", "")
                b64 = d.get("data", "")
                if path and b64:
                    try:
                        Path(path).write_bytes(base64.b64decode(b64))
                        self.statusMsg.emit(f"截图已保存: {Path(path).name}")
                    except Exception as ex:
                        self.statusMsg.emit(f"截图失败: {ex}")
            elif e == "recordSave":
                self.recordData.emit(d.get("data", ""), d.get("size", 0))
            elif e == "error":
                QMessageBox.warning(None, "模型加载错误", d.get("msg", "未知错误"))
                self._loading = False
            elif e == "modelLoaded":
                rec = d.get("recommendedChannels", 0)
                self.statusMsg.emit(
                    f"模型加载完成 | 面:{d.get('faces', 0)} | 面积:{d.get('surfaceArea', '?')}mm²"
                    + (f" | 建议通道:{rec}" if rec else "")
                )
                self._loading = False
                self._dirty = False
                self._model_loaded = True
            elif e == "menuAction":
                self.menuAction.emit(d.get("action", ""))
        except Exception:
            pass

    @property
    def total_channels(self):
        return max(self._total, 1)


class BridgePage(QWebEnginePage):
    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self._bridge = bridge

    def javaScriptConsoleMessage(self, level, msg, line, src):
        try:
            text = str(msg)
            if text.startswith("BRIDGE:"):
                self._bridge.handle(text[7:])
            else:
                level_name = {0: "INFO", 1: "WARN", 2: "ERROR"}.get(level, "?")
                print(f"[JS {level_name}] L{line}: {text}", flush=True)
        except Exception:
            pass
