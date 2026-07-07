"""Minimal QWebEngineView test — check if any HTML can load."""
import sys, os
os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-gpu-sandbox --no-sandbox'
os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = '1'

from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtCore import QUrl, QTimer

app = QApplication(sys.argv)

# Use explicit data path
profile = QWebEngineProfile.defaultProfile()
profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)

wv = QWebEngineView()
wv.setMinimumSize(400, 300)

done = False
def on_finish(ok):
    global done
    done = True
    print(f'Load finished: ok={ok}', flush=True)
    app.quit()

wv.loadFinished.connect(on_finish)

# Try minimal HTML
wv.setHtml('<html><body><h1>Hello World</h1><p>If you see this, QWebEngine works.</p></body></html>')

wv.show()
print('Window shown...', flush=True)
QTimer.singleShot(10000, lambda: (print('Timeout', flush=True), app.quit()))
app.exec()
if not done:
    print('Did not receive loadFinished signal', flush=True)
