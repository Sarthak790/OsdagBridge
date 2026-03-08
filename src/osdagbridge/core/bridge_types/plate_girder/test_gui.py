import sys
import numpy as np
import plotly.graph_objects as go
import os

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--ignore-gpu-blocklist"
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QCheckBox
)

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings



# ============================================================
# TOY DATASET
# ============================================================

FORCE_MAP = {
    "Fy (Shear)": ("Vy_i", "Vy_j"),
    "Mz (Moment)": ("Mz_i", "Mz_j"),
}

LOADCASES = ["Toy Loadcase 1", "Toy Loadcase 2"]

nodes = {
    1: [0, 0, 0],   2: [10, 0, 0],  3: [20, 0, 0],  4: [30, 0, 0],
    5: [0, 0, 5],   6: [10, 0, 5],  7: [20, 0, 5],  8: [30, 0, 5],
    9: [0, 0, 10], 10: [10, 0, 10], 11: [20, 0, 10], 12: [30, 0, 10]
}

members = {
    1: [1, 2], 2: [2, 3], 3: [3, 4],
    4: [5, 6], 5: [6, 7], 6: [7, 8],
    7: [9, 10], 8: [10, 11], 9: [11, 12]
}

girders = {
    0.0: [1, 2, 3],
    5.0: [4, 5, 6],
    10.0: [7, 8, 9]
}


# ============================================================
# MOCK FORCE FUNCTION
# ============================================================

def get_mock_force(elem, comp, is_end_node=False):

    n1, n2 = members[elem]
    nid = n2 if is_end_node else n1
    x = nodes[nid][0]

    if "V" in comp:
        return 50 - (100 * x / 30)

    if "M" in comp:
        return 0.5 * x * (30 - x)

    return 0


# ============================================================
# BUILD POLYLINE
# ============================================================

def build_polyline(elem_list, comp_i, comp_j):

    xs, ys, zs, vals, node_ids = [], [], [], [], []

    for e in elem_list:

        n1, n2 = members[e]
        x1, y1, z1 = nodes[n1]

        xs.append(x1)
        ys.append(y1)
        zs.append(z1)

        vals.append(get_mock_force(e, comp_i, False))
        node_ids.append(n1)

    last_e = elem_list[-1]
    n1, n2 = members[last_e]

    x2, y2, z2 = nodes[n2]

    xs.append(x2)
    ys.append(y2)
    zs.append(z2)

    vals.append(get_mock_force(last_e, comp_j, True))
    node_ids.append(n2)

    return np.array(xs), np.array(ys), np.array(zs), np.array(vals), node_ids


# ============================================================
# SFD
# ============================================================

def build_figure_sfd(force_key):

    comp_i, comp_j = FORCE_MAP[force_key]

    fig = go.Figure()

    for gid, elems in girders.items():

        xs, ys, zs, Vy, node_ids = build_polyline(elems, comp_i, comp_j)

        z_base = np.mean(zs)

        vy_range = max(Vy) - min(Vy)

        if vy_range == 0:
            shear_scale = 1
        else:
            shear_scale = 0.1 * abs((max(xs) - min(xs)) / vy_range)

        fig.add_trace(go.Scatter3d(
            x=xs,
            y=[0]*len(xs),
            z=zs,
            mode="lines",
            line=dict(color="green", width=3)
        ))

        x_step = np.repeat(xs, 2)[1:-1]
        Vy_step = np.repeat(Vy[:-1], 2)

        fig.add_trace(go.Scatter3d(
            x=x_step,
            y=Vy_step * shear_scale,
            z=[z_base]*len(x_step),
            mode="lines",
            line=dict(color="blue", width=6)
        ))

    fig.update_layout(
        title="3D Shear Force Diagram",
        scene=dict(aspectmode="auto")
    )

    return fig.to_html(include_plotlyjs='cdn', full_html=True)


# ============================================================
# BMD
# ============================================================

def build_figure_bmd(force_key, use_contour=False):

    comp_i, comp_j = FORCE_MAP[force_key]

    fig = go.Figure()

    for gid, elems in girders.items():

        xs, ys, zs, mz, node_ids = build_polyline(elems, comp_i, comp_j)

        mz_range = max(mz) - min(mz)

        if mz_range == 0:
            scale = 1
        else:
            scale = 0.1 * abs((max(xs) - min(xs)) / mz_range)

        y_plot = mz * scale

        fig.add_trace(go.Scatter3d(
            x=xs,
            y=y_plot,
            z=zs,
            mode="lines+markers",
            line=dict(color="red", width=4),
            marker=dict(size=3)
        ))

    fig.update_layout(
        title="3D Bending Moment Diagram",
        scene=dict(aspectmode="auto")
    )

    return fig.to_html(include_plotlyjs='cdn', full_html=True)


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

        settings = self.web.settings()

        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)

        layout.addLayout(top)
        layout.addWidget(self.web)

        self.update_plot()


    def update_plot(self):

        force_key = self.force_combo.currentText()

        if "Shear" in force_key:

            self.contour.setEnabled(False)
            html = build_figure_sfd(force_key)

        else:

            self.contour.setEnabled(True)
            html = build_figure_bmd(force_key, self.contour.isChecked())

        from PySide6.QtCore import QUrl
        self.web.setHtml(html, QUrl("http://localhost/"))


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    app = QApplication(sys.argv)

    w = PlotWidget()
    w.resize(1000,700)
    w.show()

    sys.exit(app.exec())