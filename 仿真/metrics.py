"""
评价指标模块
"""

import numpy as np
from scipy import ndimage


def rmse(reconstructed: np.ndarray, ground_truth: np.ndarray) -> float:
    mask = ground_truth > 0
    if mask.sum() == 0:
        return 0.0
    diff = reconstructed[mask] - ground_truth[mask]
    return float(np.sqrt(np.mean(diff ** 2)))


def mae(reconstructed: np.ndarray, ground_truth: np.ndarray) -> float:
    mask = ground_truth > 0
    if mask.sum() == 0:
        return 0.0
    return float(np.mean(np.abs(reconstructed[mask] - ground_truth[mask])))


def max_error(reconstructed: np.ndarray, ground_truth: np.ndarray) -> float:
    mask = ground_truth > 0
    if mask.sum() == 0:
        return 0.0
    return float(np.max(np.abs(reconstructed[mask] - ground_truth[mask])))


def local_peak_count(field: np.ndarray, threshold_ratio: float = 0.3) -> int:
    threshold = field.max() * threshold_ratio
    if threshold <= 0:
        return 0
    labels, n_labels = ndimage.label(field > threshold)
    return n_labels


def smoothness_measure(field: np.ndarray) -> float:
    grad_y, grad_x = np.gradient(field)
    grad_mag = np.sqrt(grad_x ** 2 + grad_y ** 2)
    return float(np.mean(grad_mag))


def coverage_score(field: np.ndarray, ground_truth: np.ndarray) -> float:
    gt_active = ground_truth > 0.01 * ground_truth.max()
    if gt_active.sum() == 0:
        return 1.0
    field_active = field > 0.01 * field.max()
    return float(field_active.sum() / gt_active.sum())


def edge_decay_rate(field: np.ndarray, border_width: int = 10) -> float:
    interior = field[border_width:-border_width, border_width:-border_width]
    if interior.size == 0:
        return 0.0
    interior_mean = float(np.mean(interior[interior > 0])) if np.any(interior > 0) else 0.0
    if interior_mean == 0:
        return 0.0
    border_vals = np.concatenate([
        field[:border_width, :].ravel(),
        field[-border_width:, :].ravel(),
        field[:, :border_width].ravel(),
        field[:, -border_width:].ravel(),
    ])
    border_mean = float(np.mean(border_vals[border_vals > 0])) if np.any(border_vals > 0) else 0.0
    return 1.0 - border_mean / interior_mean if interior_mean > 0 else 0.0
