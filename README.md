# MetaScreener 2.0

> Open-source multi-LLM ensemble for systematic review workflows

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

**Note**: Looking for MetaScreener v1? See the [`v1-legacy`](../../tree/v1-legacy) branch.

---

MetaScreener 2.0 is a complete rewrite of [MetaScreener](https://github.com/ChaokunHong/MetaScreener), designed for AI-assisted systematic review (SR) workflows. It uses a **Hierarchical Consensus Network (HCN)** of 4 open-source LLMs with calibrated confidence aggregation, covering literature screening, data extraction, and risk-of-bias assessment in a single tool.

## Highlights

- **4 open-source LLMs** in a Hierarchical Consensus Network (HCN) ensemble
- **3 SR modules**: literature screening, structured data extraction, quality/risk-of-bias assessment
- **>=95% sensitivity** on benchmark datasets (Cohen 2006, ASReview Synergy)
- **Complete reproducibility** -- all models are open-source with version-locked weights; no proprietary APIs required
- **~$0.005/record** average cost via OpenRouter or Together AI
- **TRIPOD-LLM compliant** audit trail for every decision

## Installation

### pip (recommended)

```bash
pip install metascreener
```

### Docker

```bash
# Slim image -- CLI and Streamlit UI
docker build -f docker/Dockerfile --target slim -t metascreener .
docker run metascreener screen --help
docker run -p 8501:8501 metascreener ui

# Full image -- includes validation experiments for paper reproduction
docker build -f docker/Dockerfile --target full -t metascreener:full .
docker run metascreener:full bash scripts/run_all_validations.sh --mock
```

### From source

```bash
git clone https://github.com/ChaokunHong/MetaScreener.git
cd MetaScreener
uv sync --extra dev
uv run metascreener --help
```

## Configuration

MetaScreener requires an API key for LLM inference. Set one of the following environment variables:

```bash
export OPENROUTER_API_KEY="your-key-here"   # OpenRouter (default)
# or
export TOGETHER_API_KEY="your-key-here"     # Together AI
```

For local inference via vLLM or Ollama, see `configs/models.yaml`.

## Quick Start

### 1. Define review criteria

```bash
# From a research topic (AI generates and refines PICO criteria)
metascreener init --topic "antimicrobial resistance in ICU patients"

# From existing criteria text
metascreener init --criteria path/to/criteria.txt
```

### 2. Screen papers

```bash
# Title/abstract screening
metascreener screen --input search_results.ris --stage ta

# Full-text screening
metascreener screen --input search_results.ris --stage ft

# Both stages sequentially
metascreener screen --input search_results.ris --stage both
```

### 3. Extract data

```bash
# Build an extraction form interactively
metascreener init-form

# Run extraction on included PDFs
metascreener extract --pdfs papers/ --form extraction_form.yaml
```

### 4. Assess quality / risk of bias

```bash
metascreener assess-rob --pdfs papers/ --tool rob2       # RoB 2 (RCTs)
metascreener assess-rob --pdfs papers/ --tool robins-i   # ROBINS-I (observational)
metascreener assess-rob --pdfs papers/ --tool quadas2    # QUADAS-2 (diagnostic)
```

### 5. Evaluate and export

```bash
metascreener evaluate --labels gold_standard.ris --visualize
metascreener export --format ris,csv,excel,audit
```

### Web UI

```bash
metascreener ui   # launches Streamlit dashboard at localhost:8501
```

## Architecture

MetaScreener's screening module uses a 4-layer Hierarchical Consensus Network:

1. **Layer 1 -- Parallel LLM Inference**: Each record is evaluated independently by 4 open-source LLMs
2. **Layer 2 -- Semantic Rule Engine**: Hard and soft PICO-based rules filter obvious exclusions
3. **Layer 3 -- Calibrated Confidence Aggregation (CCA)**: Platt-scaled model scores are combined via weighted consensus with entropy-based confidence estimation
4. **Layer 4 -- Hierarchical Decision Router**: Records are routed to one of 4 tiers (auto-exclude, auto-include with high/medium confidence, or human review) based on optimized thresholds

### LLM Models

All models are open-source and version-locked for reproducibility.

| Model | Parameters | License | Role |
| ----- | ---------- | ------- | ---- |
| Qwen3-235B-A22B | 235B (22B active, MoE) | Apache 2.0 | Multilingual + structured extraction |
| DeepSeek-V3.2 | 685B (37B active, MoE) | MIT | Complex reasoning + rule adherence |
| Llama 4 Scout | ~100B+ (MoE) | Llama License | General understanding |
| Mistral Small 3.1 24B | 24B (dense) | Apache 2.0 | Fast screening + deterministic cases |

Inference runs via OpenRouter or Together AI APIs. Local deployment via vLLM or Ollama is also supported.

## Reproducibility

All validation experiments can be reproduced with a single command:

```bash
bash scripts/run_all_validations.sh
```

This runs 7 experiments covering screening benchmarks (Cohen 2006, ASReview Synergy), ablation studies, extraction accuracy, risk-of-bias reliability, and cost analysis. All experiments use `seed=42` and report bootstrap 95% confidence intervals.

The `full` Docker image bundles everything needed for reproduction:

```bash
docker run metascreener:full bash scripts/run_all_validations.sh --mock
```

### Key design decisions for reproducibility

- `temperature=0.0` for all LLM calls
- SHA256 prompt hashing in every audit trail entry
- Version-locked model weights in `configs/models.yaml`
- Seeded randomness (`seed=42`) for all stochastic operations

## Development

```bash
uv sync --extra dev
uv run pytest                                     # run tests
uv run pytest --cov=src --cov-report=term-missing  # with coverage
uv run ruff check src/                            # lint
uv run mypy src/                                  # type check
```

## Citation

If you use MetaScreener in your research, please cite:

```bibtex
@article{hong2026metascreener,
  title     = {MetaScreener 2.0: An Open-Source Multi-LLM Ensemble for
               Systematic Review Screening, Data Extraction, and
               Quality Assessment},
  author    = {Hong, Chaokun},
  journal   = {The Lancet Digital Health},
  year      = {2026},
  note      = {Manuscript in preparation}
}

@software{hong2026metascreener_software,
  author    = {Hong, Chaokun},
  title     = {MetaScreener},
  url       = {https://github.com/ChaokunHong/MetaScreener},
  version   = {2.0.0},
  year      = {2026}
}
```

## License

Apache 2.0 -- see [LICENSE](LICENSE).
