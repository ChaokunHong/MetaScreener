"""Screening API routes — thin re-export that mounts all sub-routers.

Sub-modules:
  screening_helpers   — shared utility functions
  screening_sessions  — session state, cleanup, criteria CRUD routes
  screening_ta        — Title/Abstract screening routes
  screening_ft        — Full-Text screening routes
  screening_feedback  — feedback (include/exclude/undo) routes
"""
from __future__ import annotations

from fastapi import APIRouter

from metascreener.api.routes.screening_feedback import feedback_router
from metascreener.api.routes.screening_ft import ft_router
from metascreener.api.routes.screening_sessions import (
    _ft_sessions,
    _sessions,
    sessions_router,
)
from metascreener.api.routes.screening_ta import ta_router

# Re-export state dicts for backward compatibility (used by evaluation routes)
__all__ = ["router", "_sessions", "_ft_sessions"]

router = APIRouter(prefix="/api/screening", tags=["screening"])

router.include_router(sessions_router)
router.include_router(ta_router)
router.include_router(ft_router)
router.include_router(feedback_router)
