# 00 — Project Setup & Configuration

## Overview

This document covers the project scaffolding, dependency management, configuration loading, and environment variable handling.

---

## Project Packaging (`pyproject.toml`)

```toml
[project]
name = "alpharxiv-trendy-analysis"
version = "0.1.0"
description = "Automated discovery and analysis of trending AI research papers from alphaxiv.org"
requires-python = ">=3.12"
dependencies = [
    "anthropic>=0.40",
    "playwright>=1.40",
    "httpx>=0.27",
    "click>=8.1",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
pdf = [
    "pdfplumber>=0.10",        # only needed for Stage 3 if arXiv HTML unavailable
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.3",
]

[project.scripts]
arxiv-trendy = "src.cli:cli"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.setuptools.packages.find]
include = ["src*"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

### Post-install: Playwright Browser

```bash
playwright install chromium
```

---

## Configuration (`config.py`)

### `AppConfig` — Frozen Dataclass

All configuration is loaded once at startup and passed through the pipeline. No mutable global state.

```python
from dataclasses import dataclass, field
from pathlib import Path
import tomllib
import os

@dataclass(frozen=True)
class ScrapingConfig:
    sort: str = "Hot"                          # "Hot" or "Likes"
    categories: list[str] = field(default_factory=list)
    subcategories: list[str] = field(default_factory=list)
    custom_categories: list[str] = field(default_factory=list)
    min_bookmarks: int = 0
    min_views: int = 0

@dataclass(frozen=True)
class EnrichmentConfig:
    rate_limit_seconds: float = 1.0            # arXiv API rate limit
    timeout_seconds: float = 30.0

@dataclass(frozen=True)
class LLMConfig:
    # Per-stage model selection (Opus for reasoning, Sonnet for lightweight tasks)
    model_analyze: str = "claude-opus-4-6"       # Stage 2 Phase A (deep analysis)
    model_review: str = "claude-opus-4-6"        # Stage 3 (literature review)
    model_parse: str = "claude-sonnet-4-6"       # Stage 1 parse fallback
    model_translate: str = "claude-sonnet-4-6"   # Stage 3/4 translation to Chinese
    model_plan: str = "claude-opus-4-6"          # Stage 4 planning agent
    model_critic: str = "claude-opus-4-6"        # Stage 4 adversarial critic
    max_tokens: int = 16000
    max_tokens_analyze: int = 32000              # Stage 2 Phase A needs larger output
    max_tokens_review: int = 16000               # Stage 3 per-turn output (configurable)
    max_tokens_plan: int = 24000                 # Stage 4 per-turn output (ablations+risks need headroom)
    temperature: float = 1.0                     # required for extended thinking
    thinking_budget_parse: int = 5000
    thinking_budget_analyze: int = 40000         # must reason across ~60 papers comparatively
    thinking_budget_review: int = 16000          # per turn (3 turns per paper)
    thinking_budget_plan: int = 24000            # per planning turn (up to 4 turns per proposal)
    thinking_budget_critic: int = 16000          # adversarial critic review

@dataclass(frozen=True)
class CriteriaConfig:
    max_compute_gpus: int = 16
    gpu_model: str = "H200"
    focus_areas: list[str] = field(default_factory=lambda: [
        "LLM", "Agent", "Reasoning", "Training", "Optimization",
        "Alignment", "RLHF", "Data Curation",
    ])
    require_theoretical: bool = True
    exclude_pure_engineering: bool = True
    target_venues: list[str] = field(default_factory=lambda: [
        "ICLR", "NeurIPS", "ICML", "ACL", "EMNLP", "AAAI", "UAI",
    ])

@dataclass(frozen=True)
class DatabaseConfig:
    path: str = "data/trendy.db"

@dataclass(frozen=True)
class OutputConfig:
    base_dir: str = "data/runs"

@dataclass(frozen=True)
class AppConfig:
    scraping: ScrapingConfig
    enrichment: EnrichmentConfig
    llm: LLMConfig
    criteria: CriteriaConfig
    database: DatabaseConfig
    output: OutputConfig
    anthropic_api_key: str = ""
```

### Loading

```python
def load_config(config_path: Path = Path("config.toml")) -> AppConfig:
    """Load config from TOML file + .env overrides.

    Priority: .env > config.toml > defaults.
    """
    from dotenv import load_dotenv
    load_dotenv()

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    return AppConfig(
        scraping=ScrapingConfig(**raw.get("scraping", {})),
        enrichment=EnrichmentConfig(**raw.get("enrichment", {})),
        llm=LLMConfig(**raw.get("llm", {})),
        criteria=CriteriaConfig(**raw.get("criteria", {})),
        database=DatabaseConfig(**raw.get("database", {})),
        output=OutputConfig(**raw.get("output", {})),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
    )
```

---

## Example `config.toml`

```toml
[scraping]
sort = "Hot"
categories = ["computer-science"]
subcategories = []
custom_categories = []
min_bookmarks = 0
min_views = 0

[enrichment]
rate_limit_seconds = 1.0
timeout_seconds = 30.0

[llm]
model_analyze = "claude-opus-4-6"         # Stage 2 Phase A (deep analysis)
model_review = "claude-opus-4-6"          # Stage 3 (literature review)
model_parse = "claude-sonnet-4-6"         # Stage 1 parse fallback
model_translate = "claude-sonnet-4-6"     # Stage 3/4 translation
model_plan = "claude-opus-4-6"           # Stage 4 planning agent
model_critic = "claude-opus-4-6"         # Stage 4 adversarial critic
max_tokens = 16000
max_tokens_analyze = 32000                # Stage 2 Phase A needs larger output for ~60 papers
max_tokens_review = 16000                 # Stage 3 per-turn output
max_tokens_plan = 24000                   # Stage 4 per-turn output (Turn 3 has 4 sections)
temperature = 1.0
thinking_budget_parse = 5000
thinking_budget_analyze = 40000           # comparative reasoning across ~60 papers
thinking_budget_review = 16000            # per turn (3 turns per paper)
thinking_budget_plan = 24000              # per planning turn (up to 4 turns per proposal)
thinking_budget_critic = 16000            # adversarial critic review

[criteria]
max_compute_gpus = 16
gpu_model = "H200"
focus_areas = ["LLM", "Agent", "Reasoning", "Training", "Optimization", "Alignment", "RLHF", "Data Curation"]
require_theoretical = true
exclude_pure_engineering = true
target_venues = ["ICLR", "NeurIPS", "ICML", "ACL", "EMNLP", "AAAI", "UAI"]

[database]
path = "data/trendy.db"

[output]
base_dir = "data/runs"
```

---

## `.env`

```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Constants (`constants.py`)

```python
ALPHAXIV_BASE_URL = "https://alphaxiv.org"
ARXIV_API_BASE_URL = "http://export.arxiv.org/api/query"

# Parsing thresholds
MIN_PAPERS_REGEX_THRESHOLD = 3  # If regex finds fewer papers, fall back to LLM parser

# Regex patterns for raw text parsing
DATE_PATTERN = r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}"
VIEW_BLOG_MARKER = "View blog"
BOOKMARK_RESOURCES_MARKER = "BookmarkResources"

# Output file names
RAW_INPUT_FILE = "raw_input.txt"
PAPERS_JSON_FILE = "papers.json"
TITLES_MD_FILE = "titles.md"
ENRICHED_JSON_FILE = "enriched_papers.json"
FILTER_RESULT_FILE = "filter_result.json"
FILTERED_ZH_FILE = "filtered_zh.md"
FILTERED_EN_FILE = "filtered_en.md"
LIT_REVIEW_ZH_FILE = "literature_review_zh.md"
LIT_REVIEW_EN_FILE = "literature_review_en.md"
LIT_REVIEW_JSON_FILE = "literature_review.json"    # structured proposals for Stage 4
EXPERIMENT_PLAN_EN_TEMPLATE = "experiment_plan_p{paper}_r{proposal}_en.md"
EXPERIMENT_PLAN_ZH_TEMPLATE = "experiment_plan_p{paper}_r{proposal}_zh.md"
EXPERIMENT_PLAN_JSON_TEMPLATE = "experiment_plan_p{paper}_r{proposal}.json"
THINKING_LOGS_DIR = "thinking_logs"

# Semantic Scholar
S2_API_BASE_URL = "https://api.semanticscholar.org/graph/v1"
```

---

## Error Hierarchy (`errors.py`)

```python
class AlphaRxivError(Exception):
    """Base exception for the application."""

class ScrapeError(AlphaRxivError):
    """Failed to scrape alphaxiv trending page."""

class ParseError(AlphaRxivError):
    """Failed to parse raw text into structured papers."""

class EnrichmentError(AlphaRxivError):
    """Failed to enrich paper via arXiv API."""

class LLMError(AlphaRxivError):
    """LLM API call failed."""

class LLMThinkingError(LLMError):
    """Extended thinking produced insufficient or malformed output."""

class PlanningError(AlphaRxivError):
    """Experiment planning failed (Stage 4)."""

class ConfigError(AlphaRxivError):
    """Configuration is invalid or missing."""
```

---

## Directory Structure

Each run creates a timestamped output directory:

```
data/runs/2026-03-20/
├── raw_input.txt
├── papers.json
├── titles.md
├── enriched_papers.json
├── filter_result.json
├── filtered_zh.md
├── filtered_en.md
├── literature_review_zh.md
├── literature_review_en.md
├── literature_review.json              # structured proposals (Stage 4 input)
├── experiment_plan_p3_r1_en.md
├── experiment_plan_p3_r1_zh.md
├── experiment_plan_p3_r1.json
└── thinking_logs/
    ├── stage2_analysis.txt
    ├── stage3_paper_1_turn_1.txt
    ├── stage3_paper_1_turn_2.txt
    ├── stage3_paper_1_turn_3.txt
    ├── stage4_p3_r1_plan_turn1.txt
    ├── stage4_p3_r1_plan_turn2.txt
    ├── stage4_p3_r1_plan_turn3.txt
    ├── stage4_p3_r1_critic.txt
    ├── stage4_p3_r1_revision.txt
    └── ...
```

The `thinking_logs/` directory stores the extended thinking content from each LLM call for debugging and quality review.
