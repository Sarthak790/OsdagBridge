import sys
import os
import ctypes

# =====================================================================
# THE C++ RAM-PINNING HACK
# =====================================================================
# 1. Locate the folder where PySide6 is installed
pyside_dir = os.path.join(sys.prefix, 'Lib', 'site-packages', 'PySide6')

# 2. Force Windows to prioritize this directory for DLL searches
if hasattr(os, 'add_dll_directory'):
    os.add_dll_directory(pyside_dir)

# 3. RAM-PINNING: Force Windows to load the correct DLLs
try:
    ctypes.CDLL(os.path.join(pyside_dir, "Qt6Core.dll"))
    ctypes.CDLL(os.path.join(pyside_dir, "Qt6Gui.dll"))
    ctypes.CDLL(os.path.join(pyside_dir, "Qt6Widgets.dll"))
    print("DLLs successfully pinned to RAM!")
except Exception as e:
    print(f"Pinning warning: {e}")

# =====================================================================
# NOW SAFELY IMPORT PYSIDE6
# =====================================================================
from PySide6.QtWidgets import QApplication, QMainWindow, QTextBrowser

app = QApplication(sys.argv)

window = QMainWindow()
window.setWindowTitle("PySide6 Widget Test")
window.resize(600, 400)

# QTextBrowser can render basic HTML inside the widget
browser = QTextBrowser()

html = """
<body style="background-color:#1e1e1e; color:#00ff00;
             font-family:monospace; text-align:center; padding-top:100px;">
    <h1>SUCCESS!</h1>
    <p>The PySide6 widget is rendering HTML without an external browser.</p>
</body>
"""

browser.setHtml(html)

window.setCentralWidget(browser)
window.show()

sys.exit(app.exec())