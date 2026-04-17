# PyInstaller spec for GSBoard (Windows .exe build).
#
# Build:
#   pyinstaller gsboard.spec
#
# Output:
#   dist/GSBoard.exe  (single-file build — slower first launch since the
#   bootloader unpacks into a temp dir, but one portable artifact).

# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = []
# pynput picks its platform backend at runtime; PyInstaller's static analysis
# misses the win32 keyboard/mouse submodules without help.
hiddenimports += collect_submodules("pynput.keyboard")
hiddenimports += collect_submodules("pynput.mouse")

datas = [
    ("gsboard/resources/gsboard.png", "gsboard/resources"),
    ("gsboard/resources/gsboard.ico", "gsboard/resources"),
]

a = Analysis(
    ["gsboard/main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Keep the bundle lean — these modules ship with PyQt6 or get picked up
    # transitively but GSBoard never uses them.
    excludes=[
        "tkinter",
        "scipy",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtNetwork",
        "PyQt6.QtPdf",
        "PyQt6.QtDBus",
    ],
    noarchive=False,
)

# Drop large Qt DLLs / plugins / translations we don't use. PyInstaller's
# Qt hook pulls these in automatically; matching them here prunes the
# transitive haul without touching the site-packages install.
_QT_BINARY_DROPLIST = (
    "opengl32sw.dll",
    "Qt6Pdf.dll",
    "Qt6Network.dll",
    "Qt6DBus.dll",
    "Qt6Quick.dll",
    "Qt6Qml.dll",
)
_QT_PLUGIN_DROP_DIRS = ("networkinformation", "tls", "generic")

def _drop(entries):
    kept = []
    for entry in entries:
        dest = entry[0].replace("\\", "/")
        name = os.path.basename(dest).lower()
        if name in (b.lower() for b in _QT_BINARY_DROPLIST):
            continue
        if "qt6/translations/" in dest.lower() and not name.startswith("qtbase_en"):
            continue
        if any(f"qt6/plugins/{d}/" in dest.lower() for d in _QT_PLUGIN_DROP_DIRS):
            continue
        kept.append(entry)
    return kept

a.binaries = _drop(a.binaries)
a.datas = _drop(a.datas)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GSBoard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # windowed app — no console window
    disable_windowed_traceback=False,
    icon="gsboard/resources/gsboard.ico",
)
