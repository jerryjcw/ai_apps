"""Centralised constants for Scholar Inbox Curate."""

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

CURRENT_SCHEMA_VERSION = 4

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
RATE_LIMIT_DELAY_WITH_KEY = 0.1  # seconds – with API key

# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

SIMILARITY_THRESHOLD = 0.85

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
