import os
import sys
import threading
import http.server
import socket
import subprocess
import tempfile
from pathlib import Path

from core.exceptions import STPConversionError, DecimationError


def start_server(root_dir):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=root_dir, **kwargs)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(('127.0.0.1', port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return port


def convert_step_to_stl_bytes(step_path, converter_script, log_cb=None):
    if log_cb is None:
        log_cb = lambda msg: None

    tmp_out = os.path.join(tempfile.gettempdir(), f"_stp_convert_{os.getpid()}.stl")

    log_cb(f"=== STP转换开始: {step_path} ===")
    if not os.path.isfile(converter_script):
        raise FileNotFoundError(f"找不到转换器: {converter_script}")

    converted = False
    try:
        _conv_dir = os.path.dirname(converter_script)
        if _conv_dir not in sys.path:
            sys.path.insert(0, _conv_dir)
        from stp_converter import convert_step_to_stl
        log_cb("in-process convert started")
        convert_step_to_stl(step_path, tmp_out)
        converted = True
        log_cb("in-process convert done")
    except ImportError as e:
        log_cb(f"in-process ImportError: {e}, trying subprocess")
    except Exception as e:
        log_cb(f"in-process failed: {type(e).__name__}: {e}, trying subprocess fallback")

    if not converted:
        python_exe = _find_python_exe()
        log_cb(f"subprocess python={python_exe}")
        result = subprocess.run(
            [python_exe, converter_script, step_path, tmp_out],
            capture_output=True, text=True, timeout=300
        )
        if result.stdout:
            log_cb(f"stdout: {result.stdout[:500]}")
        if result.stderr:
            log_cb(f"stderr: {result.stderr[:500]}")
        if result.returncode != 0:
            raise RuntimeError(
                f"转换失败 (rc={result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip() or '?'}"
            )

    log_cb(f"tmp_out exists={os.path.isfile(tmp_out)} "
           f"size={os.path.getsize(tmp_out) if os.path.isfile(tmp_out) else 0}")

    raw = Path(tmp_out).read_bytes()
    try:
        os.unlink(tmp_out)
    except Exception:
        pass

    if not raw or len(raw) < 84:
        raise STPConversionError(f"转换结果为空或无效STL (size={len(raw)})")

    face_count = int.from_bytes(raw[80:84], 'little')
    log_cb(f"output STL: {len(raw)} bytes, {face_count} faces")
    if face_count == 0:
        raise STPConversionError("转换结果STL面数为0")

    return raw, face_count


def decimate_stl(raw, log_cb=None):
    if log_cb is None:
        log_cb = lambda msg: None

    if len(raw) <= 84:
        return raw, False, 0, 0

    original_faces = int.from_bytes(raw[80:84], 'little')
    if original_faces <= 200000:
        return raw, False, original_faces, 0

    before_bytes = len(raw)
    target = 300000
    reduction = 1.0 - (target / original_faces)
    actual_faces = 0
    decimated = False

    try:
        import trimesh
        mesh = trimesh.load(trimesh.util.wrap_as_stream(raw), file_type='stl')
    except Exception as e:
        log_cb(f"降采样: trimesh.load 失败: {e}")
        return raw, False, original_faces, 0

    if mesh.faces.shape[0] <= 200000 or not (0 < reduction < 1):
        return raw, False, original_faces, 0

    simplified = None
    sim_ok = False
    try:
        simplified = mesh.simplify_quadric_decimation(reduction)
        sim_ok = simplified is not None and simplified.faces.shape[0] > 0
    except ImportError:
        log_cb("降采样: 缺少 fast_simplification 模块, 无法降采样")
    except ValueError as ve:
        log_cb(f"降采样: 参数错误 (reduction={reduction:.4f}): {ve}")
    except Exception as se:
        log_cb(f"降采样: 异常: {type(se).__name__}: {se}")

    if sim_ok:
        new_raw = simplified.export(file_type='stl')
        if new_raw and len(new_raw) > 84:
            actual_faces = simplified.faces.shape[0]
            if actual_faces < original_faces:
                decimated = True
                after_bytes = len(new_raw)
                log_cb(f"降采样成功: {original_faces}→{actual_faces}面 "
                       f"| {before_bytes}→{after_bytes}bytes")
                return new_raw, decimated, original_faces, actual_faces

    return raw, False, original_faces, 0


def _find_python_exe():
    conda_prefix = os.environ.get('CONDA_PREFIX', '')
    if conda_prefix:
        candidate = os.path.join(conda_prefix, 'python.exe')
        if os.path.isfile(candidate):
            return candidate
    for candidate in [
        r'D:\Anaconda\envs\3d-editor\python.exe',
        r'D:\Anaconda\python.exe',
    ]:
        if os.path.isfile(candidate):
            return candidate
    raise RuntimeError("未找到可用的 Python 解释器 (需 pythonocc-core)")
