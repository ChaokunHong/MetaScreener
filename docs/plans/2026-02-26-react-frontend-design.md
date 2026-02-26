# MetaScreener 2.0 — React Frontend & FastAPI Design

> **Date**: 2026-02-26
> **Status**: Approved
> **Scope**: FastAPI API layer + React frontend + Docker packaging

---

## 1. Problem Statement

MetaScreener 2.0 currently only has a CLI (Typer) and Streamlit UI. User feedback:

- CLI is hard to use for interactive SR workflows (file upload, criteria editing, results review)
- Streamlit interaction is too limited (no real-time updates, poor form handling, page state loss)
- `pip install metascreener` doesn't work in fresh environments (entry point issues)
- No solution for users without Python

## 2. Architecture

### 2.1 Overall Structure

```
metascreener (PyPI package)
├── src/metascreener/
│   ├── core/                  # Existing: data models, enums
│   ├── module1_screening/     # Existing: HCN screening engine
│   ├── module2_extraction/    # Existing: data extraction engine
│   ├── module3_quality/       # Existing: RoB assessment engine
│   ├── criteria/              # Existing: PICO criteria wizard
│   ├── evaluation/            # Existing: metrics, calibration
│   ├── llm/                   # Existing: LLM adapters
│   ├── io/                    # Existing: readers/writers
│   ├── cli/                   # Existing: Typer CLI
│   ├── api/                   # NEW: FastAPI service layer
│   │   ├── main.py            #   FastAPI app + static file serving
│   │   ├── routes/
│   │   │   ├── screening.py   #   Upload, criteria, run, results
│   │   │   ├── evaluation.py  #   Metrics, visualization data
│   │   │   ├── extraction.py  #   Form, PDF upload, extract
│   │   │   ├── quality.py     #   RoB assessment
│   │   │   └── settings.py    #   Configuration CRUD
│   │   ├── schemas.py         #   API request/response Pydantic models
│   │   ├── deps.py            #   Dependency injection
│   │   └── ws.py              #   WebSocket handlers
│   └── web/                   # Frontend build artifacts (in wheel)
│       └── dist/              #   React production build output
│
├── frontend/                  # React source (NOT in PyPI package)
│   ├── src/
│   │   ├── components/        #   Glass Design System components
│   │   │   ├── ui/            #     shadcn/ui with glass overrides
│   │   │   ├── glass/         #     GlassCard, GlassModal, GlassButton
│   │   │   └── layout/        #     Sidebar, Header, PageContainer
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Screening.tsx  #     Stepper: Upload→Criteria→Run→Results
│   │   │   ├── Evaluation.tsx
│   │   │   ├── Extraction.tsx
│   │   │   ├── Quality.tsx
│   │   │   └── Settings.tsx
│   │   ├── stores/            #   Zustand state management
│   │   ├── api/               #   API client (fetch + TanStack Query)
│   │   ├── hooks/             #   Custom React hooks
│   │   └── styles/
│   │       ├── aurora.css     #   Aurora gradient background (from v1.0)
│   │       └── glass.css      #   Glass morphism variables (from v1.0)
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── tailwind.config.ts
│
└── docker/
    └── Dockerfile             # Multi-stage: node build → python runtime
```

### 2.2 Data Flow

```
User (Browser)
    │
    ▼ HTTP / WebSocket
┌──────────────┐
│  FastAPI      │─── serves React static files (web/dist/)
│  localhost:   │─── REST API endpoints (/api/*)
│  8000         │─── WebSocket (/api/screening/progress)
└──────┬───────┘
       │ Python function calls
       ▼
┌──────────────┐
│  Core Engine  │─── TAScreener, ExtractionEngine, RoBAssessor
│  (existing)   │─── CriteriaWizard, EvaluationRunner
└──────┬───────┘
       │ HTTP (async)
       ▼
┌──────────────┐
│  LLM APIs    │─── OpenRouter / Together AI / local vLLM
└──────────────┘
```

### 2.3 Frontend Build Packaging

The React build artifacts must be included in the PyPI wheel so that
`pip install metascreener` gives users a working Web UI without Node.js.

**pyproject.toml configuration:**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/metascreener"]

[tool.hatch.build.targets.wheel.force-include]
"src/metascreener/web/dist" = "metascreener/web/dist"
```

**CI/CD pipeline (GitHub Actions):**

1. `cd frontend && npm ci && npm run build`
2. Output to `src/metascreener/web/dist/`
3. `hatch build` → wheel includes dist/
4. `twine upload` → PyPI

**Local development:**

```bash
cd frontend && npm run dev      # Vite dev server on :5173
metascreener serve --api-only   # FastAPI on :8000
# Vite proxies /api/* to :8000
```

## 3. Pages

### 3.1 Dashboard (`/`)

- Project overview with workflow status cards
- Quick-start buttons for each module
- Recent activity log
- System status (API key configured, models available)

### 3.2 Screening (`/screening`)

Linear 4-step stepper workflow:

**Step 1 — Upload Files**
- Drag-drop zone for RIS/BibTeX/CSV/Excel/JSON
- File parsing preview: record count, with/without abstract stats
- Support multiple file upload and merge

**Step 2 — Set Criteria** (embedded wizard)
- Option A: Upload existing criteria.yaml
- Option B: Enter topic → AI generates PICO criteria
- Option C: Select from built-in templates
- Inline editing of include/exclude terms
- Framework auto-detection (PICO/PEO/SPIDER/PCC)

**Step 3 — Run Screening**
- Model selection (which of the 4 LLMs to use)
- WebSocket real-time progress: per-record status, running metrics
- Live updating pie chart of Include/Exclude/Human Review
- Pause/resume capability

**Step 4 — Results**
- Filterable/sortable decision table
- Decision distribution visualization
- Tier breakdown (Tier 0-3)
- Per-record detail: model votes, confidence, rule overrides
- Export: RIS, CSV, Excel, JSON

### 3.3 Evaluation (`/evaluation`)

- Upload gold-standard labels (RIS/CSV with include/exclude annotations)
- Compute metrics: sensitivity, specificity, F1, WSS@95, AUROC, ECE, Brier, κ
- Interactive Plotly charts: ROC curve, calibration plot, score distribution
- Bootstrap 95% CI display
- Lancet-formatted metrics text (middle dot, en dash)
- Paper-quality figure export (PNG 300 DPI, SVG)

### 3.4 Extraction (`/extraction`)

- Upload or create extraction form (YAML)
- Upload PDFs of included papers
- Run multi-LLM extraction with progress
- Editable results table with consensus indicators
- Field-level agreement display
- Export: CSV, JSON, Excel

### 3.5 Quality (`/quality`)

- Select assessment tool: RoB 2, ROBINS-I, QUADAS-2
- Upload PDFs
- Run assessment with progress
- Traffic-light summary table
- Domain drill-down with rationale and supporting quotes
- Per-model judgement comparison
- Export: JSON, Excel (Summary + Details sheets)

### 3.6 Settings (`/settings`)

- **API Keys**: OpenRouter, Together AI key input with test/validate button
- **Model Selection**: Enable/disable individual models, set weights
- **Inference Parameters**: Temperature (locked to 0.0), seed, timeout, max retries
- **Provider Selection**: OpenRouter / Together AI / Local vLLM / Ollama
- **Advanced**: Calibration parameters, threshold tuning
- Config persisted to `~/.metascreener/config.yaml`

## 4. Visual Design: Glass Design System

Migrated from MetaScreener v1.0's Glass Design System.

### 4.1 Core Visual Properties

```css
:root {
  /* Aurora Dream Colors */
  --aurora-green: rgba(0, 255, 146, 0.18);
  --aurora-blue: rgba(79, 172, 254, 0.15);
  --aurora-purple: rgba(147, 51, 234, 0.15);
  --aurora-pink: rgba(236, 72, 153, 0.12);
  --aurora-cyan: rgba(34, 211, 238, 0.12);

  /* Glass Material */
  --glass-blur: 20px;
  --glass-bg: rgba(255, 255, 255, 0.18);
  --glass-bg-strong: rgba(255, 255, 255, 0.25);
  --glass-bg-subtle: rgba(255, 255, 255, 0.10);
  --glass-border: rgba(255, 255, 255, 0.4);
  --glass-border-light: rgba(255, 255, 255, 0.6);

  /* Purple Theme */
  --primary-purple: #8b5cf6;
  --primary-purple-hover: #7c3aed;
}
```

### 4.2 Key Effects

- **Aurora background**: 6 animated color orbs, 40s cycle, `filter: blur(40px)`
- **Glass containers**: `backdrop-filter: blur(20px) saturate(140%) brightness(1.08)`
- **Layered borders**: top border lighter for bevel effect
- **Primary buttons**: purple gradient glass with light-flow animation
- **Modals**: scale+translateY entrance, blurred overlay
- **Three-tier depth**: Strong → Normal → Subtle backgrounds

### 4.3 Implementation

- Tailwind CSS with custom theme extending glass variables
- shadcn/ui components restyled with glass overrides
- Dedicated `components/glass/` for GlassCard, GlassButton, GlassModal
- Aurora CSS as global background layer

## 5. API Design

### 5.1 REST Endpoints

```
# Screening
POST   /api/screening/upload          # Upload literature files
POST   /api/screening/criteria        # Generate/validate criteria
POST   /api/screening/run             # Start HCN screening
GET    /api/screening/results/{id}    # Get screening results
GET    /api/screening/export/{id}     # Export results (format query param)

# Evaluation
POST   /api/evaluation/upload-labels  # Upload gold standard
POST   /api/evaluation/run            # Compute metrics
GET    /api/evaluation/figures/{type} # Get chart data (roc, calibration, etc.)

# Extraction
POST   /api/extraction/upload-form    # Upload extraction form YAML
POST   /api/extraction/upload-pdfs    # Upload PDFs
POST   /api/extraction/run            # Run extraction
GET    /api/extraction/results/{id}   # Get extraction results

# Quality
POST   /api/quality/upload-pdfs       # Upload PDFs for RoB
POST   /api/quality/run               # Run assessment
GET    /api/quality/results/{id}      # Get assessment results

# Settings
GET    /api/settings                  # Get current configuration
PUT    /api/settings                  # Update configuration
POST   /api/settings/test-key         # Validate API key
GET    /api/settings/models           # List available models
```

### 5.2 WebSocket

```
WS /api/screening/progress
   → { type: "record_update", record_id, decision, confidence, progress }
   → { type: "screening_complete", summary }
   → { type: "error", message }
```

### 5.3 Response Format

```json
{
  "status": "success",
  "data": { ... },
  "meta": { "timestamp": "...", "version": "2.0.0" }
}
```

## 6. Distribution Matrix

| Method | Target User | Priority | Timeline |
|--------|-------------|----------|----------|
| `pip install metascreener` | Python researchers | P0 | Now |
| `metascreener serve` → React UI | Daily usage | P0 | Now |
| `docker run metascreener` | Reproducibility / no Python | P0 | With paper |
| MetaScreener.dmg / .exe (Electron) | Zero-tech-barrier users | P1 | Post-paper |

## 7. Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend | React + TypeScript | 19.x |
| UI Components | shadcn/ui + Tailwind CSS | Latest |
| State Management | Zustand | 5.x |
| Data Fetching | TanStack Query | 5.x |
| Charts | Recharts or Nivo | Latest |
| Build Tool | Vite | 6.x |
| Backend API | FastAPI + uvicorn | 0.115+ |
| Real-time | WebSocket (native) | — |
| Desktop (P1) | Electron | 33.x |
| Container | Docker (multi-stage) | — |

## 8. What Stays Unchanged

- All existing Python modules (core, module1-3, criteria, evaluation, llm, io)
- CLI commands (metascreener screen, extract, assess-rob, evaluate, export)
- Streamlit app (kept as optional, may deprecate later)
- Test suite (669 tests)
- CLAUDE.md project guidelines
