import sys
import os

# --- THE TWO MAGIC CONDA FIXES ---
# 1. Disable the Chromium Sandbox (Conda environments break it)
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
# 2. Force software rendering (bypasses Windows driver clashes)
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView

app = QApplication(sys.argv)

window = QMainWindow()
window.setWindowTitle("Conda WebEngine Sandbox Test")
window.resize(600, 400)

web_view = QWebEngineView()
window.setCentralWidget(web_view)

# Basic HTML Test
html = """
<body style="background-color: #2b2b2b; color: #00ff00; font-family: monospace; text-align: center; padding-top: 100px;">
    <h1>SUCCESS!</h1>
    <p>The WebEngine is alive and the sandbox crash is bypassed.</p>
</body>
"""

web_view.setHtml(html)

window.show()
sys.exit(app.exec())