"""  
低面数模型力场渲染 — 六方案可视化对比实验
"""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from scipy.ndimage import gaussian_filter
import os

# Chinese font setup
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

output_dir = r"D:\workshop\3D-\方案对比"
os.makedirs(output_dir, exist_ok=True)
np.random.seed(42)

# ═══════════ 工具函数 ═══════════
def wendland_phi(r): return 0 if r >= 1 else (1 - r)**4 * (4 * r + 1)

def jet_colormap(t):
    t = max(0, min(1, t))
    if t < 0.125: s = t / 0.125; r, g, b = 0, 0, (128 + 127 * s) / 255
    elif t < 0.375: s = (t - 0.125) / 0.25; r, g, b = 0, s, 1
    elif t < 0.625: s = (t - 0.375) / 0.25; r, g, b = s, 1, 1 - s
    elif t < 0.875: s = (t - 0.625) / 0.25; r, g, b = 1, 1 - s, 0
    else: s = (t - 0.875) / 0.125; r, g, b = 1 - s * 0.5, 0, 0
    return (r, g, b)

def create_sphere(n_lat=8, n_lon=12):
    verts = [(0, 0, 1)]
    for lat in np.linspace(0.1, np.pi - 0.1, n_lat):
        for lon in np.linspace(0, 2 * np.pi, n_lon, endpoint=False):
            verts.append((np.sin(lat) * np.cos(lon), np.sin(lat) * np.sin(lon), np.cos(lat)))
    verts.append((0, 0, -1))
    n_ring = n_lon
    faces = []
    for i in range(n_ring): faces.append((0, 1 + i, 1 + (i + 1) % n_ring))
    for ri in range(n_lat - 1):
        b0 = 1 + ri * n_ring; b1 = 1 + (ri + 1) * n_ring
        for i in range(n_ring):
            nxt = (i + 1) % n_ring
            faces.append((b0 + i, b0 + nxt, b1 + i))
            faces.append((b0 + nxt, b1 + nxt, b1 + i))
    last = len(verts) - 1
    b0 = 1 + (n_lat - 1) * n_ring
    for i in range(n_ring): faces.append((b0 + i, last, b0 + (i + 1) % n_ring))
    return np.array(verts), np.array(faces)

def plot_mesh(ax, verts, faces, face_colors, alpha=0.9):
    tris = [[verts[a], verts[b], verts[c]] for a, b, c in faces]
    pc = Poly3DCollection(tris, alpha=alpha, linewidths=0, edgecolor='none')
    pc.set_facecolor(face_colors)
    ax.add_collection3d(pc)

def compute_face_colors(verts, faces, cells, radius):
    colors = []
    for a, b, c in faces:
        center = (verts[a] + verts[b] + verts[c]) / 3
        num, den = 0, 0
        for cell in cells:
            d = np.linalg.norm(center - cell["pos"])
            if d > radius: continue
            w = wendland_phi(d / radius)
            num += cell["pressure"] * w
            den += w
        if den > 1e-6:
            colors.append(jet_colormap(num / den))
        else:
            colors.append((0.5, 0.5, 0.5))
    return colors

def compute_grid_colors(x, y, z, cells, radius):
    colors = np.zeros((*x.shape, 3))
    for i in range(x.shape[0]):
        for j in range(x.shape[1]):
            p = np.array([x[i, j], y[i, j], z[i, j]])
            num, den = 0, 0
            for cell in cells:
                d = np.linalg.norm(p - cell["pos"])
                if d > radius: continue
                w = wendland_phi(d / radius)
                num += cell["pressure"] * w; den += w
            colors[i, j] = jet_colormap(num / den) if den > 1e-6 else (0.5, 0.5, 0.5)
    return colors

def plot_cells(ax):
    for cell in cells:
        ax.scatter(*cell["pos"], c='white', s=80, edgecolors='black', linewidth=1.5, zorder=10)

def setup_3d_axes(ax, title):
    ax.set_title(title, fontsize=12, fontweight='bold')
    ax.set_xlim(-1.1, 1.1); ax.set_ylim(-1.1, 1.1); ax.set_zlim(-1.1, 1.1)
    ax.set_box_aspect([1, 1, 1])

# ═══════════ 测试数据 ═══════════
cells = [
    {"pos": np.array([0.7, 0.2, 0.68]), "pressure": 0.85},
    {"pos": np.array([-0.5, -0.3, 0.82]), "pressure": 0.55},
    {"pos": np.array([0.1, 0.85, 0.45]), "pressure": 0.65},
]
for c in cells: c["pos"] /= np.linalg.norm(c["pos"])
radius = 1.4

# ═══════════ 图1: 问题现状 ═══════════
print("Generating: 01_problem_comparison.png")
fig, axes = plt.subplots(1, 2, figsize=(16, 7), subplot_kw={'projection': '3d'})
for ax_idx, (title, nl, nn) in enumerate([
    ("低面模型 (~200面)", 8, 12),
    ("高面模型 (~2000面)", 25, 40),
]):
    v, f = create_sphere(nl, nn)
    fc = compute_face_colors(v, f, cells, radius)
    plot_mesh(axes[ax_idx], v, f, fc)
    plot_cells(axes[ax_idx])
    setup_3d_axes(axes[ax_idx], title)
plt.suptitle("问题现状：低面数 vs 高面数 力场渲染对比", fontsize=16, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "01_problem_comparison.png"), dpi=150, bbox_inches='tight')
plt.close()

# ═══════════ 图2: 六方案 ═══════════
print("Generating: 02_six_schemes.png")
fig, axes = plt.subplots(2, 3, figsize=(20, 14), subplot_kw={'projection': '3d'})
axes = axes.flatten()
schemes = [
    ("一: 独立透明层+自适应细分", 25, 40),
    ("二: 原模型直接细分", 25, 40),
    ("三: GPU片元Shader", None, None),
    ("四: 屏幕空间后处理", None, None),
    ("五: UV纹理烘焙", None, None),
    ("六: 表面采样点云", None, None),
]

for ax_idx, (name, nl, nn) in enumerate(schemes):
    ax = axes[ax_idx]
    if ax_idx == 2:  # Shader = pixel-perfect grid rendering
        th = np.linspace(0, np.pi, 60); ph = np.linspace(0, 2 * np.pi, 90)
        tt, pp = np.meshgrid(th, ph)
        x, y, z = np.sin(tt) * np.cos(pp), np.sin(tt) * np.sin(pp), np.cos(tt)
        colors = compute_grid_colors(x, y, z, cells, radius)
        ax.plot_surface(x, y, z, facecolors=colors, rstride=1, cstride=1, shade=False)
    elif ax_idx == 3:  # 后处理 = blur
        res = 60; xg, yg = np.meshgrid(np.linspace(-1, 1, res), np.linspace(-1, 1, res))
        mask = xg**2 + yg**2 <= 1; zg = np.sqrt(np.clip(1 - xg**2 - yg**2, 0, None))
        img = compute_grid_colors(xg, yg, zg, cells, radius)
        for ch in range(3): img[..., ch] = gaussian_filter(img[..., ch], sigma=2.5)
        ax.plot_surface(xg, yg, zg, facecolors=img, rstride=2, cstride=2, shade=False)
    elif ax_idx == 4:  # UV
        u = np.linspace(0, 2 * np.pi, 96); v = np.linspace(0.1, np.pi - 0.1, 48)
        uu, vv = np.meshgrid(u, v)
        x, y, z = np.sin(vv) * np.cos(uu), np.sin(vv) * np.sin(uu), np.cos(vv)
        colors = compute_grid_colors(x, y, z, cells, radius)
        ax.plot_surface(x, y, z, facecolors=colors, rstride=1, cstride=1, shade=False)
    elif ax_idx == 5:  # 点云
        n = 4000; th = np.arccos(1 - 2 * np.random.random(n))
        ph = 2 * np.pi * np.random.random(n)
        sx, sy, sz = np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)
        for i in range(n):
            p = np.array([sx[i], sy[i], sz[i]])
            num, den = 0, 0
            for cell in cells:
                d = np.linalg.norm(p - cell["pos"])
                if d > radius: continue
                w = wendland_phi(d / radius); num += cell["pressure"] * w; den += w
            if den > 1e-6:
                ax.scatter(sx[i], sy[i], sz[i], c=[jet_colormap(num / den)], s=15, alpha=0.7)
    else:
        v, f = create_sphere(nl, nn)
        fc = compute_face_colors(v, f, cells, radius)
        plot_mesh(ax, v, f, fc)
    plot_cells(ax)
    setup_3d_axes(ax, name)
plt.suptitle("六种力场渲染方案效果对比", fontsize=16, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "02_six_schemes.png"), dpi=150, bbox_inches='tight')
plt.close()

# ═══════════ 图3: 密度对比 ═══════════
print("Generating: 03_density_vs_quality.png")
fig, axes = plt.subplots(1, 4, figsize=(22, 6), subplot_kw={'projection': '3d'})
configs = [("~200面", 8, 12, "mesh"), ("~800面", 15, 24, "mesh"),
           ("~3000面", 30, 50, "mesh"), ("像素级", 80, 120, "grid")]
for ax_idx, (title, nl, nn, mode) in enumerate(configs):
    ax = axes[ax_idx]
    if mode == "grid":
        th = np.linspace(0.1, np.pi - 0.1, nl); ph = np.linspace(0, 2 * np.pi, nn)
        tt, pp = np.meshgrid(th, ph)
        x, y, z = np.sin(tt) * np.cos(pp), np.sin(tt) * np.sin(pp), np.cos(tt)
        colors = compute_grid_colors(x, y, z, cells, radius)
        ax.plot_surface(x, y, z, facecolors=colors, rstride=1, cstride=1, shade=False)
    else:
        v, f = create_sphere(nl, nn)
        fc = compute_face_colors(v, f, cells, radius)
        plot_mesh(ax, v, f, fc)
    plot_cells(ax)
    setup_3d_axes(ax, title)
plt.suptitle("顶点密度对渲染效果的影响", fontsize=16, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "03_density_vs_quality.png"), dpi=150, bbox_inches='tight')
plt.close()

# ═══════════ 图4: 雷达图 ═══════════
print("Generating: 04_radar_scores.png")
fig, ax = plt.subplots(1, 1, figsize=(10, 10), subplot_kw={'projection': 'polar'})
cats = ["视觉平滑度", "低面效果", "实现容易度", "性能", "系统影响小", "推荐度"]
N = len(cats)
angles = [n / N * 2 * np.pi for n in range(N)] + [0]
scores = {
    "① 力场层+细分": [7, 8, 6, 6, 8, 9],
    "② 原模型细分": [7, 8, 8, 4, 3, 4],
    "③ GPU Shader": [10, 10, 3, 7, 8, 10],
    "④ 屏幕后处理": [10, 10, 2, 6, 5, 5],
    "⑤ UV纹理": [9, 8, 2, 7, 5, 3],
    "⑥ 点云采样": [7, 8, 5, 6, 7, 6],
}
clrs = ['#2196F3', '#FF9800', '#4CAF50', '#9C27B0', '#F44336', '#607D8B']
for (name, sc), c in zip(scores.items(), clrs):
    vals = sc + sc[:1]
    ax.fill(angles, vals, alpha=0.1, color=c)
    ax.plot(angles, vals, 'o-', linewidth=2, label=name, color=c, markersize=5)
ax.set_xticks(angles[:-1]); ax.set_xticklabels(cats, fontsize=11)
ax.set_ylim(0, 10); ax.set_yticks([2, 4, 6, 8, 10])
ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=9)
ax.set_title("六方案多维评分对比", fontsize=16, fontweight='bold', pad=20)
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "04_radar_scores.png"), dpi=150, bbox_inches='tight')
plt.close()

# ═══════════ 图5: 路线图 ═══════════
print("Generating: 05_roadmap.png")
fig, ax = plt.subplots(1, 1, figsize=(18, 6))
ax.set_xlim(0, 10); ax.set_ylim(0, 4); ax.axis('off')
phases = [
    ("Phase 1\n短期", "独立力场层\n+自适应细分", "中等难度\n快速落地", "#2196F3", 2),
    ("Phase 2\n验证", "低面模型\n效果测试", "性能调优\n参数确定", "#4CAF50", 4.5),
    ("Phase 3\n中期", "替换为\nGPU片元Shader", "高难度\n长期方案", "#FF9800", 7),
    ("Phase 4\n远期", "法线约束\n测地距离", "薄壁模型\n背面串色", "#9C27B0", 9.2),
]
for title, desc, detail, color, x in phases:
    rect = FancyBboxPatch((x-0.8, 1.5), 1.6, 0.8, boxstyle="round,pad=0.1",
                          facecolor=color, edgecolor='white', linewidth=2, alpha=0.9)
    ax.add_patch(rect)
    ax.text(x, 2.3, title, ha='center', fontsize=11, fontweight='bold', color='#333')
    ax.text(x, 1.9, desc, ha='center', fontsize=9, color='white', fontweight='bold')
    ax.text(x, 1.5, detail, ha='center', fontsize=8, color='#eee')
    if x < 9:
        ax.annotate('', xy=(x+0.7, 1.9), xytext=(x+0.9, 1.9),
                    arrowprops=dict(arrowstyle='->', color='#666', lw=2))
ax.set_title("推荐实施路线图", fontsize=18, fontweight='bold', pad=10)
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "05_roadmap.png"), dpi=150, bbox_inches='tight')
plt.close()

print("\n=== Done ===\n" + "\n".join(os.listdir(output_dir)))
