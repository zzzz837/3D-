"""PyInstaller runtime hook: set OCC DLL path before any imports."""
import os, sys

if getattr(sys, 'frozen', False):
    _root = sys._MEIPASS
    occ_core = os.path.join(_root, 'OCC', 'Core')
    paths = []
    if os.path.isdir(occ_core):
        os.add_dll_directory(occ_core)
        paths.append(occ_core)
    if os.path.isdir(_root):
        os.add_dll_directory(_root)
        paths.append(_root)
    if paths:
        os.environ['PATH'] = ';'.join(paths) + ';' + os.environ.get('PATH', '')
        os.environ.setdefault('OCCT_ESSENTIALS_ROOT', _root)
