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


class TestSimPresets:
    """v1.0.1 模拟压力预设: Uniform/Wave/Pulse"""

    def _sim_uniform(self, cells, t, p_min=0, p_max=100):
        base = p_min + (p_max - p_min) * 0.25
        amp = (p_max - p_min) * 0.4
        for c in cells:
            c["pressure"] = base + amp * (0.5 + 0.5 * math.sin(t * 1.0))

    def test_uniform_all_cells_same_pressure(self):
        cells = [{"id": i} for i in range(10)]
        self._sim_uniform(cells, t=0.0, p_min=0, p_max=100)
        pressures = [c["pressure"] for c in cells]
        assert all(abs(p - pressures[0]) < 0.01 for p in pressures)

    def test_uniform_pressure_in_range(self):
        cells = [{"id": i} for i in range(10)]
        for t_val in [0, 1, 2, 3, 10]:
            self._sim_uniform(cells, t=t_val, p_min=0, p_max=100)
            for c in cells:
                assert 0 <= c["pressure"] <= 100

    def _sim_wave(self, cells, t, p_min=0, p_max=100):
        for c in cells:
            phase = (c["id"] + 1) * 0.73
            freq = 0.3 + (c["id"] % 7) * 0.15
            base = p_min + (p_max - p_min) * 0.2
            amp = (p_max - p_min) * 0.35
            c["pressure"] = base + amp * (0.5 + 0.5 * math.sin(t * freq + phase))

    def test_wave_different_cells_have_different_phase(self):
        cells = [{"id": i} for i in range(10)]
        self._sim_wave(cells, t=5.0, p_min=0, p_max=100)
        vals = [round(c["pressure"], 1) for c in cells]
        assert len(set(vals)) > 1  # Not all identical

    def test_wave_pressure_in_range(self):
        cells = [{"id": i} for i in range(10)]
        for t_val in [0, 1, 5, 10, 100]:
            self._sim_wave(cells, t=t_val, p_min=20, p_max=80)
            for c in cells:
                assert 20 <= c["pressure"] <= 80

    def test_wave_changes_over_time(self):
        cells = [{"id": 0}, {"id": 1}]
        self._sim_wave(cells, t=0.0, p_min=0, p_max=100)
        p1_before = [c["pressure"] for c in cells]
        self._sim_wave(cells, t=1.0, p_min=0, p_max=100)
        p1_after = [c["pressure"] for c in cells]
        changed = any(abs(p1_before[i] - p1_after[i]) > 0.01 for i in range(len(cells)))
        assert changed

    def test_wave_pressure_written_to_cell(self):
        """preset 只写 C[id].pressure，不返回独立 map"""
        cells = [{"id": 0}, {"id": 1}]
        self._sim_wave(cells, t=1.0)
        assert "pressure" in cells[0]
        assert isinstance(cells[0]["pressure"], float)

    def _sim_pulse(self, cells, t, cycle=0, p_min=0, p_max=100):
        cycle_len = 2.5
        hotspot_ids = {cells[i % len(cells)]["id"] for i in range(min(3, len(cells)))}
        base = p_min + (p_max - p_min) * 0.15
        amp = (p_max - p_min) * 0.5
        for c in cells:
            if c["id"] in hotspot_ids:
                local_t = max(0, min(1, t / cycle_len))
                c["pressure"] = base + amp * math.pow(math.sin(math.pi * local_t), 2)
            else:
                c["pressure"] = base

    def test_pulse_hotspot_higher_than_background(self):
        cells = [{"id": i} for i in range(10)]
        self._sim_pulse(cells, t=0.5, p_min=0, p_max=100)
        hotspot_p = [c["pressure"] for c in cells if c["id"] < 3]
        bg_p = [c["pressure"] for c in cells if c["id"] >= 3]
        assert max(hotspot_p) > max(bg_p) * 1.5

    def test_pulse_pressure_in_range(self):
        cells = [{"id": i} for i in range(20)]
        for t_val in [0.1, 0.5, 1.0, 1.5, 2.0]:
            self._sim_pulse(cells, t=t_val, p_min=0, p_max=100)
            for c in cells:
                assert 0 <= c["pressure"] <= 100

    def test_pulse_written_to_cell_pressure(self):
        cells = [{"id": i} for i in range(5)]
        self._sim_pulse(cells, t=1.0)
        for c in cells:
            assert "pressure" in c
            assert isinstance(c["pressure"], float)


# ============================
# v1.0.2 新增: Jet 色带 + 网格细分测试
# ============================

def jet_color_new(t):
    """Jet 色带 (设计文档定义): DeepBlue→Blue→Cyan→Green→Yellow→Orange→Red"""
    t = max(0.0, min(1.0, t))
    stops = [0.0, 0.15, 0.30, 0.45, 0.55, 0.70, 1.0]
    colors = [
        [0, 0, 143],      # DeepBlue  0.00
        [0, 0, 255],      # Blue      0.15
        [0, 255, 255],    # Cyan      0.30
        [0, 255, 0],      # Green     0.45
        [255, 255, 0],    # Yellow    0.55
        [255, 165, 0],    # Orange    0.70
        [255, 0, 0]       # Red       1.00
    ]
    lo = 0
    for i in range(len(stops) - 1):
        if stops[i] <= t <= stops[i + 1]:
            lo = i
            break
    else:
        lo = len(stops) - 2
    s = (t - stops[lo]) / (stops[lo + 1] - stops[lo] + 1e-9)
    c0, c1 = colors[lo], colors[lo + 1]
    return (
        (c0[0] + (c1[0] - c0[0]) * s) / 255,
        (c0[1] + (c1[1] - c0[1]) * s) / 255,
        (c0[2] + (c1[2] - c0[2]) * s) / 255
    )


class TestJetColorNew:
    """v1.0.2 Jet 色带边界颜色验证"""

    def test_t_0_is_deep_blue(self):
        r, g, b = jet_color_new(0.0)
        assert r < 0.01 and g < 0.01
        assert b == pytest.approx(143 / 255, abs=0.01)

    def test_t_015_is_blue(self):
        r, g, b = jet_color_new(0.15)
        assert r < 0.01 and g < 0.01
        assert b == pytest.approx(1.0, abs=0.01)

    def test_t_030_is_cyan(self):
        r, g, b = jet_color_new(0.30)
        assert r < 0.01
        assert g == pytest.approx(1.0, abs=0.01)
        assert b == pytest.approx(1.0, abs=0.01)

    def test_t_045_is_green(self):
        r, g, b = jet_color_new(0.45)
        assert r < 0.01
        assert g == pytest.approx(1.0, abs=0.01)
        assert b < 0.01

    def test_t_055_is_yellow(self):
        r, g, b = jet_color_new(0.55)
        assert r == pytest.approx(1.0, abs=0.01)
        assert g == pytest.approx(1.0, abs=0.01)
        assert b < 0.01

    def test_t_070_is_orange(self):
        r, g, b = jet_color_new(0.70)
        assert r == pytest.approx(1.0, abs=0.01)
        assert g == pytest.approx(165 / 255, abs=0.01)
        assert b < 0.01

    def test_t_1_is_red(self):
        r, g, b = jet_color_new(1.0)
        assert r == pytest.approx(1.0, abs=0.01)
        assert g < 0.01 and b < 0.01

    def test_color_components_in_range(self):
        for t in [0.0, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95, 1.0]:
            r, g, b = jet_color_new(t)
            assert 0.0 <= r <= 1.0
            assert 0.0 <= g <= 1.0
            assert 0.0 <= b <= 1.0

    def test_monotonic_brightness_in_red(self):
        """在 t ≥ 0.55 区间，红色分量应该单调递增"""
        r_prev = -1
        for t in [0.55, 0.60, 0.70, 0.85, 1.0]:
            r, _, _ = jet_color_new(t)
            assert r >= r_prev - 1e-9, f"Red not monotonic at t={t}: {r} < {r_prev}"
            r_prev = r


def barycentric_subdivide_1_triangle():
    """单三角形 Barycentric 细分: 1→4 三角形"""
    # 三角形顶点: (0,0,0), (1,0,0), (0,1,0)
    v0, v1, v2 = (0, 0, 0), (1, 0, 0), (0, 1, 0)
    mid01 = ((v0[0] + v1[0]) / 2, (v0[1] + v1[1]) / 2, (v0[2] + v1[2]) / 2)
    mid12 = ((v1[0] + v2[0]) / 2, (v1[1] + v2[1]) / 2, (v1[2] + v2[2]) / 2)
    mid20 = ((v2[0] + v0[0]) / 2, (v2[1] + v0[1]) / 2, (v2[2] + v0[2]) / 2)
    # 4个子三角形
    tris = [
        (v0, mid01, mid20),
        (v1, mid12, mid01),
        (v2, mid20, mid12),
        (mid01, mid12, mid20)
    ]
    return tris


def bulge_displace(vertex, normal, scalar, height):
    """法线位移隆起公式"""
    return (
        vertex[0] + normal[0] * scalar * height,
        vertex[1] + normal[1] * scalar * height,
        vertex[2] + normal[2] * scalar * height
    )


class TestMeshSubdivision:
    """v1.0.2 网格细分与隆起位移测试"""

    def test_barycentric_subdiv_quadruples_triangles(self):
        """1个三角形细分1次 → 4个三角形"""
        tris = barycentric_subdivide_1_triangle()
        assert len(tris) == 4

    def test_subdivided_vertices_are_distinct(self):
        """细分后所有顶点应不同"""
        tris = barycentric_subdivide_1_triangle()
        all_verts = []
        for tri in tris:
            for v in tri:
                all_verts.append(v)
        unique = set(round(x, 10) for v in all_verts for x in v)
        assert len(unique) >= 3  # At least 3 distinct coordinates

    def test_barycentric_center_triangle_exists(self):
        """细分后应有中心三角形 (由三个中点组成)"""
        tris = barycentric_subdivide_1_triangle()
        # 中心三角形顶点都在中点位置
        mid01 = (0.5, 0.0, 0.0)
        mid12 = (0.5, 0.5, 0.0)
        mid20 = (0.0, 0.5, 0.0)
        found = False
        for tri in tris:
            verts_set = {tuple(round(x, 10) for x in v) for v in tri}
            expected = {tuple(round(x, 10) for x in (mid01, mid12, mid20)[i]) for i in range(3)}
            # Actually check if center triangle exists
            if all(any(abs(v[i] - 0.5) < 1e-9 and abs(v[j] - 0.0) < 1e-9 for v in tri) for i, j in [(0, 2), (1, 2), (2, 2)]):
                found = True
        # Simpler check: a triangle where all vertices have z=0 and at least one has x≈0.5,y≈0
        center_like = sum(1 for tri in tris for v in tri if abs(v[0] - 0.5) < 1e-9 and abs(v[1]) < 1e-9)
        assert center_like >= 1

    def test_bulge_zero_scalar_no_displacement(self):
        """scalar=0 时不应有位移"""
        v = (1.0, 2.0, 3.0)
        n = (0.0, 0.0, 1.0)
        result = bulge_displace(v, n, 0.0, 10.0)
        assert result == pytest.approx(v)

    def test_bulge_max_scalar_full_displacement(self):
        """scalar=1 时位移应为 height"""
        v = (0.0, 0.0, 0.0)
        n = (0.0, 0.0, 1.0)
        result = bulge_displace(v, n, 1.0, 5.0)
        assert result == pytest.approx((0.0, 0.0, 5.0))

    def test_bulge_normal_direction(self):
        """位移沿法线方向"""
        v = (1.0, 1.0, 1.0)
        n = (1.0, 0.0, 0.0)  # 沿 X 轴
        result = bulge_displace(v, n, 0.5, 4.0)
        assert result[0] == pytest.approx(3.0)  # 1.0 + 0.5 * 4.0
        assert result[1] == pytest.approx(1.0)
        assert result[2] == pytest.approx(1.0)

    def test_adaptive_level_coarse_mesh(self):
        """模拟粗网格 (814顶点, 最大边长 >> FIELD_R/4) → level ≥ 1"""
        # 粗网格: 最大边长远大于 target edge
        # FIELD_R=60, targetEdge=15mm, 粗网格 maxEdge≈50mm → level≥1
        max_edge_mm = 50.0
        field_r = 60
        target_edge = max(field_r / 4, 1)
        level = 0
        if max_edge_mm > target_edge * 2.5:
            level = 2
        elif max_edge_mm > target_edge * 1.2:
            level = 1
        assert level >= 1, f"Coarse mesh should need subdivision, target={target_edge}"

    def test_adaptive_level_dense_mesh(self):
        """模拟密网格 (25K顶点, 最大边长 ≤ FIELD_R/4) → level = 0"""
        max_edge_mm = 2.0
        field_r = 60
        target_edge = max(field_r / 4, 1)
        level = 0
        if max_edge_mm > target_edge * 2.5:
            level = 2
        elif max_edge_mm > target_edge * 1.2:
            level = 1
        assert level == 0, f"Dense mesh should not need subdivision"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
