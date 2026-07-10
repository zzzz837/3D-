"""
基于 OBJ 模型的三种压力场重建算法对比

在真实 3D 模型表面放置传感器Cell，运行三种算法，
渲染带热力图颜色的3D网格，从多角度截图对比。

用法:
    python mesh_compare.py
    python mesh_compare.py --cells 80 --radius 30
"""

import os, sys, argparse, time
import numpy as np
import trimesh
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from scipy.spatial import KDTree
from scipy import sparse
from scipy.sparse.linalg import spsolve

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
OBJ_PATH = r"D:\workshop\3D-\HumanoidRobot_v3_L1.123c22979121-1c38-4620-bee4-8aad3c69735f\11072_HumanoidRobot_v3.obj"

JET_COLORS = [
    (0.000, (0, 0, 0.5)),
    (0.125, (0, 0, 1)),
    (0.375, (0, 1, 1)),
    (0.625, (1, 1, 0)),
    (0.875, (1, 0, 0)),
    (1.000, (0.5, 0, 0)),
]
JET = LinearSegmentedColormap.from_list("jet_sim", JET_COLORS)


# ══════════════════════════════════════════════════════════════
# Mesh loading & cell sampling
# ══════════════════════════════════════════════════════════════

def load_mesh(path):
    print(f"Loading mesh: {path}")
    mesh = trimesh.load(path, force="mesh")
    if isinstance(mesh, trimesh.Scene):
        meshes = list(mesh.geometry.values())
        mesh = trimesh.util.concatenate(meshes)
    print(f"  Vertices: {len(mesh.vertices):,}, Faces: {len(mesh.faces):,}")
    return mesh


def sample_cells_on_mesh(mesh, n_cells, seed=42):
    """在 mesh 表面采样 cell 位置, 并生成合成压力值."""
    np.random.seed(seed)
    pts, face_idx = trimesh.sample.sample_surface(mesh, n_cells * 2)
    pts = np.unique(np.round(pts, 2), axis=0)
    if len(pts) < n_cells:
        pts = pts
    else:
        idxs = np.random.choice(len(pts), n_cells, replace=False)
        pts = pts[idxs]
    print(f"  Sampled {len(pts)} cells on surface")

    # 合成压力: 几个椭圆高斯热点
    pressures = np.zeros(len(pts))
    hotspots = [
        (np.array([5, -8, 100]), np.array([25, 15, 40]), 1.0),
        (np.array([-10, -10, 50]), np.array([20, 12, 30]), 0.7),
        (np.array([8, -5, 140]), np.array([15, 10, 20]), 0.6),
    ]
    for center, sigma, amp in hotspots:
        d = (pts - center) / sigma
        dist = np.sqrt(np.sum(d ** 2, axis=1))
        pressures += amp * np.exp(-0.5 * dist ** 2)
    pressures = np.clip(pressures * 100, 0, 100)

    print(f"  Pressure range: [{pressures.min():.1f}, {pressures.max():.1f}]")
    return pts, pressures


# ══════════════════════════════════════════════════════════════
# Three Reconstructors (3D)
# ══════════════════════════════════════════════════════════════

def wendland_kernel(r):
    phi = np.zeros_like(r, dtype=float)
    m = r <= 1.0
    phi[m] = (1.0 - r[m]) ** 4 * (4.0 * r[m] + 1.0)
    return phi


def wendland_reconstruct_3d(vertices, cell_pos, cell_val, radius_mm=30.0):
    """Wendland C2 核加权插值 (3D Euclidean)."""
    t0 = time.perf_counter()
    field = np.zeros(len(vertices))
    radius = radius_mm

    # 3D 空间分桶
    bucket_size = radius
    v_min = vertices.min(axis=0)
    v_max = vertices.max(axis=0)
    span = v_max - v_min + 1e-6
    b_counts = np.maximum(1, np.ceil(span / bucket_size).astype(int))
    b_xy = b_counts[0] * b_counts[1]

    buckets = [[] for _ in range(b_counts[0] * b_counts[1] * b_counts[2])]
    for ci, pos in enumerate(cell_pos):
        bi = np.floor((pos - v_min) / bucket_size).astype(int)
        bi = np.clip(bi, 0, b_counts - 1)
        buck_i = int(bi[0] + bi[1] * b_counts[0] + bi[2] * b_xy)
        buckets[buck_i].append(ci)

    for vi, vtx in enumerate(vertices):
        bi = np.floor((vtx - v_min) / bucket_size).astype(int)
        bi = np.clip(bi, 0, b_counts - 1)
        numer = 0.0
        denom = 0.0

        for dz in range(max(0, bi[2] - 1), min(b_counts[2], bi[2] + 2)):
            for dy in range(max(0, bi[1] - 1), min(b_counts[1], bi[1] + 2)):
                for dx in range(max(0, bi[0] - 1), min(b_counts[0], bi[0] + 2)):
                    buck_i = dx + dy * b_counts[0] + dz * b_xy
                    for ci in buckets[buck_i]:
                        d = np.sqrt(np.sum((vtx - cell_pos[ci]) ** 2))
                        if d <= radius:
                            r_val = d / radius
                            w = float((1.0 - r_val) ** 4 * (4.0 * r_val + 1.0))
                            numer += cell_val[ci] * w
                            denom += w

        if denom > 1e-12:
            field[vi] = (numer / denom) * min(1.0, denom)

    elapsed = time.perf_counter() - t0
    return field, elapsed


def mls_reconstruct_3d(vertices, cell_pos, cell_val, k=12):
    """MLS 局部一次曲面拟合 (3D)."""
    t0 = time.perf_counter()
    field = np.zeros(len(vertices))
    tree = KDTree(cell_pos)
    k_actual = min(k, len(cell_pos))

    for vi, vtx in enumerate(vertices):
        dists, idxs = tree.query(vtx, k=k_actual)
        idxs = np.atleast_1d(idxs)
        dists = np.atleast_1d(dists)

        dx = cell_pos[idxs] - vtx
        vals = cell_val[idxs]

        sigma = max(np.mean(dists) * 2.0, 1e-6)
        w = np.exp(-0.5 * (dists / sigma) ** 2)
        W_sqrt = np.sqrt(w)

        A = np.column_stack([dx[:, 0], dx[:, 1], dx[:, 2], np.ones_like(dx[:, 0])])
        A_w = A * W_sqrt[:, np.newaxis]
        b_w = vals * W_sqrt

        try:
            coeffs, _, _, _ = np.linalg.lstsq(A_w, b_w, rcond=None)
            field[vi] = float(coeffs[3])
        except np.linalg.LinAlgError:
            field[vi] = float(np.mean(vals))

    elapsed = time.perf_counter() - t0
    return field, elapsed


def laplacian_reconstruct_3d(mesh, cell_pos, cell_val):
    """Graph Laplacian 扩散 (使用 mesh 连通性)."""
    t0 = time.perf_counter()
    vertices = mesh.vertices
    n = len(vertices)

    # 找每个 cell 的最近顶点
    tree = KDTree(vertices)
    _, nearest_v = tree.query(cell_pos)
    known_mask = np.zeros(n, dtype=bool)
    known_val = np.zeros(n)
    for vi, val in zip(nearest_v, cell_val):
        known_mask[vi] = True
        known_val[vi] = val

    # 从 faces 构建邻接关系
    adj = {}
    for f in mesh.faces:
        for i in range(3):
            for j in range(3):
                if i != j:
                    a, b = f[i], f[j]
                    adj.setdefault(a, set()).add(b)

    # 构建稀疏 Laplace 矩阵 (uniform weights)
    row, col, data = [], [], []
    for i in range(n):
        if known_mask[i]:
            row.append(i)
            col.append(i)
            data.append(1.0)
        else:
            neighbors = adj.get(i, set())
            deg = len(neighbors)
            if deg == 0:
                row.append(i)
                col.append(i)
                data.append(1.0)
            else:
                row.append(i)
                col.append(i)
                data.append(float(deg))
                for nb in neighbors:
                    row.append(i)
                    col.append(nb)
                    data.append(-1.0)

    L = sparse.csr_matrix((data, (row, col)), shape=(n, n))
    b = known_val.copy()
    x = spsolve(L, b)
    field = np.asarray(x).ravel()

    elapsed = time.perf_counter() - t0
    return field, elapsed


# ══════════════════════════════════════════════════════════════
# Visualization
# ══════════════════════════════════════════════════════════════

def _norm_colors(values, cmap):
    vmin, vmax = values.min(), values.max()
    if vmax - vmin < 1e-8:
        vmax = vmin + 1.0
    normed = (values - vmin) / (vmax - vmin)
    if hasattr(cmap, '__call__'):
        return cmap(normed)[:, :3]
    return plt.cm.jet(normed)[:, :3]


def render_mesh_heatmap(mesh, vertex_values, title, save_path,
                        cells_pos=None, cells_val=None, cmap=JET):
    """用 matplotlib 3D 渲染带顶点颜色的 mesh."""
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")
    ax.set_title(title, fontsize=12, fontweight="bold")

    vertices = mesh.vertices
    faces = mesh.faces
    vcolors = _norm_colors(vertex_values, cmap)

    # 简化: 渲染三角形子集 (每10个面取1个, 否则太密)
    step = max(1, len(faces) // 15000)
    subset_faces = faces[::step]
    tri_verts = vertices[subset_faces]
    face_colors = np.mean(vcolors[subset_faces], axis=1)
    face_colors = np.clip(face_colors, 0, 1)

    mesh_collection = Poly3DCollection(
        tri_verts, facecolors=face_colors, edgecolors="none",
        alpha=0.9, linewidths=0, antialiased=True,
    )
    ax.add_collection3d(mesh_collection)

    # Cell 散点
    if cells_pos is not None and cells_val is not None:
        cell_colors = _norm_colors(cells_val, cmap)
        ax.scatter(
            cells_pos[:, 0], cells_pos[:, 1], cells_pos[:, 2],
            c=cell_colors, s=20, edgecolors="white", linewidths=0.3,
            depthshade=True,
        )

    # 坐标轴
    b = mesh.bounds
    cx = (b[0, 0] + b[1, 0]) / 2
    cy = (b[0, 1] + b[1, 1]) / 2
    cz = (b[0, 2] + b[1, 2]) / 2
    span = max(b[1] - b[0]) / 2
    ax.set_xlim(cx - span * 0.7, cx + span * 0.7)
    ax.set_ylim(cy - span * 0.7, cy + span * 0.7)
    ax.set_zlim(cz - span * 0.7, cz + span * 0.7)
    ax.set_xlabel("X"); ax.set_ylabel("Y"); ax.set_zlabel("Z")

    # 视角
    ax.view_init(elev=25, azim=-60)

    plt.tight_layout()
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return save_path


def render_multiview_grid(mesh, results, out_dir):
    """从6个不同角度渲染同一组结果, 拼成一张大图."""
    angles = [
        ("front", 25, -90),
        ("back", 25, 90),
        ("side_left", 25, 0),
        ("side_right", 25, 180),
        ("top", 90, -90),
        ("iso", 40, -60),
    ]
    n_methods = len(results)
    fig, axes = plt.subplots(
        len(angles), n_methods + 1,
        figsize=(3.5 * (n_methods + 1), 3 * len(angles)),
        subplot_kw={"projection": "3d"},
    )
    fig.suptitle("Multi-View Comparison — OBJ Surface Heatmap", fontsize=14, fontweight="bold")

    vertices = results[list(results.keys())[0]]["mesh"].vertices
    faces = results[list(results.keys())[0]]["mesh"].faces
    b = results[list(results.keys())[0]]["mesh"].bounds
    span = max(b[1] - b[0]) / 2
    cx = (b[0] + b[1]) / 2

    # 面采样步长
    step = max(1, len(faces) // 10000)
    subset_faces = faces[::step]

    for row, (label, elev, azim) in enumerate(angles):
        for i, (method_name, res) in enumerate(results.items()):
            col = i + 1  # 列0是Cells, 列1/2/3是三个方法
            ax = axes[row, col]
            vvals = res["field"]
            fcolors = np.mean(_norm_colors(vvals, JET)[subset_faces], axis=1)
            tri_verts = vertices[subset_faces]
            mc = Poly3DCollection(
                tri_verts, facecolors=fcolors, edgecolors="none",
                alpha=0.95, antialiased=True,
            )
            ax.add_collection3d(mc)
            ax.set_title(method_name if row == 0 else "", fontsize=9)
            ax.set_xlim(cx[0] - span * 0.7, cx[0] + span * 0.7)
            ax.set_ylim(cx[1] - span * 0.7, cx[1] + span * 0.7)
            ax.set_zlim(cx[2] - span * 0.7, cx[2] + span * 0.7)
            ax.view_init(elev=elev, azim=azim)
            ax.set_xticklabels([]); ax.set_yticklabels([]); ax.set_zticklabels([])

        # 第1列: cell positions
        ax = axes[row, 0]
        cells_pos = results[list(results.keys())[0]]["cells_pos"]
        cells_val = results[list(results.keys())[0]]["cells_val"]
        # 灰色 mesh
        tri_verts = vertices[subset_faces]
        gray_mc = Poly3DCollection(
            tri_verts, facecolors=[[0.7, 0.7, 0.7]] * len(subset_faces),
            edgecolors="none", alpha=0.4, antialiased=True,
        )
        ax.add_collection3d(gray_mc)
        ccolors = _norm_colors(cells_val, JET)
        ax.scatter(
            cells_pos[:, 0], cells_pos[:, 1], cells_pos[:, 2],
            c=ccolors, s=12, edgecolors="k", linewidths=0.2, depthshade=True,
        )
        ax.set_title("Cells" if row == 0 else "", fontsize=9)
        ax.set_xlim(cx[0] - span * 0.7, cx[0] + span * 0.7)
        ax.set_ylim(cx[1] - span * 0.7, cx[1] + span * 0.7)
        ax.set_zlim(cx[2] - span * 0.7, cx[2] + span * 0.7)
        ax.view_init(elev=elev, azim=azim)
        ax.set_xticklabels([]); ax.set_yticklabels([]); ax.set_zticklabels([])

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    save_path = os.path.join(out_dir, "multiview_comparison.png")
    fig.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return save_path


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cells", type=int, default=80,
                        help="Number of sensor cells (default: 80)")
    parser.add_argument("--radius", type=float, default=30.0,
                        help="Wendland query radius in mm (default: 30)")
    parser.add_argument("--mls-k", type=int, default=12,
                        help="MLS KNN neighbors (default: 12)")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    # ── Load ──
    mesh = load_mesh(OBJ_PATH)
    cell_pos, cell_val = sample_cells_on_mesh(mesh, args.cells)

    # ── Reconstruct ──
    print(f"\nRunning 3 algorithms on {len(mesh.vertices):,} vertices...")

    print("  [1/3] Wendland C2 (R={:.0f}mm) ... ".format(args.radius), end="", flush=True)
    w_field, w_time = wendland_reconstruct_3d(
        mesh.vertices, cell_pos, cell_val, radius_mm=args.radius
    )
    print(f"done ({w_time:.1f}s)")

    print("  [2/3] MLS (k={}) ... ".format(args.mls_k), end="", flush=True)
    m_field, m_time = mls_reconstruct_3d(
        mesh.vertices, cell_pos, cell_val, k=args.mls_k
    )
    print(f"done ({m_time:.1f}s)")

    print("  [3/3] Graph Laplacian (mesh topology) ... ", end="", flush=True)
    l_field, l_time = laplacian_reconstruct_3d(mesh, cell_pos, cell_val)
    print(f"done ({l_time:.1f}s)")

    # ── Pack results ──
    results = {
        "Wendland C2": {"field": w_field, "elapsed": w_time,
                        "cells_pos": cell_pos, "cells_val": cell_val, "mesh": mesh},
        "MLS (k={})".format(args.mls_k): {"field": m_field, "elapsed": m_time,
                                           "cells_pos": cell_pos, "cells_val": cell_val, "mesh": mesh},
        "Graph Laplacian": {"field": l_field, "elapsed": l_time,
                            "cells_pos": cell_pos, "cells_val": cell_val, "mesh": mesh},
    }

    # ── Single views ──
    print("\nRendering single-view images...")
    for method_name, res in results.items():
        path = os.path.join(OUT_DIR, f"mesh_{method_name.replace(' ', '_').replace('(','').replace(')','')}.png")
        render_mesh_heatmap(
            mesh, res["field"],
            f"{method_name}  ({res['elapsed']:.1f}s)",
            path,
            cells_pos=cell_pos, cells_val=cell_val,
        )
        print(f"  {method_name}: {os.path.basename(path)}")

    # ── Multi-view grid ──
    print("\nRendering multi-view grid...")
    mv_path = render_multiview_grid(mesh, results, OUT_DIR)
    print(f"  {os.path.basename(mv_path)}")

    # ── Report ──
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Model: {OBJ_PATH}")
    print(f"  Vertices: {len(mesh.vertices):,}, Faces: {len(mesh.faces):,}")
    print(f"  Cells: {len(cell_pos)},  Radius: {args.radius}mm")
    print(f"  {'Method':<20} {'Time':>8} {'Mean':>8} {'Max':>8} {'Min':>8}")
    for name, res in results.items():
        f = res["field"]
        print(f"  {name:<20} {res['elapsed']:>7.1f}s {f.mean():>8.2f} {f.max():>8.2f} {f.min():>8.2f}")
    print(f"  Images saved to: {OUT_DIR}")


if __name__ == "__main__":
    main()
