from __future__ import annotations

from pathlib import Path

import pytest
from tests.unit.ms_active.batch_helpers import dataset_input

from metascreener.module1_screening.ms_active import batch as batch_module
from metascreener.module1_screening.ms_active.batch import run_ms_active_batch


def test_run_ms_active_batch_refuses_existing_nonempty_dir_without_force(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "old.txt").write_text("do not overwrite", encoding="utf-8")

    with pytest.raises(FileExistsError, match="non-empty"):
        run_ms_active_batch(
            [dataset_input(tmp_path)],
            output_dir=output_dir,
            ranker_kind="a1_tfidf",
        )


def test_run_ms_active_batch_force_overwrites_own_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "manifest.json").write_text("old", encoding="utf-8")
    (output_dir / "per_dataset_summary.jsonl").write_text("old", encoding="utf-8")
    (output_dir / "events.jsonl.gz").write_text("old", encoding="utf-8")

    summary = run_ms_active_batch(
        [dataset_input(tmp_path)],
        output_dir=output_dir,
        ranker_kind="a1_tfidf",
        force=True,
        run_id="forced",
        created_at_utc="2026-04-30T00:00:00Z",
    )

    assert "forced" in summary.manifest_path.read_text(encoding="utf-8")
    assert "old" not in summary.per_dataset_path.read_text(encoding="utf-8")


def test_run_ms_active_batch_force_rejects_unknown_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "old.txt").write_text("do not delete", encoding="utf-8")

    with pytest.raises(FileExistsError, match="unknown"):
        run_ms_active_batch(
            [dataset_input(tmp_path)],
            output_dir=output_dir,
            ranker_kind="a1_tfidf",
            force=True,
        )

    assert (output_dir / "old.txt").read_text(encoding="utf-8") == "do not delete"
    assert not (output_dir / "manifest.json").exists()
    assert not (output_dir / "per_dataset_summary.jsonl").exists()
    assert not (output_dir / "events.jsonl.gz").exists()


def test_run_ms_active_batch_force_rejects_symlink_output_dir(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.symlink_to(target_dir, target_is_directory=True)

    with pytest.raises(FileExistsError, match="symlink"):
        run_ms_active_batch(
            [dataset_input(tmp_path)],
            output_dir=output_dir,
            ranker_kind="a1_tfidf",
            force=True,
        )

    assert not (target_dir / "manifest.json").exists()


def test_run_ms_active_batch_propagates_unsupported_ranker(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported ranker_kind"):
        run_ms_active_batch(
            [dataset_input(tmp_path)],
            output_dir=tmp_path / "out",
            ranker_kind="asreview",
        )


def test_batch_failure_does_not_leave_success_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    with pytest.raises(ValueError, match="Unsupported ranker_kind"):
        run_ms_active_batch(
            [dataset_input(tmp_path)],
            output_dir=output_dir,
            ranker_kind="asreview",
        )

    assert not output_dir.exists()


def test_batch_jsonl_write_failure_does_not_leave_partial_new_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "out"

    def fail_jsonl(*args: object, **kwargs: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(batch_module, "_write_jsonl", fail_jsonl)

    with pytest.raises(RuntimeError, match="disk full"):
        run_ms_active_batch(
            [dataset_input(tmp_path)],
            output_dir=output_dir,
            ranker_kind="a1_tfidf",
        )

    assert not output_dir.exists()


def test_batch_install_failure_removes_partial_new_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "out"
    original_replace = Path.replace

    def fail_manifest_install(self: Path, target: Path) -> Path:
        if (
            self.name == "manifest.json"
            and self.parent.name.startswith(".out.")
            and ".backup." not in self.parent.name
        ):
            raise RuntimeError("install failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_manifest_install)

    with pytest.raises(RuntimeError, match="install failed"):
        run_ms_active_batch(
            [dataset_input(tmp_path)],
            output_dir=output_dir,
            ranker_kind="a1_tfidf",
        )

    assert not output_dir.exists()


def test_batch_force_jsonl_write_failure_preserves_existing_owned_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "manifest.json").write_text("old manifest", encoding="utf-8")
    (output_dir / "per_dataset_summary.jsonl").write_text("old rows", encoding="utf-8")
    (output_dir / "events.jsonl.gz").write_text("old events", encoding="utf-8")

    def fail_jsonl(*args: object, **kwargs: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(batch_module, "_write_jsonl", fail_jsonl)

    with pytest.raises(RuntimeError, match="disk full"):
        run_ms_active_batch(
            [dataset_input(tmp_path)],
            output_dir=output_dir,
            ranker_kind="a1_tfidf",
            force=True,
        )

    assert (output_dir / "manifest.json").read_text(encoding="utf-8") == "old manifest"
    assert (output_dir / "per_dataset_summary.jsonl").read_text(encoding="utf-8") == "old rows"
    assert (output_dir / "events.jsonl.gz").read_text(encoding="utf-8") == "old events"


def test_batch_force_install_failure_restores_existing_owned_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "manifest.json").write_text("old manifest", encoding="utf-8")
    (output_dir / "per_dataset_summary.jsonl").write_text("old rows", encoding="utf-8")
    (output_dir / "events.jsonl.gz").write_text("old events", encoding="utf-8")
    original_replace = Path.replace

    def fail_manifest_install(self: Path, target: Path) -> Path:
        if (
            self.name == "manifest.json"
            and self.parent.name.startswith(".out.")
            and ".backup." not in self.parent.name
        ):
            raise RuntimeError("install failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_manifest_install)

    with pytest.raises(RuntimeError, match="install failed"):
        run_ms_active_batch(
            [dataset_input(tmp_path)],
            output_dir=output_dir,
            ranker_kind="a1_tfidf",
            force=True,
        )

    assert (output_dir / "manifest.json").read_text(encoding="utf-8") == "old manifest"
    assert (output_dir / "per_dataset_summary.jsonl").read_text(encoding="utf-8") == "old rows"
    assert (output_dir / "events.jsonl.gz").read_text(encoding="utf-8") == "old events"
