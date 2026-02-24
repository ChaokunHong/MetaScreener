"""Tests for wizard session persistence and lifecycle management."""

from __future__ import annotations

import os
import time
from pathlib import Path

from metascreener.core.models import WizardSession
from metascreener.criteria.session import SessionManager


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    """Saved session should be loadable with identical state."""
    mgr = SessionManager(sessions_dir=tmp_path)
    session = WizardSession(current_step=2)
    mgr.save(session)
    loaded = mgr.load(session.session_id)
    assert loaded is not None
    assert loaded.current_step == 2
    assert loaded.session_id == session.session_id


def test_load_nonexistent_returns_none(tmp_path: Path) -> None:
    """Loading a non-existent session ID should return None."""
    mgr = SessionManager(sessions_dir=tmp_path)
    assert mgr.load("nonexistent-id") is None


def test_load_latest(tmp_path: Path) -> None:
    """load_latest should return the most recently saved session."""
    mgr = SessionManager(sessions_dir=tmp_path)
    s1 = WizardSession(current_step=1)
    s2 = WizardSession(current_step=3)
    mgr.save(s1)
    mgr.save(s2)
    latest = mgr.load_latest()
    assert latest is not None
    assert latest.current_step == 3


def test_cleanup_removes_old_sessions(tmp_path: Path) -> None:
    """Cleanup should remove sessions older than max_age_days."""
    mgr = SessionManager(sessions_dir=tmp_path)
    old = WizardSession(current_step=1)
    mgr.save(old)
    # Manually backdate the file
    old_path = tmp_path / f"{old.session_id}.json"
    old_time = time.time() - 8 * 86400  # 8 days ago
    os.utime(old_path, (old_time, old_time))
    mgr.cleanup(max_age_days=7)
    assert not old_path.exists()


def test_cleanup_keeps_recent_sessions(tmp_path: Path) -> None:
    """Cleanup should not remove sessions within max_age_days."""
    mgr = SessionManager(sessions_dir=tmp_path)
    recent = WizardSession(current_step=5)
    mgr.save(recent)
    removed = mgr.cleanup(max_age_days=7)
    assert removed == 0
    assert mgr.load(recent.session_id) is not None


def test_delete_session(tmp_path: Path) -> None:
    """Deleting a session should make it unloadable."""
    mgr = SessionManager(sessions_dir=tmp_path)
    session = WizardSession()
    mgr.save(session)
    mgr.delete(session.session_id)
    assert mgr.load(session.session_id) is None


def test_delete_nonexistent_is_noop(tmp_path: Path) -> None:
    """Deleting a non-existent session should not raise."""
    mgr = SessionManager(sessions_dir=tmp_path)
    mgr.delete("does-not-exist")  # Should not raise


def test_load_latest_empty_dir(tmp_path: Path) -> None:
    """load_latest on empty directory should return None."""
    mgr = SessionManager(sessions_dir=tmp_path)
    assert mgr.load_latest() is None


def test_load_latest_no_dir(tmp_path: Path) -> None:
    """load_latest when directory doesn't exist should return None."""
    mgr = SessionManager(sessions_dir=tmp_path / "nonexistent")
    assert mgr.load_latest() is None


def test_cleanup_returns_count(tmp_path: Path) -> None:
    """Cleanup should return number of removed sessions."""
    mgr = SessionManager(sessions_dir=tmp_path)
    for _ in range(3):
        s = WizardSession()
        mgr.save(s)
        p = tmp_path / f"{s.session_id}.json"
        old_time = time.time() - 10 * 86400
        os.utime(p, (old_time, old_time))
    removed = mgr.cleanup(max_age_days=7)
    assert removed == 3


def test_save_creates_directory(tmp_path: Path) -> None:
    """Save should create the sessions directory if it doesn't exist."""
    nested = tmp_path / "deep" / "nested" / "sessions"
    mgr = SessionManager(sessions_dir=nested)
    session = WizardSession(current_step=1)
    path = mgr.save(session)
    assert path.exists()
    assert nested.exists()


def test_save_overwrites_existing(tmp_path: Path) -> None:
    """Saving a session with same ID should overwrite the file."""
    mgr = SessionManager(sessions_dir=tmp_path)
    session = WizardSession(current_step=1)
    mgr.save(session)
    session.current_step = 5
    mgr.save(session)
    loaded = mgr.load(session.session_id)
    assert loaded is not None
    assert loaded.current_step == 5
