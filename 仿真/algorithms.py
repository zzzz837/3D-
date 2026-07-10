"""
三种压力场重建算法实现
1. Wendland C2 紧支撑核加权插值
2. Moving Least Squares (MLS) 局部曲面拟合
3. Graph Laplacian 扩散
"""

import time
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class CellData:
    positions: np.ndarray
    pressures: np.ndarray

    @property
    def n_cells(self) -> int:
        return len(self.pressures)


# ══════════════════════════════════════════════════════════════
# 1. Wendland C2 紧支撑核加权插值
# ══════════════════════════════════════════════════════════════

class WendlandC2Reconstructor:
    """Wendland C2 kernel weighted interpolation with spatial bucketing."""

    def __init__(self, query_radius_mm: float = 60.0):
        self.R = query_radius_mm

    @staticmethod
    def kernel(r: np.ndarray) -> np.ndarray:
        """Wendland C2: (1-r)^4 * (4r+1) for 0 <= r <= 1, else 0."""
        phi = np.zeros_like(r)
        mask = r <= 1.0
        phi[mask] = (1.0 - r[mask]) ** 4 * (4.0 * r[mask] + 1.0)
        return phi

    def reconstruct(
        self,
        grid_x: np.ndarray,
        grid_y: np.ndarray,
        cells: CellData,
        use_buckets: bool = True,
    ) -> Tuple[np.ndarray, float]:
        t0 = time.perf_counter()
        H, W = grid_x.shape
        field = np.zeros((H, W))

        if cells.n_cells == 0:
            return field, time.perf_counter() - t0

        if use_buckets and cells.n_cells > 10:
            field = self._reconstruct_bucketed(grid_x, grid_y, cells)
        else:
            field = self._reconstruct_bruteforce(grid_x, grid_y, cells)

        return field, time.perf_counter() - t0

    def _reconstruct_bruteforce(self, grid_x, grid_y, cells):
        H, W = grid_x.shape
        field = np.zeros((H, W))
        for iy in range(H):
            for ix in range(W):
                gx, gy = grid_x[iy, ix], grid_y[iy, ix]
                dists = np.sqrt(
                    (cells.positions[:, 0] - gx) ** 2
                    + (cells.positions[:, 1] - gy) ** 2
                )
                mask = dists <= self.R
                if np.any(mask):
                    d_norm = dists[mask] / self.R
                    w = self.kernel(d_norm)
                    numer = float(np.dot(cells.pressures[mask], w))
                    denom = float(np.sum(w))
                    if denom > 1e-12:
                        field[iy, ix] = (numer / denom) * min(1.0, denom)
        return field

    def _reconstruct_bucketed(self, grid_x, grid_y, cells):
        H, W = grid_x.shape
        field = np.zeros((H, W))
        bucket_size = self.R

        x_min, x_max = grid_x.min(), grid_x.max()
        y_min, y_max = grid_y.min(), grid_y.max()

        bx_count = max(1, int(np.ceil((x_max - x_min) / bucket_size)) + 1)
        by_count = max(1, int(np.ceil((y_max - y_min) / bucket_size)) + 1)

        buckets = [[] for _ in range(bx_count * by_count)]
        for ci in range(cells.n_cells):
            cx, cy = cells.positions[ci, 0], cells.positions[ci, 1]
            bx = int((cx - x_min) / bucket_size)
            by = int((cy - y_min) / bucket_size)
            bx = max(0, min(bx_count - 1, bx))
            by = max(0, min(by_count - 1, by))
            buckets[by * bx_count + bx].append(ci)

        for iy in range(H):
            for ix in range(W):
                gx, gy = grid_x[iy, ix], grid_y[iy, ix]
                bx = int((gx - x_min) / bucket_size)
                by = int((gy - y_min) / bucket_size)
                bx = max(0, min(bx_count - 1, bx))
                by = max(0, min(by_count - 1, by))

                numer = 0.0
                denom = 0.0
                for dby in (-1, 0, 1):
                    nby = by + dby
                    if nby < 0 or nby >= by_count:
                        continue
                    for dbx in (-1, 0, 1):
                        nbx = bx + dbx
                        if nbx < 0 or nbx >= bx_count:
                            continue
                        nb = nby * bx_count + nbx
                        for ci in buckets[nb]:
                            cx = cells.positions[ci, 0]
                            cy = cells.positions[ci, 1]
                            dx = gx - cx
                            dy = gy - cy
                            d = np.sqrt(dx * dx + dy * dy)
                            if d <= self.R:
                                w = self.kernel(d / self.R)
                                numer += cells.pressures[ci] * w
                                denom += w

                if denom > 1e-12:
                    field[iy, ix] = (numer / denom) * min(1.0, denom)
        return field


# ══════════════════════════════════════════════════════════════
# 2. Moving Least Squares (MLS) 局部曲面拟合
# ══════════════════════════════════════════════════════════════

class MLSReconstructor:
    """Moving Least Squares — 在每个顶点上用加权最小二乘拟合局部多项式."""

    def __init__(self, k_neighbors: int = 12, poly_order: int = 1):
        self.k = k_neighbors
        self.order = poly_order

    def reconstruct(
        self,
        grid_x: np.ndarray,
        grid_y: np.ndarray,
        cells: CellData,
    ) -> Tuple[np.ndarray, float]:
        t0 = time.perf_counter()
        H, W = grid_x.shape
        field = np.zeros((H, W))

        if cells.n_cells == 0:
            return field, time.perf_counter() - t0

        from scipy.spatial import KDTree
        tree = KDTree(cells.positions[:, :2])

        for iy in range(H):
            for ix in range(W):
                gx, gy = grid_x[iy, ix], grid_y[iy, ix]
                k = min(self.k, cells.n_cells)
                dists, idxs = tree.query([gx, gy], k=k)
                idxs = np.atleast_1d(idxs)
                dists = np.atleast_1d(dists)

                dx = cells.positions[idxs, 0] - gx
                dy = cells.positions[idxs, 1] - gy
                vals = cells.pressures[idxs]

                sigma = max(np.mean(dists) * 2.0, 1e-6)
                w = np.exp(-0.5 * (dists / sigma) ** 2)
                W_sqrt = np.sqrt(w)

                if self.order == 1:
                    A = np.column_stack([dx, dy, np.ones_like(dx)])
                else:
                    A = np.column_stack(
                        [dx ** 2, dy ** 2, dx * dy, dx, dy, np.ones_like(dx)]
                    )

                A_w = A * W_sqrt[:, np.newaxis]
                b_w = vals * W_sqrt

                try:
                    coeffs, _, _, _ = np.linalg.lstsq(A_w, b_w, rcond=None)
                    if self.order == 1:
                        field[iy, ix] = coeffs[2]
                    else:
                        field[iy, ix] = coeffs[5]
                except np.linalg.LinAlgError:
                    field[iy, ix] = float(np.mean(vals))

        return field, time.perf_counter() - t0


# ══════════════════════════════════════════════════════════════
# 3. Graph Laplacian 扩散
# ══════════════════════════════════════════════════════════════

class GraphLaplacianReconstructor:
    """Graph Laplacian 扩散 — 沿网格连通性做调和插值."""

    def __init__(self, connectivity: int = 4):
        if connectivity not in (4, 8):
            raise ValueError("connectivity must be 4 or 8")
        self.conn = connectivity

    def reconstruct(
        self,
        grid_x: np.ndarray,
        grid_y: np.ndarray,
        cells: CellData,
    ) -> Tuple[np.ndarray, float]:
        t0 = time.perf_counter()
        H, W = grid_x.shape
        N = H * W

        if cells.n_cells == 0:
            return np.zeros((H, W)), time.perf_counter() - t0

        from scipy import sparse
        from scipy.sparse.linalg import spsolve

        flat_x = grid_x.ravel()
        flat_y = grid_y.ravel()
        b = np.zeros(N)
        known_mask = np.zeros(N, dtype=bool)

        for ci in range(cells.n_cells):
            cx, cy = cells.positions[ci, 0], cells.positions[ci, 1]
            dists = np.sqrt((flat_x - cx) ** 2 + (flat_y - cy) ** 2)
            nearest_idx = int(np.argmin(dists))
            known_mask[nearest_idx] = True
            b[nearest_idx] = cells.pressures[ci]

        row = []
        col = []
        data = []

        offsets = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        if self.conn == 8:
            offsets += [(-1, -1), (-1, 1), (1, -1), (1, 1)]

        for iy in range(H):
            for ix in range(W):
                idx = iy * W + ix
                if known_mask[idx]:
                    row.append(idx)
                    col.append(idx)
                    data.append(1.0)
                else:
                    degree = 0
                    for dx, dy in offsets:
                        nx, ny = ix + dx, iy + dy
                        if 0 <= nx < W and 0 <= ny < H:
                            nidx = ny * W + nx
                            degree += 1
                            row.append(idx)
                            col.append(nidx)
                            data.append(-1.0)
                    row.append(idx)
                    col.append(idx)
                    data.append(float(degree))

        L = sparse.csr_matrix((data, (row, col)), shape=(N, N))
        x = spsolve(L, b)
        field = x.reshape(H, W)

        return field, time.perf_counter() - t0
