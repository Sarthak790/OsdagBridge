import sys
import numpy as np

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QCheckBox
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


# ============================================================
# TOY DATASET
# ============================================================

FORCE_MAP = {
    "Fy (Shear)": ("Vy_i", "Vy_j"),
    "Mz (Moment)": ("Mz_i", "Mz_j"),
}

LOADCASES = ["Toy Loadcase 1", "Toy Loadcase 2"]

nodes = {
    1: [0, 0, 0], 2: [10, 0, 0], 3: [20, 0, 0], 4: [30, 0, 0],
    5: [0, 0, 5], 6: [10, 0, 5], 7: [20, 0, 5], 8: [30, 0, 5],
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
# FORCE FUNCTION
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
# POLYLINE
# ============================================================

def build_polyline(elem_list, comp_i, comp_j):

    xs, ys, zs, vals = [], [], [], []

    for e in elem_list:
        n1, n2 = members[e]
        x1, y1, z1 = nodes[n1]

        xs.append(x1)
        ys.append(y1)
        zs.append(z1)

        vals.append(get_mock_force(e, comp_i))

    last_e = elem_list[-1]
    n1, n2 = members[last_e]
    x2, y2, z2 = nodes[n2]

    xs.append(x2)
    ys.append(y2)
    zs.append(z2)

    vals.append(get_mock_force(last_e, comp_j, True))

    return np.array(xs), np.array(ys), np.array(zs), np.array(vals)


# ============================================================
# MATPLOTLIB CANVAS
# ============================================================

class PlotCanvas(FigureCanvasQTAgg):

    def __init__(self):

        self.fig = Figure()
        self.ax = self.fig.add_subplot(111, projection='3d')

        super().__init__(self.fig)

    def plot_sfd(self, force_key):

        self.ax.clear()

        comp_i, comp_j = FORCE_MAP[force_key]

        for gid, elems in girders.items():

            xs, ys, zs, Vy = build_polyline(elems, comp_i, comp_j)

            vy_range = max(Vy) - min(Vy)

            if vy_range == 0:
                scale = 1
            else:
                scale = 0.1 * abs((max(xs) - min(xs)) / vy_range)

            y_plot = Vy * scale

            self.ax.plot(xs, y_plot, zs, color="blue", linewidth=3)
            self.ax.plot(xs, np.zeros_like(xs), zs, color="green", linewidth=2)

        self.ax.set_title("3D Shear Force Diagram")
        self.draw()

    def plot_bmd(self, force_key):

        self.ax.clear()

        comp_i, comp_j = FORCE_MAP[force_key]

        for gid, elems in girders.items():

            xs, ys, zs, mz = build_polyline(elems, comp_i, comp_j)

            mz_range = max(mz) - min(mz)

            if mz_range == 0:
                scale = 1
            else:
                scale = 0.1 * abs((max(xs) - min(xs)) / mz_range)

            y_plot = mz * scale

            self.ax.plot(xs, y_plot, zs, color="red", linewidth=3, marker="o")

        self.ax.set_title("3D Bending Moment Diagram")
        self.draw()


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
        self.force_combo.currentTextChanged.connect(self.update_plot)

        top.addWidget(self.force_combo)

        self.contour = QCheckBox("Contour (Moments only)")
        top.addWidget(self.contour)

        top.addStretch()

        layout.addLayout(top)

        self.canvas = PlotCanvas()
        layout.addWidget(self.canvas)

        self.update_plot()

    def update_plot(self):

        force_key = self.force_combo.currentText()

        if "Shear" in force_key:
            self.canvas.plot_sfd(force_key)

        else:
            self.canvas.plot_bmd(force_key)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    app = QApplication(sys.argv)

    w = PlotWidget()
    w.resize(1000, 700)
    w.show()

    sys.exit(app.exec())