"""File-based history persistence for MetaScreener sessions.

Stores session history as JSON files under ``~/.metascreener/history/{module}/{uuid}.json``.
Each file contains metadata (id, module, name, timestamps, summary) plus the full
module-specific payload under a ``data`` key.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

VALID_MODULES = frozenset({"criteria", "screening", "evaluation", "extraction", "quality"})

_BASE_DIR = Path.home() / ".metascreener" / "history"


class HistoryStore:
    """CRUD interface for file-based session history.

    Args:
        base_dir: Root directory for history storage.
            Defaults to ``~/.metascreener/history/``.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = base_dir or _BASE_DIR

    def _module_dir(self, module: str) -> Path:
        """Return the directory for a given module, creating it if needed."""
        if module not in VALID_MODULES:
            msg = f"Invalid module '{module}'. Must be one of {sorted(VALID_MODULES)}"
            raise ValueError(msg)
        # If a stale file exists at the base or module path, remove it
        # so we can create the directory tree.
        for ancestor in (self._base, self._base / module):
            if ancestor.exists() and not ancestor.is_dir():
                ancestor.unlink()
                logger.warning("history_removed_stale_file", path=str(ancestor))
        d = self._base / module
        d.mkdir(parents=True, exist_ok=True)
        return d

    def create(
        self,
        module: str,
        data: dict[str, Any],
        name: str | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new history item.

        Args:
            module: Module name (criteria, screening, etc.).
            data: Module-specific payload.
            name: Optional human-readable label.
            summary: Optional short description.
            tags: Optional list of tag strings.

        Returns:
            The full history item envelope (including generated id and timestamps).
        """
        item_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        item: dict[str, Any] = {
            "id": item_id,
            "module": module,
            "name": name or f"{module} — {now[:16]}",
            "created_at": now,
            "updated_at": now,
            "summary": summary or "",
            "tags": tags or [],
            "data": data,
        }
        path = self._module_dir(module) / f"{item_id}.json"
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("history_item_created", module=module, item_id=item_id)
        return item

    def list_items(self, module: str) -> list[dict[str, Any]]:
        """List history items for a module (metadata only, no ``data`` field).

        Args:
            module: Module name to filter by.

        Returns:
            List of item summaries sorted by ``created_at`` descending (newest first).
        """
        d = self._module_dir(module)
        items: list[dict[str, Any]] = []
        for path in d.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                items.append({
                    "id": raw["id"],
                    "module": raw["module"],
                    "name": raw["name"],
                    "created_at": raw["created_at"],
                    "updated_at": raw["updated_at"],
                    "summary": raw.get("summary", ""),
                    "tags": raw.get("tags", []),
                })
            except (json.JSONDecodeError, KeyError):
                logger.warning("history_corrupt_file", path=str(path))
        items.sort(key=lambda x: x["created_at"], reverse=True)
        return items

    def get(self, module: str, item_id: str) -> dict[str, Any] | None:
        """Retrieve a full history item (including ``data``).

        Args:
            module: Module name.
            item_id: UUID of the item.

        Returns:
            Full item envelope, or ``None`` if not found.
        """
        path = self._module_dir(module) / f"{item_id}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        except (json.JSONDecodeError, KeyError):
            logger.warning("history_corrupt_file", path=str(path))
            return None

    def rename(self, module: str, item_id: str, new_name: str) -> dict[str, Any] | None:
        """Rename a history item.

        Args:
            module: Module name.
            item_id: UUID of the item.
            new_name: New human-readable label.

        Returns:
            Updated item summary (without ``data``), or ``None`` if not found.
        """
        path = self._module_dir(module) / f"{item_id}.json"
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            return None
        raw["name"] = new_name
        raw["updated_at"] = datetime.now(UTC).isoformat()
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "id": raw["id"],
            "module": raw["module"],
            "name": raw["name"],
            "created_at": raw["created_at"],
            "updated_at": raw["updated_at"],
            "summary": raw.get("summary", ""),
        }

    def delete(self, module: str, item_id: str) -> bool:
        """Delete a history item.

        Args:
            module: Module name.
            item_id: UUID of the item.

        Returns:
            ``True`` if the item was deleted, ``False`` if not found.
        """
        path = self._module_dir(module) / f"{item_id}.json"
        if not path.is_file():
            return False
        path.unlink()
        logger.info("history_item_deleted", module=module, item_id=item_id)
        return True

    def clear_module(self, module: str) -> int:
        """Delete all history items for a module.

        Args:
            module: Module name.

        Returns:
            Number of items deleted.
        """
        d = self._module_dir(module)
        count = 0
        for path in d.glob("*.json"):
            path.unlink()
            count += 1
        if count:
            logger.info("history_module_cleared", module=module, count=count)
        return count

    def clear_all(self) -> int:
        """Delete all history items across all modules.

        Returns:
            Total number of items deleted.
        """
        total = 0
        for module in sorted(VALID_MODULES):
            total += self.clear_module(module)
        return total
