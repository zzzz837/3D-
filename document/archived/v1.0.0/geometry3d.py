"""3D 几何工具函数 — core 层纯 numpy，无 Qt 依赖"""

from typing import Tuple, Optional

import numpy as np


def triangle_area(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """计算三角形面积（标量）。"""
    return float(0.5 * np.linalg.norm(np.cross(b - a, c - a)))


def triangle_area_batch(v0: np.ndarray, v1: np.ndarray, v2: np.ndarray) -> np.ndarray:
    """批量计算三角面面积，返回 (M,) 数组。"""
    return 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v1), axis=1)


def compute_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """右手定则计算三角面法线 (M, 3)。"""
    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]
    normals = np.cross(v1 - v0, v2 - v0)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths < 1e-10] = 1.0
    return normals / lengths


def compute_bounding_box(vertices: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """返回 (bounds_min, bounds_max)，各 (3,) float32。空数组返回零包围盒。"""
    if len(vertices) == 0:
        return np.zeros(3, dtype=np.float32), np.zeros(3, dtype=np.float32)
    return vertices.min(axis=0).astype(np.float32), vertices.max(axis=0).astype(np.float32)


def is_point_in_triangle(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> bool:
    """重心坐标法判断点是否在三角形内（含边界）。"""
    v0 = c - a
    v1 = b - a
    v2 = p - a
    dot00 = np.dot(v0, v0)
    dot01 = np.dot(v0, v1)
    dot02 = np.dot(v0, v2)
    dot11 = np.dot(v1, v1)
    dot12 = np.dot(v1, v2)
    inv_denom = 1.0 / (dot00 * dot11 - dot01 * dot01 + 1e-12)
    u = (dot11 * dot02 - dot01 * dot12) * inv_denom
    v = (dot00 * dot12 - dot01 * dot02) * inv_denom
    return (u >= -1e-8) and (v >= -1e-8) and (u + v <= 1.0 + 1e-8)


def perpendicular(v: np.ndarray) -> np.ndarray:
    """返回任意与 v 垂直的单位向量（用于构造切平面基）。"""
    if abs(v[0]) < abs(v[1]):
        u = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    else:
        u = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    perp = np.cross(v, u)
    return perp / np.linalg.norm(perp)


def build_tangent_basis(normal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """由法向量构造切平面正交基 (u, v)，均单位向量"""
    u = perpendicular(normal)
    v = np.cross(normal, u)
    return u, v


def closest_point_on_triangle(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """求点 p 到三角形 (a,b,c) 的最近点（单位化投影）。"""
    ab = b - a
    ac = c - a
    ap = p - a
    d1 = np.dot(ab, ap)
    d2 = np.dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a.copy()
    bp = p - b
    d3 = np.dot(ab, bp)
    d4 = np.dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return b.copy()
    cp_vec = p - c
    d5 = np.dot(ab, cp_vec)
    d6 = np.dot(ac, cp_vec)
    if d6 >= 0.0 and d5 <= d6:
        return c.copy()
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        t = d1 / (d1 - d3 + 1e-12)
        return a + t * ab
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        t = d2 / (d2 - d6 + 1e-12)
        return a + t * ac
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        t = (d4 - d3) / ((d4 - d3) + (d5 - d6) + 1e-12)
        return b + t * (c - b)
    denom = 1.0 / (va + vb + vc + 1e-12)
    u = vb * denom
    v = vc * denom
    return a + ab * u + ac * v


def unify_normals(vertices: np.ndarray, faces: np.ndarray, normals: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """基于连通分量分析将所有法线翻转到一致朝外。"""
    adj = _build_face_adjacency(faces)
    visited = set()
    for seed in range(len(faces)):
        if seed in visited:
            continue
        queue = [seed]
        visited.add(seed)
        while queue:
            f_idx = queue.pop(0)
            for neighbor in adj.get(f_idx, set()):
                if neighbor in visited:
                    continue
                if np.dot(normals[f_idx], normals[neighbor]) < 0:
                    normals[neighbor] *= -1
                    faces[neighbor] = faces[neighbor][[0, 2, 1]]
                queue.append(neighbor)
                visited.add(neighbor)
    return faces, normals


def _build_face_adjacency(faces: np.ndarray) -> dict:
    """构建面邻接图（共享边的面）。"""
    edge_to_faces = {}
    adj = {i: set() for i in range(len(faces))}
    for fi, face in enumerate(faces):
        for ei in range(3):
            e = tuple(sorted([int(face[ei]), int(face[(ei + 1) % 3])]))
            if e in edge_to_faces:
                for fj in edge_to_faces[e]:
                    adj[fi].add(fj)
                    adj[fj].add(fi)
                edge_to_faces[e].append(fi)
            else:
                edge_to_faces[e] = [fi]
    return adj
