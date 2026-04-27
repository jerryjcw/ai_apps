# Changelog

All notable changes to Scholar Inbox Curate will be documented in this file.

## [Unreleased]

### Added

- **Stats tab** (`/stats`) — new top-level page showing:
  - Oldest and newest paper by publication date, plus the ingestion tracking window.
  - Last-poll freshness distribution (never polled / <1w / 1–2w / 2–4w / 4–8w / 8+w) with a headline "X of Y papers haven't been polled in the past week" indicator.
  - Papers ingested per month (last 12 months) as a bar chart.
  - Citation updates per week (last 26 ISO weeks) as a filled line chart.
- `src/web/routes/stats.py`, `templates/stats.html`, and stats-specific CSS.
- Four new db helpers in `src/db.py`: `get_paper_date_range`, `get_poll_staleness_buckets`, `get_monthly_ingest_counts`, `get_weekly_citation_updates`.
- 24 new tests in `tests/scholar_inbox_curate/web/test_stats.py`.
- `scripts/merge_old_db.py` — one-shot tool to merge an older `scholar_curate.db` into the current one (papers not in local are inserted; for overlapping papers, old citation snapshots are merged and the local row is replaced only when its `citation_count` is NULL/0).
- Design doc `docs/scholar_inbox_curate/detailed_design/frontend/08_stats_page.md`.

### Changed

- Base-template nav now includes a Stats entry between Papers and Settings.
- Chart.js CDN usage expanded — loaded on both paper detail and stats pages via `extra_scripts`.

## [1.2.0] - 2026-02-27

### Added

- `doi` column to papers database table (schema V2→V3 migration, auto-applied)
- `login` CLI command — launches headed browser for manual Scholar Inbox authentication
- `POST /partials/trigger-rules` web endpoint — runs prune/promote rules via the web UI
- Conditional paper resolution — papers with pre-existing `semantic_scholar_id` from Scholar Inbox skip the Semantic Scholar API lookup, reducing API calls significantly
- New tests: V2→V3 migration, doi column, pre-resolved paper handling, login CLI, trigger-rules endpoint (379 total tests passing)

### Changed

- Schema version: 2 → 3
- `backfill --threshold` CLI option: `int` → `float` type (matches 0.0-1.0 config scale)
- `reset-session` command now deletes cookies file and browser profile directory before re-auth
- `scrape_date` log message fixed for float threshold display

### Fixed

- `scrape_date` log format used `%d%%` which would fail with float threshold values — changed to `%.0f%%` with `score_threshold * 100`

### Documentation

- All 8 backend design documents updated for consistency (score thresholds, doi column, resolver optimization, login command, error handling, frontend routes)
- README updated with login command, schema V3 info, project structure
- CHANGELOG updated

---

## [1.1.0] - 2026-02-27

### ⚠️ BREAKING CHANGES

**Configuration Format Update Required**

Score threshold settings now use a **decimal format (0.0-1.0)** instead of integer format (0-100).

**Migration Required**: All existing `config.toml` files must be updated before running v1.1+

```toml
# OLD FORMAT (v1.0 and earlier) - NO LONGER WORKS
score_threshold = 60
backfill_score_threshold = 60

# NEW FORMAT (v1.1+) - REQUIRED
score_threshold = 0.60
backfill_score_threshold = 0.60
```

**Why this change?**
The Scholar Inbox API returns scores on a 0.0-1.0 decimal scale. The old integer format (0-100) was incompatible and would result in **all papers being filtered out** (e.g., comparing 0.85 < 60 is always true).

### Added

- ✨ **paper_to_dict()** function in resolver module for standardized paper conversion
- ✨ **Backfill date recording** in ingestion orchestration for proper audit trails
- ✨ Comprehensive test suite (`test_critical_fixes.py`) with 11 tests covering:
  - Score threshold conversion (decimal scale validation)
  - paper_to_dict() function behavior
  - Configuration validation
  - TOML decimal format parsing
- 📄 README.md with complete documentation and troubleshooting guide
- 📄 CHANGELOG.md (this file)

### Fixed

- 🔴 **CRITICAL**: Score threshold conversion bug
  - **Issue**: API returns 0.0-1.0 decimal scores but code compared against 0-100 integer thresholds, filtering all papers
  - **Fix**: Changed configuration system to use 0.0-1.0 decimal scale consistently throughout
  - **Files**: config.py, scraper.py, config.toml, design docs

- 🔴 **CRITICAL**: Missing paper_to_dict() function
  - **Issue**: Design doc referenced undefined function, breaking paper storage
  - **Fix**: Implemented complete function with proper field mappings and type conversion
  - **Files**: resolver.py, design docs

- 🔴 **CRITICAL**: Incomplete backfill audit trail
  - **Issue**: Regular ingestion didn't record scraped dates, preventing backfill gap detection
  - **Fix**: Added date recording to ingestion orchestration
  - **Files**: orchestrate.py, design docs

- 🔴 **CRITICAL**: Schema version inconsistency
  - **Issue**: Documentation stated version=1 but V2 migration existed
  - **Fix**: Updated schema version constant to 2 (current state)
  - **Files**: Design docs

### Changed

- ✏️ Configuration validation: Changed score threshold range from 0-100 to 0.0-1.0
- ✏️ Scraper: Updated to use decimal thresholds directly (removed 100x division)
- ✏️ Logging: Fixed percentage display to work with decimal scale (0.60 * 100 = 60%)
- ✏️ Database recording: Enhanced _resolved_to_db_dict() with all required fields

### Technical Details

- **Score Threshold Type**: `int` → `float`
- **Decimal Range**: 0.0 to 1.0 (previously 0 to 100)
- **Default Score Threshold**: 0.60 (60th percentile)
- **Default Backfill Score Threshold**: 0.60
- **Database Migration**: No schema migration needed, format change only
- **API Compatibility**: No breaking API changes (addition-only for new functions)

### Testing

- ✅ 11/11 new tests passing
- ✅ Score conversion validation
- ✅ Configuration range validation
- ✅ TOML parsing of decimal format
- ✅ paper_to_dict() field conversion
- ✅ Timestamp inclusion verification

### Migration Guide

If you're upgrading from v1.0:

1. **Update config.toml** (required):
   ```bash
   # Find and replace in config.toml:
   # score_threshold = 60     →  score_threshold = 0.60
   # score_threshold = 75     →  score_threshold = 0.75
   # (Divide old values by 100 and use as decimals)
   ```

2. **No database migration needed**
   - Existing SQLite databases are compatible
   - V1→V2 migrations still apply for old databases

3. **Restart the application**
   ```bash
   scholar-curate reset-session  # Optional, re-authenticates
   scholar-curate ingest         # Run first ingestion with new config
   ```

### Documentation Updates

- 📚 Added comprehensive README.md with quick start guide
- 📚 Design documents updated (docs/scholar_inbox_curate/detailed_design/backend/)
- 📚 Configuration examples updated to show decimal format
- 📚 Troubleshooting section added for common issues

---

## [1.0.0] - 2026-02-15

### Initial Release

- ✅ Basic Scholar Inbox paper scraping
- ✅ Paper metadata resolution via Semantic Scholar
- ✅ SQLite database with citation tracking
- ✅ Paper pruning rules (age, citations, velocity)
- ✅ Paper promotion rules
- ✅ CLI with core commands (ingest, get-citations, update-status, backfill)
- ✅ Comprehensive design documentation (9 design documents)

---

## Version Format

This project follows [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes (configuration format, API changes)
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes and improvements

---

## How to Upgrade

See the Migration Guide section under each version for specific upgrade instructions.
