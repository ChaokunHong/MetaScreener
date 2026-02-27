# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the MetaScreener desktop shell."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
ENTRY_SCRIPT = SRC_DIR / "metascreener" / "desktop" / "app_main.py"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
MACOS_ICON_DEFAULT = PROJECT_ROOT / "packaging" / "macos" / "MetaScreener.icns"


def _project_version() -> str:
    try:
        import tomllib  # noqa: PLC0415
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[import-not-found]  # noqa: PLC0415

    if not PYPROJECT.is_file():
        return "0.0.0"
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data.get("project", {})
    raw = project.get("version", "0.0.0")
    return str(raw)


def _apple_numeric_version(version: str) -> str:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if match:
        return ".".join(match.groups())
    digits = re.findall(r"\d+", version)
    if not digits:
        return "0.0.0"
    padded = (digits + ["0", "0"])[:3]
    return ".".join(padded)


RAW_VERSION = _project_version()
APPLE_VERSION = _apple_numeric_version(RAW_VERSION)

icon_env = os.environ.get("METASCREENER_DESKTOP_ICON", "").strip()
icon_path = Path(icon_env).expanduser() if icon_env else MACOS_ICON_DEFAULT
MACOS_ICON = str(icon_path) if icon_path.is_file() else None

datas = collect_data_files("metascreener", includes=["web/dist/**/*"])
hiddenimports = collect_submodules("webview")

block_cipher = None

a = Analysis(
    [str(ENTRY_SCRIPT)],
    pathex=[str(SRC_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="MetaScreener",
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
    name="MetaScreener",
)

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F841
        coll,
        name="MetaScreener.app",
        icon=MACOS_ICON,
        bundle_identifier="org.metascreener.desktop",
        info_plist={
            "CFBundleName": "MetaScreener",
            "CFBundleDisplayName": "MetaScreener",
            "CFBundleExecutable": "MetaScreener",
            "CFBundleIdentifier": "org.metascreener.desktop",
            "CFBundleShortVersionString": APPLE_VERSION,
            "CFBundleVersion": APPLE_VERSION,
            "CFBundleGetInfoString": f"MetaScreener {RAW_VERSION}",
            "LSApplicationCategoryType": "public.app-category.developer-tools",
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
        },
    )
