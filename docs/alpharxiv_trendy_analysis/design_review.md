# Design Review: AlphaRxiv Trendy Paper Analysis (v3)

**Date**: 2026-03-21
**Scope**: Full requirements (FR-1 through FR-9, QR-1, QR-2, NFR) vs. detailed design (00–06)
**Verdict**: All critical and high-priority issues from v1 and v2 reviews have been **resolved**. One low-priority item remains open (M3: scraping filter UI is a development-time TODO).

---

## Full Resolution History

### v1 Issues (2026-03-20)

| ID | Issue | Status | How Addressed |
|----|-------|--------|---------------|
| C1 | Thinking budget too low (10K) | RESOLVED | Increased to 40K |
| C2 | Wrong model tier (Sonnet-only) | RESOLVED | Per-stage model config, Opus for reasoning |
| C3 | max_tokens insufficient (16K) | RESOLVED | max_tokens_analyze = 32K |
| C4 | Phase B should be deterministic | RESOLVED | `render_analysis_markdown()` in Python |
| C5 | Multi-turn loses thinking chain | RESOLVED | `raw_content_blocks` preserved |
| C6 | Hallucination risk in Turn 2 | RESOLVED | Semantic Scholar citation grounding |
| C7 | Bilingual strategy undefined | RESOLVED | English + Sonnet translation |
| H1 | No output validation | RESOLVED | `validate_analysis_result()` with auto-retry |
| H2 | No prompt caching | RESOLVED | `cache_control` on system prompts |
| H3 | Suboptimal few-shot placement | RESOLVED | Output-only, user message, per-turn |
| H4 | Missing cost estimates | RESOLVED | Cost tables in design.md and 06_experiment_planning.md (corrected in v2 for thinking accumulation) |
| M1 | No tool use for JSON | RESOLVED | `call_with_tool()` method |
| M2 | Poor arXiv title matching | RESOLVED | Multi-strategy with fuzzy matching |
| M3 | Scraping filter UI is TODO | **OPEN** | Still `pass` in `_apply_filters()` — acceptable as a development-time TODO with fallback behavior (continue unfiltered + log warning). FR-1.6 is partially met: config accepts filter values, but UI interaction logic requires discovering live selectors during implementation. |
| M4 | No deduplication handling | RESOLVED | `cross_ref` field in excluded papers |
| M5 | No error recovery in `run` | RESOLVED | `--force` flag, stage-level skip |

### v2 Issues (2026-03-21)

| ID | Issue | Status | How Addressed |
|----|-------|--------|---------------|
| N1 | Stage 3 proposals not structured — breaks Stage 4 | RESOLVED | Turn 3 uses tool use (`PROPOSAL_TOOL_SCHEMA`), `ReviewProposal` dataclass, saves `literature_review.json`. Stage 4 uses `load_proposal()` from JSON. |
| N2 | No output validation for Stage 3/4 | RESOLVED | `validate_review_proposals()` in `03_llm_integration`, `validate_experiment_plan()` in `03_llm_integration`. CLI prints warnings. |
| N3 | Stage 4 cost estimate ~2.5x too low | RESOLVED | Cost table corrected with thinking accumulation breakdown (~$10-11/proposal). design.md total updated to ~$21-23. |
| N4 | S2 novelty search uses raw proposal text | RESOLVED | `_build_novelty_queries()` strips filler, uses structured proposal fields, runs 2-3 targeted queries with dedup. |
| N5 | Planning turns have no structured extraction | RESOLVED | `PLAN_TURN1_TOOL`, `PLAN_TURN2_TOOL`, `PLAN_TURN3_TOOL` schemas added. |
| N6 | S2 failures degrade silently | RESOLVED | `s2_grounding_available` flag on `PaperReview`, CLI warnings in `review` command, `s2_available` flag in Stage 4 research context. |
| N7 | No max_tokens for Stage 3/4 | RESOLVED | `max_tokens_review=16000`, `max_tokens_plan=24000` added to `LLMConfig` and config.toml. |
| N8 | Critic receives unstructured draft | RESOLVED | `_assemble_draft_plan()` with structured sections from tool use. `build_critic_prompt()` also receives `s2_novelty_papers` for independent novelty verification. |

---

## Remaining Open Item

### M3. Scraping Filter UI Interaction (`_apply_filters()`)

**Requirement**: FR-1.6

**Status**: `_apply_filters()` in `01_scraping_and_parsing.md` is `pass` with a TODO comment. This is acceptable at the design level because:
1. The exact CSS selectors depend on the live alphaxiv React UI and must be discovered during implementation
2. The fallback behavior is well-defined: log a warning and continue with unfiltered results
3. Category/subcategory config values are accepted and stored — only the UI interaction is missing

**Action**: Implement during development by inspecting the live alphaxiv UI. No design change needed.
