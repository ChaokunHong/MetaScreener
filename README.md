<p align="center">
  <h1 align="center">MetaScreener</h1>
  <p align="center">
    Open-source multi-LLM ensemble for systematic review workflows
  </p>
</p>

<p align="center">
  <a href="https://pypi.org/project/metascreener/"><img alt="PyPI" src="https://img.shields.io/pypi/v/metascreener?include_prereleases&color=blue"></a>
  <a href="https://hub.docker.com/r/chaokunhong/metascreener"><img alt="Docker" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fhub.docker.com%2Fv2%2Frepositories%2Fchaokunhong%2Fmetascreener%2Ftags%2Flatest&query=name&label=docker&color=blue"></a>
  <a href="https://github.com/ChaokunHong/MetaScreener/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ChaokunHong/MetaScreener/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://opensource.org/licenses/Apache-2.0"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-blue.svg"></a>
</p>

---

MetaScreener is a local Python tool for AI-assisted systematic review (SR) workflows. It uses a **Hierarchical Consensus Network (HCN)** of 4 open-source LLMs with calibrated confidence aggregation, covering the full SR pipeline -- literature screening, data extraction, and risk-of-bias assessment -- in a single tool.

> **Note**: Looking for MetaScreener v1? See the [`v1-legacy`](../../tree/v1-legacy) branch.

## Features

- **Multi-LLM Ensemble** -- 4 open-source LLMs (Qwen3, DeepSeek-V3, Llama 4 Scout, Mistral Small 3.1) vote on every decision; no single model is a point of failure
- **3 SR Modules** -- Title/abstract screening, structured data extraction from PDFs, and risk-of-bias assessment (RoB 2, ROBINS-I, QUADAS-2)
- **Reproducible by Design** -- All models are open-source with version-locked weights; `temperature=0.0` for all inference; seeded randomness; SHA256 prompt hashing in every audit trail entry
- **Framework-Agnostic Criteria** -- Supports PICO, PEO, SPIDER, PCC, and custom frameworks with an interactive criteria wizard
- **Multiple Input/Output Formats** -- Reads RIS, BibTeX, CSV, PubMed XML, Excel; exports to RIS, CSV, JSON, Excel, and audit trail
- **CLI + Web UI** -- Full Typer CLI and Streamlit dashboard
- **Evaluation Toolkit** -- Built-in metrics (sensitivity, specificity, F1, WSS@95, AUROC, ECE, Brier score), Plotly visualizations (ROC, calibration, score distribution), and bootstrap 95% confidence intervals

## Installation

### pip

```bash
pip install metascreener
```

### Docker

```bash
# Slim image -- CLI and Streamlit UI
docker pull chaokunhong/metascreener:latest

# Full image -- includes validation experiments
docker pull chaokunhong/metascreener:full
```

### From source

```bash
git clone https://github.com/ChaokunHong/MetaScreener.git
cd MetaScreener
uv sync --extra dev
uv run metascreener --help
```

## Configuration

MetaScreener calls LLMs via cloud APIs. Set one of the following environment variables:

```bash
export OPENROUTER_API_KEY="your-key-here"   # OpenRouter (default)
# or
export TOGETHER_API_KEY="your-key-here"     # Together AI
```

Local inference via vLLM or Ollama is also supported -- see [`configs/models.yaml`](configs/models.yaml).

## Quick Start

### 1. Define review criteria

```bash
# From a research topic -- AI generates and refines criteria interactively
metascreener init --topic "antimicrobial resistance in ICU patients"

# From existing criteria text
metascreener init --criteria path/to/criteria.txt
```

The wizard auto-detects your criteria framework (PICO, PEO, SPIDER, PCC, or custom), generates structured criteria via multi-LLM consensus, validates them, and saves a versioned `criteria.yaml`.

### 2. Screen papers

```bash
# Title/abstract screening
metascreener screen --input search_results.ris --stage ta

# Full-text screening
metascreener screen --input search_results.ris --stage ft

# Both stages sequentially
metascreener screen --input search_results.ris --stage both
```

Each record passes through the 4-layer HCN and is assigned a decision (`INCLUDE`, `EXCLUDE`, or `HUMAN_REVIEW`) with a confidence tier (Tier 0--3).

### 3. Extract data

```bash
# Build a YAML extraction form interactively
metascreener extract init-form

# Run extraction on included PDFs
metascreener extract --pdfs papers/ --form extraction_form.yaml
```

Supports 7 field types: text, integer, float, boolean, date, list, and categorical. Multi-LLM extraction with majority-vote consensus.

### 4. Assess risk of bias

```bash
metascreener assess-rob --pdfs papers/ --tool rob2       # RoB 2 (RCTs)
metascreener assess-rob --pdfs papers/ --tool robins-i   # ROBINS-I (observational)
metascreener assess-rob --pdfs papers/ --tool quadas2    # QUADAS-2 (diagnostic)
```

Each tool follows its official domain structure with signaling questions. Multi-LLM assessment with worst-case-per-domain merging and majority-vote consensus.

### 5. Evaluate and export

```bash
# Evaluate against gold-standard labels with interactive Plotly charts
metascreener evaluate --labels gold_standard.csv --predictions results.json --visualize

# Export results in multiple formats
metascreener export --results results.json --format csv,json,excel,audit
```

### Web UI

```bash
metascreener ui   # Launches Streamlit dashboard at localhost:8501
```

## Architecture

MetaScreener's screening module uses a 4-layer Hierarchical Consensus Network:

```text
Records (RIS/BibTeX/CSV/XML/Excel)
    │
    ▼
┌────────────────────────────────────────────────────┐
│  Layer 1: Parallel LLM Inference                    │
│  4 models evaluate each record independently        │
│  Framework-specific prompts (PICO/PEO/SPIDER/PCC)  │
├────────────────────────────────────────────────────┤
│  Layer 2: Semantic Rule Engine                      │
│  3 hard rules (publication type, language,           │
│    study design) → auto-exclude                     │
│  3 soft rules (population, outcome, intervention)   │
│    → score penalty                                  │
├────────────────────────────────────────────────────┤
│  Layer 3: Calibrated Confidence Aggregation (CCA)   │
│  Platt/isotonic calibration + weighted consensus    │
│  S = Σ(wᵢ·sᵢ·cᵢ·φᵢ) / Σ(wᵢ·cᵢ·φᵢ)              │
│  C = 1 − H(p_inc, p_exc) / log(2)                 │
├────────────────────────────────────────────────────┤
│  Layer 4: Hierarchical Decision Router              │
│  Tier 0: Hard rule violation  → EXCLUDE             │
│  Tier 1: Unanimous + high conf → AUTO               │
│  Tier 2: Majority + mid conf  → INCLUDE             │
│  Tier 3: Disagreement / low   → HUMAN_REVIEW        │
└────────────────────────────────────────────────────┘
    │
    ▼
ScreeningDecision + AuditEntry (per record)
```

### LLM Models

All models are open-source and version-locked in [`configs/models.yaml`](configs/models.yaml).

| Model | Parameters | License | Role |
| ----- | ---------- | ------- | ---- |
| [Qwen3-235B-A22B](https://huggingface.co/Qwen/Qwen3-235B-A22B-Instruct) | 235B (22B active, MoE) | Apache 2.0 | Multilingual + structured extraction |
| [DeepSeek-V3.2](https://huggingface.co/deepseek-ai/DeepSeek-V3-0324) | 685B (37B active, MoE) | MIT | Complex reasoning + rule adherence |
| [Llama 4 Scout](https://huggingface.co/meta-llama/Llama-4-Scout-17B-16E-Instruct) | ~100B+ (MoE) | Llama License | General understanding |
| [Mistral Small 3.1 24B](https://huggingface.co/mistralai/Mistral-Small-3.1-24B-Instruct-2503) | 24B (dense) | Apache 2.0 | Fast screening + deterministic cases |

Inference runs via [OpenRouter](https://openrouter.ai/) or [Together AI](https://www.together.ai/) APIs. Local deployment via [vLLM](https://github.com/vllm-project/vllm) or [Ollama](https://ollama.com/) is also supported.

## Project Structure

```text
src/metascreener/
├── core/                  # Shared data models, enums, exceptions
├── io/                    # Readers/writers (RIS, BibTeX, CSV, XML, Excel, PDF)
├── llm/                   # LLM backends + parallel runner
│   └── adapters/          # OpenRouter, Together AI, vLLM, Ollama, Mock
├── criteria/              # Criteria wizard (8 frameworks, multi-LLM generation)
├── module1_screening/     # HCN screening (4 layers)
├── module2_extraction/    # Structured data extraction from PDFs
├── module3_quality/       # Risk-of-bias assessment (RoB 2, ROBINS-I, QUADAS-2)
├── evaluation/            # Metrics, calibration, Plotly visualization
├── cli/                   # Typer CLI commands
└── app/                   # Streamlit Web UI
```

## Reproducibility

Every design decision prioritizes reproducibility:

- **Deterministic inference**: `temperature=0.0` for all LLM calls
- **Version-locked models**: Exact model versions pinned in `configs/models.yaml`
- **Seeded randomness**: All stochastic operations accept a `seed` parameter (default: 42)
- **Prompt versioning**: SHA256 hash of every prompt stored in audit trail
- **Full audit trail**: Every decision logged with model outputs, rule results, calibration parameters, and confidence scores
- **Docker**: Complete environment reproduction via `docker/Dockerfile`
- **One-command reproduction**: `bash scripts/run_all_validations.sh` reruns all experiments

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests (645 tests)
uv run pytest

# Run tests with coverage (minimum 80%)
uv run pytest --cov=src/metascreener --cov-report=term-missing --cov-fail-under=80

# Lint
uv run ruff check src/

# Type check
uv run mypy src/
```

## Citation

If you use MetaScreener in your research, please cite:

```bibtex
@software{hong2026metascreener,
  author    = {Hong, Chaokun},
  title     = {MetaScreener: Open-Source Multi-LLM Ensemble for Systematic Review Workflows},
  url       = {https://github.com/ChaokunHong/MetaScreener},
  version   = {2.0.0},
  year      = {2026},
  license   = {Apache-2.0}
}
```

## License

Apache 2.0 -- see [LICENSE](LICENSE).
