# 05 — CLI & Orchestration

## Overview

The CLI is the sole entry point. It orchestrates the pipeline stages and manages the run output directory.

---

## Module: `src/cli.py`

### Entry Point

```python
import click
import asyncio
from pathlib import Path
from datetime import date

@click.group()
@click.pass_context
def cli(ctx):
    """AlphaRxiv Trendy Paper Analysis."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config()
```

### Commands

#### `scrape` — Stage 0

```python
@cli.command()
@click.pass_context
def scrape(ctx):
    """Scrape alphaxiv trending page."""
    config = ctx.obj["config"]
    run_dir = _ensure_run_dir(config)

    raw_text = asyncio.run(scrape_trending(config))

    output_path = run_dir / RAW_INPUT_FILE
    output_path.write_text(raw_text, encoding="utf-8")
    click.echo(f"Saved raw text to {output_path} ({len(raw_text)} chars)")
```

#### `parse` — Stage 1

```python
@cli.command()
@click.option("--input", "input_file", type=click.Path(exists=True),
              help="Path to raw_input.txt. Defaults to today's run.")
@click.pass_context
def parse(ctx, input_file):
    """Parse raw text into structured papers."""
    config = ctx.obj["config"]
    run_dir = _ensure_run_dir(config)

    if input_file:
        raw_text = Path(input_file).read_text(encoding="utf-8")
    else:
        raw_text = (run_dir / RAW_INPUT_FILE).read_text(encoding="utf-8")

    try:
        papers = parse_raw_text(raw_text)
    except ParseError:
        click.echo("Regex parsing failed, using LLM fallback...")
        papers = asyncio.run(parse_with_llm_fallback(raw_text, config))

    # Apply engagement filters
    papers = filter_by_engagement(
        papers,
        min_bookmarks=config.scraping.min_bookmarks,
        min_views=config.scraping.min_views,
    )

    write_papers_json(papers, run_dir / PAPERS_JSON_FILE)
    write_titles_md(papers, date.today().isoformat(), run_dir / TITLES_MD_FILE)
    click.echo(f"Parsed {len(papers)} papers")
```

#### `analyze` — Stages 1.5 + 2

```python
@cli.command()
@click.option("--input", "input_dir", type=click.Path(exists=True),
              help="Path to run directory. Defaults to today's run.")
@click.pass_context
def analyze(ctx, input_dir):
    """Enrich papers and run LLM analysis."""
    config = ctx.obj["config"]
    run_dir = Path(input_dir) if input_dir else _get_run_dir(config)

    # Load parsed papers
    papers = _load_papers_json(run_dir / PAPERS_JSON_FILE)

    # Stage 1.5: Enrich
    click.echo(f"Enriching {len(papers)} papers via arXiv API...")
    enriched = asyncio.run(enrich_papers(papers, config))
    write_json(enriched, run_dir / ENRICHED_JSON_FILE)
    click.echo(f"Enriched: {sum(1 for p in enriched if p.enrichment_status == 'success')}/{len(enriched)} found on arXiv")

    # Stage 2: Analyze
    llm = LLMClient(config.llm, config.anthropic_api_key)
    click.echo("Running LLM analysis (this may take 1–2 minutes)...")
    result = asyncio.run(run_analysis(enriched, config, llm))

    # Save outputs
    write_json(result.filter_result, run_dir / FILTER_RESULT_FILE)
    (run_dir / FILTERED_ZH_FILE).write_text(result.filtered_zh, encoding="utf-8")
    (run_dir / FILTERED_EN_FILE).write_text(result.filtered_en, encoding="utf-8")

    # Save thinking log (Phase A only — Phase B is deterministic)
    save_thinking_log(result.thinking_log_analysis, "stage2_analysis", run_dir)

    # Report validation warnings
    if result.validation_warnings:
        click.echo("Validation warnings:")
        for w in result.validation_warnings:
            click.echo(f"  - {w}")

    n_included = len(result.filter_result["included_papers"])
    n_excluded = len(result.filter_result["excluded_papers"])
    click.echo(f"Analysis complete: {n_included} included, {n_excluded} excluded")
    click.echo(f"Output: {run_dir / FILTERED_ZH_FILE}")

    # Record in DB
    conn = init_db(Path(config.database.path))
    run_id = record_run(conn, date.today().isoformat(), len(enriched))
    for p in enriched:
        paper_id = upsert_paper(conn, p, date.today().isoformat())
        link_run_paper(conn, run_id, paper_id, p.index, p.bookmark_count, p.view_count)
    update_run_status(conn, run_id, "completed", filtered_count=n_included)
    conn.close()
```

#### `review` — Stage 3

```python
@cli.command()
@click.option("--papers", required=True,
              help="Comma-separated paper indices to review (e.g., '1,3,5').")
@click.option("--input", "input_dir", type=click.Path(exists=True),
              help="Path to run directory. Defaults to today's run.")
@click.pass_context
def review(ctx, papers, input_dir):
    """Run literature review for selected papers."""
    config = ctx.obj["config"]
    run_dir = Path(input_dir) if input_dir else _get_run_dir(config)

    paper_indices = [int(x.strip()) for x in papers.split(",")]

    llm = LLMClient(config.llm, config.anthropic_api_key)
    click.echo(f"Running literature review for papers: {paper_indices}")
    click.echo("This may take several minutes (multi-turn analysis per paper)...")

    reviews = asyncio.run(run_literature_review(paper_indices, run_dir, config, llm))

    # Report S2 grounding status
    for r in reviews:
        if not r.s2_grounding_available:
            click.echo(f"  WARNING: Paper #{r.paper_index} — Semantic Scholar data "
                       "unavailable, landscape analysis uses model knowledge only "
                       "(elevated hallucination risk)")

    # Report proposal validation warnings
    for r in reviews:
        warnings = validate_review_proposals(r.proposals_structured)
        if warnings:
            click.echo(f"  Validation warnings for paper #{r.paper_index}:")
            for w in warnings:
                click.echo(f"    - {w}")

    # Render markdown output
    en_md = render_review_markdown(reviews, date.today().isoformat(), "en")
    zh_md = render_review_markdown(reviews, date.today().isoformat(), "zh")
    (run_dir / LIT_REVIEW_EN_FILE).write_text(en_md, encoding="utf-8")
    (run_dir / LIT_REVIEW_ZH_FILE).write_text(zh_md, encoding="utf-8")

    # Save structured JSON (proposals for Stage 4 consumption)
    review_json = {
        "papers": [
            {
                "paper_index": r.paper_index,
                "title": r.paper_title,
                "proposals": [asdict(p) for p in r.proposals_structured],
            }
            for r in reviews
        ]
    }
    write_json(review_json, run_dir / LIT_REVIEW_JSON_FILE)

    click.echo(f"Review complete for {len(reviews)} papers")
    click.echo(f"Output: {run_dir / LIT_REVIEW_EN_FILE}")
    click.echo(f"Structured proposals: {run_dir / LIT_REVIEW_JSON_FILE}")
```

#### `plan` — Stage 4

```python
@cli.command()
@click.option("--paper", required=True, type=int,
              help="Paper index from the review (e.g., 3).")
@click.option("--proposal", required=True, type=int,
              help="Proposal index within the paper's review (e.g., 1).")
@click.option("--input", "input_dir", type=click.Path(exists=True),
              help="Path to run directory. Defaults to today's run.")
@click.pass_context
def plan(ctx, paper, proposal, input_dir):
    """Run experiment planning with adversarial critic for a selected proposal.

    Requires a completed Stage 3 review for the specified paper.
    Uses Orchestrator + Adversarial Critic architecture:
    1. Parallel Semantic Scholar research (novelty, baselines, related work)
    2. Planning agent (Opus, 3 turns: novelty → MVE/plan → ablations/risks)
    3. Adversarial critic (Opus, separate conversation)
    4. Revision (Opus, addresses critic feedback)
    5. Translation (Sonnet, EN → ZH)
    """
    config = ctx.obj["config"]
    run_dir = Path(input_dir) if input_dir else _get_run_dir(config)

    # Verify Stage 3 structured output exists
    review_json_path = run_dir / LIT_REVIEW_JSON_FILE
    if not review_json_path.exists():
        raise click.ClickException(
            f"No review JSON found at {review_json_path}. Run 'review' first."
        )

    llm = LLMClient(config.llm, config.anthropic_api_key)
    click.echo(f"Planning experiment for paper #{paper}, proposal #{proposal}")
    click.echo("Phase 1: Searching Semantic Scholar for related work...")
    click.echo("Phase 2: Planning agent (3 turns, this may take several minutes)...")

    result = asyncio.run(
        run_experiment_planning(paper, proposal, run_dir, config, llm)
    )

    click.echo("Phase 3: Adversarial critic reviewing plan...")
    click.echo("Phase 4: Revising plan based on critique...")

    # Render and save outputs
    en_file = EXPERIMENT_PLAN_EN_TEMPLATE.format(paper=paper, proposal=proposal)
    zh_file = EXPERIMENT_PLAN_ZH_TEMPLATE.format(paper=paper, proposal=proposal)
    json_file = EXPERIMENT_PLAN_JSON_TEMPLATE.format(paper=paper, proposal=proposal)

    en_md = render_experiment_plan_markdown(result, date.today().isoformat())
    (run_dir / en_file).write_text(en_md, encoding="utf-8")

    # Translate to Chinese
    zh_md = asyncio.run(translate_to_chinese(en_md, llm, config))
    (run_dir / zh_file).write_text(zh_md, encoding="utf-8")

    write_json(result, run_dir / json_file)

    # Save thinking logs
    for i, log in enumerate(result.thinking_logs):
        labels = ["plan_turn1", "plan_turn2", "plan_turn3", "critic", "revision"]
        if i < len(labels):
            save_thinking_log(log, f"stage4_p{paper}_r{proposal}_{labels[i]}", run_dir)

    click.echo(f"Experiment plan complete.")
    click.echo(f"Output: {run_dir / en_file}")
    if result.critique:
        click.echo(f"Critic raised {result.critique.count('**Issue**:')} issues (see plan for details)")
```

#### `run` — Full Pipeline (Stages 0–2)

```python
@cli.command()
@click.option("--force", is_flag=True, help="Re-run all stages even if outputs exist.")
@click.pass_context
def run(ctx, force):
    """Run full pipeline: scrape → parse → enrich → analyze.

    Each stage checks for existing outputs and skips if present (unless --force).
    This allows resuming from the last successful stage after a mid-pipeline failure.
    """
    config = ctx.obj["config"]
    run_dir = _ensure_run_dir(config)

    # Stage 0: Scrape
    if force or not (run_dir / RAW_INPUT_FILE).exists():
        ctx.invoke(scrape)
    else:
        click.echo(f"Skipping scrape (output exists: {run_dir / RAW_INPUT_FILE})")

    # Stage 1: Parse
    if force or not (run_dir / PAPERS_JSON_FILE).exists():
        ctx.invoke(parse)
    else:
        click.echo(f"Skipping parse (output exists: {run_dir / PAPERS_JSON_FILE})")

    # Stages 1.5 + 2: Enrich + Analyze
    if force or not (run_dir / FILTER_RESULT_FILE).exists():
        ctx.invoke(analyze)
    else:
        click.echo(f"Skipping analyze (output exists: {run_dir / FILTER_RESULT_FILE})")

    click.echo("Pipeline complete.")
```

#### `history` — View Past Runs

```python
@cli.command()
@click.option("--limit", default=20, help="Number of recent runs to show.")
@click.pass_context
def history(ctx, limit):
    """List past runs from the database."""
    config = ctx.obj["config"]
    conn = init_db(Path(config.database.path))
    runs = get_run_history(conn, limit)
    conn.close()

    if not runs:
        click.echo("No runs recorded yet.")
        return

    click.echo(f"{'Date':<12} {'Papers':<8} {'Filtered':<10} {'Status':<10}")
    click.echo("-" * 42)
    for r in runs:
        click.echo(f"{r['run_date']:<12} {r['paper_count']:<8} {r['filtered_count']:<10} {r['status']:<10}")
```

#### `trending` — View Papers Trending Across Runs

```python
@cli.command()
@click.option("--min-days", default=3, help="Minimum days a paper must be trending.")
@click.pass_context
def trending(ctx, min_days):
    """Show papers that have been trending for N+ days."""
    config = ctx.obj["config"]
    conn = init_db(Path(config.database.path))
    papers = get_trending_papers(conn, min_days)
    conn.close()

    if not papers:
        click.echo(f"No papers trending for {min_days}+ days.")
        return

    click.echo(f"Papers trending for {min_days}+ days:\n")
    click.echo(f"{'Title':<60} {'Days':<6} {'First Seen':<12} {'Max Bookmarks':<14}")
    click.echo("-" * 94)
    for p in papers:
        title = p['title'][:57] + "..." if len(p['title']) > 60 else p['title']
        click.echo(f"{title:<60} {p['times_seen']:<6} {p['first_seen']:<12} {p['max_bookmarks']:<14}")
```

---

## Helpers

```python
def _ensure_run_dir(config: AppConfig) -> Path:
    """Create and return today's run directory."""
    run_dir = Path(config.output.base_dir) / date.today().isoformat()
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir

def _get_run_dir(config: AppConfig) -> Path:
    """Get today's run directory (must exist)."""
    run_dir = Path(config.output.base_dir) / date.today().isoformat()
    if not run_dir.exists():
        raise click.ClickException(f"No run directory for today: {run_dir}")
    return run_dir
```

---

## Cron Automation

A simple shell script for daily execution:

```bash
#!/bin/bash
# scripts/daily_run.sh
cd "$(dirname "$0")/.."
source .venv/bin/activate
arxiv-trendy run 2>&1 | tee "data/runs/$(date +%Y-%m-%d)/run.log"
```

Cron entry (run daily at 9 AM):
```
0 9 * * * /path/to/applications/alpharxiv_trendy_analysis/scripts/daily_run.sh
```
