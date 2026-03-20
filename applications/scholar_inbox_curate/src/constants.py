"""Centralised constants for Scholar Inbox Curate."""

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

CURRENT_SCHEMA_VERSION = 5

# ---------------------------------------------------------------------------
# Re-resolution
# ---------------------------------------------------------------------------

MAX_RESOLVE_FAILURES = 3  # skip paper after this many consecutive failures

# ---------------------------------------------------------------------------
# Scholar Inbox API
# ---------------------------------------------------------------------------

SCHOLAR_INBOX_API_URL = "https://api.scholar-inbox.com"
COOKIES_FILENAME = "cookies.json"
DEFAULT_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Semantic Scholar API
# ---------------------------------------------------------------------------

S2_BASE_URL = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = (
    "paperId,title,authors,abstract,venue,year,"
    "publicationDate,externalIds,citationCount,url"
)
RATE_LIMIT_DELAY_NO_KEY = 1.1   # seconds – unauthenticated
RATE_LIMIT_DELAY_WITH_KEY = 1.0  # seconds – with API key

# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

SIMILARITY_THRESHOLD = 0.85

# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------

# Import here so consumers can do ``from src.constants import DEFAULT_RETRY``
from src.retry import RetryConfig  # noqa: E402

DEFAULT_RETRY = RetryConfig()  # exponential, 5 attempts, 2s base, 60s cap

# ---------------------------------------------------------------------------
# Semantic Scholar Batch API (Citation Polling)
# ---------------------------------------------------------------------------

S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_BATCH_FIELDS = "citationCount,externalIds"
S2_BATCH_DELAY_WITH_KEY = 1.0    # seconds between batch requests (with key)
S2_BATCH_DELAY_NO_KEY = 10.0     # seconds between batch requests (no key)

# ---------------------------------------------------------------------------
# OpenAlex API
# ---------------------------------------------------------------------------

OPENALEX_BASE_URL = "https://api.openalex.org"
OPENALEX_RATE_DELAY = 0.5  # seconds – polite pool allows ~2 req/sec

# ---------------------------------------------------------------------------
# Citation Velocity
# ---------------------------------------------------------------------------

VELOCITY_MIN_DAYS = 7  # minimum days of data before computing velocity
