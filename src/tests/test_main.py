"""
单元测试 — 3D拟物Layout编辑器 beta2
测试范围: find_root, NewProjectDialog, ZIP package roundtrip, legacy JSON
"""
import sys, os, json, base64, zipfile, tempfile, io
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestFindRoot:
    """find_root() 应返回项目根目录"""

    def test_returns_valid_dir(self):
        from main import find_root
        root = find_root()
        assert os.path.isdir(root), f"find_root() 返回的目录不存在: {root}"
        assert os.path.isfile(os.path.join(root, "src", "3D编辑器原型.html")), \
            f"HTML文件不在预期位置: {root}/src/3D编辑器原型.html"


class TestNewProjectDialog:
    """NewProjectDialog 数据收集"""

    @pytest.fixture
    def dialog(self):
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        from main import NewProjectDialog
        dlg = NewProjectDialog()
        yield dlg
        dlg.close()

    def test_initial_values(self, dialog):
        """对话框初始值正确"""
        assert dialog.name_edit.text() == "未命名项目"
        assert dialog.channels_spin.value() == 200
        assert dialog.channels_spin.minimum() == 1
        assert dialog.channels_spin.maximum() > 200  # 无上限
        assert dialog.real_height.value() == 0

    def test_get_project_info_structure(self, dialog):
        """get_project_info() 返回正确的字段"""
        dialog.name_edit.setText("测试项目")
        dialog.channels_spin.setValue(50)
        # 模拟选择模型
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
            f.write(b"solid test\nfacet normal 0 0 0\nouter loop\nendloop\nendfacet\nendsolid\n")
            model_path = f.name
        dialog._model_path = model_path
        dialog.real_height.setValue(7.0)

        info = dialog.get_project_info()
        assert info["name"] == "测试项目"
        assert info["channels"] == 50
        assert info["model_path"] == model_path
        assert info["real_height"] == 70.0
        assert "device_type" not in info  # Q4 否决
        assert "description" not in info  # Q4 否决
        os.unlink(model_path)


class TestZipPackage:
    """ZIP 包 (.3dlp) 保存/打开 闭环测试"""

    def test_roundtrip_cells(self, tmp_path):
        """导出 cells → .3dlp → 解析后 cells 一致"""
        cells_data = [
            {"id": 0, "center_3d": {"x": 10.0, "y": 20.0, "z": 30.0},
             "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
             "radius_mm": 10.0, "width_mm": 20.0, "height_mm": 20.0,
             "rotation_deg": 0.0, "label": ""},
            {"id": 1, "center_3d": {"x": 40.0, "y": 50.0, "z": 60.0},
             "normal": {"x": 0.0, "y": 1.0, "z": 0.0},
             "radius_mm": 8.0, "width_mm": 16.0, "height_mm": 16.0,
             "rotation_deg": 45.0, "label": "ADC1"},
        ]
        project = {
            "version": "2.0",
            "project_name": "测试项目",
            "created_at": "2026-01-01T00:00:00",
            "total_points": 2,
            "unit_mm": 1.0,
            "surface_model": {"format": "stl", "file_name": "test.stl"},
            "cells": cells_data,
        }

        # 写入 .3dlp
        model_bytes = b"fake stl content"
        pkg_path = tmp_path / "test.3dlp"
        with zipfile.ZipFile(str(pkg_path), "w", zipfile.ZIP_DEFLATED) as zf:
            project_copy = json.loads(json.dumps(project))
            project_copy.pop("surface_model", None)
            project_copy["model_file"] = "test.stl"
            zf.writestr("project.json", json.dumps(project_copy, indent=2, ensure_ascii=False))
            zf.writestr("test.stl", model_bytes)

        # 读取 .3dlp
        with zipfile.ZipFile(str(pkg_path), "r") as zf:
            project_data = json.loads(zf.read("project.json").decode("utf-8"))
            assert "test.stl" in zf.namelist()
            raw_model = zf.read("test.stl")

        assert project_data["project_name"] == "测试项目"
        assert raw_model == model_bytes
        assert len(project_data["cells"]) == 2
        assert project_data["cells"][0]["id"] == 0
        assert project_data["cells"][0]["center_3d"]["x"] == 10.0
        assert project_data["cells"][1]["radius_mm"] == 8.0
        assert project_data["cells"][1]["label"] == "ADC1"

    def test_legacy_json_with_base64(self, tmp_path):
        """向后兼容: 打开旧版JSON（含 data_base64）"""
        legacy_data = {
            "version": "2.0",
            "display_name": "旧项目",
            "device_model": "Glove",
            "total_points": 5,
            "surface_model": {
                "format": "stl",
                "file_name": "old_model.stl",
                "data_base64": base64.b64encode(b"binary stl here").decode(),
            },
            "cells": [
                {"id": 0, "center_3d": {"x": 1.0, "y": 2.0, "z": 3.0},
                 "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
                 "radius_mm": 12.5, "rotation_deg": 30.0, "label": "test"},
            ],
        }
        path = tmp_path / "legacy.json"
        path.write_text(json.dumps(legacy_data, ensure_ascii=False), encoding="utf-8")

        # 模拟 Python 端解析
        data = json.loads(path.read_text(encoding="utf-8"))
        sm = data.get("surface_model", {})
        model_b64 = sm.get("data_base64", "")
        assert model_b64 == legacy_data["surface_model"]["data_base64"]
        raw = base64.b64decode(model_b64)
        assert raw == b"binary stl here"

        cells = data.get("cells", [])
        assert len(cells) == 1
        assert cells[0]["center_3d"]["x"] == 1.0


class TestStpConverter:
    """STEP 转换器 接口测试"""

    def test_no_args_exits(self):
        """无参数时报错"""
        import subprocess
        converter = os.path.join(os.path.dirname(__file__), "..", "stp_converter.py")
        result = subprocess.run(
            [sys.executable, converter],
            capture_output=True, timeout=10
        )
        assert result.returncode != 0

    def test_nonexistent_file(self):
        """文件不存在时返回非0"""
        import subprocess
        converter = os.path.join(os.path.dirname(__file__), "..", "stp_converter.py")
        result = subprocess.run(
            [sys.executable, converter, "/nonexistent/file.stp"],
            capture_output=True, timeout=10
        )
        assert result.returncode != 0
