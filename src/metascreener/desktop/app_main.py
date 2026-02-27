"""Packaged desktop app entry point."""
from __future__ import annotations

import sys

from metascreener.desktop.launcher import launch_desktop


def main() -> None:
    """Launch the embedded desktop UI with production defaults."""
    try:
        launch_desktop()
    except RuntimeError as exc:
        print(f"MetaScreener desktop startup error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

