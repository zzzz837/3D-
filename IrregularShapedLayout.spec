# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for IrregularShapedLayout.exe
3D拟物Layout编辑器 v1.0 — PyQt5 build"""
import os, sys

block_cipher = None
PROJECT = SPECPATH

datas = []

# Icon
icon_src = os.path.join(PROJECT, 'download.png')
if os.path.isfile(icon_src):
    datas.append((icon_src, '.'))

# Entry point HTML
html_src = os.path.join(PROJECT, 'src', '3D编辑器原型.html')
if os.path.isfile(html_src):
    datas.append((html_src, 'src'))

# STP converter
stp_src = os.path.join(PROJECT, 'src', 'stp_converter.py')
if os.path.isfile(stp_src):
    datas.append((stp_src, 'src'))

# Three.js vendored libs (under src/lib/three/)
lib_dir = os.path.join(PROJECT, 'src', 'lib')
if os.path.isdir(lib_dir):
    for root, dirs, files in os.walk(lib_dir):
        for f in files:
            src = os.path.join(root, f)
            dst = os.path.join('src', 'lib', os.path.relpath(src, lib_dir))
            datas.append((src, os.path.dirname(dst)))

# OCC (pythonocc-core) — collect ALL DLLs from conda Library/bin
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files
binaries = collect_dynamic_libs('OCC')
datas += collect_data_files('OCC')
occ_dir = os.path.dirname(__import__('OCC').__file__)
for root, dirs, files in os.walk(occ_dir):
    for f in files:
        if f == '__init__.py':
            src = os.path.join(root, f)
            dst = os.path.relpath(root, occ_dir)
            datas.append((src, 'OCC/' + dst.replace('\\', '/')))
# Gather ALL DLLs from conda Library/bin (not just TK-prefixed)
conda_lib_bin = os.path.join(os.path.dirname(sys.executable), 'Library', 'bin')
if os.path.isdir(conda_lib_bin):
    for f in os.listdir(conda_lib_bin):
        fp = os.path.join(conda_lib_bin, f)
        if os.path.isfile(fp) and f.lower().endswith('.dll'):
            # Skip Qt5/PyQt DLLs (PyInstaller handles those via hooks)
            if f.lower().startswith('qt') or f.lower().startswith('pyqt'):
                continue
            binaries.append((fp, 'OCC/Core'))

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
        'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngineCore',
        'PyQt5.QtNetwork', 'PyQt5.QtWebChannel',
        # pythonocc-core for STEP/STP conversion
        'OCC', 'OCC.Core', 'OCC.Core.STEPControl', 'OCC.Core.BRepMesh',
        'OCC.Core.StlAPI', 'OCC.Core.TopoDS', 'OCC.Core.TColStd',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(PROJECT, 'pyi_rth_occ.py')],
    excludes=['tkinter', 'matplotlib', 'scipy', 'IPython'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='IrregularShapedLayout',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='IrregularShapedLayout',
)
