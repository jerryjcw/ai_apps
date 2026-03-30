# High-Level Design: AlphaRxiv Trendy Paper Analysis

## 1. Problem & Motivation

Discovering and analyzing trending AI research papers from alphaxiv.org is currently a manual, repetitive workflow: browse the trending page, copy raw content into Claude (cowork), iteratively parse paper lists, filter against research criteria, and perform literature reviews on selected papers. This application automates the full pipeline end-to-end.

## 2. System Overview

```
┌────────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────────┐
│  Scrape    │─▶│  Parse    │─▶│  Enrich   │─▶│  Analyze  │─▶│  Review   │─▶│  Plan         │
│(Playwright)│  │(Regex/LLM)│  │(arXiv API)│  │(Claude)   │  │(Claude)   │  │(Claude+Critic)│
└────────────┘  └───────────┘  └───────────┘  └───────────┘  └───────────┘  └───────────────┘
   Stage 0       Stage 1        Stage 1.5      Stage 2        Stage 3         Stage 4
 raw_input.txt   titles.md     enriched.json   filtered_*.md  lit_review_*.md experiment_plan_*.md
                 papers.json                filter_result.json
```

- **Stages 0–2** are fully automated (single `run` command)
- **Stage 3** requires user to select papers from filtered output, then runs automatically
- **Stage 4** requires user to select a proposal from Stage 3, then runs automatically (planning + adversarial critic review)

## 3. Data Sources

| Source               | Purpose                                      | Access Method                                                 |
| -------------------- | -------------------------------------------- | ------------------------------------------------------------- |
| alphaxiv.org         | Trending papers list                         | Playwright (React SPA, no login required, needs JS rendering) |
| arXiv API            | Full abstracts, metadata, arXiv IDs          | REST API via httpx (free, 1 req/sec)                          |
| Semantic Scholar API | Citation context for lit review grounding    | REST API via httpx (free, 100 req/sec)                        |
| Claude API           | Paper analysis, filtering, literature review | Anthropic Python SDK                                          |

### alphaxiv.org Specifics

- Trending page at `https://alphaxiv.org` or `/explore` — publicly accessible, **no login required**
- React SPA with server-side hydration — static HTTP fetch won't work, Playwright required
- Paper cards contain: title, date, authors, abstract excerpt, hashtags, engagement metrics (bookmarks, views)

#### Available Server-Side Filters

The alphaxiv UI exposes filtering controls (driven by React state, not URL params):

| Filter                | Examples                                                                              | Notes                                       |
| --------------------- | ------------------------------------------------------------------------------------- | ------------------------------------------- |
| **Sort**              | Hot (default), Likes                                                                  | `?sort=Hot` / `?sort=Likes` — works via URL |
| **Categories**        | computer-science, physics, math                                                       | May require UI interaction via Playwright   |
| **Subcategories**     | computation-and-language, machine-learning, computer-vision-and-pattern-recognition   | Nested under categories                     |
| **Custom categories** | agents, attention-mechanisms, generative-models, chain-of-thought, agentic-frameworks | Topic-level tags                            |
| **Organizations**     | Filter by affiliation                                                                 | UI-driven                                   |

**No time-range filter** exists — the feed shows the last few days of papers only.

#### Client-Side Filtering (Engagement Thresholds)

Since alphaxiv does not provide server-side min bookmark/view filters, the scraper applies **client-side filtering after extraction**: papers below the configured `min_bookmarks` or `min_views` thresholds are discarded before proceeding to the parse stage. This reduces noise from low-engagement papers early in the pipeline.

### Raw Data Format (from alphaxiv page)

Each paper entry in the rendered page follows this pattern:

```
{Title}{DD Mon YYYY}{Authors/Institutions}{Abstract}View blog#{tag1}#{tag2}...{numbers}BookmarkResources{bookmark_count}{view_count}
```

## 4. Pipeline Stages

### Stage 0: Scrape — `src/scraping/trending.py`

- Launch headless Chromium via Playwright
- Navigate to alphaxiv trending page with configured sort order and category filters
- If categories/subcategories are configured, interact with the filter UI controls via Playwright
- Wait for React hydration (paper card elements to appear)
- Extract full page text content
- **Apply engagement thresholds**: discard papers with `bookmark_count < min_bookmarks` or `view_count < min_views` (configured in `[scraping]`)
- Save to `data/runs/YYYY-MM-DD/raw_input.txt`
- Log: total papers found, papers after filtering, filters applied

### Stage 1: Parse — `src/parsing/raw_parser.py`

- Regex + state-machine parser extracts structured papers from raw text
- Key delimiters: date pattern (`DD Mon YYYY`), "View blog" literal, "BookmarkResources" marker
- **Fallback**: if regex finds < 3 papers (format changed), use an LLM call to parse
  - Enable **extended thinking** (`thinking` parameter with budget tokens) so the model reasons through the raw text structure before producing output
  - Prompt includes: the raw text, the expected `ParsedPaper` schema, and 2–3 few-shot examples of raw→structured mappings from known-good historical runs
  - Request structured JSON output; validate all required fields are present before accepting
- Output: `papers.json` (machine-readable) + `titles.md` (human-readable)
- Data model:
  ```
  ParsedPaper: index, title, date, authors_raw, abstract, hashtags,
               bookmark_count, view_count, arxiv_id (if extractable)
  ```

### Stage 1.5: Enrich — `src/enrichment/arxiv_api.py`

- For each paper, search arXiv API by title to get: full abstract, confirmed arXiv ID, categories, PDF URL
- Rate-limited to 1 req/sec (arXiv policy)
- Output: `enriched_papers.json`

### Stage 2: Analyze — `src/analysis/filter_analyzer.py`

This is the most critical LLM stage — it must replicate the depth and quality of an interactive cowork session where a researcher iterates with Claude on paper analysis.

#### LLM Call Strategy

**Phase A (1 LLM call) + Phase B (deterministic code):**

1. **Phase A — Deep Analysis (extended thinking enabled)**
   - Model: `claude-opus-4-6` (configurable via `model_analyze`)
   - Enable **extended thinking** with budget (`budget_tokens = 40000`, configurable in `[llm]`) so the model thoroughly reasons about each paper's contribution, novelty, and feasibility before committing to ratings
   - `max_tokens = 32000` to accommodate full output (12+ included papers with detailed fields + 48+ excluded papers)
   - Input: all enriched papers + full research criteria + user's compute/resource constraints
   - Uses **tool use** for structured JSON extraction (guaranteed valid schema)
   - The prompt must instruct the model to:
     - First read and internalize ALL papers before scoring any (avoid anchoring bias)
     - For each paper, reason through: what is the core technical contribution? Is it theoretical or engineering? How does it relate to the focus areas? What compute would reproduction require?
     - Only after reasoning, produce structured JSON with all analysis fields
   - Output: `filter_result.json` — structured analysis data
   - **Post-validation**: `validate_analysis_result()` checks all papers accounted for, rating distribution spans full range, exclusion reasons are specific, Top 5 is complete. Auto-retries with increased thinking budget on critical failures.

2. **Phase B — Deterministic Formatting (no LLM)**
   - Implemented as `render_analysis_markdown(filter_result, lang)` in `src/output/formatter.py`
   - Takes structured JSON from Phase A and renders into polished markdown using Python string templates
   - One call for Chinese (`filtered_zh.md`), one for English (`filtered_en.md`)
   - No LLM needed — this is a deterministic JSON-to-markdown transformation
   - Faster, cheaper, and more consistent than LLM rendering

#### Prompt Design Principles

- **System prompt** establishes the persona: senior AI researcher evaluating papers for a lab with specific compute constraints
- **Few-shot examples**: include 2–3 examples of high-quality paper analyses from historical cowork sessions (stored in `src/analysis/examples/`) so the model calibrates its depth and style
- **Explicit rubrics** for each rating dimension:
  - Importance (1–5 stars): 1 = incremental, 3 = solid contribution, 5 = paradigm-shifting
  - Conference probability: based on venue acceptance rates, paper novelty, and experimental rigor
  - Research directions: must be concrete enough to start a project, not generic suggestions
- **Anti-patterns to prevent**: surface-level summaries, generic research directions like "explore more datasets", ratings that cluster at 3–4 stars without differentiation

#### Analysis Fields Per Paper

| Field                      | Description                                                                        |
| -------------------------- | ---------------------------------------------------------------------------------- |
| arXiv ID                   | Confirmed ID from enrichment                                                       |
| Topic Category             | Specific sub-area (e.g., "RLHF / Alignment", not just "LLM")                       |
| Core Contribution          | 2–3 sentence technical summary of what's actually new                              |
| Importance                 | 1–5 stars with justification                                                       |
| Research Directions        | 4 sub-items (a–d), each a concrete actionable direction with feasibility note      |
| Compute Estimate           | GPU type × count × hours (e.g., "8×H200, ~48h")                                    |
| Data Estimate              | Dataset size/type needed for reproduction                                          |
| Datasets                   | Specific datasets used or applicable                                               |
| Top Conference Probability | Percentage + colored emoji (green >= 65%, yellow >= 50%, red < 50%) with reasoning |

#### Output Structure

- **Included papers**: full analysis table per paper
- **Excluded papers**: table with paper title + specific exclusion reason (not just "not relevant")
- **Top 5 summary**: ranked table of most promising papers with 1-line justification each

### Stage 3: Review — `src/analysis/lit_reviewer.py`

This stage produces the deepest analysis — a full literature review per selected paper, equivalent to a multi-turn cowork research session.

#### Workflow

1. User reads filtered output, selects papers via CLI (`--papers 1,3,5`)
2. For each selected paper: fetch full paper content via arXiv (HTML preferred, PDF fallback — see [02 — Enrichment](detailed_design/02_enrichment_and_database.md) for fetching details)
3. For each paper: fetch citation context from **Semantic Scholar API** (references + citations) for Turn 2 grounding
4. For each paper, run a **multi-turn LLM conversation in English** (not a single prompt):

#### Multi-Turn LLM Strategy (Per Paper)

Each paper gets its own conversation using **Opus** (`model_review`) with extended thinking enabled (**`budget_tokens = 16000` per turn**, so 3 turns × 16K = up to 48K thinking tokens per paper). The multi-turn context **preserves full response content blocks including thinking** (required by the Anthropic API for extended thinking conversations):

- **Turn 1 — Deep Read**: Provide the full paper content. Ask the model to thoroughly read and summarize: core contribution, methodology, key results, limitations, and open questions. Extended thinking lets the model reason through the paper before responding.
- **Turn 2 — Literature Landscape**: Provide **grounded citation data** from Semantic Scholar (real references and citing papers). Ask the model to map the related work landscape using these anchors, supplementing with its own knowledge. The model should reference specific papers and methods, not generic trends.
- **Turn 3 — Research Opportunities**: Given the user's compute constraints and focus areas (from `[criteria]`), ask for 2–3 concrete research proposals. Each proposal must include:
  - Problem statement (1–2 sentences)
  - Proposed approach with technical specifics
  - Required compute and data resources
  - Feasibility assessment (can this be done with the user's constraints?)
  - Expected impact and target venue
  - Key risks and mitigation strategies

#### Prompt Design Principles

- **System prompt**: senior AI researcher conducting a literature review for a lab planning its next project
- **Extended thinking** is critical here — the model needs to synthesize knowledge across its training data to identify genuine research gaps, not regurgitate paper abstracts
- **Specificity requirement**: prompts explicitly instruct "cite specific methods, papers, and datasets — do not give generic advice like 'explore more data augmentation techniques'"
- **Feasibility grounding**: every proposal must be evaluated against the configured compute/resource constraints, not in the abstract

#### Bilingual Strategy

Stage 3 runs entirely in **English** (the model's strongest language for research analysis). The Chinese version is produced by a single **translation LLM call** per paper using Sonnet (`model_translate`). This costs 4 API calls per paper (3 Opus turns + 1 Sonnet translation) instead of 6 (running the full conversation twice).

#### Output

- `literature_review_en.md` — full review in English (primary, generated by Opus)
- `literature_review_zh.md` — full review in Traditional Chinese (translated by Sonnet)
- Per paper sections: summary, landscape analysis, opportunity proposals with feasibility

### Stage 4: Experiment Planning — `src/planning/experiment_planner.py`

This stage transforms a research proposal from Stage 3 into a complete, actionable experiment plan. It uses an **Orchestrator + Adversarial Critic** architecture — the one multi-agent pattern that provides genuine quality improvement over single-agent planning.

See [06 — Experiment Planning](detailed_design/06_experiment_planning.md) for the full multi-agent architecture rationale and detailed design.

#### Architecture: Why Adversarial Critic?

Full multi-agent systems (AutoGen, CrewAI, LangGraph) were evaluated and rejected — the planning tasks are deeply interdependent, and splitting them across agents fragments the reasoning chain while duplicating context. However, a **separate critic agent** with a "find problems" persona genuinely improves quality because:
- The planning agent has confirmation bias toward its own plan
- An independent reviewer evaluates the plan as a peer reviewer would evaluate a paper
- This mirrors the actual research peer review process

#### Pipeline (Per Proposal)

1. **Parallel Research** (Semantic Scholar API, no LLM): Search for similar methods (novelty check), established baselines, and related work — all concurrently
2. **Planning Agent** (Opus, 3 turns with extended thinking):
   - Turn 1: Novelty assessment + novel approach synthesis (cross-pollinating ideas from ALL papers in the current run)
   - Turn 2: Minimum Viable Experiment + phased experiment plan
   - Turn 3: Ablation design + baseline selection + risk register + issue anticipation
3. **Adversarial Critic** (Opus, separate conversation): Stress-tests the draft plan — challenges novelty claims, timeline realism, baseline completeness, risk coverage
4. **Revision** (Opus, Turn 4 of planning conversation): Addresses each valid critique point
5. **Translation** (Sonnet): English → Traditional Chinese

**Total**: 5 Opus calls + 1 Sonnet call per proposal (~$6–7)

#### Output

- `experiment_plan_p{N}_r{M}_en.md` — English experiment plan
- `experiment_plan_p{N}_r{M}_zh.md` — Chinese experiment plan
- `experiment_plan_p{N}_r{M}.json` — Structured data

## 5. Research Criteria (Configurable)

Stored in `config.toml` under `[criteria]`:

| Criterion                  | Default                  | Description                                                            |
| -------------------------- | ------------------------ | ---------------------------------------------------------------------- |
| `max_compute_gpus`         | 16                       | Maximum GPU count (moderate compute)                                   |
| `gpu_model`                | "H200"                   | Target GPU model                                                       |
| `focus_areas`              | ["LLM", "Agent", ...]    | Must be related to these areas                                         |
| `require_theoretical`      | true                     | Must have theory/model/loss/training improvement, not pure engineering |
| `exclude_pure_engineering` | true                     | Exclude pure systems/framework papers                                  |
| `target_venues`            | ["ICLR", "NeurIPS", ...] | Target top conferences for feasibility assessment                      |

## 6. LLM Integration — `src/analysis/llm_client.py`

### Client Design

- Wrapper around `anthropic` Python SDK
- Supports both single-turn and multi-turn conversations (Stage 3 uses multi-turn)
- **Extended thinking** enabled for all analysis calls via the `thinking` parameter:
  - `thinking: { type: "enabled", budget_tokens: <configurable> }`
  - Budget tokens configurable per stage (parse fallback: 5000, analysis: 40000, review: 16000 per turn)
  - **Constraint**: `temperature` must be set to `1.0` when extended thinking is enabled (Anthropic API requirement)
- **Per-stage model selection**: Opus for reasoning-heavy stages (analysis, review), Sonnet for lightweight tasks (parse fallback, translation)
- **Tool use** for structured JSON extraction in Phase A (guaranteed valid JSON)
- **Prompt caching** via `cache_control` markers on system prompts
- Logs thinking content to `data/runs/YYYY-MM-DD/thinking_logs/` for debugging and quality review

### Configuration (`[llm]` in config.toml)

```toml
[llm]
model_analyze = "claude-opus-4-6"         # Stage 2 Phase A (deep analysis) — Opus for quality
model_review = "claude-opus-4-6"          # Stage 3 (literature review) — Opus for quality
model_parse = "claude-sonnet-4-6"         # Stage 1 parse fallback
model_translate = "claude-sonnet-4-6"     # Stage 3/4 translation to Chinese
model_plan = "claude-opus-4-6"           # Stage 4 planning agent
model_critic = "claude-opus-4-6"         # Stage 4 adversarial critic
max_tokens = 16000                        # default max output tokens
max_tokens_analyze = 32000                # Stage 2 Phase A (12 included + 48 excluded papers)
max_tokens_review = 16000                 # Stage 3 per-turn output
max_tokens_plan = 24000                   # Stage 4 per-turn output (Turn 3 has 4 dense sections)
temperature = 1.0                         # required when extended thinking is enabled
thinking_budget_parse = 5000              # thinking budget for parse fallback
thinking_budget_analyze = 40000           # thinking budget for Stage 2 analysis (~660 tokens/paper for 60 papers)
thinking_budget_review = 16000            # thinking budget for Stage 3 review (per turn, 3 turns per paper)
thinking_budget_plan = 24000              # thinking budget for Stage 4 planning (per turn, up to 4 turns)
thinking_budget_critic = 16000            # thinking budget for Stage 4 adversarial critic
```

### Prompt Templates — `src/analysis/prompts.py`

Python functions that build prompts dynamically:

| Function                                                      | Stage | Description                                                                                 |
| ------------------------------------------------------------- | ----- | ------------------------------------------------------------------------------------------- |
| `build_parse_fallback_prompt(raw_text)`                       | 1     | Includes raw text + schema + few-shot examples from `src/analysis/examples/`                |
| `build_filter_system_prompt(criteria)`                        | 2     | Establishes researcher persona + rating rubrics + anti-pattern warnings                     |
| `build_filter_analysis_prompt(papers)`                        | 2     | Paper data + explicit instruction to read all before scoring + output-only few-shot example |
| `build_review_system_prompt(criteria)`                        | 3     | Researcher persona + specificity requirements                                               |
| `build_review_read_prompt(paper_content)`                     | 3     | Turn 1: deep read and summarize                                                             |
| `build_review_landscape_prompt(citation_context)`             | 3     | Turn 2: map related work with grounded Semantic Scholar citations                           |
| `build_review_proposals_prompt(criteria)`                     | 3     | Turn 3: concrete proposals with feasibility                                                 |
| `build_review_translation_prompt(english_review)`             | 3     | Translate English review to Traditional Chinese                                             |
| `build_plan_system_prompt(criteria)`                          | 4     | Principal researcher persona for experiment planning                                        |
| `build_plan_novelty_prompt(proposal, s2_results, run_papers)` | 4     | Turn 1: novelty delta + novel approach synthesis                                            |
| `build_plan_experiment_prompt()`                              | 4     | Turn 2: MVE + phased experiment plan                                                        |
| `build_plan_details_prompt(baselines, criteria)`              | 4     | Turn 3: ablations + baselines + risks + issues                                              |
| `build_critic_system_prompt()`                                | 4     | Adversarial reviewer persona                                                                |
| `build_critic_prompt(draft_plan, criteria)`                   | 4     | Critic: stress-test the experiment plan                                                     |
| `build_revision_prompt(critique)`                             | 4     | Turn 4: revise plan based on critic feedback                                                |

### Few-Shot Examples — `src/analysis/examples/`

Store high-quality examples from historical cowork sessions to calibrate output quality:

| File                         | Used By        | Content                                                        |
| ---------------------------- | -------------- | -------------------------------------------------------------- |
| `example_filter_output.json` | Stage 2        | Expected analysis JSON (output only — no input example needed) |
| `example_review_turn1.md`    | Stage 3 Turn 1 | Sample deep read output (included per-turn, not all at once)   |
| `example_review_turn2.md`    | Stage 3 Turn 2 | Sample landscape analysis output                               |
| `example_review_turn3.md`    | Stage 3 Turn 3 | Sample research proposals output                               |

Sourced from reference cowork sessions at `/Users/jerry/Documents/cowork/alphaxiv/20260318/`. These are included in prompts so the model matches the expected depth and style.

## 7. Storage

### File-Based Output (Primary)

Each run produces a timestamped directory under `data/runs/YYYY-MM-DD/` with all intermediate and final artifacts:

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
├── literature_review.json           # Structured proposals (Stage 4 input)
├── experiment_plan_p3_r1_en.md      # Stage 4: paper 3, proposal 1
├── experiment_plan_p3_r1_zh.md
└── experiment_plan_p3_r1.json
```

### SQLite Trend Tracking (`src/db.py`)

Tracks papers across runs for trend analysis:

| Table        | Purpose                                                     |
| ------------ | ----------------------------------------------------------- |
| `runs`       | Run metadata (date, paper count, status)                    |
| `papers`     | Unique papers with first_seen, last_seen, times_seen        |
| `run_papers` | Many-to-many: which papers appeared in which run, with rank |

Enables: "papers trending 3+ days", "new entries this week", "consistently popular papers".

## 8. CLI Design

Entry point: `arxiv-trendy` (Click group)

| Command                       | Description                                      | Automation Level             |
| ----------------------------- | ------------------------------------------------ | ---------------------------- |
| `scrape`                      | Scrape alphaxiv trending page                    | Fully automated              |
| `parse --input <file>`        | Parse raw text into structured papers            | Fully automated              |
| `analyze [--input DIR]`       | Filter + analyze papers via LLM                  | Fully automated              |
| `review --papers 1,3,5`       | Literature review for selected papers            | User selects, then automated |
| `plan --paper 3 --proposal 1` | Experiment planning with adversarial critic      | User selects, then automated |
| `run`                         | Full pipeline: scrape + parse + enrich + analyze | Fully automated              |
| `history`                     | List past runs from DB                           | Read-only                    |
| `trending [--min-days N]`     | Show papers trending for N+ days across runs     | Read-only                    |

Daily automation via cron: a `scripts/daily_run.sh` wrapper runs `arxiv-trendy run` and logs output. See [05 — CLI & Orchestration](detailed_design/05_cli_and_orchestration.md) for the cron entry.

## 9. Configuration

### `config.toml`

Sections: `[database]`, `[output]`, `[llm]`, `[scraping]`, `[enrichment]`, `[criteria]`

Example `[scraping]` section:
```toml
[scraping]
sort = "Hot"                          # "Hot" or "Likes"
categories = ["computer-science"]     # top-level category filter (optional)
subcategories = []                    # e.g. ["machine-learning", "computation-and-language"]
custom_categories = []                # e.g. ["agents", "chain-of-thought"]
min_bookmarks = 0                     # discard papers with fewer bookmarks (0 = no filter)
min_views = 0                         # discard papers with fewer views (0 = no filter)
```

### `.env`

`ANTHROPIC_API_KEY` — Claude API key (required for analyze/review steps)

## 10. Module Structure

```
applications/alpharxiv_trendy_analysis/
├── pyproject.toml
├── config.toml
├── .env
├── data/
│   └── runs/
│       └── YYYY-MM-DD/
└── src/
    ├── cli.py                    # Click CLI entry point
    ├── config.py                 # Frozen dataclass config (TOML + .env)
    ├── constants.py              # URLs, defaults, patterns
    ├── errors.py                 # Exception hierarchy
    ├── db.py                     # SQLite trend tracking
    ├── scraping/
    │   └── trending.py           # Playwright scraper
    ├── parsing/
    │   └── raw_parser.py         # Regex parser + LLM fallback
    ├── analysis/
    │   ├── llm_client.py         # Anthropic SDK wrapper (tool use, prompt caching, multi-turn)
    │   ├── prompts.py            # Prompt templates (Stages 2-3)
    │   ├── validator.py          # Output validation with auto-retry
    │   ├── filter_analyzer.py    # Stage 2 pipeline
    │   └── lit_reviewer.py       # Stage 3 pipeline
    ├── planning/
    │   ├── experiment_planner.py # Stage 4 orchestrator (parallel research + plan + critic + revision)
    │   └── prompts.py            # Stage 4 prompt templates (planner + critic)
    ├── enrichment/
    │   ├── arxiv_api.py          # arXiv metadata fetcher (multi-strategy matching)
    │   └── semantic_scholar.py   # S2 API (citations for Stage 3, novelty/baseline search for Stage 4)
    └── output/
        └── formatter.py          # Deterministic markdown renderers (zh + en)
```

## 11. Key Dependencies

- `anthropic` — Claude API access
- `httpx` — arXiv API calls and paper content fetching
- `click` — CLI framework
- `python-dotenv` — Environment variable loading
- `playwright` — Browser automation for alphaxiv scraping
- `pdfplumber` (optional) — PDF text extraction for Stage 3, only needed if arXiv HTML is unavailable

No web UI for v1. No FastAPI. No complex scheduling — a simple cron script suffices.

Note: The Semantic Scholar API is free and requires no additional dependencies — it's accessed via `httpx` (already a dependency).

## 12. Cost Estimate Per Run

| Stage                                  | Model               | Input Tokens | Output Tokens | Thinking Tokens |   Est. Cost |
| -------------------------------------- | ------------------- | ------------ | ------------- | --------------- | ----------: |
| Stage 2 Phase A                        | Opus                | ~25,000      | ~15,000       | ~40,000         |      ~$1.50 |
| Stage 2 Phase B                        | N/A (deterministic) | —            | —             | —               |       $0.00 |
| Stage 3 Turn 1 (per paper)             | Opus                | ~21,000      | ~3,000        | ~16,000         |      ~$0.80 |
| Stage 3 Turn 2 (per paper)             | Opus                | ~25,000      | ~4,000        | ~16,000         |      ~$0.90 |
| Stage 3 Turn 3 (per paper)             | Opus                | ~30,000      | ~4,000        | ~16,000         |      ~$1.00 |
| Stage 3 Translation (per paper)        | Sonnet              | ~12,000      | ~10,000       | —               |      ~$0.10 |
| Stage 4 Planning Turn 1 (per proposal) | Opus                | ~30,000      | ~4,000        | ~24,000         |      ~$1.20 |
| Stage 4 Planning Turn 2 (per proposal) | Opus                | ~60,000      | ~5,000        | ~24,000         |      ~$2.10 |
| Stage 4 Planning Turn 3 (per proposal) | Opus                | ~100,000     | ~6,000        | ~24,000         |      ~$3.00 |
| Stage 4 Critic (per proposal)          | Opus                | ~26,000      | ~3,000        | ~16,000         |      ~$0.90 |
| Stage 4 Revision (per proposal)        | Opus                | ~135,000     | ~3,000        | ~16,000         |      ~$3.50 |
| Stage 4 Translation (per proposal)     | Sonnet              | ~15,000      | ~12,000       | —               |      ~$0.15 |
| **Total (run + 3 reviews + 1 plan)**   |                     |              |               |                 | **~$21–23** |

Note: Stage 4 planning turns accumulate thinking blocks in context (required by the Anthropic API for multi-turn extended thinking), which significantly increases input tokens for later turns.

With prompt caching enabled, subsequent runs with the same system prompts save ~90% on cached input tokens (~$0.50/run savings).

## 13. Output Format Reference

Outputs must match the quality and structure of the manual cowork workflow. Reference files:

- `/Users/jerry/Documents/cowork/alphaxiv/20260318/titles.md`
- `/Users/jerry/Documents/cowork/alphaxiv/20260318/filtered.md`

Key formatting requirements:

- Markdown tables with Chinese/English labels
- Star ratings (1–5)
- Colored probability emojis: green (>= 65%), yellow (>= 50%), red (< 50%)
- 4 research direction sub-items per paper
- Excluded papers section with reasons
- Top 5 summary table
