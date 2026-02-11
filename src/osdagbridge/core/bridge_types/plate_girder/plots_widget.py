import sys
import os

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QRadioButton, QButtonGroup,
    QLabel, QComboBox, QCheckBox
)


import numpy as np
import plotly.graph_objects as go
import webbrowser

from analysis_results import PlateGirderAnalysisResults
from osdagbridge.core.bridge_types.plate_girder.analyser import BridgeGrillageModel

CURRENT_LOADCASE = None

# ============================================================
# MODEL + ANALYSIS (DATA FROM ANALYSER)
# ============================================================

model = BridgeGrillageModel()
model.create_model()

# ---------- ADD LOADS ----------
model.create_self_weight_load()
model.create_deck_load()
model.create_wearing_course_load()
model.create_footpath_load()
model.create_crash_barrier_load()
model.create_railing_load()
model.create_median_load()

# ---------- RUN ANALYSIS ----------
model.analyze()
# ---------- GET DATASET FROM ANALYSER ----------
ds = model.dataset
CURRENT_LOADCASE = ds.coords["Loadcase"].values[2]

# ================= LOADCASES =================
LOADCASES = list(ds.coords["Loadcase"].values)

# ================= FORCE MAP =================
FORCE_MAP = {
    "Fx": ("Vx_i", "Vx_j"),
    "Fy": ("Vy_i", "Vy_j"),
    "Fz": ("Vz_i", "Vz_j"),
    "Mx": ("Mx_i", "Mx_j"),
    "My": ("My_i", "My_j"),
    "Mz": ("Mz_i", "Mz_j"),
}

def get_ds(loadcase):
    return ds.sel(Loadcase=loadcase)


if __name__ == "__main__":
    print(type(ds))
    print(ds)

# ============================================================
# RESULT HANDLER + GIRDER BUILD
# ============================================================
res = PlateGirderAnalysisResults(
    dataset=ds,
    model=model
)

nodes, elements_all, adj = res.build_grillage_connectivity()

girder_map, elements = res.build_girders(verbose=False)

members = elements_all

# ============================================================
# EXTRACT FORCE DATA FROM analysis_results
# ============================================================

girder_force_data = {}

for g, data in girder_map.items():

    elems = data["elements"]

    girder_force_data[g] = {}

    for comp in ds.coords["Component"].values:

        results = res.get_beam_element_results(
            elems,
            CURRENT_LOADCASE,
            comp
        )

        # Convert array → float
        girder_force_data[g][comp] = {
            e: float(v) if v is not None else 0.0
            for e, v in results.items()
        }

# ============================================================
# FILTER GIRDER ELEMENTS (MATCH DATASET)
# ============================================================
dataset_elements = set(ds.coords["Element"].values)

for g, data in girder_map.items():

    valid_elems = [
        e for e in data["elements"]
        if e in dataset_elements
    ]

    girder_map[g]["elements"] = valid_elems


# print("Girders found →", girder_map.keys())


# ============================================================
# TEMP HTML
# ============================================================
TEMP_HTML = os.path.abspath("temp_plot.html")
import webbrowser

def open_plot():
    webbrowser.open("file://" + TEMP_HTML)
# ============================================================
# SFD (UNCHANGED)
def build_figure_sfd(loadcase, force_key):

    def find_component(name):
        for c in ds["Component"].values:
            if c.lower() == name.lower():
                return c
        return None

    Vy_i = find_component("Vy_i")
    Vy_j = find_component("Vy_j")
    Mz_i = find_component("Mz_i")
    Mz_j = find_component("Mz_j")
    # ----------------------------------------
    # FETCH FORCES FROM analysis_results CLASS
    # ----------------------------------------
    girder_force_data = {}

    for g, data in girder_map.items():

        elems = data["elements"]

        girder_force_data[g] = {}

        # list all components you need
        components = ["Vy_i", "Vy_j", "Mz_i", "Mz_j"]

        for comp in components:
            girder_force_data[g][comp] = res.get_beam_element_results(
                elems,
                CURRENT_LOADCASE,
                comp
            )



    # GIRDER GROUPING
    girders = {}

    for i, (key, g) in enumerate(girder_map.items(), start=1):
        girders[i] = g["elements"]
    '''
    colors = {
        1: "red",
        2: "orange",
        3: "green",
        4: "blue",
        5: "purple"
    }
    '''

    # BUILD GIRDER POLYLINES
    def build_polyline(elem_list, comp_i, comp_j, current_girder):
        xs, ys, zs, vals, node_ids = [], [], [], [], []

        for e in elem_list:
            n1, n2 = members[e]
            x1, y1, z1 = nodes[n1]

            xs.append(x1)
            ys.append(y1)
            zs.append(z1)
            vals.append(
                girder_force_data[current_girder]["Vy_i"][e] * 10
            )
            node_ids.append(n1)

        # Last end node
        last_e = elem_list[-1]
        n1, n2 = members[last_e]
        x2, y2, z2 = nodes[n2]

        xs.append(x2)
        ys.append(y2)
        zs.append(z2)
        vals.append(
            girder_force_data[current_girder]["Vy_j"][last_e] * 10
        )
        node_ids.append(n2)

        return np.array(xs), np.array(ys), np.array(zs), np.array(vals), node_ids

    # ===================== 3D STEPPED SFD =====================

    fig_sfd = go.Figure()

    # girder_spacing = 3.0

    for i, (gid, elems) in enumerate(girders.items()):

        xs, ys, zs, vy, node_ids = build_polyline(
            elems, Vy_i, Vy_j, f"g{gid}"
        )


        Vy = vy.astype(float)

        # use real Z from coordinates file
        z_base = np.mean(zs)  # or zs[0]

        shear_scale = 0.1 * abs((max(xs) - min(xs)) / (max(Vy) - min(Vy)))

        # ---------- BASELINE (GROUND) -------------
        fig_sfd.add_trace(go.Scatter3d(
            x=xs,
            y=[0] * len(xs),
            z=zs,  # [z_base] * len(xs),
            mode="lines",
            line=dict(color="green", width=3),
            hoverinfo="skip",
            showlegend=False
        ))

        # ---------- STEPPED SHEAR (MOUNTAINS) ----------
        x_step = np.repeat(xs, 2)[1:-1]
        Vy_step = np.repeat(Vy[:-1], 2)

        y_step = Vy_step * shear_scale
        z_step = [z_base] * len(y_step)

        fig_sfd.add_trace(go.Scatter3d(
            x=x_step,
            y=y_step,
            z=z_step,
            mode="lines",
            line=dict(color="blue", width=6),
            hoverinfo="text",
            text=[
                # f"Girder {gid}"
                f"<br>Node {nid}"
                f"<br>X = {x:.3f}"
                f"<br>Vy = {v:.3f}"
                for x, v, nid in zip(x_step, Vy_step, np.repeat(node_ids, 2)[1:-1])
            ],
            showlegend=False
        ))

        # ---------- VERTICAL WALLS (CLIFFS) ----------

        for xi, vyi in zip(xs, Vy):
            if xi == xs[-1]:
                fig_sfd.add_trace(go.Scatter3d(
                    x=[xi, xi],
                    y=[0, -vyi * shear_scale],
                    z=[z_base, z_base],
                    mode="lines",
                    line=dict(color="blue", width=4),
                    hoverinfo="skip",
                    showlegend=False

                ))
                # skip end nodes
            else:
                fig_sfd.add_trace(go.Scatter3d(
                    x=[xi, xi],
                    y=[0, vyi * shear_scale],
                    z=[z_base, z_base],
                    mode="lines",
                    line=dict(color="blue", width=4),
                    hoverinfo="skip",
                    showlegend=False

                ))
        # fig_bmd = go.Figure()
        # ------------ SUPPORT GEOMETRY -----------
        L = max(xs) - min(xs)
        h = 0.0199 * L  # support height
        w = 0.006 * L  # support half-width
        r = 0.0025 * L  # roller radius
        # ---------- PIN SUPPORT (START NODE) ----------
        x0, z0 = xs[0], zs[0]

        fig_sfd.add_trace(go.Scatter3d(
            x=[x0 - w, x0, x0 + w, x0 - w],
            y=[-h, 0, -h, -h],
            z=[z0, z0, z0, z0],
            mode="lines",
            line=dict(color="green", width=5),
            showlegend=False,
            hoverinfo="skip"
        ))
        # ===== PIN SUPPORT BASE (GROUND + HATCH) =====
        n_hatch = 6
        hatch_len = 0.15 * h

        # ground line
        fig_sfd.add_trace(go.Scatter3d(
            x=[x0 - 1.3 * w, x0 + 1.3 * w],
            y=[-h, -h],
            z=[z_base, z_base],
            mode="lines",
            line=dict(color="green", width=4),
            showlegend=False,
            hoverinfo="skip"
        ))

        # hatch lines
        xs_hatch = np.linspace(x0 - 1.2 * w, x0 + 1.2 * w, n_hatch)

        for xh in xs_hatch:
            fig_sfd.add_trace(go.Scatter3d(
                x=[xh - 0.04 * w, xh + 0.04 * w],
                y=[-h, -h - hatch_len],
                z=[z_base, z_base],
                mode="lines",
                line=dict(color="green", width=2),
                showlegend=False,
                hoverinfo="skip"
            ))

        # --------ROLLER SUPPORT(END NODE)--------------
        x1, z1 = xs[-1], zs[-1]

        # Triangle
        fig_sfd.add_trace(go.Scatter3d(
            x=[x1 - w, x1, x1 + w, x1 - w],
            y=[-h, 0, -h, -h],
            z=[z1, z1, z1, z1],
            mode="lines",
            line=dict(color="green", width=5),
            showlegend=False,
            hoverinfo="skip"
        ))
        Yb = -h  # base of triangle

        # Rollers (two wheels)
        theta = np.linspace(0, 2 * np.pi, 60)

        for dx in [-w / 2, w / 2]:
            fig_sfd.add_trace(go.Scatter3d(
                x=x1 + dx + r * np.cos(theta),
                y=(Yb - r) + r * np.sin(theta),  # tangent to triangle base
                z=[z1] * len(theta),
                mode="lines",
                line=dict(color="green", width=5),
                showlegend=False,
                hoverinfo="skip"
            ))
            # ===== ROLLER SUPPORT BASE (GROUND + HATCH) =====
        # ===== ROLLER SUPPORT BASE (TANGENT TO ROLLERS) =====
        n_hatch = 6
        hatch_len = 0.15 * h

        y_ground = Yb - 2 * r  # tangent to roller bottom

        # ground line
        fig_sfd.add_trace(go.Scatter3d(
            x=[x1 - 1.3 * w, x1 + 1.3 * w],
            y=[y_ground, y_ground],
            z=[z_base, z_base],
            mode="lines",
            line=dict(color="green", width=4),
            showlegend=False,
            hoverinfo="skip"
        ))

        # hatch lines
        xs_hatch = np.linspace(x1 - 1.2 * w, x1 + 1.2 * w, n_hatch)

        for xh in xs_hatch:
            fig_sfd.add_trace(go.Scatter3d(
                x=[xh - 0.04 * w, xh + 0.04 * w],
                y=[y_ground, y_ground - hatch_len],
                z=[z_base, z_base],
                mode="lines",
                line=dict(color="green", width=2),
                showlegend=False,
                hoverinfo="skip"
            ))

    fig_sfd.update_layout(
        title="3D Shear Force Diagram",
        scene=dict(

            xaxis=dict(
                showbackground=False, showticklabels=False, title="", showspikes=False
                #

            ),
            yaxis=dict(
                showbackground=False, showticklabels=False, title="", showspikes=False
                #
            ),
            zaxis=dict(
                showbackground=False, showticklabels=False, title="", showspikes=False, autorange="reversed"
                #

            ),

            aspectmode="data",
            camera=dict(
                eye=dict(x=1.6, y=1.2, z=1.6),
                up=dict(x=0, y=1, z=0)
            ),

        ),
        margin=dict(l=0, r=0, t=40, b=0)
    )
    fig_sfd.write_html(TEMP_HTML, include_plotlyjs=True, full_html=True)
    open_plot()



# ============================================================
#  BMD

def build_figure_bmd(loadcase, force_key):
    # LOAD INTERNAL FORCES (NETCDF)
    def find_component(name):
        for c in ds["Component"].values:
            if c.lower() == name.lower():
                return c
        return None

    Vy_i = find_component("Vy_i")
    Vy_j = find_component("Vy_j")
    Mz_i = find_component("Mz_i")
    Mz_j = find_component("Mz_j")


    # GIRDER GROUPING
    girders = {
        i + 1: data["elements"]
        for i, (g, data) in enumerate(girder_map.items())
    }

    # BUILD GIRDER POLYLINES
    def build_polyline(elem_list, comp_i, comp_j, current_girder):
        xs, ys, zs, vals, node_ids = [], [], [], [], []

        for e in elem_list:
            n1, n2 = members[e]
            x1, y1, z1 = nodes[n1]
            xs.append(x1)
            ys.append(y1)
            zs.append(z1)
            vals.append(
                girder_force_data[current_girder][comp_i][e]
            )
            node_ids.append(n1)

        # Last end node
        last_e = elem_list[-1]
        n1, n2 = members[last_e]
        x2, y2, z2 = nodes[n2]

        xs.append(x2)
        ys.append(y2)
        zs.append(z2)
        vals.append(
            girder_force_data[current_girder][comp_j][last_e]
        )
        node_ids.append(n2)

        return np.array(xs), np.array(ys), np.array(zs), np.array(vals), node_ids

    # PLOTLY 3D BMD INTERACTIVE
    fig_bmd = go.Figure()
    '''
    xfull=[]
    mzfull =[]
    for gid, elems in girders.items():
        xs, ys, zs, mz, node_ids = build_polyline(elems, Mz_i, Mz_j)
        xfull.extend(xs)
        mzfull.extend(mz)
    diffxfull = max(xfull)-min(xfull)
    diffmzfull = max(mzfull)-min(mzfull)
    #factormz= abs(diffmzfull/diffxfull)*0.2
    '''
    for gid, elems in girders.items():
        xs, ys, zs, mz, node_ids = build_polyline(
            elems, Mz_i, Mz_j, f"g{gid}"
        )
        if max(mz) - min(mz) == 0:
            factormz = 0.1 * abs((max(xs) - min(xs)) / (max(mz) - 0))
        else:
            factormz = 0.1 * abs((max(xs) - min(xs)) / (max(mz) - min(mz)))
        y_plot = mz * factormz  # * 0.05  # moment scale
        hover_text = [
            f"Node {nid}<br>X = {x:.3f}<br>Mz = {v:.3f}<br>Z = {z:.3f}"
            for nid, x, v, z in zip(node_ids, xs, mz, zs)
        ]

        fig_bmd.add_trace(go.Scatter3d(
            x=xs,
            y=y_plot,
            z=zs,
            mode='lines+markers',
            line=dict(color="red", width=4),
            marker=dict(size=3, color="red"),
            # name=f"Girder {gid}",
            showlegend=False,
            text=hover_text,
            hoverinfo="text"
        ))

        # baseline
        fig_bmd.add_trace(go.Scatter3d(
            x=[xs[0], xs[-1]],  # first and last node X
            y=[0, 0],  # Mz = 0 baseline
            z=[zs[0], zs[0]],  # same girder elevation
            mode='lines',
            line=dict(
                color="green",
                width=3,
                dash='solid'
            ),
            showlegend=False,
            hoverinfo='skip'
        ))

        fig_bmd.add_trace(go.Scatter3d(
            x=[xs[np.argmax(mz)], xs[np.argmax(mz)]],
            y=[0, max(mz) * factormz],
            z=[zs[0]] * 2,
            mode="lines",
            line=dict(color="black", width=3),
            legendgroup="max_lines",
            showlegend=False,
            visible=False,  # start OFF
            hoverinfo="skip"
        ))

        fig_bmd.add_trace(go.Scatter3d(
            x=[xs[np.argmin(mz)]] * 2,
            y=[0, min(mz) * factormz],
            z=[zs[0]] * 2,
            mode="lines",
            line=dict(color="black", width=3),
            legendgroup="min_lines",
            showlegend=False,
            visible=False,  # start OFF
            hoverinfo="skip"
        ))

        # ------------ SUPPORT GEOMETRY -----------
        L = max(xs) - min(xs)
        h = 0.0399 * L  # support height
        w = 0.015 * L  # support half-width
        r = 0.005 * L  # roller radius

        # ---------- PIN SUPPORT (START NODE) ----------
        x0, z0 = xs[0], zs[0]

        fig_bmd.add_trace(go.Scatter3d(
            x=[x0 - w, x0, x0 + w, x0 - w],
            y=[-h, 0, -h, -h],
            z=[z0, z0, z0, z0],
            mode="lines",
            line=dict(color="green", width=5),
            showlegend=False,
            hoverinfo="skip"
        ))
        n_hatch = 6
        hatch_len = 0.15 * h

        # ground line
        fig_bmd.add_trace(go.Scatter3d(
            x=[x0 - 1.3 * w, x0 + 1.3 * w],
            y=[-h, -h],
            z=[z0, z0],
            mode="lines",
            line=dict(color="green", width=4),
            showlegend=False,
            hoverinfo="skip"
        ))

        # hatch lines
        xs_hatch = np.linspace(x0 - 1.2 * w, x0 + 1.2 * w, n_hatch)

        for xh in xs_hatch:
            fig_bmd.add_trace(go.Scatter3d(
                x=[xh - 0.04 * w, xh + 0.04 * w],
                y=[-h, -h - hatch_len],
                z=[z0, z0],
                mode="lines",
                line=dict(color="green", width=2),
                showlegend=False,
                hoverinfo="skip"
            ))
        # --------ROLLER SUPPORT(END NODE)--------------
        x1, z1 = xs[-1], zs[-1]

        # Triangle
        fig_bmd.add_trace(go.Scatter3d(
            x=[x1 - w, x1, x1 + w, x1 - w],
            y=[-h, 0, -h, -h],
            z=[z1, z1, z1, z1],
            mode="lines",
            line=dict(color="green", width=5),
            showlegend=False,
            hoverinfo="skip"
        ))
        Yb = -h  # base of triangle

        # Rollers (two wheels)
        theta = np.linspace(0, 2 * np.pi, 60)

        for dx in [-w / 2, w / 2]:
            fig_bmd.add_trace(go.Scatter3d(
                x=x1 + dx + r * np.cos(theta),
                y=(Yb - r) + r * np.sin(theta),  # tangent to triangle base
                z=[z1] * len(theta),
                mode="lines",
                line=dict(color="green", width=5),
                showlegend=False,
                hoverinfo="skip"
            ))
        n_hatch = 6
        hatch_len = 0.15 * h

        y_ground = Yb - 2 * r  # tangent to roller bottom

        # ground line
        fig_bmd.add_trace(go.Scatter3d(
            x=[x1 - 1.3 * w, x1 + 1.3 * w],
            y=[y_ground, y_ground],
            z=[z1, z1],
            mode="lines",
            line=dict(color="green", width=4),
            showlegend=False,
            hoverinfo="skip"
        ))

        # hatch lines
        xs_hatch = np.linspace(x1 - 1.2 * w, x1 + 1.2 * w, n_hatch)

        for xh in xs_hatch:
            fig_bmd.add_trace(go.Scatter3d(
                x=[xh - 0.04 * w, xh + 0.04 * w],
                y=[y_ground, y_ground - hatch_len],
                z=[z1, z1],
                mode="lines",
                line=dict(color="green", width=2),
                showlegend=False,
                hoverinfo="skip"
            ))

    # pad = 0.01*(max(xfull) - min(xfull))
    # pad2 = 0.01*(max(mzfull) - min(mzfull))

    max_idx = [i for i, t in enumerate(fig_bmd.data) if t.legendgroup == "max_lines"]
    min_idx = [i for i, t in enumerate(fig_bmd.data) if t.legendgroup == "min_lines"]

    fig_bmd.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                x=0.5,
                y=1.15,
                showactive=True,
                active=-1,
                buttons=[
                    # -------- MAX TOGGLE --------
                    dict(
                        label="MAX",
                        method="update",

                        # OFF → ON
                        args=[{
                            "visible": [
                                True if t.legendgroup == "max_lines" else t.visible
                                for t in fig_bmd.data
                            ]
                        }],

                        # ON → OFF
                        args2=[{
                            "visible": [
                                False if t.legendgroup == "max_lines" else t.visible
                                for t in fig_bmd.data
                            ]
                        }]
                    ),

                    # -------- MIN TOGGLE --------
                    dict(
                        label="MIN",
                        method="update",

                        # OFF → ON
                        args=[{
                            "visible": [
                                True if t.legendgroup == "min_lines" else t.visible
                                for t in fig_bmd.data
                            ]
                        }],

                        # ON → OFF
                        args2=[{
                            "visible": [
                                False if t.legendgroup == "min_lines" else t.visible
                                for t in fig_bmd.data
                            ]
                        }]
                    ),
                ]
            )
        ],
        title="Interactive 3D BMD",

        scene=dict(

            camera=dict(
                # eye=dict(x=2.5, y=1, z=10),  #  pull camera along X
                up=dict(x=0, y=0.5, z=0),
                # center=dict(x=0, y=0, z=0),
                # projection=dict(type="orthographic")
            ),
            xaxis=dict(
                title="girder length",
                # range=[min(xfull) - pad, max(xfull) + pad],
                showbackground=False,  # removes YZ plane
                showgrid=False,
                zeroline=False,
                visible=False
            ),
            yaxis=dict(
                # range=[min(mzfull) - 0.25 * (max(mzfull) - min(mzfull)),max(mzfull) + 0.25 * (max(mzfull) - min(mzfull))],
                title="Mz values",
                # range = [min(mzfull)-pad2,max(mzfull)+pad2],
                showbackground=True,  #
                backgroundcolor="rgba(200,200,200,0.15)",
                showgrid=False,
                zeroline=False,
                visible=False  # showaxis line, keep plane
            ),
            zaxis=dict(
                showbackground=False,  # removes XY plane
                showgrid=False,
                zeroline=False,
                visible=False,
                autorange="reversed"
            ),
            aspectmode='data',

        ),

        # legend=dict(title="Girders")
    )

    fig_bmd.write_html(TEMP_HTML, include_plotlyjs=True, full_html=True)
    open_plot()



# ============================================================
# BMD CONTOUR
def build_figure_bmd_contour(loadcase, force_key):
    def find_component(name):
        for c in ds["Component"].values:
            if c.lower() == name.lower():
                return c
        return None

    Mz_i = find_component("Mz_i")
    Mz_j = find_component("Mz_j")

    def get_force(girder_key, elem, comp):
        return girder_force_data[girder_key][comp].get(elem, 0.0)

    girders = girder_map

    # -------------------------------------------------------------
    # BUILD GIRDER POLYLINE
    # -------------------------------------------------------------
    def build_polyline(girder_key, elem_list, comp_i, comp_j):
        xs, ys, zs, mz, node_ids = [], [], [], [], []

        for e in elem_list:
            n1, n2 = members[e]
            x1, y1, z1 = nodes[n1]

            xs.append(x1)
            ys.append(y1)
            zs.append(z1)
            mz.append(get_force(girder_key, e, comp_i))
            node_ids.append(n1)

        last_e = elem_list[-1]
        n1, n2 = members[last_e]
        x2, y2, z2 = nodes[n2]

        xs.append(x2)
        ys.append(y2)
        zs.append(z2)
        mz.append(get_force(girder_key, last_e, comp_j))
        node_ids.append(n2)

        return np.array(xs), np.array(ys), np.array(zs), np.array(mz), node_ids

    xfull, mzfull = [], []
    for girder_key, data in girders.items():
        elems = data["elements"]

        xs, ys, zs, mz, _ = build_polyline(
            girder_key, elems, Mz_i, Mz_j
        )

        xfull.extend(xs)
        mzfull.extend(mz)

    # moment_scale = 0.2 * abs(dx / dmz)   # visual-only scale

    # -------------------------------------------------------------
    # FIGURE
    # -------------------------------------------------------------
    fig = go.Figure()

    for gid, (girder_key, data) in enumerate(girders.items(), start=1):

        elems = data["elements"]

        xs, ys, zs, mz, node_ids = build_polyline(
            girder_key, elems, Mz_i, Mz_j
        )
        if max(mz) - min(mz) == 0:
            moment_scale = 0.1 * abs((max(xs) - min(xs)) / (max(mz) - 0))
        else:
            moment_scale = 0.1 * abs((max(xs) - min(xs)) / (max(mz) - min(mz)))
        y_plot = mz * moment_scale

        # -------- CONTOUR-STYLE BMD LINE --------
        fig.add_trace(go.Scatter3d(
            x=xs,
            y=y_plot,
            z=zs,
            mode="lines",
            line=dict(
                width=6,
                color=mz,  # color by Mz
                colorscale="Jet",
                cmin=min(mzfull),
                cmax=max(mzfull)
            ),
            showlegend=False,
            hoverinfo="text",
            text=[
                f"Node {nid}<br>X={x:.3f}<br>Mz={v:.3f}"
                for nid, x, v in zip(node_ids, xs, mz)
            ]
        ))

        # -------- BASELINE (Mz = 0) --------
        fig.add_trace(go.Scatter3d(
            x=[xs[0], xs[-1]],
            y=[0, 0],
            z=[zs[0], zs[0]],
            mode="lines",
            line=dict(color="green", width=3),
            hoverinfo="skip",
            showlegend=False
        ))

        # ---------- DROPLINES FROM BASELINE TO BMD ----------
        for xi, zi, mzi in zip(xs, zs, mz):
            fig.add_trace(go.Scatter3d(
                x=[xi, xi],
                y=[0, mzi * moment_scale],  # baseline → BMD
                z=[zi, zi],
                mode="lines",
                line=dict(
                    width=4,
                    color=[mzi, mzi],  # same color as contour
                    colorscale="Jet",
                    cmin=min(mzfull),
                    cmax=max(mzfull)
                ),
                showlegend=False,
                hoverinfo="skip"
            ))

        # ------------ SUPPORT GEOMETRY -----------
        L = max(xs) - min(xs)
        h = 0.0399 * L  # support height
        w = 0.015 * L  # support half-width
        r = 0.005 * L  # roller radius

        # ---------- PIN SUPPORT (FIRST NODE) ----------
        x0, z0 = xs[0], zs[0]

        fig.add_trace(go.Scatter3d(
            x=[x0 - w, x0, x0 + w, x0 - w],
            y=[-h, 0, -h, -h],
            z=[z0, z0, z0, z0],
            mode="lines",
            line=dict(color="green", width=5),
            showlegend=False,
            hoverinfo="skip"
        ))

        # ---------- ROLLER SUPPORT (LAST NODE) ----------
        x1, z1 = xs[-1], zs[-1]

        # Triangle
        fig.add_trace(go.Scatter3d(
            x=[x1 - w, x1, x1 + w, x1 - w],
            y=[-h, 0, -h, -h],
            z=[z1, z1, z1, z1],
            mode="lines",
            line=dict(color="green", width=5),
            showlegend=False,
            hoverinfo="skip"
        ))

        Yb = -h  # base of triangle
        theta = np.linspace(0, 2 * np.pi, 60)

        # Two rollers
        for dxr in [-w / 2, w / 2]:
            fig.add_trace(go.Scatter3d(
                x=x1 + dxr + r * np.cos(theta),
                y=(Yb - r) + r * np.sin(theta),
                z=[z1] * len(theta),
                mode="lines",
                line=dict(color="green", width=5),
                showlegend=False,
                hoverinfo="skip"
            ))
        n_hatch = 6
        hatch_len = 0.15 * h

        # ground line
        fig.add_trace(go.Scatter3d(
            x=[x0 - 1.3 * w, x0 + 1.3 * w],
            y=[-h, -h],
            z=[z0, z0],
            mode="lines",
            line=dict(color="green", width=4),
            showlegend=False,
            hoverinfo="skip"
        ))

        # hatch lines
        xs_hatch = np.linspace(x0 - 1.2 * w, x0 + 1.2 * w, n_hatch)

        for xh in xs_hatch:
            fig.add_trace(go.Scatter3d(
                x=[xh - 0.04 * w, xh + 0.04 * w],
                y=[-h, -h - hatch_len],
                z=[z0, z0],
                mode="lines",
                line=dict(color="green", width=2),
                showlegend=False,
                hoverinfo="skip"
            ))

        y_ground = Yb - 2 * r  # tangent to roller bottom

        # ground line
        fig.add_trace(go.Scatter3d(
            x=[x1 - 1.3 * w, x1 + 1.3 * w],
            y=[y_ground, y_ground],
            z=[z1, z1],
            mode="lines",
            line=dict(color="green", width=4),
            showlegend=False,
            hoverinfo="skip"
        ))

        # hatch lines
        xs_hatch = np.linspace(x1 - 1.2 * w, x1 + 1.2 * w, n_hatch)

        for xh in xs_hatch:
            fig.add_trace(go.Scatter3d(
                x=[xh - 0.04 * w, xh + 0.04 * w],
                y=[y_ground, y_ground - hatch_len],
                z=[z1, z1],
                mode="lines",
                line=dict(color="green", width=2),
                showlegend=False,
                hoverinfo="skip"
            ))

    # LAYOUT (POST-PROCESSOR STYLE)

    fig.update_layout(
        title="3D Bending Moment Diagram  Contour View",

        scene=dict(

            camera=dict(
                # eye=dict(x=2.5, y=0.15, z=10),  # 👈 pull camera along X
                up=dict(x=0, y=1, z=0),
                # center=dict(x=0, y=0, z=0),
                # projection=dict(type="orthographic")
            ),
            xaxis=dict(
                title="girder length",
                # range=[min(xfull) - pad, max(xfull) + pad],
                showbackground=False,  # removes YZ plane
                showgrid=False,
                zeroline=False,
                visible=False
            ),
            yaxis=dict(
                # range=[min(mzfull) - 0.25 * (max(mzfull) - min(mzfull)),max(mzfull) + 0.25 * (max(mzfull) - min(mzfull))],
                title="Mz values",
                # range = [min(mzfull)-pad2,max(mzfull)+pad2],
                showbackground=True,  #
                backgroundcolor="rgba(200,200,200,0.15)",
                showgrid=False,
                zeroline=False,
                visible=False  # showaxis line, keep plane
            ),
            zaxis=dict(
                showbackground=False,  # removes XY plane
                showgrid=False,
                zeroline=False,
                visible=False,
                autorange="reversed"
            ),
            aspectmode='data',

        ),
    )

    fig.write_html(TEMP_HTML, include_plotlyjs=True, full_html=True)
    open_plot()

# ============================================================
# ====================== QT WIDGET
# ============================================================
# ============================================================
# ====================== QT WIDGET
# ============================================================
class PlotWidget(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plate Girder Results")

        layout = QVBoxLayout(self)

        # ---------- TOP CONTROLS ----------
        top = QHBoxLayout()

        # Loadcase
        top.addWidget(QLabel("Loadcase:"))
        self.combo = QComboBox()
        self.combo.addItems(LOADCASES)
        self.combo.currentTextChanged.connect(self.update_plot)
        top.addWidget(self.combo)

        # Force
        top.addWidget(QLabel("Force:"))
        self.force_combo = QComboBox()
        self.force_combo.addItems(list(FORCE_MAP.keys()))
        self.force_combo.setCurrentText("Fy")
        self.force_combo.currentTextChanged.connect(self.update_plot)
        top.addWidget(self.force_combo)

        # Contour
        self.contour = QCheckBox("Contour (Moments only)")
        self.contour.stateChanged.connect(self.update_plot)
        top.addWidget(self.contour)

        top.addStretch()

        # ---------- WEB VIEW ----------


        layout.addLayout(top)


        self.update_plot()

    # ========================================================
    def update_plot(self):

        loadcase = self.combo.currentText()
        force_key = self.force_combo.currentText()

        global CURRENT_LOADCASE
        CURRENT_LOADCASE = loadcase

        # ----- Force vs Moment logic -----
        if force_key.startswith("F"):

            self.contour.setChecked(False)
            self.contour.setEnabled(False)

            build_figure_sfd(loadcase, force_key)

        else:

            self.contour.setEnabled(True)

            if self.contour.isChecked():
                build_figure_bmd_contour(loadcase, force_key)
            else:
                build_figure_bmd(loadcase, force_key)

# ============================================================
# ======================= MAIN
# ============================================================


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PlotWidget()
    w.resize(1200, 800)
    w.show()
    sys.exit(app.exec())

