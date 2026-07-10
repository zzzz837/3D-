# v1.0.1 进展记录

> **日期**: 2026-07-09 | **版本**: v1.0.1 稳定演示版

---

## 背景

v1.0.1 基于 beta4 已验收能力，目标：删减未成熟功能、优化大模型体验、提升模拟演示效果。

---

## 一、已解决 (16项)

### 功能

| # | 需求 | 方案 |
|---|------|------|
| F1 | 删除导入数据模式 | real mode / importFieldJSON / _importedField / tbImportField / 菜单项全面清理 |
| F2 | 压力归一化 0~1 | 删除 pressureMin/Max UI+变量+readPressureRange；applyFieldColors 硬编码 [0,1] |
| F3 | propPressure 输入 | placeholder "0~1"，自动 clamp [0,1]，保存为 0~1 小数 |
| F4 | 模拟压力三预设 | Uniform(0.2~0.8) / Wave(0.15~0.85) / Pulse(0.1~1.0)，全部输出到 `C[id].pressure` |
| F5 | 模拟预设 UI | 独立下拉框，仅模拟模式显示，默认 Wave |
| F6 | 帧率优化 | SIM_INTERVAL_MS=40 (25FPS)，`performance.now()` 计时 |
| F7 | 大模型提示 | 面数 >50万 显示"大模型，性能优化已启用" |
| F8 | 打开工程不自动预览 | loadStl 流程中不调用 togglePreview，保持编辑状态 |

### Bug 修复

| # | 问题 | 修复 |
|---|------|------|
| B1 | BVH 失败致 Cell/力场异常 | `computeBoundsTree()` 加 try/catch，失败→回退 `THREE.Mesh.prototype.raycast` |
| B2 | 切换项目残留 | loadStl 入口轻量清理 (timers/preview/M/cache)，保留 unitMM/radius/MAX |
| B3 | .3dlp 模型丢失排查 | Python + JS 全链路日志 (文件/cache/URL/fetch/parse/setup) |
| B4 | JS 失败无提示 | `sendBridge('error')` → Python `QMessageBox.warning` 弹窗 |
| B5 | clearGapSpheres 报错 | 删除无效调用 |
| B6 | STP 力场不显示 | BVH 容错修复，力场链路 `Cell→pressure→Wendland→vertexColor` 统一 |
| B7 | STP Cell 贴合异常 | BVH 回退原生 raycast 确保射线正确 |
| B8 | 导入数据残留 UI | 按钮/隐藏input/菜单/select option 全部删除 |

### 回归保护

| 模块 | 状态 |
|------|------|
| Wendland C2 核函数 | 不改 |
| CSR Influence Cache | 不改 |
| _cv 覆盖顶点遍历 | 不改 |
| 手动压力输入 | 字段独立 |
| pressure 保存/恢复 | 完整保留 |
| 力场半径 slider | 不变 |
| Jet colormap | 不变 |

---

## 二、测试

```
45/45 passed
  test_force_field: 29 原有 + 9 模拟预设 (Uniform/Wave/Pulse) + 7 test_main
```

---

## 三、改动文件

| 文件 | 说明 |
|------|------|
| `src/3D编辑器原型.html` | v1.0.1 全部 JS 改动 (~120行) |
| `src/main.py` | Python 日志 + 错误弹窗 (~15行) |
| `src/tests/test_force_field.py` | 9 项模拟预设测试 (~93行) |
| `document/update/v1.0.1/版本需求.md` | v1.0.1 需求文档 |
| `document/update/v1.0.1/问题清单.md` | Q1-Q24 问题清单 + 用户答复 |

---

## 四、已知遗留 (2项)

| # | 问题 | 现象 | 排查方向 |
|---|------|------|---------|
| **L1** | 大面片 STL (~150万面) 导入失败 | 新建项目或打开 .3dlp 均无法加载大模型 | 可能 STLLoader.parse 主线程超时/内存不足；需增加超时提示或分片解析 |
| **L2** | STP 模型力场预览不显示热力图 | STP 导入后 Cell 位置正常但点"力场预览"无热力图 | 可能力场链路中 M/mesh/C/cache 初始化不完整；需对比 STL 流程排查 |

---

## 五、v1.0.1 未开发范围 (by design)

- 真实 ADC 接入
- CSV/JSON 数据导入
- 时间序列回放 / 时间轴
- MLS / Graph Laplacian
- GPU Shader 重构 / WebGPU / 多线程
- 降采样 (SimplifyModifier 已移除，待后续)
