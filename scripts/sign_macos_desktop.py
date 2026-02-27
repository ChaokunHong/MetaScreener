"""Sign MetaScreener macOS desktop artifacts with codesign."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_APP_PATH = Path("dist") / "desktop" / "MetaScreener.app"
DEFAULT_DMG_PATH = Path("dist") / "desktop" / "MetaScreener.dmg"
DEFAULT_ENTITLEMENTS = Path("packaging") / "macos" / "entitlements.plist"
IDENTITY_ENV = "METASCREENER_CODESIGN_IDENTITY"


def _ensure_macos() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("macOS signing is only supported on macOS.")


def _find_tool(name: str) -> str:
    tool = shutil.which(name)
    if not tool:
        raise RuntimeError(f"Required macOS tool not found: {name}")
    return tool


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _resolve_identity(explicit: str | None) -> str:
    identity = (explicit or os.environ.get(IDENTITY_ENV, "")).strip()
    if not identity:
        raise RuntimeError(
            "Code signing identity not provided. Pass --identity or set "
            f"{IDENTITY_ENV}."
        )
    return identity


def _resolve_optional_file(path_str: str | None) -> Path | None:
    if path_str is None:
        return None
    path = Path(path_str).expanduser().resolve()
    if not path.exists():
        raise RuntimeError(f"File not found: {path}")
    return path


def _existing_default(path: Path) -> Path | None:
    resolved = path.resolve()
    return resolved if resolved.exists() else None


def _resolve_entitlements(
    path_str: str | None,
    use_default: bool,
) -> Path | None:
    if path_str:
        path = Path(path_str).expanduser().resolve()
        if not path.is_file():
            raise RuntimeError(f"Entitlements file not found: {path}")
        return path
    if not use_default:
        return None
    default_path = DEFAULT_ENTITLEMENTS.resolve()
    return default_path if default_path.is_file() else None


def sign_app(
    *,
    app_path: Path,
    identity: str,
    entitlements: Path | None,
    verify: bool,
) -> None:
    codesign = _find_tool("codesign")
    cmd = [
        codesign,
        "--force",
        "--deep",
        "--options",
        "runtime",
        "--timestamp",
        "--sign",
        identity,
    ]
    if entitlements is not None:
        cmd.extend(["--entitlements", str(entitlements)])
    cmd.append(str(app_path))
    _run(cmd)

    if verify:
        _run([codesign, "--verify", "--deep", "--strict", "--verbose=2", str(app_path)])
        spctl = shutil.which("spctl")
        if spctl:
            _run([spctl, "-a", "-vvv", "--type", "exec", str(app_path)])


def sign_dmg(*, dmg_path: Path, identity: str, verify: bool) -> None:
    codesign = _find_tool("codesign")
    _run([
        codesign,
        "--force",
        "--timestamp",
        "--sign",
        identity,
        str(dmg_path),
    ])

    if verify:
        _run([codesign, "--verify", "--verbose=2", str(dmg_path)])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sign MetaScreener macOS desktop artifacts (.app / .dmg)."
    )
    parser.add_argument(
        "--identity",
        help=f"codesign identity (fallback env: {IDENTITY_ENV})",
    )
    parser.add_argument(
        "--app",
        help=f"Path to .app bundle (default: {DEFAULT_APP_PATH}) if present",
    )
    parser.add_argument(
        "--dmg",
        help=f"Path to .dmg file (default: {DEFAULT_DMG_PATH}) if present",
    )
    parser.add_argument(
        "--entitlements",
        help=(
            "Path to entitlements plist for .app signing "
            "(defaults to packaging/macos/entitlements.plist if present)"
        ),
    )
    parser.add_argument(
        "--no-default-entitlements",
        action="store_true",
        help="Do not use the default entitlements plist automatically.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip codesign/spctl verification after signing.",
    )
    args = parser.parse_args()

    try:
        _ensure_macos()
        identity = _resolve_identity(args.identity)

        app_path = _resolve_optional_file(args.app) or _existing_default(DEFAULT_APP_PATH)
        dmg_path = _resolve_optional_file(args.dmg) or _existing_default(DEFAULT_DMG_PATH)
        if app_path is None and dmg_path is None:
            raise RuntimeError(
                "No .app or .dmg artifact found to sign. "
                "Build desktop artifacts first (e.g. make build-desktop-dmg)."
            )

        entitlements = _resolve_entitlements(
            args.entitlements,
            use_default=not args.no_default_entitlements,
        )
        verify = not args.no_verify

        if app_path is not None:
            sign_app(
                app_path=app_path,
                identity=identity,
                entitlements=entitlements,
                verify=verify,
            )
            print(f"Signed app: {app_path}")

        if dmg_path is not None:
            sign_dmg(dmg_path=dmg_path, identity=identity, verify=verify)
            print(f"Signed dmg: {dmg_path}")

    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc


if __name__ == "__main__":
    main()
