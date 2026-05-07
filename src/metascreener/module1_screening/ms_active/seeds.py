"""Seed-selection helpers for MS-Active-Risk simulations."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Iterable
from dataclasses import dataclass

from metascreener.module1_screening.ms_active.models import ActiveRecord, RecordLabel


class SeedSelectionError(ValueError):
    """Raised when the primary offline seed protocol cannot be satisfied."""


@dataclass(frozen=True)
class InitialSeedSelection:
    """Initial labelled records for one active-learning simulation."""

    records: tuple[ActiveRecord, ActiveRecord]

    @property
    def human_work(self) -> int:
        """Return human work consumed by the initial labels."""
        return len(self.records)


def derive_seed(base_seed: int, dataset: str, stream: str) -> int:
    """Derive a stable 32-bit seed from a base seed, dataset, and stream."""
    key = f"{base_seed}:{dataset}:{stream}".encode()
    digest = hashlib.sha256(key).digest()
    return int.from_bytes(digest[:4], byteorder="big", signed=False)


def select_initial_seed_records(
    records: Iterable[ActiveRecord],
    *,
    base_seed: int,
    dataset: str,
) -> InitialSeedSelection:
    """Select one INCLUDE and one EXCLUDE seed record deterministically."""
    sorted_records = sorted(records, key=lambda record: record.record_id)
    if any(record.dataset != dataset for record in sorted_records):
        raise SeedSelectionError(
            f"Primary seed protocol requires records from a single dataset: {dataset}"
        )
    includes = [record for record in sorted_records if record.true_label is RecordLabel.INCLUDE]
    excludes = [record for record in sorted_records if record.true_label is RecordLabel.EXCLUDE]
    if not includes or not excludes:
        raise SeedSelectionError(
            "Primary seed protocol requires at least one INCLUDE and one EXCLUDE"
        )
    rng = random.Random(derive_seed(base_seed, dataset, "initial"))
    selected = [rng.choice(includes), rng.choice(excludes)]
    ordered_list = sorted(selected, key=lambda record: record.record_id)
    ordered = (ordered_list[0], ordered_list[1])
    return InitialSeedSelection(records=ordered)
