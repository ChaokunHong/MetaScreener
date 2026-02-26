# React Frontend + FastAPI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a professional React Web UI with FastAPI backend to MetaScreener, using the Glass Design System from v1.0.

**Architecture:** FastAPI wraps existing Python engines (TAScreener, ExtractionEngine, RoBAssessor, CriteriaWizard, EvaluationRunner) as REST + WebSocket endpoints. React frontend (shadcn/ui + Tailwind + Glass morphism) communicates via HTTP/WS. Frontend build artifacts ship inside the PyPI wheel. `metascreener serve` starts both.

**Tech Stack:** Python 3.11+ / FastAPI / uvicorn / React 19 / TypeScript / Vite / shadcn/ui / Tailwind CSS / Zustand / TanStack Query / Recharts

**Design doc:** `docs/plans/2026-02-26-react-frontend-design.md`

---

## Phase 1: FastAPI Backend (Tasks 1–6)

### Task 1: FastAPI App Skeleton + `metascreener serve`

**Files:**
- Create: `src/metascreener/api/__init__.py`
- Create: `src/metascreener/api/main.py`
- Create: `src/metascreener/api/deps.py`
- Modify: `src/metascreener/cli/__init__.py` (add `serve` command)
- Modify: `pyproject.toml` (add `fastapi`, `uvicorn` deps)
- Test: `tests/unit/test_api_main.py`

**Step 1: Add dependencies to pyproject.toml**

Add to `dependencies` list:
```toml
"fastapi>=0.115",
"uvicorn[standard]>=0.32",
```

Add to `[tool.mypy]` overrides:
```toml
[[tool.mypy.overrides]]
module = ["uvicorn", "uvicorn.*"]
ignore_missing_imports = true
```

**Step 2: Write the failing test**

```python
# tests/unit/test_api_main.py
"""Tests for the FastAPI application setup."""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


class TestFastAPIApp:
    """Test FastAPI app creation and configuration."""

    def test_app_creates_successfully(self) -> None:
        from metascreener.api.main import create_app

        app = create_app()
        assert app is not None
        assert app.title == "MetaScreener"

    def test_health_endpoint(self) -> None:
        from metascreener.api.main import create_app

        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_static_file_serving_returns_index_for_spa(self) -> None:
        """When web/dist/index.html exists, GET / serves it."""
        from metascreener.api.main import create_app

        app = create_app()
        client = TestClient(app)
        # Without dist, non-API routes return 404
        resp = client.get("/nonexistent")
        assert resp.status_code == 404

    def test_cors_headers_present(self) -> None:
        from metascreener.api.main import create_app

        app = create_app()
        client = TestClient(app)
        resp = client.options(
            "/api/health",
            headers={"Origin": "http://localhost:5173"},
        )
        # CORS should allow localhost origins in dev
        assert resp.status_code in (200, 405)


class TestServeCommand:
    """Test the 'metascreener serve' CLI command."""

    def test_serve_command_exists(self) -> None:
        from typer.testing import CliRunner
        from metascreener.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "serve" in result.output.lower() or "FastAPI" in result.output
```

**Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'metascreener.api'`

**Step 4: Write minimal implementation**

```python
# src/metascreener/api/__init__.py
"""MetaScreener 2.0 FastAPI service layer."""
```

```python
# src/metascreener/api/deps.py
"""FastAPI dependency injection for shared resources."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from metascreener.config import MetaScreenerConfig, load_model_config
from metascreener.llm.adapters.openrouter import OpenRouterAdapter
from metascreener.llm.base import LLMBackend


def get_config_path() -> Path:
    """Resolve the model config YAML path."""
    # Check project root first, then package dir
    candidates = [
        Path.cwd() / "configs" / "models.yaml",
        Path(__file__).resolve().parents[2] / "configs" / "models.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    msg = "models.yaml not found"
    raise FileNotFoundError(msg)


@lru_cache(maxsize=1)
def get_config() -> MetaScreenerConfig:
    """Load and cache model configuration."""
    return load_model_config(get_config_path())


def create_backends() -> list[LLMBackend]:
    """Create LLM backends from config and environment."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    config = get_config()
    backends: list[LLMBackend] = []
    for name, entry in config.models.items():
        if entry.provider == "openrouter":
            backends.append(
                OpenRouterAdapter(
                    model_id=name,
                    openrouter_model_name=entry.model_id,
                    api_key=api_key,
                    model_version=entry.version,
                    timeout_s=config.inference.timeout_s,
                    max_retries=config.inference.max_retries,
                )
            )
    return backends
```

```python
# src/metascreener/api/main.py
"""FastAPI application for MetaScreener 2.0 Web UI."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import metascreener


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="MetaScreener",
        version=metascreener.__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # CORS for local dev (Vite on :5173)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check
    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": metascreener.__version__}

    # Serve React static files if dist/ exists
    dist_dir = Path(__file__).parent.parent / "web" / "dist"
    if dist_dir.is_dir():
        # Serve static assets (js, css, images)
        assets_dir = dist_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        # SPA fallback: serve index.html for all non-API routes
        @app.get("/{path:path}")
        async def spa_fallback(path: str) -> FileResponse | JSONResponse:
            # If path matches a real file in dist, serve it
            file_path = dist_dir / path
            if file_path.is_file():
                return FileResponse(str(file_path))
            # Otherwise serve index.html for SPA routing
            index = dist_dir / "index.html"
            if index.is_file():
                return FileResponse(str(index))
            return JSONResponse({"error": "not found"}, status_code=404)

    return app
```

Add `serve` command to CLI:

```python
# In src/metascreener/cli/__init__.py, add after the ui() command:

@app.command()
def serve(
    port: int = typer.Option(8000, help="Port to listen on."),  # noqa: B008
    host: str = typer.Option("127.0.0.1", help="Host to bind to."),  # noqa: B008
    api_only: bool = typer.Option(  # noqa: B008
        False, "--api-only", help="Only start API server, skip frontend."
    ),
) -> None:
    """Launch the FastAPI web server with React UI."""
    import uvicorn  # noqa: PLC0415

    typer.echo(f"Starting MetaScreener server on http://{host}:{port}")
    if not api_only:
        typer.echo("Open your browser to start using the Web UI.")

    uvicorn.run(
        "metascreener.api.main:create_app",
        host=host,
        port=port,
        factory=True,
    )
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_api_main.py -v`
Expected: PASS

**Step 6: Run full test suite**

Run: `uv run pytest --tb=short -q && uv run ruff check src/ tests/`
Expected: All 669+ tests pass, 0 lint errors

**Step 7: Commit**

```bash
git add src/metascreener/api/ tests/unit/test_api_main.py pyproject.toml src/metascreener/cli/__init__.py
git commit -m "feat: add FastAPI skeleton with serve command and health endpoint"
```

---

### Task 2: Settings API + Config Persistence

**Files:**
- Create: `src/metascreener/api/routes/__init__.py`
- Create: `src/metascreener/api/routes/settings.py`
- Create: `src/metascreener/api/schemas.py`
- Modify: `src/metascreener/api/main.py` (register router)
- Test: `tests/unit/test_api_settings.py`

**Purpose:** Settings page needs: GET/PUT config, test API key, list models. Config persists to `~/.metascreener/config.yaml`.

**Step 1: Write the failing test**

```python
# tests/unit/test_api_settings.py
"""Tests for the settings API routes."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


class TestSettingsAPI:
    """Test settings CRUD endpoints."""

    def _client(self) -> TestClient:
        from metascreener.api.main import create_app
        return TestClient(create_app())

    def test_get_settings_returns_defaults(self) -> None:
        client = self._client()
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "api_keys" in data
        assert "inference" in data
        assert data["inference"]["temperature"] == 0.0
        assert data["inference"]["seed"] == 42

    def test_put_settings_updates_api_key(self, tmp_path: Path) -> None:
        with patch(
            "metascreener.api.routes.settings._config_path",
            return_value=tmp_path / "config.yaml",
        ):
            client = self._client()
            resp = client.put(
                "/api/settings",
                json={"api_keys": {"openrouter": "sk-test-123"}},
            )
            assert resp.status_code == 200
            # Verify persisted
            assert (tmp_path / "config.yaml").exists()

    def test_get_models_returns_model_list(self) -> None:
        client = self._client()
        resp = client.get("/api/settings/models")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Should have at least the 4 default models
        assert len(data) >= 1

    def test_test_key_without_key_returns_error(self) -> None:
        client = self._client()
        resp = client.post(
            "/api/settings/test-key",
            json={"provider": "openrouter", "api_key": ""},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api_settings.py -v`
Expected: FAIL

**Step 3: Implement schemas and settings route**

```python
# src/metascreener/api/schemas.py
"""Pydantic schemas for API request/response models."""
from __future__ import annotations

from pydantic import BaseModel, Field


class APIKeysConfig(BaseModel):
    openrouter: str = ""
    together: str = ""

class InferenceSettings(BaseModel):
    temperature: float = 0.0
    seed: int = 42
    timeout_s: float = 120.0
    max_retries: int = 3

class SettingsResponse(BaseModel):
    api_keys: APIKeysConfig = Field(default_factory=APIKeysConfig)
    inference: InferenceSettings = Field(default_factory=InferenceSettings)
    enabled_models: list[str] = Field(default_factory=list)

class SettingsUpdate(BaseModel):
    api_keys: APIKeysConfig | None = None
    inference: InferenceSettings | None = None
    enabled_models: list[str] | None = None

class ModelInfo(BaseModel):
    model_id: str
    name: str
    provider: str
    version: str
    license: str
    enabled: bool = True

class TestKeyRequest(BaseModel):
    provider: str
    api_key: str

class TestKeyResponse(BaseModel):
    valid: bool
    message: str
```

```python
# src/metascreener/api/routes/__init__.py
"""FastAPI route modules."""

# src/metascreener/api/routes/settings.py
"""Settings management API routes."""
from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter

from metascreener.api.deps import get_config
from metascreener.api.schemas import (
    ModelInfo,
    SettingsResponse,
    SettingsUpdate,
    TestKeyRequest,
    TestKeyResponse,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

def _config_path() -> Path:
    p = Path.home() / ".metascreener" / "config.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def _load_user_settings() -> dict:
    p = _config_path()
    if p.exists():
        with open(p) as f:
            return yaml.safe_load(f) or {}
    return {}

def _save_user_settings(data: dict) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        yaml.dump(data, f, default_flow_style=False)

@router.get("", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    user = _load_user_settings()
    return SettingsResponse(**user)

@router.put("")
async def update_settings(update: SettingsUpdate) -> dict:
    current = _load_user_settings()
    if update.api_keys is not None:
        current["api_keys"] = update.api_keys.model_dump()
    if update.inference is not None:
        current["inference"] = update.inference.model_dump()
    if update.enabled_models is not None:
        current["enabled_models"] = update.enabled_models
    _save_user_settings(current)
    return {"status": "ok"}

@router.get("/models", response_model=list[ModelInfo])
async def list_models() -> list[ModelInfo]:
    try:
        config = get_config()
    except FileNotFoundError:
        return []
    return [
        ModelInfo(
            model_id=key,
            name=entry.name,
            provider=entry.provider,
            version=entry.version,
            license=entry.license_,
        )
        for key, entry in config.models.items()
    ]

@router.post("/test-key", response_model=TestKeyResponse)
async def test_api_key(req: TestKeyRequest) -> TestKeyResponse:
    if not req.api_key or not req.api_key.strip():
        return TestKeyResponse(valid=False, message="API key is empty")
    # Basic format validation; real validation would call the API
    if len(req.api_key) < 10:
        return TestKeyResponse(valid=False, message="Key too short")
    return TestKeyResponse(valid=True, message="Key format looks valid")
```

Register in `main.py` — add inside `create_app()`:
```python
from metascreener.api.routes.settings import router as settings_router
app.include_router(settings_router)
```

**Step 4: Run tests, lint, commit**

Run: `uv run pytest tests/unit/test_api_settings.py tests/unit/test_api_main.py -v`
Run: `uv run ruff check src/metascreener/api/`
Expected: PASS

```bash
git add src/metascreener/api/ tests/unit/test_api_settings.py
git commit -m "feat: add settings API with config persistence and model listing"
```

---

### Task 3: Screening API (Upload + Run + WebSocket Progress)

**Files:**
- Create: `src/metascreener/api/routes/screening.py`
- Create: `src/metascreener/api/ws.py`
- Modify: `src/metascreener/api/main.py` (register router)
- Modify: `src/metascreener/api/schemas.py` (add screening schemas)
- Test: `tests/unit/test_api_screening.py`

**Purpose:** Core screening workflow: upload file → parse records → upload/generate criteria → run HCN screening with WebSocket progress → get results → export.

**Key integration points:**
- `read_records(path)` for file parsing
- `TAScreener.screen_single()` + `screen_batch()` for screening
- WebSocket for real-time progress during screening
- In-memory session store (dict) keyed by session ID

**Step 1: Write tests (key tests only — full file includes 8+ tests)**

```python
# tests/unit/test_api_screening.py
"""Tests for screening API routes."""
from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestScreeningUpload:

    def _client(self) -> TestClient:
        from metascreener.api.main import create_app
        return TestClient(create_app())

    def test_upload_ris_parses_records(self) -> None:
        ris_content = b"""TY  - JOUR\nTI  - Test Study\nAB  - An abstract\nER  - \n"""
        client = self._client()
        resp = client.post(
            "/api/screening/upload",
            files={"file": ("test.ris", io.BytesIO(ris_content), "application/x-research-info-systems")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["record_count"] >= 1
        assert "session_id" in data

    def test_upload_unsupported_format_returns_400(self) -> None:
        client = self._client()
        resp = client.post(
            "/api/screening/upload",
            files={"file": ("test.xyz", io.BytesIO(b"data"), "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_get_results_without_session_returns_404(self) -> None:
        client = self._client()
        resp = client.get("/api/screening/results/nonexistent")
        assert resp.status_code == 404
```

**Step 2: Implement screening routes**

The screening route should:
1. `POST /api/screening/upload` — save file to temp, call `read_records()`, store in session dict, return session_id + record_count
2. `POST /api/screening/criteria` — accept YAML upload or JSON body, parse into `ReviewCriteria`
3. `POST /api/screening/run` — accept session_id, create TAScreener, screen batch, store results
4. `WS /api/screening/progress/{session_id}` — WebSocket that sends per-record updates during screening
5. `GET /api/screening/results/{session_id}` — return stored results
6. `GET /api/screening/export/{session_id}?format=csv` — export results

Use an in-memory dict `_sessions: dict[str, SessionData]` to store state between requests. This is fine for single-user local mode.

**Step 3: Run tests, lint, commit**

```bash
git add src/metascreener/api/routes/screening.py src/metascreener/api/ws.py \
        src/metascreener/api/schemas.py tests/unit/test_api_screening.py
git commit -m "feat: add screening API with file upload, HCN execution, and WebSocket progress"
```

---

### Task 4: Evaluation API

**Files:**
- Create: `src/metascreener/api/routes/evaluation.py`
- Modify: `src/metascreener/api/main.py` (register router)
- Test: `tests/unit/test_api_evaluation.py`

**Purpose:** Upload gold labels, compute metrics via `EvaluationRunner`, return chart data for Plotly/Recharts.

**Endpoints:**
- `POST /api/evaluation/upload-labels` — upload gold-standard file
- `POST /api/evaluation/run` — compute metrics from session screening results + gold labels
- `GET /api/evaluation/figures/{type}` — get chart data as JSON (roc, calibration, distribution)

**Step 1–4:** Same TDD pattern. Key test: upload labels, run eval, check metrics dict has `sensitivity`, `specificity`, `auroc` keys.

```bash
git commit -m "feat: add evaluation API with metrics computation and chart data"
```

---

### Task 5: Extraction + Quality API

**Files:**
- Create: `src/metascreener/api/routes/extraction.py`
- Create: `src/metascreener/api/routes/quality.py`
- Modify: `src/metascreener/api/main.py` (register routers)
- Test: `tests/unit/test_api_extraction.py`
- Test: `tests/unit/test_api_quality.py`

**Purpose:** Wrap `ExtractionEngine` and `RoBAssessor` as REST endpoints.

**Extraction endpoints:**
- `POST /api/extraction/upload-form` — upload YAML form
- `POST /api/extraction/upload-pdfs` — upload PDF files
- `POST /api/extraction/run` — run extraction
- `GET /api/extraction/results/{session_id}` — get results

**Quality endpoints:**
- `POST /api/quality/upload-pdfs` — upload PDFs
- `POST /api/quality/run` — run RoB assessment
- `GET /api/quality/results/{session_id}` — get results

```bash
git commit -m "feat: add extraction and quality assessment API routes"
```

---

### Task 6: API Integration Test

**Files:**
- Create: `tests/integration/test_api_full_workflow.py`

**Purpose:** End-to-end test: upload file → set criteria → mock-screen → get results. Uses mock LLM backends.

```bash
git commit -m "test: add API integration test for full screening workflow"
```

---

## Phase 2: React Frontend Setup (Tasks 7–10)

### Task 7: Initialize React Project + Glass Design System

**Files:**
- Create: `frontend/` directory with full Vite + React + TypeScript scaffold
- Create: `frontend/src/styles/aurora.css` (from v1.0)
- Create: `frontend/src/styles/glass.css` (from v1.0)
- Create: `frontend/tailwind.config.ts` (with glass theme extensions)
- Modify: `.gitignore` (allow `frontend/` but ignore `frontend/node_modules/`)

**Step 1: Scaffold React project**

```bash
cd /Users/hongchaokun/Documents/PhD/MetaScreener
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

**Step 2: Install dependencies**

```bash
npm install react-router-dom zustand @tanstack/react-query recharts lucide-react clsx tailwind-merge
npm install -D tailwindcss @tailwindcss/vite
npx shadcn@latest init
```

**Step 3: Configure Vite proxy**

In `frontend/vite.config.ts`:
```typescript
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: '../src/metascreener/web/dist',
    emptyOutDir: true,
  },
})
```

**Step 4: Set up Glass Design System CSS**

Port the core CSS variables and aurora background from v1.0 into `aurora.css` and `glass.css`. Extend Tailwind theme with glass colors and blur utilities.

**Step 5: Configure build output path + .gitignore**

Update `.gitignore`:
```
# v1.0 frontend (ignore)
metascreener1.0/

# v2.0 frontend source (track)
!frontend/
frontend/node_modules/
frontend/dist/

# Built web assets (generated, don't commit)
src/metascreener/web/dist/
```

**Step 6: Verify build**

```bash
cd frontend && npm run build
# Should output to ../src/metascreener/web/dist/
ls ../src/metascreener/web/dist/index.html
```

```bash
git add frontend/ .gitignore
git commit -m "feat: initialize React frontend with Vite, Tailwind, shadcn/ui, and Glass Design System"
```

---

### Task 8: Layout Components + Router

**Files:**
- Create: `frontend/src/components/layout/Sidebar.tsx`
- Create: `frontend/src/components/layout/Header.tsx`
- Create: `frontend/src/components/layout/PageContainer.tsx`
- Create: `frontend/src/components/glass/GlassCard.tsx`
- Create: `frontend/src/components/glass/GlassButton.tsx`
- Create: `frontend/src/App.tsx` (router setup)
- Create: `frontend/src/pages/` (placeholder pages)

**Purpose:** App shell with sidebar navigation (Dashboard, Screening, Evaluation, Extraction, Quality, Settings) + glass-morphism layout components.

**Router structure:**
```typescript
<Routes>
  <Route path="/" element={<Dashboard />} />
  <Route path="/screening" element={<Screening />} />
  <Route path="/evaluation" element={<Evaluation />} />
  <Route path="/extraction" element={<Extraction />} />
  <Route path="/quality" element={<Quality />} />
  <Route path="/settings" element={<Settings />} />
</Routes>
```

Each page initially renders a `<GlassCard>` with its title. Sidebar uses `lucide-react` icons. Aurora background is global.

```bash
git commit -m "feat: add layout components, router, and glass card/button primitives"
```

---

### Task 9: API Client + Zustand Stores

**Files:**
- Create: `frontend/src/api/client.ts` (fetch wrapper)
- Create: `frontend/src/api/queries.ts` (TanStack Query hooks)
- Create: `frontend/src/stores/settings.ts` (Zustand)
- Create: `frontend/src/stores/screening.ts` (Zustand)
- Create: `frontend/src/hooks/useWebSocket.ts`

**Purpose:** Type-safe API client, React Query hooks for data fetching, Zustand stores for client state, WebSocket hook for screening progress.

```typescript
// api/client.ts — thin wrapper around fetch
export async function apiGet<T>(path: string): Promise<T> { ... }
export async function apiPost<T>(path: string, body?: unknown): Promise<T> { ... }
export async function apiPut<T>(path: string, body: unknown): Promise<T> { ... }

// api/queries.ts — TanStack Query hooks
export function useSettings() { return useQuery({ queryKey: ['settings'], queryFn: ... }) }
export function useModels() { return useQuery({ queryKey: ['models'], queryFn: ... }) }
export function useScreeningResults(sessionId: string) { ... }

// hooks/useWebSocket.ts
export function useScreeningProgress(sessionId: string | null) {
  // Connect to ws://localhost:8000/api/screening/progress/{sessionId}
  // Return { progress, latestResult, isConnected }
}
```

```bash
git commit -m "feat: add API client, TanStack Query hooks, Zustand stores, and WebSocket hook"
```

---

### Task 10: Settings Page

**Files:**
- Create: `frontend/src/pages/Settings.tsx`

**Purpose:** First real page. API key input fields, model list with enable/disable toggles, inference parameter display. Uses Settings API from Task 2.

**Sections:**
1. API Keys — text inputs for OpenRouter / Together AI, "Test Key" button
2. Models — table of available models from `/api/settings/models`, toggle switches
3. Inference — seed input (default 42), timeout slider, temperature display (locked 0.0)
4. Save button that PUTs to `/api/settings`

```bash
git commit -m "feat: add Settings page with API key config and model management"
```

---

## Phase 3: Core Pages (Tasks 11–15)

### Task 11: Dashboard Page

**Files:**
- Create: `frontend/src/pages/Dashboard.tsx`

**Purpose:** Landing page with workflow overview cards, system status, quick-start buttons.

**Components:**
- 5 workflow step cards (Upload → Criteria → Screen → Extract → Assess)
- System status badges (API key configured?, models available?)
- Quick-start buttons linking to each page

```bash
git commit -m "feat: add Dashboard page with workflow cards and system status"
```

---

### Task 12: Screening Page — Steps 1 & 2 (Upload + Criteria)

**Files:**
- Create: `frontend/src/pages/Screening.tsx`
- Create: `frontend/src/components/screening/FileUpload.tsx`
- Create: `frontend/src/components/screening/CriteriaSetup.tsx`
- Create: `frontend/src/components/screening/Stepper.tsx`

**Purpose:** Linear stepper UI. Step 1: drag-drop file upload with format detection and record preview table. Step 2: criteria setup (upload YAML / enter topic for AI generation / select template).

**File upload component:**
- Drag-drop zone accepting .ris, .bib, .csv, .xlsx, .json
- Calls `POST /api/screening/upload` with FormData
- Displays: record count, with/without abstract stats, preview table

**Criteria setup component:**
- Tab interface: "Upload YAML" | "Generate from Topic" | "Use Template"
- Upload YAML: file picker → `POST /api/screening/criteria`
- Generate: text input → `POST /api/screening/criteria` with `{mode: "topic", text: "..."}`
- Template: list of built-in templates → select → preview → confirm

```bash
git commit -m "feat: add Screening page with file upload and criteria setup steps"
```

---

### Task 13: Screening Page — Steps 3 & 4 (Run + Results)

**Files:**
- Create: `frontend/src/components/screening/ScreeningRunner.tsx`
- Create: `frontend/src/components/screening/ScreeningResults.tsx`

**Purpose:** Step 3: model selection, "Run Screening" button, real-time progress via WebSocket (progress bar, live pie chart, per-record status log). Step 4: filterable results table, decision distribution chart, tier breakdown, export buttons.

**WebSocket progress display:**
- Progress bar: `{screened}/{total}` with percentage
- Live pie chart updating as decisions come in
- Scrolling log of per-record decisions
- Estimated time remaining

**Results table:**
- Columns: ID, Title, Decision (color-coded), Tier, Score, Confidence, Models
- Sort by any column
- Filter by decision type
- Export: CSV, Excel, JSON, RIS download buttons

```bash
git commit -m "feat: add screening execution with WebSocket progress and results display"
```

---

### Task 14: Evaluation Page

**Files:**
- Create: `frontend/src/pages/Evaluation.tsx`

**Purpose:** Upload gold standard → compute metrics → display interactive charts → export for paper.

**Sections:**
1. Gold standard upload (file picker)
2. "Run Evaluation" button → calls API
3. Metrics summary cards (sensitivity, specificity, F1, WSS@95, AUROC, ECE)
4. Interactive charts: ROC curve, calibration plot, score distribution (Recharts)
5. Lancet-formatted text area (copy-ready: middle dots, en dashes)
6. Figure export: PNG (300 DPI), SVG download buttons

```bash
git commit -m "feat: add Evaluation page with metrics display and paper-quality chart export"
```

---

### Task 15: Extraction + Quality Pages

**Files:**
- Create: `frontend/src/pages/Extraction.tsx`
- Create: `frontend/src/pages/Quality.tsx`

**Extraction page:**
1. Upload form YAML → display as structured table
2. Upload PDFs → show file list with sizes
3. "Run Extraction" → progress → editable results table
4. Consensus indicators per field
5. Export: CSV, JSON, Excel

**Quality page:**
1. Tool selector: RoB 2 / ROBINS-I / QUADAS-2 (radio with descriptions)
2. Upload PDFs
3. "Run Assessment" → progress
4. Traffic-light summary table (green/yellow/red/grey)
5. Expandable domain drill-down with rationale and quotes
6. Export: JSON, Excel

```bash
git commit -m "feat: add Extraction and Quality Assessment pages"
```

---

## Phase 4: Packaging + Docker (Tasks 16–18)

### Task 16: PyPI Wheel with Frontend Assets

**Files:**
- Modify: `pyproject.toml` (force-include web/dist)
- Create: `Makefile` (build commands)
- Modify: `.github/workflows/` or `scripts/build.sh`

**Step 1: Add force-include to pyproject.toml**

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/metascreener/web/dist" = "metascreener/web/dist"
```

**Step 2: Create build script**

```makefile
# Makefile
.PHONY: build-frontend build-backend build

build-frontend:
	cd frontend && npm ci && npm run build

build-backend: build-frontend
	hatch build

build: build-backend

dev-frontend:
	cd frontend && npm run dev

dev-backend:
	uv run metascreener serve --api-only
```

**Step 3: Verify wheel contains dist/**

```bash
make build
unzip -l dist/metascreener-*.whl | grep web/dist
# Should show index.html, assets/*, etc.
```

```bash
git commit -m "feat: configure PyPI wheel to include React build artifacts"
```

---

### Task 17: Docker Multi-Stage Build

**Files:**
- Modify: `docker/Dockerfile` (add Node.js build stage)

**Updated Dockerfile:**

```dockerfile
# ---- Node: Build React frontend ----
FROM node:22-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build
# Output: /app/frontend/dist → maps to /app/src/metascreener/web/dist

# ---- Python base ----
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md ./
COPY src/ src/
COPY configs/ configs/
# Copy frontend build artifacts
COPY --from=frontend-builder /app/frontend/dist src/metascreener/web/dist/
RUN uv sync --frozen --no-dev

# ---- Slim: metascreener serve ----
FROM base AS slim
EXPOSE 8000
ENTRYPOINT ["uv", "run", "metascreener"]
CMD ["serve", "--host", "0.0.0.0"]

# ---- Full: reproduction ----
FROM base AS full
RUN uv sync --frozen --extra dev --extra viz
COPY validation/ validation/
COPY scripts/ scripts/
COPY paper/ paper/
COPY tests/ tests/
ENTRYPOINT ["bash"]
```

**Verify:**
```bash
docker build -f docker/Dockerfile --target slim -t metascreener .
docker run -p 8000:8000 -e OPENROUTER_API_KEY=test metascreener
# Browser opens localhost:8000 → React UI
```

```bash
git commit -m "feat: update Dockerfile with Node.js build stage for React frontend"
```

---

### Task 18: End-to-End Verification

**Checklist:**
- [ ] `pip install -e .` → `metascreener serve` → browser shows React UI
- [ ] `metascreener screen --input test.ris` → CLI still works
- [ ] `metascreener ui` → Streamlit still works
- [ ] `docker build` → `docker run` → React UI accessible
- [ ] All 669+ existing tests still pass
- [ ] `uv run ruff check src/ tests/` → 0 errors
- [ ] `uv run mypy src/` → 0 errors
- [ ] Settings page: can enter API key, see models
- [ ] Screening page: upload RIS → set criteria → run → see results (with mock or real API key)

```bash
git commit -m "test: verify end-to-end workflow for pip install, Docker, and all pages"
git tag v2.0.0a4
```

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| Phase 1 | 1–6 | FastAPI backend: skeleton, settings, screening, evaluation, extraction, quality APIs |
| Phase 2 | 7–10 | React setup: Vite scaffold, Glass Design System, layout, router, API client, Settings page |
| Phase 3 | 11–15 | Core pages: Dashboard, Screening (4-step stepper), Evaluation, Extraction, Quality |
| Phase 4 | 16–18 | Packaging: PyPI wheel with assets, Docker multi-stage, E2E verification |

**Total: 18 tasks across 4 phases.**

Phases 1 and 2 can be developed in parallel (backend + frontend independently).
Tasks within Phase 3 can also be parallelized (each page is independent).
