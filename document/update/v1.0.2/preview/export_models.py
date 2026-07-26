"""Export model data as FLAT JSON arrays for the HTML viewer.
Models: indenter (.3dlp), chair (STL), box (procedural)."""
import sys
import os
import json
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, '..'))

from common.dlp_loader import load_3dlp, extract_cell_arrays
from common.stl_loader import load_stl
from common.mesh_utils import compute_vertex_normals

PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', '..', '..', '..', '..'))
INDENTER_3DLP = os.path.join(PROJECT_ROOT, 'Document', '3D Model', '\u534a\u5706\u67f1\u538b\u5934.3dlp')
CHAIR_STL   = os.path.join(PROJECT_ROOT, 'Document', '3D Model', '\u6905\u5b50\u0032.stl')


def _flat_list(arr, decimals=4):
    return np.round(arr, decimals).ravel().tolist()


def export_indenter():
    print("Loading indenter from .3dlp...")
    verts, faces, cells, project = load_3dlp(INDENTER_3DLP)
    vn = compute_vertex_normals(verts, faces)
    cell_pos, cell_n, cell_r = extract_cell_arrays(cells)

    rng = np.random.default_rng(42)
    base_p = rng.uniform(0.3, 0.8, len(cell_pos))
    phases = rng.uniform(0, 2 * np.pi, len(cell_pos))

    bbox_min = verts.min(axis=0).tolist()
    bbox_max = verts.max(axis=0).tolist()

    print(f"  Vertices: {len(verts)}, Faces: {len(faces)}, Cells: {len(cell_pos)}")

    return {
        "name": "\u534a\u5706\u67f1\u538b\u5934 (Indenter)",
        "vCount": int(len(verts)), "fCount": int(len(faces)), "cCount": int(len(cell_pos)),
        "vertices": _flat_list(verts), "faces": faces.ravel().tolist(),
        "normals": _flat_list(vn),
        "cellPositions": _flat_list(cell_pos), "cellNormals": _flat_list(cell_n),
        "cellRadii": cell_r.tolist(),
        "cellBasePressures": base_p.tolist(), "cellPhases": phases.tolist(),
        "queryRadius": 8.0,
        "bbox": {"min": bbox_min, "max": bbox_max},
    }


def export_chair():
    print("Loading chair from STL...")
    verts, faces = load_stl(CHAIR_STL)
    vn = compute_vertex_normals(verts, faces)

    rng = np.random.default_rng(42)
    v0 = verts[faces[:, 0]]; v1 = verts[faces[:, 1]]; v2 = verts[faces[:, 2]]
    cross = np.cross(v1 - v0, v2 - v0)
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    face_idxs = rng.choice(len(faces), size=50, p=areas / areas.sum(), replace=False)

    cell_pos, cell_n = [], []
    for fi in face_idxs:
        r1, r2 = rng.random(), rng.random()
        if r1 + r2 > 1: r1, r2 = 1 - r1, 1 - r2
        r3 = 1 - r1 - r2
        pt = r1*verts[faces[fi,0]] + r2*verts[faces[fi,1]] + r3*verts[faces[fi,2]]
        n = r1*vn[faces[fi,0]] + r2*vn[faces[fi,1]] + r3*vn[faces[fi,2]]
        n = n / (np.linalg.norm(n) + 1e-12)
        cell_pos.append(pt); cell_n.append(n)

    cell_pos = np.array(cell_pos, dtype=np.float64)
    cell_n   = np.array(cell_n,   dtype=np.float64)
    cell_r   = np.full(50, 0.04, dtype=np.float64)
    base_p   = rng.uniform(0.3, 0.8, 50)
    phases   = rng.uniform(0, 2 * np.pi, 50)

    bbox_min = verts.min(axis=0).tolist()
    bbox_max = verts.max(axis=0).tolist()

    print(f"  Vertices: {len(verts)}, Faces: {len(faces)}, Cells: 50")

    return {
        "name": "\u6905\u5b50 (Chair)",
        "vCount": int(len(verts)), "fCount": int(len(faces)), "cCount": 50,
        "vertices": _flat_list(verts), "faces": faces.ravel().tolist(),
        "normals": _flat_list(vn),
        "cellPositions": _flat_list(cell_pos), "cellNormals": _flat_list(cell_n),
        "cellRadii": cell_r.tolist(),
        "cellBasePressures": base_p.tolist(), "cellPhases": phases.tolist(),
        "queryRadius": 0.08,
        "bbox": {"min": bbox_min, "max": bbox_max},
    }


def export_box():
    """Procedural box 50x30x50mm, cells on top face + front face only."""
    print("Generating procedural box model...")

    # Box dimensions: 50 wide (X), 30 tall (Y), 50 deep (Z), centered
    w, h, d = 50.0, 30.0, 50.0
    hw, hh, hd = w/2, h/2, d/2

    # 24 unique vertices (4 per face, 6 faces, sharp normals)
    verts = np.array([
        # Top face (Y = +hh), normal (0,1,0)
        [-hw, hh, -hd], [ hw, hh, -hd], [ hw, hh,  hd], [-hw, hh,  hd],
        # Bottom face (Y = -hh), normal (0,-1,0)
        [-hw, -hh,  hd], [ hw, -hh,  hd], [ hw, -hh, -hd], [-hw, -hh, -hd],
        # Front face (Z = +hd), normal (0,0,1)
        [-hw, -hh,  hd], [ hw, -hh,  hd], [ hw,  hh,  hd], [-hw,  hh,  hd],
        # Back face (Z = -hd), normal (0,0,-1)
        [ hw, -hh, -hd], [-hw, -hh, -hd], [-hw,  hh, -hd], [ hw,  hh, -hd],
        # Right face (X = +hw), normal (1,0,0)
        [ hw, -hh,  hd], [ hw, -hh, -hd], [ hw,  hh, -hd], [ hw,  hh,  hd],
        # Left face (X = -hw), normal (-1,0,0)
        [-hw, -hh, -hd], [-hw, -hh,  hd], [-hw,  hh,  hd], [-hw,  hh, -hd],
    ], dtype=np.float64)

    faces = np.array([
        [ 0, 1, 2], [ 0, 2, 3],   # top
        [ 4, 5, 6], [ 4, 6, 7],   # bottom
        [ 8, 9,10], [ 8,10,11],   # front
        [12,13,14], [12,14,15],   # back
        [16,17,18], [16,18,19],   # right
        [20,21,22], [20,22,23],   # left
    ], dtype=np.int32)

    # Subdivide to get enough vertices for visible force field
    from common.mesh_utils import barycentric_subdivide
    verts, faces = barycentric_subdivide(verts, faces, iterations=3)

    vn = compute_vertex_normals(verts, faces)

    # Generate cells: 10 on TOP face, 10 on FRONT face
    rng = np.random.default_rng(42)
    margin = 5.0

    cell_pos_list, cell_n_list = [], []

    # Top face cells: random within X[-hw+margin, hw-margin], Z[-hd+margin, hd-margin], Y = hh
    top_x = rng.uniform(-hw + margin, hw - margin, 10)
    top_z = rng.uniform(-hd + margin, hd - margin, 10)
    top_y = np.full(10, hh)
    for i in range(10):
        cell_pos_list.append([top_x[i], top_y[i], top_z[i]])
        cell_n_list.append([0.0, 1.0, 0.0])

    # Front face cells: random within X[-hw+margin, hw-margin], Y[-hh+margin, hh-margin], Z = hd
    fr_x = rng.uniform(-hw + margin, hw - margin, 10)
    fr_y = rng.uniform(-hh + margin, hh - margin, 10)
    fr_z = np.full(10, hd)
    for i in range(10):
        cell_pos_list.append([fr_x[i], fr_y[i], fr_z[i]])
        cell_n_list.append([0.0, 0.0, 1.0])

    cell_pos = np.array(cell_pos_list, dtype=np.float64)
    cell_n   = np.array(cell_n_list,   dtype=np.float64)
    cell_r   = np.full(20, 4.0, dtype=np.float64)  # 4mm radius
    base_p   = rng.uniform(0.4, 0.9, 20)
    phases   = rng.uniform(0, 2 * np.pi, 20)

    bbox_min = verts.min(axis=0).tolist()
    bbox_max = verts.max(axis=0).tolist()

    print(f"  Vertices: {len(verts)}, Faces: {len(faces)}, Cells: 20 (10 top + 10 front)")

    return {
        "name": "方盒子 (Box)",
        "vCount": int(len(verts)), "fCount": int(len(faces)), "cCount": 20,
        "vertices": _flat_list(verts), "faces": faces.ravel().tolist(),
        "normals": _flat_list(vn),
        "cellPositions": _flat_list(cell_pos), "cellNormals": _flat_list(cell_n),
        "cellRadii": cell_r.tolist(),
        "cellBasePressures": base_p.tolist(), "cellPhases": phases.tolist(),
        "queryRadius": 8.0,
        "bbox": {"min": bbox_min, "max": bbox_max},
    }


def main():
    data = {
        "indenter": export_indenter(),
        "chair":    export_chair(),
        "box":      export_box(),
    }

    output_path = os.path.join(SCRIPT_DIR, 'models_data.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'), ensure_ascii=False)

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"\nExported to: {output_path}")
    print(f"File size: {size_mb:.2f} MB")


if __name__ == '__main__':
    main()
