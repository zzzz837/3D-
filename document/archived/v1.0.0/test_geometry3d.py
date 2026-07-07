"""测试 core.geometry3d — 三角面面积、法线、包围盒、点三角形测试"""

import numpy as np
import pytest

from src.core.geometry3d import (
    triangle_area,
    compute_normals,
    compute_bounding_box,
    is_point_in_triangle,
    perpendicular,
    build_tangent_basis,
    closest_point_on_triangle,
)


class TestTriangleArea:
    def test_right_triangle(self):
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([4.0, 0.0, 0.0])
        c = np.array([0.0, 3.0, 0.0])
        assert abs(triangle_area(a, b, c) - 6.0) < 1e-6


class TestComputeNormals:
    def test_xy_plane(self):
        v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float32)
        f = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int32)
        n = compute_normals(v, f)
        assert np.allclose(n[0], [0, 0, 1]) or np.allclose(n[0], [0, 0, -1])


class TestBoundingBox:
    def test_cube(self):
        v = np.array([[0, 0, 0], [10, 10, 10]], dtype=np.float32)
        mn, mx = compute_bounding_box(v)
        assert np.allclose(mn, [0, 0, 0])
        assert np.allclose(mx, [10, 10, 10])


class TestPointInTriangle:
    def test_inside(self):
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([10.0, 0.0, 0.0])
        c = np.array([5.0, 8.0, 0.0])
        assert is_point_in_triangle(np.array([5.0, 3.0, 0.0]), a, b, c)
        assert not is_point_in_triangle(np.array([15.0, 0.0, 0.0]), a, b, c)


class TestPerpendicular:
    def test_dot_product(self):
        v = np.array([0.5, 0.3, 0.8])
        p = perpendicular(v)
        assert abs(np.dot(v, p)) < 1e-6


class TestTangentBasis:
    def test_orthonormal(self):
        normal = np.array([0.1, 0.2, 0.96])
        normal = normal / np.linalg.norm(normal)
        u, v = build_tangent_basis(normal)
        assert abs(np.dot(normal, u)) < 1e-6
        assert abs(np.dot(normal, v)) < 1e-6
        assert abs(np.dot(u, v)) < 1e-6
        assert abs(np.linalg.norm(u) - 1.0) < 1e-6
        assert abs(np.linalg.norm(v) - 1.0) < 1e-6


class TestClosestPointOnTriangle:
    def test_on_triangle(self):
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        c = np.array([0.0, 1.0, 0.0])
        cp = closest_point_on_triangle(np.array([0.25, 0.25, 0.0]), a, b, c)
        assert np.allclose(cp, [0.25, 0.25, 0.0])

    def test_outside_edge(self):
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        c = np.array([0.0, 1.0, 0.0])
        cp = closest_point_on_triangle(np.array([2.0, 0.0, 0.0]), a, b, c)
        assert np.allclose(cp, [1.0, 0.0, 0.0])


class TestBasket:
    def test_land_unland(self):
        from src.core.basket import CellBasket3D
        basket = CellBasket3D(16)
        assert basket.next_id == 0
        basket.land(0)
        assert basket.next_id == 1
        basket.unland(0)
        assert basket.next_id == 0
