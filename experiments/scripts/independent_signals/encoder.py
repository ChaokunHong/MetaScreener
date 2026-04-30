"""B4 encoder environment pre-flight."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from experiments.scripts.independent_signals.common import OUT_DIR, write_json


def run_encoder_env_preflight(out_dir: Path = OUT_DIR) -> dict[str, Any]:
    """Check whether B4 PubMedBERT/SciBERT can run in this environment."""
    modules = ["transformers", "torch", "sentence_transformers"]
    module_status = {
        module: importlib.util.find_spec(module) is not None
        for module in modules
    }
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    cached_models = (
        sorted(path.name for path in hf_cache.glob("models--*"))
        if hf_cache.exists()
        else []
    )
    candidate_cached = [
        name for name in cached_models
        if "pubmedbert" in name.lower() or "scibert" in name.lower()
    ]
    summary = {
        "scope": "B4_encoder_environment_preflight",
        "module_status": module_status,
        "huggingface_cache_exists": hf_cache.exists(),
        "cached_model_count": len(cached_models),
        "candidate_pubmedbert_scibert_cached_models": candidate_cached,
        "b4_correlation_runnable": (
            module_status["transformers"]
            and module_status["torch"]
            and bool(candidate_cached)
        ),
        "note": (
            "B4 correlation requires transformers, torch, and a cached or "
            "downloadable PubMedBERT/SciBERT model. This preflight does not "
            "download models."
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(summary, out_dir / "b4_encoder_env_preflight_summary.json")
    print(json.dumps(summary, indent=2, default=str))
    return summary
