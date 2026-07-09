# beta4 力场重建算法说明

> **版本**: beta4 | **更新**: 2026-07-09 | **状态**: 已集成生效

---

## 1. 概述

将离散 Cell 压力值重建为 3D Mesh 表面连续压力场并渲染热力图。

```
Cell[i].pressure → getCellPressures() → applyFieldColors() → vertexColors → 热力图
                           ↑                      ↑
                   手动/模拟/导入三模式       CSR缓存 + _cv遍历
```

---

## 2. 核心公式

### 2.1 Wendland C2 核函数

归一化距离 $r = d / R$，$d$ 为顶点到Cell中心距离，$R$ 为影响半径(FIELD_R, 默认60mm)：

$$
\varphi(r) = (1-r)^4 (4r+1), \quad 0 \le r \le 1
$$
$$
\varphi(r) = 0, \quad r > 1
$$

**性质**: 紧支撑(r≥1严格为零) · C2光滑(r=1处 φ=φ'=φ''=0) · 严格正定

### 2.2 加权平均

$$
P(v) = \frac{\sum_i P_i \cdot \varphi(r_i)}{\sum_i \varphi(r_i)} \times \min(1,\;\sum_i \varphi(r_i))
$$

- 分子/分母归一化：消除Cell密度假象
- min(1, Σw)：置信度衰减，coverage不足时渐隐

### 2.3 着色

$$
t = clamp\big(\frac{P - p_{min}}{p_{max} - p_{min}},\;0,\;1\big)
$$
$$
color = grey \cdot (1-confidence) + jet(t) \cdot confidence
$$
$$
confidence = \min(1,\;\sum_i \varphi(r_i))
$$

无Cell覆盖的顶点保持灰色(0x7f8998)，热力图仅出现在Cell影响半径内。

---

## 3. JS 实现

### 3.1 核函数

```js
function wendlandPhi(r) {
  return r >= 1 ? 0 : Math.pow(1 - r, 4) * (4 * r + 1);
}
```

### 3.2 Jet 色彩映射

```
t=0     → 深蓝 (0,0,128)
t=0.125 → 纯蓝 (0,0,255)
t=0.375 → 青色 (0,255,255)
t=0.625 → 黄色 (255,255,0)
t=0.875 → 红色 (255,0,0)
t=1     → 深红 (128,0,0)
```

```js
function jetColor(t) {
  t = Math.max(0, Math.min(1, t));
  let r, g, b;
  if (t < .125) { const s = t / .125; r = 0; g = 0; b = 128 + 127 * s }
  else if (t < .375) { const s = (t - .125) / .25; r = 0; g = 255 * s; b = 255 }
  else if (t < .625) { const s = (t - .375) / .25; r = 255 * s; g = 255; b = 255 * (1 - s) }
  else if (t < .875) { const s = (t - .625) / .25; r = 255; g = 255 * (1 - s); b = 0 }
  else { const s = (t - .875) / .125; r = 255 * (1 - s * .5); g = 0; b = 0 }
  return new T.Color(r / 255, g / 255, b / 255);
}
```

### 3.3 压力数据源

| 模式 | 数据来源 | 触发 |
|------|---------|------|
| manual | `C[id].pressure` 用户输入 | propPressure.onchange |
| simulated | `updateSimPressures()` 正弦波 | toggleSimulate() |
| real | `_importedField` JSON导入 | importFieldJSON() |

```js
function getCellPressures(cells) {
  if (FIELD_MODE === 'real') return _importedField;
  const p = {};
  cells.forEach(c => {
    const v = parseFloat(c.pressure);
    p[c.id] = Number.isFinite(v) ? v : 0;
  });
  return p;
}
```

### 3.4 模拟压力 (per-Cell正弦波)

```js
function updateSimPressures() {
  const cells = Object.values(C), now = Date.now() / 1000;
  cells.forEach(c => {
    const phase = (c.id + 1) * 0.73,
          freq = 0.25 + (c.id % 7) * 0.12,
          base = pressureMin + (pressureMax - pressureMin) * 0.2,
          amp = (pressureMax - pressureMin) * 0.35;
    c.pressure = base + amp * (0.5 + 0.5 * Math.sin(now * freq + phase));
  });
}
```

---

## 4. 性能架构

### 4.1 三层缓存

```
Layer 1 — _vpos (Float32Array)
  缓存全部顶点在Cell空间的坐标（一次性，~18MB for 150万面）
  消除每帧 matrix multiply

Layer 2 — CSR Influence Cache
  _ioff[N+1]  行偏移
  _icell[M]   Cell ID
  _iwgt[M]    Wendland 权重
  消除每帧 空间分桶+Wendland计算
  仅在 Cell位置/半径变化时重建

Layer 3 — _cv (Uint32Array)
  覆盖顶点索引列表
  applyFieldColors 只遍历 _cv，不再全量遍历
  150万面 → ~5-10万覆盖顶点 → 遍历量↓93%
```

### 4.2 两个核心函数

| 函数 | 何时调用 | 耗时 (150万面) |
|------|---------|---------------|
| `rebuildFieldCache()` | Cell增删移动 / FIELD_R变化 | 2-5s (一次性) |
| `applyFieldColors()` | 压力变化时(手动) / 500ms(模拟) | 10-50ms |

### 4.3 空间分桶

```js
// 将Cell按FIELD_R网格分桶
// 查询时只检查所在桶及26个相邻桶 (3×3×3)
// O(V×N) → O(V×k), k = 每个桶内Cell数
```

### 4.4 缓存失效

| 操作 | 动作 |
|------|------|
| Cell 增删移动 | `invalidateFieldCache()` — 清灰 + 重建CSR |
| FIELD_R 变化 | `invalidateFieldCache()` — 重建CSR |
| 压力值变化 | `_lastKey=null` — 仅触发着色 |
| 模型更换 | `_vpos=null` + `invalidateFieldCache()` |

---

## 5. 参数

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| FIELD_R | 60 mm | 20-200 | 影响半径，约Cell间距2倍 |
| pressureMin | 0 | 用户定义 | 归一化下界(对应蓝色) |
| pressureMax | 100 | 用户定义 | 归一化上界(对应红色) |
| coverageThreshold | 0.01 | 内部固定 | 置信度低于此不显色 |
| 距离度量 | Euclidean | — | 3D空间直线距离 |

---

## 6. 关键文件

| 文件 | 说明 |
|------|------|
| `src/3D编辑器原型.html` | 完整实现 (~950行, Wendland引擎+CSR+UI) |
| `src/tests/test_force_field.py` | 算法测试 29项 passed |
| `仿真/algorithms.py` | Python参考实现 WendlandC2Reconstructor |
| `仿真/output/all_metrics.csv` | 仿真定量结果 |
