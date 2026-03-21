"""Unit tests for the file-based HistoryStore."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from metascreener.api.history_store import HistoryStore, VALID_MODULES


@pytest.fixture()
def store(tmp_path: Path) -> HistoryStore:
    """Create a HistoryStore backed by a temporary directory."""
    return HistoryStore(base_dir=tmp_path)


# ── create ────────────────────────────────────────────────────


class TestCreate:
    """Tests for HistoryStore.create()."""

    def test_create_returns_envelope(self, store: HistoryStore) -> None:
        item = store.create("criteria", data={"framework": "PICO"})
        assert item["module"] == "criteria"
        assert item["data"] == {"framework": "PICO"}
        assert "id" in item
        assert "created_at" in item
        assert "updated_at" in item

    def test_create_persists_file(self, store: HistoryStore, tmp_path: Path) -> None:
        item = store.create("screening", data={"results": []})
        path = tmp_path / "screening" / f"{item['id']}.json"
        assert path.is_file()
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["module"] == "screening"
        assert raw["data"] == {"results": []}

    def test_create_with_custom_name_and_summary(self, store: HistoryStore) -> None:
        item = store.create(
            "evaluation",
            data={"metrics": {}},
            name="My Evaluation",
            summary="10 papers evaluated",
        )
        assert item["name"] == "My Evaluation"
        assert item["summary"] == "10 papers evaluated"

    def test_create_auto_generates_name(self, store: HistoryStore) -> None:
        item = store.create("extraction", data={})
        assert item["name"].startswith("extraction")

    def test_create_invalid_module_raises(self, store: HistoryStore) -> None:
        with pytest.raises(ValueError, match="Invalid module"):
            store.create("invalid_module", data={})


# ── list_items ────────────────────────────────────────────────


class TestListItems:
    """Tests for HistoryStore.list_items()."""

    def test_list_empty(self, store: HistoryStore) -> None:
        items = store.list_items("criteria")
        assert items == []

    def test_list_returns_metadata_only(self, store: HistoryStore) -> None:
        store.create("criteria", data={"big": "payload"})
        items = store.list_items("criteria")
        assert len(items) == 1
        assert "data" not in items[0]
        assert items[0]["module"] == "criteria"

    def test_list_sorted_newest_first(self, store: HistoryStore) -> None:
        store.create("screening", data={"n": 1}, name="First")
        store.create("screening", data={"n": 2}, name="Second")
        items = store.list_items("screening")
        assert len(items) == 2
        # Newest (Second) should be first
        assert items[0]["name"] == "Second"
        assert items[1]["name"] == "First"

    def test_list_filters_by_module(self, store: HistoryStore) -> None:
        store.create("criteria", data={})
        store.create("screening", data={})
        assert len(store.list_items("criteria")) == 1
        assert len(store.list_items("screening")) == 1

    def test_list_invalid_module_raises(self, store: HistoryStore) -> None:
        with pytest.raises(ValueError, match="Invalid module"):
            store.list_items("bogus")

    def test_list_skips_corrupt_files(self, store: HistoryStore, tmp_path: Path) -> None:
        store.create("criteria", data={})
        # Write a corrupt file
        d = tmp_path / "criteria"
        (d / "bad.json").write_text("not json", encoding="utf-8")
        items = store.list_items("criteria")
        assert len(items) == 1  # corrupt file skipped


# ── get ───────────────────────────────────────────────────────


class TestGet:
    """Tests for HistoryStore.get()."""

    def test_get_existing(self, store: HistoryStore) -> None:
        created = store.create("quality", data={"tool": "rob2"})
        fetched = store.get("quality", created["id"])
        assert fetched is not None
        assert fetched["data"] == {"tool": "rob2"}

    def test_get_nonexistent(self, store: HistoryStore) -> None:
        result = store.get("criteria", "no-such-id")
        assert result is None

    def test_get_corrupt_file(self, store: HistoryStore, tmp_path: Path) -> None:
        d = tmp_path / "criteria"
        d.mkdir(parents=True, exist_ok=True)
        (d / "bad-id.json").write_text("{invalid", encoding="utf-8")
        assert store.get("criteria", "bad-id") is None


# ── rename ────────────────────────────────────────────────────


class TestRename:
    """Tests for HistoryStore.rename()."""

    def test_rename_updates_name_and_timestamp(self, store: HistoryStore) -> None:
        created = store.create("criteria", data={}, name="Old")
        result = store.rename("criteria", created["id"], "New Name")
        assert result is not None
        assert result["name"] == "New Name"
        assert result["updated_at"] >= created["updated_at"]
        # No data field in summary
        assert "data" not in result

    def test_rename_persists(self, store: HistoryStore) -> None:
        created = store.create("screening", data={}, name="Old")
        store.rename("screening", created["id"], "Renamed")
        fetched = store.get("screening", created["id"])
        assert fetched is not None
        assert fetched["name"] == "Renamed"

    def test_rename_nonexistent(self, store: HistoryStore) -> None:
        result = store.rename("criteria", "no-such-id", "X")
        assert result is None


# ── delete ────────────────────────────────────────────────────


class TestDelete:
    """Tests for HistoryStore.delete()."""

    def test_delete_existing(self, store: HistoryStore) -> None:
        created = store.create("extraction", data={})
        assert store.delete("extraction", created["id"]) is True
        assert store.get("extraction", created["id"]) is None

    def test_delete_nonexistent(self, store: HistoryStore) -> None:
        assert store.delete("criteria", "no-such-id") is False

    def test_delete_reduces_list(self, store: HistoryStore) -> None:
        a = store.create("quality", data={})
        store.create("quality", data={})
        assert len(store.list_items("quality")) == 2
        store.delete("quality", a["id"])
        assert len(store.list_items("quality")) == 1


# ── valid modules ─────────────────────────────────────────────


class TestClearModule:
    """Tests for HistoryStore.clear_module()."""

    def test_clear_module_returns_count(self, store: HistoryStore) -> None:
        store.create("criteria", data={"a": 1})
        store.create("criteria", data={"b": 2})
        store.create("screening", data={"c": 3})
        count = store.clear_module("criteria")
        assert count == 2
        assert len(store.list_items("criteria")) == 0
        assert len(store.list_items("screening")) == 1

    def test_clear_module_empty(self, store: HistoryStore) -> None:
        count = store.clear_module("criteria")
        assert count == 0

    def test_clear_module_invalid_raises(self, store: HistoryStore) -> None:
        with pytest.raises(ValueError, match="Invalid module"):
            store.clear_module("bogus")


class TestClearAll:
    """Tests for HistoryStore.clear_all()."""

    def test_clear_all_returns_total_count(self, store: HistoryStore) -> None:
        store.create("criteria", data={})
        store.create("screening", data={})
        store.create("evaluation", data={})
        count = store.clear_all()
        assert count == 3
        for m in VALID_MODULES:
            assert len(store.list_items(m)) == 0

    def test_clear_all_empty(self, store: HistoryStore) -> None:
        count = store.clear_all()
        assert count == 0


class TestValidModules:
    """Tests for module validation."""

    @pytest.mark.parametrize("module", sorted(VALID_MODULES))
    def test_all_valid_modules_work(self, store: HistoryStore, module: str) -> None:
        item = store.create(module, data={"test": True})
        assert item["module"] == module
        assert len(store.list_items(module)) == 1


def test_create_with_tags(tmp_path: Path) -> None:
    """History items should store and return tags."""
    store = HistoryStore(base_dir=tmp_path)
    item = store.create(
        module="criteria",
        data={"framework": "pico"},
        name="My Criteria",
        tags=["cardiology", "RCT"],
    )
    assert item["tags"] == ["cardiology", "RCT"]
    items = store.list_items("criteria")
    assert items[0]["tags"] == ["cardiology", "RCT"]
    full = store.get("criteria", item["id"])
    assert full["tags"] == ["cardiology", "RCT"]


def test_create_without_tags_defaults_empty(tmp_path: Path) -> None:
    """Tags should default to empty list when not provided."""
    store = HistoryStore(base_dir=tmp_path)
    item = store.create(module="criteria", data={})
    assert item["tags"] == []
