import sys
import os
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings

# =====================================================================
# 1. DIAGNOSTIC PAGE (Intercepts hidden browser errors)
# =====================================================================
class DiagnosticPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        # This will print any internal browser/Plotly crashes directly to your Python terminal!
        print(f"🖥️ [BROWSER CONSOLE] {message} (Line: {lineNumber})")

# =====================================================================
# 2. MAIN DIAGNOSTIC WINDOW
# =====================================================================
class WebEngineTester(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sarthak's WebEngine Diagnostic Tool")
        self.resize(800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # --- Top Buttons ---
        btn_layout = QHBoxLayout()
        
        btn_html = QPushButton("Test 1: Basic HTML")
        btn_html.clicked.connect(self.run_test_html)
        btn_layout.addWidget(btn_html)

        btn_js = QPushButton("Test 2: JavaScript")
        btn_js.clicked.connect(self.run_test_js)
        btn_layout.addWidget(btn_js)

        btn_webgl = QPushButton("Test 3: WebGL (Plotly 3D Core)")
        btn_webgl.clicked.connect(self.run_test_webgl)
        btn_layout.addWidget(btn_webgl)

        layout.addLayout(btn_layout)

        # --- WebEngine View ---
        self.web_view = QWebEngineView()
        
        # Attach our custom error-catching page
        self.diagnostic_page = DiagnosticPage()
        self.web_view.setPage(self.diagnostic_page)

        # Enable necessary features for Plotly
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        layout.addWidget(self.web_view)

        # Start with a neutral background
        self.web_view.setHtml("<body style='background-color: #f0f0f0;'><h2 style='text-align:center; margin-top: 20%; font-family: sans-serif;'>Ready for testing. Click a button above.</h2></body>")

    # =================================================================
    # 3. TEST PAYLOADS
    # =================================================================
    def run_test_html(self):
        print("\n--- Running Test 1: Basic HTML ---")
        html = """
        <body style="background-color: #e6f7ff; font-family: sans-serif; text-align: center; padding-top: 50px;">
            <h1 style="color: #005c99;">✅ Test 1 Passed!</h1>
            <p>The core Chromium web engine is successfully installed and rendering HTML.</p>
        </body>
        """
        self.web_view.setHtml(html)

    def run_test_js(self):
        print("\n--- Running Test 2: JavaScript ---")
        html = """
        <body style="background-color: #fff2e6; font-family: sans-serif; text-align: center; padding-top: 50px;">
            <h1 id="result" style="color: #cc5200;">Testing JavaScript...</h1>
            <script>
                console.log("JavaScript engine has started successfully.");
                document.getElementById('result').innerHTML = "✅ Test 2 Passed!<br><span style='font-size: 16px; color: black;'>JavaScript execution is allowed.</span>";
            </script>
        </body>
        """
        self.web_view.setHtml(html)

    def run_test_webgl(self):
        print("\n--- Running Test 3: WebGL ---")
        # Plotly 3D relies completely on WebGL. If this fails, Plotly will be a blank screen.
        html = """
        <body style="background-color: #e6ffe6; font-family: sans-serif; text-align: center; padding-top: 50px;">
            <h1 style="color: #006600;">Testing WebGL...</h1>
            <canvas id="glcanvas" width="400" height="200" style="border: 2px solid black;"></canvas>
            <p id="gl-result"></p>
            <script>
                const canvas = document.getElementById('glcanvas');
                const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                const resultText = document.getElementById('gl-result');
                
                if (!gl) {
                    console.error("FATAL: WebGL context creation failed. The GPU or driver rejected the request.");
                    resultText.innerHTML = "❌ <b>FAILED:</b> WebGL is not working. Plotly 3D will not render.";
                    resultText.style.color = "red";
                } else {
                    console.log("WebGL context acquired successfully!");
                    // Clear canvas to a nice blue color to prove it works
                    gl.clearColor(0.0, 0.5, 1.0, 1.0);
                    gl.clear(gl.COLOR_BUFFER_BIT);
                    resultText.innerHTML = "✅ <b>Test 3 Passed!</b><br>WebGL is working perfectly. The blue box above was drawn by your GPU.";
                }
            </script>
        </body>
        """
        self.web_view.setHtml(html)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WebEngineTester()
    window.show()
    sys.exit(app.exec())