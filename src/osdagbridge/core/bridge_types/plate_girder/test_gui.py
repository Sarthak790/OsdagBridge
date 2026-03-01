import sys
import numpy as np
import plotly.graph_objects as go
import os

# Disable GPU acceleration to prevent black screens on certain Windows drivers
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QCheckBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings  # <-- Added for security settings
from PySide6.QtCore import QUrl                         # <-- Added for URL loading

# ============================================================
# TOY DATASET SETUP
# ============================================================
FORCE_MAP = {
    "Fy (Shear)": ("Vy_i", "Vy_j"),
    "Mz (Moment)": ("Mz_i", "Mz_j"),
}

LOADCASES = ["Toy Loadcase 1", "Toy Loadcase 2"]

# Mock Bridge Geometry (30m span, 3 girders)
nodes = {
    1: [0, 0, 0],   2: [10, 0, 0],  3: [20, 0, 0],  4: [30, 0, 0],    # Girder 1
    5: [0, 0, 5],   6: [10, 0, 5],  7: [20, 0, 5],  8: [30, 0, 5],    # Girder 2
    9: [0, 0, 10], 10: [10, 0, 10], 11: [20, 0, 10], 12: [30, 0, 10]  # Girder 3
}

members = {
    1: [1, 2], 2: [2, 3], 3: [3, 4],     # Girder 1 elements
    4: [5, 6], 5: [6, 7], 6: [7, 8],     # Girder 2 elements
    7: [9, 10], 8: [10, 11], 9: [11, 12] # Girder 3 elements
}

girders = {
    0.0: [1, 2, 3], 
    5.0: [4, 5, 6], 
    10.0: [7, 8, 9]
}

def get_mock_force(elem, comp, is_end_node=False):
    """Generates a fake force profile depending on the X coordinate."""
    n1, n2 = members[elem]
    nid = n2 if is_end_node else n1
    x = nodes[nid][0]

    if "V" in comp:
        return 50.0 - (100.0 * x / 30.0)
    elif "M" in comp:
        return 0.5 * x * (30.0 - x)
    return 0.0

# ============================================================
# PLOTTING FUNCTIONS
# ============================================================
def build_polyline(elem_list, comp_i, comp_j):
    xs, ys, zs, vals, node_ids = [], [], [], [], []
    for e in elem_list:
        n1, n2 = members[e]
        x1, y1, z1 = nodes[n1]
        xs.append(x1); ys.append(y1); zs.append(z1)
        vals.append(get_mock_force(e, comp_i, False))
        node_ids.append(n1)

    last_e = elem_list[-1]
    n1, n2 = members[last_e]
    x2, y2, z2 = nodes[n2]
    xs.append(x2); ys.append(y2); zs.append(z2)
    vals.append(get_mock_force(last_e, comp_j, True))
    node_ids.append(n2)

    return np.array(xs), np.array(ys), np.array(zs), np.array(vals), node_ids


def build_figure_sfd(force_key):
    comp_i, comp_j = FORCE_MAP[force_key]
    fig = go.Figure()

    for gid, elems in girders.items():
        xs, ys, zs, Vy, node_ids = build_polyline(elems, comp_i, comp_j)
        z_base = np.mean(zs)

        vy_range = max(Vy) - min(Vy)
        if vy_range == 0:
            shear_scale = 1.0 if max(Vy) == 0 else 0.1 * abs((max(xs) - min(xs)) / max(Vy))
        else:
            shear_scale = 0.1 * abs((max(xs) - min(xs)) / vy_range)

        # Baseline
        fig.add_trace(go.Scatter3d(x=xs, y=[0]*len(xs), z=zs, mode="lines", line=dict(color="green", width=3), hoverinfo="skip"))

        # Stepped Shear
        x_step = np.repeat(xs, 2)[1:-1]
        Vy_step = np.repeat(Vy[:-1], 2)
        fig.add_trace(go.Scatter3d(
            x=x_step, y=Vy_step * shear_scale, z=[z_base]*len(x_step),
            mode="lines", line=dict(color="blue", width=6),
            text=[f"Node {nid}<br>X={x:.1f}<br>V={v:.1f}" for x, v, nid in zip(x_step, Vy_step, np.repeat(node_ids, 2)[1:-1])],
            hoverinfo="text", showlegend=False
        ))

        # Vertical Walls
        for xi, vyi in zip(xs, Vy):
            y_end = -vyi * shear_scale if xi == xs[-1] else vyi * shear_scale
            fig.add_trace(go.Scatter3d(x=[xi, xi], y=[0, y_end], z=[z_base, z_base], mode="lines", line=dict(color="blue", width=4), hoverinfo="skip"))

    fig.update_layout(title="Toy Dataset: 3D Shear Force Diagram", scene=dict(aspectmode="auto"))
    
    # Use include_plotlyjs=True to embed the JS directly (bypasses network/CORS issues)
    return fig.to_html(include_plotlyjs=True, full_html=True)


def build_figure_bmd(force_key, use_contour=False):
    comp_i, comp_j = FORCE_MAP[force_key]
    fig = go.Figure()

    for gid, elems in girders.items():
        xs, ys, zs, mz, node_ids = build_polyline(elems, comp_i, comp_j)
        
        mz_range = max(mz) - min(mz)
        if mz_range == 0:
            factormz = 1.0 if max(mz) == 0 else 0.1 * abs((max(xs) - min(xs)) / max(mz))
        else:
            factormz = 0.1 * abs((max(xs) - min(xs)) / mz_range)
            
        y_plot = mz * factormz

        if use_contour:
            # Contour Style
            fig.add_trace(go.Scatter3d(
                x=xs, y=y_plot, z=zs, mode="lines",
                line=dict(width=6, color=mz, colorscale="Jet", cmin=-50, cmax=120),
                text=[f"X={x:.1f}<br>M={v:.1f}" for x, v in zip(xs, mz)],
                hoverinfo="text", showlegend=False
            ))
            for xi, zi, mzi in zip(xs, zs, mz):
                fig.add_trace(go.Scatter3d(x=[xi, xi], y=[0, mzi * factormz], z=[zi, zi], mode="lines", line=dict(width=2, color="gray"), hoverinfo="skip"))
        else:
            # Standard Line Style
            fig.add_trace(go.Scatter3d(
                x=xs, y=y_plot, z=zs, mode='lines+markers',
                line=dict(color="red", width=4), marker=dict(size=3, color="red"),
                text=[f"X={x:.1f}<br>M={v:.1f}" for x, v in zip(xs, mz)],
                hoverinfo="text", showlegend=False
            ))

        # Baseline
        fig.add_trace(go.Scatter3d(x=[xs[0], xs[-1]], y=[0, 0], z=[zs[0], zs[0]], mode='lines', line=dict(color="green", width=3), hoverinfo='skip'))

    title = "Toy Dataset: 3D BMD Contour View" if use_contour else "Toy Dataset: Interactive 3D BMD"
    fig.update_layout(title=title, scene=dict(aspectmode="auto"))
    
    # Use include_plotlyjs=True to embed the JS directly
    return fig.to_html(include_plotlyjs=True, full_html=True)

# ============================================================
# QT WIDGET
# ============================================================
class PlotWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Toy Plate Girder Results")
        layout = QVBoxLayout(self)
        top = QHBoxLayout()

        top.addWidget(QLabel("Load case:"))
        self.combo = QComboBox()
        self.combo.addItems(LOADCASES)
        self.combo.currentTextChanged.connect(self.update_plot)
        top.addWidget(self.combo)

        top.addWidget(QLabel("Force:"))
        self.force_combo = QComboBox()
        self.force_combo.addItems(list(FORCE_MAP.keys()))
        self.force_combo.setCurrentText("Fy (Shear)")
        self.force_combo.currentTextChanged.connect(self.update_plot)
        top.addWidget(self.force_combo)

        self.contour = QCheckBox("Contour (Moments only)")
        self.contour.stateChanged.connect(self.update_plot)
        top.addWidget(self.contour)
        top.addStretch()

        self.web = QWebEngineView()
        
        # --- FIX: LOWER SECURITY SHIELDS TO ALLOW PLOTLY RENDERING ---
        self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        
        layout.addLayout(top)
        layout.addWidget(self.web)

        # Temporary file path to pass to the WebEngine
        self.temp_file_path = os.path.abspath("temp_gui_plot.html")

        self.update_plot()

    def update_plot(self):
        force_key = self.force_combo.currentText()
        is_force = "Shear" in force_key
        is_moment = "Moment" in force_key

        html_string = ""

        if is_force:
            self.contour.blockSignals(True)
            self.contour.setChecked(False)
            self.contour.setEnabled(False)
            self.contour.blockSignals(False)
            
            html_string = build_figure_sfd(force_key)
            
        elif is_moment:
            self.contour.setEnabled(True)
            html_string = build_figure_bmd(force_key, use_contour=self.contour.isChecked())

        # WRITE HTML TO FILE AND LOAD IT VIA URL
        # if html_string:
        #     with open(self.temp_file_path, "w", encoding="utf-8") as f:
        #         f.write(html_string)
            
            # Use QUrl.fromLocalFile to safely pass the path to the internal browser
            # self.web.load(QUrl.fromLocalFile(self.temp_file_path))
        # Temporarily force a simple text render
        self.web.setHtml("<h1 style='color: white; background: red;'>HELLO SARTHAK! IF YOU SEE THIS, WEBENGINE WORKS.</h1>")
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PlotWidget()
    w.resize(1000, 700)
    w.show()
    sys.exit(app.exec())