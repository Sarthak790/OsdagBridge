import sys
import os
import json

# Performance Flags
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--ignore-gpu-blocklist "
    "--enable-gpu-rasterization "
    "--enable-webgl "
    "--enable-transparent-visuals "
    "--disable-software-rasterizer "
    "--disable-gpu-driver-bug-workarounds"
)

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QCheckBox, QTableWidget, QTableWidgetItem, 
    QHeaderView, QPushButton, QDialog
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtCore import QUrl, Qt, QPoint
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage

# --- IMPORT THE BACKEND LOGIC ---
from osdagbridge.core.bridge_types.plate_girder.plots_logic import (
    build_figure_sfd, 
    build_figure_bmd, 
    build_figure_bmd_contour, 
    get_ds, 
    LOADCASES, 
    FORCE_MAP, 
    TEMP_DIR
)
class BridgeWebPage(QWebEnginePage):
    """A custom web page that secretly listens to the JavaScript console."""
    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        # Use 'in' to ignore hidden newline characters or quotes
        if "TRIGGER_SUMMARY_DIALOG" in message:
            self.parent_widget.show_summary_dialog()
            
        super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)

class SummaryDialog(QDialog):
    """A floating tool palette that hovers over the main UI without disturbing it."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Extreme Values")
        
        # Qt.Tool makes it a neat floating palette. 
        # WindowStaysOnTopHint prevents it from hiding behind the main app.
        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)
        self.resize(350, 250)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Girder", "Max (N mm)", "Min (N mm)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

    def update_data(self, stats):
        self.table.setRowCount(len(stats))
        for row, (girder, vals) in enumerate(stats.items()):
            item_girder = QTableWidgetItem(girder)
            item_max = QTableWidgetItem(f"{vals['max']:.2f}")
            item_min = QTableWidgetItem(f"{vals['min']:.2f}")
            
            item_max.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item_min.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self.table.setItem(row, 0, item_girder)
            self.table.setItem(row, 1, item_max)
            self.table.setItem(row, 2, item_min)


class PlotWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plate Girder Results")
        layout = QVBoxLayout(self)
        top = QHBoxLayout()

        # ---------- LOADCASE ----------
        top.addWidget(QLabel("Load case:"))
        self.combo = QComboBox()
        self.combo.addItems(LOADCASES)
        self.combo.currentTextChanged.connect(self.update_plot)
        top.addWidget(self.combo)

        # ---------- FORCE ----------
        top.addWidget(QLabel("Force:"))
        self.force_combo = QComboBox()
        self.force_combo.addItems(list(FORCE_MAP.keys()))
        self.force_combo.setCurrentText("Fy")
        self.force_combo.currentTextChanged.connect(self.update_plot)
        top.addWidget(self.force_combo)

        # ---------- CONTOUR CHECKBOX ----------
        self.contour = QCheckBox("Contour (Moments only)")
        self.contour.stateChanged.connect(self.update_plot)
        top.addWidget(self.contour)
        
        # ---------- THE NEW DIALOG BUTTON ----------
        # self.btn_summary = QPushButton("Max/Min Values")
        # self.btn_summary.clicked.connect(self.show_summary_dialog)
        # top.addWidget(self.btn_summary)

        top.addStretch()
        layout.addLayout(top)

        # ---------- MAIN BROWSER AREA ----------
        self.web = QWebEngineView()
        self.custom_page = BridgeWebPage(self)
        self.web.setPage(self.custom_page)
        settings = self.web.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        layout.addWidget(self.web)

        # ---------- INITIALIZATION ----------
        self.stats_dict = {}  # Store the latest data here
        self.summary_dialog = SummaryDialog(self)

        base_html_path = str(TEMP_DIR / "base_plot.html")
        self.web.load(QUrl.fromLocalFile(base_html_path))
        self.web.loadFinished.connect(self.update_plot)

    def show_summary_dialog(self):
        """Pops up the dialog perfectly in the top-left corner of the web view."""
        if not self.stats_dict:
            return  
            
        self.summary_dialog.update_data(self.stats_dict)
        self.summary_dialog.show()
        
        # --- NEW: FORCE THE DIALOG TO THE FRONT ---
        self.summary_dialog.raise_()
        self.summary_dialog.activateWindow()
        # ------------------------------------------
        
        # Calculate exactly where the top-left of the 3D plot is on the screen
        top_left_corner = self.web.mapToGlobal(QPoint(15, 15))
        self.summary_dialog.move(top_left_corner)

    def update_plot(self):
        loadcase = self.combo.currentText()
        force_key = self.force_combo.currentText()
        ds = get_ds(loadcase)

        is_force = force_key.startswith("F") 
        is_moment = force_key.startswith("M") 

        if is_force:
            self.contour.blockSignals(True)
            self.contour.setChecked(False)
            self.contour.setEnabled(False)
            self.contour.blockSignals(False)
            
            # Disable the button for SFD since we aren't tracking stats for it yet
            # self.btn_summary.setEnabled(False) 
            self.stats_dict = {}
            
            plot_json = build_figure_sfd(ds, force_key)

        elif is_moment:
            self.contour.setEnabled(True)
            # self.btn_summary.setEnabled(True) # Re-enable the button
            
            if self.contour.isChecked():
                # Note: If you want stats for the contour plot too, you'll need to 
                # update the contour function to return the stats dict later!
                plot_json = build_figure_bmd_contour(ds, force_key)
                self.stats_dict = {}
            else:
                plot_json, self.stats_dict = build_figure_bmd(ds, force_key)
                
                # If the dialog is currently open, dynamically update the numbers
                if self.summary_dialog.isVisible():
                    self.summary_dialog.update_data(self.stats_dict)

        else:
            raise ValueError(f"Unsupported force: {force_key}")

        # -------- INJECT PLOT --------
        safe_json = json.dumps(plot_json) 
        js_command = f"updatePlotFromPython({safe_json});"
        self.web.page().runJavaScript(js_command)


# ======================= MAIN
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PlotWidget()
    w.resize(1200, 800)
    w.show()
    sys.exit(app.exec())