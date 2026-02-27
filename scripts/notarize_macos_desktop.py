"""Notarize MetaScreener macOS desktop artifacts with notarytool."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_DMG_PATH = Path("dist") / "desktop" / "MetaScreener.dmg"
DEFAULT_APP_PATH = Path("dist") / "desktop" / "MetaScreener.app"

PROFILE_ENV = "METASCREENER_NOTARY_KEYCHAIN_PROFILE"
APPLE_ID_ENV = "METASCREENER_NOTARY_APPLE_ID"
TEAM_ID_ENV = "METASCREENER_NOTARY_TEAM_ID"
PASSWORD_ENV = "METASCREENER_NOTARY_PASSWORD"


def _ensure_macos() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("Notarization is only supported on macOS.")


def _find_xcrun() -> str:
    tool = shutil.which("xcrun")
    if not tool:
        raise RuntimeError("`xcrun` not found. Xcode command line tools are required.")
    return tool


def _resolve_existing(path_str: str | None, default_path: Path) -> Path | None:
    if path_str:
        path = Path(path_str).expanduser().resolve()
        if not path.exists():
            raise RuntimeError(f"File not found: {path}")
        return path
    default_resolved = default_path.resolve()
    return default_resolved if default_resolved.exists() else None


def _auth_args(args: argparse.Namespace) -> list[str]:
    profile = (args.keychain_profile or os.environ.get(PROFILE_ENV, "")).strip()
    if profile:
        return ["--keychain-profile", profile]

    apple_id = (args.apple_id or os.environ.get(APPLE_ID_ENV, "")).strip()
    team_id = (args.team_id or os.environ.get(TEAM_ID_ENV, "")).strip()
    password = (args.password or os.environ.get(PASSWORD_ENV, "")).strip()
    if apple_id and team_id and password:
        return [
            "--apple-id",
            apple_id,
            "--team-id",
            team_id,
            "--password",
            password,
        ]

    raise RuntimeError(
        "Notary credentials missing. Use --keychain-profile (or "
        f"{PROFILE_ENV}), or provide --apple-id/--team-id/--password "
        f"(or envs {APPLE_ID_ENV}, {TEAM_ID_ENV}, {PASSWORD_ENV})."
    )


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def notarize(
    *,
    submit_path: Path,
    auth_args: list[str],
    wait: bool,
) -> None:
    xcrun = _find_xcrun()
    cmd = [xcrun, "notarytool", "submit", str(submit_path), *auth_args]
    if wait:
        cmd.append("--wait")
    _run(cmd)


def staple(path: Path) -> None:
    xcrun = _find_xcrun()
    _run([xcrun, "stapler", "staple", str(path)])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Notarize MetaScreener macOS desktop artifacts (.dmg/.app)."
    )
    parser.add_argument(
        "--submit",
        help=f"Artifact to submit to notarytool (default: {DEFAULT_DMG_PATH} if present, else app)",
    )
    parser.add_argument(
        "--app",
        help=(
            "Path to .app bundle for stapling after notarizing a DMG "
            f"(default: {DEFAULT_APP_PATH} if present)"
        ),
    )
    parser.add_argument(
        "--keychain-profile",
        help=f"notarytool keychain profile (fallback env: {PROFILE_ENV})",
    )
    parser.add_argument(
        "--apple-id",
        help=f"Apple ID email (fallback env: {APPLE_ID_ENV})",
    )
    parser.add_argument(
        "--team-id",
        help=f"Apple Developer Team ID (fallback env: {TEAM_ID_ENV})",
    )
    parser.add_argument(
        "--password",
        help=f"App-specific password or keychain ref (fallback env: {PASSWORD_ENV})",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Do not wait for notarization result (skips stapling).",
    )
    parser.add_argument(
        "--no-staple",
        action="store_true",
        help="Do not staple notarization ticket after submission.",
    )
    args = parser.parse_args()

    try:
        _ensure_macos()
        auth_args = _auth_args(args)

        submit_path = _resolve_existing(args.submit, DEFAULT_DMG_PATH)
        if submit_path is None:
            submit_path = _resolve_existing(None, DEFAULT_APP_PATH)
        if submit_path is None:
            raise RuntimeError(
                "No artifact found to notarize. Build and sign a .dmg or .app first."
            )

        app_path = _resolve_existing(args.app, DEFAULT_APP_PATH)
        wait = not args.no_wait
        notarize(submit_path=submit_path, auth_args=auth_args, wait=wait)
        print(f"Submitted for notarization: {submit_path}")

        if wait and not args.no_staple:
            staple(submit_path)
            print(f"Stapled: {submit_path}")
            if submit_path.suffix.lower() == ".dmg" and app_path is not None:
                staple(app_path)
                print(f"Stapled app bundle: {app_path}")

    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc


if __name__ == "__main__":
    main()
