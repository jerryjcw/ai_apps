# 02 — Enrichment & Database

## Overview

Stage 1.5 (enrich) fetches full metadata from the arXiv API for each parsed paper. The database layer tracks papers across runs for trend analysis.

---

## Module: `src/enrichment/arxiv_api.py`

### Public Interface

```python
@dataclass
class EnrichedPaper:
    """A paper with full metadata from arXiv."""
    # Carried from ParsedPaper
    index: int
    title: str
    date: str
    authors_raw: str
    abstract: str                # may be updated with full arXiv abstract
    hashtags: list[str]
    bookmark_count: int
    view_count: int

    # Added by enrichment
    arxiv_id: str | None = None
    arxiv_title: str | None = None        # canonical title from arXiv
    arxiv_abstract: str | None = None     # full abstract from arXiv
    arxiv_authors: list[str] | None = None
    arxiv_categories: list[str] | None = None  # e.g. ["cs.CL", "cs.AI"]
    arxiv_pdf_url: str | None = None
    arxiv_published: str | None = None    # ISO date
    enrichment_status: str = "pending"    # "success", "not_found", "error"


async def enrich_papers(
    papers: list[ParsedPaper],
    config: AppConfig,
) -> list[EnrichedPaper]:
    """Enrich all papers with arXiv metadata.

    Rate-limited to 1 request/second per arXiv API policy.
    Papers that can't be found on arXiv retain their original data
    with enrichment_status = "not_found".
    """
```

### arXiv API Search

```python
import httpx
import xml.etree.ElementTree as ET
import asyncio

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}

async def _search_arxiv(
    title: str,
    arxiv_id_hint: str | None,
    client: httpx.AsyncClient,
) -> dict | None:
    """Search arXiv API with multi-strategy matching.

    Strategy (in order):
    1. If arxiv_id_hint is available (extracted from alphaxiv page URL/links),
       fetch directly by ID — most reliable.
    2. Try exact title search: ti:"{title}".
    3. Try simplified title search: remove special characters, lowercase.
    4. For each result, compute fuzzy match score against the original title
       and accept only if similarity > 0.85.

    Returns dict with: arxiv_id, title, abstract, authors, categories,
    pdf_url, published. Returns None if no match found.
    """
    # Strategy 1: Direct ID lookup if available
    if arxiv_id_hint:
        resp = await client.get(ARXIV_API_URL, params={
            "id_list": arxiv_id_hint, "max_results": 1,
        })
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            entries = root.findall("atom:entry", ARXIV_NS)
            if entries and entries[0].find("atom:title", ARXIV_NS) is not None:
                return _parse_entry(entries[0])

    # Strategy 2: Exact title search
    result = await _title_search(title, client)
    if result and _fuzzy_title_match(title, result["title"]) > 0.85:
        return result

    # Strategy 3: Simplified title search
    simplified = re.sub(r"[^\w\s]", "", title).lower()
    result = await _title_search(simplified, client)
    if result and _fuzzy_title_match(title, result["title"]) > 0.85:
        return result

    return None


async def _title_search(title: str, client: httpx.AsyncClient) -> dict | None:
    """Search arXiv by title string."""
    query = f'ti:"{title}"'
    params = {"search_query": query, "start": 0, "max_results": 3}
    resp = await client.get(ARXIV_API_URL, params=params)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    entries = root.findall("atom:entry", ARXIV_NS)
    return _parse_entry(entries[0]) if entries else None


def _fuzzy_title_match(title_a: str, title_b: str) -> float:
    """Compute normalized similarity between two titles.

    Uses simple token overlap (Jaccard similarity on lowercased words).
    Returns float 0.0–1.0.
    """
    words_a = set(title_a.lower().split())
    words_b = set(title_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _parse_entry(entry: ET.Element) -> dict:
    """Parse a single arXiv Atom entry into a dict."""
    arxiv_id = entry.find("atom:id", ARXIV_NS).text.split("/abs/")[-1]
    title = entry.find("atom:title", ARXIV_NS).text.strip().replace("\n", " ")
    abstract = entry.find("atom:summary", ARXIV_NS).text.strip()
    authors = [
        a.find("atom:name", ARXIV_NS).text
        for a in entry.findall("atom:author", ARXIV_NS)
    ]
    categories = [
        c.get("term")
        for c in entry.findall("atom:category", ARXIV_NS)
    ]
    pdf_url = None
    for link in entry.findall("atom:link", ARXIV_NS):
        if link.get("title") == "pdf":
            pdf_url = link.get("href")
    published = entry.find("atom:published", ARXIV_NS).text

    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "categories": categories,
        "pdf_url": pdf_url,
        "published": published,
    }
```

### Rate Limiting

```python
async def enrich_papers(papers, config):
    enriched = []
    async with httpx.AsyncClient(timeout=config.enrichment.timeout_seconds) as client:
        for paper in papers:
            result = await _search_arxiv(paper.title, paper.arxiv_id, client)
            if result:
                enriched.append(EnrichedPaper(
                    **_carry_fields(paper),
                    arxiv_id=result["arxiv_id"],
                    arxiv_abstract=result["abstract"],
                    arxiv_authors=result["authors"],
                    arxiv_categories=result["categories"],
                    arxiv_pdf_url=result["pdf_url"],
                    arxiv_published=result["published"],
                    enrichment_status="success",
                ))
            else:
                enriched.append(EnrichedPaper(
                    **_carry_fields(paper),
                    enrichment_status="not_found",
                ))
            # arXiv rate limit: 1 req/sec
            await asyncio.sleep(config.enrichment.rate_limit_seconds)
    return enriched
```

### Output: `enriched_papers.json`

Full JSON serialization of all `EnrichedPaper` objects, including enrichment status.

---

## Semantic Scholar Citation Fetching (Stage 3 Turn 2 Grounding)

Stage 3 Turn 2 (Literature Landscape) requires citing specific papers, methods, and research groups. To prevent hallucinated citations, we fetch real citation data from the Semantic Scholar API before Turn 2.

### API: Semantic Scholar (free, 100 req/sec)

```python
S2_API_BASE = "https://api.semanticscholar.org/graph/v1"

async def fetch_citation_context(
    arxiv_id: str,
    client: httpx.AsyncClient,
    max_references: int = 15,
    max_citations: int = 10,
) -> dict:
    """Fetch references and citations for a paper from Semantic Scholar.

    Args:
        arxiv_id: The arXiv ID of the paper.
        client: httpx async client.
        max_references: Max number of references to return.
        max_citations: Max number of citing papers to return.

    Returns:
        Dict with:
        - "references": list of {title, authors, year, venue, abstract} for papers this paper cites
        - "citations": list of {title, authors, year, venue, abstract} for papers citing this one
        - "related": list of related papers by topic similarity

    The Semantic Scholar API is free (100 req/sec, no auth required for basic access).
    An API key can be provided via S2_API_KEY env var for higher rate limits.
    """
    paper_id = f"ArXiv:{arxiv_id}"
    fields = "title,authors,year,venue,abstract"

    # Fetch references (papers this paper cites)
    refs_url = f"{S2_API_BASE}/paper/{paper_id}/references"
    refs_resp = await client.get(refs_url, params={"fields": fields, "limit": max_references})

    # Fetch citations (papers that cite this paper)
    cites_url = f"{S2_API_BASE}/paper/{paper_id}/citations"
    cites_resp = await client.get(cites_url, params={"fields": fields, "limit": max_citations})

    references = []
    if refs_resp.status_code == 200:
        for item in refs_resp.json().get("data", []):
            ref = item.get("citedPaper", {})
            if ref.get("title"):
                references.append({
                    "title": ref["title"],
                    "authors": [a["name"] for a in ref.get("authors", [])[:3]],
                    "year": ref.get("year"),
                    "venue": ref.get("venue", ""),
                    "abstract": (ref.get("abstract") or "")[:200],
                })

    citations = []
    if cites_resp.status_code == 200:
        for item in cites_resp.json().get("data", []):
            cite = item.get("citingPaper", {})
            if cite.get("title"):
                citations.append({
                    "title": cite["title"],
                    "authors": [a["name"] for a in cite.get("authors", [])[:3]],
                    "year": cite.get("year"),
                    "venue": cite.get("venue", ""),
                    "abstract": (cite.get("abstract") or "")[:200],
                })

    return {"references": references, "citations": citations}
```

### Integration with Stage 3 Turn 2

Before Turn 2, the pipeline:
1. Calls `fetch_citation_context(arxiv_id)` for the paper being reviewed
2. Formats the citation data as structured context
3. Prepends it to the Turn 2 prompt so the model has real citations to anchor its landscape analysis

This transforms Turn 2 from "hallucinate a landscape" to "analyze a real landscape with grounded citations."

### Dependency

Add `S2_API_KEY` (optional) to `.env` for higher rate limits. The API works without authentication at 100 req/sec.

---

## Paper Content Fetching (Stage 3)

Stage 3 (literature review) needs the full paper content, not just abstracts. This is fetched on-demand when the user selects papers for review.

### Strategy: HTML Preferred, PDF Fallback

```python
async def fetch_paper_content(
    arxiv_id: str,
    client: httpx.AsyncClient,
) -> str:
    """Fetch full paper content for literature review.

    Strategy:
    1. Try arXiv HTML version first (https://arxiv.org/html/{arxiv_id}).
       HTML is preferred because it's structured text — no PDF extraction needed.
    2. If HTML is not available (404), fall back to PDF:
       a. Download PDF from https://arxiv.org/pdf/{arxiv_id}.
       b. Extract text using pdfplumber.
    3. If both fail, fall back to the enriched abstract with a warning.

    Returns:
        Extracted paper text content.

    Raises:
        EnrichmentError: If all fetch methods fail.
    """
    # Try HTML first
    html_url = f"https://arxiv.org/html/{arxiv_id}"
    resp = await client.get(html_url, follow_redirects=True, timeout=30)
    if resp.status_code == 200:
        return _strip_html(resp.text)

    # Fall back to PDF
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    resp = await client.get(pdf_url, follow_redirects=True, timeout=60)
    if resp.status_code == 200:
        return _extract_pdf_text(resp.content)

    raise EnrichmentError(f"Could not fetch content for {arxiv_id}")


def _strip_html(html: str) -> str:
    """Extract main text content from arXiv HTML page.

    Strips navigation, headers, footers, and markup.
    Preserves section structure and math notation where possible.
    """
    from html.parser import HTMLParser
    # Implementation: extract text from <article> or <main> element,
    # strip tags, normalize whitespace.
    ...


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber.

    Note: pdfplumber is an optional dependency, only needed for Stage 3.
    """
    import pdfplumber
    import io
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    return "\n\n".join(text_parts)
```

### Dependency Note

`pdfplumber` is only required if arXiv HTML is unavailable. It should be listed as an optional dependency:

```toml
[project.optional-dependencies]
pdf = ["pdfplumber>=0.10"]
```

### Fallback Behavior

If paper content cannot be fetched (both HTML and PDF fail), the review falls back to using the enriched abstract. The review output will include a warning noting that only the abstract was available, which limits analysis depth.

---

## Module: `src/db.py`

### Schema

```sql
-- Run metadata
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,              -- YYYY-MM-DD
    paper_count INTEGER NOT NULL,
    filtered_count INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'started',  -- started, completed, failed
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Unique papers tracked across runs
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arxiv_id TEXT UNIQUE,                -- canonical ID (may be NULL)
    title TEXT NOT NULL,
    first_seen TEXT NOT NULL,            -- YYYY-MM-DD
    last_seen TEXT NOT NULL,             -- YYYY-MM-DD
    times_seen INTEGER NOT NULL DEFAULT 1,
    max_bookmarks INTEGER DEFAULT 0,
    max_views INTEGER DEFAULT 0
);

-- Many-to-many: which papers appeared in which run
CREATE TABLE IF NOT EXISTS run_papers (
    run_id INTEGER NOT NULL REFERENCES runs(id),
    paper_id INTEGER NOT NULL REFERENCES papers(id),
    rank INTEGER,                        -- position on trending page
    bookmark_count INTEGER DEFAULT 0,
    view_count INTEGER DEFAULT 0,
    PRIMARY KEY (run_id, paper_id)
);

PRAGMA user_version = 1;
```

### Public Interface

```python
import sqlite3
from pathlib import Path

def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize SQLite database with WAL mode and schema."""

def record_run(conn: sqlite3.Connection, run_date: str, paper_count: int) -> int:
    """Create a new run record. Returns run_id."""

def update_run_status(conn: sqlite3.Connection, run_id: int, status: str,
                       filtered_count: int = 0):
    """Update run status to 'completed' or 'failed'."""

def upsert_paper(conn: sqlite3.Connection, paper: EnrichedPaper,
                  run_date: str) -> int:
    """Insert or update a paper. Returns paper_id.

    On conflict (same arxiv_id or title match):
    - Update last_seen, increment times_seen
    - Update max_bookmarks/max_views if current values are higher
    """

def link_run_paper(conn: sqlite3.Connection, run_id: int, paper_id: int,
                    rank: int, bookmark_count: int, view_count: int):
    """Record which papers appeared in which run."""

def get_trending_papers(conn: sqlite3.Connection, min_days: int = 3) -> list[dict]:
    """Get papers that have been trending for at least min_days."""

def get_run_history(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    """Get recent runs with summary stats."""
```
