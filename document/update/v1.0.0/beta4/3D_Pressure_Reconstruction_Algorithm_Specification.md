# 3D Pressure Reconstruction Algorithm Specification

> **版本**: beta3 / beta4 热力图引擎
> **来源**: `Wendland压力场重建模型.md`
> **beta3**: 方法论文档 | **beta4**: 代码实现

---

## 1. 推荐方案：Wendland C2 紧支撑核加权插值

### 1.1 物理模型

将每个 Cell 视为连续压力场的**离散采样点**。对 Mesh 上每个顶点（或像素），在其影响半径内查询邻域 Cell，使用 Wendland C2 核函数计算权重并做加权平均。整个过程属于 **局部加权插值 (Local Weighted Interpolation)**，不是压力叠加。

### 1.2 Wendland C2 核函数

归一化距离 $r = d / R$，其中 $d$ 为顶点到 Cell 中心的距离，$R$ 为影响半径（query_radius_mm）：

$$
\varphi(r) = \begin{cases}
(1-r)^4 (4r+1), & 0 \le r \le 1 \\
0, & r > 1
\end{cases}
$$

**核心性质**：
- **紧支撑**：$r \ge 1$ 时严格为零，无硬截断伪影
- **C2 光滑**：$r=1$ 处 $\varphi = \varphi' = \varphi'' = 0$，全部连续
- **严格正定**：在 $\mathbb{R}^5$ 及以下所有维度正定（覆盖 2D 曲面和 3D 体积）

### 1.3 加权平均公式

对顶点 $v$：

$$
P(v) = \frac{\sum_i P_i \cdot \varphi(r_i)}{\sum_i \varphi(r_i)} \times \min\!\big(1,\; \sum_i \varphi(r_i)\big)
$$

- **分子/分母归一化**：消除传感器密度假象（密集区域不偏亮）
- **$\min(1, \sum w)$ 置信度衰减**：Coverage 不足时自然渐隐，避免边缘硬切

### 1.4 距离度量

| 优先级 | 方法 | 说明 |
|--------|------|------|
| 1 | **Geodesic Distance** | 沿曲面测地距离，最准确（需要 BVH/Mesh 支持） |
| 2 | **Euclidean Distance** | 3D 空间直线距离，计算简便，曲面平坦时近似可用 |

beta4 默认使用 Euclidean Distance，后续版本可升级为 Geodesic。

### 1.5 默认参数

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `query_radius_mm` | 60.0 | 紧支撑半径，约等于 Cell 间距的 2 倍保证平滑过渡 |
| `post_gaussian_sigma` | 1.5 px | 后处理高斯 sigma（像素单位），去噪润色用 |

### 1.6 性能优化：空间分桶

暴力复杂度 $O(V \times N)$（顶点数 × Cell 数）。以 200 Cell × 40万顶点为例，需 8000 万次距离计算。

**优化**：将画布按 `query_radius_mm` 网格分桶。每个顶点仅查询所在桶及 8 个相邻桶内的 Cell → 复杂度降至 $O(V \times k)$，其中 $k \ll N$。

### 1.7 后处理：可分离 Gaussian 卷积

可选的后处理步骤，用于消除像素级噪点：

- 先水平方向 1D 卷积，再垂直方向 1D 卷积
- 复杂度 $O(W \times H \times 2K)$ 而非 $O(W \times H \times K^2)$
- **不做归一化**（中心权重保持 1.0）——保持恒定压力区域输出不变

### 1.8 工作流

```
Mesh / Pixel Grid
      ↓
For Each Vertex / Pixel
      ↓
  QueryRadius (spatial bucket)
      ↓
  Compute Distance (Euclidean/Geodesic)
      ↓
  Compute Wendland Weight φ(r)
      ↓
  numer += pressure × weight
  denom += weight
      ↓
  VertexPressure = numer / denom × min(1, denom)
      ↓
  Post-process: separable Gaussian (optional)
      ↓
  Color Mapping (Jet LUT)
```

---

## 2. 备选方案：Moving Least Squares (MLS)

### 2.1 原理

每个顶点不直接加权平均，而是在邻域 Cell 上拟合**局部连续曲面**（一次或二次多项式），然后用拟合曲面计算顶点压力值。属于**局部曲面拟合 (Local Surface Fitting)**。

### 2.2 数学

最小化加权残差：

$$
\min \sum_i w_i(\mathbf{x}) \big(P_i - f(\mathbf{x}_i)\big)^2
$$

其中 $f(\mathbf{x})$ 为局部多项式：
- 一次：$f(x,y) = ax + by + c$
- 二次：$f(x,y) = ax^2 + by^2 + cxy + dx + ey + f$

### 2.3 优劣

| 优势 | 劣势 |
|------|------|
| 曲面更光滑（多项式拟合） | 每个顶点需求解最小二乘 → $O(K^3)$ |
| 适合稀疏采样 | Cell 密集时过度平滑丢失细节 |
| | 需要 KNN 搜索（非半径搜索） |

### 2.4 参数

| 参数 | 建议值 | 说明 |
|------|--------|------|
| K | 8-15 | KNN 邻居数 |
| 多项式阶数 | 1 | 一次曲面（二次为可选模式） |
| 权重核 | Wendland / Gaussian | 距离加权 |

---

## 3. 备选方案：Graph Laplacian 扩散

### 3.1 原理

将 Mesh 视为图（Graph）：顶点为节点，边为 Mesh 连接关系。压力沿 Graph 连通性扩散，不依赖欧氏距离。属于**表面扩散 (Surface Diffusion)**。

### 3.2 数学

构造 Laplacian 矩阵 $L = D - A$（$A$ 邻接矩阵，$D$ 度矩阵），求解线性系统：

$$
L\mathbf{x} = \mathbf{b}
$$

其中 Sensor Cell 位置作为 Dirichlet 边界条件。

### 3.3 优劣

| 优势 | 劣势 |
|------|------|
| 自然处理 Mesh 拓扑 | 需构建和求解稀疏线性系统 |
| 扩散不受测地距离限制 | 仅适用于有 Mesh 的场景 |
| 适合全局求解 | 复杂度较高（$O(n \log n)$） |

---

## 4. 方案推荐

| 场景 | 推荐方案 |
|------|---------|
| **beta4 默认** | Wendland C2 核（紧支撑 + 正定 + C2 光滑 + 可实时） |
| Cell 稀疏 (<20个) | MLS 一次曲面（更光滑的插值） |
| 有完整 Mesh 拓扑 | Graph Laplacian（全局最优，离线场景） |

**beta4 实现选择**：Wendland C2 核 + 空间分桶 + 可选 Gaussian 后处理。热力图代码独立模块化，方便后续与其他软件数据对接。
