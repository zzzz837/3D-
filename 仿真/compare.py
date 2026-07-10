"""
仿真入口 — 三种压力场重建算法横向对比

用法:
    python compare.py                          # 全部场景, 分辨率 200
    python compare.py --resolution 150         # 低分辨率快速验证
    python compare.py --scenario uniform_gaussian  # 只跑单个场景
    python compare.py --no-buckets             # Wendland 不用空间分桶 (测加速比)
"""

import os, sys, json, argparse
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from algorithms import WendlandC2Reconstructor, MLSReconstructor, GraphLaplacianReconstructor
from data_generator import generate_all_scenarios
from metrics import rmse, mae, max_error, local_peak_count, smoothness_measure, coverage_score, edge_decay_rate
from visualize import save_comparison_figure, save_summary_figure


OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def run_scenario(scenario, args):
    print(f"\n{'='*60}")
    print(f"Scenario: {scenario.name}")
    print(f"  {scenario.description}")
    print(f"  Cells: {scenario.cells.n_cells},  Grid: {scenario.grid_x.shape}")

    results = {}
    metrics = {}

    # ── 1. Wendland C2 ──
    print("  [1/3] Wendland C2 ... ", end="", flush=True)
    wendland = WendlandC2Reconstructor(query_radius_mm=60.0)
    field, elapsed = wendland.reconstruct(
        scenario.grid_x, scenario.grid_y, scenario.cells,
        use_buckets=not args.no_buckets,
    )
    results["Wendland"] = {"field": field, "elapsed": elapsed, "cells": scenario.cells}
    print(f"done ({elapsed*1000:.0f} ms)")

    # ── 2. MLS ──
    print("  [2/3] MLS (k=12) ... ", end="", flush=True)
    mls = MLSReconstructor(k_neighbors=12, poly_order=1)
    field, elapsed = mls.reconstruct(scenario.grid_x, scenario.grid_y, scenario.cells)
    results["MLS"] = {"field": field, "elapsed": elapsed, "cells": scenario.cells}
    print(f"done ({elapsed*1000:.0f} ms)")

    # ── 3. Graph Laplacian ──
    print("  [3/3] Graph Laplacian (4-conn) ... ", end="", flush=True)
    laplacian = GraphLaplacianReconstructor(connectivity=4)
    field, elapsed = laplacian.reconstruct(scenario.grid_x, scenario.grid_y, scenario.cells)
    results["Laplacian"] = {"field": field, "elapsed": elapsed, "cells": scenario.cells}
    print(f"done ({elapsed*1000:.0f} ms)")

    # ── Evaluate ──
    gt = scenario.ground_truth
    for name, res in results.items():
        f = res["field"]
        metrics[name] = {
            "rmse": rmse(f, gt),
            "mae": mae(f, gt),
            "max_err": max_error(f, gt),
            "local_peaks": local_peak_count(f),
            "smoothness": smoothness_measure(f),
            "coverage": coverage_score(f, gt),
            "edge_decay": edge_decay_rate(f),
            "runtime_ms": res["elapsed"] * 1000,
        }

    # ── Print summary ──
    print(f"\n  {'Method':<12} {'RMSE':>8} {'MAE':>8} {'Peaks':>6} {'Coverage':>9} {'EdgeDecay':>10} {'ms':>7}")
    print(f"  {'GroundTruth':<12} {'---':>8} {'---':>8} {local_peak_count(gt):>6}")
    for name in ["Wendland", "MLS", "Laplacian"]:
        m = metrics[name]
        print(f"  {name:<12} {m['rmse']:>8.2f} {m['mae']:>8.2f} {m['local_peaks']:>6} "
              f"{m['coverage']:>9.3f} {m['edge_decay']:>10.3f} {m['runtime_ms']:>7.0f}")

    return results, metrics


def main():
    parser = argparse.ArgumentParser(description="3D Pressure Reconstruction Simulation")
    parser.add_argument("--resolution", type=int, default=200,
                        help="Grid resolution (default: 200)")
    parser.add_argument("--scenario", type=str, default=None,
                        help="Run single scenario by name")
    parser.add_argument("--no-buckets", action="store_true",
                        help="Disable spatial bucketing in Wendland")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    scenarios = generate_all_scenarios(resolution=args.resolution, seed=42)
    if args.scenario:
        scenarios = [s for s in scenarios if s.name == args.scenario]
        if not scenarios:
            print(f"Unknown scenario: {args.scenario}")
            print(f"Available: {[s.name for s in generate_all_scenarios(resolution=args.resolution)]}")
            sys.exit(1)

    all_scenario_names = []
    all_metrics = []

    for scenario in scenarios:
        results, metrics_out = run_scenario(scenario, args)
        save_comparison_figure(
            scenario.name,
            scenario.grid_x, scenario.grid_y,
            scenario.ground_truth,
            results, metrics_out,
            OUT_DIR,
        )
        np.save(os.path.join(OUT_DIR, f"ground_truth_{scenario.name}.npy"), scenario.ground_truth)
        for name, res in results.items():
            np.save(os.path.join(OUT_DIR, f"result_{scenario.name}_{name}.npy"), res["field"])

        all_scenario_names.append(scenario.name)
        all_metrics.append(metrics_out)

        json_path = os.path.join(OUT_DIR, f"metrics_{scenario.name}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metrics_out, f, indent=2, ensure_ascii=False)

    # 全局汇总
    if len(all_scenario_names) > 1:
        save_summary_figure(all_scenario_names, all_metrics, OUT_DIR)

    # 汇总 CSV
    csv_path = os.path.join(OUT_DIR, "all_metrics.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        header = "scenario,method,rmse,mae,max_err,local_peaks,smoothness,coverage,edge_decay,runtime_ms\n"
        f.write(header)
        for sname, mdict in zip(all_scenario_names, all_metrics):
            for method, m in mdict.items():
                f.write(f"{sname},{method},{m['rmse']:.4f},{m['mae']:.4f},{m['max_err']:.4f},"
                        f"{m['local_peaks']},{m['smoothness']:.4f},{m['coverage']:.4f},"
                        f"{m['edge_decay']:.4f},{m['runtime_ms']:.1f}\n")

    print(f"\n{'='*60}")
    print(f"Done. Output: {OUT_DIR}")
    print(f"  PNG files: comparison_*.png, summary_comparison.png")
    print(f"  JSON:      metrics_*.json")
    print(f"  CSV:       all_metrics.csv")
    print(f"  NPY:       result_*.npy (ground_truth.npy)")


if __name__ == "__main__":
    main()
