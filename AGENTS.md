## Project Overview
3D拟物Layout编辑器 — 3D Skeuomorphic Layout Editor for placing tactile sensor cells on 3D curved surfaces (gloves, insoles, etc.).

**Tech Stack:** Python 3.10+ / PySide6 6.9+ desktop container + Three.js r160 WebGL engine via QWebEngineView.
**Target:** Windows 10/11 64-bit, offline, WebGL 2.0 required.
**Max cells:** 200, **Undo depth:** 100.

## Directory Convention
- `src/` — all application code:
  - `main.py` — entry point
  - `core/` — data models & geometry (model.py, geometry3d.py, basket.py, exceptions.py)
  - `render/` — STL importers (model_importer.py)
  - `qml/` — Qt Quick UI components (ToolBar, CellBasket, PropertyPanel, ChannelTable, StatusBar, Viewport3D)
  - `tests/` — pytest tests (test_model.py, test_geometry3d.py)
  - `3D编辑器原型.html` — Three.js embedded engine page
  - `download.png` — app icon
  - `手套模型.stl` — test STL model
- `thirdparty/three/` — vendored Three.js r160 + three-mesh-bvh 0.7.3 + OrbitControls + STLLoader
- `document/` — organized by function:
  - `01-产品定义与需求/` — requirements spec + version acceptance
  - `02-问题与验收/` — issue tracker
  - `03-工作计划/` — work plan + stage planning
  - `04-技术开发/` — dev standards, data schema, architecture, UI design, rendering, dependencies/packaging
  - `05-构建配置/` — PyInstaller .spec
  - `update/vX.Y.Z/` — versioned stage documents + built .exe + _internal runtime

## Key Commands
- Run dev: `python src/main.py`
- Run tests: `pytest src/tests/ -v`
- Build package: `pyinstaller IrregularShapedLayout.spec --noconfirm`

## Architecture Notes
- Hybrid Python+JS: QMainWindow hosts QWebEngineView; Three.js runs as embedded HTML with importmap
- Bridge: Python ↔ JS via `runJavaScript()` and `console.log()` intercept (BridgePage)
- Rendering: on-demand via `_needsRender` flag; BVH ray casting via `three-mesh-bvh` 0.7.3
- Cell surface conformity: 10×10 subdiv vertex ray projection
- Coordinate system: unitMM, model units vs real mm

## Non-Project File
- `add_vscode_context_menu.reg` is a local dev utility for Windows Explorer right-click. Not part of application logic.
