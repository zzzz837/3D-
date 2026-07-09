# Version 验收文档 — 3D 拟物 Layout 编辑器 v1.0 (as-built)

> **文档版本**: 2.0 | **日期**: 2026-07-03
> **构建状态**: v1.0.0 可执行文件已产出 (`IrregularShapedLayout.exe` + `_internal`, ~851MB)
>
> **适用 Version**: v1.0（全量 Stage1-5 完成后验收）
>
> **验收原则**: 零上下文可验收 — 任何 Agent 仅凭本文档 + 仓库代码即可独立执行验收并判定通过/失败。
>
> **as-built 注意事项**:
> - v1.0.0 仅支持 STL 模型导入 (非 OBJ/GLTF)
> - 不使用 QML 面板 (纯 QWidget UI)
> - Bridge 为 console.log 拦截模式 (非 QWebChannel)

---

## 1. 验收范围

### 覆盖内容
- 全部功能需求组 (FR-01 ~ FR-21)
- 全部 4 项非功能需求 (NFR-01 ~ NFR-04)
- Stage1~Stage5 全部交付物
- 跨 Stage 集成流程（启动→导入模型→编辑→预览→保存 全链路）

### 不覆盖内容
- 硬件连接（编辑器不连接传感器设备）
- macOS / Linux 兼容性（仅 Windows 10/11）
- 后续版本扩展功能（OBJ/GLTF 导入/批量放置/自动保存）

---

## 2. 验收环境

| 维度 | 要求 |
|------|------|
| 操作系统 | Windows 10/11 64-bit |
| Python | 3.10+ |
| 依赖 | PySide6 6.9+, numpy 1.26+, 内置模块 (json, struct, base64) |
| 3D 引擎 | Three.js r160 (通过 QWebEngineView 加载 HTML) |
| 构建 | `python -m src.main` 直接运行 (开发模式) |
| 打包 | `IrregularShapedLayout.exe` (PyInstaller `--onedir` 模式) |
| 测试数据 | 手套模型.stl (约150万面, 已验证可加载) |
| 分辨率 | ≥ 1024×700 |

---

## 3. 前置条件

- [ ] 全部 5 个 Stage 的验收已通过（Stage 验收文档签名通过）
- [ ] 全部 5 个 Stage 的完成报告已产出
- [ ] 所有 Stage 问题清单无未关闭的置顶区问题
- [ ] `pytest tests/` 全量单元测试通过
- [ ] `LayoutEditor3D.exe` 已构建（如需要打包验收）

---

## 4. 验收项

### V1. 版本完整性

- **目的**: 验证全量交付物存在且内容完整
- **前置条件**: Stage1-5 全部完成
- **操作步骤**:
  1. 检查 `3D拟物Layout开发文档/` 下所有文档
  2. 检查 `src/` 目录结构是否符合 Stage1-5 设计
  3. 检查 `qml/` 目录下所有 QML 组件
- **期望结果**: 文件结构与设计文档一致，无残留 `TODO` / `FIXME` / `pass`
- **通过标准**: 文件清单与 Stage1-5 各总体计划中"文件结构"一致
- **失败标准**: 任一指定文件缺失或为空
- **证据要求**: `dir /s src\ qml\ > file_list.txt`

---

### V2. 全业务流程 (端到端)

- **目的**: 验证从零到最终配置文件输出的完整用户工作流
- **前置条件**: 应用正常启动
- **操作步骤**:
  1. 启动应用 (`python -m src.main`)
  2. 点击"新建"→ 选择 STL 模型文件 → 自动加载并渲染
  3. 在放置模式下点击曲面放置 5 个 Cell
  4. 选中 #0，通过属性面板修改边长、旋转
  5. 选中 #1 删除 → 撤销(Ctrl+Z)恢复
  6. 保存(Ctrl+S) → 导出 JSON 文件
  7. 关闭应用 → 重新打开 → 打开上一步保存的 JSON → 验证 Cell 恢复一致
  8. Tab 切换到预览模式 → 验证手柄隐藏
  9. 3D 预览 → 验证动画运行
  10. 验证 2D 预览降维功能
- **期望结果**: 全程无崩溃、无异常日志、每个操作都有正确的 UI 反馈
- **通过标准**: 10 步全部成功，JSON round-trip 数据一致
- **失败标准**: 任一步骤崩溃、数据丢失、UI 异常
- **证据要求**: 每步截图 + 最终 JSON 文件 content diff

---

### V3. 格式兼容性

- **目的**: 验证 v1.3 ↔ v2.0 双向兼容
- **前置条件**: V2 通过
- **操作步骤**:
  1. 用编辑器打开 v1.3 JSON（XY 参考平面显示）
  2. 验证 Cell 在 XY 参考平面正确渲染（z=0）
  3. 导入 3D 曲面模型 → 升级向导 → Z 轴投影 → 确认
  4. 保存为 v2.0 JSON
  5. 重新打开 v2.0 JSON → 验证恢复正确
  6. 降维导出为 v1.3 → 对比与原 v1.3 的差异
- **期望结果**: v2.0 round-trip 一致；降维导出的 v1.3 结构与原始 schema 兼容
- **通过标准**: JSON diff 仅含预期字段变化(version/surface_model)，Cell 数据一致
- **失败标准**: round-trip 后数据丢失或变化
- **证据要求**: diff 命令输出

---

### V4. 性能基准

- **目的**: 验证性能达标
- **前置条件**: 应用正常启动, 加载手套模型.stl (约150万面)
- **操作步骤**:
  1. 导入模型 → 记录加载耗时 (Three.js JS解析, 不应 > 15s)
  2. 放置 200 个 Cell → 3D 视口中 Orbit 旋转 → 观察帧率 (≥ 25fps)
  3. 打开 3D 预览 → 观察帧率
  4. 任务管理器查看内存占用
- **期望结果**: 视口帧率 ≥ 25fps, 预览帧率 ≥ 50fps, 内存 < 2GB
- **通过标准**: 全部达标
- **失败标准**: 任一指标未达标
- **证据要求**: 计时日志、FPS 计数器截图、任务管理器截图

---

### V5. 撤销/重做完整性

- **目的**: 验证 UndoStack 深度与合并逻辑
- **操作步骤**:
  1. 连续放置 5 个 Cell
  2. Ctrl+Z 5 次 → 验证全部移除 (回到空项目)
  3. Ctrl+Y 5 次 → 验证全部恢复
  4. 拖拽 #0 大范围移动 → 释放 → Ctrl+Z → 验证一步回到初始位置
  5. 放置 #1 → 修改边长 → 修改旋转 → Ctrl+Z 3 次 → 验证依次撤销
  6. 所有操作完成后检查 Undo/Redo 按钮状态
- **通过标准**: 所有操作正确撤销/重做, 按钮状态正确, UndoStack 深度 50 无溢出
- **失败标准**: 任一操作 undo/redo 失败或数据不一致
- **证据要求**: 每步 before/after 截图

---

### V6. 异常与边界

- **目的**: 验证异常场景下的稳定性
- **操作步骤**:
  1. 打开不存在的 .json 文件 → 检查错误弹框
  2. 导入损坏的 STL (手动构造) → 检查错误弹框
  3. 导入超大面数模型 → 检查性能降级策略
  4. 所有 Cell 落地后继续拖拽 → 检查"所有 Cell 已落地"提示
  5. 修改 JSON 中 version 为 "9.9" → 打开 → 检查错误提示
  6. 快速连续 Ctrl+Z 直到空栈 → 检查不再崩溃
  7. 关闭未保存项目 → 检查确认对话框 → 取消
- **通过标准**: 所有异常以错误对话框呈现, 不崩溃, 不静默忽略
- **失败标准**: 崩溃、静默失败、无错误提示
- **证据要求**: 每个异常场景的错误对话框截图

---

### V7. 离线运行

- **目的**: 验证不依赖外部网络
- **操作步骤**:
  1. 断开网络连接
  2. 启动应用
  3. 导入 STL 模型 → 放置 Cell → 保存
  4. 验证 Three.js 所有功能正常工作
- **通过标准**: 全功能离线可用
- **失败标准**: 任何功能因网络不可达而失败
- **证据要求**: 断网状态下截图

---

## 5. 失败与阻塞处理

| 情况 | 处理方式 |
|------|---------|
| 验收项失败 | 标记"失败"，记录具体失败步骤和期望/实际的差异，退回对应 Stage 修复。修复后重新执行该验收项 + 回归相关验收项 |
| 验收标准不清 | 暂停，"阻塞"，追加到 Version 问题清单置顶区，等待文档补充 |
| 环境不满足 | 标记"阻塞"，记录缺失的环境条件 |
| 3 次修复仍失败 | 上升至 MainAgent 重新规划 Stage 拆分 |

---

## 6. 回归范围

| 功能 | 回归策略 |
|------|---------|
| 所有 FR-01~FR-17 | 全量验收 (见 §4 各验收项) |
| Stage1 模型导入 | 冒烟测试 (导入 3 种格式) |
| Stage2 Cell 编辑 | 全量操作路径 |
| Stage3 UI 面板 | 全量面板检查 |
| Stage4 预览+兼容 | 全量预览 + round-trip |
| Stage5 性能+打包 | 基准测试 |

---

## 7. 交付物检查

- [ ] 需求规格-3DLayout编辑器.md (v2.0)
- [ ] 问题清单-3DLayout编辑器.md (全部关闭)
- [ ] Version 验收文档.md (本文档)
- [ ] 最终检查-工作计划.md
- [ ] 3D拟物Layout开发文档/Stage1-5/ 全部设计文档
- [ ] 3D拟物Layout开发文档/Stage1-5/ 全部问题清单.md
- [ ] 3D拟物Layout开发文档/Stage1-5/ 全部验收文档.md
- [ ] src/ 目录全部代码
- [ ] 3D编辑器原型.html (Three.js 3D 引擎)
- [ ] tests/ 目录全部测试
- [ ] IrregularShapedLayout.spec (PyInstaller 打包脚本)
- [ ] dist/IrregularShapedLayout/IrregularShapedLayout.exe

---

## 8. 验收签字

| 角色 | 姓名/ID | 日期 | 结论 |
|------|---------|------|------|
| MainAgent | | | |
| 验收 Agent | | | |

**结论**: □ 通过 / □ 失败 / □ 阻塞

---

## 9. beta4 进展 (2026-07-08 ~ 2026-07-09)

### 9.1 已解决问题

| # | 问题 | 方案 |
|---|------|------|
| 1 | Wendland力场三模式 | manual/simulated/real 数据源 + vertexColors 渲染 |
| 2 | 压力归一化方案B | 用户定义 pressureMin/pressureMax 固定范围 |
| 3 | 专用压力输入框 | propPressure 独立于 label，label 改为备注 |
| 4 | 工具栏重构 | 力场预览/模拟压力/导入数据 + 力场设置面板 |
| 5 | 模拟压力(正弦波) | 每Cell独立动态pressure，与力场预览解耦 |
| 6 | JSON导入格式 | `{"cells":{id:value},"range":[min,max]}` |
| 7 | 性能缓存架构 | _vpos(18MB) + CSR Influence Cache + _cv覆盖顶点遍历 |
| 8 | 手动模式零持续开销 | 仅压力变化时着色；模拟模式500ms间隔 |
| 9 | 代码清理 | 删除_recompute死代码、重复pressure键、_hotspots |
| 10 | 缺口检测移除 | 删除detectGaps/clearGaps函数+UI(~27行) |
| 11 | 性能二次优化 | applyFieldColors只遍历_cv，不清除150万顶点(↓93%) |
| 12 | .3dlp模型加载bug | setupModel加_needsRender + model_format字段 + 文件验证 |
| 13 | pressure保存丢失 | _on_export补全pressure字段 |
| 14 | _dirty标记 | state消息触发dirty=True，loading期屏蔽 |

### 9.2 测试

```
36/36 passed (test_force_field 29 + test_main 7)
```

---

## 10. v1.0.1 进展 (2026-07-09)

### 10.1 已解决问题

| # | 问题 | 方案 |
|---|------|------|
| 1 | 删除导入数据模式 | real mode/importFieldJSON/_importedField/tbImportField全面清理 |
| 2 | 压力归一化0~1 | 删除pressureMin/pressureMax UI+变量+readPressureRange |
| 3 | propPressure 0~1 | placeholder "0~1"，clamp [0,1]，保存为0~1小数 |
| 4 | 模拟压力三预设 | Uniform(0.2~0.8)/Wave(0.15~0.85)/Pulse(0.1~1.0) |
| 5 | 模拟预设UI | 独立下拉框，仅模拟模式显示，默认Wave |
| 6 | 帧率优化 | SIM_INTERVAL_MS=40 (25FPS)，performance.now()计时 |
| 7 | 大模型优化提示 | optRow显示"性能优化已启用" |
| 8 | BVH容错 | computeBoundsTree失败→回退THREE.Mesh.prototype.raycast |
| 9 | loadStl入口清理 | 清理timers/preview/M/cache，保留unitMM/radius/MAX |
| 10 | .3dlp全链路日志 | Python(文件/cache/URL)+JS(fetch/parse/setup)+失败弹窗 |
| 11 | 项目切换清理(Q19) | loadStl入口轻量清理(不清unitMM/radius/MAX) |
| 12 | STP力场预览(Q20) | BVH容错确保STP射线检测可用 |
| 13 | STP.3dlp模型丢失(Q21) | loadStl清理确保旧场景完全移除 |
| 14 | clearGapSpheres报错(Q22) | 删除resetAll中无效调用 |
| 15 | Cell贴合精度(Q23) | BVH失败→原生raycast确保正确射线 |
| 16 | 力场重建起点(Q24) | 同Q23修复确保Cell位置正确 |

### 10.2 测试

```
45/45 passed (test_force_field 29原有 + 9预设 + test_main 7)
```

### 10.3 已知遗留

| # | 问题 | 状态 |
|---|------|------|
| 1 | **大面片STL(~150万面)导入失败/超时** | 待排查 — 可能STLLoader.parse主线程解析超时或内存不足 |
| 2 | **STP模型力场预览不显示热力图** | 待排查 — Cell位置恢复正确但Wendland重建不生效 |
| 3 | STP转换后Cell比例可能偏小 | 与autoDetectUnit/setUnit时序相关 |
| 4 | OBJ多mesh仅加载第一个 | 不影响当前使用(STP→STL为主) |

### 10.4 改动文件

| 文件 | 改动量 | 说明 |
|------|--------|------|
| `src/3D编辑器原型.html` | +121/-53 | v1.0.1全部JS改动 |
| `src/main.py` | +15/-0 | Python侧日志+错误弹窗 |
| `src/tests/test_force_field.py` | +93 | 9项模拟预设测试 |
| `document/update/v1.0.1/` | 新增 | 版本需求+问题清单 |
