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

## What is MetaScreener?

**MetaScreener** is a free, open-source tool that helps researchers do **systematic reviews** faster using AI.

A **systematic review** is a type of research where you search for all published studies on a topic, decide which ones are relevant (screening), pull out the key data (extraction), and assess quality (risk-of-bias). This process normally takes weeks or months of manual work. MetaScreener automates the tedious parts using 4 AI language models that work together to make decisions — while keeping a human in the loop for uncertain cases.

**In plain terms:** You give MetaScreener your search results (e.g., from PubMed), tell it what you're looking for, and it reads each paper's title and abstract and tells you which ones are relevant. It can also extract data from PDFs and assess study quality.

> **Note**: Looking for MetaScreener v1? See the [`v1-legacy`](../../tree/v1-legacy) branch.

### Three ways to use MetaScreener

| Method | Best for | What it looks like |
|--------|----------|-------------------|
| **Web UI** (`metascreener serve`) | Most users — point-and-click in your browser | A modern web application at `http://localhost:8000` |
| **Interactive CLI** (`metascreener`) | Terminal users who prefer guided prompts | A step-by-step command-line wizard |
| **Direct CLI** (`metascreener screen ...`) | Power users, scripting, and automation | One-line commands with flags |

All three methods use the same underlying AI engine and produce identical results.

---

## Table of Contents

- [Quick Start (5 minutes)](#quick-start-5-minutes)
- [Installation](#installation)
  - [Option A: pip](#option-a-pip-recommended)
  - [Option B: Docker](#option-b-docker)
  - [Option C: From source](#option-c-from-source-for-developers)
- [Configuration — Get Your API Key](#configuration--get-your-api-key)
- [User Guide: Web UI](#user-guide-web-ui)
- [User Guide: Command Line](#user-guide-command-line)
  - [Interactive Mode](#interactive-mode)
  - [Step 1: Define Review Criteria](#step-1-define-review-criteria-metascreener-init)
  - [Step 2: Screen Papers](#step-2-screen-papers-metascreener-screen)
  - [Step 3: Extract Data](#step-3-extract-data-metascreener-extract)
  - [Step 4: Assess Risk of Bias](#step-4-assess-risk-of-bias-metascreener-assess-rob)
  - [Step 5: Evaluate Performance](#step-5-evaluate-performance-metascreener-evaluate)
  - [Step 6: Export Results](#step-6-export-results-metascreener-export)
- [Command Reference](#command-reference)
- [How It Works](#how-it-works)
- [Supported File Formats](#supported-file-formats)
- [Reproducibility](#reproducibility)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [Development](#development)
- [Citation](#citation)
- [License](#license)

---

## Quick Start (5 minutes)

This section gets you from zero to screening in 5 minutes.

### 1. Install MetaScreener

```bash
pip install metascreener
```

> **Prerequisite:** You need Python 3.11 or higher. To check: `python --version`. If you don't have Python, see [Installation](#installation) for alternatives including Docker (no Python needed).

### 2. Get a free API key

MetaScreener uses cloud AI services to run its language models. You need a free API key:

1. Go to [openrouter.ai](https://openrouter.ai/) and create an account
2. Go to [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) and create a new key
3. Copy the key (it starts with `sk-or-v1-`)

### 3. Set the API key

```bash
# macOS / Linux
export OPENROUTER_API_KEY="sk-or-v1-paste-your-key-here"

# Windows PowerShell
$env:OPENROUTER_API_KEY = "sk-or-v1-paste-your-key-here"
```

### 4. Launch the Web UI

```bash
metascreener serve
```

Open your browser to **http://localhost:8000**. You'll see the MetaScreener dashboard.

From there:
1. Go to **Settings** — paste your API key and save
2. Go to **Screening** — upload your search results file (.ris, .csv, etc.)
3. Set your criteria (or let AI generate them from a topic)
4. Click **Run Screening** and watch results come in

**That's it!** You can also use the [command line](#user-guide-command-line) if you prefer.

---

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

You should see a list of available commands. If you get `command not found`, make sure Python's `bin` directory is in your system PATH.

### Option B: Docker

No Python installation needed — everything is bundled in the Docker image.

```bash
# Pull the image
docker pull chaokunhong/metascreener:latest

# Launch the Web UI (opens at http://localhost:8000)
docker run -p 8000:8000 \
  -e OPENROUTER_API_KEY="sk-or-v1-your-key-here" \
  chaokunhong/metascreener

# Or run a specific command
docker run -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  chaokunhong/metascreener screen --help
```

> **What is Docker?** Docker is a tool that packages software with all its dependencies into a single container. If you don't have Docker installed, download it from [docker.com](https://www.docker.com/products/docker-desktop/).

### Option C: From source (for developers)

Requires [uv](https://docs.astral.sh/uv/) (a fast Python package manager).

```bash
git clone https://github.com/ChaokunHong/MetaScreener.git
cd MetaScreener
uv sync --extra dev
uv run metascreener --help
```

To also build the React Web UI from source:

```bash
make build          # Builds frontend + Python wheel
make dev-backend    # Start API server (terminal 1)
make dev-frontend   # Start frontend dev server (terminal 2)
```

---

## Configuration — Get Your API Key

MetaScreener calls open-source AI models via cloud API providers. The models themselves are free and open-source, but the cloud providers charge a small fee for running them (typically less than $0.005 per paper screened).

### Step 1: Choose a provider and sign up

| Provider | Free Tier | Sign-Up Link |
|----------|-----------|-------------|
| **OpenRouter** (recommended) | Yes | [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) |
| **Together AI** | Yes ($5 free credit) | [api.together.ai/settings/api-keys](https://api.together.ai/settings/api-keys) |

### Step 2: Set the environment variable

After signing up and creating an API key:

**macOS / Linux:**

```bash
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"
```

To make this permanent (so you don't have to type it every time), add the line above to your shell configuration file:

```bash
# For zsh (default on macOS)
echo 'export OPENROUTER_API_KEY="sk-or-v1-your-key-here"' >> ~/.zshrc
source ~/.zshrc

# For bash (default on most Linux)
echo 'export OPENROUTER_API_KEY="sk-or-v1-your-key-here"' >> ~/.bashrc
source ~/.bashrc
```

**Windows PowerShell:**

```powershell
$env:OPENROUTER_API_KEY = "sk-or-v1-your-key-here"
```

To make it permanent on Windows, search for "Environment Variables" in the Start menu, click "Edit the system environment variables", then add `OPENROUTER_API_KEY` as a new user variable.

**Or set it via the Web UI:** Launch `metascreener serve`, go to Settings, and paste your key there. This is saved to `~/.metascreener/config.yaml`.

### Step 3: Verify it works

```bash
metascreener screen --input your_file.ris --dry-run
```

If the key is set correctly, you will see `Validation passed` with model names listed. The `--dry-run` flag means no API calls are made and no money is spent.

### Custom model configuration (advanced)

By default, MetaScreener uses 4 models defined in [`configs/models.yaml`](configs/models.yaml). You can override this:

```bash
metascreener screen --input data.ris --config my_models.yaml
```

Local inference via [vLLM](https://github.com/vllm-project/vllm) or [Ollama](https://ollama.com/) is also supported — see the config file for adapter options.

---

## User Guide: Web UI

The Web UI is the easiest way to use MetaScreener. It provides a point-and-click interface in your browser.

### Starting the Web UI

```bash
metascreener serve
```

This starts a local web server. Open **http://localhost:8000** in your browser.

> **Tip:** Add `--port 3000` to use a different port. Add `--host 0.0.0.0` to make it accessible from other devices on your network.

### Web UI Pages

| Page | What it does |
|------|-------------|
| **Dashboard** | Overview of the workflow with quick-start links to each step |
| **Screening** | Upload search results → set criteria → run AI screening → view results |
| **Evaluation** | Upload gold-standard labels → compute metrics (sensitivity, specificity, etc.) → view charts |
| **Extraction** | Upload extraction form + PDFs → run data extraction → edit and export results |
| **Quality** | Select assessment tool (RoB 2 / ROBINS-I / QUADAS-2) → upload PDFs → view traffic-light table |
| **Settings** | Configure API keys, view available models, adjust inference parameters |

### Screening in the Web UI (step by step)

1. **Go to the Screening page** — click "Screening" in the left sidebar
2. **Upload your file** — drag and drop your .ris, .bib, .csv, or .xlsx file into the upload zone, or click "Browse Files"
3. **Set criteria** — choose one of three options:
   - **Upload YAML**: If you already have a `criteria.yaml` file from a previous session
   - **Generate from Topic**: Type your research topic (e.g., "antimicrobial resistance in ICU patients") and let AI generate criteria
   - **Enter Manually**: Type your criteria directly
4. **Run screening** — click the "Run Screening" button. You'll see a progress indicator as each paper is processed.
5. **View results** — each paper shows its decision (INCLUDE / EXCLUDE / HUMAN REVIEW), confidence score, and tier. You can sort and filter the table.
6. **Export** — download results as CSV, JSON, Excel, or RIS

### Streamlit Dashboard (legacy)

MetaScreener also includes a Streamlit-based dashboard for interactive data visualization:

```bash
metascreener ui
```

This opens at **http://localhost:8501** and provides interactive Plotly charts for evaluation results.

---

## User Guide: Command Line

### Interactive Mode

If you are new to the command line, the easiest way to start is the **interactive mode**. Run `metascreener` with no arguments:

```bash
metascreener
```

This launches a guided terminal interface:

```
┌──────────────────────────────────────────────────────┐
│  MetaScreener 2.0                                    │
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

metascreener>
```

Type a command (e.g., `/init`) and follow the prompts. Each command guides you step-by-step. You don't need to memorize any flags.

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

Each step is independent — you can use any subset. For example, you can use just the screening module without data extraction or risk-of-bias assessment.

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

If you are starting from scratch:

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

This is the core of MetaScreener. It reads your search results and classifies each paper as `INCLUDE`, `EXCLUDE`, or `HUMAN_REVIEW`.

**Basic usage:**

```bash
# Screen by title and abstract (most common)
metascreener screen --input search_results.ris --criteria criteria.yaml

# Screen with full text
metascreener screen --input search_results.ris --criteria criteria.yaml --stage ft

# Both title/abstract and full-text screening
metascreener screen --input search_results.ris --criteria criteria.yaml --stage both
```

**What happens during screening:**

For each paper, MetaScreener runs a 4-layer pipeline:

1. **Layer 1 — AI Inference**: Sends the title and abstract to 4 AI models in parallel. Each model returns a decision, a confidence score, and an element-by-element assessment (e.g., "Does the population match?").
2. **Layer 2 — Rule Engine**: Applies 6 rules: 3 "hard" rules that auto-exclude papers (e.g., editorials, wrong language, excluded study designs) and 3 "soft" rules that penalize partial mismatches.
3. **Layer 3 — Aggregation**: Combines the 4 model scores into a single confidence-weighted score using calibrated weights.
4. **Layer 4 — Decision**: Routes to a tier:
   - **Tier 0**: Hard rule violation → automatic EXCLUDE
   - **Tier 1**: All 4 models agree + high confidence → automatic decision
   - **Tier 2**: Majority agree + medium confidence → automatic INCLUDE (designed to not miss relevant papers)
   - **Tier 3**: Models disagree or low confidence → flagged for HUMAN REVIEW

**Test your setup without spending money:**

```bash
metascreener screen --input search_results.ris --dry-run
```

This validates your file, counts records, and confirms which models will be used — without making any API calls.

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
| `results/audit_trail.json` | Full audit trail with model outputs, rule violations, and prompt hashes |

---

### Step 3: Extract Data (`metascreener extract`)

After screening, extract structured data from the included PDFs.

**Step 3a: Create an extraction form**

First, define what data you want to extract:

```bash
# AI-generated form based on your research topic
metascreener extract init-form --topic "antimicrobial stewardship in ICU"
```

This creates an `extraction_form.yaml`. You can edit it to add, remove, or modify fields.

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

Place your PDFs in a folder (e.g., `papers/`). MetaScreener will:
1. Extract text from each PDF
2. Split long documents into manageable chunks
3. Send each chunk to 4 AI models
4. Merge results using majority-vote consensus
5. Validate extracted values against the field definitions

**All options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--pdfs PATH` | | Directory containing PDF files |
| `--form PATH` | `-f` | Path to `extraction_form.yaml` |
| `--output PATH` | `-o` | Output directory (default: `results/`) |
| `--dry-run` | | Validate inputs without running extraction |

| Subcommand | Description |
|------------|-------------|
| `metascreener extract init-form --topic TEXT` | Generate an extraction form using AI |

**Output:** `results/extraction_results.json` with structured data for each PDF.

---

### Step 4: Assess Risk of Bias (`metascreener assess-rob`)

Assess the quality of included studies using standardized tools:

```bash
# RoB 2 — for randomized controlled trials (5 domains, 22 signaling questions)
metascreener assess-rob --pdfs papers/ --tool rob2

# ROBINS-I — for observational studies (7 domains, 24 signaling questions)
metascreener assess-rob --pdfs papers/ --tool robins-i

# QUADAS-2 — for diagnostic accuracy studies (4 domains, 11 signaling questions)
metascreener assess-rob --pdfs papers/ --tool quadas2
```

For each study, MetaScreener:
1. Extracts text from the PDF
2. Sends each domain's signaling questions to 4 AI models
3. Uses worst-case merging per domain (most pessimistic judgment wins per model)
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

If you have gold-standard labels (e.g., from human reviewers), evaluate MetaScreener's accuracy:

```bash
# Basic evaluation
metascreener evaluate --labels gold_standard.csv

# With interactive charts
metascreener evaluate --labels gold_standard.csv --predictions results/screening_results.json --visualize
```

**Gold-standard CSV format:**

```csv
record_id,label
abc123,1
def456,0
ghi789,1
```

Where `1` = include, `0` = exclude. The `record_id` must match the IDs in your screening results.

**Metrics computed:**

| Metric | What it measures |
|--------|-----------------|
| Sensitivity (Recall) | Of all relevant papers, how many did MetaScreener find? (higher = better, target ≥95%) |
| Specificity | Of all irrelevant papers, how many did MetaScreener correctly exclude? |
| F1 Score | Balance between precision and recall |
| WSS@95 | Work saved compared to screening everything, at 95% recall |
| AUROC | Overall discriminative ability (0.5 = random, 1.0 = perfect) |
| ECE | Calibration error — how well confidence scores match actual accuracy |
| Brier Score | Mean squared prediction error (lower = better) |
| Cohen's Kappa | Agreement between MetaScreener and human reviewers |

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

Export results for use in other tools (Covidence, Rayyan, Excel, etc.):

```bash
# Export as CSV
metascreener export --results results/screening_results.json --format csv

# Multiple formats at once
metascreener export --results results/screening_results.json --format csv,json,excel,ris
```

**All options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--results PATH` | `-r` | **(Required)** Path to screening results JSON |
| `--format TEXT` | `-f` | Comma-separated: `csv`, `json`, `excel`, `audit`, `ris` (default: `csv`) |
| `--output PATH` | `-o` | Output directory (default: `export/`) |

**Output formats:**

| Format | File | Use case |
|--------|------|----------|
| `csv` | `results.csv` | Spreadsheets, import into Covidence/Rayyan |
| `json` | `results.json` | Programmatic access, data pipelines |
| `excel` | `results.xlsx` | Microsoft Excel, reporting |
| `audit` | `audit_trail.json` | Reproducibility, journal compliance |
| `ris` | `results.ris` | Import back into Zotero, EndNote, Mendeley |

---

## Command Reference

Quick reference for all commands:

```bash
# Help
metascreener --help              # Show all commands
metascreener <command> --help    # Show options for a specific command

# Web UI
metascreener serve                              # Launch Web UI at localhost:8000
metascreener serve --port 3000                  # Custom port
metascreener serve --host 0.0.0.0               # Allow network access
metascreener serve --api-only                   # API only (no frontend)

# Interactive mode
metascreener                                    # Guided slash-command REPL

# Streamlit dashboard
metascreener ui                                 # Launch at localhost:8501

# Define criteria
metascreener init --criteria criteria.txt                   # From text file
metascreener init --topic "your research topic"             # From topic
metascreener init --criteria criteria.txt --framework pico  # Force framework

# Screen papers
metascreener screen --input data.ris --criteria criteria.yaml              # Title/abstract
metascreener screen --input data.ris --criteria criteria.yaml --stage ft   # Full-text
metascreener screen --input data.ris --criteria criteria.yaml --stage both # Both stages
metascreener screen --input data.ris --dry-run                             # Validate only

# Extract data
metascreener extract init-form --topic "your topic"                # Generate form
metascreener extract --pdfs papers/ --form extraction_form.yaml    # Run extraction

# Assess risk of bias
metascreener assess-rob --pdfs papers/ --tool rob2       # RCTs
metascreener assess-rob --pdfs papers/ --tool robins-i   # Observational
metascreener assess-rob --pdfs papers/ --tool quadas2    # Diagnostic

# Evaluate
metascreener evaluate --labels gold.csv --visualize

# Export
metascreener export --results results/screening_results.json --format csv,excel,ris
```

---

## How It Works

### The Hierarchical Consensus Network (HCN)

MetaScreener's screening uses a 4-layer architecture where 4 AI models work together:

```text
Your search results (RIS / BibTeX / CSV / XML / Excel)
    │
    ▼
┌────────────────────────────────────────────────────┐
│  Layer 1: Parallel AI Inference                     │
│  4 open-source models read each paper independently │
│  Each returns: decision + confidence + reasoning    │
├────────────────────────────────────────────────────┤
│  Layer 2: Rule Engine                               │
│  3 hard rules: auto-exclude editorials, wrong       │
│    language, excluded study designs                  │
│  3 soft rules: penalize partial criteria mismatches  │
├────────────────────────────────────────────────────┤
│  Layer 3: Calibrated Aggregation                    │
│  Combine 4 model scores into one confidence-        │
│  weighted score using learned calibration weights    │
├────────────────────────────────────────────────────┤
│  Layer 4: Decision Router                           │
│  Tier 0: Rule violation     → EXCLUDE               │
│  Tier 1: All agree + high   → AUTO                  │
│  Tier 2: Majority + medium  → INCLUDE               │
│  Tier 3: Disagreement / low → HUMAN REVIEW          │
└────────────────────────────────────────────────────┘
    │
    ▼
Decision + Confidence Score + Full Audit Trail (per paper)
```

### Why 4 models instead of 1?

Using multiple models has key advantages:
- **No single point of failure** — if one model makes an error, the others catch it
- **Calibrated confidence** — when all 4 agree, you can be very confident; when they disagree, the paper is flagged for human review
- **Recall-biased design** — the system is deliberately designed to err on the side of inclusion, ensuring you don't miss relevant papers

### The 4 AI Models

All models are open-source with publicly available weights, ensuring full reproducibility.

| Model | Size | License | Strength |
| ----- | ---- | ------- | -------- |
| [Qwen3-235B-A22B](https://huggingface.co/Qwen/Qwen3-235B-A22B-Instruct) | 235B (22B active) | Apache 2.0 | Multilingual understanding |
| [DeepSeek-V3.2](https://huggingface.co/deepseek-ai/DeepSeek-V3-0324) | 685B (37B active) | MIT | Complex reasoning |
| [Llama 4 Scout](https://huggingface.co/meta-llama/Llama-4-Scout-17B-16E-Instruct) | ~100B+ | Llama License | General understanding |
| [Mistral Small 3.1 24B](https://huggingface.co/mistralai/Mistral-Small-3.1-24B-Instruct-2503) | 24B | Apache 2.0 | Fast, cost-efficient |

Models are called via [OpenRouter](https://openrouter.ai/) or [Together AI](https://www.together.ai/) APIs. Local deployment via [vLLM](https://github.com/vllm-project/vllm) or [Ollama](https://ollama.com/) is also supported.

---

## Supported File Formats

### Input formats

| Format | Extension | Where to get it |
|--------|-----------|----------------|
| RIS | `.ris` | PubMed, Scopus, Web of Science, Cochrane Library ("Export → RIS") |
| BibTeX | `.bib` | Zotero, Mendeley, Google Scholar ("Export → BibTeX") |
| CSV | `.csv` | Any spreadsheet. Must have a `title` column; `abstract` column recommended |
| PubMed XML | `.xml` | PubMed search results ("Save → XML") |
| Excel | `.xlsx` | Any spreadsheet. Must have a `title` column |

### Output formats

| Format | Extension | Use case |
|--------|-----------|----------|
| JSON | `.json` | All commands produce JSON. Good for programmatic use. |
| CSV | `.csv` | Open in Excel/Google Sheets, import into Covidence/Rayyan |
| Excel | `.xlsx` | Open directly in Microsoft Excel |
| RIS | `.ris` | Import back into reference managers (Zotero, EndNote) |
| Audit trail | `.json` | Full reproducibility record for journal submission |
| HTML charts | `.html` | Interactive evaluation plots (ROC curve, calibration) |

---

## Reproducibility

MetaScreener is designed for scientific publication. Every design decision prioritizes reproducibility:

| Feature | How it works |
|---------|-------------|
| **Deterministic inference** | `temperature=0.0` for all AI calls — same input always produces same output |
| **Version-locked models** | Exact model versions pinned in [`configs/models.yaml`](configs/models.yaml) |
| **Seeded randomness** | All stochastic operations use a configurable `seed` parameter (default: 42) |
| **Prompt versioning** | SHA256 hash of every prompt stored in the audit trail |
| **Full audit trail** | Every decision logged with: model outputs, rule results, calibration parameters, confidence scores |
| **Docker image** | Complete environment reproduction via `docker/Dockerfile` |
| **One-command reproduction** | `bash scripts/run_all_validations.sh` reruns all experiments |

---

## Troubleshooting

### "command not found: metascreener"

**Cause:** Python's `bin` directory is not in your PATH.

**Fix:**
```bash
# Try running with python -m
python -m metascreener --help

# Or find where pip installed it
pip show metascreener
```

### "OPENROUTER_API_KEY not set"

**Cause:** The environment variable is not set in your current terminal session.

**Fix:**
```bash
# Check if it's set
echo $OPENROUTER_API_KEY

# If empty, set it
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"
```

Or use the Web UI: `metascreener serve` → Settings → paste your key.

### "API error: 401 Unauthorized"

**Cause:** Your API key is invalid or expired.

**Fix:** Go to [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) and create a new key.

### "API error: 429 Too Many Requests"

**Cause:** You've hit the rate limit.

**Fix:** MetaScreener automatically retries with exponential backoff. If it persists, wait a few minutes and try again, or add credits to your account.

### "No module named 'metascreener'"

**Cause:** MetaScreener is not installed in the current Python environment.

**Fix:**
```bash
pip install metascreener
# or, if using uv:
uv pip install metascreener
```

### The Web UI shows a blank page

**Cause:** The frontend assets may not be built.

**Fix:**
```bash
# If installed via pip, reinstall:
pip install --force-reinstall metascreener

# If running from source:
cd frontend && npm ci && npm run build
```

### Screening is slow

**Cause:** Each paper requires 4 API calls (one per model). For 1000 papers, that's 4000 API calls.

**Tips:**
- Use `--dry-run` first to validate your input
- Papers are processed sequentially to respect rate limits
- Typical speed: 1-3 seconds per paper
- For large datasets (>5000 papers), consider running overnight

---

## FAQ

### How much does it cost?

MetaScreener itself is **free and open-source**. The only cost is the cloud API fees for running the AI models. With OpenRouter:
- Typical cost: **~$0.002–0.005 per paper** for title/abstract screening
- A 1000-paper screening run costs approximately **$2–5**
- OpenRouter offers a free tier for initial testing
- You can set spending limits on your OpenRouter dashboard

### Can I use it without an internet connection?

Not by default — MetaScreener calls cloud APIs for AI inference. However, if you have a GPU, you can run the models locally using [vLLM](https://github.com/vllm-project/vllm) or [Ollama](https://ollama.com/) and configure MetaScreener to use local adapters.

### Is my data sent to third parties?

Yes — paper titles and abstracts are sent to the cloud API provider (OpenRouter or Together AI) for processing. If this is a concern:
- Use local inference (vLLM/Ollama) to keep all data on your machine
- Review the API provider's privacy policies
- Do not send patient-identifiable data through cloud APIs

### What languages are supported?

MetaScreener works with papers in any language. The Qwen3 model is particularly strong at multilingual understanding. The criteria wizard can generate criteria in English, Chinese, Spanish, and other languages.

### Can I use fewer than 4 models?

Yes. Edit `configs/models.yaml` to enable/disable models, or use the Settings page in the Web UI. Using fewer models is faster and cheaper but may reduce accuracy.

### How accurate is it?

Performance depends on the dataset and criteria. In our validation experiments:
- **Sensitivity (recall):** ≥95% — MetaScreener finds at least 95% of relevant papers
- **Specificity:** ≥60% — reduces manual workload significantly
- **WSS@95:** ≥45% — saves at least 45% of screening effort at 95% recall

Papers flagged as HUMAN_REVIEW should always be checked manually.

---

## Development

### Project Structure

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
├── api/                   # FastAPI REST API + WebSocket endpoints
├── cli/                   # Typer CLI commands
├── app/                   # Streamlit Web UI (legacy)
└── web/                   # React frontend build artifacts

frontend/                  # React 19 + TypeScript + Vite source code
├── src/
│   ├── api/               # API client, TanStack Query hooks
│   ├── components/        # Glass Design System components
│   ├── pages/             # Dashboard, Screening, Evaluation, Extraction, Quality, Settings
│   ├── stores/            # Zustand state management
│   └── styles/            # Aurora + glass morphism CSS
└── vite.config.ts
```

### Running tests

```bash
# Install with dev dependencies
uv sync --extra dev

# Run all tests (723 tests)
uv run pytest

# Run with coverage report (minimum 80%)
uv run pytest --cov=src/metascreener --cov-report=term-missing --cov-fail-under=80

# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/

# Build everything (frontend + Python wheel)
make build
```

### Building the frontend from source

```bash
cd frontend
npm ci          # Install dependencies
npm run build   # Build to src/metascreener/web/dist/
npm run dev     # Start dev server with hot-reload
```

---

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

Apache 2.0 — see [LICENSE](LICENSE).
