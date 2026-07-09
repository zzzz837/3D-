# beta4.0 验收记录

> **日期**: 2026-07-09 | **版本**: v1.0.0-beta4

---

## 一、当前已完成能力

### 1.1 力场数据源 (三种模式)

| 模式 | 数据源 | UI入口 |
|------|--------|--------|
| **手动压力** | `C[id].pressure` 用户输入 | 属性面板 → 压力值 |
| **模拟压力** | 每Cell独立正弦波动态pressure | 工具栏 → 模拟压力 |
| **导入数据** | JSON `{"cells":{id:value}, "range":[min,max]}` | 工具栏 → 导入数据 |

### 1.2 压力映射

| 功能 | 状态 |
|------|------|
| 专用 `propPressure` 输入框 (独立于 label) | ✅ |
| 压力范围 `pressureMin / pressureMax` 用户可设 | ✅ |
| 固定范围归一化 `t = (p - min) / (max - min)` | ✅ |
| Jet colormap (蓝→青→绿→黄→红) | ✅ |
| Cell A=10 vs Cell B=100 → 热力图差异明显 | ✅ |
| `C[id].pressure` 统一数据源 (Cell marker + Mesh 共用) | ✅ |

### 1.3 UI

| 组件 | 内容 |
|------|------|
| 工具栏 | 力场预览 / 模拟压力 / 导入数据 / 放置模式 / 线框 / 重置视角 / 编辑模式 |
| 属性面板(选中Cell) | ID / XYZ / 法向 / 半径 / **标签(备注)** / **压力值** / 面积 / 旋转 / 碰撞检测 |
| 属性面板(力场设置) | 模式select / 压力范围 / 力场半径slider |
| 菜单栏 | 文件/编辑/视图(力场预览+模拟压力+导入数据+线框+重置)/工具(碰撞检测) |

### 1.4 力场预览行为

| 操作 | 行为 |
|------|------|
| 仅开启力场预览 | 显示当前 pressure 对应的静态热力图，不刷新 |
| 开启预览 + 模拟压力 | 压力动态变化 + 热力图定期更新 |
| 关闭模拟 | pressure 停止变化，热力图冻结 |
| 关闭预览 | 恢复模型材质，停止所有刷新 |
| 预览中修改压力值 | 手动模式即时更新；模拟模式下次周期更新 |
| Cell 移动 | 热斑跟随移动 + 自动重建影响缓存 |

### 1.5 导入/导出

| 功能 | 支持 |
|------|------|
| 项目保存/加载 (JSON) | ✅ `pressure` 字段 |
| Cell 导入/导出 (Bridge) | ✅ `pressure` 字段 |
| 力场 JSON 导入 | ✅ `cells` + 可选 `range` |

### 1.6 已移除

| 功能 | 原因 |
|------|------|
| 🔍 缺口检测 | 用户要求移除 |
| `_hotspots` 热点漂移 | 替换为每Cell独立动态pressure |
| `_recompute` 死代码 | 全代码库无引用 |
| `importCells` 重复 pressure 键 | 代码清理 |

---

## 二、性能分析 (暂不改动)

### 2.1 当前架构

```
┌─ rebuildFieldCache() ─────────────────────────────┐
│  触发: cell增删移动 / FIELD_R变化 / 模型加载       │
│  耗时: 2-5s (150万面, 一次性)                      │
│  产物: _vpos (18MB) + Influence Cache (CSR格式)    │
└───────────────────────────────────────────────────┘

┌─ applyFieldColors() ──────────────────────────────┐
│  手动: 仅 pressure 变化时调用                       │
│  模拟: setInterval 500ms                            │
│  耗时: ~100-300ms (150万面, 取决于覆盖顶点数)       │
│  操作: 遍历1.5M顶点 → 查CSR权重 → 加权 → jetColor  │
└───────────────────────────────────────────────────┘
```

### 2.2 卡性能的地方 (按影响排序)

#### 瓶颈1: 全量顶点遍历 (主要)

`applyFieldColors` 中 `for(let i=0;i<n;i++)` 遍历全部 **150万** 顶点。

- 即便未覆盖顶点 (`s===e`) 直接跳过，JS 循环本身的迭代和条件判断就有开销
- **影响**: 模拟模式下每 500ms 跑一次，造成持续 CPU 占用
- ~~**不改原因**: 需要遍历所有顶点才能清除上一帧的颜色~~ 
- **✅ 已修复 (二次优化)**: `applyFieldColors` 只遍历 `_cv` (覆盖顶点), 不再全量遍历。清灰移至 `rebuildFieldCache` 和 `invalidateFieldCache` (一次性)

#### 瓶颈2: 每顶点对象创建

- ~~`jetColor(t)` 每次调用创建 `new T.Color(...)`~~ → **✅ 已缓解** (只对覆盖顶点创建，数量从150万降到5-10万)
- ~~`MODEL_GREY.clone().lerp(jc, confidence)`~~ → **✅ 已缓解**
- **影响**: GC 压力大幅降低
- **不改原因**: Three.js API 限制，需用 `new T.Color()` / `.clone()` / `.lerp()` 设置颜色

#### 瓶颈3: DOM 读取每帧

当前 `updateHeatmap()` 中 `readPressureRange()` 读取 `D('propPressureMin').value` / `D('propPressureMax').value`，即使值没变也触发 DOM 访问。

- **影响**: 微小 (每帧2次 DOM read)，但可消除
- **不改原因**: 当前影响很小，不是主要瓶颈

#### 瓶颈4: JSON.stringify 缓存键

`const pkey=JSON.stringify(cellPressures)` 用于检测压力是否变化。

- Cell 数少时开销可忽略 (<50 cells)；Cell 数极大时(>1000)可能有开销
- **影响**: 微小，当前 Cell 数量有限
- **不改原因**: 开销远小于颜色计算，且已有效防止重复渲染

#### 瓶颈5: Influence Cache 首次构建

`rebuildFieldCache()` 首次调用需 2-5 秒。

- 两遍扫描 150万顶点 + 空间分桶查询 per vertex
- **影响**: 一次性，用户首次点"力场预览"时有等待
- **不改原因**: 只在 cell/半径变化时才重建，频率低

#### 瓶颈6: 渲染本身 (GPU)

`colArr.needsUpdate=!0` 触发 GPU 端 buffer 更新。

- 150万顶点 × 3 float × 4 bytes = 18MB 数据上传到 GPU
- `vertexColors` 启用后 GPU shader 需读取额外颜色属性
- **影响**: 这是必须的渲染成本，不是算法问题
- **不改原因**: WebGL 限制，无法避免

### 2.3 瓶颈分级 (二次优化后)

| 级别 | 瓶颈 | 手动模式影响 | 模拟模式影响 | 状态 |
|------|------|-------------|-------------|------|
| ~~🔴 主要~~ | ~~#1 全量遍历 150万顶点~~ | 无 | ~~每500ms~~ → 仅覆盖顶点 | ✅ 已修复 |
| 🟡 中等 | #2 每顶点对象创建 | 无 | 仅覆盖顶点 (~5-10万,大幅降低) | ✅ 已缓解 |
| 🟢 微小 | #3 DOM 读取 | 无 | 每500ms | 可优化 |
| 🟢 微小 | #4 JSON.stringify | 无 | 每500ms | 可优化 |
| 🟡 中等 | #5 Cache首次构建 | 一次性 | 一次性 | 可后台 |
| 🔵 必须 | #6 GPU渲染 | 仅一次 | 每500ms | 硬件限制 |

### 2.4 二次优化详解 (性能二次优化)

**修正的错误判断**: 之前认为必须遍历全部150万顶点去清除旧颜色。实际上：
- 清灰只发生在 `rebuildFieldCache` (cell/半径变化，一次性) 和 `invalidateFieldCache` (cell变化时)
- 逐帧着色 (`applyFieldColors`) 只遍历 `_cv` (覆盖顶点列表, Uint32Array)
- 覆盖顶点上一帧的颜色直接被新颜色覆盖，无需先清除

**实现**:
```
_cv (Uint32Array) — rebuildFieldCache 时预建，包含所有有影响的顶点索引
applyFieldColors — for(k=0;k<_cv.length;k++) 仅遍历覆盖顶点
invalidateFieldCache — 触发时全量清灰一次 (cell变化才会触发，频率低)
```

**预期效果 (150万面手套模型)**:
- 覆盖顶点约 5-10万 → `applyFieldColors` 遍历量减少 93-97%
- 手动模式: 零持续开销 (不变)
- 模拟模式: ~10-50ms/帧 (从 ~100-300ms 大幅降低)

### 2.4 核心算法不改动范围

| 模块 | 状态 |
|------|------|
| Wendland C2 核函数 `(1-r)^4*(4r+1)` | 不改 |
| Jet colormap | 不改 |
| 加权平均 `P = Σ(P*w) / Σw × min(1, Σw)` | 不改 |
| 空间分桶 (spatial buckets) | 不改 |
| Euclidean distance 度量 | 不改 |
| Influence Cache CSR 格式 | 不改 |
| `readPressureRange` / `getCellPressures` | 不改 |

### 2.5 为什么不继续优化

1. **手动模式已经够快**: 手动模式只在压力变化时调用一次 `applyFieldColors`，静态热力图，无持续开销
2. **模拟模式 100-300ms 可接受**: 500ms 间隔内能跑完，剩余 200ms+ 给 UI 响应
3. **剩余优化涉及 JS 层面的大改**: 用 TypedArray 直接计算颜色完全绕过 Three.js (不用 `jetColor`/`Color.lerp`/`setXYZ`)，改造成本高且收益递减
4. **瓶颈1的全量遍历**: 要避免必须先记录"哪些顶点在上帧被着色过"，引入状态管理复杂度

---

## 三、测试结果

```
单元测试: 36/36 passed
   test_force_field: 29/29 ✓ (Wendland/wendlandPhi/jetColor/归一化/manual/real/simulated)
   test_main: 7/7 ✓
启动测试: WebEngine load succeeded — 零错误
```

---

## 四、改动文件汇总

| 文件 | 状态 | 说明 |
|------|------|------|
| `src/3D编辑器原型.html` | 修改 ~300行 | 三轮迭代 |
| `src/tests/test_force_field.py` | 新增 270行 | 29项测试 |
| `document/...beta4/问题清单.md` | 更新 | Q1-Q10 闭环 + 性能优化 + 缺口移除 |
| `document/...beta4/完成报告.md` | 重写 | 三轮开发记录 |
| `document/...beta4/验收记录.md` | 新增 | 本文档 |
| `document/...beta4/beta4版本需求.md` | 更新 | 追加性能需求 + 移除缺口 |
