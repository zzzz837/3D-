"""
测试数据生成器 — 合成传感器数据 + 真值场
"""

import numpy as np
from dataclasses import dataclass
from typing import Tuple

from algorithms import CellData


@dataclass
class TestScenario:
    name: str
    cells: CellData
    grid_x: np.ndarray
    grid_y: np.ndarray
    ground_truth: np.ndarray
    description: str


def _make_grid(x_range, y_range, resolution):
    xs = np.linspace(x_range[0], x_range[1], resolution)
    ys = np.linspace(y_range[0], y_range[1], resolution)
    grid_x, grid_y = np.meshgrid(xs, ys)
    return grid_x, grid_y


# 底层真值函数池
def _gaussian_mixture(grid_x, grid_y):
    """两个高斯峰 + 背景梯度"""
    z = np.zeros_like(grid_x)
    for cx, cy, sx, sy, amp in [
        (100, 150, 50, 40, 100),
        (160, 80, 40, 60, 80),
        (60, 60, 60, 50, 60),
    ]:
        z += amp * np.exp(-((grid_x - cx) ** 2 / (2 * sx ** 2) + (grid_y - cy) ** 2 / (2 * sy ** 2)))
    z += 10 * np.exp(-((grid_x - 120) ** 2 + (grid_y - 120) ** 2) / 800)
    return z


def _saddle(grid_x, grid_y):
    """马鞍面 + 局部高斯坑"""
    z = 30 + 15 * np.sin(grid_x / 80 * np.pi) * np.cos(grid_y / 80 * np.pi)
    z += 40 * np.exp(-((grid_x - 110) ** 2 + (grid_y - 110) ** 2) / 300)
    z -= 25 * np.exp(-((grid_x - 70) ** 2 + (grid_y - 150) ** 2) / 500)
    return np.maximum(z, 0)


def _multi_peak(grid_x, grid_y):
    """密集多峰 — 测试局部平滑能力"""
    z = np.zeros_like(grid_x)
    peaks = [
        (80, 80, 25, 25, 100), (130, 90, 20, 30, 85),
        (100, 140, 30, 20, 90), (60, 130, 22, 28, 75),
        (150, 150, 25, 25, 70), (90, 100, 18, 18, 65),
        (120, 120, 15, 15, 55), (160, 60, 20, 20, 50),
    ]
    for cx, cy, sx, sy, amp in peaks:
        z += amp * np.exp(-((grid_x - cx) ** 2 / (2 * sx ** 2) + (grid_y - cy) ** 2 / (2 * sy ** 2)))
    return z


# 采样策略
def _sample_uniform(grid_x, grid_y, truth, n):
    idxs = np.random.choice(grid_x.size, n, replace=False)
    ys, xs = np.unravel_index(idxs, grid_x.shape)
    positions = np.column_stack([grid_x.ravel()[idxs], grid_y.ravel()[idxs]])
    pressures = truth.ravel()[idxs]
    return CellData(positions=positions, pressures=pressures)


def _sample_clustered(grid_x, grid_y, truth, n_clusters=3, points_per_cluster=30):
    cx_list = np.random.uniform(grid_x.min(), grid_x.max(), n_clusters)
    cy_list = np.random.uniform(grid_y.min(), grid_y.max(), n_clusters)
    positions = []
    for cx, cy in zip(cx_list, cy_list):
        for _ in range(points_per_cluster):
            px = np.clip(cx + np.random.randn() * 15, grid_x.min(), grid_x.max())
            py = np.clip(cy + np.random.randn() * 15, grid_y.min(), grid_y.max())
            positions.append([px, py])
    positions = np.array(positions)
    # 采样真值
    pressures = []
    for px, py in positions:
        dx = np.abs(grid_x[0, :] - px)
        dy = np.abs(grid_y[:, 0] - py)
        ix = np.argmin(dx)
        iy = np.argmin(dy)
        pressures.append(truth[iy, ix])
    return CellData(positions=positions, pressures=np.array(pressures))


def _sample_edge_sparse(grid_x, grid_y, truth, n_center=40, n_edge=5):
    x_center = grid_x.mean()
    y_center = grid_y.mean()
    x_span = grid_x.max() - grid_x.min()
    y_span = grid_y.max() - grid_y.min()
    positions = []
    # 中心密集
    for _ in range(n_center):
        px = np.clip(x_center + np.random.randn() * x_span * 0.2, grid_x.min(), grid_x.max())
        py = np.clip(y_center + np.random.randn() * y_span * 0.2, grid_y.min(), grid_y.max())
        positions.append([px, py])
    # 边缘稀疏
    for _ in range(n_edge):
        edge = np.random.choice(['top', 'bottom', 'left', 'right'])
        if edge == 'top':
            px = np.random.uniform(grid_x.min(), grid_x.max())
            py = grid_y.max() - np.random.uniform(0, 10)
        elif edge == 'bottom':
            px = np.random.uniform(grid_x.min(), grid_x.max())
            py = grid_y.min() + np.random.uniform(0, 10)
        elif edge == 'left':
            px = grid_x.min() + np.random.uniform(0, 10)
            py = np.random.uniform(grid_y.min(), grid_y.max())
        else:
            px = grid_x.max() - np.random.uniform(0, 10)
            py = np.random.uniform(grid_y.min(), grid_y.max())
        positions.append([px, py])

    positions = np.array(positions)
    pressures = []
    for px, py in positions:
        dx = np.abs(grid_x[0, :] - px)
        dy = np.abs(grid_y[:, 0] - py)
        ix = np.argmin(dx)
        iy = np.argmin(dy)
        pressures.append(truth[iy, ix])
    return CellData(positions=positions, pressures=np.array(pressures))


# ═══════════════════════════════════════════════════════
# 测试场景工厂
# ═══════════════════════════════════════════════════════

def generate_all_scenarios(resolution=200, seed=42) -> list[TestScenario]:
    np.random.seed(seed)
    grid_x, grid_y = _make_grid((0, 200), (0, 200), resolution)
    scenarios = []

    # 场景1: 均匀采样 + 双高斯
    truth = _gaussian_mixture(grid_x, grid_y)
    cells = _sample_uniform(grid_x, grid_y, truth, n=120)
    scenarios.append(TestScenario(
        name="uniform_gaussian",
        cells=cells,
        grid_x=grid_x, grid_y=grid_y,
        ground_truth=truth,
        description="120 cells 均匀采样 | 真值: 双高斯+背景",
    ))

    # 场景2: 聚类采样 + 双高斯
    cells = _sample_clustered(grid_x, grid_y, truth, n_clusters=4, points_per_cluster=25)
    scenarios.append(TestScenario(
        name="clustered_gaussian",
        cells=cells,
        grid_x=grid_x, grid_y=grid_y,
        ground_truth=truth,
        description="4簇×25 cells 聚类采样 | 真值: 双高斯+背景",
    ))

    # 场景3: 均匀采样 + 马鞍面
    saddle_truth = _saddle(grid_x, grid_y)
    cells = _sample_uniform(grid_x, grid_y, saddle_truth, n=100)
    scenarios.append(TestScenario(
        name="uniform_saddle",
        cells=cells,
        grid_x=grid_x, grid_y=grid_y,
        ground_truth=saddle_truth,
        description="100 cells 均匀采样 | 真值: 马鞍面+坑",
    ))

    # 场景4: 多峰复杂场 + 边缘稀疏
    multi_truth = _multi_peak(grid_x, grid_y)
    cells = _sample_edge_sparse(grid_x, grid_y, multi_truth, n_center=50, n_edge=8)
    scenarios.append(TestScenario(
        name="edge_sparse_multi",
        cells=cells,
        grid_x=grid_x, grid_y=grid_y,
        ground_truth=multi_truth,
        description="50中心+8边缘 | 真值: 8峰密集场",
    ))

    # 场景5: 极稀疏 (模拟<20 cells)
    truth = _gaussian_mixture(grid_x, grid_y)
    cells = _sample_uniform(grid_x, grid_y, truth, n=15)
    scenarios.append(TestScenario(
        name="sparse_15",
        cells=cells,
        grid_x=grid_x, grid_y=grid_y,
        ground_truth=truth,
        description="仅15 cells 极稀疏 | 真值: 双高斯+背景",
    ))

    return scenarios
