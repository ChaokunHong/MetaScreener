"""History API routes for session persistence and retrieval."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from metascreener.api.history_store import VALID_MODULES, HistoryStore
from metascreener.api.schemas import (
    HistoryCreateRequest,
    HistoryItemFull,
    HistoryItemSummary,
    HistoryListResponse,
    HistoryRenameRequest,
)

router = APIRouter(prefix="/api/history", tags=["history"])

_store = HistoryStore()


def _validate_module(module: str) -> None:
    """Raise 400 if module is not valid."""
    if module not in VALID_MODULES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid module '{module}'. Must be one of {sorted(VALID_MODULES)}",
        )


@router.get("", response_model=HistoryListResponse)
async def list_history(module: str | None = None) -> HistoryListResponse:
    """List history items, optionally filtered by module.

    Args:
        module: Optional module filter.

    Returns:
        List of item summaries sorted newest-first.
    """
    if module:
        _validate_module(module)
        items = _store.list_items(module)
    else:
        items = []
        for m in sorted(VALID_MODULES):
            items.extend(_store.list_items(m))
        items.sort(key=lambda x: x["created_at"], reverse=True)

    summaries = [HistoryItemSummary(**item) for item in items]
    return HistoryListResponse(items=summaries, total=len(summaries))


@router.get("/{module}/{item_id}", response_model=HistoryItemFull)
async def get_history_item(module: str, item_id: str) -> HistoryItemFull:
    """Get a full history item including its data payload.

    Args:
        module: Module name.
        item_id: Item UUID.

    Returns:
        Full history item.
    """
    _validate_module(module)
    item = _store.get(module, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="History item not found")
    return HistoryItemFull(**item)


@router.post("/{module}", response_model=HistoryItemFull, status_code=201)
async def create_history_item(module: str, body: HistoryCreateRequest) -> HistoryItemFull:
    """Create a new history item.

    Args:
        module: Module name.
        body: Item payload with optional name and summary.

    Returns:
        Created history item.
    """
    _validate_module(module)
    item = _store.create(
        module=module,
        data=body.data,
        name=body.name,
        summary=body.summary,
    )
    return HistoryItemFull(**item)


@router.put("/{module}/{item_id}/rename", response_model=HistoryItemSummary)
async def rename_history_item(
    module: str, item_id: str, body: HistoryRenameRequest
) -> HistoryItemSummary:
    """Rename a history item.

    Args:
        module: Module name.
        item_id: Item UUID.
        body: New name.

    Returns:
        Updated item summary.
    """
    _validate_module(module)
    result = _store.rename(module, item_id, body.name)
    if result is None:
        raise HTTPException(status_code=404, detail="History item not found")
    return HistoryItemSummary(**result)


@router.delete("/{module}/{item_id}")
async def delete_history_item(module: str, item_id: str) -> dict[str, bool]:
    """Delete a history item.

    Args:
        module: Module name.
        item_id: Item UUID.

    Returns:
        Deletion confirmation.
    """
    _validate_module(module)
    deleted = _store.delete(module, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="History item not found")
    return {"deleted": True}


@router.delete("/{module}")
async def clear_module_history(module: str) -> dict[str, int]:
    """Delete all history items for a module.

    Args:
        module: Module name.

    Returns:
        Count of deleted items.
    """
    _validate_module(module)
    count = _store.clear_module(module)
    return {"deleted": count}


@router.delete("")
async def clear_all_history() -> dict[str, int]:
    """Delete all history items across all modules.

    Returns:
        Total count of deleted items.
    """
    count = _store.clear_all()
    return {"deleted": count}
