"""SQLite-backed persistent download cache.

Uses standard :mod:`sqlite3` with :func:`asyncio.to_thread` so the cache
can be awaited from async code without a hard dependency on ``aiosqlite``.
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS downloads (
    record_id  TEXT PRIMARY KEY,
    success    INTEGER NOT NULL,
    pdf_path   TEXT,
    source     TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


class DownloadCache:
    """Persistent SQLite cache for PDF download results.

    This class is *not* thread-safe for concurrent writes from multiple
    coroutines against the same :class:`DownloadCache` instance.  The
    typical usage pattern — one downloader writing results serially —
    is safe.

    Args:
        db_path: Path to the SQLite database file.  Defaults to
            ``download_cache.db`` in the current working directory.
    """

    def __init__(self, db_path: Path | str = "download_cache.db") -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    async def initialize(self) -> None:
        """Open the database and create the schema if necessary."""
        await asyncio.to_thread(self._sync_initialize)

    def _sync_initialize(self) -> None:
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()
        logger.debug("DownloadCache initialized", db=str(self._db_path))

    async def close(self) -> None:
        """Close the underlying database connection."""
        await asyncio.to_thread(self._sync_close)

    def _sync_close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    async def get(self, record_id: str) -> dict[str, Any] | None:
        """Return cached download info or *None* on a cache miss.

        Args:
            record_id: The unique identifier of the bibliographic record.

        Returns:
            A dict with keys ``success``, ``pdf_path``, ``source`` or
            ``None`` if no entry exists for *record_id*.
        """
        return await asyncio.to_thread(self._sync_get, record_id)

    def _sync_get(self, record_id: str) -> dict[str, Any] | None:
        self._assert_initialized()
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT success, pdf_path, source FROM downloads WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        return {"success": bool(row[0]), "pdf_path": row[1], "source": row[2]}

    async def set(
        self,
        record_id: str,
        success: bool,
        pdf_path: str | None,
        source: str | None,
    ) -> None:
        """Insert or replace a download result in the cache.

        Args:
            record_id: Unique record identifier.
            success: Whether the download succeeded.
            pdf_path: Absolute path to the downloaded file, or *None*.
            source: Name of the source that provided the file, or *None*.
        """
        await asyncio.to_thread(self._sync_set, record_id, success, pdf_path, source)

    def _sync_set(
        self,
        record_id: str,
        success: bool,
        pdf_path: str | None,
        source: str | None,
    ) -> None:
        self._assert_initialized()
        assert self._conn is not None
        self._conn.execute(
            """INSERT OR REPLACE INTO downloads (record_id, success, pdf_path, source)
               VALUES (?, ?, ?, ?)""",
            (record_id, int(success), pdf_path, source),
        )
        self._conn.commit()

    def _assert_initialized(self) -> None:
        if self._conn is None:
            raise RuntimeError("DownloadCache.initialize() must be called before use")
