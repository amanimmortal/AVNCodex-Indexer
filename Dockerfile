# STAGE 1: BUILDER
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PYTHON=python3.12

WORKDIR /app
COPY pyproject.toml uv.lock ./

# Install dependencies to system (in builder stage only) or strictly to .venv
RUN uv sync --no-install-project --no-dev

# STAGE 2: RUNNER
FROM python:3.12-slim-bookworm

# Install runtime dependencies (gosu for PUID/PGID support)
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*

# Security: Create non-root user (we start as root to handle PUID/PGID, then drop privileges)
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy venv from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Copy source code
COPY --chown=appuser:appuser . .
COPY --chmod=755 docker-entrypoint.sh /app/docker-entrypoint.sh

# Environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL="sqlite+aiosqlite:////data/avn_index.db"
ENV LOG_DIR="/data/logs"

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
