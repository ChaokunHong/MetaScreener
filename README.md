<p align="center">
  <img src="frontend/public/logo.svg" alt="MetaScreener Logo" width="72" />
  <h1 align="center">MetaScreener</h1>
  <p align="center">
    Open-source multi-LLM ensemble for systematic review screening
  </p>
</p>

<p align="center">
  <a href="https://pypi.org/project/metascreener/"><img alt="PyPI" src="https://img.shields.io/pypi/v/metascreener?include_prereleases&color=blue"></a>
  <a href="https://hub.docker.com/r/chaokunhong/metascreener"><img alt="Docker" src="https://img.shields.io/badge/docker-chaokunhong%2Fmetascreener-blue"></a>
  <a href="https://opensource.org/licenses/Apache-2.0"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-blue.svg"></a>
</p>

---

## Overview

**MetaScreener** automates the screening phase of systematic reviews using an ensemble of open-source large language models. Instead of relying on a single model, it runs **multiple LLMs in parallel** and aggregates their outputs through a calibrated confidence pipeline — producing transparent, reproducible decisions with uncertainty quantification.

**Key idea:** Upload your search results from PubMed/Scopus/etc., define your review criteria (PICO/PEO/SPIDER), and MetaScreener reads each title & abstract — returning include/exclude decisions with confidence scores. Uncertain cases are routed to human review.

### Why MetaScreener?

| Feature | Description |
|---------|-------------|
| **Multi-LLM Ensemble** | 4+ open-source models vote together — no single point of failure |
| **Calibrated Confidence** | Post-hoc calibration (Platt/Isotonic) maps raw scores to true probabilities |
| **Tiered Decisions** | Auto-decide on high-confidence cases, flag uncertain ones for human review |
| **Element Consensus** | Per-element (P/I/C/O) agreement scoring across models |
| **Active Learning** | Human feedback loop recalibrates model weights in real time |
| **Full Reproducibility** | `temperature=0.0`, `seed=42`, audit trail on every decision |
| **Cost-Effective** | ~$0.003–0.009 per paper using free-tier API providers |

---

## Architecture

MetaScreener uses a **Hierarchical Consensus Network (HCN)** — a 4-layer screening pipeline:

```
                        ┌──────────────────────────────────┐
    Upload              │         Layer 1: Inference        │
  .ris/.bib ──────────▶ │  4+ LLMs run in parallel via API  │
  .csv/.xlsx            │  (DeepSeek, Qwen, Llama, Kimi…)  │
                        └──────────────┬───────────────────┘
                                       ▼
                        ┌──────────────────────────────────┐
    PICO/PEO/           │       Layer 2: Rule Engine        │
    SPIDER  ──────────▶ │  Hard rules (auto-exclude)        │
    Criteria            │  Soft rules (score penalties)      │
                        └──────────────┬───────────────────┘
                                       ▼
                        ┌──────────────────────────────────┐
                        │     Layer 3: CCA + ECS            │
                        │  Calibrated Confidence Aggregation │
                        │  Element Consensus Scoring         │
                        └──────────────┬───────────────────┘
                                       ▼
                        ┌──────────────────────────────────┐
                        │    Layer 4: Decision Router        │
                        │  Tier 0 → Hard-rule exclusion      │
                        │  Tier 1 → High-confidence auto     │
                        │  Tier 2 → Moderate auto-decide     │
                        │  Tier 3 → Human review             │
                        └──────────────────────────────────┘
```

---

## Supported Models

15 open-source LLMs via [OpenRouter](https://openrouter.ai/), organized by capability:

| Tier | Models | Characteristics |
|------|--------|----------------|
| **Flagship** | DeepSeek V3, Qwen 3, Kimi K2.5 | Best accuracy, strong medical knowledge |
| **Strong** | Llama 4 Maverick, GLM 5, MiniMax M2.7, Nous Hermes 4, Nvidia Nemotron, Cogito 671B, AI21 Jamba | Good balance of cost and performance |
| **Lightweight** | Gemma 3 27B, Mistral Small 4, Phi 4 | Fast and cheap, good for budget screening |

**Recommended presets:**

| Preset | Models | Cost/Paper | Best For |
|--------|--------|-----------|----------|
| Balanced | 4 models | ~$0.005 | Most reviews |
| Precision | 2 thinking + 2 large | ~$0.009 | High-stakes reviews |
| Budget | 1 anchor + 3 fast | ~$0.003 | Large-scale screening |

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- **An API key** from [OpenRouter](https://openrouter.ai/settings/keys) (free sign-up, pay-per-use)

### Option A: Install with pip

```bash
pip install metascreener
```

Then start the Web UI:

```bash
python -m metascreener
# → Open http://localhost:8000
```

### Option B: Docker (no Python needed)

```bash
docker pull chaokunhong/metascreener:latest

docker run -p 8000:8000 \
  -e OPENROUTER_API_KEY="sk-or-v1-your-key-here" \
  chaokunhong/metascreener
# → Open http://localhost:8000
```

### Option C: From source (for developers)

Requires [uv](https://docs.astral.sh/uv/) and [Node.js 18+](https://nodejs.org/).

```bash
git clone https://github.com/ChaokunHong/MetaScreener.git
cd MetaScreener

uv sync --extra dev        # Install Python dependencies
python run.py              # Start FastAPI + Vite dev servers
# → Backend: http://localhost:8000
# → Frontend: http://localhost:5173
```

### Configuration

Set your API key via **one** of these methods:

1. **Web UI** — Go to Settings page and paste your key
2. **Environment variable:**
   ```bash
   export OPENROUTER_API_KEY="sk-or-v1-your-key-here"
   ```

---

## Web UI Workflow

MetaScreener provides a modern web interface (Vue 3) with a guided step-by-step workflow:

| Step | Page | What It Does |
|------|------|-------------|
| 0 | **Criteria** | AI-generated PICO/PEO/SPIDER criteria from your research question |
| 1 | **Settings** | Select models, adjust thresholds, configure API keys |
| 2 | **Screening (TA)** | Upload search results → run title/abstract screening → review decisions |
| 3 | **Screening (FT)** | Upload PDFs → run full-text screening with intelligent chunking |
| 4 | **Extraction** | Extract structured data (tables, fields) from included PDFs |
| 5 | **Quality** | Risk-of-bias assessment (RoB 2 / ROBINS-I / QUADAS-2) |
| 6 | **Evaluation** | Performance metrics, calibration diagnostics, visualizations |
| 7 | **History** | Session audit trail with full decision provenance |

### Screening Flow

1. **Upload** your search export (.ris, .bib, .csv, .xlsx)
2. **Define criteria** — type your research question and let AI generate PICO criteria, or upload existing criteria
3. **Run screening** — papers are processed one-by-one with real-time progress
4. **Review** — each paper shows: decision, confidence score, tier, per-element consensus, model agreement
5. **Override** — disagree with a decision? Override it and the system learns from your feedback
6. **Export** — download results as CSV, Excel, JSON, or RIS

---

## How It Works

### Layer 1 — Parallel LLM Inference

Each paper is sent to 4+ LLMs simultaneously. Each model returns:
- **Decision** (include / exclude / uncertain)
- **Confidence score** (0–1)
- **Per-element assessment** (population, intervention, comparison, outcome)
- **Reasoning chain** explaining the decision

### Layer 2 — Semantic Rule Engine

Hard rules auto-exclude papers that violate non-negotiable criteria (e.g., wrong language, animal study when humans required). Soft rules apply score penalties for partial matches.

### Layer 3 — Calibrated Confidence Aggregation (CCA)

Raw model scores are **calibrated** using Platt scaling or isotonic regression, then aggregated with tier-weighted blending. The **Element Consensus Score (ECS)** measures per-element agreement across models — if all models agree that Population matches but disagree on Outcome, this is captured precisely.

### Layer 4 — Decision Router

Papers are routed to one of four tiers:

| Tier | Condition | Action |
|------|-----------|--------|
| **0** | Hard-rule violation | Auto-exclude |
| **1** | High ECS (≥0.60) + full model agreement | Auto-decide |
| **2** | Moderate ECS (≥0.10) + within dissent tolerance | Auto-decide with lower confidence |
| **3** | Low confidence or high disagreement | Route to human review |

---

## Supported File Formats

| Format | Extension | Source |
|--------|-----------|--------|
| RIS | `.ris` | PubMed, Scopus, Web of Science, Ovid, Embase |
| BibTeX | `.bib` | Google Scholar, Zotero, Mendeley |
| CSV | `.csv` | Any spreadsheet (must have `title` and `abstract` columns) |
| Excel | `.xlsx` | Any spreadsheet (must have `title` and `abstract` columns) |
| PDF | `.pdf` | For full-text screening and data extraction |

---

## Project Structure

```
MetaScreener/
├── configs/models.yaml            # Model registry + thresholds (single source of truth)
├── src/metascreener/
│   ├── api/                       # FastAPI backend + routes
│   ├── core/                      # Pydantic models, enums, exceptions
│   ├── io/                        # File readers/writers, PDF parser
│   ├── llm/                       # LLM backends, adapters, parallel runner
│   ├── criteria/                  # PICO/PEO/SPIDER criteria generator
│   ├── module1_screening/         # HCN 4-layer screening pipeline
│   │   ├── layer1/                #   Parallel LLM inference
│   │   ├── layer2/                #   Semantic rule engine
│   │   ├── layer3/                #   CCA + ECS aggregation
│   │   └── layer4/                #   Decision router
│   ├── module2_extraction/        # PDF data extraction
│   ├── module3_quality/           # Risk of bias (RoB 2 / ROBINS-I / QUADAS-2)
│   └── evaluation/                # Metrics, calibration, visualization
├── frontend/                      # Vue 3 + TypeScript + Vite
├── tests/                         # Unit + integration tests (all offline)
├── validation/                    # Reproducibility experiments
├── docker/Dockerfile              # Multi-stage build (slim / full)
├── run.py                         # Dev server launcher
└── pyproject.toml
```

---

## Evaluation Metrics

MetaScreener computes standard systematic review metrics:

- **Sensitivity** (recall) — proportion of relevant studies correctly identified
- **Specificity** — proportion of irrelevant studies correctly excluded
- **WSS@95** — Work Saved over Sampling at 95% recall
- **AUROC** — Area Under Receiver Operating Characteristic curve
- **Brier Score** — calibration quality (how well confidence matches correctness)
- **Calibration Curves** — visual diagnostic for model probability calibration
- **Bootstrap 95% CI** — confidence intervals on all metrics

---

## Development

```bash
# Install dependencies
uv sync --extra dev

# Run tests (all offline, no API keys needed)
uv run pytest

# Lint
uv run ruff check src/

# Type check
uv run mypy src/

# Dev server (FastAPI + Vite hot reload)
python run.py
```

### Docker Build

```bash
# Slim build (daily use)
docker build -f docker/Dockerfile --target slim -t metascreener .

# Full build (reproducibility experiments + visualization extras)
docker build -f docker/Dockerfile --target full -t metascreener:full .
```

---

## Reproducibility

MetaScreener is designed for **TRIPOD-LLM compliant** reproducibility:

- `temperature = 0.0` on all LLM calls (deterministic output)
- `seed = 42` on all stochastic operations
- Full audit trail: every decision logs model outputs, rule violations, confidence scores, and timestamps
- Session persistence: all screening sessions saved as JSON for re-analysis
- Calibration diagnostics: Brier scores, calibration curves, and confidence intervals

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Backend** | FastAPI, uvicorn, Pydantic 2 |
| **Frontend** | Vue 3 (Composition API), TypeScript, Vite, Pinia |
| **LLM Routing** | LiteLLM → OpenRouter API |
| **PDF Processing** | PyMuPDF (fitz), Tesseract OCR |
| **Data Processing** | pandas, NumPy, scikit-learn, SciPy |
| **Visualization** | Plotly, Chart.js |
| **Logging** | structlog (structured JSON) |
| **Testing** | pytest, MockLLMAdapter (fully offline) |

---

## Citation

If you use MetaScreener in your research, please cite:

```bibtex
@software{hong2025metascreener,
  author    = {Hong, Chaokun},
  title     = {{MetaScreener}: Open-Source Multi-LLM Ensemble for Systematic Review Screening},
  year      = {2025},
  url       = {https://github.com/ChaokunHong/MetaScreener},
  license   = {Apache-2.0}
}
```

---

## License

[Apache License 2.0](LICENSE) — free for academic and commercial use.
