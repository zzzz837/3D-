"""
可视化模块 — matplotlib 对比图
"""

import os
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import ScalarFormatter


JET_COLORS = [
    (0.000, (0, 0, 0.5)),
    (0.125, (0, 0, 1)),
    (0.375, (0, 1, 1)),
    (0.625, (1, 1, 0)),
    (0.875, (1, 0, 0)),
    (1.000, (0.5, 0, 0)),
]
JET_CMAP = LinearSegmentedColormap.from_list("jet_sim", JET_COLORS)


def save_comparison_figure(
    scenario_name,
    grid_x, grid_y,
    ground_truth,
    results,
    metrics,
    out_dir,
):
    """为单个场景生成完整对比图."""
    n_methods = len(results)
    fig, axes = plt.subplots(
        2 + n_methods, 2,
        figsize=(12, 4 + 3 * n_methods),
        gridspec_kw={"width_ratios": [1, 1]},
    )
    fig.suptitle(f"Scenario: {scenario_name}", fontsize=13, fontweight="bold")

    vmin = ground_truth.min()
    vmax = ground_truth.max()

    # Row 0: Ground truth + Cell positions
    _plot_field(axes[0, 0], grid_x, grid_y, ground_truth,
                "Ground Truth", vmin, vmax, cmap=JET_CMAP)
    _plot_field(axes[0, 1], grid_x, grid_y, ground_truth,
                "Cell Positions", vmin, vmax, cmap=JET_CMAP)
    # 取第一个 result 的 cells 画散点
    first_name = list(results.keys())[0]
    cells = results[first_name]["cells"]
    axes[0, 1].scatter(
        cells.positions[:, 0], cells.positions[:, 1],
        c=cells.pressures, cmap=JET_CMAP, s=12, edgecolors="k",
        linewidths=0.5, vmin=vmin, vmax=vmax,
    )

    # Rows 1..n: each method: reconstructed + error
    for i, (name, res) in enumerate(results.items()):
        row = 1 + i
        field = res["field"]
        elapsed = res["elapsed"]
        m = metrics.get(name, {})

        _plot_field(axes[row, 0], grid_x, grid_y, field,
                    f"{name}  ({elapsed * 1000:.0f} ms)", vmin, vmax, cmap=JET_CMAP)

        error = field - ground_truth
        _plot_field(axes[row, 1], grid_x, grid_y, error,
                    f"Error  |  RMSE={m.get('rmse', 0):.2f}  MAE={m.get('mae', 0):.2f}",
                    -vmax * 0.5, vmax * 0.5, cmap="coolwarm")

    # Row n+1: metric summary bar
    row = 1 + n_methods
    ax_bar = axes[row, 0]
    method_names = list(results.keys())
    labels = ["RMSE", "MAE", "Peaks", "Runtime(ms)"]
    x_vals = []
    y_vals = []
    colors = []
    bar_labels = []
    for j, mn in enumerate(method_names):
        m = metrics.get(mn, {})
        rmse_val = m.get("rmse", 0)
        mae_val = m.get("mae", 0)
        peaks = m.get("local_peaks", 0)
        rt = m.get("runtime_ms", 0)
        vals = [rmse_val, mae_val, peaks * 5, rt]
        for k, (lab, val) in enumerate(zip(labels, vals)):
            x_vals.append(j + k * 0.2)
            y_vals.append(val)
            colors.append(f"C{k}")
            bar_labels.append(lab)
    bar_width = 0.18
    xs = np.arange(len(method_names))
    for k, (lab, col) in enumerate(
        zip(["RMSE", "MAE", "Peaks*5", "ms"], ["C0", "C1", "C2", "C3"])
    ):
        vals_k = [
            (metrics.get(mn, {}).get(
                {"RMSE": "rmse", "MAE": "mae", "Peaks*5": "local_peaks", "ms": "runtime_ms"}[lab],
                0
            ) * (5 if lab == "Peaks*5" else 1))
            for mn in method_names
        ]
        ax_bar.bar(xs + k * bar_width, vals_k, bar_width, label=lab, color=col)
    ax_bar.set_xticks(xs + bar_width * 1.5)
    ax_bar.set_xticklabels(method_names)
    ax_bar.legend(fontsize=7)
    ax_bar.set_title("Metrics Comparison")

    # Row n+1, col 1: runtime bar chart
    ax_rt = axes[row, 1]
    times = [metrics.get(mn, {}).get("runtime_ms", 0) for mn in method_names]
    bars_rt = ax_rt.bar(method_names, times, color=["C0", "C1", "C2"])
    ax_rt.set_title("Runtime (ms)")
    ax_rt.set_ylabel("ms")
    for b, t in zip(bars_rt, times):
        ax_rt.text(b.get_x() + b.get_width() / 2, b.get_height() + max(times) * 0.02,
                   f"{t:.0f}", ha="center", fontsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    path = os.path.join(out_dir, f"comparison_{scenario_name}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def save_summary_figure(all_scenario_names, all_metrics, out_dir):
    """生成全局汇总图: 各方法在各场景下的 RMSE / Runtime 对比."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Cross-Scenario Summary", fontsize=13, fontweight="bold")

    method_names = list(all_metrics[0].keys())
    n_scenarios = len(all_scenario_names)
    width = 0.25
    xs = np.arange(n_scenarios)

    for k, (metric_key, title, ax_idx) in enumerate(
        [("rmse", "RMSE", 0), ("runtime_ms", "Runtime (ms)", 1)]
    ):
        ax = axes[ax_idx]
        for j, mn in enumerate(method_names):
            vals = [all_metrics[i].get(mn, {}).get(metric_key, 0) for i in range(n_scenarios)]
            ax.bar(xs + j * width, vals, width, label=mn)
        ax.set_xticks(xs + width)
        ax.set_xticklabels(all_scenario_names, rotation=20, ha="right", fontsize=8)
        ax.set_title(title)
        ax.legend(fontsize=8)

    plt.tight_layout()
    path = os.path.join(out_dir, "summary_comparison.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_field(ax, grid_x, grid_y, data, title, vmin, vmax, cmap):
    im = ax.pcolormesh(grid_x, grid_y, data, shading="auto",
                       cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_title(title, fontsize=9)
    ax.set_aspect("equal")
    plt.colorbar(im, ax=ax, fraction=0.046)


def save_raw_npy(results_dict, out_dir):
    """保存重建结果为 .npy 文件, 方便 MATLAB 或外部工具读取."""
    for name, result in results_dict.items():
        path = os.path.join(out_dir, f"result_{name}.npy")
        np.save(path, result["field"])
    return out_dir
