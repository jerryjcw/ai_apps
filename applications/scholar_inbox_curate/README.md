# Scholar Inbox Curate

A Python-based paper curation system that monitors Scholar Inbox recommendations, tracks citation metrics, and maintains a database of papers with intelligent pruning and promotion rules.

## Quick Start

### Installation

```bash
cd applications/scholar_inbox_curate
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

### Configuration

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Add your Scholar Inbox credentials:
```bash
SCHOLAR_INBOX_EMAIL=your-email@example.com
SCHOLAR_INBOX_PASSWORD=your-password
SEMANTIC_SCHOLAR_API_KEY=your-api-key  # Optional for detailed citation data
```

3. Review `config.toml` and adjust settings as needed:
```toml
[ingestion]
score_threshold = 0.60  # 0.0-1.0 decimal scale (60th percentile papers)
backfill_score_threshold = 0.60
backfill_lookback_days = 30

[citations]
semantic_scholar_batch_size = 100

[pruning]
min_age_months = 6
min_citations = 10
min_velocity = 1.0

[promotion]
citation_threshold = 50
velocity_threshold = 10.0
```

### Running the CLI

```bash
# Ingest today's recommendations
scholar-curate ingest

# Get citation counts for papers
scholar-curate get-citations

# Update paper statuses (prune/promote)
scholar-curate update-status

# Backfill papers from past dates
scholar-curate backfill --from 2026-02-01 --to 2026-02-27

# Launch headed browser for manual login
scholar-curate login

# Reset session (delete cookies + browser profile, re-authenticate)
scholar-curate reset-session --yes

# View statistics
scholar-curate stats
```

## Typical Workflows

### Workflow 1: Daily Paper Curation

Run this daily to keep your paper database fresh:

```bash
#!/bin/bash
# daily_update.sh

# 1. Ingest today's recommendations from Scholar Inbox
scholar-curate ingest
echo "✓ Ingested today's recommendations"

# 2. Get latest citation counts
scholar-curate get-citations
echo "✓ Updated citation counts"

# 3. Apply rules (prune old/unpopular papers, promote trending ones)
scholar-curate update-status
echo "✓ Applied pruning and promotion rules"

# 4. View dashboard
scholar-curate stats
```

**Frequency**: Daily (e.g., via cron: `0 9 * * * cd ~/ai_apps/applications/scholar_inbox_curate && ./daily_update.sh`)

### Workflow 2: Initial Backfill

When setting up for the first time, backfill historical data:

```bash
# Backfill last 30 days of papers
scholar-curate backfill --from 2026-01-27 --to 2026-02-27

# Then immediately get citations
scholar-curate get-citations

# Apply rules
scholar-curate update-status

# View what we loaded
scholar-curate stats
```

### Workflow 3: Catch Up After Break

If the system wasn't running for a few days:

```bash
# Find missing dates automatically
scholar-curate backfill --auto

# Or backfill specific date range
scholar-curate backfill --from 2026-02-15 --to 2026-02-27

# Update metrics
scholar-curate get-citations && scholar-curate update-status
```

### Workflow 4: Tuning Quality Thresholds

Experiment with different score thresholds:

```bash
# Temporarily ingest with higher threshold (top 25% papers)
SCHOLAR_CURATE_SCORE_THRESHOLD=0.75 scholar-curate ingest

# Or edit config.toml:
# [ingestion]
# score_threshold = 0.75
scholar-curate ingest

# Check the results
scholar-curate stats  # See how many papers ingested
```

## Configuration Examples

### Conservative Setup (High Quality Papers Only)

```toml
[ingestion]
score_threshold = 0.75        # Top 25% from Scholar Inbox
backfill_score_threshold = 0.75
backfill_lookback_days = 60

[pruning]
min_age_months = 12           # Let papers age longer
min_citations = 25            # Higher citation requirement
min_velocity = 2.0            # Faster citation growth

[promotion]
citation_threshold = 100      # Need significant citations
velocity_threshold = 20.0     # High citation velocity
```

### Exploratory Setup (Catch Emerging Papers)

```toml
[ingestion]
score_threshold = 0.40        # Broader net (60% of papers)
backfill_score_threshold = 0.40

[pruning]
min_age_months = 3            # Prune faster
min_citations = 5             # Lower threshold
min_velocity = 0.5            # Pick up trending papers

[promotion]
citation_threshold = 20       # Promote earlier
velocity_threshold = 5.0      # Fast-growing papers
```

### Balanced Setup (Default)

```toml
[ingestion]
score_threshold = 0.60        # Medium threshold
backfill_score_threshold = 0.60

[pruning]
min_age_months = 6
min_citations = 10
min_velocity = 1.0

[promotion]
citation_threshold = 50
velocity_threshold = 10.0
```

## Configuration Details

### Score Threshold (IMPORTANT - Breaking Change in v1.1)

**The score threshold format changed from integer to decimal in v1.1.**

- **Old format** (v1.0 and earlier): `score_threshold = 60` (integer on 0-100 scale)
- **New format** (v1.1+): `score_threshold = 0.60` (decimal on 0.0-1.0 scale)

This change was necessary because the Scholar Inbox API returns scores on a 0.0-1.0 decimal scale. Using the old integer format would result in **all papers being filtered out** (e.g., 0.85 < 60 is always true).

**If you're upgrading from v1.0**, you must update your `config.toml`:
```toml
# Convert score thresholds to decimal format
# Divide the old value by 100:
# Old: 60 → New: 0.60
# Old: 75 → New: 0.75
# Old: 40 → New: 0.40

score_threshold = 0.60          # Updated from 60
backfill_score_threshold = 0.60 # Updated from 60
```

### Citation and Promotion Settings

- **min_age_months**: Minimum months before a paper can be promoted (prevents premature promotion)
- **min_citations**: Minimum citations required for promotion
- **min_velocity**: Minimum velocity score required for promotion
- **citation_threshold**: Citations above this trigger promotion eligibility
- **velocity_threshold**: Velocity score above this triggers promotion eligibility

## Database

The application uses SQLite with WAL mode for better concurrency. Database location is configurable via the `database.path` setting in `config.toml`.

### Schema Versioning

The database uses SQLite's `PRAGMA user_version` for schema management. Current schema version: **3**

**Migrations** are applied automatically on startup:
- **V1→V2**: Adds `scraped_dates` table (for backfill gap detection) and `digest_date` column in `papers`
- **V2→V3**: Adds `doi` column to `papers` table

## Development

### Running Tests

```bash
# All tests
pytest tests/ -v

# Tests for specific component
pytest tests/scholar_inbox_curate/test_critical_fixes.py -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

### Project Structure

```
src/
├── config.py              # Configuration management
├── constants.py           # Application constants
├── db.py                  # Database operations
├── cli.py                 # CLI commands
├── errors.py              # Exception hierarchy
├── ingestion/
│   ├── scraper.py         # Scholar Inbox scraping
│   ├── resolver.py        # Paper metadata resolution
│   ├── backfill.py        # Historical date backfill
│   └── orchestrate.py     # Ingestion pipeline orchestration
├── citations/
│   ├── poller.py          # Citation polling orchestration
│   ├── retriever.py       # Citation metrics
│   └── snapshot.py        # Citation history snapshots
├── rules/
│   ├── pruning.py         # Paper pruning logic
│   └── promotion.py       # Paper promotion logic
└── web/
    └── app.py             # FastAPI web interface

tests/
├── conftest.py            # Pytest fixtures
└── scholar_inbox_curate/
    ├── test_critical_fixes.py
    └── <component>/
        └── test_<module>.py
```

## Advanced Usage

### Understanding Score Thresholds

Scholar Inbox's ranking algorithm scores papers on a **0.0-1.0 decimal scale**:
- **1.0** = Perfect match for your interests
- **0.75** = Very relevant papers (top 25%)
- **0.60** = Good papers (top 40%)
- **0.50** = Medium relevance (top 50%)
- **0.25** = Low relevance

```bash
# Example: Only ingest top 10% of papers
# In config.toml:
score_threshold = 0.90

# This means: "Only papers scoring 0.90 or higher"
# Much fewer papers, but higher quality
```

### Understanding Status Transitions

Papers follow this lifecycle:

```
Ingested (active)
    ↓
    ├→ Promoted (important discovery)
    │   └→ Archived (no longer relevant)
    │
    └→ Pruned (old, few citations)
```

Status rules (in `config.toml`):
- **Pruning**: `min_age_months` + `min_citations` + `min_velocity`
- **Promotion**: `citation_threshold` OR `velocity_threshold`

### Monitoring and Debugging

```bash
# Check database stats
scholar-curate stats

# Export papers with their status
sqlite3 data/scholar_curate.db "SELECT title, status, citation_count FROM papers LIMIT 10;"

# Find papers that are about to be pruned
sqlite3 data/scholar_curate.db "SELECT title, ingested_at, citation_count FROM papers WHERE status='active' ORDER BY ingested_at LIMIT 5;"

# Check last ingestion run
sqlite3 data/scholar_curate.db "SELECT * FROM ingestion_runs ORDER BY id DESC LIMIT 1;"

# View scraping history
sqlite3 data/scholar_curate.db "SELECT date, papers_found FROM scraped_dates ORDER BY date DESC LIMIT 10;"
```

### Automated Scheduling

Set up cron jobs for regular updates:

```bash
# Edit crontab
crontab -e

# Add these lines:
0 9 * * * cd ~/ai_apps/applications/scholar_inbox_curate && scholar-curate ingest 2>&1 | mail -s "Curate: Ingest" you@example.com
0 10 * * * cd ~/ai_apps/applications/scholar_inbox_curate && scholar-curate get-citations 2>&1
0 11 * * * cd ~/ai_apps/applications/scholar_inbox_curate && scholar-curate update-status 2>&1

# Weekly backfill check (Sunday)
0 12 * * 0 cd ~/ai_apps/applications/scholar_inbox_curate && scholar-curate backfill --auto 2>&1
```

## Known Issues & Troubleshooting

### "All papers filtered out"
- **Cause**: Old integer format in config (score_threshold = 60)
- **Solution**: Update to decimal format (score_threshold = 0.60)

### "Cloudflare challenge timed out"
- **Cause**: Scholar Inbox authentication failed
- **Solution**:
  ```bash
  scholar-curate login           # Re-authenticate via headed browser
  scholar-curate ingest
  # Or nuclear option:
  scholar-curate reset-session --yes  # Deletes cookies + profile, then re-auth
  ```

### "No papers found"
- **Check 1**: Verify Scholar Inbox credentials in `.env`
- **Check 2**: Ensure `score_threshold` is in correct decimal format (0.0-1.0)
- **Check 3**: Check if today's digest has papers above your threshold

## Testing Credentials

For development/testing (please don't commit real credentials):
- **Email**: jerryjcw@gmail.com
- **Password**: See CLAUDE.md in project root

## License

Internal project - see repository for licensing details.
