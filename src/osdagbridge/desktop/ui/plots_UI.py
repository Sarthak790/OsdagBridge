import sys
import os

# Performance Flags
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--ignore-gpu-blocklist "
    "--enable-gpu-rasterization "
    "--enable-webgl "
    "--enable-transparent-visuals"
)

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QCheckBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl

# --- IMPORT THE BACKEND LOGIC ---
from osdagbridge.core.bridge_types.plate_girder.plots_logic import (
    build_figure_sfd, 
    build_figure_bmd, 
    build_figure_bmd_contour, 
    get_ds, 
    LOADCASES, 
    FORCE_MAP, 
    TEMP_HTML
)


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

        # ---------- CONTOUR ----------
        self.contour = QCheckBox("Contour (Moments only)")
        self.contour.stateChanged.connect(self.update_plot)
        top.addWidget(self.contour)

        top.addStretch()

        self.web = QWebEngineView()
        settings = self.web.settings()

        layout.addLayout(top)
        layout.addWidget(self.web)

        self.update_plot()

    def update_plot(self):
        loadcase = self.combo.currentText()
        force_key = self.force_combo.currentText()

        ds = get_ds(loadcase)

        # -------- FORCE TYPE --------
        is_force = force_key.startswith("F")  # Fx, Fy, Fz
        is_moment = force_key.startswith("M")  # Mx, My, Mz

        # -------- UI LOGIC --------
        if is_force:
            # Forces → SFD, contour disabled
            self.contour.blockSignals(True)
            self.contour.setChecked(False)
            self.contour.setEnabled(False)
            self.contour.blockSignals(False)
            build_figure_sfd(ds, force_key)

        elif is_moment:
            # Moments → BMD (+ optional contour)
            self.contour.setEnabled(True)

            if self.contour.isChecked():
                build_figure_bmd_contour(ds, force_key)
            else:
                build_figure_bmd(ds, force_key)
        else:
            raise ValueError(f"Unsupported force: {force_key}")

        # -------- UPDATE VIEW --------
        clean_path = os.path.abspath(TEMP_HTML)
        self.web.load(QUrl.fromLocalFile(clean_path))


# ======================= MAIN
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PlotWidget()
    w.resize(1200, 800)
    w.show()
    sys.exit(app.exec())