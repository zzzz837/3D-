# 3D拟物Layout编辑器 v1.0 — 数据结构与JSON Schema

> 参照 2D `01-数据结构.md` 结构，适配 3D 曲面 Cell 布局。

---

## 一、数据分层

```
┌─ 持久化层 (磁盘) ─────────────────────────────────────────────┐
│  JSON v2.0 文件 (.json)                                       │
│  { version, device_model, total_points,                       │
│    surface_model: {format, file_name, data_base64},           │
│    cells: [{id, center_3d, normal, width_mm, height_mm, rot}]}│
├─ Python 核心层 (内存) ─────────────────────────────────────────┤
│  DeviceLayoutProfile3D + CellDefinition3D[] + SurfaceModel     │
│  + CellBasket3D (ID池)                                        │
├─ JS 运行时 (内存) ────────────────────────────────────────────┤
│  cellsData (C) = {id: {x,y,z, nx,ny,nz, w,h, rot, id}}      │
│  modelMesh (M), focusId (F), overlapMap (V)                   │
│  UNDO[], REDO[] (JSON快照, 深度50)                             │
└──────────────────────────────────────────────────────────────┘
```

## 二、JSON Schema v2.0

### 2.1 完整 Schema

```jsonc
{
  // ── 元信息 ──
  "version": "2.0",                       // str, 固定 "2.0"
  "device_model": "Glove",               // str, 1-64字符, 必填
  "display_name": "",                    // str, 可选, ≤128字符
  "total_points": 128,                   // int, 1-200, 传感器硬件通道数

  // ── 3D曲面模型 (Base64嵌入) ──
  "surface_model": {
    "format": "stl",                     // "stl" | "obj" | "gltf" | "glb"
    "file_name": "glove_A.stl",          // str, 原始文件名
    "data_base64": "QnJpbmcg..."         // str, 模型二进制 Base64 (单文件自包含)
  },

  // ── 传感器Cell数组 ──
  "cells": [
    {
      "id": 0,                           // int, 0~total_points-1, 不重复
      "center_3d": {                     // Cell中心在曲面上的3D坐标 (mm)
        "x": 10.0,
        "y": 20.0,
        "z": 5.0
      },
      "normal": {                        // 曲面法向量 (单位向量, 自动朝外)
        "x": 0.15,
        "y": -0.23,
        "z": 0.96
      },
      "width_mm": 10.0,                  // float, >0, 正方形约束下 == height_mm
      "height_mm": 10.0,                 // float, >0
      "rotation_deg": 0.0                // float, 0.0~360.0, 绕法向量旋转
    }
  ]
}
```

### 2.2 字段约束表

| 字段 | 类型 | 必填 | 约束 |
|------|------|------|------|
| `version` | str | 是 | `"2.0"` |
| `device_model` | str | 是 | 1-64 字符 |
| `total_points` | int | 是 | 1-200 |
| `surface_model.format` | str | 是 | `"stl"|"obj"|"gltf"|"glb"` |
| `surface_model.data_base64` | str | 是 | Base64编码的模型二进制 |
| `cells[].id` | int | 是 | 0~total_points-1, 不重复 |
| `cells[].center_3d.x/y/z` | float | 是 | mm单位 |
| `cells[].normal.x/y/z` | float | 是 | 单位向量 |
| `cells[].width_mm` | float | 是 | >0 |
| `cells[].height_mm` | float | 是 | >0 |
| `cells[].rotation_deg` | float | 是 | 0.0-360.0 |

### 2.3 v1.3 兼容 (2D→3D)

当 `version == "1.3"` 时:
- `cells[].vertices[] → center_3d`: 取多边形重心 x/y, z=0
- `cells[].centroid → center_3d`: x/y → 3D, z=0
- `side_length → width_mm/height_mm`: 2D边长直接映射
- `mask_path` → 忽略 (3D用曲面模型替代)
- `bounds` → 忽略

## 三、Python 核心数据模型

### 3.1 CellDefinition3D (core/model.py)

```python
class CellDefinition3D:
    """曲面上的正方形 Cell 数据类（纯数据，非 QObject）。

    __slots__ = ("cell_id", "center_3d", "normal", "width_mm", "height_mm", "rotation_deg")
    """
    cell_id: int              # 0 ~ total_points-1
    center_3d: np.ndarray     # (3,) float32 — 曲面中心坐标 (mm)
    normal: np.ndarray        # (3,) float32 — 曲面法向量 (单位向量)
    width_mm: float           # >0，正方形约束下 == height_mm
    height_mm: float          # >0
    rotation_deg: float       # 0~360, 绕法向量旋转

    @classmethod
    def create_square(cls, center, normal, side_mm) -> "CellDefinition3D"
        """工厂方法：创建正方形 Cell (width=height=side_mm)。"""

    @property
    def side_mm(self) -> float
        """正方形边长 (假设 width==height, 误差<1e-6)"""

    def copy(self) -> "CellDefinition3D"
    def to_dict(self) -> dict
    @staticmethod
    def from_dict(d: dict) -> "CellDefinition3D"
```

### 3.2 SurfaceModel (core/model.py)

```python
class SurfaceModel:
    """3D 三角网格模型容器。

    __slots__ = ("vertices", "faces", "normals", "bounds_min", "bounds_max", "format", "raw_data", "_tri_count")
    """
    vertices: np.ndarray      # (N, 3) float32 — 顶点世界坐标 (mm)
    faces: np.ndarray         # (M, 3) int32 — 三角面顶点索引
    normals: np.ndarray       # (M, 3) float32 — 面法线 (单位向量)
    bounds_min: np.ndarray    # (3,) float32 — 包围盒最小角
    bounds_max: np.ndarray    # (3,) float32 — 包围盒最大角
    format: str               # "stl" | "obj" | "gltf" | "glb"
    raw_data: bytes            # 原始文件二进制 (用于 Base64 嵌入)

    @property
    def face_count(self) -> int
    @property
    def size(self) -> np.ndarray          # 包围盒尺寸 (max-min)
    @property
    def diagonal(self) -> float           # 包围盒对角线长度
    def to_dict(self, include_raw=False) -> dict
    def _update_bounds(self) -> None
```

### 3.3 DeviceLayoutProfile3D (core/model.py)

```python
class DeviceLayoutProfile3D:
    """顶层配置对象 (核心层纯 Python，无 QObject)。

    SCHEMA_VERSION = "2.0"
    """
    version: str = "2.0"
    device_model: str         # 1-64 字符
    display_name: str         # 可选
    total_points: int         # 1-200
    surface_model: SurfaceModel | None
    cells: List[CellDefinition3D]
    source_file: str | None   # 文件路径, None=新建
    is_dirty: bool            # 是否有未保存修改

    def add_cell(cell: CellDefinition3D) -> None
        """添加Cell到profile。校验: cell_id范围+不重复。标记dirty。"""
    def remove_cell(cell_id: int) -> None
    def get_cell(cell_id: int) -> CellDefinition3D | None
    def to_dict() -> dict
    @classmethod def from_dict(d) -> "DeviceLayoutProfile3D"
    def save_json(path: str) -> None
    @staticmethod def load_json(path: str) -> "DeviceLayoutProfile3D"
    def mark_dirty() / mark_clean()
```

### 3.4 CellBasket3D (core/basket.py)

```python
class CellBasket3D:
    """管理 Cell ID 的落地/未落地状态。
    规则：初始全部未落地 → 每次取最小值 → 删除后归还。
    """
    total_points: int        # 1~200
    unlanded_count: int
    landed_count: int
    next_id: int | None      # 未落地集合中最小ID
    landed_ids: List[int]    # 升序
    unlanded_ids: List[int]

    def land(cell_id: int) -> None
        """标记cell_id为已落地。未在未落地集合→CellBasketError"""
    def unland(cell_id: int) -> None
        """归还到未落地。未在已落地集合→CellBasketError"""
    def is_landed(cell_id) / is_unlanded(cell_id) -> bool
    def resize(new_total: int) -> None
        """调整总数，保留已落地ID，扩展/截断未落地集合"""
```

### 3.5 异常 (core/exceptions.py)

```python
class ModelImportError(Exception):
    """3D 模型导入失败（格式不支持、解析错误、面数超限）"""

class SchemaValidationError(ValueError):
    """JSON Schema 校验失败（版本不对、total_points范围错、重复cell_id）"""

class CellBasketError(Exception):
    """Cell 篮子操作异常（land未在未落地、unland未在已落地）"""
```

## 四、几何工具函数 (core/geometry3d.py)

```python
def triangle_area(a, b, c) -> float
    """单个三角面面积 (1/2 * |cross(b-a, c-a)|)"""

def triangle_area_batch(v0, v1, v2) -> np.ndarray
    """批量计算三角面面积 → (M,) float"""

def compute_normals(vertices, faces) -> np.ndarray
    """右手定则计算三角面法线。零面积三角面 → [0,0,1] 兜底"""

def compute_bounding_box(vertices) -> (np.ndarray, np.ndarray)
    """返回 (min, max)，各 (3,) float32. 空数组→零包围盒"""

def is_point_in_triangle(p, a, b, c) -> bool
    """重心坐标法判断点是否在三角形内 (含边界, 容差1e-8)"""

def perpendicular(v) -> np.ndarray
    """返回与v垂直的任意单位向量 (用于构造切平面基)"""

def build_tangent_basis(normal) -> (np.ndarray, np.ndarray)
    """由法向量构造切平面正交基 (u, v)，均单位向量"""

def closest_point_on_triangle(p, a, b, c) -> np.ndarray
    """求点p到三角形(a,b,c)的最近点 (单位化投影, 7区域判定)"""

def unify_normals(vertices, faces, normals) -> (np.ndarray, np.ndarray)
    """基于连通分量分析(BFS), 将所有面法线翻转到一致朝外
       算法: 构建面邻接图(共享边) → BFS遍历 → 相邻面法线夹角>90°则翻转"""
```

## 五、JS 运行时数据结构

```javascript
// ── 全局状态 ──
let MAX = 0;           // 总通道数 (模型加载后自动推导)
let C = {};            // cellsData[id] = {x,y,z, nx,ny,nz, w,h, rot, id}
let M = null;          // modelMesh — THREE.Mesh (3D曲面模型)
let F = -1;            // focusId — 选中Cell ID (-1=无)
let E = true;          // editMode
let V = {};            // overlapMap[id] = 重叠层数
let S = 1;             // modelScale — 包围盒最大尺寸
let side = 10;         // defaultSide — 默认Cell边长 (mm)
let unitMM = 1;        // mm_per_model_unit

// ── 三维结构 ──
let UNDO = [];         // JSON快照栈 (深度50)
let REDO = [];
let collisionEnabled = true;  // 碰撞检测开关
let dragCellId = -1;   // Ctrl+拖拽中的Cell ID
let dragging = false;
let PREVIEW = false;   // 3D热力图预览模式
let HEAT_SPEED = 2;    // 预览动画周期 (秒)

// ── 每个Cell的JS表示 ──
cell = {
    id: int,            // 通道编号
    x, y, z: float,     // 曲面中心 (模型坐标单位, 非mm)
    nx, ny, nz: float,  // 曲面法向量
    w, h: float,        // 宽/高 (mm)
    rot: float          // 旋转角 (°)
};
```

## 六、Bridge 通信协议

### Python → JS (`self._wv.page().runJavaScript(js)`)

```
window.pyCommand(cmd, data)

cmd                    | data参数                 | 触发场景
───────────────────────┼──────────────────────────┼──────────
loadStl                | {b64, name, cells?, total_points?} | 新建/打开 (加载3D模型)
exportCells            | {}                       | 保存前请求Cell数据
undo                   | {}                       | 撤销
redo                   | {}                       | 重做
toggleEdit             | {}                       | 编辑/预览切换
togglePlace            | {}                       | 放置模式
togglePreview          | {}                       | 3D热力图预览
autoFill               | {}                       | 自动填充
wire                   | {}                       | 线框模式
reset                  | {}                       | 重置视角
deleteCell             | {}                       | 删除选中Cell
escape                 | {}                       | 取消选中
focusCell              | {id}                     | 聚焦指定Cell
loadJsonCells          | [{id,center_3d,...}]     | 打开JSON恢复Cell
setTotal               | {n}                      | 设置总通道数
screenshot             | {path}                   | 截图当前视图
```

### JS → Python (`console.log('BRIDGE:' + JSON.stringify({e, d}))`)

```
e                    | d参数                                | 触发时机
─────────────────────┼──────────────────────────────────────┼────────
ready                | {max, side, unitMM}                   | 引擎就绪 (1s延迟)
state                | {landed, unlanded, max, overlap}      | 篮子/Cell状态变化
cell                 | {id, x, y, z, side, area, rot, overlap, nx, ny, nz} | Cell选中
allCells             | [...cellData]                         | 全部Cell列表
exportCells          | {cells, total_points}                 | 保存时Cell数据
modelLoaded          | {faces, size[], surfaceArea, recommendedChannels} | 模型加载完成
screenshotData       | {data: base64_png, path}              | 截图生成后
error                | {msg}                                 | JS异常
```

## 七、坐标系统

```
3D世界 (Three.js)
    │ mm2u(mm) = mm / unitMM  模型单位 ← real mm
    │ u2mm(u)  = u * unitMM   real mm  ← 模型单位
    ▼
STL顶点坐标 (模型单位)
    └── center_3d (mm): Cell中心在曲面上的3D坐标
        normal: 曲面法向量 (单位向量, 自动朝外)
        width_mm/height_mm: 真实物理尺寸 → 渲染时换算为模型单位
```

- `unitMM` 默认 1mm/模型单位
- 导入时自动检测包围盒尺寸: 米制→1000, 厘米→100
- 用户可在属性面板手动修改单位比例