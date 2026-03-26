# CLAUDE.md — MetaScreener 2.0

> **Target**: Lancet Digital Health | **Version**: 2.0.0 | **Language**: 用中文交流

## What

Open-source SR tool: 4 open-source LLMs → ensemble screening with calibrated confidence → full reproducibility.

## Architecture

```
FastAPI backend (src/metascreener/api/)
  ├── criteria/       → PICO wizard (Step 0)
  ├── module1_screening/ → HCN 4-layer screening
  │   ├── layer1/ → 4 LLM parallel inference
  │   ├── layer2/ → semantic rule engine
  │   ├── layer3/ → calibrated confidence aggregation (CCA)
  │   └── layer4/ → decision router (Tier 0-3)
  ├── module2_extraction/ → PDF data extraction
  ├── module3_quality/    → RoB 2 / ROBINS-I / QUADAS-2
  └── evaluation/         → metrics, calibrator, visualizer

Vue 3 frontend (frontend/)
  └── src/views/ + stores/ + api.ts

Config: configs/models.yaml (single source of truth)
```

## Directory

```
MetaScreener/
├── configs/models.yaml       # Model registry + thresholds
├── src/metascreener/
│   ├── api/                  # FastAPI server + routes
│   ├── core/                 # Models, enums, exceptions
│   ├── io/                   # Readers, writers, PDF parser
│   ├── llm/                  # Backends + adapters + factory
│   ├── criteria/             # PICO criteria wizard
│   ├── module1_screening/    # HCN (4 layers)
│   ├── module2_extraction/   # Data extraction
│   ├── module3_quality/      # Risk of bias
│   ├── evaluation/           # Metrics + visualization
│   └── __main__.py           # Entry: uvicorn server
├── frontend/                 # Vue 3 + TypeScript + Vite
├── tests/                    # Unit + integration (all offline)
├── validation/               # Experiments for paper
├── docker/Dockerfile
├── run.py                    # Dev launcher (FastAPI + Vite)
└── pyproject.toml
```

## Entry Points

- **Production**: `python -m metascreener` → uvicorn on :8000
- **Development**: `python run.py` → FastAPI + Vite dev servers
- **No CLI**: CLI was removed. All interaction via Web UI.

## Code Rules

- Type annotations on all functions
- Google-style docstrings on public APIs
- `structlog` only (never `print`)
- `temperature=0.0` always
- `seed: int = 42` on all stochastic ops
- Files under 400 lines
- Tests run offline with MockLLMAdapter

## Run

```bash
uv sync --extra dev          # Install
uv run pytest                # Test
uv run ruff check src/       # Lint
uv run mypy src/             # Type check
python run.py                # Dev server
```

## Status

Code complete. 5-round systematic audit passed (903 tests, 30 issues fixed).
Next: run validation experiments with real LLMs (Cohen benchmark, ablation study).
