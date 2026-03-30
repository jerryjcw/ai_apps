# 01 — Scraping & Parsing

## Overview

Stage 0 (scrape) fetches raw text from alphaxiv.org's trending page using Playwright. Stage 1 (parse) converts the raw text into structured paper data using regex, with an LLM fallback if the format changes.

---

## Module: `src/scraping/trending.py`

### Public Interface

```python
async def scrape_trending(config: AppConfig) -> str:
    """Scrape alphaxiv trending page and return raw text content.

    Steps:
        1. Launch headless Chromium via Playwright.
        2. Navigate to alphaxiv with configured sort order.
        3. If categories/subcategories configured, interact with filter UI.
        4. Wait for React hydration (paper cards to render).
        5. Scroll to load all papers (if lazy-loaded).
        6. Extract full page text via page.inner_text("body").
        7. Return raw text.

    Raises:
        ScrapeError: If page fails to load or no paper content detected.
    """
```

### Playwright Strategy

```python
from playwright.async_api import async_playwright

async def _launch_and_scrape(config: AppConfig) -> str:
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    page = await browser.new_page()

    # Build URL with sort parameter
    url = f"{ALPHAXIV_BASE_URL}?sort={config.scraping.sort}"
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)

    # Wait for React hydration — paper cards to appear
    await page.wait_for_selector("[class*='paper'], [class*='card'], article",
                                  timeout=15000)

    # Apply category filters if configured (UI interaction required)
    if config.scraping.categories or config.scraping.subcategories:
        await _apply_filters(page, config.scraping)

    # Scroll to bottom to trigger lazy loading
    await _scroll_to_bottom(page)

    # Extract text
    raw_text = await page.inner_text("body")

    await browser.close()
    await pw.stop()
    return raw_text


async def _scroll_to_bottom(page, max_scrolls: int = 20, pause_ms: int = 1000):
    """Scroll incrementally to trigger lazy-loaded paper cards."""
    prev_height = 0
    for _ in range(max_scrolls):
        curr_height = await page.evaluate("document.body.scrollHeight")
        if curr_height == prev_height:
            break
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(pause_ms)
        prev_height = curr_height


async def _apply_filters(page, scraping_config: ScrapingConfig):
    """Interact with alphaxiv filter UI to apply category filters.

    Category/subcategory filters are optional. If no filters are configured,
    this function is not called.

    Note: The exact selectors will need discovery during development
    (inspect the live React UI). The filter UI is React-driven, so we
    look for filter toggle buttons, category checkboxes, etc.

    Fallback behavior: If filter interaction fails (selector not found,
    timeout, element not clickable), log a warning and continue with
    unfiltered results. The pipeline should never fail because of a
    filter UI change — unfiltered results are still useful.

    Raises:
        Nothing — failures are logged as warnings, not raised.
    """
    try:
        # TODO: Discover actual selectors during development.
        # Expected approach:
        # 1. Click filter/category toggle button
        # 2. Select configured categories from dropdown/checkboxes
        # 3. Wait for page to re-render with filtered results
        pass
    except Exception as e:
        logger.warning("Failed to apply category filters: %s. Continuing unfiltered.", e)
```

### Engagement Threshold Filtering

Engagement filtering happens after parsing (not during scraping), since bookmark/view counts are extracted from the raw text during parse. See the `filter_by_engagement()` function in the parser module.

---

## Module: `src/parsing/raw_parser.py`

### Public Interface

```python
@dataclass
class ParsedPaper:
    """A single paper extracted from alphaxiv trending page."""
    index: int
    title: str
    date: str                    # "DD Mon YYYY" as found on page
    authors_raw: str             # unparsed author/institution string
    abstract: str
    hashtags: list[str]          # e.g. ["#attention-mechanisms", "#computer-science"]
    bookmark_count: int
    view_count: int
    arxiv_id: str | None = None  # extracted from URL if present


def parse_raw_text(raw_text: str) -> list[ParsedPaper]:
    """Parse raw alphaxiv page text into structured papers.

    Uses regex + state machine approach.
    If fewer than 3 papers are found, raises ParseError to trigger LLM fallback.

    Raises:
        ParseError: If regex parsing yields < 3 papers.
    """


def filter_by_engagement(
    papers: list[ParsedPaper],
    min_bookmarks: int = 0,
    min_views: int = 0,
) -> list[ParsedPaper]:
    """Discard papers below engagement thresholds.

    Args:
        papers: Parsed papers from parse_raw_text().
        min_bookmarks: Minimum bookmark count (0 = no filter).
        min_views: Minimum view count (0 = no filter).

    Returns:
        Filtered list. Re-indexes papers starting from 1.
    """
```

### Raw Text Format

Each paper in the rendered page text follows this pattern:

```
{Title}{DD Mon YYYY}{Authors/Institutions}{Abstract}View blog#{tag1}#{tag2}...{numbers}BookmarkResources{bookmark_count}{view_count}
```

Example:
```
Attention Residuals16 Mar 2026Kimi TeamGuangyu ChenYu ZhangThe Kimi Team introduced...View blog#attention-mechanisms#computer-science#computation-and-language121BookmarkResources8102,250
```

### Regex Parsing Strategy

```python
import re

DATE_PATTERN = r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})"
HASHTAG_PATTERN = r"(#[\w-]+)"
BOOKMARK_RESOURCES_PATTERN = r"BookmarkResources([\d,]+)([\d,]+)"

def _parse_with_regex(raw_text: str) -> list[ParsedPaper]:
    """State-machine parser that splits raw text into paper entries.

    Approach:
    1. Find all date matches — each date starts a new paper entry.
    2. The text BEFORE the date (back to the previous entry's end) is the title.
    3. The text AFTER the date until "View blog" contains authors + abstract.
    4. Between "View blog" and "BookmarkResources" are the hashtags.
    5. After "BookmarkResources" are bookmark_count and view_count.

    The authors/abstract boundary is ambiguous — we split by heuristic:
    authors = text up to the first sentence-like fragment (capitalized, > 50 chars).
    """
```

### LLM Fallback Parser

If the regex parser finds fewer than 3 papers, the format may have changed. Fall back to an LLM call.

```python
async def parse_with_llm_fallback(
    raw_text: str,
    config: AppConfig,
) -> list[ParsedPaper]:
    """Parse raw text using LLM when regex fails.

    Uses extended thinking to reason through the text structure.
    Includes few-shot examples from src/analysis/examples/.
    """
```

See [03 — LLM Integration](03_llm_integration.md) for the full prompt design and extended thinking configuration for this fallback.

---

## Output Files

### `papers.json`

```json
[
    {
        "index": 1,
        "title": "Attention Residuals",
        "date": "16 Mar 2026",
        "authors_raw": "Kimi Team, Guangyu Chen, Yu Zhang",
        "abstract": "The Kimi Team introduced Attention Residuals...",
        "hashtags": ["#attention-mechanisms", "#computer-science"],
        "bookmark_count": 810,
        "view_count": 2250,
        "arxiv_id": null
    }
]
```

### `titles.md`

Human-readable markdown matching the reference format from cowork sessions:

```markdown
# AlphaXiv Popular Papers - YYYY/MM/DD

Total papers extracted: **N**

---

## 1. {Title}

**Date:** {DD Mon YYYY}

**Abstract:** {Abstract text}

---

## 2. {Title}
...
```

### Generation

```python
def write_titles_md(papers: list[ParsedPaper], run_date: str, output_path: Path):
    """Write titles.md matching the reference cowork output format."""

def write_papers_json(papers: list[ParsedPaper], output_path: Path):
    """Write papers.json for machine consumption."""
```
