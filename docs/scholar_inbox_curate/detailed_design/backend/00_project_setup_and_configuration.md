# 00 — Project Setup & Configuration

## Overview

This document covers the project scaffolding, dependency management, configuration loading, and environment variable handling needed before any application logic runs.

---

## Project Packaging (`pyproject.toml`)

The project uses a standard `pyproject.toml` with a `[project.scripts]` entry point for the CLI.

```toml
[project]
name = "scholar-inbox-curate"
version = "0.1.0"
description = "Monitor Scholar Inbox paper recommendations and track citation traction"
requires-python = ">=3.12"
dependencies = [
    "playwright>=1.40",
    "httpx>=0.27",
    "apscheduler>=3.10,<4",
    "click>=8.1",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "jinja2>=3.1",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.3",
]

[project.scripts]
scholar-curate = "src.cli:cli"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.setuptools.packages.find]
include = ["src*"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

### Post-install: Playwright Browser

After `pip install`, Playwright's Chromium browser must be installed:

```bash
playwright install chromium
```

This should be documented in the README and can be added as a post-install script or Makefile target.

---

## Directory Layout

```
scholar_inbox_curate/              # Project root
├── src/
│   ├── __init__.py
│   ├── cli.py                     # Click CLI entry point
│   ├── config.py                  # Load config.toml + .env
│   ├── constants.py               # Centralised constants (URLs, thresholds, schema version)
│   ├── db.py                      # SQLite connection, migrations, queries
│   ├── errors.py                  # Custom exception hierarchy + retry decorator
│   ├── rules.py                   # Prune/promote logic
│   ├── scheduler.py               # APScheduler setup
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── scraper.py             # Scholar Inbox API client (httpx + Playwright auth)
│   │   ├── resolver.py            # Resolve paper IDs via Semantic Scholar
│   │   ├── reresolver.py          # Re-resolve dangling papers with fallback IDs
│   │   ├── orchestrate.py         # Ingestion orchestration (shared by CLI and web)
│   │   └── backfill.py            # Gap detection, backfill, and dangling paper re-resolution
│   ├── citations/
│   │   ├── __init__.py
│   │   ├── semantic_scholar.py    # Semantic Scholar batch API client
│   │   ├── openalex.py            # OpenAlex API client
│   │   ├── velocity.py            # Velocity computation logic
│   │   └── poller.py              # Citation poll orchestration
│   └── web/
│       ├── __init__.py
│       ├── app.py                 # FastAPI application factory
│       ├── filters.py             # Jinja2 template filters
│       ├── routes/
│       │   ├── __init__.py
│       │   ├── dashboard.py
│       │   ├── papers.py
│       │   ├── settings.py
│       │   └── triggers.py
│       ├── templates/
│       └── static/
├── scripts/
│   └── daily_update.sh            # Daily cron script (backfill + ingest + poll + prune)
├── data/                          # Runtime data (gitignored)
│   ├── scholar_curate.db
│   ├── cookies.json               # Session cookies for API access
│   └── browser_profile/           # Playwright persistent context (headed login only)
├── config.toml
├── .env
├── pyproject.toml
├── CHANGELOG.md
└── tests/
    ├── __init__.py
    ├── conftest.py                # Shared fixtures (in-memory DB, mock configs)
    └── scholar_inbox_curate/
        ├── citations/
        │   ├── test_openalex.py
        │   ├── test_poller.py
        │   ├── test_semantic_scholar.py
        │   └── test_velocity.py
        ├── cli/
        │   └── test_cli.py
        ├── config/
        │   └── test_config.py
        ├── db/
        │   └── test_db.py
        ├── errors/
        │   └── test_errors.py
        ├── ingestion/
        │   ├── test_backfill.py
        │   ├── test_orchestrate.py
        │   ├── test_reresolver.py
        │   ├── test_resolver.py
        │   └── test_scraper.py
        ├── rules/
        │   └── test_rules.py
        ├── scheduler/
        │   └── test_scheduler.py
        └── web/
            ├── test_app.py
            ├── test_dashboard.py
            ├── test_filters.py
            ├── test_paper_detail.py
            ├── test_paper_list.py
            └── test_settings.py
```

The `data/` directory is created at runtime if it doesn't exist. It is added to `.gitignore`.

---

## Configuration Loading (`src/config.py`)

Configuration is loaded in two layers:

1. **`config.toml`** — application settings (thresholds, schedules, paths)
2. **`.env`** — secrets (credentials, API keys)

### Config Data Class

```python
from dataclasses import dataclass, field
from pathlib import Path
import tomllib
from dotenv import load_dotenv
import os


@dataclass(frozen=True)
class IngestionConfig:
    score_threshold: float = 0.60  # Ranking score 0.0-1.0 (displayed as 0-100 in Scholar Inbox UI)
    schedule_cron: str = "0 8 * * 1"
    backfill_score_threshold: float = 0.60  # threshold used during backfill (0.0-1.0 scale)
    backfill_lookback_days: int = 30        # how far back to search for gaps


@dataclass(frozen=True)
class CitationConfig:
    semantic_scholar_batch_size: int = 100
    poll_schedule_cron: str = "0 6 * * 3"
    poll_budget_fraction: float = 0.10  # Fraction of non-pruned papers to poll per cycle


@dataclass(frozen=True)
class PruningConfig:
    min_age_months: int = 6
    min_citations: int = 10
    min_velocity: float = 1.0


@dataclass(frozen=True)
class PromotionConfig:
    citation_threshold: int = 50
    velocity_threshold: float = 10.0


@dataclass(frozen=True)
class BrowserConfig:
    profile_dir: str = "data/browser_profile"
    headed_fallback: bool = True


@dataclass(frozen=True)
class SecretsConfig:
    scholar_inbox_email: str = ""
    scholar_inbox_password: str = ""
    semantic_scholar_api_key: str = ""


@dataclass(frozen=True)
class AppConfig:
    ingestion: IngestionConfig = field(default_factory=IngestionConfig)
    citations: CitationConfig = field(default_factory=CitationConfig)
    pruning: PruningConfig = field(default_factory=PruningConfig)
    promotion: PromotionConfig = field(default_factory=PromotionConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    secrets: SecretsConfig = field(default_factory=SecretsConfig)
    db_path: str = "data/scholar_curate.db"
```

### Loading Logic

```python
def load_config(config_path: str = "config.toml", env_path: str = ".env") -> AppConfig:
    """Load configuration from TOML file and environment variables.

    Priority: environment variables > .env file > config.toml > defaults.
    """
    # Load .env into os.environ
    load_dotenv(env_path)

    # Load TOML
    toml_data = {}
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file, "rb") as f:
            toml_data = tomllib.load(f)

    # Build config from TOML sections
    ingestion = IngestionConfig(**toml_data.get("ingestion", {}))
    citations = CitationConfig(**toml_data.get("citations", {}))
    pruning = PruningConfig(**toml_data.get("pruning", {}))
    promotion = PromotionConfig(**toml_data.get("promotion", {}))
    browser = BrowserConfig(**toml_data.get("browser", {}))

    # Secrets from environment
    secrets = SecretsConfig(
        scholar_inbox_email=os.getenv("SCHOLAR_INBOX_EMAIL", ""),
        scholar_inbox_password=os.getenv("SCHOLAR_INBOX_PASSWORD", ""),
        semantic_scholar_api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY", ""),
    )

    db_path = toml_data.get("database", {}).get("path", "data/scholar_curate.db")

    return AppConfig(
        ingestion=ingestion,
        citations=citations,
        pruning=pruning,
        promotion=promotion,
        browser=browser,
        secrets=secrets,
        db_path=db_path,
    )
```

### Validation

`load_config()` performs basic validation after loading:

- `score_threshold` must be between 0.0 and 1.0 (decimal scale representing API ranking score)
- `backfill_score_threshold` must be between 0.0 and 1.0
- `backfill_lookback_days` must be > 0
- `min_age_months` must be > 0
- `min_citations` must be >= 0
- `semantic_scholar_batch_size` must be between 1 and 500 (API limit)
- `poll_budget_fraction` must be between 0.0 (exclusive) and 1.0 (inclusive)
- Secrets: warn (not error) if `scholar_inbox_email` or `scholar_inbox_password` are empty — ingestion CLI commands will fail at runtime, but citation polling can still work independently

Validation errors raise `ConfigError(message)` — a custom exception defined in `src/errors.py` and imported into `src/config.py`.

---

## Default `config.toml`

Shipped with the repo as a reference:

```toml
[database]
path = "data/scholar_curate.db"

[ingestion]
score_threshold = 0.60            # Scholar Inbox API ranking score (0.0-1.0 decimal scale)
schedule_cron = "0 8 * * 1"       # Every Monday at 8 AM
backfill_score_threshold = 0.60   # Score threshold for backfill runs
backfill_lookback_days = 30       # How many days back to check for gaps

[citations]
semantic_scholar_batch_size = 100
poll_schedule_cron = "0 6 * * 3"  # Every Wednesday at 6 AM
poll_budget_fraction = 0.10       # Cap each poll cycle to 10% of non-pruned papers

[pruning]
min_age_months = 6
min_citations = 10
min_velocity = 1.0

[promotion]
citation_threshold = 50
velocity_threshold = 10.0

[browser]
profile_dir = "data/browser_profile"
headed_fallback = true
```

---

## `.env` Template

A `.env.example` is committed to the repo:

```
SCHOLAR_INBOX_EMAIL=
SCHOLAR_INBOX_PASSWORD=
SEMANTIC_SCHOLAR_API_KEY=
```

The actual `.env` is gitignored.

---

## Logging

The application uses Python's built-in `logging` module. Configuration is set up once in `cli.py` before any command runs:

```python
import logging

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
```

Each module gets its own logger: `logger = logging.getLogger(__name__)`.

Log levels:
- **DEBUG**: API request/response details, SQL queries, scraping element details
- **INFO**: ingestion/poll cycle start/end, paper counts, status changes
- **WARNING**: missing API keys, rate limit approaching, Cloudflare challenge detected
- **ERROR**: API failures, scraping errors, database errors

---

## Runtime Directory Initialization

On startup (in `cli.py`), ensure the `data/` directory exists:

```python
from pathlib import Path

def ensure_data_dir(config: AppConfig):
    Path(config.db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(config.browser.profile_dir).mkdir(parents=True, exist_ok=True)
```

This runs before any database or browser operations.
