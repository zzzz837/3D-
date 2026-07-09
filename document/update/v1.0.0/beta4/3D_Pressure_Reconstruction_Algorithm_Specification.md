# 3D Pressure Reconstruction Algorithm Specification

> **版本**: beta4 最终版
> **更新**: 2026-07-09 — 基于仿真对比结果 + 代码实现定稿
> **状态**: ✅ Wendland C2 已集成到生产环境 (src/3D编辑器原型.html)
> **备选**: ○ Graph Laplacian (稀疏场景降级, 待后续版本)

---

## 1. 最终方案：Wendland C2 紧支撑核加权插值

> 选型依据：5 场景 × 8 指标仿真对比 (仿真框架 ~1500行 Python, 详见 `仿真/3D压力场重建仿真对比报告.md`)

### 1.1 物理模型

将每个 Cell 视为连续压力场的**离散采样点**。对 Mesh 上每个顶点，在其影响半径内查询邻域 Cell，使用 Wendland C2 核函数计算权重并做加权平均。属于 **局部加权插值 (Local Weighted Interpolation)**，不是压力叠加。

### 1.2 Wendland C2 核函数

归一化距离 $r = d / R$，$d$ 为顶点到 Cell 中心距离，$R$ 为影响半径 (FIELD_R, 默认 60mm)：

$$
\varphi(r) = \begin{cases}
(1-r)^4 (4r+1), & 0 \le r \le 1 \\
0, & r > 1
\end{cases}
$$

**核心性质**：
- **紧支撑**: $r \ge 1$ 时严格为零，无硬截断伪影 → 边缘自然渐隐 (edge_decay = 0.90)
- **C2 光滑**: $r=1$ 处 $\varphi = \varphi' = \varphi'' = 0$，全部连续 → 无视觉伪影
- **严格正定**: 在 $\mathbb{R}^5$ 及以下所有维度正定

### 1.3 加权平均公式

对顶点 $v$：

$$
P(v) = \frac{\sum_i P_i \cdot \varphi(r_i)}{\sum_i \varphi(r_i)} \times \min\!\big(1,\; \sum_i \varphi(r_i)\big)
$$

- **分子/分母归一化 (Shepard-like)**: 消除传感器密度假象（密集区域不偏亮）
- **min(1, Σw) 置信度衰减**: Coverage 不足时自然渐隐，避免边缘硬切

### 1.4 最终着色公式

```
vertexColor = MODEL_GREY.lerp(jetColor(normalizedPressure), confidence)
```

其中：
- `normalizedPressure = clamp((P - pressureMin) / (pressureMax - pressureMin), 0, 1)` — 用户定义归一化
- `confidence = min(1, Σφ)` — Wendland 权重和
- `MODEL_GREY = rgb(0x7f8998)` — 未覆盖区域底色

无 Cell 覆盖的顶点保持灰色，热力图仅出现在 Cell 影响范围内。

### 1.5 距离度量

| 当前 | 方法 | 后续升级方向 |
|------|------|-------------|
| ✅ | **Euclidean Distance** | 3D 空间直线距离，曲面平坦时可用 |
| ○ | Geodesic Distance | 沿曲面测地距离，需 BVH/Mesh，精度更高 |

### 1.6 参数配置

| 参数 | 默认值 | 范围 | 状态 |
|------|--------|------|------|
| `FIELD_R` (影响半径) | 60 mm | 20-200 mm | ✅ 已实现 |
| `pressureMin` | 0 | 用户定义 | ✅ 已实现 |
| `pressureMax` | 100 | 用户定义 | ✅ 已实现 |
| `coverageThreshold` | 0.01 | 内部固定 | ✅ 已实现 |
| `post_gaussian_sigma` | 1.5 px | — | ❌ 未实现 (预留) |

### 1.7 工作流

```
Cell Pressure Values
      ↓
getCellPressures()  (manual/simulated/real 三模式)
      ↓
[Cache OK?] ──No──→ rebuildFieldCache()  ⚡ 一次性 (cell/半径变化时)
      │                 ├─ _vpos: 缓存150万顶点坐标 (~18MB)
      │                 ├─ _cv: 收集覆盖顶点列表 (Uint32Array)
      │                 └─ CSR: _ioff/_icell/_iwgt (影响关系+Wendland权重)
      │
      └──Yes──→ applyFieldColors()  ⚡ 每帧 (~10-50ms)
                    ├─ 只遍历 _cv (覆盖顶点, ~5-10万)
                    ├─ 读 CSR 预存权重 → 加权求和
                    ├─ normalize → jetColor → lerp(grey, confidence)
                    └─ col.setXYZ → needsUpdate → GPU
```

---

## 2. 选型过程 (仿真验证)

### 2.1 仿真框架

```
仿真/  (~1500行 Python)
├── algorithms.py        # Wendland C2 / MLS / Graph Laplacian (276行)
├── data_generator.py    # 5种测试场景生成器 (197行)
├── compare.py           # 2D仿真入口 (151行)
├── mesh_compare.py      # 3D OBJ模型仿真 (452行)
├── metrics.py           # 8维定量指标 (67行)
├── visualize.py         # matplotlib可视化 (173行)
└── output/              # 36个结果文件
```

### 2.2 仿真实测结果

| 场景 | 指标 | Wendland C2 | MLS | Graph Laplacian |
|------|------|:-----------:|:---:|:---------------:|
| uniform_gaussian (120 cells) | RMSE | 7.54 | **4.71** | 7.95 |
| clustered_gaussian (100 cells) | RMSE | 44.41 | **19.32** | 24.29 |
| uniform_saddle (100 cells) | RMSE | **4.26** | 5.66 | 4.82 |
| **edge_sparse (58 cells)** | RMSE | **16.41** | 35.38 ❌ | 32.24 |
| | **edge_decay** | **0.90** | 0.79 | 0.43 |
| | local_peaks | **1** | **7 ❌假峰** | 1 |
| sparse_15 (15 cells) | RMSE | 56.33 | 30.37 | **26.97** |
| 3D OBJ 52K顶点 | Runtime | 20.3s | 6s | **0.6s (33x)** |
| | 压力保界 | ✓ 98.78 | ❌ 108超界8% | ✓ 100.0 |

### 2.3 结论

```
┌──────────────────────────────────────────────────────┐
│  主方案: Wendland C2  ✅ (已集成)                      │
│  • 边缘衰减率 0.90 (最优)                              │
│  • 无假峰、压力严格保界                                 │
│  • C2 光滑 → 视觉无伪影                                │
├──────────────────────────────────────────────────────┤
│  备选: Graph Laplacian  ○ (待后续版本降级)              │
│  • Cell < 20 的极限稀疏场景 (RMSE 26.97 vs 56.33)      │
│  • 3D Mesh 有拓扑时快 20-40x (0.6s vs 20.3s)          │
├──────────────────────────────────────────────────────┤
│  淘汰: MLS  ✗                                          │
│  • 边缘稀疏产生 7 个假峰 (过拟合)                        │
│  • 3D 模型压力超界 8%                                  │
└──────────────────────────────────────────────────────┘
```

---

## 3. 生产优化架构 (beta4 实现)

### 3.1 空间分桶 (Layer 0)

暴力复杂度 $O(V \times N)$。将空间按 `FIELD_R` 网格分桶，每个顶点仅查询所在桶及 26 个相邻桶 → $O(V \times k)$。

- 2D: 8-邻域 (3×3)
- 3D: 26-邻域 (3×3×3)

### 3.2 CSR Influence Cache (Layer 1)

只在 Cell 位置/半径变化时重建：

```
_ioff[N+1]     Uint32Array   行偏移: 顶点 i 的影响从 _ioff[i] 开始
_icell[M]      Uint32Array   Cell ID 列表
_iwgt[M]       Float32Array  Wendland 权重列表

遍历顶点 i:
  for (j = _ioff[i]; j < _ioff[i+1]; j++) {
    cellId = _icell[j];  weight = _iwgt[j];
    pressure += cellPressures[cellId] * weight;
  }
```

### 3.3 覆盖顶点遍历 (Layer 2)

$$
_cv (Uint32Array) — rebuildFieldCache 时收集所有有影响的顶点索引
$$

逐帧着色只遍历 `_cv`，不再遍历全部顶点。150万面模型覆盖顶点 ~5-10万，**遍历量减少 93-97%**。

### 3.4 缓存失效策略

| 操作 | 触发 | 代价 |
|------|------|------|
| Cell 增删移动 / FIELD_R 变化 | `invalidateFieldCache()` 全量清灰 + 重建 CSR | 一次性 2-5s |
| 压力值变化 | `_lastKey=null` (仅触发着色) | 10-50ms |
| 模型更换 | `_vpos=null` + 重建 | 一次性 |

---

## 4. 淘汰方案记录

### 4.1 MLS — 淘汰

**原理**: 每个顶点在 KNN 邻域 Cell 上拟合局部多项式曲面。

**淘汰原因**:
1. 边缘稀疏场景产生 **7 个假峰**（真值仅 1 个）
2. 3D 模型压力**超界 8%**（读取到 108，没有任何 Sensor 输出此值）
3. 每个顶点需求解最小二乘 O(K³)，性能差
4. 需要 KNN 搜索而非半径搜索，无法利用 Wendland 的紧支撑优势

### 4.2 Graph Laplacian — 备选

**原理**: Mesh 拓扑图上的 Dirichlet 边值问题，求解 Lx = b。

**保留原因**:
1. Cell < 20 极限稀疏场景 RMSE 最优 (26.97 vs Wendland 56.33)
2. 3D Mesh 有拓扑时快 20-40x (0.6s vs 20.3s)
3. 天然适配 Mesh 面片拓扑

**待集成**: 后续版本中 Cell < 20 时自动降级到 Laplacian。

---

## 5. 代码实现索引

| 文件 | 行数 | 说明 |
|------|------|------|
| `src/3D编辑器原型.html` | ~950 | JS 生产实现 (Wendland引擎+CSR缓存+三模式+UI) |
| `src/tests/test_force_field.py` | 335 | Python 等效算法 29 项测试 |
| `仿真/algorithms.py` | 276 | 三种算法 Python 参考实现 |
| `仿真/mesh_compare.py` | 452 | 3D OBJ 模型仿真程序 |
| `仿真/3D压力场重建仿真对比报告.md` | 612 | 完整选型分析报告 |
| `仿真/output/` | 36 文件 | 全部仿真输出 (PNG/CSV/JSON/NPY) |
