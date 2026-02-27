"""Build a packaged desktop shell with PyInstaller."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_LOGO_SVG = Path("logo") / "Meta Screener LOGO图标 透明背景.svg"
DEFAULT_MACOS_ICNS = Path("packaging") / "macos" / "MetaScreener.icns"

ICONSET_ENTRIES = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _frontend_bundle_exists(root: Path) -> bool:
    return (root / "src" / "metascreener" / "web" / "dist" / "index.html").is_file()


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True)


def _ensure_pyinstaller() -> None:
    try:
        import PyInstaller.__main__  # noqa: F401, PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "PyInstaller is not installed. Install desktop build deps with "
            "`uv sync --extra desktop-build`."
        ) from exc


def _ensure_macos() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("DMG packaging is currently supported only on macOS.")


def _ensure_hdiutil() -> str:
    hdiutil = shutil.which("hdiutil")
    if not hdiutil:
        raise RuntimeError("`hdiutil` not found. DMG packaging requires macOS system tool hdiutil.")
    return hdiutil


def _ensure_macos_icon_tools() -> tuple[str, str]:
    sips = shutil.which("sips")
    iconutil = shutil.which("iconutil")
    if not sips or not iconutil:
        raise RuntimeError(
            "SVG -> ICNS conversion requires macOS tools `sips` and `iconutil`."
        )
    return sips, iconutil


def _render_png_from_svg(svg_path: Path, out_png: Path, size_px: int) -> None:
    sips, _ = _ensure_macos_icon_tools()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sips,
            "-z",
            str(size_px),
            str(size_px),
            "-s",
            "format",
            "png",
            str(svg_path),
            "--out",
            str(out_png),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not out_png.is_file():
        raise RuntimeError(f"Failed to render PNG icon from SVG: {svg_path}")


def _generate_icns_from_svg(svg_path: Path, out_icns: Path) -> Path:
    _ensure_macos()
    _, iconutil = _ensure_macos_icon_tools()

    if not svg_path.is_file():
        raise RuntimeError(f"SVG icon file not found: {svg_path}")

    out_icns.parent.mkdir(parents=True, exist_ok=True)
    iconset_dir = out_icns.parent / "MetaScreener.iconset"
    shutil.rmtree(iconset_dir, ignore_errors=True)
    iconset_dir.mkdir(parents=True, exist_ok=True)

    for filename, size_px in ICONSET_ENTRIES:
        _render_png_from_svg(svg_path, iconset_dir / filename, size_px)

    subprocess.run(
        [
            iconutil,
            "-c",
            "icns",
            str(iconset_dir),
            "-o",
            str(out_icns),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not out_icns.is_file():
        raise RuntimeError(f"Failed to generate ICNS icon: {out_icns}")
    return out_icns


def _resolve_icon(icon: str | None, *, root: Path, build_dir: Path) -> Path | None:
    if not icon:
        default_icns = (root / DEFAULT_MACOS_ICNS).resolve()
        if default_icns.is_file():
            return default_icns

        default_svg = (root / DEFAULT_LOGO_SVG).resolve()
        if default_svg.is_file() and sys.platform == "darwin":
            generated_dir = build_dir / "generated-assets"
            return _generate_icns_from_svg(default_svg, generated_dir / "MetaScreener.icns")
        return None

    icon_path = Path(icon).expanduser().resolve()
    if not icon_path.is_file():
        raise RuntimeError(f"Icon file not found: {icon_path}")
    suffix = icon_path.suffix.lower()
    if suffix == ".icns":
        return icon_path
    if suffix == ".svg":
        generated_dir = build_dir / "generated-assets"
        return _generate_icns_from_svg(icon_path, generated_dir / "MetaScreener.icns")
    raise RuntimeError("Desktop icon must be a macOS .icns or .svg file.")


def _find_macos_app(dist_dir: Path) -> Path:
    app_path = dist_dir / "MetaScreener.app"
    if not app_path.is_dir():
        raise RuntimeError(
            "PyInstaller .app bundle not found. "
            "Ensure PyInstaller packaging completed successfully "
            "and the spec generated `MetaScreener.app`."
        )
    return app_path


def _build_macos_dmg(app_path: Path, dmg_path: Path) -> Path:
    hdiutil = _ensure_hdiutil()
    dmg_path.parent.mkdir(parents=True, exist_ok=True)
    dmg_path.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="metascreener-dmg-") as tmpdir:
        staging = Path(tmpdir)
        staged_app = staging / app_path.name
        shutil.copytree(app_path, staged_app, symlinks=True)
        apps_link = staging / "Applications"
        apps_link.symlink_to("/Applications")

        subprocess.run(
            [
                hdiutil,
                "create",
                "-volname",
                "MetaScreener",
                "-srcfolder",
                str(staging),
                "-ov",
                "-format",
                "UDZO",
                str(dmg_path),
            ],
            check=True,
        )
    return dmg_path


def build_desktop(
    *,
    rebuild_frontend: bool = False,
    clean: bool = False,
    build_dmg: bool = False,
    icon: str | None = None,
) -> tuple[Path, Path | None]:
    """Build the desktop app bundle and optionally produce a macOS DMG."""
    root = _project_root()

    if rebuild_frontend:
        _run(["npm", "run", "build"], cwd=root / "frontend")

    if not _frontend_bundle_exists(root):
        raise RuntimeError(
            "Frontend bundle not found at src/metascreener/web/dist. "
            "Run `npm run build` in frontend/ first (or pass --rebuild-frontend)."
        )

    _ensure_pyinstaller()

    spec_path = root / "packaging" / "pyinstaller" / "metascreener-desktop.spec"
    build_dir = root / "build" / "pyinstaller"
    dist_dir = root / "dist" / "desktop"

    if clean:
        shutil.rmtree(build_dir, ignore_errors=True)
        shutil.rmtree(dist_dir, ignore_errors=True)

    from PyInstaller.__main__ import run as pyinstaller_run  # noqa: PLC0415
    resolved_icon = _resolve_icon(icon, root=root, build_dir=build_dir)

    pyinstaller_args = [
        "--noconfirm",
        "--clean",
        f"--distpath={dist_dir}",
        f"--workpath={build_dir}",
        str(spec_path),
    ]

    previous_icon_env = os.environ.get("METASCREENER_DESKTOP_ICON")
    try:
        if resolved_icon is not None:
            os.environ["METASCREENER_DESKTOP_ICON"] = str(resolved_icon)
        pyinstaller_run(pyinstaller_args)
    finally:
        if previous_icon_env is None:
            os.environ.pop("METASCREENER_DESKTOP_ICON", None)
        else:
            os.environ["METASCREENER_DESKTOP_ICON"] = previous_icon_env

    dmg_path: Path | None = None
    if build_dmg:
        _ensure_macos()
        app_path = _find_macos_app(dist_dir)
        dmg_path = _build_macos_dmg(app_path, dist_dir / "MetaScreener.dmg")

    return dist_dir / "MetaScreener", dmg_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the MetaScreener desktop shell bundle (PyInstaller onedir)."
    )
    parser.add_argument(
        "--rebuild-frontend",
        action="store_true",
        help="Run `npm run build` in frontend/ before packaging.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove previous PyInstaller build/dist directories before packaging.",
    )
    parser.add_argument(
        "--dmg",
        action="store_true",
        help="On macOS, also create a DMG from the generated .app bundle.",
    )
    parser.add_argument(
        "--icon",
        help="Path to a macOS .icns or .svg file for the app icon (PyInstaller BUNDLE on macOS).",
    )
    args = parser.parse_args()

    try:
        output, dmg_path = build_desktop(
            rebuild_frontend=args.rebuild_frontend,
            clean=args.clean,
            build_dmg=args.dmg,
            icon=args.icon,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc

    print(f"Desktop bundle built at: {output}")
    if dmg_path is not None:
        print(f"DMG built at: {dmg_path}")


if __name__ == "__main__":
    main()
