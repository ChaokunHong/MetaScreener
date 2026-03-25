"""Tests for RuntimeTracker model credibility system."""
from __future__ import annotations

from metascreener.core.enums import Decision
from metascreener.core.models import ModelOutput, PICOAssessment
from metascreener.module1_screening.layer3.runtime_tracker import RuntimeTracker


def _make_output(
    model_id: str,
    decision: Decision,
    score: float,
    confidence: float,
    elements: dict[str, bool | None] | None = None,
) -> ModelOutput:
    """Helper to create ModelOutput with optional element assessments."""
    pico: dict[str, PICOAssessment] = {}
    if elements:
        for key, match in elements.items():
            pico[key] = PICOAssessment(match=match, evidence="test")
    return ModelOutput(
        model_id=model_id,
        decision=decision,
        score=score,
        confidence=confidence,
        rationale="test",
        pico_assessment=pico,
    )


def test_no_contradiction_when_consistent() -> None:
    """Model with matching elements and decision has 0 contradiction rate."""
    tracker = RuntimeTracker(model_ids=["m1", "m2"])
    outputs = [
        _make_output("m1", Decision.INCLUDE, 0.8, 0.9,
                     {"population": True, "intervention": True}),
        _make_output("m2", Decision.INCLUDE, 0.7, 0.8,
                     {"population": True, "intervention": True}),
    ]
    tracker.update(outputs)
    weights = tracker.get_runtime_weights()
    assert weights["m1"] == 1.0
    assert weights["m2"] == 1.0


def test_contradiction_all_mismatch_but_include() -> None:
    """Model with all elements MISMATCH but decision INCLUDE is contradictory."""
    tracker = RuntimeTracker(model_ids=["m1", "m2"], window_size=5)
    for _ in range(5):
        outputs = [
            _make_output("m1", Decision.INCLUDE, 0.8, 0.9,
                         {"population": False, "intervention": False, "outcome": False}),
            _make_output("m2", Decision.EXCLUDE, 0.2, 0.9,
                         {"population": False, "intervention": False, "outcome": False}),
        ]
        tracker.update(outputs)
    weights = tracker.get_runtime_weights()
    assert weights["m1"] == 0.5  # 100% contradiction > 0.3 -> *0.5
    assert weights["m2"] == 1.0


def test_contradiction_all_match_but_exclude() -> None:
    """Model with all elements MATCH but decision EXCLUDE is contradictory."""
    tracker = RuntimeTracker(model_ids=["m1"], window_size=5)
    for _ in range(5):
        outputs = [
            _make_output("m1", Decision.EXCLUDE, 0.2, 0.9,
                         {"population": True, "intervention": True, "outcome": True}),
        ]
        tracker.update(outputs)
    weights = tracker.get_runtime_weights()
    assert weights["m1"] == 0.5


def test_moderate_contradiction_rate() -> None:
    """Contradiction rate between 0.15-0.3 gets moderate penalty."""
    tracker = RuntimeTracker(model_ids=["m1"], window_size=10)
    # 2 contradictions out of 10 = 0.2
    for i in range(10):
        if i < 2:
            outputs = [_make_output("m1", Decision.INCLUDE, 0.8, 0.9,
                                    {"population": False, "intervention": False})]
        else:
            outputs = [_make_output("m1", Decision.INCLUDE, 0.8, 0.9,
                                    {"population": True, "intervention": True})]
        tracker.update(outputs)
    weights = tracker.get_runtime_weights()
    assert weights["m1"] == 0.75  # 0.2 > 0.15 -> *0.75


def test_pilot_accuracy_low_with_sufficient_samples() -> None:
    """Low pilot accuracy penalizes runtime weight when n >= 30."""
    tracker = RuntimeTracker(model_ids=["m1", "m2"])
    tracker.set_pilot_accuracies({"m1": 0.4, "m2": 0.9}, n_samples=50)
    weights = tracker.get_runtime_weights()
    assert weights["m1"] == 0.3  # <0.5 -> *0.3
    assert weights["m2"] == 1.0


def test_pilot_accuracy_ignored_with_small_sample() -> None:
    """Pilot accuracy NOT applied when n < 30 (statistical noise)."""
    tracker = RuntimeTracker(model_ids=["m1", "m2"])
    tracker.set_pilot_accuracies({"m1": 0.4, "m2": 0.9}, n_samples=20)
    weights = tracker.get_runtime_weights()
    assert weights["m1"] == 1.0  # Not penalized — too few samples
    assert weights["m2"] == 1.0


def test_pilot_accuracy_moderate() -> None:
    """Moderate pilot accuracy gets moderate penalty when n >= 30."""
    tracker = RuntimeTracker(model_ids=["m1"])
    tracker.set_pilot_accuracies({"m1": 0.65}, n_samples=40)
    weights = tracker.get_runtime_weights()
    assert weights["m1"] == 0.6  # 0.5-0.7 -> *0.6


def test_composite_weights_normalized() -> None:
    """Composite weights are properly normalized to sum to 1."""
    tracker = RuntimeTracker(model_ids=["m1", "m2"])
    tracker.set_pilot_accuracies({"m1": 0.4, "m2": 0.9}, n_samples=50)
    base = {"m1": 0.5, "m2": 0.5}
    composite = tracker.get_composite_weights(base)
    assert composite["m2"] > composite["m1"]
    assert abs(sum(composite.values()) - 1.0) < 1e-6


def test_weight_floor_never_below_min() -> None:
    """No model weight drops below 0.1 even with all penalties."""
    tracker = RuntimeTracker(model_ids=["m1", "m2"], window_size=3)
    tracker.set_pilot_accuracies({"m1": 0.3, "m2": 0.9}, n_samples=50)
    for _ in range(3):
        outputs = [
            _make_output("m1", Decision.INCLUDE, 0.9, 0.9,
                         {"population": False, "intervention": False}),
            _make_output("m2", Decision.EXCLUDE, 0.1, 0.9,
                         {"population": False, "intervention": False}),
        ]
        tracker.update(outputs)
    weights = tracker.get_runtime_weights()
    assert weights["m1"] >= 0.1


def test_empty_elements_no_contradiction() -> None:
    """Models without element assessments are not flagged as contradictory."""
    tracker = RuntimeTracker(model_ids=["m1"])
    outputs = [_make_output("m1", Decision.INCLUDE, 0.8, 0.9)]
    tracker.update(outputs)
    weights = tracker.get_runtime_weights()
    assert weights["m1"] == 1.0


def test_error_outputs_ignored() -> None:
    """Error outputs are skipped by the tracker."""
    tracker = RuntimeTracker(model_ids=["m1"])
    error_output = ModelOutput(
        model_id="m1", decision=Decision.HUMAN_REVIEW,
        score=0.5, confidence=0.0, rationale="error",
        error="parse failure",
    )
    tracker.update([error_output])
    weights = tracker.get_runtime_weights()
    assert weights["m1"] == 1.0  # No data recorded


def test_full_lifecycle() -> None:
    """Full lifecycle: cold start -> contradiction -> pilot -> composite."""
    tracker = RuntimeTracker(model_ids=["strong", "weak"], window_size=10)

    # Phase 1: Cold start — all 1.0
    assert tracker.get_runtime_weights() == {"strong": 1.0, "weak": 1.0}

    # Phase 2: weak model contradicts itself
    for _ in range(10):
        tracker.update([
            _make_output("strong", Decision.EXCLUDE, 0.2, 0.9,
                         {"population": False, "intervention": False}),
            _make_output("weak", Decision.INCLUDE, 0.8, 0.9,
                         {"population": False, "intervention": False}),
        ])

    weights = tracker.get_runtime_weights()
    assert weights["weak"] < weights["strong"]

    # Phase 3: Pilot confirms weak is bad (n=50, above min threshold of 30)
    tracker.set_pilot_accuracies({"strong": 0.95, "weak": 0.35}, n_samples=50)
    weights = tracker.get_runtime_weights()
    assert weights["weak"] <= 0.15  # 0.5 * 0.3

    # Phase 4: Composite with prior
    prior = {"strong": 0.6, "weak": 0.4}
    composite = tracker.get_composite_weights(prior)
    assert composite["strong"] > 0.8
    assert abs(sum(composite.values()) - 1.0) < 1e-6
