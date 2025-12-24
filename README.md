# AVNCodex Indexer

A high-performance, async FastAPI application for indexing and tracking games from F95Zone. It bridges the gap between F95Zone's raw data and a rich, queryable local library with detailed metadata from F95Checker.

## Features

- **Automated Indexing**: Scrapes F95Zone for new games and updates.
- **Rich Metadata**: Enriches tracked games with detailed info (downloads, changelogs, tags) via F95Checker API.
- **Async & Fast**: Built with `httpx` and `asyncio` for non-blocking operations.
- **Local Search**: Fast local search with fallback to remote F95Zone search.
- **Tracking**: "Track" specific games to prioritize them for updates.

## Prerequisites

- **Python 3.12+**
- **uv** (Package Manager)
- **Docker** (Optional, for containerized deployment)

## Setup

1.  **Clone the repository**:
    ```bash
    git clone <url>
    cd AVNCodex-Indexer
    ```

2.  **Install Dependencies**:
    ```bash
    uv sync
    ```

3.  **Environment Configuration**:
    Copy `.env.example` to `.env` and fill in your credentials.
    ```bash
    cp .env.example .env
    ```
    *Note: `F95_USERNAME` and `F95_PASSWORD` are required for full functionality.*

4.  **Database Initialization**:
    Run migrations to set up the SQLite database.
    ```bash
    uv run alembic upgrade head
    ```

## Usage

### Local Development
Start the development server:
```bash
uv run fastapi dev app/main.py
```
Access the API at `http://localhost:8000`.
Docs available at `http://localhost:8000/docs`.

### Docker
```bash
docker compose up -d --build
```

## API Reference
See [docs/API_REFERENCE.md](docs/API_REFERENCE.md) for detailed endpoint documentation.

## Verification
To verify API connectivity and client functionality:
```bash
uv run python scripts/verify_api.py
```
