# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for IrregularShapedLayout.exe
3D拟物Layout编辑器 v1.0"""
import os, sys

block_cipher = None
PROJECT = SPECPATH

# Data files (HTML + Three.js + icon)
datas = []
for pattern in [
    ('3D编辑器原型.html', '.'),
    ('download.png', '.'),
]:
    src = os.path.join(PROJECT, pattern[0])
    if os.path.isfile(src):
        datas.append((src, pattern[1]))

# Three.js libs
lib_dir = os.path.join(PROJECT, "lib")
if os.path.isdir(lib_dir):
    for root, dirs, files in os.walk(lib_dir):
        for f in files:
            src = os.path.join(root, f)
            dst = os.path.join("lib", os.path.relpath(src, lib_dir))
            datas.append((src, os.path.dirname(dst)))

a = Analysis(
    ['src/v1.0.0/main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
        'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore',
        'PySide6.QtNetwork', 'numpy',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    icon=os.path.join(PROJECT, 'download.png'),
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
