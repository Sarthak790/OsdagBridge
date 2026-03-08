import sys
import openseespy.opensees as ops
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QCheckBox
)

import numpy as np
import xarray as xr

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import mplcursors

from osdagbridge.core.bridge_types.plate_girder.analyser import BridgeGrillageModel


FORCE_MAP = {
    "Fx": ("Vx_i", "Vx_j"),
    "Fy": ("Vy_i", "Vy_j"),
    "Fz": ("Vz_i", "Vz_j"),
    "Mx": ("Mx_i", "Mx_j"),
    "My": ("My_i", "My_j"),
    "Mz": ("Mz_i", "Mz_j"),
}


# ============================================================
# RUN ANALYSIS
# ============================================================

bridge = BridgeGrillageModel()
bridge.create_model()
bridge.create_self_weight_load()
bridge.create_deck_load()
bridge.create_wearing_course_load()
bridge.create_footpath_load()
bridge.create_crash_barrier_load()
bridge.create_railing_load()
bridge.create_median_load()
bridge.analyze()

results = bridge.model.get_results()
ds_all = results


LOADCASES = [
    "girder self weight",
    "Deck slab load",
    "Wearing course self weight",
    "Footpath load",
    "Crash barrier load",
    "Railing load",
    "Median load",
]


def get_ds(loadcase):
    return ds_all.sel(Loadcase=loadcase)


# ============================================================
# GEOMETRY FROM OPENSEES
# ============================================================

nodes = {
    int(n): list(map(float, ops.nodeCoord(n)))
    for n in ops.getNodeTags()
}

members = {
    int(e): list(map(int, ops.eleNodes(e)))
    for e in ops.getEleTags()
}


# ============================================================
# GIRDER GROUPING
# ============================================================

def get_girders():

    from collections import defaultdict

    Z_TOL = 3
    node_z = {}

    for n in ops.getNodeTags():
        z = float(ops.nodeCoord(n)[2])
        node_z[int(n)] = round(z, Z_TOL)

    girders = defaultdict(list)

    for ele in ops.getEleTags():
        n1, n2 = map(int, ops.eleNodes(ele))

        if node_z[n1] == node_z[n2]:
            girders[node_z[n1]].append(int(ele))

    return girders


# ============================================================
# FORCE EXTRACTION
# ============================================================

def find_component(ds, name):

    for c in ds["Component"].values:
        if c.lower() == name.lower():
            return c

    return None


def get_force(ds, elem, comp):

    return float(ds["forces"].sel(Element=elem, Component=comp).values)


# ============================================================
# POLYLINE BUILDER
# ============================================================

def build_polyline(ds, elem_list, comp_i, comp_j):

    xs, ys, zs, vals, node_ids = [], [], [], [], []

    for e in elem_list:

        n1, n2 = members[e]
        x1, y1, z1 = nodes[n1]

        xs.append(x1)
        ys.append(y1)
        zs.append(z1)

        vals.append(get_force(ds, e, comp_i))
        node_ids.append(n1)

    last_e = elem_list[-1]
    n1, n2 = members[last_e]
    x2, y2, z2 = nodes[n2]

    xs.append(x2)
    ys.append(y2)
    zs.append(z2)

    vals.append(get_force(ds, last_e, comp_j))
    node_ids.append(n2)

    return np.array(xs), np.array(ys), np.array(zs), np.array(vals), node_ids


# ============================================================
# MATPLOTLIB CANVAS
# ============================================================

class BridgePlotCanvas(FigureCanvasQTAgg):

    def __init__(self):

        self.fig = Figure()
        self.ax = self.fig.add_subplot(111, projection="3d")

        super().__init__(self.fig)

        self.ax.grid(True, linestyle="--", alpha=0.3)

    def clear(self):

        self.ax.cla()
        self.ax.grid(True, linestyle="--", alpha=0.3)

    # --------------------------------------------------------

    def plot_sfd(self, ds, force_key):

        self.clear()

        comp_i_name, comp_j_name = FORCE_MAP[force_key]

        comp_i = find_component(ds, comp_i_name)
        comp_j = find_component(ds, comp_j_name)

        girders = get_girders()

        for gid, elems in girders.items():

            xs, ys, zs, Vy, node_ids = build_polyline(
                ds, elems, comp_i, comp_j
            )

            shear_scale = 0.1 * abs((max(xs) - min(xs)) /
                                    (max(Vy) - min(Vy) + 1e-9))

            y_plot = Vy * shear_scale

            # baseline
            self.ax.plot(xs, [0]*len(xs), zs,
                         color="green", linewidth=2)

            # shear diagram
            self.ax.plot(xs, y_plot, zs,
                         color="blue", linewidth=4)

        self.ax.set_title("3D Shear Force Diagram")

        self.draw()

    # --------------------------------------------------------

    def plot_bmd(self, ds, force_key):

        self.clear()

        comp_i_name, comp_j_name = FORCE_MAP[force_key]

        comp_i = find_component(ds, comp_i_name)
        comp_j = find_component(ds, comp_j_name)

        girders = get_girders()

        for gid, elems in girders.items():

            xs, ys, zs, mz, node_ids = build_polyline(
                ds, elems, comp_i, comp_j
            )

            scale = 0.1 * abs((max(xs) - min(xs)) /
                              (max(mz) - min(mz) + 1e-9))

            y_plot = mz * scale

            self.ax.plot(xs, y_plot, zs,
                         color="red",
                         linewidth=4,
                         marker="o",
                         markersize=3)

            self.ax.plot(xs, [0]*len(xs), zs,
                         color="green",
                         linewidth=2)

        self.ax.set_title("3D Bending Moment Diagram")

        self.draw()


# ============================================================
# QT WIDGET
# ============================================================

class PlotWidget(QWidget):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("Plate Girder Results")

        layout = QVBoxLayout(self)

        top = QHBoxLayout()

        # LOADCASE
        top.addWidget(QLabel("Load case:"))

        self.combo = QComboBox()
        self.combo.addItems(LOADCASES)
        self.combo.currentTextChanged.connect(self.update_plot)

        top.addWidget(self.combo)

        # FORCE
        top.addWidget(QLabel("Force:"))

        self.force_combo = QComboBox()
        self.force_combo.addItems(list(FORCE_MAP.keys()))
        self.force_combo.setCurrentText("Fy")
        self.force_combo.currentTextChanged.connect(self.update_plot)

        top.addWidget(self.force_combo)

        # CONTOUR
        self.contour = QCheckBox("Contour (Moments only)")
        self.contour.stateChanged.connect(self.update_plot)

        top.addWidget(self.contour)

        top.addStretch()

        layout.addLayout(top)

        # PLOT
        self.canvas = BridgePlotCanvas()

        layout.addWidget(self.canvas)

        self.update_plot()

    # --------------------------------------------------------

    def update_plot(self):

        loadcase = self.combo.currentText()
        force_key = self.force_combo.currentText()

        ds = get_ds(loadcase)

        if force_key.startswith("F"):

            self.contour.setEnabled(False)
            self.canvas.plot_sfd(ds, force_key)

        else:

            self.contour.setEnabled(True)
            self.canvas.plot_bmd(ds, force_key)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    app = QApplication(sys.argv)

    w = PlotWidget()
    w.resize(1200, 800)
    w.show()

    sys.exit(app.exec())