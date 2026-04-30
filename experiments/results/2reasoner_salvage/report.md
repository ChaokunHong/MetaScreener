# 2-Reasoner Salvage Analysis

This is a cache-only counterfactual on the historical 13-dataset dev cohort.

## Pooled Results

| variant | sens | spec | auto | HR | delta auto | delta FN |
|---|---:|---:|---:|---:|---:|---:|
| auto_exclude_veto_any_include | 0.9944 | 0.1410 | 0.5552 | 0.4448 | +0.0000 | +0 |
| auto_exclude_veto_both_include | 0.9944 | 0.1410 | 0.5552 | 0.4448 | +0.0000 | +0 |
| base | 0.9944 | 0.1410 | 0.5552 | 0.4448 | +0.0000 | +0 |
| hr_include_only_both_include | 0.9944 | 0.1410 | 0.5559 | 0.4441 | +0.0007 | +0 |
| include_only_plus_veto_any_include | 0.9944 | 0.1410 | 0.5559 | 0.4441 | +0.0007 | +0 |
| old_hr_both_include_or_exclude | 0.9143 | 0.3231 | 0.7353 | 0.2647 | +0.1801 | +128 |

## Interpretation

- The old 2-reasoner auto-EXCLUDE rule is the unsafe condition.
- Include-only release is sensitivity-safe here but resolves almost no HR.
- Auto-EXCLUDE veto cannot be evaluated well unless reasoner cache covers base EXCLUDE records.
