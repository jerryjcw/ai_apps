# 03 — Paper ID Resolution

## Overview

After scraping raw paper data from Scholar Inbox, each paper needs a stable, canonical identifier for tracking. This module resolves papers against the Semantic Scholar Academic Graph API to obtain a `paperId`, and enriches the paper record with additional metadata (venue, year, publication date, DOI).

---

## Module: `src/ingestion/resolver.py`

### Public Interface

```python
from dataclasses import dataclass

@dataclass
class ResolvedPaper:
    """A paper with a resolved Semantic Scholar ID and enriched metadata."""
    semantic_scholar_id: str    # Primary ID for our database
    title: str
    authors: list[str]
    abstract: str
    url: str | None
    arxiv_id: str | None
    doi: str | None
    venue: str | None
    year: int | None
    published_date: str | None  # ISO 8601
    citation_count: int         # Initial citation count from S2
    scholar_inbox_score: float
    scholar_inbox_url: str | None
    category: str | None = None


async def resolve_paper(
    client: httpx.AsyncClient,
    raw: RawPaper,
    config: AppConfig,
) -> ResolvedPaper | None:
    """Resolve a single RawPaper to a ResolvedPaper via Semantic Scholar.

    The config is needed to obtain the API key for rate limiting.
    Returns None if the paper cannot be found on Semantic Scholar.
    """

async def resolve_papers(
    client: httpx.AsyncClient,
    papers: list[RawPaper],
    config: AppConfig,
) -> list[ResolvedPaper]:
    """Resolve a batch of RawPapers, with rate limiting between requests.

    Papers that already have a semantic_scholar_id from Scholar Inbox are
    converted directly to ResolvedPaper without an API call. Only papers
    missing their S2 ID are resolved via the Semantic Scholar API.

    Papers that fail to resolve are given fallback IDs and included.
    """
```

---

## Resolution Strategy

Papers are resolved using a priority chain — try the most specific identifier first, fall back to less specific methods:

### 1. arXiv ID Lookup (Preferred)

If the scraped paper has an `arxiv_id`, look it up directly:

```
GET https://api.semanticscholar.org/graph/v1/paper/ARXIV:{arxiv_id}
    ?fields=paperId,title,authors,abstract,venue,year,publicationDate,
            externalIds,citationCount,url
```

This is the most reliable method — arXiv IDs are unambiguous.

### 2. DOI Lookup

If a DOI is available (less common from Scholar Inbox but possible):

```
GET https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}
    ?fields=paperId,title,authors,abstract,venue,year,publicationDate,
            externalIds,citationCount,url
```

### 3. Title Search (Fallback)

If neither arXiv ID nor DOI is available, search by title:

```
GET https://api.semanticscholar.org/graph/v1/paper/search
    ?query={url_encoded_title}
    &fields=paperId,title,authors,abstract,venue,year,publicationDate,
            externalIds,citationCount,url
    &limit=5
```

Then match against the scraped title using fuzzy comparison.

---

## Title Matching Logic

When using the search endpoint, the API may return multiple results. We need to select the correct one:

```python
from difflib import SequenceMatcher

def _normalize_title(title: str) -> str:
    """Normalize a title for comparison.

    - Lowercase
    - Remove punctuation
    - Collapse whitespace
    """
    import re
    title = title.lower().strip()
    title = re.sub(r'[^\w\s]', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title

def _title_similarity(title1: str, title2: str) -> float:
    """Compute similarity ratio between two titles (0.0 to 1.0)."""
    t1 = _normalize_title(title1)
    t2 = _normalize_title(title2)
    return SequenceMatcher(None, t1, t2).ratio()

def _find_best_match(scraped_title: str, results: list[dict]) -> dict | None:
    """Find the best matching paper from Semantic Scholar search results.

    Returns the result with highest title similarity, if it exceeds
    the minimum threshold of 0.85.
    """
    SIMILARITY_THRESHOLD = 0.85

    best = None
    best_score = 0.0

    for result in results:
        score = _title_similarity(scraped_title, result.get("title", ""))
        if score > best_score:
            best_score = score
            best = result

    if best and best_score >= SIMILARITY_THRESHOLD:
        return best

    return None
```

**Why 0.85?** Titles may have minor differences (e.g., capitalization of special terms, Unicode characters). 0.85 allows small variations while avoiding false matches.

---

## Semantic Scholar API Details

### Base URL

```
https://api.semanticscholar.org/graph/v1
```

### Authentication

Optional but recommended. With an API key, rate limits increase from 1 req/sec to 100 req/sec:

```python
def _get_headers(config: AppConfig) -> dict:
    headers = {"Accept": "application/json"}
    api_key = config.secrets.semantic_scholar_api_key
    if api_key:
        headers["x-api-key"] = api_key
    return headers
```

### Fields Requested

```
paperId,title,authors,abstract,venue,year,publicationDate,externalIds,citationCount,url
```

The `authors` field returns a list of objects: `[{"authorId": "...", "name": "Alice Smith"}, ...]`. We extract just the names.

### Response Parsing

```python
def _parse_s2_response(data: dict, raw: RawPaper) -> ResolvedPaper:
    """Convert Semantic Scholar API response into a ResolvedPaper."""
    authors = [a["name"] for a in data.get("authors", [])]
    external_ids = data.get("externalIds", {})

    return ResolvedPaper(
        semantic_scholar_id=data["paperId"],
        title=data.get("title", raw.title),
        authors=authors if authors else raw.authors,
        abstract=data.get("abstract") or raw.abstract,
        url=data.get("url", raw.scholar_inbox_url),
        arxiv_id=external_ids.get("ArXiv"),
        doi=external_ids.get("DOI"),
        venue=data.get("venue") or raw.venue,
        year=data.get("year") or raw.year,
        published_date=data.get("publicationDate"),
        citation_count=data.get("citationCount", 0),
        scholar_inbox_score=raw.score,
        scholar_inbox_url=raw.scholar_inbox_url,
    )
```

---

## Rate Limiting

Semantic Scholar enforces rate limits. The resolver respects them with a pre-request delay and configurable retry on 429/5xx:

```python
import asyncio
from src.retry import RetryConfig
from src.constants import DEFAULT_RETRY

# Without API key: 1 request per second
# With API key: 100 requests per second (use 10/sec to be safe)
RATE_LIMIT_DELAY_NO_KEY = 1.1  # seconds
RATE_LIMIT_DELAY_WITH_KEY = 0.1  # seconds

async def _rate_limited_request(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    has_api_key: bool,
    *,
    retry: RetryConfig = DEFAULT_RETRY,
) -> httpx.Response:
    """Make an API request with rate limiting and configurable retry.

    Retries on 429 and 5xx using the strategy defined by *retry*.
    For 429 the Retry-After header is used as a minimum wait time.
    """
    delay = RATE_LIMIT_DELAY_WITH_KEY if has_api_key else RATE_LIMIT_DELAY_NO_KEY
    await asyncio.sleep(delay)

    for attempt in range(retry.max_attempts):
        response = await client.get(url, headers=headers, timeout=30.0)
        if response.status_code == 429:
            wait = max(int(response.headers.get("Retry-After", "0")),
                       retry.delay(attempt))
            await asyncio.sleep(wait)
            continue
        if 500 <= response.status_code < 600:
            await asyncio.sleep(retry.delay(attempt))
            continue
        return response
    return response  # last error response
```

### RetryConfig

Retry behaviour is controlled by `RetryConfig` (see `src/retry.py`):

```python
RetryConfig(strategy="exponential")  # 2s, 4s, 8s, 16s … + jitter (default)
RetryConfig(strategy="fixed", base_delay=5.0)  # 5s, 5s, 5s …
```

---

## Fallback ID Generation

If Semantic Scholar cannot find a paper (API returns 404 or no match), generate a synthetic ID so the paper can still be tracked:

```python
def _generate_fallback_id(raw: RawPaper) -> str:
    """Generate a deterministic fallback ID for papers not found on S2.

    Priority:
    1. arxiv:{arxiv_id} — if arXiv ID is known
    2. title:{hash} — hash of normalized title (last resort)
    """
    if raw.arxiv_id:
        return f"arxiv:{raw.arxiv_id}"

    import hashlib
    title_hash = hashlib.sha256(
        _normalize_title(raw.title).encode()
    ).hexdigest()[:16]
    return f"title:{title_hash}"
```

Papers with synthetic IDs cannot be citation-polled via the S2 batch API. They remain in the database and are automatically re-resolved by the backfill process (see below).

---

## Re-Resolution of Dangling Papers

Papers stored with synthetic fallback IDs (`title:` or `si-` prefix) are considered "dangling" — they exist in the database but cannot participate in citation polling because:

- `title:{hash}` IDs are explicitly skipped by `_to_s2_id()` in the citation poller
- `si-{paper_id}` IDs (from backfill) are passed to S2 as-is but don't match any real S2 paper

### Module: `src/ingestion/reresolver.py`

The re-resolver finds these dangling papers and re-attempts Semantic Scholar resolution:

```python
@dataclass
class ReResolveResult:
    total_dangling: int = 0
    resolved: int = 0
    already_exists: int = 0
    still_unresolved: int = 0
    errors: list[str] = field(default_factory=list)


async def re_resolve_dangling(config: AppConfig) -> ReResolveResult:
    """Find and re-resolve papers with synthetic/fallback IDs.

    Steps:
    1. Query DB for papers with id LIKE 'title:%' OR id LIKE 'si-%'
       AND resolve_failures < MAX_RESOLVE_FAILURES (default 3)
    2. Reconstruct a RawPaper from the stored data (set semantic_scholar_id=None
       to force re-resolution)
    3. Call resolve_paper() to attempt S2 lookup via arXiv ID, DOI, or title search
    4. If resolved to a real S2 ID:
       a. Delete old row (ON DELETE CASCADE removes any snapshots)
       b. Insert new row with resolved ID and enriched metadata
       c. Reset resolve_failures to 0
    5. If the resolved ID already exists in the DB, delete the dangling duplicate
    6. On failure or unresolved: increment resolve_failures counter
    7. Papers that reach MAX_RESOLVE_FAILURES are skipped in future runs
       until the counter resets (next backfill cycle resets all counters)
    """
```

### Failure Tracking

Each dangling paper tracks a `resolve_failures` counter in the `papers` table:

- **On resolution failure** (exception, no S2 match, or returned another synthetic ID): increment `resolve_failures`
- **On success**: the old row is deleted and replaced, so the counter resets naturally
- **Max failures**: Papers with `resolve_failures >= MAX_RESOLVE_FAILURES` (default 3) are skipped by `get_dangling_papers()`. This prevents the re-resolver from repeatedly hitting the S2 API for papers that are genuinely not indexed.
- **Counter reset**: The `backfill` command resets all `resolve_failures` counters to 0 before running re-resolution, giving every paper a fresh set of attempts on each backfill cycle.

### Integration with Backfill

Re-resolution runs automatically at the end of every `run_backfill()` call. This means:

- Papers that failed S2 resolution due to temporary API outages (5xx and 4xx) get another chance on the next daily backfill
- Papers ingested via backfill with `si-` IDs get resolved to proper S2 IDs
- No manual intervention required — the daily script handles it
- Failure counters are reset at the start of each backfill, so papers get `MAX_RESOLVE_FAILURES` fresh attempts per backfill cycle

### ID Replacement Strategy

Since `id` is the primary key and `citation_snapshots` has `ON DELETE CASCADE`, replacement uses DELETE + INSERT within a single transaction. This is safe because dangling papers have no useful citation snapshots (they were never successfully polled).

If the newly resolved ID already exists in the database (the paper was independently ingested through another path), the dangling duplicate is simply deleted.

### CLI Command

```
scholar-curate re-resolve    # Re-attempt resolution for papers with fallback IDs
```

---

## Conversion to Database Format

```python
def paper_to_dict(paper: ResolvedPaper) -> dict:
    """Convert a ResolvedPaper dataclass to a dictionary for database storage.

    Parameters
    ----------
    paper : ResolvedPaper
        The resolved paper to convert

    Returns
    -------
    dict
        Dictionary with keys matching the papers table schema
    """
    import json
    from datetime import datetime, timezone

    return {
        "id": paper.semantic_scholar_id,
        "title": paper.title,
        "authors": json.dumps(paper.authors),
        "abstract": paper.abstract,
        "url": paper.url,
        "arxiv_id": paper.arxiv_id,
        "doi": paper.doi,
        "venue": paper.venue,
        "year": paper.year,
        "published_date": paper.published_date,
        "scholar_inbox_score": paper.scholar_inbox_score,
        "scholar_inbox_url": paper.scholar_inbox_url,
        "citation_count": paper.citation_count,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",
        "manual_status": 0,
    }
```

This function is used by the orchestration layer to convert resolved papers into the format expected by `upsert_paper()`.

---

## Batch Resolution Flow

```python
async def resolve_papers(
    client: httpx.AsyncClient,
    papers: list[RawPaper],
    config: AppConfig,
) -> list[ResolvedPaper]:
    """Resolve all scraped papers with progress logging.

    Optimized: papers that already have a semantic_scholar_id from Scholar
    Inbox are converted directly without an API call. Only papers missing
    their S2 ID go through the Semantic Scholar resolution pipeline.
    """
    resolved = []
    skipped = 0  # already had S2 ID
    failed = 0

    for i, raw in enumerate(papers):
        # Optimization: Scholar Inbox already provides semantic_scholar_id
        # for most papers — skip the S2 API call for these.
        if raw.semantic_scholar_id:
            resolved.append(_create_pre_resolved(raw))
            skipped += 1
            continue

        logger.info("Resolving paper %d/%d: %s", i + 1, len(papers), raw.title[:60])

        result = await resolve_paper(client, raw, config)

        if result:
            resolved.append(result)
        else:
            failed += 1
            logger.warning("Could not resolve: %s", raw.title[:80])
            # Create a ResolvedPaper with fallback ID
            fallback = _create_fallback_resolved(raw)
            resolved.append(fallback)

    logger.info(
        "Resolution complete: %d pre-resolved (from API), %d resolved via S2, "
        "%d used fallback IDs",
        skipped, len(resolved) - skipped - failed, failed
    )
    return resolved


def _create_pre_resolved(raw: RawPaper) -> ResolvedPaper:
    """Convert a RawPaper that already has a semantic_scholar_id into a ResolvedPaper.

    Used when Scholar Inbox provides the S2 ID directly, avoiding an API call.
    Citation count is not available at this stage and defaults to 0;
    it will be populated on the first citation poll.
    """
    return ResolvedPaper(
        semantic_scholar_id=raw.semantic_scholar_id,
        title=raw.title,
        authors=raw.authors,
        abstract=raw.abstract,
        url=raw.scholar_inbox_url,
        arxiv_id=raw.arxiv_id,
        doi=None,  # Will be enriched during citation polling via S2 batch API
        venue=raw.venue,
        year=raw.year,
        published_date=raw.publication_date,  # From Scholar Inbox epoch ms → ISO 8601
        citation_count=0,
        scholar_inbox_score=raw.score,
        scholar_inbox_url=raw.scholar_inbox_url,
        category=raw.category,
    )
```

---

## Error Handling

- **HTTP errors (429 / 5xx):** Retried using the configured `RetryConfig` strategy (default: exponential backoff with jitter, up to 5 attempts). If all attempts are exhausted, skip the paper and use a fallback ID.
- **Timeout:** Log and skip.
- **No results:** Use fallback ID.

All errors are logged but do not abort the full ingestion run — individual paper failures are tolerable.
