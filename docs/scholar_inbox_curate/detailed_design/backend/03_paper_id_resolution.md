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
    url: str
    arxiv_id: str | None
    doi: str | None
    venue: str | None
    year: int | None
    published_date: str | None  # ISO 8601
    citation_count: int         # Initial citation count from S2
    scholar_inbox_score: float
    scholar_inbox_url: str


async def resolve_paper(client: httpx.AsyncClient, raw: RawPaper) -> ResolvedPaper | None:
    """Resolve a single RawPaper to a ResolvedPaper via Semantic Scholar.

    Returns None if the paper cannot be found on Semantic Scholar.
    """

async def resolve_papers(
    client: httpx.AsyncClient,
    papers: list[RawPaper],
    batch_size: int = 10,
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

Semantic Scholar enforces rate limits. The resolver respects them:

```python
import asyncio

# Without API key: 1 request per second
# With API key: 100 requests per second (use 10/sec to be safe)
RATE_LIMIT_DELAY_NO_KEY = 1.1  # seconds
RATE_LIMIT_DELAY_WITH_KEY = 0.1  # seconds

async def _rate_limited_request(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    has_api_key: bool,
) -> httpx.Response:
    """Make an API request with rate limiting."""
    delay = RATE_LIMIT_DELAY_WITH_KEY if has_api_key else RATE_LIMIT_DELAY_NO_KEY
    await asyncio.sleep(delay)

    response = await client.get(url, headers=headers, timeout=30.0)

    if response.status_code == 429:
        # Rate limited — back off and retry once
        retry_after = int(response.headers.get("Retry-After", "5"))
        logger.warning("Rate limited by Semantic Scholar, retrying in %ds", retry_after)
        await asyncio.sleep(retry_after)
        response = await client.get(url, headers=headers, timeout=30.0)

    return response
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

Papers with synthetic IDs will have limited citation tracking (only OpenAlex by title search), but they remain in the database and can be re-resolved later if Semantic Scholar indexes them.

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
    batch_size: int = 10,
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

        result = await resolve_paper(client, raw)

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
        published_date=None,  # Will be enriched during citation polling
        citation_count=0,
        scholar_inbox_score=raw.score,
        scholar_inbox_url=raw.scholar_inbox_url,
    )
```

---

## Error Handling

- **HTTP errors (5xx):** Log and retry once after 5 seconds. If still failing, skip the paper.
- **Timeout:** Log and skip.
- **No results:** Use fallback ID.
- **Rate limit (429):** Wait and retry as described above.

All errors are logged but do not abort the full ingestion run — individual paper failures are tolerable.
