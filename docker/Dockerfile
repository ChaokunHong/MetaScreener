# ============================================================
# MetaScreener 2.0 — Multi-stage Docker Build
# ============================================================
# Targets:
#   slim  — daily use (metascreener CLI + Streamlit UI)
#   full  — reproduction (validation experiments + paper outputs)
#
# Build:
#   docker build -f docker/Dockerfile --target slim -t metascreener .
#   docker build -f docker/Dockerfile --target full -t metascreener:full .
#
# Run:
#   docker run metascreener screen --help
#   docker run -p 8501:8501 metascreener ui
#   docker run metascreener:full bash scripts/run_all_validations.sh --mock
# ============================================================

# ---- Base: Python + uv + runtime dependencies ----
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install runtime dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code and install project
COPY src/ src/
COPY configs/ configs/
RUN uv sync --frozen --no-dev

# ---- Slim: Daily use image ----
FROM base AS slim

LABEL org.opencontainers.image.title="MetaScreener" \
      org.opencontainers.image.description="Open-source multi-LLM ensemble for systematic review workflows" \
      org.opencontainers.image.source="https://github.com/ChaokunHong/MetaScreener" \
      org.opencontainers.image.licenses="Apache-2.0"

EXPOSE 8501

ENTRYPOINT ["uv", "run", "metascreener"]

# ---- Full: Reproduction image ----
FROM base AS full

# Install dev + viz extras for validation experiments
RUN uv sync --frozen --extra dev --extra viz

# Copy validation infrastructure
COPY validation/ validation/
COPY scripts/ scripts/
COPY paper/ paper/
COPY tests/ tests/

LABEL org.opencontainers.image.title="MetaScreener (full)" \
      org.opencontainers.image.description="MetaScreener with validation experiments for paper reproduction"

ENTRYPOINT ["bash"]
