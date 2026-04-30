# HR Attribution Audit

Config: `a13b_coverage_rule`

## Baseline

- Records: 226,941
- Sensitivity: 0.9594
- Auto rate: 0.3997
- Human review rate: 0.6003
- HR records: 136,228
- HR true excludes: 134,844
- HR true includes protected: 1,384

## Interpretation Warning

Current result JSONs do not store `eas_score`. Buckets mentioning `eas_or_margin_unobserved` are deliberately conservative: they mark where the saved trace is insufficient for exact router-cause recovery.

## Largest HR Buckets

| true label | proposed direction | cause | n |
|---:|---|---|---:|
| 0 | INCLUDE | include_blocked_by_low_ecs_or_possible_eas_widened_margin | 67,094 |
| 0 | EXCLUDE | exclude_blocked_by_exclude_certainty_or_possible_eas_widened_margin | 40,891 |
| 0 | EXCLUDE | exclude_blocked_by_exclude_certainty | 14,729 |
| 0 | EXCLUDE | exclude_blocked_by_inclusion_ecs_or_possible_eas_widened_margin | 4,101 |
| 0 | INCLUDE | include_blocked_by_eas_or_margin_unobserved | 3,461 |
| 0 | EXCLUDE | exclude_blocked_by_inclusion_ecs | 3,285 |
| 0 | INCLUDE | include_blocked_by_low_ecs | 674 |
| 1 | EXCLUDE | exclude_blocked_by_exclude_certainty_or_possible_eas_widened_margin | 578 |
| 1 | INCLUDE | include_blocked_by_low_ecs_or_possible_eas_widened_margin | 330 |
| 0 | EXCLUDE | exclude_blocked_by_two_model_eas_or_margin | 295 |

## Top Candidate Release Rules

| rule | selected HR | extra FN | auto gain | new sensitivity | precision |
|---|---:|---:|---:|---:|---:|
| p<=0.005, ECS<=0.4, EC=ignore, models=any, ASR>=0.8 | 1,978 | 0 | 0.0087 | 0.9594 | 1.0000 |
| p<=0.005, ECS<=0.4, EC=ignore, models=early2, ASR>=0.8 | 1,976 | 0 | 0.0087 | 0.9594 | 1.0000 |
| p<=0.005, ECS<=0.3, EC=ignore, models=any, ASR>=0.8 | 1,771 | 0 | 0.0078 | 0.9594 | 1.0000 |
| p<=0.005, ECS<=0.3, EC=ignore, models=early2, ASR>=0.8 | 1,769 | 0 | 0.0078 | 0.9594 | 1.0000 |
| p<=0.002, ECS<=0.4, EC=ignore, models=any, ASR>=0.8 | 1,755 | 0 | 0.0077 | 0.9594 | 1.0000 |
| p<=0.002, ECS<=0.4, EC=ignore, models=early2, ASR>=0.8 | 1,754 | 0 | 0.0077 | 0.9594 | 1.0000 |
| p<=0.002, ECS<=0.3, EC=ignore, models=any, ASR>=0.8 | 1,587 | 0 | 0.0070 | 0.9594 | 1.0000 |
| p<=0.002, ECS<=0.3, EC=ignore, models=early2, ASR>=0.8 | 1,586 | 0 | 0.0070 | 0.9594 | 1.0000 |
| p<=0.005, ECS<=0.2, EC=ignore, models=any, ASR>=0.8 | 1,420 | 0 | 0.0063 | 0.9594 | 1.0000 |
| p<=0.005, ECS<=0.2, EC=ignore, models=early2, ASR>=0.8 | 1,418 | 0 | 0.0062 | 0.9594 | 1.0000 |
| p<=0.002, ECS<=0.2, EC=ignore, models=any, ASR>=0.8 | 1,268 | 0 | 0.0056 | 0.9594 | 1.0000 |
| p<=0.002, ECS<=0.2, EC=ignore, models=early2, ASR>=0.8 | 1,267 | 0 | 0.0056 | 0.9594 | 1.0000 |

