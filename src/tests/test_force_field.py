"""
单元测试 — beta4 力场压力重建 (JS等效算法的Python实现)
测试范围: wendlandPhi, jetColor, 固定范围归一化, manual/simulated/real模式
"""
import math
import json
import pytest


# ============================
# JS等效算法实现
# ============================

def wendland_phi(r):
    """Wendland C2 紧支撑核函数: (1-r)^4 * (4r+1) for r<1, else 0"""
    if r >= 1.0:
        return 0.0
    return (1.0 - r) ** 4 * (4.0 * r + 1.0)


def jet_color(t):
    """Jet colormap: t in [0,1] -> (r,g,b) in [0,1]"""
    t = max(0.0, min(1.0, t))
    if t < 0.125:
        s = t / 0.125
        r, g, b = 0, 0, (128 + 127 * s) / 255
    elif t < 0.375:
        s = (t - 0.125) / 0.25
        r, g, b = 0, 255 * s / 255, 1.0
    elif t < 0.625:
        s = (t - 0.375) / 0.25
        r, g, b = 255 * s / 255, 1.0, (255 * (1 - s)) / 255
    elif t < 0.875:
        s = (t - 0.625) / 0.25
        r, g, b = 1.0, (255 * (1 - s)) / 255, 0
    else:
        s = (t - 0.875) / 0.125
        r, g, b = (255 * (1 - s * 0.5)) / 255, 0, 0
    return (r, g, b)


def normalize_fixed(value, p_min, p_max):
    """固定范围归一化: (value-min)/(max-min), clamped to [0,1]"""
    if p_max <= p_min:
        return 0.5
    return max(0.0, min(1.0, (value - p_min) / (p_max - p_min)))


def get_cell_pressures_manual(cells):
    """manual模式: 读取每个cell的pressure字段"""
    result = {}
    for c in cells:
        try:
            v = float(c.get("pressure", 0))
            result[c["id"]] = v if math.isfinite(v) else 0.0
        except (ValueError, TypeError):
            result[c["id"]] = 0.0
    return result


def get_cell_pressures_real(imported_field, cells):
    """real模式: 使用导入数据，不存在ID返回0"""
    result = {}
    for c in cells:
        result[c["id"]] = float(imported_field.get(str(c["id"]), 0))
    return result


def compute_sim_pressure(cells, t, p_min=0, p_max=100):
    """simulated模式: 每Cell独立动态pressure (正弦波)"""
    result = {}
    for c in cells:
        cid = c["id"]
        phase = (cid + 1) * 0.73
        freq = 0.25 + (cid % 7) * 0.12
        base = p_min + (p_max - p_min) * 0.2
        amp = (p_max - p_min) * 0.35
        result[cid] = base + amp * (0.5 + 0.5 * math.sin(t * freq + phase))
    return result


def wendland_reconstruct(vertices, cells, cell_pressures, field_radius=60.0):
    """Wendland 加权平均重建顶点压力 (简化版，用于测试逻辑正确性)"""
    result = {}
    for vi, v in enumerate(vertices):
        num, den = 0.0, 0.0
        for c in cells:
            cid = c["id"]
            dx = v[0] - c["x"]
            dy = v[1] - c["y"]
            dz = v[2] - c["z"]
            d = math.sqrt(dx*dx + dy*dy + dz*dz)
            if d > field_radius:
                continue
            r = d / field_radius
            w = wendland_phi(r)
            pressure = cell_pressures.get(cid, 0)
            num += pressure * w
            den += w
        if den <= 1e-6:
            result[vi] = None
        else:
            result[vi] = num / den
    return result


# ============================
# 测试用例
# ============================

class TestWendlandPhi:
    """wendlandPhi(r) 紧支撑性质测试"""

    def test_r_zero_returns_one(self):
        assert wendland_phi(0.0) == pytest.approx(1.0)

    def test_r_half(self):
        val = wendland_phi(0.5)
        expected = (0.5 ** 4) * (4 * 0.5 + 1)  # = 0.0625 * 3 = 0.1875
        assert val == pytest.approx(expected)

    def test_r_at_one_is_zero(self):
        assert wendland_phi(1.0) == pytest.approx(0.0, abs=1e-10)

    def test_r_above_one_is_zero(self):
        assert wendland_phi(1.5) == 0.0
        assert wendland_phi(10.0) == 0.0

    def test_monotonic_decreasing(self):
        """phi(r) should decrease as r increases in [0,1]"""
        vals = [wendland_phi(r) for r in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]]
        for i in range(len(vals) - 1):
            assert vals[i] >= vals[i+1] - 1e-10


class TestJetColor:
    """jetColor(t) 色彩映射测试"""

    def test_t_zero_is_blue(self):
        r, g, b = jet_color(0.0)
        assert r < 0.1
        assert g < 0.1
        assert b > 0.4  # 128/255 ≈ 0.502

    def test_t_half_is_yellow_green(self):
        """t=0.5 → yellow-green transition (r≈0.5,g≈1,b≈0.5)"""
        r, g, b = jet_color(0.5)
        assert g > 0.9  # green channel dominant
        assert r > 0.4 and b > 0.4  # red+blue at mid-level = yellow-green

    def test_t_one_is_dark_red(self):
        r, g, b = jet_color(1.0)
        assert r > 0.4  # 128/255
        assert g < 0.1
        assert b < 0.1

    def test_t_out_of_range_clamped(self):
        r1, g1, b1 = jet_color(-0.5)
        r2, g2, b2 = jet_color(1.5)
        assert (r1, g1, b1) == pytest.approx(jet_color(0.0))
        assert (r2, g2, b2) == pytest.approx(jet_color(1.0))

    def test_color_components_in_range(self):
        for t in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]:
            r, g, b = jet_color(t)
            assert 0.0 <= r <= 1.0
            assert 0.0 <= g <= 1.0
            assert 0.0 <= b <= 1.0


class TestFixedRangeNormalization:
    """固定范围归一化测试 (方案B)"""

    def test_min_maps_to_zero(self):
        assert normalize_fixed(0, 0, 100) == pytest.approx(0.0)

    def test_max_maps_to_one(self):
        assert normalize_fixed(100, 0, 100) == pytest.approx(1.0)

    def test_below_min_clamped(self):
        assert normalize_fixed(-10, 0, 100) == pytest.approx(0.0)

    def test_above_max_clamped(self):
        assert normalize_fixed(200, 0, 100) == pytest.approx(1.0)

    def test_wide_range_preserves_difference(self):
        """10 vs 100 with range [0,100]: normalized difference = 0.9"""
        t_a = normalize_fixed(10, 0, 100)
        t_b = normalize_fixed(100, 0, 100)
        assert t_b - t_a == pytest.approx(0.9)
        # Colors should be visually different
        ca = jet_color(t_a)
        cb = jet_color(t_b)
        diff = math.sqrt(sum((a - b)**2 for a, b in zip(ca, cb)))
        assert diff > 0.3, f"Color difference {diff} too small for 10 vs 100"

    def test_equal_range_returns_mid(self):
        assert normalize_fixed(50, 100, 100) == pytest.approx(0.5)


class TestManualPressureMode:
    """manual模式: pressure从cell读取"""

    def test_reads_pressure_field(self):
        cells = [
            {"id": 0, "x": 0, "y": 0, "z": 0, "pressure": 50},
            {"id": 1, "x": 1, "y": 1, "z": 1, "pressure": 100},
        ]
        p = get_cell_pressures_manual(cells)
        assert p[0] == 50
        assert p[1] == 100

    def test_label_not_used_as_pressure(self):
        """pressure and label are independent — label is NOT fallback"""
        cells = [
            {"id": 0, "x": 0, "y": 0, "z": 0, "pressure": 50, "label": "100"},
        ]
        p = get_cell_pressures_manual(cells)
        assert p[0] == 50  # NOT 100

    def test_missing_pressure_defaults_to_zero(self):
        cells = [{"id": 0, "x": 0, "y": 0, "z": 0}]
        p = get_cell_pressures_manual(cells)
        assert p[0] == 0

    def test_two_cells_visible_difference(self):
        """Cell A=10, Cell B=100 → reconstructed pressure near each cell differs"""
        cells = [
            {"id": 0, "x": 0, "y": 0, "z": 0, "pressure": 10},
            {"id": 1, "x": 100, "y": 0, "z": 0, "pressure": 100},
        ]
        pressures = get_cell_pressures_manual(cells)
        vertices = [(0, 0, 0), (100, 0, 0)]
        reconstructed = wendland_reconstruct(vertices, cells, pressures, field_radius=60)
        p0 = reconstructed[0]  # near cell 0 (pressure=10)
        p1 = reconstructed[1]  # near cell 1 (pressure=100)
        assert p1 is not None and p0 is not None
        assert p1 > p0, f"p1={p1} not greater than p0={p0}"
        # After fixed-range normalization [0,100], colors should differ visibly
        t0 = normalize_fixed(p0, 0, 100)
        t1 = normalize_fixed(p1, 0, 100)
        assert t1 > t0, f"Normalized t1={t1} should be > t0={t0}"
        diff = math.sqrt(sum((a-b)**2 for a, b in zip(jet_color(t0), jet_color(t1))))
        assert diff > 0.25, f"Color difference {diff} too small for 10 vs 100"


class TestRealImportMode:
    """real模式: JSON导入"""

    def test_basic_import(self):
        json_str = '{"cells":{"0":0.5,"1":0.8,"3":0.2}}'
        data = json.loads(json_str)
        imported = data.get("cells", data)

        cells = [{"id": 0}, {"id": 1}, {"id": 2}, {"id": 3}]
        p = get_cell_pressures_real(imported, cells)
        assert p[0] == 0.5
        assert p[1] == 0.8
        assert p[2] == 0.0  # not in JSON
        assert p[3] == 0.2

    def test_range_optional_parsing(self):
        json_str = '{"cells":{"0":50,"1":80},"range":[0,100]}'
        data = json.loads(json_str)
        imported = data.get("cells", data)
        range_val = data.get("range")
        assert range_val == [0, 100]
        cells = [{"id": 0}, {"id": 1}]
        p = get_cell_pressures_real(imported, cells)
        assert p[0] == 50
        assert p[1] == 80

    def test_missing_range_uses_defaults(self):
        json_str = '{"cells":{"0":10,"1":20}}'
        data = json.loads(json_str)
        range_val = data.get("range", None)
        assert range_val is None  # caller should use UI pressureMin/pressureMax


class TestSimulatedPressureMode:
    """simulated模式: 每Cell独立动态pressure"""

    def test_output_within_range(self):
        cells = [{"id": 0}, {"id": 1}, {"id": 5}]
        p = compute_sim_pressure(cells, t=1.0, p_min=0, p_max=100)
        for cid in [0, 1, 5]:
            assert 0 <= p[cid] <= 100, f"Cell {cid} pressure {p[cid]} out of range"

    def test_different_cells_have_different_pressures(self):
        """同期不同Cell应有不同压力值"""
        cells = [{"id": i} for i in range(10)]
        p = compute_sim_pressure(cells, t=5.0, p_min=0, p_max=100)
        values = list(p.values())
        # At least some cells should differ
        assert len(set(round(v, 1) for v in values)) > 1

    def test_pressure_changes_over_time(self):
        cells = [{"id": 0}, {"id": 1}]
        p1 = compute_sim_pressure(cells, t=0.0, p_min=0, p_max=100)
        p2 = compute_sim_pressure(cells, t=1.0, p_min=0, p_max=100)
        # At least one cell should change
        changed = any(abs(p1[cid] - p2[cid]) > 0.01 for cid in [0, 1])
        assert changed, "Pressure did not change over time"

    def test_static_when_no_time_change(self):
        cells = [{"id": 0}, {"id": 1}]
        p1 = compute_sim_pressure(cells, t=3.14, p_min=0, p_max=100)
        p2 = compute_sim_pressure(cells, t=3.14, p_min=0, p_max=100)
        for cid in [0, 1]:
            assert p1[cid] == pytest.approx(p2[cid])


class TestWendlandReconstruction:
    """Wendland 加权平均重建综合测试"""

    def test_isolated_cell_returns_own_pressure(self):
        """顶点正好在Cell中心，应返回该Cell的压力值"""
        cells = [{"id": 0, "x": 0, "y": 0, "z": 0, "pressure": 50}]
        pressures = {0: 50}
        vertices = [(0, 0, 0)]
        result = wendland_reconstruct(vertices, cells, pressures, field_radius=60)
        assert result[0] is not None
        assert result[0] == pytest.approx(50, rel=0.01)

    def test_vertex_far_from_all_cells_returns_none(self):
        """顶点在影响半径外 → None (灰色)"""
        cells = [{"id": 0, "x": 0, "y": 0, "z": 0, "pressure": 50}]
        pressures = {0: 50}
        vertices = [(200, 0, 0)]  # far away
        result = wendland_reconstruct(vertices, cells, pressures, field_radius=10)
        assert result[0] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
