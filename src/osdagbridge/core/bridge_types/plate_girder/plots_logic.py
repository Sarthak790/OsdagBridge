import xarray as xr
import numpy as np
import plotly.graph_objects as go
from pathlib import Path
import openseespy.opensees as ops

from osdagbridge.core.bridge_types.plate_girder.analyser import BridgeGrillageModel
from osdagbridge.core.bridge_types.plate_girder.analysis_results import PlateGirderAnalysisResults

FORCE_MAP = {
    "Fx": ("Vx_i", "Vx_j"),
    "Fy": ("Vy_i", "Vy_j"),
    "Fz": ("Vz_i", "Vz_j"),
    "Mx": ("Mx_i", "Mx_j"),
    "My": ("My_i", "My_j"),
    "Mz": ("Mz_i", "Mz_j"),
}

# ============================================================
# MODEL GENERATION & RESULTS EXTRACTION
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

bridge.vehicle_lane_coordinates()
bridge.create_vehicle_load_cases()
bridge.add_vehicle_load_cases_from_combinations()
bridge.create_moving_vehicle_load_cases()

bridge.analyze()

results = bridge.model.get_results()

result_handler = PlateGirderAnalysisResults(dataset=results, model=bridge.model)
LOADCASES = [str(lc) for lc in result_handler.get_available_loadcases()]

ds_all = results


def get_ds(loadcase):
    return ds_all.sel(Loadcase=loadcase)

# ============================================================
# HTML FILE MANAGEMENT
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMP_DIR = BASE_DIR / "temp_files"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
TEMP_HTML = str(TEMP_DIR / "temp_plot.html")

# ============================================================
# BUILD GEOMETRY ONCE
# ============================================================
nodes = {
    int(n): list(map(float, ops.nodeCoord(n)))
    for n in ops.getNodeTags()
}

members = {
    int(e): list(map(int, ops.eleNodes(e)))
    for e in ops.getEleTags()
}

def add_grillage_background(fig, nodes_dict, members_dict):
    """
    Adds a distinct grey background mesh showing all longitudinal 
    and transverse elements in the grillage at the y=0 baseline.
    """
    x_grill, y_grill, z_grill = [], [], []
    
    for ele_tag, (n1, n2) in members_dict.items():
        x1, _, z1 = nodes_dict[n1]
        x2, _, z2 = nodes_dict[n2]
        
        # Add the line segment, then a None to break the line
        x_grill.extend([x1, x2, None])
        y_grill.extend([0, 0, None])  # Draw it flat at the baseline
        z_grill.extend([z1, z2, None])
        
    fig.add_trace(go.Scatter3d(
        x=x_grill, 
        y=y_grill, 
        z=z_grill,
        mode='lines',
        line=dict(color='darkgrey', width=2), 
        opacity=0.9, 
        hoverinfo='skip',
        showlegend=False
    ))

# ============================================================
# SFD
# ============================================================
def build_figure_sfd(ds, force_key):
    def find_component(name):
        for c in ds["Component"].values:
            if c.lower() == name.lower():
                return c
        return None

    comp_i_name, comp_j_name = FORCE_MAP[force_key]
    comp_i = find_component(comp_i_name)
    comp_j = find_component(comp_j_name)

    def get_force(elem, comp):
        return float(ds["forces"].sel(Element=elem, Component=comp).values)

    Z_TOL = 3  
    node_z = {}
    for n in ops.getNodeTags():
        z = float(ops.nodeCoord(n)[2])
        node_z[int(n)] = round(z, Z_TOL)
        
    from collections import defaultdict
    girders = defaultdict(list)

    for ele in ops.getEleTags():
        ele_id = int(ele)
        n1, n2 = map(int, ops.eleNodes(ele))
        z1 = node_z[n1]
        z2 = node_z[n2]
        if z1 == z2:
            girders[z1].append(int(ele))

    def build_polyline(elem_list, comp_i, comp_j):
        xs, ys, zs, vals, node_ids = [], [], [], [], []
        for e in elem_list:
            n1, n2 = members[e]
            x1, y1, z1 = nodes[n1]
            xs.append(x1)
            ys.append(y1)
            zs.append(z1)
            vals.append(round(get_force(e, comp_i), 3))
            node_ids.append(n1)

        last_e = elem_list[-1]
        n1, n2 = members[last_e]
        x2, y2, z2 = nodes[n2]
        xs.append(x2)
        ys.append(y2)
        zs.append(z2)
        vals.append(round(get_force(last_e, comp_j), 3))
        node_ids.append(n2)
        return np.array(xs), np.array(ys), np.array(zs), np.array(vals), node_ids

    fig_sfd = go.Figure()
    add_grillage_background(fig_sfd, nodes, members)

    # =========================================================
    # MASTER LISTS FOR REDUCING LINE DRAW CALLS
    # =========================================================
    master_base_x, master_base_y, master_base_z = [], [], []
    master_shear_x, master_shear_y, master_shear_z = [], [], []
    master_hover_text = []
    master_cliff_x, master_cliff_y, master_cliff_z = [], [], []
    master_label_x, master_label_y, master_label_z, master_label_text = [], [], [], []

    sorted_girders = sorted(girders.items(), key=lambda item: item[0])
    for i, (z_val, elems) in enumerate(sorted_girders):
        girder_name = f"G{i+1}"
        xs, ys, zs, vy, node_ids = build_polyline(elems, comp_i, comp_j)
        Vy = vy.astype(float)
        z_base = np.mean(zs) 

        if max(Vy) - min(Vy) == 0:
            shear_scale = 0.25 * abs((max(xs) - min(xs)) / (max(Vy) - 0))
        else:
            shear_scale = 0.25 * abs((max(xs) - min(xs)) / (max(Vy) - min(Vy)))

        x_step = np.repeat(xs, 2)[1:-1]
        Vy_step = np.repeat(Vy[:-1], 2)
        y_step = Vy_step * shear_scale
        z_step = [z_base] * len(y_step)

        # 1. ADD GO.SURFACE DIRECTLY (Preserving your exact look)
        fig_sfd.add_trace(go.Surface(
            x=[x_step, x_step], y=[np.zeros(len(y_step)), y_step], z=[z_step, z_step],
            surfacecolor=[[1]*len(y_step), [1]*len(y_step)], colorscale=[[0, 'blue'], [1, 'blue']],          
            opacity=0.2, showscale=False, hoverinfo="skip"
        ))

        # 2. Append to Master Baseline
        master_base_x.extend(list(xs) + [None])
        master_base_y.extend([0] * len(xs) + [None])
        master_base_z.extend(list(zs) + [None])

        # 3. Append to Master Stepped Shear Line
        master_shear_x.extend(list(x_step) + [None])
        master_shear_y.extend(list(y_step) + [None])
        master_shear_z.extend(list(z_step) + [None])

        hover_strings = [f"<br>Node {nid}<br>X = {x:.2f}<br>{force_key} = {v:.2f}"
                         for x, v, nid in zip(x_step, Vy_step, np.repeat(node_ids, 2)[1:-1])]
        master_hover_text.extend(hover_strings + [None])

        # 4. Append to Master Vertical Cliffs
        for xi, vyi in zip(xs, Vy):
            master_cliff_x.extend([xi, xi, None])
            master_cliff_z.extend([z_base, z_base, None])
            if xi == xs[-1]:
                master_cliff_y.extend([0, -vyi * shear_scale, None])
            else:
                master_cliff_y.extend([0, vyi * shear_scale, None])

        # 5. Append to Master Text Labels
        master_label_x.append(xs[0])
        master_label_y.append(0)
        master_label_z.append(zs[0])
        master_label_text.append(f"<b>{girder_name}</b>")

    # =========================================================
    # ADD MASTER TRACES (Hundreds of objects compressed into 4)
    # =========================================================

    # Add ALL baselines as a single object
    fig_sfd.add_trace(go.Scatter3d(
        x=master_base_x, y=master_base_y, z=master_base_z, mode="lines",
        line=dict(color="green", width=3), hoverinfo="skip", showlegend=False
    ))

    # Add ALL Stepped Shear lines as a single object
    fig_sfd.add_trace(go.Scatter3d(
        x=master_shear_x, y=master_shear_y, z=master_shear_z, mode="lines",
        line=dict(color="blue", width=6), hoverinfo="text", text=master_hover_text, showlegend=False
    ))

    # Add ALL vertical cliffs as a single object
    fig_sfd.add_trace(go.Scatter3d(
        x=master_cliff_x, y=master_cliff_y, z=master_cliff_z, mode="lines",
        line=dict(color="blue", width=4), hoverinfo="skip", showlegend=False
    ))

    # Add ALL labels as a single object
    fig_sfd.add_trace(go.Scatter3d( 
        x=master_label_x, y=master_label_y, z=master_label_z, mode="text", 
        text=master_label_text, textposition="middle left", textfont=dict(size=14, color="black"),
        showlegend=False, hoverinfo="skip"
    ))

    fig_sfd.update_layout(
        hoverlabel=dict(
            bgcolor="#E6F2FF", font_size=12, font_family="Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif", 
            font_color="#2C3E50", bordercolor="#BBD6EE", namelength=-1                
        ),
        scene=dict(
            xaxis=dict(showbackground=False, showticklabels=False, title="", showspikes=False),
            yaxis=dict(showbackground=False, showticklabels=False, title="", showspikes=False),
            zaxis=dict(showbackground=False, showticklabels=False, title="", showspikes=False, autorange="reversed"),
            aspectmode="data",
            camera=dict(eye=dict(x=1.6, y=1.2, z=1.6), up=dict(x=0, y=1, z=0)),
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        paper_bgcolor="white", plot_bgcolor="white"
    )
    fig_sfd.write_html(TEMP_HTML, include_plotlyjs=True, full_html=True)


# ============================================================
# BMD
# ============================================================
def build_figure_bmd(ds, force_key):
    def find_component(name):
        for c in ds["Component"].values:
            if c.lower() == name.lower():
                return c
        return None

    comp_i_name, comp_j_name = FORCE_MAP[force_key]
    comp_i = find_component(comp_i_name)
    comp_j = find_component(comp_j_name)

    def get_force(elem, comp):
        return float(ds["forces"].sel(Element=elem, Component=comp).values)

    Z_TOL = 3 
    node_z = {}
    for n in ops.getNodeTags():
        z = float(ops.nodeCoord(n)[2])
        node_z[int(n)] = round(z, Z_TOL)
        
    from collections import defaultdict
    girders = defaultdict(list)

    for ele in ops.getEleTags():
        ele_id = int(ele)
        n1, n2 = map(int, ops.eleNodes(ele))
        z1 = node_z[n1]
        z2 = node_z[n2]
        if z1 == z2:
            girders[z1].append(int(ele))

    def build_polyline(elem_list, comp_i, comp_j):
        xs, ys, zs, vals, node_ids = [], [], [], [], []
        for e in elem_list:
            n1, n2 = members[e]
            x1, y1, z1 = nodes[n1]
            xs.append(x1)
            ys.append(y1)
            zs.append(z1)
            vals.append(round(get_force(e, comp_i), 3))
            node_ids.append(n1)
            
        last_e = elem_list[-1]
        n1, n2 = members[last_e]
        x2, y2, z2 = nodes[n2]
        xs.append(x2)
        ys.append(y2)
        zs.append(z2)
        vals.append(round(get_force(last_e, comp_j), 3))
        node_ids.append(n2)
        return np.array(xs), np.array(ys), np.array(zs), np.array(vals), node_ids

    fig_bmd = go.Figure()
    add_grillage_background(fig_bmd, nodes, members)

    # =========================================================
    # MASTER LISTS FOR REDUCING DRAW CALLS
    # =========================================================
    master_line_x, master_line_y, master_line_z = [], [], []
    master_base_x, master_base_y, master_base_z = [], [], []
    master_max_x, master_max_y, master_max_z = [], [], []
    master_min_x, master_min_y, master_min_z = [], [], []
    master_hover_text = []
    master_label_x, master_label_y, master_label_z, master_label_text = [], [], [], []

    sorted_girders = sorted(girders.items(), key=lambda item: item[0])
    for i, (gid, elems) in enumerate(sorted_girders):
        girder_name = f"G{i+1}"
        xs, ys, zs, mz, node_ids = build_polyline(elems, comp_i, comp_j)
        if max(mz) - min(mz) == 0:
            factormz = 0.1 * abs((max(xs) - min(xs)) / (max(mz) - 0))
        else:
            factormz = 0.1 * abs((max(xs) - min(xs)) / (max(mz) - min(mz)))
            
        y_plot = mz * factormz 
        
        # 1. ADD GO.SURFACE DIRECTLY (Preserving your exact look)
        fig_bmd.add_trace(go.Surface(
            x=[xs, xs], y=[np.zeros(len(xs)), y_plot], z=[zs, zs],
            surfacecolor=[[1]*len(xs), [1]*len(xs)], colorscale=[[0, 'red'], [1, 'red']],     
            opacity=0.2, showscale=False, hoverinfo="skip"
        ))
        
        # 2. Append to Master Moment Line
        master_line_x.extend(list(xs) + [None])
        master_line_y.extend(list(y_plot) + [None])
        master_line_z.extend(list(zs) + [None])
        
        hover_text = [
            f"Node {nid}<br>X = {x:.2f}<br>{force_key} = {v:.2f}<br>Z = {z:.2f}"
            for nid, x, v, z in zip(node_ids, xs, mz, zs)
        ]
        master_hover_text.extend(hover_text + [None])

        # 3. Append to Master Baseline
        master_base_x.extend([xs[0], xs[-1], None])
        master_base_y.extend([0, 0, None])
        master_base_z.extend([zs[0], zs[0], None])

        # 4. Append to Master Text Labels
        master_label_x.append(xs[0])
        master_label_y.append(0)
        master_label_z.append(zs[0])
        master_label_text.append(f"<b>{girder_name}</b>")

        # 5. Append to Master MAX lines
        idx_max = np.argmax(mz)
        master_max_x.extend([xs[idx_max], xs[idx_max], None])
        master_max_y.extend([0, max(mz) * factormz, None])
        master_max_z.extend([zs[0], zs[0], None])

        # 6. Append to Master MIN lines
        idx_min = np.argmin(mz)
        master_min_x.extend([xs[idx_min], xs[idx_min], None])
        master_min_y.extend([0, min(mz) * factormz, None])
        master_min_z.extend([zs[0], zs[0], None])

    # =========================================================
    # ADD MASTER TRACES (Hundreds of objects compressed down)
    # =========================================================

    # Add ALL moment lines and markers as a single object
    fig_bmd.add_trace(go.Scatter3d(
        x=master_line_x, y=master_line_y, z=master_line_z, mode='lines+markers', line=dict(color="red", width=4),
        marker=dict(size=3, color="red"), showlegend=False, text=master_hover_text, hoverinfo="text"
    ))

    # Add ALL baselines as a single object
    fig_bmd.add_trace(go.Scatter3d(
        x=master_base_x, y=master_base_y, z=master_base_z, mode='lines',
        line=dict(color="green", width=3, dash='solid'), showlegend=False, hoverinfo='skip'
    ))

    # Add ALL labels as a single object
    fig_bmd.add_trace(go.Scatter3d(
        x=master_label_x, y=master_label_y, z=master_label_z, mode="text", text=master_label_text,
        textposition="middle left", textfont=dict(size=14, color="black"),
        showlegend=False, hoverinfo="skip"
    ))

    # Add ALL MAX lines as a single hidden object
    fig_bmd.add_trace(go.Scatter3d(
        x=master_max_x, y=master_max_y, z=master_max_z, mode="lines", line=dict(color="black", width=3),
        legendgroup="max_lines", showlegend=False, visible=False, hoverinfo="skip"
    ))

    # Add ALL MIN lines as a single hidden object
    fig_bmd.add_trace(go.Scatter3d(
        x=master_min_x, y=master_min_y, z=master_min_z, mode="lines", line=dict(color="black", width=3),
        legendgroup="min_lines", showlegend=False, visible=False, hoverinfo="skip"
    ))

    fig_bmd.update_layout(
        hoverlabel=dict(
            bgcolor="#FFE4E1", font_size=12, font_family="Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif", 
            font_color="#2C3E50", bordercolor="#CBD5E1", namelength=-1                
        ),
        updatemenus=[
            dict(
                type="buttons", direction="right", x=0.5, y=1.15, showactive=True, active=-1,
                buttons=[
                    dict(
                        label="MAX", method="update",
                        args=[{"visible": [True if t.legendgroup == "max_lines" else t.visible for t in fig_bmd.data]}],
                        args2=[{"visible": [False if t.legendgroup == "max_lines" else t.visible for t in fig_bmd.data]}]
                    ),
                    dict(
                        label="MIN", method="update",
                        args=[{"visible": [True if t.legendgroup == "min_lines" else t.visible for t in fig_bmd.data]}],
                        args2=[{"visible": [False if t.legendgroup == "min_lines" else t.visible for t in fig_bmd.data]}]
                    ),
                ]
            )
        ],
        scene=dict(
            camera=dict(up=dict(x=0, y=0.5, z=0)),
            xaxis=dict(title="girder length", showbackground=False, showgrid=False, zeroline=False, visible=False),
            yaxis=dict(title="Mz values", showbackground=True, backgroundcolor="rgba(200,200,200,0.15)", showgrid=False, zeroline=False, visible=False),
            zaxis=dict(showbackground=False, showgrid=False, zeroline=False, visible=False, autorange="reversed"),
            aspectmode='data',
        ),
        # --- THE ANTI-FLICKER BACKGROUND FIX ---
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin=dict(l=0, r=0, t=40, b=0)
    )
    fig_bmd.write_html(TEMP_HTML, include_plotlyjs=True, full_html=True)


# ============================================================
# BMD CONTOUR
# ============================================================
def build_figure_bmd_contour(ds, force_key):
    def find_component(name):
        for c in ds["Component"].values:
            if c.lower() == name.lower():
                return c
        return None

    comp_i_name, comp_j_name = FORCE_MAP[force_key]
    comp_i = find_component(comp_i_name)
    comp_j = find_component(comp_j_name)

    def get_force(elem, comp):
        return float(ds["forces"].sel(Element=elem, Component=comp).values)

    Z_TOL = 3 
    node_z = {}
    for n in ops.getNodeTags():
        z = float(ops.nodeCoord(n)[2])
        node_z[int(n)] = round(z, Z_TOL)
        
    from collections import defaultdict
    girders = defaultdict(list)

    for ele in ops.getEleTags():
        ele_id = int(ele)
        n1, n2 = map(int, ops.eleNodes(ele))
        z1 = node_z[n1]
        z2 = node_z[n2]
        if z1 == z2:
            girders[z1].append(int(ele))

    def build_polyline(elem_list, comp_i, comp_j):
        xs, ys, zs, mz, node_ids = [], [], [], [], []
        for e in elem_list:
            n1, n2 = members[e]
            x1, y1, z1 = nodes[n1]
            xs.append(x1)
            ys.append(y1)
            zs.append(z1)
            mz.append(round(get_force(e, comp_i), 3))
            node_ids.append(n1)

        last_e = elem_list[-1]
        n1, n2 = members[last_e]
        x2, y2, z2 = nodes[n2]
        xs.append(x2)
        ys.append(y2)
        zs.append(z2)
        mz.append(round(get_force(last_e, comp_j), 3))
        node_ids.append(n2)
        return np.array(xs), np.array(ys), np.array(zs), np.array(mz), node_ids

    xfull, mzfull = [], []
    for elems in girders.values():
        xs, ys, zs, mz, _ = build_polyline(elems, comp_i, comp_j)
        xfull.extend(xs)
        mzfull.extend(mz)

    fig = go.Figure()
    add_grillage_background(fig, nodes, members)

    # =========================================================
    # MASTER LISTS FOR REDUCING DRAW CALLS
    # =========================================================
    master_drop_x, master_drop_y, master_drop_z, master_drop_color = [], [], [], []
    master_base_x, master_base_y, master_base_z = [], [], []

    sorted_girders = sorted(girders.items(), key=lambda item: item[0])
    for i, (gid, elems) in enumerate(sorted_girders):
        girder_name = f"G{i+1}"
        xs, ys, zs, mz, node_ids = build_polyline(elems, comp_i, comp_j)
        if max(mz) - min(mz) == 0:
            moment_scale = 0.1 * abs((max(xs) - min(xs)) / (max(mz) - 0))
        else:
            moment_scale = 0.1 * abs((max(xs) - min(xs)) / (max(mz) - min(mz)))
            
        y_plot = mz * moment_scale

        # 1. Add Translucent Surface (Must remain per girder)
        fig.add_trace(go.Surface(
            x=[xs, xs], y=[np.zeros(len(xs)), y_plot], z=[zs, zs],
            surfacecolor=[mz, mz], colorscale="Jet", cmin=min(mzfull), cmax=max(mzfull),
            opacity=0.4, showscale=False, hoverinfo="skip"
        ))

        # 2. Add Top Contour Line (Must remain per girder for hover text mapping)
        fig.add_trace(go.Scatter3d(
            x=xs, y=y_plot, z=zs, mode="lines",
            line=dict(width=6, color=mz, colorscale="Jet", cmin=min(mzfull), cmax=max(mzfull)),
            showlegend=False, hoverinfo="text",
            text=[f"Node {nid}<br>X={x:.2f}<br>{force_key}={v:.2f}" for nid, x, v in zip(node_ids, xs, mz)]
        ))

        # 3. Add Girder Text Label
        fig.add_trace(go.Scatter3d(
            x=[xs[0]], y=[0], z=[zs[0]], mode="text", text=[f"<b>{girder_name}</b>"],
            textposition="middle left", textfont=dict(size=14, color="black"),
            showlegend=False, hoverinfo="skip"
        ))

        # 4. Append to Master Baseline
        master_base_x.extend([xs[0], xs[-1], None])
        master_base_y.extend([0, 0, None])
        master_base_z.extend([zs[0], zs[0], None])

        # 5. Append to Master Droplines
        for xi, zi, mzi in zip(xs, zs, mz):
            master_drop_x.extend([xi, xi, None])
            master_drop_y.extend([0, mzi * moment_scale, None])
            master_drop_z.extend([zi, zi, None])
            master_drop_color.extend([mzi, mzi, mzi])

    # =========================================================
    # ADD MASTER TRACES (Hundreds of objects compressed into 2)
    # =========================================================
    
    # Add ALL baselines as a single object
    fig.add_trace(go.Scatter3d(
        x=master_base_x, y=master_base_y, z=master_base_z, mode="lines",
        line=dict(color="green", width=3), hoverinfo="skip", showlegend=False
    ))

    # Add ALL droplines as a single object
    fig.add_trace(go.Scatter3d(
        x=master_drop_x, y=master_drop_y, z=master_drop_z, mode="lines",
        line=dict(width=4, color=master_drop_color, colorscale="Jet", cmin=min(mzfull), cmax=max(mzfull)),
        showlegend=False, hoverinfo="skip"
    ))

    fig.update_layout(
        hoverlabel=dict(
            bgcolor="rgba(15, 23, 42, 0.95)", font_size=12, font_family="Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif", 
            font_color="#F8F9FA", bordercolor="#0EA5E9", namelength=-1                      
        ),
        scene=dict(
            camera=dict(up=dict(x=0, y=1, z=0)),
            xaxis=dict(title="girder length", showbackground=False, showgrid=False, zeroline=False, visible=False),
            yaxis=dict(title="Mz values", showbackground=True, backgroundcolor="rgba(200,200,200,0.15)", showgrid=False, zeroline=False, visible=False),
            zaxis=dict(showbackground=False, showgrid=False, zeroline=False, visible=False, autorange="reversed"),
            aspectmode='data',
        ),
        # --- THE ANTI-FLICKER BACKGROUND FIX ---
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin=dict(l=0, r=0, t=40, b=0)
    )
    
    fig.write_html(TEMP_HTML, include_plotlyjs=True, full_html=True)