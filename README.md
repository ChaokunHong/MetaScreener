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

- [Prerequisites — What You Need Before Starting](#prerequisites--what-you-need-before-starting)
- [Installation (Step by Step)](#installation-step-by-step)
  - [Option A: Install with pip (recommended)](#option-a-install-with-pip-recommended)
  - [Option B: Install in PyCharm](#option-b-install-in-pycharm)
  - [Option C: Install with Docker (no Python needed)](#option-c-install-with-docker-no-python-needed)
  - [Option D: Install from source (for developers)](#option-d-install-from-source-for-developers)
- [Configuration — Get Your API Key](#configuration--get-your-api-key)
  - [Step 1: Get a free API key](#step-1-get-a-free-api-key)
  - [Step 2: Set the API key](#step-2-set-the-api-key)
  - [Setting the API key in PyCharm](#setting-the-api-key-in-pycharm)
  - [Step 3: Verify it works](#step-3-verify-it-works)
- [Quick Start — Your First Screening](#quick-start--your-first-screening)
- [User Guide: Web UI](#user-guide-web-ui)
- [User Guide: Command Line](#user-guide-command-line)
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

## Prerequisites — What You Need Before Starting

Before installing MetaScreener, make sure you have:

### 1. Python 3.11 or higher

**Check if you already have Python:**

Open a terminal (see below) and type:

```bash
python --version
```

If you see `Python 3.11.x` or higher (3.12, 3.13, etc.), you're good. Skip to [Installation](#installation-step-by-step).

If you see an older version, or `command not found`, you need to install Python.

**How to install Python:**

1. Go to https://www.python.org/downloads/
2. Download Python 3.12 (or the latest 3.x version)
3. Run the installer
   - **IMPORTANT (Windows):** Check the box that says **"Add Python to PATH"** at the bottom of the installer. If you miss this, MetaScreener commands won't work.
   - **macOS:** The installer handles PATH automatically.
4. After installation, close and reopen your terminal, then verify: `python --version`

> **Windows users:** If `python --version` still doesn't work after installing, try `python3 --version` or `py --version`. Windows sometimes uses different command names.

### 2. A terminal (command line)

- **macOS:** Open **Terminal** (press `Cmd + Space`, type "Terminal", press Enter)
- **Windows:** Open **PowerShell** (press `Win + X`, select "Windows PowerShell") or **Command Prompt** (press `Win + R`, type `cmd`, press Enter)
- **Linux:** Open your distribution's terminal emulator (usually `Ctrl + Alt + T`)
- **PyCharm:** Click **Terminal** tab at the bottom of the PyCharm window (see [PyCharm section](#option-b-install-in-pycharm) for details)

### 3. An internet connection

MetaScreener calls cloud AI services to run its language models. You need internet access during screening, extraction, and quality assessment.

### 4. An API key (free)

MetaScreener uses open-source AI models hosted by cloud providers. You need a free API key from OpenRouter or Together AI. We'll set this up in the [Configuration](#configuration--get-your-api-key) section.

---

## Installation (Step by Step)

### Option A: Install with pip (recommended)

This is the simplest method. Open a terminal and run:

```bash
pip install metascreener
```

**If this fails**, try one of these alternatives:

```bash
# Some systems use pip3 instead of pip
pip3 install metascreener

# If you get a "permission denied" error
pip install --user metascreener

# If you use Python 3 explicitly
python3 -m pip install metascreener
```

**Verify the installation:**

```bash
metascreener --help
```

You should see output like:

```
Usage: metascreener [OPTIONS] COMMAND [ARGS]...

  MetaScreener — AI-assisted systematic review tool.

Commands:
  assess-rob  Assess risk of bias for included studies.
  evaluate    Evaluate screening performance against gold-standard labels.
  export      Export results in various formats.
  extract     Extract structured data from PDFs.
  init        Generate structured review criteria using AI.
  screen      Screen literature against review criteria using HCN.
  serve       Launch the MetaScreener Web UI.
  ui          Launch the Streamlit evaluation dashboard.
```

If you see this, MetaScreener is installed correctly. Skip to [Configuration](#configuration--get-your-api-key).

**If you see "command not found":**

```bash
# Try running as a Python module
python -m metascreener --help

# Or python3
python3 -m metascreener --help
```

If `python -m metascreener --help` works but `metascreener --help` doesn't, it means Python's scripts directory is not in your system PATH. See [Troubleshooting](#command-not-found-metascreener) for how to fix this.

---

### Option B: Install in PyCharm

If you use **PyCharm** (a popular Python IDE), follow these steps:

#### Step B1: Create a new project (or open your existing project)

1. Open PyCharm
2. Go to **File → New Project** (or open your existing project)
3. Choose a location (e.g., `~/my-review-project`)
4. Under **Python Interpreter**, select **Python 3.11** or higher
   - If you don't see Python 3.11+, click the gear icon and select **Add Interpreter → System Interpreter**, then browse to your Python installation
5. Click **Create**

#### Step B2: Install MetaScreener in PyCharm

**Method 1: Using PyCharm's built-in package manager**

1. Go to **PyCharm → Settings** (Mac: `Cmd + ,`) or **File → Settings** (Windows/Linux: `Ctrl + Alt + S`)
2. Navigate to **Project → Python Interpreter**
3. Click the **+** button (top-left of the packages list)
4. Search for **metascreener**
5. Click **Install Package**
6. Wait for installation to complete
7. Close the Settings dialog

**Method 2: Using PyCharm's terminal**

1. Click the **Terminal** tab at the bottom of the PyCharm window
2. Type:
   ```bash
   pip install metascreener
   ```
3. Press Enter and wait for installation to complete

#### Step B3: Verify installation in PyCharm

In PyCharm's Terminal tab, type:

```bash
metascreener --help
```

or:

```bash
python -m metascreener --help
```

You should see the command list. If not, make sure PyCharm is using the correct Python interpreter (the one where you installed MetaScreener).

#### Step B4: Set the API key in PyCharm

See [Setting the API key in PyCharm](#setting-the-api-key-in-pycharm) below.

#### Step B5: Run MetaScreener in PyCharm

**Option 1: Use the Terminal tab**

Click the Terminal tab at the bottom of PyCharm and type commands directly:

```bash
metascreener serve                 # Launch Web UI
metascreener screen --help         # See screening options
```

**Option 2: Create a Run Configuration**

1. Go to **Run → Edit Configurations**
2. Click **+** → **Python**
3. Set:
   - **Name:** MetaScreener Web UI
   - **Module name:** `metascreener.cli` (select "Module name" instead of "Script path")
   - **Parameters:** `serve`
   - **Environment variables:** `OPENROUTER_API_KEY=sk-or-v1-your-key-here`
   - **Working directory:** your project folder
4. Click **OK**
5. Click the green **Run** button (or press `Shift + F10`)

This launches the Web UI. Open http://localhost:8000 in your browser.

---

### Option C: Install with Docker (no Python needed)

Docker packages everything (Python, MetaScreener, all dependencies) into a single container. You don't need to install Python.

**Step C1: Install Docker**

Download Docker Desktop from https://www.docker.com/products/docker-desktop/ and install it.

**Step C2: Pull and run MetaScreener**

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

> **What is Docker?** Docker is a tool that packages software with all its dependencies into a single container. Think of it like a virtual computer that has everything pre-installed. You don't need to worry about Python versions or dependencies.

---

### Option D: Install from source (for developers)

This method is for developers who want to modify the code. Requires [uv](https://docs.astral.sh/uv/) and [Node.js 18+](https://nodejs.org/).

```bash
git clone https://github.com/ChaokunHong/MetaScreener.git
cd MetaScreener

# Install Python dependencies
uv sync --extra dev

# Run MetaScreener
uv run metascreener --help

# Run tests
uv run pytest
```

To also build the React Web UI from source:

```bash
make build          # Builds frontend + Python wheel
make dev-backend    # Start API server (terminal 1)
make dev-frontend   # Start frontend dev server (terminal 2)
```

---

## Configuration — Get Your API Key

MetaScreener uses open-source AI models via cloud API providers. The models themselves are free and open-source, but the cloud providers charge a small fee for running them (typically **$0.002–0.005 per paper**).

### Step 1: Get a free API key

| Provider | Free Tier | Sign-Up Link |
|----------|-----------|-------------|
| **OpenRouter** (recommended) | Yes | [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) |
| **Together AI** | Yes ($5 free credit) | [api.together.ai/settings/api-keys](https://api.together.ai/settings/api-keys) |

**How to get an OpenRouter API key:**

1. Go to https://openrouter.ai/ and click **Sign Up** (you can sign in with Google)
2. After signing in, go to https://openrouter.ai/settings/keys
3. Click **Create Key**
4. Give it a name (e.g., "MetaScreener")
5. Copy the key — it starts with `sk-or-v1-`
6. **Save this key somewhere safe** (you'll need it in the next step)

### Step 2: Set the API key

You need to tell MetaScreener your API key. There are **3 ways** to do this:

#### Way 1: Set via the Web UI (easiest)

1. Run `metascreener serve` in your terminal
2. Open http://localhost:8000 in your browser
3. Go to **Settings** (click the gear icon in the sidebar)
4. Paste your API key in the "OpenRouter API Key" field
5. Click **Save**

This saves the key to `~/.metascreener/config.yaml` and persists across sessions.

#### Way 2: Set as an environment variable (for terminal users)

**macOS / Linux:**

```bash
export OPENROUTER_API_KEY="sk-or-v1-paste-your-key-here"
```

To make this permanent (so you don't have to type it every time you open a terminal):

```bash
# For zsh (default on macOS)
echo 'export OPENROUTER_API_KEY="sk-or-v1-paste-your-key-here"' >> ~/.zshrc
source ~/.zshrc

# For bash (default on most Linux)
echo 'export OPENROUTER_API_KEY="sk-or-v1-paste-your-key-here"' >> ~/.bashrc
source ~/.bashrc
```

**Windows PowerShell:**

```powershell
$env:OPENROUTER_API_KEY = "sk-or-v1-paste-your-key-here"
```

To make it permanent on Windows:
1. Press `Win + S` and search for "Environment Variables"
2. Click "Edit the system environment variables"
3. Click "Environment Variables..." at the bottom
4. Under "User variables", click "New..."
5. Variable name: `OPENROUTER_API_KEY`
6. Variable value: `sk-or-v1-paste-your-key-here`
7. Click OK on all dialogs
8. **Restart your terminal** (or PyCharm) for the change to take effect

#### Way 3: Set in your Python code (for scripting)

```python
import os
os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-paste-your-key-here"
```

### Setting the API key in PyCharm

If you're using PyCharm, there are two ways:

**Way A: Set in PyCharm's terminal**

1. Click the **Terminal** tab at the bottom of PyCharm
2. Type (macOS/Linux):
   ```bash
   export OPENROUTER_API_KEY="sk-or-v1-paste-your-key-here"
   ```
   Or (Windows):
   ```powershell
   $env:OPENROUTER_API_KEY = "sk-or-v1-paste-your-key-here"
   ```
3. Now run MetaScreener commands in the same terminal window

> **Note:** This only lasts for the current terminal session. If you close and reopen the terminal, you'll need to set it again.

**Way B: Set in Run Configuration (permanent for PyCharm)**

1. Go to **Run → Edit Configurations**
2. Select your MetaScreener configuration (or create one)
3. Find the **Environment variables** field
4. Click the **...** button next to it
5. Click **+** to add a new variable:
   - Name: `OPENROUTER_API_KEY`
   - Value: `sk-or-v1-paste-your-key-here`
6. Click OK
7. Now every time you run this configuration, the key will be set automatically

**Way C: Set in PyCharm globally**

1. Go to **PyCharm → Settings** (Mac) or **File → Settings** (Windows/Linux)
2. Navigate to **Build, Execution, Deployment → Console → Python Console**
3. Add to **Environment variables**: `OPENROUTER_API_KEY=sk-or-v1-paste-your-key-here`

### Step 3: Verify it works

```bash
metascreener screen --input your_file.ris --dry-run
```

If the key is set correctly, you'll see a validation summary. The `--dry-run` flag means **no API calls are made and no money is spent**.

If you don't have a file yet, just check that the command runs:

```bash
metascreener --help
```

---

## Quick Start — Your First Screening

Now that MetaScreener is installed and configured, let's do your first screening.

### Using the Web UI (recommended for beginners)

**Step 1:** Start MetaScreener:

```bash
metascreener serve
```

You should see output like:

```
INFO     Started server process [12345]
INFO     Uvicorn running on http://0.0.0.0:8000
```

**Step 2:** Open your browser and go to http://localhost:8000

You'll see the MetaScreener dashboard with links to each step.

**Step 3:** Go to **Settings** (sidebar) and paste your API key if you haven't already.

**Step 4:** Go to **Screening** (sidebar):
1. Upload your search results file (.ris, .csv, .bib, .xlsx)
2. Set your criteria: type your research topic and let AI generate them, or upload an existing `criteria.yaml`
3. Click **Run Screening**
4. Watch results appear in real time
5. Export results as CSV, JSON, or Excel

### Using the command line

```bash
# Step 1: Generate criteria from your research topic
metascreener init --topic "antimicrobial resistance in ICU patients"

# Step 2: Screen papers (title/abstract)
metascreener screen --input search_results.ris --criteria criteria.yaml

# Step 3: Export results
metascreener export --results results/screening_results.json --format csv
```

### Using the interactive mode

```bash
metascreener
```

This launches a guided interface. Type `/init` to start, and follow the prompts step by step.

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

If you are new to the command line, the easiest way to start is the **interactive mode**:

```bash
metascreener
```

This launches a guided terminal interface:

```
┌──────────────────────────────────────────────────┐
│  MetaScreener 2.0                                │
│  AI-assisted systematic review tool              │
│                                                  │
│  Type /help for commands, /quit to exit.         │
└──────────────────────────────────────────────────┘

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

---

### Step 3: Extract Data (`metascreener extract`)

After screening, extract structured data from the included PDFs.

**Step 3a: Create an extraction form**

```bash
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

**All options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--pdfs PATH` | | Directory containing PDF files |
| `--form PATH` | `-f` | Path to `extraction_form.yaml` |
| `--output PATH` | `-o` | Output directory (default: `results/`) |
| `--dry-run` | | Validate inputs without running extraction |

---

### Step 4: Assess Risk of Bias (`metascreener assess-rob`)

```bash
# RoB 2 — for randomized controlled trials (5 domains, 22 signaling questions)
metascreener assess-rob --pdfs papers/ --tool rob2

# ROBINS-I — for observational studies (7 domains, 24 signaling questions)
metascreener assess-rob --pdfs papers/ --tool robins-i

# QUADAS-2 — for diagnostic accuracy studies (4 domains, 11 signaling questions)
metascreener assess-rob --pdfs papers/ --tool quadas2
```

**All options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--pdfs PATH` | | **(Required)** Directory containing PDF files |
| `--tool TEXT` | `-t` | Assessment tool: `rob2` (default), `robins-i`, `quadas2` |
| `--output PATH` | `-o` | Output directory (default: `results/`) |
| `--seed INTEGER` | `-s` | Random seed (default: `42`) |
| `--dry-run` | | Validate inputs without running |

---

### Step 5: Evaluate Performance (`metascreener evaluate`)

If you have gold-standard labels (e.g., from human reviewers), evaluate MetaScreener's accuracy:

```bash
metascreener evaluate --labels gold_standard.csv --predictions results/screening_results.json --visualize
```

**Gold-standard CSV format:**

```csv
record_id,label
abc123,1
def456,0
ghi789,1
```

Where `1` = include, `0` = exclude.

**Metrics computed:**

| Metric | What it measures |
|--------|-----------------|
| Sensitivity (Recall) | Of all relevant papers, how many did MetaScreener find? (target ≥95%) |
| Specificity | Of all irrelevant papers, how many did MetaScreener correctly exclude? |
| F1 Score | Balance between precision and recall |
| WSS@95 | Work saved compared to screening everything, at 95% recall |
| AUROC | Overall discriminative ability (0.5 = random, 1.0 = perfect) |
| ECE | Calibration error — how well confidence scores match actual accuracy |
| Cohen's Kappa | Agreement between MetaScreener and human reviewers |

All metrics include bootstrap 95% confidence intervals (1000 iterations).

---

### Step 6: Export Results (`metascreener export`)

```bash
# Export as CSV
metascreener export --results results/screening_results.json --format csv

# Multiple formats at once
metascreener export --results results/screening_results.json --format csv,json,excel,ris
```

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

**Cause:** Python's `bin` / `Scripts` directory is not in your PATH.

**Fix (try in order):**

```bash
# 1. Try as a Python module
python -m metascreener --help

# 2. Try with python3
python3 -m metascreener --help

# 3. Find where pip installed it
pip show metascreener
# Look at the "Location:" line — it tells you where the package is

# 4. On macOS/Linux, add Python's bin to PATH
export PATH="$HOME/.local/bin:$PATH"

# 5. On Windows, find the Scripts folder and add to PATH
# Usually: C:\Users\YourName\AppData\Local\Programs\Python\Python311\Scripts
```

**PyCharm-specific fix:** Make sure PyCharm is using the right Python interpreter:
1. Go to **File → Settings → Project → Python Interpreter**
2. Check that MetaScreener is listed in the packages
3. If not, click **+** and install it

### "OPENROUTER_API_KEY not set"

**Cause:** The environment variable is not set in your current terminal session.

**Fix:**

```bash
# Check if it's set
echo $OPENROUTER_API_KEY    # macOS/Linux
echo $env:OPENROUTER_API_KEY  # Windows PowerShell

# If empty, set it
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"  # macOS/Linux
$env:OPENROUTER_API_KEY = "sk-or-v1-your-key-here"  # Windows PowerShell
```

Or use the Web UI: `metascreener serve` → Settings → paste your key.

**PyCharm-specific:** See [Setting the API key in PyCharm](#setting-the-api-key-in-pycharm) above.

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
```

**PyCharm-specific:** Make sure MetaScreener is installed in the same Python interpreter that PyCharm is using:
1. Go to **File → Settings → Project → Python Interpreter**
2. Check if `metascreener` appears in the package list
3. If not, click **+**, search for `metascreener`, and install it

### The Web UI shows a blank page

**Cause:** The frontend assets may not be included in your installation.

**Fix:**

```bash
# Reinstall
pip install --force-reinstall metascreener

# If running from source, build the frontend first:
cd frontend && npm ci && npm run build
```

### Screening is slow

**Cause:** Each paper requires 4 API calls (one per model). For 1000 papers, that's 4000 API calls.

**Tips:**
- Use `--dry-run` first to validate your input
- Typical speed: 1-3 seconds per paper
- For large datasets (>5000 papers), consider running overnight

### PyCharm can't find the metascreener command

**Cause:** PyCharm may be using a different Python environment than your system.

**Fix:**
1. Open PyCharm's Terminal tab
2. Check which Python is active: `python --version` and `which python` (macOS/Linux) or `where python` (Windows)
3. Install metascreener in that specific environment: `pip install metascreener`
4. Verify: `python -m metascreener --help`

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

### I installed MetaScreener but nothing happens when I type the command

This usually means one of three things:
1. **Wrong Python version:** MetaScreener requires Python 3.11+. Check: `python --version`
2. **PATH issue:** Python's scripts directory isn't in your PATH. Try: `python -m metascreener --help`
3. **Wrong environment:** If using PyCharm or conda, make sure you installed MetaScreener in the active environment. See [PyCharm section](#option-b-install-in-pycharm).

### How do I update MetaScreener?

```bash
pip install --upgrade metascreener
```

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
