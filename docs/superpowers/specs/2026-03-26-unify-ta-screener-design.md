# Design: Unify TAScreener as HCNScreener Subclass

**Date**: 2026-03-26
**Status**: Approved
**Goal**: Eliminate dual-track architecture; make TAScreener a thin subclass of HCNScreener

## Problem

`TAScreener` is an independent implementation that duplicates `HCNScreener`'s Layer 1-4 pipeline but omits CAMD calibration, ECS gating, element consensus, and disagreement classification. The TA API route uses `TAScreener`, so these features — described in the paper and improved across 4 review rounds — are dead code in production TA screening.

## Design

### TAScreener becomes `HCNScreener` subclass

```python
# ta_screener.py — after
class TAScreener(HCNScreener):
    """Title/Abstract screening — thin HCN subclass (stage='ta')."""
    default_stage: str = "ta"
```

No custom `screen_single`, `screen_batch`, or `build_audit_entry`. All inherited from `HCNScreener`. Mirrors `FTScreener(HCNScreener)` pattern.

### Constructor compatibility

TAScreener's `__init__` accepts the same parameters as HCNScreener plus passes them through via `super().__init__()`. Existing callers using only `backends`, `timeout_s`, `router`, `aggregator` continue working (extra params have defaults).

### API route updates (`screening_ta.py`)

Two construction sites updated to pass config values:

```python
screener = TAScreener(
    backends=backends,
    timeout_s=180.0,
    router=dr,
    aggregator=agg,
    heuristic_alpha=cfg.calibration.camd_alpha,
    element_weights=ew,  # framework-specific from config
)
```

Where `ew = cfg.element_weights.get(framework, cfg.element_weights.get("default"))`.

### `__init__.py` export

Unchanged: `from metascreener.module1_screening.ta_screener import TAScreener`

### Files changed

| File | Change |
|------|--------|
| `ta_screener.py` | Rewrite: independent class → HCNScreener subclass (~190 lines → ~20 lines) |
| `screening_ta.py` | Update 2 construction sites with `heuristic_alpha` + `element_weights` |
| `__init__.py` | No change |
| `test_ta_screener.py` | Update assertions: `ScreeningDecision` now has `element_consensus`, `ecs_result`, `disagreement_result` fields |
| `test_hcn_pipeline.py` | May need minor adjustments |

### Files NOT changed

- `hcn_screener.py` — zero modifications
- `ft_screener.py` — zero modifications
- Frontend — zero modifications
- `configs/models.yaml` — zero modifications

### Backward compatibility

- `TAScreener(backends=[...])` still works (all extra params have defaults)
- `screen_single(record, criteria, seed=42)` still works (stage defaults to "ta")
- `screen_batch(records, criteria)` still works
- `ScreeningDecision` gains populated `element_consensus`, `ecs_result`, `disagreement_result` fields (previously None/empty) — additive, non-breaking

### What becomes active in TA screening

| Feature | Before | After |
|---------|--------|-------|
| CAMD calibration | ❌ | ✅ |
| ECS computation | ❌ | ✅ |
| ECS gating (Tier 1 EXCLUDE) | ❌ | ✅ |
| ECS gating (Tier 2) | ❌ | ✅ |
| Element consensus | ❌ | ✅ |
| Disagreement classification | ❌ | ✅ |
| min_decided threshold | ❌ | ✅ |
| Checkpoint support | ❌ | ✅ (via inherited screen_batch) |

### Risk

Low. The HCNScreener pipeline is well-tested (882+ tests pass). TAScreener tests will verify the subclass produces correct output. The behavioral change is that TA screening now applies stricter quality controls (CAMD, ECS gating) which may increase HUMAN_REVIEW rate — this is the intended improvement.
