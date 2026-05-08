# External v2 FP Audit Adjudicator Instructions

**Status:** Template prepared before sampling. Do not attach records until the
OSF/Zenodo public timestamp for `paper/fp_audit_external_v2_protocol.md` v1.0
has been obtained.

## Purpose

You are independently adjudicating records sampled from the external v2
false-positive audit of MetaScreener. The goal is to classify why each sampled
record was a false positive under the original dataset label.

This is not a human-factors study. We are not measuring trust, speed, or
reviewer preference. We are only adjudicating record-level eligibility against
the dataset-specific criteria.

## What You Will See

For each record, you will see:

- dataset name;
- title;
- abstract;
- dataset-specific eligibility criteria.

You will not see:

- the original gold label;
- the MetaScreener decision;
- model scores or confidence fields;
- whether the record came from auto-INCLUDE or HUMAN_REVIEW.

## Procedure

Before you adjudicate the real audit set, you will receive a **10-record
training set** drawn from records outside the locked frame. Training answers
are not counted toward the audit metric — they only align you on the category
definitions below. After training, you may ask procedural questions, but you
may not discuss specific records with the other adjudicators.

The real audit records are presented to you in a **fixed pseudo-random order
specific to you**. The order is set by a per-adjudicator seed derived from
the locked sampling seed; you cannot influence the order, and you do not
need to know it. You must adjudicate every record in your assigned set.

## Categories

Choose exactly one category per record.

**Categories are mutually exclusive.** Do not assign two categories to one record.
If a record has more than one issue, pick the **dominant** cause — the single
category that best explains why this record is a false positive. Use the comment
field to flag any secondary issue.

**Categories are locked.** You cannot propose new categories or modify the
definitions below. If a record genuinely does not fit any of the five
categories, mark `adjudication_error_or_unclear` and explain in the comment.

### `genuine_fp`

The record clearly fails the review's eligibility criteria. The system-side
INCLUDE / review-routing decision was wrong on the merits.

### `label_error`

The record arguably or clearly meets the eligibility criteria. The original
review's EXCLUDE label appears incorrect or unsupported.

### `ambiguous_scope`

The review criteria are not specific enough to decide from title and abstract.
Both INCLUDE and EXCLUDE could be defended because the criteria are ambiguous.

### `insufficient_information`

The title and abstract do not contain enough information to apply the criteria.
This differs from `ambiguous_scope`: here the criteria may be clear, but the
record does not provide enough information.

### `adjudication_error_or_unclear`

Use this residual category only if the criteria document, audit interface, or
record metadata appears wrong, or if the case does not fit any category above.

## Confidence

Assign one confidence level:

- `low`
- `medium`
- `high`

Confidence is your confidence in the category assignment, not your confidence in
MetaScreener or the original dataset.

## Comments

Add a short comment only when it helps explain the category. One sentence is
enough. Do not include model-score speculation; you are blinded to those fields.

## Independence

Do not discuss specific records with other adjudicators until the full audit is
complete. If you believe a record or criteria file is corrupted, mark
`adjudication_error_or_unclear` and note the issue in the comment.
