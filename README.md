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

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [User Guide](#user-guide)
  - [Interactive Mode](#interactive-mode)
  - [Typical Workflow](#typical-workflow)
  - [Step 1: Define Review Criteria](#step-1-define-review-criteria-metascreener-init)
  - [Step 2: Screen Papers](#step-2-screen-papers-metascreener-screen)
  - [Step 3: Extract Data](#step-3-extract-data-metascreener-extract)
  - [Step 4: Assess Risk of Bias](#step-4-assess-risk-of-bias-metascreener-assess-rob)
  - [Step 5: Evaluate Performance](#step-5-evaluate-performance-metascreener-evaluate)
  - [Step 6: Export Results](#step-6-export-results-metascreener-export)
- [Command Reference](#command-reference)
- [Architecture](#architecture)
- [Supported Formats](#supported-formats)
- [Reproducibility](#reproducibility)
- [Development](#development)
- [Citation](#citation)
- [License](#license)

## Features

- **Multi-LLM Ensemble** -- 4 open-source LLMs (Qwen3, DeepSeek-V3, Llama 4 Scout, Mistral Small 3.1) vote on every decision; no single model is a point of failure
- **3 SR Modules** -- Title/abstract screening, structured data extraction from PDFs, and risk-of-bias assessment (RoB 2, ROBINS-I, QUADAS-2)
- **Reproducible by Design** -- All models are open-source with version-locked weights; `temperature=0.0` for all inference; seeded randomness; SHA256 prompt hashing in every audit trail entry
- **Framework-Agnostic Criteria** -- Supports PICO, PEO, SPIDER, PCC, and custom frameworks with an interactive criteria wizard
- **Multiple Input/Output Formats** -- Reads RIS, BibTeX, CSV, PubMed XML, Excel; exports to RIS, CSV, JSON, Excel, and audit trail
- **Interactive Mode** -- Guided slash-command REPL that walks you through each step; no flags to memorize
- **CLI + Web UI** -- Full Typer CLI and Streamlit dashboard
- **Evaluation Toolkit** -- Built-in metrics (sensitivity, specificity, F1, WSS@95, AUROC, ECE, Brier score), Plotly visualizations, and bootstrap 95% confidence intervals

## Installation

### Option A: pip (recommended)

Requires **Python 3.11 or higher**.

```bash
pip install metascreener
```

Verify the installation:

```bash
metascreener --help
```

### Option B: Docker

No Python installation required -- everything is bundled in the image.

```bash
# Slim image -- CLI and Streamlit UI
docker pull chaokunhong/metascreener:latest

# Run a command
docker run -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" chaokunhong/metascreener screen --help

# Launch the web UI (accessible at http://localhost:8501)
docker run -p 8501:8501 -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" chaokunhong/metascreener ui
```

### Option C: From source

Requires [uv](https://docs.astral.sh/uv/) (Python package manager).

```bash
git clone https://github.com/ChaokunHong/MetaScreener.git
cd MetaScreener
uv sync --extra dev
uv run metascreener --help
```

## Configuration

MetaScreener calls open-source LLMs via cloud API providers. You need an API key from one of the following services:

### Get an API key

| Provider | Sign Up | Free Tier | Environment Variable |
|----------|---------|-----------|---------------------|
| [OpenRouter](https://openrouter.ai/) (default) | [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) | Yes | `OPENROUTER_API_KEY` |
| [Together AI](https://www.together.ai/) | [api.together.ai/settings/api-keys](https://api.together.ai/settings/api-keys) | Yes ($5 credit) | `TOGETHER_API_KEY` |

### Set the environment variable

```bash
# Linux / macOS
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"

# To make it permanent, add the line above to your ~/.bashrc or ~/.zshrc
echo 'export OPENROUTER_API_KEY="sk-or-v1-your-key-here"' >> ~/.zshrc
```

```powershell
# Windows (PowerShell)
$env:OPENROUTER_API_KEY = "sk-or-v1-your-key-here"
```

### Verify it works

```bash
metascreener screen --input your_file.ris --dry-run
```

If the key is set correctly, you will see `Validation passed` with model names listed. If not, you will see an error message asking you to set the key.

### Custom model configuration (advanced)

By default, MetaScreener uses 4 models defined in [`configs/models.yaml`](configs/models.yaml). You can override this with a custom config:

```bash
metascreener screen --input data.ris --config my_models.yaml
```

Local inference via [vLLM](https://github.com/vllm-project/vllm) or [Ollama](https://ollama.com/) is also supported -- see the config file for adapter options.

## User Guide

### Interactive Mode

If you are new to MetaScreener, the easiest way to get started is the **interactive mode**. Simply run `metascreener` with no arguments:

```bash
metascreener
```

This launches a guided terminal interface with slash commands:

```
┌──────────────────────────────────────────────────────┐
│  MetaScreener 2.0.0a3                                │
│  AI-assisted systematic review tool                  │
│                                                      │
│  Type /help for commands, /quit to exit.             │
└──────────────────────────────────────────────────────┘

 Quick Start — Typical Workflow
  Step  Command      Description
  1     /init        Define your review criteria
  2     /screen      Screen papers against your criteria
  3     /evaluate    Evaluate screening accuracy
  4     /extract     Extract structured data from PDFs
  5     /assess-rob  Assess risk of bias for included studies
  6     /export      Export results in your preferred format

metascreener> /init
```

Each command guides you step-by-step through the required inputs with prompts, defaults, and validation. You don't need to memorize any flags or options.

Available slash commands:

| Command | Description |
| ------- | ----------- |
| `/init` | Generate structured review criteria (PICO/PEO/SPIDER/PCC) |
| `/screen` | Screen literature (title/abstract or full-text) |
| `/extract` | Extract structured data from PDFs |
| `/assess-rob` | Assess risk of bias (RoB 2 / ROBINS-I / QUADAS-2) |
| `/evaluate` | Evaluate screening performance and compute metrics |
| `/export` | Export results (CSV, JSON, Excel, RIS) |
| `/status` | Show current working files and project state |
| `/help` | Show all available commands |
| `/quit` | Exit MetaScreener |

> **Tip**: All commands also work as direct CLI subcommands (e.g., `metascreener screen --input file.ris --criteria criteria.yaml`). See the [Command Reference](#command-reference) below for full flag documentation.

### Typical Workflow

A systematic review with MetaScreener follows these steps:

```
 1. Export search results from a database (PubMed, Scopus, etc.)
    ↓  (download as .ris, .bib, or .csv)
 2. Define your review criteria
    ↓  metascreener init
 3. Screen papers by title/abstract
    ↓  metascreener screen
 4. Extract data from included PDFs
    ↓  metascreener extract
 5. Assess risk of bias
    ↓  metascreener assess-rob
 6. (Optional) Evaluate screening accuracy against gold-standard labels
    ↓  metascreener evaluate
 7. Export results
    ↓  metascreener export
```

Each step is independent -- you can use any subset of commands. For example, you can use just the screening module without data extraction or risk-of-bias assessment.

---

### Step 1: Define Review Criteria (`metascreener init`)

Before screening, you need structured inclusion/exclusion criteria. The `init` command uses AI to help you create them.

**Mode A: From existing criteria text**

If you already have criteria written in a text file (e.g., from your protocol):

```bash
metascreener init --criteria criteria.txt
```

The tool will:
1. Parse your text and detect your framework (PICO, PEO, SPIDER, PCC, or custom)
2. Generate structured inclusion/exclusion criteria using 4 LLMs
3. Validate the criteria and check for gaps
4. Save the result as `criteria.yaml`

**Mode B: From a research topic**

If you are starting from scratch, provide a research topic and the AI will generate criteria for you:

```bash
metascreener init --topic "antimicrobial resistance in ICU patients"
```

**Example `criteria.txt`:**

```text
Population: Adult patients (>=18 years) admitted to intensive care units
Intervention: Antimicrobial stewardship programs or antibiotic de-escalation
Comparison: Standard care or no stewardship program
Outcome: Antimicrobial resistance rates, mortality, length of ICU stay
Study design: RCTs, cohort studies, before-after studies
Exclusions: Pediatric populations, non-ICU settings, editorials, case reports
```

**All options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--criteria PATH` | `-c` | Path to a text file containing your criteria |
| `--topic TEXT` | `-t` | Research topic (AI generates criteria from this) |
| `--mode [smart\|guided]` | `-m` | `smart` (default): minimal prompts; `guided`: step-by-step |
| `--output PATH` | `-o` | Output file path (default: `criteria.yaml`) |
| `--framework TEXT` | `-f` | Override auto-detected framework (e.g., `pico`, `peo`, `spider`, `pcc`) |
| `--template TEXT` | | Start from a built-in template (e.g., `amr`) |
| `--language TEXT` | `-l` | Force output language (e.g., `en`, `zh`, `es`) |
| `--resume` | | Resume an interrupted session |
| `--clean-sessions` | | Remove old session checkpoint files |

**Output:** A `criteria.yaml` file that is used by subsequent commands.

---

### Step 2: Screen Papers (`metascreener screen`)

The screening command is the core of MetaScreener. It reads your search results and uses the 4-layer HCN to classify each paper as `INCLUDE`, `EXCLUDE`, or `HUMAN_REVIEW`.

**Basic usage:**

```bash
# Screen by title and abstract (most common)
metascreener screen --input search_results.ris --criteria criteria.yaml

# Screen with full text
metascreener screen --input search_results.ris --criteria criteria.yaml --stage ft

# Run both title/abstract and full-text screening sequentially
metascreener screen --input search_results.ris --criteria criteria.yaml --stage both
```

**What happens during screening:**

For each paper, MetaScreener:
1. **Layer 1**: Sends the title/abstract to 4 LLMs in parallel; each returns a decision, confidence score, and element-by-element assessment
2. **Layer 2**: Applies 6 semantic rules (3 hard rules that auto-exclude editorials/letters/wrong language, 3 soft rules that penalize partial PICO mismatches)
3. **Layer 3**: Calibrates and aggregates the 4 model scores into a single confidence-weighted score
4. **Layer 4**: Routes to a decision tier:
   - **Tier 0**: Hard rule violation (e.g., editorial) -- auto-excluded
   - **Tier 1**: All 4 models agree + high confidence -- auto-decided
   - **Tier 2**: Majority agree + medium confidence -- auto-included (recall-biased)
   - **Tier 3**: Disagreement or low confidence -- flagged for human review

**Test your setup without making API calls:**

```bash
metascreener screen --input search_results.ris --dry-run
```

This validates your input file, shows how many records were loaded, and confirms which models will be used -- without calling any APIs or spending any credits.

**All options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--input PATH` | `-i` | **(Required)** Input file: `.ris`, `.bib`, `.csv`, `.xml`, `.xlsx` |
| `--criteria PATH` | `-c` | Path to `criteria.yaml` (from `metascreener init`) |
| `--stage [ta\|ft\|both]` | `-s` | Screening stage: `ta` (title/abstract, default), `ft` (full-text), `both` |
| `--output PATH` | `-o` | Output directory (default: `results/`) |
| `--config PATH` | | Custom `models.yaml` config file |
| `--seed INTEGER` | | Random seed for reproducibility (default: `42`) |
| `--dry-run` | | Validate inputs without running screening (no API calls) |

**Output files:**

| File | Description |
|------|-------------|
| `results/screening_results.json` | Decision, tier, score, and confidence for each paper |
| `results/audit_trail.json` | Full audit trail: model outputs, rule violations, prompt hashes, model versions |

---

### Step 3: Extract Data (`metascreener extract`)

After screening, extract structured data from the included PDFs.

**Step 3a: Create an extraction form**

First, define what data you want to extract. You can either write the YAML manually or let AI generate it:

```bash
# AI-generated form based on your research topic
metascreener extract init-form --topic "antimicrobial stewardship in ICU"
```

This creates an `extraction_form.yaml` that defines the fields to extract. You can edit this file to add, remove, or modify fields.

**Example `extraction_form.yaml`:**

```yaml
name: AMR stewardship extraction form
fields:
  - name: sample_size
    type: integer
    description: Total number of participants
  - name: study_design
    type: categorical
    options: [RCT, cohort, before-after, case-control]
  - name: intervention_type
    type: text
    description: Type of stewardship intervention
  - name: mortality_rate
    type: float
    description: All-cause mortality rate (proportion)
  - name: resistance_reduced
    type: boolean
    description: Whether antimicrobial resistance was reduced
```

Supported field types: `text`, `integer`, `float`, `boolean`, `date`, `list`, `categorical`.

**Step 3b: Run extraction**

```bash
metascreener extract --pdfs papers/ --form extraction_form.yaml
```

Place your PDF files in a directory (e.g., `papers/`). MetaScreener will:
1. Extract text from each PDF
2. Split long documents into chunks
3. Send each chunk to 4 LLMs
4. Merge results across chunks using majority-vote consensus
5. Validate extracted values against the field definitions

**All options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--pdfs PATH` | | Directory containing PDF files |
| `--form PATH` | `-f` | Path to `extraction_form.yaml` |
| `--output PATH` | `-o` | Output directory (default: `results/`) |
| `--dry-run` | | Validate inputs without running extraction |

**Subcommand:**

| Command | Description |
|---------|-------------|
| `metascreener extract init-form --topic TEXT` | Generate an extraction form using AI |

**Output:** `results/extraction_results.json` with structured data for each PDF.

---

### Step 4: Assess Risk of Bias (`metascreener assess-rob`)

Assess the risk of bias of included studies using standardized tools.

```bash
# RoB 2 -- for randomized controlled trials (5 domains, 22 signaling questions)
metascreener assess-rob --pdfs papers/ --tool rob2

# ROBINS-I -- for observational studies (7 domains, 24 signaling questions)
metascreener assess-rob --pdfs papers/ --tool robins-i

# QUADAS-2 -- for diagnostic accuracy studies (4 domains, 11 signaling questions)
metascreener assess-rob --pdfs papers/ --tool quadas2
```

Each assessment tool follows its official domain structure. For each study, MetaScreener:
1. Extracts text from the PDF
2. Sends each domain's signaling questions to 4 LLMs
3. Uses worst-case-per-domain merging (most pessimistic judgment wins per model)
4. Applies majority-vote consensus across models
5. Determines an overall risk-of-bias judgment

**All options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--pdfs PATH` | | **(Required)** Directory containing PDF files |
| `--tool TEXT` | `-t` | Assessment tool: `rob2` (default), `robins-i`, `quadas2` |
| `--output PATH` | `-o` | Output directory (default: `results/`) |
| `--seed INTEGER` | `-s` | Random seed (default: `42`) |
| `--dry-run` | | Validate inputs without running |

**Output:** `results/rob_results.json` with per-domain judgments, signaling question responses, and rationale.

---

### Step 5: Evaluate Performance (`metascreener evaluate`)

If you have gold-standard labels (e.g., from a human screening), you can evaluate MetaScreener's accuracy.

```bash
# Basic evaluation
metascreener evaluate --labels gold_standard.csv

# With interactive Plotly charts
metascreener evaluate --labels gold_standard.csv --predictions results/screening_results.json --visualize
```

**Gold-standard CSV format:**

```csv
record_id,label
abc123,1
def456,0
ghi789,1
```

Where `1` = include, `0` = exclude. The `record_id` column must match the IDs in your screening results.

**Metrics computed:**

| Metric | Description |
|--------|-------------|
| Sensitivity (Recall) | Proportion of relevant papers correctly identified |
| Specificity | Proportion of irrelevant papers correctly excluded |
| F1 Score | Harmonic mean of precision and recall |
| WSS@95 | Work saved over sampling at 95% recall |
| AUROC | Area under the ROC curve |
| ECE | Expected calibration error |
| Brier Score | Mean squared prediction error |
| Cohen's Kappa | Inter-rater agreement |

All metrics include bootstrap 95% confidence intervals (1000 iterations).

**All options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--labels PATH` | `-l` | **(Required)** Gold-standard labels CSV |
| `--predictions PATH` | `-p` | Predictions JSON file |
| `--visualize` | | Generate interactive HTML charts (ROC, calibration, score distribution) |
| `--output PATH` | `-o` | Output directory (default: `results/`) |
| `--seed INTEGER` | `-s` | Bootstrap random seed (default: `42`) |
| `--dry-run` | | Validate inputs only |

---

### Step 6: Export Results (`metascreener export`)

Export screening results to various formats for use in other tools (e.g., Covidence, Rayyan, Excel).

```bash
# Export as CSV
metascreener export --results results/screening_results.json --format csv

# Export as multiple formats at once
metascreener export --results results/screening_results.json --format csv,json,excel,audit
```

**All options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--results PATH` | `-r` | **(Required)** Path to screening results JSON |
| `--format TEXT` | `-f` | Comma-separated formats: `csv`, `json`, `excel`, `audit`, `ris` (default: `csv`) |
| `--output PATH` | `-o` | Output directory (default: `export/`) |

**Output formats:**

| Format | File | Use Case |
|--------|------|----------|
| `csv` | `results.csv` | Spreadsheet analysis, import into other SR tools |
| `json` | `results.json` | Programmatic access, data pipelines |
| `excel` | `results.xlsx` | Microsoft Excel, reporting |
| `audit` | `audit_trail.json` | Reproducibility, TRIPOD-LLM compliance |
| `ris` | `results.ris` | Import back into reference managers (Zotero, EndNote) |

---

## Command Reference

Quick reference for all commands:

```bash
# Help
metascreener --help              # Show all commands
metascreener <command> --help    # Show options for a specific command

# Step 0: Define criteria
metascreener init --criteria criteria.txt                  # From text file
metascreener init --topic "your research topic"            # From topic
metascreener init --criteria criteria.txt --framework pico # Force framework

# Step 1: Screen papers
metascreener screen --input data.ris --criteria criteria.yaml              # Title/abstract
metascreener screen --input data.ris --criteria criteria.yaml --stage ft   # Full-text
metascreener screen --input data.ris --criteria criteria.yaml --stage both # Both stages
metascreener screen --input data.ris --dry-run                             # Validate only

# Step 2: Extract data
metascreener extract init-form --topic "your topic"                # Generate form
metascreener extract --pdfs papers/ --form extraction_form.yaml    # Run extraction

# Step 3: Assess risk of bias
metascreener assess-rob --pdfs papers/ --tool rob2       # RCTs
metascreener assess-rob --pdfs papers/ --tool robins-i   # Observational
metascreener assess-rob --pdfs papers/ --tool quadas2    # Diagnostic

# Step 4: Evaluate
metascreener evaluate --labels gold.csv --visualize

# Step 5: Export
metascreener export --results results/screening_results.json --format csv,excel,ris
```

## Architecture

MetaScreener's screening module uses a 4-layer Hierarchical Consensus Network:

```text
Records (RIS/BibTeX/CSV/XML/Excel)
    |
    v
+----------------------------------------------------+
|  Layer 1: Parallel LLM Inference                    |
|  4 models evaluate each record independently        |
|  Framework-specific prompts (PICO/PEO/SPIDER/PCC)  |
+----------------------------------------------------+
|  Layer 2: Semantic Rule Engine                      |
|  3 hard rules (publication type, language,          |
|    study design) -> auto-exclude                    |
|  3 soft rules (population, outcome, intervention)   |
|    -> score penalty                                 |
+----------------------------------------------------+
|  Layer 3: Calibrated Confidence Aggregation (CCA)   |
|  Platt/isotonic calibration + weighted consensus    |
|  S = sum(w_i * s_i * c_i * phi_i)                  |
|      / sum(w_i * c_i * phi_i)                      |
|  C = 1 - H(p_inc, p_exc) / log(2)                 |
+----------------------------------------------------+
|  Layer 4: Hierarchical Decision Router              |
|  Tier 0: Hard rule violation  -> EXCLUDE            |
|  Tier 1: Unanimous + high conf -> AUTO              |
|  Tier 2: Majority + mid conf  -> INCLUDE            |
|  Tier 3: Disagreement / low   -> HUMAN_REVIEW       |
+----------------------------------------------------+
    |
    v
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

## Supported Formats

### Input formats

| Format | Extension | Notes |
|--------|-----------|-------|
| RIS | `.ris` | Most common export format from databases (PubMed, Scopus, Web of Science) |
| BibTeX | `.bib` | Exported from Zotero, Mendeley, Google Scholar |
| CSV | `.csv` | Must have `title` column; `abstract` column recommended |
| PubMed XML | `.xml` | Direct PubMed search export |
| Excel | `.xlsx` | Must have `title` column |

### Output formats

| Format | Extension | Generated by |
|--------|-----------|-------------|
| JSON | `.json` | All commands |
| CSV | `.csv` | `metascreener export --format csv` |
| Excel | `.xlsx` | `metascreener export --format excel` |
| RIS | `.ris` | `metascreener export --format ris` |
| Audit trail | `.json` | `metascreener export --format audit` |
| HTML charts | `.html` | `metascreener evaluate --visualize` |

## Reproducibility

Every design decision prioritizes reproducibility:

- **Deterministic inference**: `temperature=0.0` for all LLM calls
- **Version-locked models**: Exact model versions pinned in `configs/models.yaml`
- **Seeded randomness**: All stochastic operations accept a `seed` parameter (default: 42)
- **Prompt versioning**: SHA256 hash of every prompt stored in audit trail
- **Full audit trail**: Every decision logged with model outputs, rule results, calibration parameters, and confidence scores
- **Docker**: Complete environment reproduction via `docker/Dockerfile`
- **One-command reproduction**: `bash scripts/run_all_validations.sh` reruns all experiments

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
