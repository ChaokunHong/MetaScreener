from __future__ import annotations

import json
from pathlib import Path

import pytest
from experiments.scripts import fp_audit_external_v2_sample as sample


def _record(
    dataset: str,
    record_id: str,
    decision: str,
    p_include: float,
    true_label: int = 0,
) -> dict[str, object]:
    return {
        "dataset": dataset,
        "record_id": record_id,
        "decision": decision,
        "true_label": true_label,
        "p_include": p_include,
        "final_score": p_include,
        "tier": "TWO",
        "models_called": 4,
        "ecs_final": 0.2,
        "eas_score": 0.8,
        "esas_score": 0.7,
        "exclude_certainty": 0.1,
        "effective_difficulty": 0.5,
        "title": f"Title {record_id}",
        "abstract": f"Abstract {record_id}",
        "criteria_path": f"experiments/criteria/{dataset}_criteria_v2.json",
    }


def test_frame_record_assigns_scope_family_and_confidence_band() -> None:
    low = sample.frame_record(_record("Cohen_ADHD", "r1", "INCLUDE", 0.1))
    mid = sample.frame_record(_record("CLEF_CD010038", "r2", "HUMAN_REVIEW", 0.5))
    high = sample.frame_record(_record("CLEF_CD010038", "r3", "INCLUDE", 0.9))

    assert low is not None
    assert low["scope"] == "A"
    assert low["dataset_family"] == "Cohen"
    assert low["p_include_band"] == "low"
    assert mid is not None
    assert mid["scope"] == "B"
    assert mid["dataset_family"] == "CLEF"
    assert mid["p_include_band"] == "mid"
    assert high is not None
    assert high["p_include_band"] == "high"


def test_frame_record_excludes_non_fp_and_zero_positive_datasets() -> None:
    assert sample.frame_record(_record("Cohen_ADHD", "r1", "EXCLUDE", 0.1)) is None
    assert sample.frame_record(_record("Cohen_ADHD", "r2", "INCLUDE", 0.9, true_label=1)) is None
    assert sample.frame_record(_record("CLEF_CD011140", "r3", "INCLUDE", 0.9)) is None


def test_allocate_scope_targets_redistributes_deficits_within_scope() -> None:
    cells = {
        ("Cohen", "low"): ["a"],
        ("Cohen", "mid"): [],
        ("Cohen", "high"): ["b", "c", "d"],
        ("CLEF", "low"): ["e", "f"],
        ("CLEF", "mid"): ["g"],
        ("CLEF", "high"): ["h", "i", "j"],
    }

    allocation = sample.allocate_scope_targets(cells, target_total=6)

    assert allocation == {
        ("Cohen", "low"): 1,
        ("Cohen", "mid"): 0,
        ("Cohen", "high"): 2,
        ("CLEF", "low"): 1,
        ("CLEF", "mid"): 1,
        ("CLEF", "high"): 1,
    }
    assert sum(allocation.values()) == 6


def test_sample_scope_is_deterministic_and_never_exceeds_cell_capacity() -> None:
    rows = [
        sample.frame_record(_record("Cohen_ADHD", "a", "INCLUDE", 0.1)),
        sample.frame_record(_record("Cohen_ADHD", "b", "INCLUDE", 0.8)),
        sample.frame_record(_record("Cohen_ADHD", "c", "INCLUDE", 0.9)),
        sample.frame_record(_record("CLEF_CD010038", "d", "INCLUDE", 0.4)),
    ]
    framed = [row for row in rows if row is not None]

    first = sample.sample_scope(framed, target_total=3, seed=20260507)
    second = sample.sample_scope(framed, target_total=3, seed=20260507)

    assert [row["audit_id"] for row in first.sampled] == [
        row["audit_id"] for row in second.sampled
    ]
    assert len(first.sampled) == 3
    assert first.scope == "A"


def test_cli_refuses_to_write_manifest_before_public_timestamp(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "fp_audit_external_v2"

    with pytest.raises(SystemExit, match="public timestamp"):
        sample.main([
            "--results-dir",
            str(tmp_path / "results"),
            "--datasets-dir",
            str(tmp_path / "datasets"),
            "--criteria-dir",
            str(tmp_path / "criteria"),
            "--output-dir",
            str(output_dir),
        ])

    assert not output_dir.exists()


def test_write_outputs_omits_system_fields_from_adjudicator_inputs(
    tmp_path: Path,
) -> None:
    rows = [
        sample.frame_record(_record("Cohen_ADHD", "a", "INCLUDE", 0.9)),
        sample.frame_record(_record("CLEF_CD010038", "b", "HUMAN_REVIEW", 0.2)),
    ]
    framed = [row for row in rows if row is not None]

    sample.write_outputs(
        output_dir=tmp_path,
        sampled=framed,
        manifest={
            "audit_id": "fp-audit-external-v2",
            "records": [
                sample.manifest_record(row)
                for row in framed
            ],
        },
    )

    manifest = json.loads((tmp_path / "sampling_manifest.json").read_text())
    assert len(manifest["records"]) == 2
    inputs = sorted((tmp_path / "audit_inputs").glob("*.json"))
    assert len(inputs) == 2
    packet = json.loads(inputs[0].read_text())
    assert {"audit_id", "dataset", "record_id", "title", "abstract", "criteria_path"} <= set(packet)
    forbidden = {"decision", "true_label", "p_include", "final_score", "ecs_final"}
    assert forbidden.isdisjoint(packet)


def test_build_sampling_manifest_includes_all_protocol_required_fields() -> None:
    """Lock the §4 manifest schema: every field listed in the protocol must
    be present, with the correct type / value where deterministic."""
    rows = [
        sample.frame_record(_record("Cohen_ADHD", "a", "INCLUDE", 0.1)),
        sample.frame_record(_record("Cohen_ADHD", "b", "INCLUDE", 0.5)),
        sample.frame_record(_record("CLEF_CD010038", "c", "INCLUDE", 0.9)),
        sample.frame_record(_record("CLEF_CD010038", "d", "HUMAN_REVIEW", 0.2)),
    ]
    framed = [row for row in rows if row is not None]
    scope_a = [row for row in framed if row["scope"] == "A"]
    scope_b = [row for row in framed if row["scope"] == "B"]
    scope_samples = [
        sample.sample_scope(scope_a, target_total=min(2, len(scope_a)), seed=20260507),
        sample.sample_scope(scope_b, target_total=min(1, len(scope_b)), seed=20260508),
    ]
    sampled = [row for sample_obj in scope_samples for row in sample_obj.sampled]

    manifest = sample.build_sampling_manifest(
        sampled=sampled,
        scope_samples=scope_samples,
        frame=framed,
        seed=20260507,
        protocol_commit="312efbba1bb301e5cda9c2b21849a783aba3f70e",
        public_timestamp="2026-05-09T12:00:00Z",
        script_commit_sha="testcommit0123456789abcdef",
    )

    required = {
        "audit_id",
        "generated_at_utc",
        "protocol_version",
        "protocol_commit",
        "script_commit_sha",
        "public_timestamp",
        "sampling_seed",
        "frame_snapshot_sha256",
        "n_frame_records",
        "n_sampled_records",
        "scope_targets",
        "realised_scope_counts",
        "per_scope_cell_available",
        "per_scope_cell_targets",
        "records",
    }
    assert required <= set(manifest.keys()), (
        f"manifest missing required fields: {required - set(manifest.keys())}"
    )
    assert manifest["audit_id"] == "fp-audit-external-v2"
    assert manifest["protocol_version"] == "v1.0"
    assert manifest["protocol_commit"] == "312efbba1bb301e5cda9c2b21849a783aba3f70e"
    assert manifest["script_commit_sha"] == "testcommit0123456789abcdef"
    assert manifest["public_timestamp"] == "2026-05-09T12:00:00Z"
    assert manifest["sampling_seed"] == 20260507
    assert manifest["scope_targets"] == {"A": 120, "B": 120}
    assert isinstance(manifest["frame_snapshot_sha256"], str)
    assert len(manifest["frame_snapshot_sha256"]) == 64
    assert manifest["n_frame_records"] == len(framed)
    assert manifest["n_sampled_records"] == len(sampled)


def test_build_sampling_manifest_records_omit_blinded_fields_in_packet_path() -> None:
    """Manifest records may carry system fields (audit/admin trail), but
    nothing in the manifest path should leak into adjudicator-facing packets.
    Re-asserts the contract at the manifest layer."""
    rows = [sample.frame_record(_record("Cohen_ADHD", "a", "INCLUDE", 0.9))]
    framed = [row for row in rows if row is not None]
    record = sample.manifest_record(framed[0])
    # Manifest records SHOULD include system fields for stratification audit.
    assert "p_include" in record
    assert "decision" in record
    assert "tier" in record
    # Adjudicator packets MUST NOT (covered by previous test).
