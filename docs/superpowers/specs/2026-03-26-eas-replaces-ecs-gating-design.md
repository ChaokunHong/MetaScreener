# Design: Element Agreement Score (EAS) Replaces ECS for Router Gating

**Date**: 2026-03-26
**Status**: Approved
**Goal**: Fix inverted ECS gating that blocks correct EXCLUDE decisions

## Problem

ECS (Element Consensus Score) measures element **match support**: `support_ratio = n_match / (n_match + n_mismatch)`. When used as a router gate, this creates an inverted relationship for EXCLUDE decisions:

- Papers that should be excluded have elements that DON'T match → low ECS
- Low ECS triggers the gate → HUMAN_REVIEW
- Result: **the more correct the exclusion, the more likely it gets blocked**

Real-world observation: 4/4 models unanimously EXCLUDE with high confidence → ECS ≈ 0.0 → gate fires → HUMAN_REVIEW. This makes automation rate near-zero for exclusions.

## Solution

Introduce **Element Agreement Score (EAS)** — a direction-agnostic metric that measures model **consistency** on element assessments, regardless of whether elements match or mismatch.

```
agreement_ratio_e = max(n_match, n_mismatch) / (n_match + n_mismatch)
EAS = Σ(w_e × agreement_ratio_e) / Σ(w_e)
```

| Scenario | ECS | EAS | Interpretation |
|----------|-----|-----|----------------|
| 4/4 match | 1.0 | 1.0 | Agree: elements match |
| 4/4 mismatch | 0.0 | 1.0 | Agree: elements don't match |
| 2 match + 2 mismatch | 0.5 | 0.5 | Disagree on elements |
| 3 match + 1 mismatch | 0.75 | 0.75 | Mostly agree |

EAS is symmetric — works correctly for both INCLUDE and EXCLUDE gating without special-casing.

## Changes

### 1. Add `compute_eas()` to `element_consensus.py`

New function alongside existing `compute_ecs()`:

```python
def compute_eas(
    element_consensus: dict[str, ElementConsensus],
    element_weights: dict[str, float] | None = None,
    min_decided: int = _MIN_DECIDED_VOTES,
) -> float:
    """Element Agreement Score — direction-agnostic model consistency.

    EAS = Σ(w_e × agreement_ratio_e) / Σ(w_e)
    agreement_ratio = max(n_match, n_mismatch) / (n_match + n_mismatch)
    """
```

- Same weights and `min_decided` logic as ECS
- When `decided < min_decided`: agreement = 0.5 (uncertain)
- Returns float in [0.0, 1.0]

### 2. Add `eas_score` to `ECSResult` model

Extend `ECSResult` with an `eas_score: float` field so both scores are available in a single object. No new model class needed.

### 3. Update `HCNScreener.screen_single()` to compute EAS

Call `compute_eas()` after `compute_ecs()`, store result in `ecs_result.eas_score`.

### 4. Replace ECS with EAS in router gating

In `router.py`, all three gate locations change from:
```python
ecs_result.score < self.ecs_threshold  # ECS: match support
```
To:
```python
ecs_result.eas_score < self.ecs_threshold  # EAS: model agreement
```

### 5. Keep ECS for informational purposes

- `ECSResult.score` (ECS) still computed and stored
- Available in `ScreeningDecision` for frontend display and audit trail
- `weak_elements` and `conflict_pattern` still derived from ECS

### Files changed

| File | Change |
|------|--------|
| `src/metascreener/core/models_consensus.py` | Add `eas_score` field to `ECSResult` |
| `src/metascreener/module1_screening/layer3/element_consensus.py` | Add `compute_eas()` function |
| `src/metascreener/module1_screening/hcn_screener.py` | Call `compute_eas()`, store in result |
| `src/metascreener/module1_screening/layer4/router.py` | Gate on `eas_score` instead of `score` |
| Tests | Update ECS gate tests, add EAS-specific tests |

### Files NOT changed

- `configs/models.yaml` — `ecs_threshold: 0.60` reused for EAS (same semantics: min agreement for auto-decision)
- Frontend — no change needed (EAS is backend-only gating metric)
- `config.py` — no new config values
