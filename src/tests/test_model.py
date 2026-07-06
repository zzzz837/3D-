"""测试 core.model — CellDefinition3D, SurfaceModel, DeviceLayoutProfile3D"""

import tempfile
import numpy as np
import pytest

from src.core.model import CellDefinition3D, SurfaceModel, DeviceLayoutProfile3D


class TestCellDefinition3D:
    def test_create_square(self):
        center = np.array([10.0, 20.0, 30.0])
        normal = np.array([0.0, 0.0, 1.0])
        cell = CellDefinition3D.create_square(center, normal, side_mm=15.0)
        assert cell.width_mm == 15.0
        assert cell.height_mm == 15.0
        assert cell.rotation_deg == 0.0

    def test_side_mm_property(self):
        cell = CellDefinition3D(0, np.zeros(3), np.array([0, 0, 1]), 12.0, 12.0)
        assert cell.side_mm == 12.0

    def test_to_dict_from_dict_roundtrip(self):
        cell = CellDefinition3D(5, np.array([1, 2, 3]), np.array([0, 1, 0]), 10.0, 10.0, 45.0)
        d = cell.to_dict()
        cell2 = CellDefinition3D.from_dict(d)
        assert cell2.cell_id == 5
        assert cell2.width_mm == 10.0
        assert cell2.height_mm == 10.0
        assert cell2.rotation_deg == 45.0
        assert np.allclose(cell2.center_3d, [1, 2, 3])

    def test_invalid_cell_id(self):
        with pytest.raises(ValueError):
            CellDefinition3D(-2, np.zeros(3), np.array([0, 0, 1]))

    def test_invalid_dimension(self):
        with pytest.raises(ValueError):
            CellDefinition3D(0, np.zeros(3), np.array([0, 0, 1]), 0.0, 0.0)

    def test_copy_independence(self):
        cell = CellDefinition3D(1, np.array([1, 2, 3]), np.array([0, 1, 0]), 10.0, 10.0)
        c2 = cell.copy()
        c2.center_3d[0] = 99.0
        assert cell.center_3d[0] == 1.0


class TestSurfaceModel:
    def test_basic(self):
        v = np.random.rand(100, 3).astype(np.float32)
        f = np.random.randint(0, 100, (50, 3)).astype(np.int32)
        sm = SurfaceModel(v, f, format="stl")
        assert sm.face_count == 50
        assert sm.format == "stl"

    def test_bounds(self):
        v = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [10, 10, 0]], dtype=np.float32)
        f = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int32)
        sm = SurfaceModel(v, f)
        assert np.allclose(sm.bounds_min, [0, 0, 0])
        assert np.allclose(sm.bounds_max, [10, 10, 0])


class TestDeviceLayoutProfile3D:
    def test_empty_profile(self):
        p = DeviceLayoutProfile3D(device_model="Glove", total_points=32)
        assert p.version == "2.0"
        assert p.total_points == 32
        assert len(p.cells) == 0

    def test_add_remove_cell(self):
        p = DeviceLayoutProfile3D(total_points=200)
        cell = CellDefinition3D(0, np.zeros(3), np.array([0, 0, 1]))
        p.add_cell(cell)
        assert len(p.cells) == 1
        assert p.is_dirty
        p.remove_cell(0)
        assert len(p.cells) == 0

    def test_duplicate_cell_id(self):
        p = DeviceLayoutProfile3D(total_points=200)
        p.add_cell(CellDefinition3D(0, np.zeros(3), np.array([0, 0, 1])))
        with pytest.raises(ValueError):
            p.add_cell(CellDefinition3D(0, np.ones(3), np.array([0, 1, 0])))

    def test_json_roundtrip(self):
        v = np.random.rand(10, 3).astype(np.float32)
        f = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int32)
        sm = SurfaceModel(v, f, raw_data=b"test")
        p = DeviceLayoutProfile3D(
            device_model="Test",
            total_points=16,
            surface_model=sm,
        )
        p.add_cell(CellDefinition3D(0, np.array([1, 2, 3]), np.array([0, 0, 1]), 10.0, 10.0))

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w+", delete=False) as tmp:
            path = tmp.name
        p.save_json(path)

        p2 = DeviceLayoutProfile3D.load_json(path)
        assert p2.device_model == "Test"
        assert p2.total_points == 16
        assert len(p2.cells) == 1
        assert p2.cells[0].cell_id == 0
        assert p2.cells[0].width_mm == 10.0

    def test_dirty_flag(self):
        p = DeviceLayoutProfile3D()
        assert not p.is_dirty
        p.add_cell(CellDefinition3D(0, np.zeros(3), np.array([0, 0, 1])))
        assert p.is_dirty
        p.mark_clean()
        assert not p.is_dirty
