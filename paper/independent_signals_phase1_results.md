# Independent Signals Phase 1 Results

**Generated:** 2026-04-30
**Pre-registration:** `paper/independent_signals_ablation_preregistration.md`
**Scope:** SYNERGY-only diagnostics plus B3 pre-flight and sampled B4 encoder checks.
**External tuning:** none.

## Phase 1 Summary

| Component | Result | Interpretation |
|---|---:|---|
| B1 pooled HR AUC | 0.6161 | Fails the conservative pooled AUC >= 0.65 diagnostic gate |
| B1 mean dataset HR AUC | 0.7786 | Lexical signal is useful within many individual reviews |
| B1 median dataset HR AUC | 0.7639 | Same direction as mean dataset AUC |
| B1 HR PR-AUC, pooled | 0.0292 | Low absolute precision under severe class imbalance |
| B1 Spearman with `p_include`, HR pooled | 0.3234 | Lexical is not redundant with LLM score |
| B3 identifier queryable rate | 100% in Cohen/CLEF/SYNERGY | Citation-network work is technically feasible |
| B3 OpenAlex sample found rate | 100% in all sampled cohorts | PMID and OpenAlex identifiers resolve after URN fix |
| B4 SciBERT delta sample AUC | 0.5813 | Weak sampled signal; does not pass the 0.65 diagnostic gate |
| B4 SciBERT include-cosine sample AUC | 0.6408 | Still below the gate, despite being the stronger encoder score |
| B4 PubMedBERT delta sample AUC | 0.5429 | Weaker than SciBERT |
| B4 PubMedBERT include-cosine sample AUC | 0.5428 | Weaker than SciBERT |
| B4-v2 SciBERT supervised ranker AUC | 0.5794 | Frozen-embedding LODO ranker does not improve over cosine |
| B4-v2 PubMedBERT supervised ranker AUC | 0.5908 | Better than PubMedBERT cosine, still below 0.65 |
| B4 best Spearman with `p_include` | 0.3324 | Not highly redundant with LLM score, but weak |
| B2 OpenAlex metadata sample AUC | 0.6672 | Modest sampled signal; not yet a full LODO gate result |
| B3 oracle citation sample AUC | 0.7126 | Promising upper bound, but uses ground-truth include seed IDs |
| B3 deployable 5-seed neighborhood AUC | 0.7309 | Real seed protocol passes diagnostic gate on sampled rows |
| B3 deployable 5-seed neighborhood full AUC | 0.6448 | Full HR result falls just below 0.65 gate |
| B3 citation-count sample AUC | 0.6084 | Raw citation volume is weak |
| B1+B2+B3 sampled LODO AUC | 0.7831 | Improves over each individual sampled signal, with moderate feature correlations |
| B1+B2+B3 deployable sampled LODO AUC | 0.7602 | Uses real 5-seed B3; improves little over B1 alone |
| B1+B2+B3 deployable full LODO AUC | 0.6020 | Full LODO combination does not improve over B3 alone |

## B1 Lexical Diagnostic

Primary task: among `HUMAN_REVIEW` records in SYNERGY, classify true INCLUDE
versus true EXCLUDE using B1 lexical score.

Pooled HR diagnostic:

| n HR | true INCLUDE | true EXCLUDE | AUC | PR-AUC |
|---:|---:|---:|---:|---:|
| 142,362 | 1,778 | 140,584 | 0.6161 | 0.0292 |

Dataset-level diagnostic:

| Metric | Value |
|---|---:|
| Datasets with defined AUC | 25/26 |
| Mean dataset AUC | 0.7786 |
| Median dataset AUC | 0.7639 |

Interpretation:

- If the diagnostic gate is interpreted as **pooled SYNERGY AUC**, B1 fails
  because 0.6161 < 0.65.
- If interpreted as **mean held-out dataset AUC**, B1 passes because 0.7786 >
  0.65.
- This ambiguity should be adjudicated before B1 is allowed to advance. I
  recommend treating the pooled result as the conservative gate and reporting
  the dataset-level result as evidence of within-review utility.

## B1 Decision Sweep

These sweeps are descriptive only. No threshold is selected.

### Rescue: auto-EXCLUDE -> HUMAN_REVIEW

| Auto-EXCLUDE fraction moved to HR | Records moved | FN rescued | Efficiency |
|---:|---:|---:|---:|
| 1% | 213 | 3 | 0.0141 |
| 5% | 1,061 | 5 | 0.0047 |
| 10% | 2,122 | 5 | 0.0024 |
| 25% | 5,304 | 9 | 0.0017 |

The 1% rescue slice is the only one above the pre-registered low-efficiency
flag of 0.01. Larger rescue slices save more false negatives but are
inefficient.

### Release: HUMAN_REVIEW -> EXCLUDE

| HR fraction released | Records released | New FN | True-EXCLUDE precision |
|---:|---:|---:|---:|
| 1% | 1,424 | 24 | 0.9831 |
| 5% | 7,119 | 80 | 0.9888 |
| 10% | 14,237 | 136 | 0.9904 |
| 25% | 35,591 | 298 | 0.9916 |

B1 lexical release does **not** approach the 99.9% true-EXCLUDE precision gate.
It cannot safely reduce HR as a direct decision rule.

## B3 Citation Pre-flight

Full-cohort identifier coverage:

| Cohort | Datasets | Records | Identifier type | Queryable rate |
|---|---:|---:|---|---:|
| Cohen | 15 | 18,731 | PMID | 1.000 |
| CLEF | 18 | 39,354 | PMID | 1.000 |
| SYNERGY | 26 | 169,288 | OpenAlex ID | 1.000 |

OpenAlex availability sample, 20 records per cohort:

| Cohort | OpenAlex found | referenced_works available | related_works available |
|---|---:|---:|---:|
| Cohen | 1.00 | 0.85 | 1.00 |
| CLEF | 1.00 | 0.75 | 0.95 |
| SYNERGY | 1.00 | 0.90 | 0.95 |

Interpretation: B3 is feasible from an identifier/coverage standpoint. A full
B3 implementation would still need rate-limited caching and a clear network
manifest.

## B2/B3 Stratified OpenAlex Sample

After the coverage pre-flight, a SYNERGY-only stratified HR sample was run with
up to 10 true-INCLUDE and 10 true-EXCLUDE `HUMAN_REVIEW` records per dataset.
This sampled diagnostic is not a full LODO gate result.

| Sample | Value |
|---|---:|
| Sampled records | 467 |
| OpenAlex records found | 462 |
| True INCLUDE | 205 |
| True EXCLUDE | 257 |

Diagnostic AUCs:

| Signal | AUC | PR-AUC | Interpretation |
|---|---:|---:|---|
| B1 lexical score, same sample | 0.7566 | 0.7478 | Strongest single sampled signal |
| B2 metadata score | 0.6672 | 0.6159 | Modest independent signal |
| B3 oracle citation seed overlap | 0.7126 | 0.6543 | Stronger, but oracle-only |
| Citation count score | 0.6084 | 0.5273 | Weak bibliometric proxy |
| B1+B2+B3 LODO logistic combination | 0.7831 | 0.7820 | Best sampled diagnostic, but inherits B3 oracle caveat |

Feature correlations on the same sampled rows:

| Pair | Spearman rho | Interpretation |
|---|---:|---|
| B1 lexical vs B2 metadata | 0.5824 | Moderate overlap, not redundant |
| B1 lexical vs B3 oracle citation | 0.3962 | Low-to-moderate overlap |
| B2 metadata vs B3 oracle citation | 0.2631 | Low overlap |

The B2 metadata score uses OpenAlex metadata terms only: work type, source,
topics, concepts, MeSH descriptors, keywords, and language. It intentionally
does not use title or abstract text.

The B3 oracle citation score counts overlap between a sampled record's
OpenAlex `referenced_works` / `related_works` and the same dataset's
ground-truth included OpenAlex IDs. This is an upper-bound diagnostic for a
future seed-based active-learning workflow. It is not deployable as-is because
the full ground-truth include set is unavailable during screening.

The B1+B2+B3 combination was evaluated with leave-one-dataset-out logistic
regression on the sampled rows. It is useful as a conflict/redundancy check:
the three signals are complementary enough to improve sampled AUC from 0.7566
(B1 alone on the same rows) to 0.7831. It should not be interpreted as a
deployable B5 result because B3 currently uses oracle include seeds.

## B3 Deployable Seed Protocol

To replace the oracle B3 score, a deployable seed-based protocol was tested on
the same SYNERGY sampled HR records. For each dataset, the protocol chooses a
fixed deterministic set of known true-INCLUDE OpenAlex works as seed papers
(`k = 1, 3, 5`). Each evaluated record is removed from its own seed set, so a
record cannot score highly by being known as its own seed. Scores are computed
from direct seed overlap and from overlap with the seed citation neighborhood.

Deployable B3 diagnostics:

| Score | AUC | PR-AUC | Interpretation |
|---|---:|---:|---|
| 1-seed direct overlap | 0.5259 | 0.4671 | Too sparse |
| 1-seed neighborhood count | 0.6226 | 0.5487 | Weak |
| 1-seed neighborhood Jaccard | 0.6226 | 0.5534 | Weak |
| 3-seed direct overlap | 0.5646 | 0.5052 | Too sparse |
| 3-seed neighborhood count | 0.7083 | 0.6413 | Useful |
| 3-seed neighborhood Jaccard | 0.7074 | 0.6505 | Useful |
| 5-seed direct overlap | 0.5927 | 0.5333 | Still weak |
| 5-seed neighborhood count | 0.7309 | 0.6744 | Best deployable B3 score |
| 5-seed neighborhood Jaccard | 0.7293 | 0.6760 | Comparable to count |

Deployable B1+B2+B3 combination:

| Feature set | AUC | PR-AUC | Interpretation |
|---|---:|---:|---|
| B1 lexical + B2 metadata + B3 5-seed neighborhood count | 0.7602 | 0.7649 | Slightly above B1 alone, below oracle combination |

Deployable feature correlations:

| Pair | Spearman rho | Interpretation |
|---|---:|---|
| B1 lexical vs B2 metadata | 0.5824 | Moderate overlap |
| B1 lexical vs B3 5-seed neighborhood count | 0.5194 | Moderate overlap |
| B2 metadata vs B3 5-seed neighborhood count | 0.3655 | Low-to-moderate overlap |

Interpretation: B3 is genuinely deployable if the workflow includes a small
set of known included seed papers. The useful signal comes from the citation
neighborhood, not from direct citation to the seed papers. However, after
replacing the oracle B3 score with the deployable 5-seed neighborhood score,
the combined B1+B2+B3 sampled LODO AUC drops from 0.7831 to 0.7602. This means
B3 is real but not transformative at this sample size.

## B1+B2+B3 Full SYNERGY LODO

The deployable B1+B2+B3 protocol was then rerun on the full SYNERGY HR set,
not the 10+10 stratified sample. This is the decisive diagnostic for whether
B1/B2/B3 should advance as a robust feature family. The run used 12 workers,
per-dataset feature caches, and only SYNERGY data.

| Quantity | Value |
|---|---:|
| HR records processed | 142,362 |
| OpenAlex-resolved HR records | 141,717 |
| True INCLUDE among resolved HR | 1,771 |
| True EXCLUDE among resolved HR | 139,946 |

Full diagnostic AUCs:

| Signal | AUC | PR-AUC | Interpretation |
|---|---:|---:|---|
| B1 lexical | 0.6170 | 0.0294 | Matches the earlier pooled B1 result |
| B2 metadata | 0.6159 | 0.0214 | Weak on full data |
| B3 1-seed neighborhood count | 0.6178 | 0.0293 | Weak |
| B3 3-seed neighborhood count | 0.6345 | 0.0328 | Useful but below gate |
| B3 5-seed neighborhood count | 0.6448 | 0.0354 | Best full single signal, just below 0.65 |
| B3 5-seed neighborhood Jaccard | 0.6426 | 0.0340 | Similar to count |

Full LODO combination:

| C | AUC | PR-AUC |
|---:|---:|---:|
| 0.1 | 0.6020 | 0.0361 |
| 1.0 | 0.6020 | 0.0361 |
| 10.0 | 0.6020 | 0.0361 |

Full feature correlations:

| Pair | Spearman rho | Interpretation |
|---|---:|---|
| B1 lexical vs B2 metadata | 0.2733 | Low-to-moderate overlap |
| B1 lexical vs B3 5-seed neighborhood count | 0.2554 | Low-to-moderate overlap |
| B2 metadata vs B3 5-seed neighborhood count | 0.0789 | Very low overlap |

Interpretation: the full-data result overrides the sampled optimism. B3
citation neighborhood is a real independent signal, but it lands just below the
pre-registered 0.65 diagnostic threshold. More importantly, the full
leave-one-dataset-out logistic combination does not improve over the best
single B3 feature; it drops to AUC 0.6020. This suggests the B1/B2/B3 signals
are not destructively correlated, but their calibration is not stable enough
across SYNERGY reviews for a pooled supervised combination to transfer.

Interpretation:

- B2 metadata is worth a proper SYNERGY LODO diagnostic if we accept the cost
  of caching OpenAlex metadata, but the full result shows it is weak alone.
- B3 citation network is promising only in a seed-based setting, and full-data
  B3 5-seed neighborhood count nearly reaches the diagnostic gate. It should
  not be presented as a direct MS-Screen component.
- B1+B2+B3 does not show destructive conflict on this sampled diagnostic:
  correlations are moderate or low, and the combined LODO AUC is higher than
  all individual sampled signals. The limiting issue is deployability of the
  current B3 oracle signal, not signal incompatibility.
- With a deployable 5-seed B3 protocol, the conflict concern remains low, but
  the full LODO combination is unstable and worse than B3 alone.
- Raw citation volume alone is not a useful independent signal.

## B4 Encoder Diagnostic

Environment pre-flight initially showed that `transformers`, `torch`, and a
cached PubMedBERT/SciBERT model were absent. B4 was then run with an ephemeral
`uv run --with torch --with transformers` environment, without changing project
dependencies. Both encoder runs used MPS.

Sample:

| Sample | Value |
|---|---:|
| Sampled records | 467 |
| True INCLUDE | 207 |
| True EXCLUDE | 260 |
| Batch size | 16 |
| Max length | 256 |

Diagnostic AUCs:

| Model | Encoder score | AUC | PR-AUC | Interpretation |
|---|---|---:|---:|---|
| SciBERT | Include cosine minus exclude cosine | 0.5813 | 0.5089 | Weak |
| SciBERT | Include cosine alone | 0.6408 | 0.5523 | Better, but still below 0.65 |
| PubMedBERT | Include cosine minus exclude cosine | 0.5429 | 0.4748 | Weak |
| PubMedBERT | Include cosine alone | 0.5428 | 0.4692 | Weak |

Correlation with LLM scores:

| Model | Pair | Spearman rho |
|---|---|---:|
| SciBERT | Encoder delta vs `p_include` | 0.3324 |
| SciBERT | Encoder delta vs `final_score` | 0.3324 |
| PubMedBERT | Encoder delta vs `p_include` | 0.2533 |
| PubMedBERT | Encoder delta vs `final_score` | 0.2533 |

Interpretation: neither SciBERT nor PubMedBERT is strongly redundant with the
LLM panel, but both are too weak to justify advancing B4 as a decision or
ranking feature under the pre-registered gate. PubMedBERT is materially worse
than SciBERT on this sampled diagnostic.

### B4-v2 Frozen Encoder + Supervised LODO Ranker

Because raw encoder cosine may be too weak a use of the embedding space, a
second B4 design was tested. In B4-v2, SciBERT/PubMedBERT are frozen feature
extractors over record title+abstract. A logistic classifier is trained under
leave-one-dataset-out folds, so each held-out dataset is scored by a model
trained only on the other 25 SYNERGY datasets. C values `{0.1, 1.0, 10.0}` are
reported explicitly.

SciBERT ranker:

| C | AUC | PR-AUC |
|---:|---:|---:|
| 0.1 | 0.5794 | 0.4989 |
| 1.0 | 0.5501 | 0.4761 |
| 10.0 | 0.5422 | 0.4692 |

PubMedBERT ranker:

| C | AUC | PR-AUC |
|---:|---:|---:|
| 0.1 | 0.5908 | 0.5187 |
| 1.0 | 0.5732 | 0.4995 |
| 10.0 | 0.5656 | 0.4876 |

Best-ranker correlations with LLM scores:

| Model | Spearman with `p_include` | Spearman with `final_score` |
|---|---:|---:|
| SciBERT ranker, C=0.1 | 0.1204 | 0.1204 |
| PubMedBERT ranker, C=0.1 | 0.0699 | 0.0699 |

Interpretation: B4-v2 confirms that the problem is not just the simple cosine
scoring rule. Frozen biomedical encoder embeddings are nearly independent of
the LLM score, but they do not provide a transferable discriminative boundary
across SYNERGY reviews. A stronger B4 would require a materially different
model class, such as a cross-encoder or fine-tuned task model, not just a
linear head over frozen embeddings.

## Current Recommendation

B1 should not advance to direct HR-release. The release precision is far below
the 99.9% gate.

For the diagnostic gate, there is a real interpretability issue:

- pooled AUC says B1 fails;
- mean dataset AUC says B1 has within-review signal.

The conservative path is:

1. treat B1 as failing the direct decision gate;
2. keep B1 as a ranking/feature candidate because it shows strong
   dataset-level and sampled signal, but do not use it as a standalone
   direct-decision release rule;
3. do not advance B2 metadata as a standalone component; the full diagnostic
   is weak despite low overlap with B1/B3;
4. treat deployable B3 as a near-miss independent signal: scientifically
   informative, but not yet passing the pre-registered full-data gate;
5. do not advance B4 encoder features based on either the cosine diagnostics
   or the frozen-embedding supervised ranker diagnostics.

## Source Files

- `experiments/scripts/independent_signals_phase1.py`
- `experiments/scripts/independent_signals/`
- `experiments/results/independent_signals_phase1/b1_synergy_summary.json`
- `experiments/results/independent_signals_phase1/b2_b3_openalex_synergy_sample_summary.json`
- `experiments/results/independent_signals_phase1/b3_seed_protocol_synergy_sample_summary.json`
- `experiments/results/independent_signals_phase1/b1_b2_b3_full_lodo_full_summary.json`
- `experiments/results/independent_signals_phase1/b3_citation_preflight_summary.json`
- `experiments/results/independent_signals_phase1/b4_encoder_env_preflight_summary.json`
- `experiments/results/independent_signals_phase1/b4_encoder_synergy_sample_allenai__scibert_scivocab_uncased_summary.json`
- `experiments/results/independent_signals_phase1/b4_encoder_synergy_sample_microsoft__BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext_summary.json`
- `experiments/results/independent_signals_phase1/b4_encoder_ranker_synergy_sample_allenai__scibert_scivocab_uncased_summary.json`
- `experiments/results/independent_signals_phase1/b4_encoder_ranker_synergy_sample_microsoft__BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext_summary.json`
