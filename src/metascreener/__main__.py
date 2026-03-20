"""Entry point for python -m metascreener — launches the FastAPI server."""
from __future__ import annotations

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "metascreener.api.main:create_app",
        host="127.0.0.1",
        port=8000,
        factory=True,
    )
