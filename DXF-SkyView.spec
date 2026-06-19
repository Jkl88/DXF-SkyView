# -*- mode: python ; coding: utf-8 -*-
"""Спецификация PyInstaller для DXF SkyView."""

from pathlib import Path

ROOT = Path(SPECPATH)
LOGO = ROOT / "АКОЛЕД.png"
APP_ICON = ROOT / "DXF.ico"
FILE_ICON = ROOT / "DXFfile.ico"

datas = []
for asset in (LOGO, ROOT / "DXF.png", FILE_ICON):
    if asset.is_file():
        datas.append((str(asset), "."))

block_cipher = None

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "ezdxf",
        "ezdxf.addons",
        "ezdxf.entities",
        "ezdxf.layouts",
        "ezdxf.sections",
        "ezdxf.tools",
        "ezdxf.path",
        "ezdxf.math",
        "ezdxf.bbox",
        "ezdxf.acc.matrix44",
        "ezdxf.acc.vector",
        "ezdxf.acc.np_support",
        "numpy",
        "numpy.core._methods",
        "numpy.lib.format",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5",
        "PyQt6",
        "PyQt5.QtCore",
        "PyQt5.QtGui",
        "PyQt5.QtWidgets",
        "matplotlib",
        "matplotlib.pyplot",
        "PIL",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="DXF-SkyView",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(APP_ICON) if APP_ICON.is_file() else None,
)
