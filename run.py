#!/usr/bin/env python3
"""
MetaScreener 2.0 — Development Runner

Usage:
    python run.py           # Start both FastAPI backend and Vite frontend
    python run.py --api     # Start FastAPI only (port 8000)
    python run.py --ui      # Start Vite only (port 5173)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
FRONTEND_DIR = ROOT / "frontend"
SRC_DIR = ROOT / "src"


def run_api() -> subprocess.Popen:
    """Start the FastAPI backend with hot reload."""
    env = os.environ.copy()
    # Add src to PYTHONPATH so metascreener is importable without install
    pythonpath = str(SRC_DIR)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{pythonpath}:{existing}" if existing else pythonpath

    cmd = [
        sys.executable, "-m", "uvicorn",
        "metascreener.api.main:create_app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload",
        "--reload-dir", str(SRC_DIR),
        "--factory",
    ]
    print("🚀 Starting FastAPI backend at http://localhost:8000")
    return subprocess.Popen(cmd, env=env)


def run_ui() -> subprocess.Popen:
    """Start the Vite dev server."""
    if not FRONTEND_DIR.exists():
        print("❌ frontend/ directory not found. Run 'cd frontend && npm install' first.")
        sys.exit(1)

    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        print("📦 Installing frontend dependencies…")
        subprocess.run(["npm", "install"], cwd=FRONTEND_DIR, check=True)

    print("✨ Starting Vite dev server at http://localhost:5173")
    return subprocess.Popen(["npm", "run", "dev"], cwd=FRONTEND_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(description="MetaScreener 2.0 development runner")
    parser.add_argument("--api", action="store_true", help="Start API server only")
    parser.add_argument("--ui", action="store_true", help="Start Vite dev server only")
    args = parser.parse_args()

    procs: list[subprocess.Popen] = []

    try:
        if args.api:
            procs.append(run_api())
        elif args.ui:
            procs.append(run_ui())
        else:
            # Start API first, give it a moment, then start UI
            procs.append(run_api())
            time.sleep(1.5)
            procs.append(run_ui())
            print("\n" + "=" * 50)
            print("  MetaScreener 2.0 is running!")
            print("  Frontend: http://localhost:5173")
            print("  API docs: http://localhost:8000/api/docs")
            print("  Press Ctrl+C to stop")
            print("=" * 50 + "\n")

        # Wait for all processes
        for p in procs:
            p.wait()

    except KeyboardInterrupt:
        print("\n⏹  Shutting down…")
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("✓ Stopped")


if __name__ == "__main__":
    main()
