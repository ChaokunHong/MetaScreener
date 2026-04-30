#!/usr/bin/env python3
"""Phase 1 entrypoint for independent-signal ablation pre-flight."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.scripts.independent_signals.b1_lexical import run_b1_synergy  # noqa: E402
from experiments.scripts.independent_signals.b3_full_lodo import (  # noqa: E402
    run_b1_b2_b3_full_lodo,
)
from experiments.scripts.independent_signals.b3_seed_protocol import (  # noqa: E402
    run_b3_seed_protocol_synergy_sample,
)
from experiments.scripts.independent_signals.citation import run_citation_preflight  # noqa: E402
from experiments.scripts.independent_signals.common import OUT_DIR  # noqa: E402
from experiments.scripts.independent_signals.encoder import run_encoder_env_preflight  # noqa: E402
from experiments.scripts.independent_signals.encoder_bert import (  # noqa: E402
    SCIBERT_MODEL,
    run_encoder_synergy_sample,
)
from experiments.scripts.independent_signals.encoder_ranker import (  # noqa: E402
    run_encoder_ranker_synergy_sample,
)
from experiments.scripts.independent_signals.openalex_sample import (  # noqa: E402
    run_openalex_synergy_sample,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=[
            "b1-synergy",
            "b1-b2-b3-full-lodo",
            "b3-seed-protocol-synergy-sample",
            "citation-preflight",
            "encoder-env-preflight",
            "encoder-ranker-synergy-sample",
            "encoder-synergy-sample",
            "openalex-synergy-sample",
        ],
        required=True,
    )
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--sample-size", type=int, default=0)
    parser.add_argument("--pos-per-dataset", type=int, default=5)
    parser.add_argument("--neg-per-dataset", type=int, default=5)
    parser.add_argument("--model-name", default=SCIBERT_MODEL)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--timeout-s", type=float, default=10.0)
    parser.add_argument("--max-records-per-dataset", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.mode == "b1-synergy":
        run_b1_synergy(args.out_dir)
    elif args.mode == "b1-b2-b3-full-lodo":
        run_b1_b2_b3_full_lodo(
            out_dir=args.out_dir,
            timeout_s=args.timeout_s,
            max_records_per_dataset=args.max_records_per_dataset or None,
            workers=args.workers,
            force=args.force,
        )
    elif args.mode == "b3-seed-protocol-synergy-sample":
        run_b3_seed_protocol_synergy_sample(
            out_dir=args.out_dir,
            pos_per_dataset=args.pos_per_dataset,
            neg_per_dataset=args.neg_per_dataset,
            timeout_s=args.timeout_s,
        )
    elif args.mode == "citation-preflight":
        run_citation_preflight(
            out_dir=args.out_dir,
            sample_size=args.sample_size,
            timeout_s=args.timeout_s,
        )
    elif args.mode == "encoder-env-preflight":
        run_encoder_env_preflight(args.out_dir)
    elif args.mode == "encoder-ranker-synergy-sample":
        run_encoder_ranker_synergy_sample(
            out_dir=args.out_dir,
            model_name=args.model_name,
            pos_per_dataset=args.pos_per_dataset,
            neg_per_dataset=args.neg_per_dataset,
            batch_size=args.batch_size,
            max_length=args.max_length,
        )
    elif args.mode == "openalex-synergy-sample":
        run_openalex_synergy_sample(
            out_dir=args.out_dir,
            pos_per_dataset=args.pos_per_dataset,
            neg_per_dataset=args.neg_per_dataset,
            timeout_s=args.timeout_s,
        )
    elif args.mode == "encoder-synergy-sample":
        run_encoder_synergy_sample(
            out_dir=args.out_dir,
            model_name=args.model_name,
            pos_per_dataset=args.pos_per_dataset,
            neg_per_dataset=args.neg_per_dataset,
            batch_size=args.batch_size,
            max_length=args.max_length,
        )


if __name__ == "__main__":
    main()
