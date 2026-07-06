"""
3D 模型导入管线 — STL ASCII / Binary 解析 + 后处理

依赖: core.model.SurfaceModel, core.geometry3d
"""

import struct
from pathlib import Path
from typing import Tuple

import numpy as np

from ..core.model import SurfaceModel
from ..core.geometry3d import compute_normals, compute_bounding_box, unify_normals
from ..core.exceptions import ModelImportError

MAX_FACE_COUNT = 2_000_000  # 放宽到 200 万以兼容手套模型（~150 万面）


def import_model(filepath: str) -> SurfaceModel:
    """统一入口：自动检测 STL 格式 → 解析 → 后处理 → SurfaceModel。"""
    path = Path(filepath)
    if not path.exists():
        raise ModelImportError(f"File not found: {filepath}")

    ext = path.suffix.lower()
    data = path.read_bytes()

    if ext != ".stl":
        raise ModelImportError(f"Unsupported format: {ext} (Stage1 supports .stl only)")

    # STL 二进制检测：80 字节头 + 4 字节面数 → 文件大小匹配
    try:
        model = _parse_stl_binary(data)
    except Exception:
        model = _parse_stl_ascii(data)

    if model.vertices.size == 0:
        raise ModelImportError("Model contains no vertices")
    if model.faces.size == 0:
        raise ModelImportError("Model contains no faces")
    if not np.all(np.isfinite(model.vertices)):
        raise ModelImportError("Model contains NaN/Inf vertices")
    if model.face_count > MAX_FACE_COUNT:
        raise ModelImportError(
            f"Model face count ({model.face_count}) exceeds limit ({MAX_FACE_COUNT}). "
            f"Please simplify the model before importing."
        )

    # 后处理
    model.normals = compute_normals(model.vertices, model.faces)
    model.faces, model.normals = unify_normals(model.vertices, model.faces, model.normals)
    model._update_bounds()
    model.raw_data = data

    return model


def _detect_stl_binary(data: bytes) -> bool:
    """检测是否为 STL binary 格式。"""
    if len(data) < 84:
        return False
    try:
        face_count = struct.unpack_from("<I", data, 80)[0]
        return 84 + face_count * 50 == len(data)
    except Exception:
        return False


def _parse_stl_binary(data: bytes) -> SurfaceModel:
    """解析 STL binary 格式。

    文件结构: 80 bytes 头 + 4 bytes uint32 面数 + M × 50 bytes
    每面: 12 bytes float32×3 法向量 + 36 bytes float32×3×3 顶点 + 2 bytes uint16 属性
    """
    offset = 80
    face_count = struct.unpack_from("<I", data, offset)[0]
    offset += 4

    total_vertices = face_count * 3
    vertices_list = np.empty((total_vertices, 3), dtype=np.float32)

    for i in range(face_count):
        offset += 12  # 跳法线
        for j in range(3):
            x, y, z = struct.unpack_from("<3f", data, offset)
            vertices_list[i * 3 + j] = [x, y, z]
            offset += 12
        offset += 2  # 跳属性

    faces = np.arange(total_vertices, dtype=np.int32).reshape(-1, 3)

    return SurfaceModel(vertices=vertices_list, faces=faces, format="stl")


def _parse_stl_ascii(data: bytes) -> SurfaceModel:
    """解析 STL ASCII 格式。

    solid name
      facet normal nx ny nz
        outer loop
          vertex x y z
          vertex x y z
          vertex x y z
        endloop
      endfacet
    endsolid name
    """
    text = data.decode("utf-8", errors="replace")
    vertices_list = []
    face_verts: list = []
    targets_per_face = 3

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("solid") or stripped.startswith("endsolid"):
            continue
        if stripped.startswith("facet normal") or stripped.startswith("outer loop") or stripped.startswith("endloop") or stripped.startswith("endfacet"):
            continue
        if stripped.startswith("vertex"):
            parts = stripped.split()
            if len(parts) >= 4:
                face_verts.append([float(parts[-3]), float(parts[-2]), float(parts[-1])])
            if len(face_verts) == targets_per_face:
                vertices_list.extend(face_verts)
                face_verts = []

    if not vertices_list:
        raise ModelImportError("No vertices found in ASCII STL")

    vertices = np.array(vertices_list, dtype=np.float32)
    faces = np.arange(len(vertices), dtype=np.int32).reshape(-1, 3)

    return SurfaceModel(vertices=vertices, faces=faces, format="stl")


def is_plausible_mm(bounds_min: np.ndarray, bounds_max: np.ndarray) -> bool:
    """检测包围盒是否在合理的 mm 范围内 [1, 2000] mm。"""
    size = bounds_max - bounds_min
    return bool(np.all((size >= 1.0) & (size <= 2000.0)))


def detect_model_units(model: SurfaceModel) -> Tuple[str, float]:
    """根据包围盒尺寸推荐单位比例 (mm/模型单位)。

    Returns: (unit_name, mm_per_model_unit)
    """
    size = model.size
    max_dim = float(np.max(size))
    if max_dim <= 2.0:
        return ("米 (m)", 1000.0)
    elif max_dim <= 20.0:
        return ("厘米 (cm)", 100.0)
    elif max_dim <= 50.0:
        return ("英寸 (inch)", 25.4)
    else:
        return ("毫米 (mm)", 1.0)
