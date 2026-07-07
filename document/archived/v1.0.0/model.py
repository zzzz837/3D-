"""
3D Layout Editor — 核心数据模型

定义与 JSON Schema v2.0 对齐的 Cell、SurfaceModel、DeviceLayoutProfile3D 等。
Cell 是传感器通道的物理代理，锚定 channel ID、空间位置（重心/顶点）、覆盖范围（边长和扩散半径）。
"""

import copy
import json
from typing import List, Optional, Tuple, Dict, Any

import numpy as np

from .exceptions import SchemaValidationError
from .geometry3d import compute_bounding_box


class CellDefinition3D:
    """曲面上的正方形 Cell 数据类（纯数据，非 QObject）。

    Cell 锚定：
      - channel ID（cell_id）
      - 空间位置（center_3d / normal）
      - 覆盖范围（width_mm / height_mm，正方形约束下相等）
    """

    __slots__ = ("cell_id", "center_3d", "normal", "width_mm", "height_mm", "rotation_deg")

    def __init__(
        self,
        cell_id: int,
        center_3d: np.ndarray,
        normal: np.ndarray,
        width_mm: float = 10.0,
        height_mm: float = 10.0,
        rotation_deg: float = 0.0,
    ):
        if cell_id < -1:
            raise ValueError(f"cell_id must be >= -1, got {cell_id}")
        if width_mm <= 0 or height_mm <= 0:
            raise ValueError(f"width/height must be > 0, got {width_mm}/{height_mm}")
        self.cell_id: int = cell_id
        self.center_3d: np.ndarray = np.asarray(center_3d, dtype=np.float32)
        self.normal: np.ndarray = np.asarray(normal, dtype=np.float32)
        self.width_mm: float = float(width_mm)
        self.height_mm: float = float(height_mm)
        self.rotation_deg: float = float(rotation_deg)

    @classmethod
    def create_square(cls, center: np.ndarray, normal: np.ndarray, side_mm: float) -> "CellDefinition3D":
        """工厂方法：创建正方形 Cell。"""
        return cls(cell_id=-1, center_3d=center, normal=normal, width_mm=side_mm, height_mm=side_mm)

    @property
    def side_mm(self) -> float:
        """正方形边长（假设 width == height）。"""
        return self.width_mm if abs(self.width_mm - self.height_mm) < 1e-6 else max(self.width_mm, self.height_mm)

    def copy(self) -> "CellDefinition3D":
        return CellDefinition3D(
            cell_id=self.cell_id,
            center_3d=self.center_3d.copy(),
            normal=self.normal.copy(),
            width_mm=self.width_mm,
            height_mm=self.height_mm,
            rotation_deg=self.rotation_deg,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.cell_id,
            "center_3d": {"x": float(self.center_3d[0]), "y": float(self.center_3d[1]), "z": float(self.center_3d[2])},
            "normal": {"x": float(self.normal[0]), "y": float(self.normal[1]), "z": float(self.normal[2])},
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "rotation_deg": self.rotation_deg,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CellDefinition3D":
        c = d.get("center_3d", {})
        n = d.get("normal", {})
        return CellDefinition3D(
            cell_id=d["id"],
            center_3d=np.array([c["x"], c["y"], c["z"]], dtype=np.float32),
            normal=np.array([n["x"], n["y"], n["z"]], dtype=np.float32),
            width_mm=d.get("width_mm", 10.0),
            height_mm=d.get("height_mm", 10.0),
            rotation_deg=d.get("rotation_deg", 0.0),
        )

    def __repr__(self) -> str:
        return (
            f"CellDefinition3D(id={self.cell_id}, "
            f"center=({self.center_3d[0]:.1f},{self.center_3d[1]:.1f},{self.center_3d[2]:.1f}), "
            f"side={self.width_mm:.1f}mm)"
        )


class SurfaceModel:
    """3D 三角网格模型容器。"""

    __slots__ = ("vertices", "faces", "normals", "bounds_min", "bounds_max", "format", "raw_data", "_tri_count")

    def __init__(
        self,
        vertices: np.ndarray,
        faces: np.ndarray,
        normals: Optional[np.ndarray] = None,
        format: str = "stl",
        raw_data: Optional[bytes] = None,
    ):
        if vertices.ndim != 2 or vertices.shape[1] != 3:
            raise ValueError(f"vertices must be (N,3), got {vertices.shape}")
        if faces.ndim != 2 or faces.shape[1] != 3:
            raise ValueError(f"faces must be (M,3), got {faces.shape}")
        self.vertices: np.ndarray = vertices.astype(np.float32)
        self.faces: np.ndarray = faces.astype(np.int32)
        self.normals: np.ndarray = normals.astype(np.float32) if normals is not None else np.empty((0, 3), dtype=np.float32)
        self.format: str = format
        self.raw_data: Optional[bytes] = raw_data
        self._tri_count: int = len(faces)
        self._update_bounds()

    def _update_bounds(self) -> None:
        mn, mx = compute_bounding_box(self.vertices)
        self.bounds_min: np.ndarray = mn
        self.bounds_max: np.ndarray = mx

    @property
    def face_count(self) -> int:
        return self._tri_count

    @property
    def size(self) -> np.ndarray:
        return self.bounds_max - self.bounds_min

    @property
    def diagonal(self) -> float:
        return float(np.linalg.norm(self.size))

    def to_dict(self, include_raw: bool = False) -> Dict[str, Any]:
        import base64
        d: Dict[str, Any] = {
            "format": self.format,
            "file_name": "",
            "bounds": {
                "min": self.bounds_min.tolist(),
                "max": self.bounds_max.tolist(),
            },
            "face_count": self.face_count,
        }
        if include_raw and self.raw_data:
            d["data_base64"] = base64.b64encode(self.raw_data).decode("ascii")
        return d

    def __repr__(self) -> str:
        return f"SurfaceModel(format={self.format}, faces={self.face_count}, size={self.size})"


class DeviceLayoutProfile3D:
    """顶层配置文件对象（核心层纯 Python，无 QObject）。"""

    SCHEMA_VERSION = "2.0"

    def __init__(
        self,
        device_model: str = "",
        display_name: str = "",
        total_points: int = 200,
        surface_model: Optional[SurfaceModel] = None,
        cells: Optional[List[CellDefinition3D]] = None,
        source_file: Optional[str] = None,
    ):
        if not 1 <= total_points <= 200:
            raise ValueError(f"total_points must be 1-200, got {total_points}")
        self.version: str = self.SCHEMA_VERSION
        self.device_model: str = device_model
        self.display_name: str = display_name
        self.total_points: int = total_points
        self.surface_model: Optional[SurfaceModel] = surface_model
        self.cells: List[CellDefinition3D] = cells or []
        self.source_file: Optional[str] = source_file
        self._is_dirty: bool = False

    @property
    def is_dirty(self) -> bool:
        return self._is_dirty

    def mark_dirty(self) -> None:
        self._is_dirty = True

    def mark_clean(self) -> None:
        self._is_dirty = False

    def add_cell(self, cell: CellDefinition3D) -> None:
        if cell.cell_id < 0 or cell.cell_id >= self.total_points:
            raise ValueError(f"cell_id {cell.cell_id} out of range [0, {self.total_points})")
        for existing in self.cells:
            if existing.cell_id == cell.cell_id:
                raise ValueError(f"Duplicate cell_id {cell.cell_id}")
        self.cells.append(cell)
        self.mark_dirty()

    def remove_cell(self, cell_id: int) -> None:
        self.cells = [c for c in self.cells if c.cell_id != cell_id]
        self.mark_dirty()

    def get_cell(self, cell_id: int) -> Optional[CellDefinition3D]:
        for c in self.cells:
            if c.cell_id == cell_id:
                return c
        return None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "version": self.version,
            "device_model": self.device_model,
            "display_name": self.display_name,
            "total_points": self.total_points,
        }
        if self.surface_model:
            d["surface_model"] = self.surface_model.to_dict(include_raw=True)
        else:
            d["surface_model"] = None
        d["cells"] = [c.to_dict() for c in self.cells]
        return d

    def save_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        self.mark_clean()

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DeviceLayoutProfile3D":
        version = d.get("version")
        if version not in ("2.0", "1.3"):
            raise SchemaValidationError(f"Unsupported schema version: {version}")
        total_points = d.get("total_points", 200)
        if not 1 <= total_points <= 200:
            raise SchemaValidationError(f"total_points must be 1-200, got {total_points}")

        cells = [CellDefinition3D.from_dict(c) for c in d.get("cells", [])]
        cell_ids = {c.cell_id for c in cells}
        if len(cell_ids) != len(cells):
            raise SchemaValidationError("Duplicate cell_id in cells array")

        surface_model = None
        sm = d.get("surface_model")
        if sm:
            import base64
            raw = base64.b64decode(sm["data_base64"]) if sm.get("data_base64") else None
            surface_model = SurfaceModel(
                vertices=np.empty((0, 3), dtype=np.float32),
                faces=np.empty((0, 3), dtype=np.int32),
                format=sm.get("format", "stl"),
                raw_data=raw,
            )

        return cls(
            device_model=d.get("device_model", ""),
            display_name=d.get("display_name", ""),
            total_points=total_points,
            surface_model=surface_model,
            cells=cells,
        )

    @staticmethod
    def load_json(path: str) -> "DeviceLayoutProfile3D":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile = DeviceLayoutProfile3D.from_dict(data)
        profile.source_file = path
        return profile

    def __repr__(self) -> str:
        return (
            f"DeviceLayoutProfile3D(device_model={self.device_model!r}, "
            f"total_points={self.total_points}, cells={len(self.cells)})"
        )
