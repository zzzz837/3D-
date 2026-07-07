"""Test: load HTML via setHtml with <base> tag for ES module resolution."""
import sys, os
sys.path.insert(0, 'src')

from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, QTimer
import threading, http.server, socket
import urllib.parse as up

# Start HTTP server at project root
project_root = os.path.abspath('.')
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=project_root, **kw)
    def log_message(self, *a): pass

server = http.server.HTTPServer(('127.0.0.1', port), Handler)
t = threading.Thread(target=server.serve_forever, daemon=True)
t.start()

app = QApplication(sys.argv)

# Debug QWebEngine
os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-gpu-sandbox --no-sandbox'
os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = '1'
print(f"QtWebEngineProcess path: {os.environ.get('QTWEBENGINEPROCESS_PATH', 'not set')}", flush=True)
print(f"QT_PLUGIN_PATH: {os.environ.get('QT_PLUGIN_PATH', 'not set')}", flush=True)
wv = QWebEngineView()

# Read HTML and insert <base> tag for module resolution
html_path = os.path.join(project_root, 'src', '3D编辑器原型.html')
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

base_url = f'http://127.0.0.1:{port}/src/'
html = html.replace('<head>', f'<head><base href="{base_url}">')

done = False
def on_finish(ok):
    global done
    done = True
    print(f'Load finished: ok={ok}', flush=True)
    if ok:
        print('SUCCESS: HTML loaded with setHtml()', flush=True)
    else:
        print('FAILED: setHtml() + <base> approach also failed', flush=True)
    app.quit()

wv.loadFinished.connect(on_finish)
wv.setHtml(html, QUrl(f'http://127.0.0.1:{port}/'))
wv.resize(800, 600)
wv.show()
print('Window shown, waiting for load...', flush=True)

QTimer.singleShot(15000, lambda: (print('Timeout!', flush=True), app.quit()))
app.exec()
server.shutdown()
