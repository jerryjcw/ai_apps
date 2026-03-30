# Research Ideation & Experiment Design Tool -- High-Level Design

> **Project**: Multi-agent research ideation system
> **Architecture Reference**: [AutoResearchClaw System Analysis](investigate/autoresearchclaw_system_design.md)
> **Design Date**: 2026-03-27

---

## Table of Contents

1. [Problem & Motivation](#1-problem--motivation)
2. [System Overview](#2-system-overview)
3. [Agent Roles](#3-agent-roles)
4. [Pipeline Stages](#4-pipeline-stages)
5. [Communication Protocol](#5-communication-protocol)
6. [Quality Gates & Progressive Standards](#6-quality-gates--progressive-standards)
7. [Iteration Mechanics](#7-iteration-mechanics)
8. [Skill Definitions](#8-skill-definitions)
9. [Prompt Design](#9-prompt-design)
10. [Python Helpers](#10-python-helpers)
11. [Logging Strategy](#11-logging-strategy)
12. [File & Directory Structure](#12-file--directory-structure)
13. [Cost Estimate](#13-cost-estimate)
14. [Future Extensibility](#14-future-extensibility)
15. [Implementation Sequencing](#15-implementation-sequencing)

---

## 1. Problem & Motivation

Turning a vague research direction into a publishable research plan requires iterative cycles of literature review, ideation, hypothesis refinement, and critical review -- a process that typically takes weeks of advisor-student interaction. This tool automates that loop using three distinct LLM-powered roles that debate, refine, and stress-test ideas until they reach top-conference quality.

**What it does**: Given a research topic (and optionally some reference paper titles), the system autonomously:
- Searches and reads real literature
- Generates 8-10 candidate ideas
- Develops hypotheses, methods, and experiment plans
- Iterates through advisor and external reviewer feedback
- Outputs 3-5 polished research plans ready for implementation

**What it does NOT do (yet)**: Execute experiments, write papers, or generate code. The design reserves extension points for these future phases.

---

## 2. System Overview

### Architecture: Orchestrator + Role Skills + Python Helpers

```
User: /research-ideate "Use contrastive decoding to improve reasoning in small LMs"
                        + optional: "papers: Contrastive Decoding (Li et al. 2023)"
         |
  ┌──────v──────────────────────────────────────────────────────────┐
  │  research-ideate (Orchestrator Skill)                           │
  │  Model: Opus  |  User-invocable: true                          │
  │                                                                 │
  │  - Parses user input (topic, paper titles, constraints)         │
  │  - Initializes proposal_space/ directory + state.json           │
  │  - Drives the 9-stage pipeline as a state machine               │
  │  - Spawns sub-agents for each role via Agent tool               │
  │  - Reads agent outputs, writes to proposal_space/               │
  │  - Enforces quality gates, decides PROCEED/REFINE/PIVOT/DROP    │
  │  - Produces final output when pipeline completes                │
  └───────┬─────────────────┬────────────────────┬─────────────────┘
          │                 │                    │
    ┌─────v──────┐   ┌─────v────────┐   ┌──────v──────────────┐
    │  Student   │   │  Advisor     │   │  Visiting Professor │
    │  (Sonnet)  │   │  (Opus)      │   │  (Opus)             │
    │            │   │              │   │                     │
    │  - Lit     │   │  - Hypothesis│   │  - External stress  │
    │    search  │   │    gate      │   │    test             │
    │  - Idea    │   │  - Plan      │   │  - Find issues      │
    │    gen     │   │    review    │   │    Advisor missed   │
    │  - Hypo-   │   │  - Final     │   │  - Reviewer attack  │
    │    thesis  │   │    ranking   │   │    vectors          │
    │  - Exp     │   │              │   │                     │
    │    plan    │   │              │   │                     │
    └────────────┘   └──────────────┘   └─────────────────────┘
          |                 |                    |
          v                 v                    v
  ┌─────────────────────────────────────────────────────────────┐
  │                   proposal_space/                            │
  │                                                             │
  │  state/          - Pipeline state machine (state.json)      │
  │  literature/     - Collected papers + landscape tables      │
  │  ideas/          - Candidate idea lists                     │
  │  hypotheses/     - Developed hypotheses + methods           │
  │  plans/          - Experiment plans                         │
  │  reviews/        - Advisor + VP reviews (visible to each)   │
  │  interaction_log/ - Complete audit trail of ALL interactions│
  │  final/          - Approved plans awaiting output           │
  └─────────────────────────────────────────────────────────────┘
```

### Data Flow Summary

```
Input (topic + optional paper titles)
    |
    v
Stage 1: Literature Collection ──────── Student (Sonnet) ── WebSearch/WebFetch
    |
    v
Stage 2: Idea Generation (8-10) ─────── Student (Sonnet)
    |
    v
Stage 3: Hypothesis + Method ────────── Student (Sonnet)
    |                                    + Advisor gate (Opus)
    |  <── REFINE loop (Advisor feedback)
    v
Stage 4: Experiment Planning ────────── Student (Sonnet)
    |
    v
Stage 5: Proposal Submission ────────── Orchestrator (automatic, writes manifest)
    |
    v
Stage 6: Advisor Review ─────────────── Advisor (Opus) ── reads VP prior review
    |
    v
Stage 7: Visiting Prof Review ──────── VP (Opus) ── reads Advisor review, WebSearch
    |
    v
Stage 8: Decision ───────────────────── Orchestrator
    |  APPROVE  → idea moves to final pool
    |  REFINE   → back to Stage 3 or 4
    |  PIVOT    → back to Stage 2 (replace idea)
    |  DROP     → permanently removed
    v
Stage 9: Final Filtering + Output ──── Orchestrator + Advisor (Opus)
    |
    v
3-5 Final Research Plans (.md)
```

---

## 3. Agent Roles

### 3.1 Graduate Student (研究生)

| Attribute | Value |
|-----------|-------|
| **Model** | Sonnet (cost-efficient for high-volume generative work) |
| **Cognitive stance** | Generative, exploratory, breadth-first. Produces volume. |
| **Stages** | 1 (literature), 2 (ideation), 3 (hypothesis/method), 4 (experiment planning) |
| **Tools needed** | WebSearch, WebFetch, Read |
| **Agent type** | `general-purpose` (needs WebSearch + WebFetch access) |

The Student does the bulk of the research legwork. It searches for real papers, generates many candidate ideas, develops them into hypotheses, and designs experiment plans. When reviewers send feedback, the Student revises accordingly.

**Key instruction**: The Student must **ground all claims in real papers** found via WebSearch. No fabricated citations. If a paper title is provided by the user without a URL, the Student must find and read it.

### 3.2 Advisor (指導教授)

| Attribute | Value |
|-----------|-------|
| **Model** | Opus (deep reasoning for quality assessment) |
| **Cognitive stance** | Constructive critic. Helps the student succeed, but kills flawed ideas. |
| **Stages** | 3-gate (hypothesis review), 6 (plan review), 9 (final ranking) |
| **Tools needed** | Read (reviews, plans), WebSearch (occasional claim verification) |
| **Agent type** | `general-purpose` |

The Advisor intervenes at two critical points:
1. **Hypothesis gate (Stage 3)**: Preliminary check before the Student invests in experiment planning. Quick verdicts: DEVELOP / REFINE / DROP.
2. **Full plan review (Stage 6)**: Thorough review of complete experiment plans. Applies the current round's quality standard.

The Advisor reads the Visiting Professor's prior review (if available) and is explicitly prompted to offer **different perspectives**.

**Evaluation techniques the Advisor must apply** (based on proven research evaluation patterns):
1. **Cross-domain analogy test**: "Isn't this just X from field Y?" If the idea can be reduced to a known method in one sentence, demand deeper novelty.
2. **Counterexample pressure test**: Find 3 concrete failure cases and check if the method design addresses them (not just in limitations).
3. **Anti-circularity check**: Catch bootstrap estimation loops where "estimate X using Y, but Y depends on X."
4. **Actionable cross-over test**: If the idea claims to unify two areas, demand a closed-loop feedback mechanism (not just shared math tools).
5. **Multi-level framework test**: Prefer ideas that form multi-level frameworks (each level removes one assumption) over single-trick heuristics.

### 3.3 Visiting Professor (客座教授)

| Attribute | Value |
|-----------|-------|
| **Model** | Opus (independent critical perspective) |
| **Cognitive stance** | Adversarial. No stake in the ideas succeeding. Finds weaknesses. |
| **Stages** | 7 (external review) |
| **Tools needed** | Read (plans, advisor review), WebSearch (check for concurrent/scooping work) |
| **Agent type** | `general-purpose` |

The VP provides the "ICML/NeurIPS reviewer" perspective. They:
- Deliberately look for issues the Advisor missed
- Identify top-3 reviewer attack vectors per plan
- Check for very recent competing work via WebSearch
- Suggest specific preemptive defenses

### 3.4 Orchestrator (Pipeline Runner)

Not a separate agent -- this IS the main Claude Code conversation. The orchestrator:
- Manages `state.json` via Python helpers
- Spawns role agents via the Agent tool
- Writes agent outputs to `proposal_space/`
- Logs all interactions
- Enforces quality gates and iteration limits
- Makes PROCEED/REFINE/PIVOT/DROP decisions based on aggregated reviews

---

## 4. Pipeline Stages -- Detailed

### Stage 1: Literature Collection

**Actor**: Student (Sonnet)
**Entry**: User has provided topic + optional paper titles
**Process**:
1. If user provided paper titles without URLs, search for each via WebSearch and fetch content (arXiv HTML preferred, abstract as fallback)
2. Search for 15-25 related papers using topic keywords via WebSearch (Google Scholar, Semantic Scholar, arXiv)
3. For each paper found, extract: title, authors, year, venue, abstract, key contributions, method summary
4. Build a **prior-art landscape table** (modeled on `llm_research/spec.md` Phase 1):

   | Paper | Core Claim | What It Solves | What It Does NOT Solve | Why Naive Follow-up = Low Novelty | Remaining Gap |
   |-------|-----------|---------------|----------------------|----------------------------------|---------------|

   This table format is critical -- the "Why Naive Follow-up = Low Novelty" column forces the Student to think about what is NOT worth doing, preventing low-novelty ideas in Stage 2.

5. Identify: crowded sub-areas (avoid), underexplored gaps (target), recent trends (leverage)

**Exit criteria**: >= 10 papers with abstracts collected. Landscape table has gap column populated.
**Fail action**: Re-search with broader/alternative terms (max 2 retries).
**Output**: `proposal_space/literature/landscape_round{N}.md`

**Post-stage**: **Viability Checkpoint 1** runs automatically (see §7 TOPIC_INFEASIBLE). If the Advisor returns INFEASIBLE, the pipeline terminates with a viability report. If VIABLE_WITH_CAVEATS, the caveats are injected into Stage 2's prompt.

### Stage 2: Idea Generation

**Actor**: Student (Sonnet)
**Entry**: Literature landscape exists
**Process**:
1. Generate **8-10 candidate ideas** based on identified gaps
2. For each idea:
   - One-paragraph description (what's new, why it matters)
   - Which gap it addresses (reference specific landscape table entry)
   - Closest prior work and how this differs
   - Initial novelty self-assessment (high/medium/low confidence)
   - Rough feasibility (compute, data requirements)
3. Apply Round 1 lenient filtering: pass anything with a plausible novelty claim
4. In later rounds (PIVOT replacements), the Student sees what was tried and failed

**Exit criteria**: >= 8 ideas with distinct novelty claims.
**Fail action**: Generate more (max 1 retry).
**Output**: `proposal_space/ideas/candidates_round{N}.md`

### Stage 3: Hypothesis & Method Design + Advisor Gate

**Actor**: Student (Sonnet) produces; Advisor (Opus) reviews
**Entry**: Candidate ideas exist
**Process**:

**Student phase** -- For each surviving idea, develop:
1. **Thesis statement**: one-sentence claim (what mechanism + why current methods fail + what improvement)
2. **Theoretical basis**: specific theory/framework grounding the approach, with verifiable propositions
3. **Method sketch**: inputs -> intermediate signals -> algorithm -> objective -> key ablation dimensions
4. **Variants**: propose 2-4 method variants, each removing one limitation of the base method. Frame as a multi-level framework (Level 1 = simplest version, Level 2+ = each removes one assumption). Each level's ablation should answer an independent scientific question.
5. **Closest prior work comparison**: side-by-side with 5-8 papers (like/unlike/why-not-just-a-variant). Must include papers from adjacent fields that solve similar problems with different methods.
6. **Circularity check**: explicitly verify that no estimation step is circular (e.g., "estimate X using Y, but Y depends on X"). If circularity exists, acknowledge and propose fix.

**Advisor gate** -- For each hypothesis, the Advisor applies a **9-dimension harsh filter** (adapted from proven filtering rubric):

| Dimension | Description |
|-----------|------------|
| Novelty vs base papers | Can this be reduced to a known method in one sentence? If yes, novelty insufficient. |
| Novelty vs recent neighbors | Has someone done something very similar in the last 6 months? |
| Theoretical depth | Is this a single-trick heuristic, or a multi-level framework? |
| Implementation risk | How hard is the engineering? What's the most likely failure mode? |
| Experimental clarity | Can the ablations be cleanly designed? Does each answer an independent scientific question? |
| Storyline strength | Is there a sharp hook? Can the contribution be explained in one paragraph? |
| Reviewer attack risk | What's the top-3 likely reviewer attacks? Are they addressable? |
| 6-month executability | Can a strong research engineer produce an MVP in 6 months? |
| 12-month upside | If it works, what's the ceiling? Could this define a new research direction? |

The Advisor scores each dimension 1-5 and provides:
- Verdict: **DEVELOP** (proceed to experiment planning), **REFINE** (specific issues to fix), **DROP** (fatal flaw)
- **PIVOT is NOT available at Stage 3** -- it is reserved for Stage 6 (full plan review) where the Advisor has seen the complete experiment plan.
- If REFINE: numbered list of specific issues with **severity labels** [severe|major|minor|slight] and suggestions
- The Advisor reviews ideas **one by one**, not in batch. Each idea is independently assessed and must independently meet the quality bar. An idea with DEVELOP verdict must have no open severe or major issues.

**REFINE sub-loop**: Student revises based on Advisor feedback. Up to **2 Student agents per idea** may work in parallel on independent issues. Max 3 sub-iterations per idea at this stage. If the Advisor issues REFINE but `can_refine()` returns False (refine_count >= MAX), the idea is automatically **DROPPED**.

**Ideas stuck in REFINE**: Any idea still in `refine` status after the Stage 3 REFINE sub-loop completes (including all retry attempts) without achieving DEVELOP is automatically **DROPPED**.

**Quality gate**: >= 3 ideas must receive DEVELOP verdict (status `planning`). If fewer than 3 after 2 mini-Stage 2 retry attempts, trigger **Viability Checkpoint 2** (see §7 TOPIC_INFEASIBLE). The original >= 5 target is aspirational; the hard floor is 3.
**Output**: `proposal_space/hypotheses/hypothesis_{slug}_round{N}.md`, `proposal_space/reviews/advisor_hypothesis_round{N}.md`

### Stage 4: Experiment Planning

**Actor**: Student (Sonnet)
**Entry**: >= 5 Advisor-approved hypotheses
**Process**: For each approved hypothesis, produce:

1. **Minimum Viable Experiment (MVE)**: the simplest test that could falsify the hypothesis
   - Model, dataset, metric, expected outcome, time estimate
2. **Full experiment plan** (3 phases):
   - Phase 1: Core validation (MVE + 1-2 extensions)
   - Phase 2: Scaling + ablations
   - Phase 3: Benchmarks + comparisons
3. **Baselines**: 3-5 strongest competing methods with code availability noted
4. **Ablation table**: what to vary, what to hold constant, what each ablation tests
5. **Datasets**: specific datasets with sizes, access methods, preprocessing needs
6. **Metrics**: primary metric + secondary diagnostics
7. **Compute estimate**: GPU type x count x hours per phase
8. **Success criteria**: what result would make this publishable vs. what would kill it
9. **Risk register**: top-3 risks with early warning signs and mitigation
10. **Reviewer-facing paper storyline**: hook -> insight -> method -> empirical -> contribution

**Output**: `proposal_space/plans/plan_{slug}_round{N}.md`

### Stage 5: Proposal Submission

**Actor**: Orchestrator (automatic)
**Entry**: Experiment plans written
**Process**: Verify all plans are present for ideas with `planning` status. **Ideas already in `approved` status from prior rounds are NOT re-submitted** -- they retain their approved status and skip Stages 5-8. Only ideas with `planning` or `refine` status from the current round enter the review pipeline. Create submission manifest:
```json
{
  "round": N,
  "timestamp": "YYYY-MM-DDTHH:MM:SS",
  "quality_standard": "lenient|moderate|strict",
  "ideas_submitted": ["slug_1", "slug_2", ...],
  "status": "pending_advisor_review"
}
```
**Output**: `proposal_space/state/submission_round{N}.json`

### Stage 6: Advisor Review

**Actor**: Advisor (Opus)
**Entry**: Submission manifest with status `pending_advisor_review`
**Input context**: All experiment plans for this round + VP review from prior round (if exists)
**Process**:

The Advisor reviews **each plan in a separate agent call** -- one proposal per call, not batch. When reviewing individually, the Advisor evaluates against **absolute quality criteria** (the 9-dimension filter), not relative to other proposals. Cross-plan comparison is done by the orchestrator at Stage 9 (final ranking).

For each plan, using the **current round's quality standard**:
1. Evaluate: novelty strength, theoretical rigor, experimental sufficiency, baseline coverage, ablation completeness, storyline clarity
2. Label each issue with severity: **severe** / **major** / **minor** / **slight**
3. Check the review tracker for any prior unresolved issues; confirm resolved or still-open
4. Verdict: **APPROVE** / **REFINE** / **PIVOT** / **DROP**
   - APPROVE only when NO severe and NO major issues remain (only minor/slight may remain as caveats).
   - REFINE: specific actionable feedback with severity labels (not vague "needs more work")

**Output**: `proposal_space/reviews/advisor_{slug}_round{N}.md` (one file per proposal)

### Stage 7: Visiting Professor Review

**Actor**: Visiting Professor (Opus)
**Entry**: Advisor review for this round exists
**Process**: The VP reviews **each plan in a separate agent call** -- one proposal per call, matching the Advisor's per-proposal pattern.

For each plan:
1. Read the Advisor's review for THIS specific plan
2. Check the review tracker for prior unresolved issues
3. **Explicitly prompted**: "Provide perspectives the Advisor has NOT raised. Do not merely agree."
4. Stress-test on:
   - Theoretical correctness (are claims logically sound?)
   - Experimental validity (do experiments actually test the hypothesis?)
   - Missing baselines or ablations the Advisor didn't flag
   - **Top-3 reviewer attack vectors** with suggested defenses
   - Very recent competing work (use WebSearch to check for scooping, papers from last 3 months)
5. Label each issue with severity: **severe** / **major** / **minor** / **slight**
6. Verdict: APPROVE / REFINE / DROP (VP does not issue PIVOT -- that's the Advisor's prerogative)
   - APPROVE only when NO severe and NO major issues remain (only minor/slight may remain)

**Output**: `proposal_space/reviews/vp_{slug}_round{N}.md` (one file per proposal)

### Stage 8: Revision Decision + Review Tracker + Student Revision Loop

**Actor**: Orchestrator + Student(s)
**Entry**: Both reviews exist for this round

#### 8.1 Review Tracker

All issues from both reviewers are collected into a **review tracker** (`proposal_space/state/review_tracker.json`) that tracks every issue's severity, status, and resolution. Each issue gets a unique ID (e.g., `R1-ADV-1`, `R1-VP-3`) and one of four severity levels:

| Severity | Definition | Blocks approval? |
|----------|-----------|-----------------|
| **severe** | Fatal or near-fatal flaw. Paper WILL be rejected if not addressed. | YES |
| **major** | Significant weakness. Top-venue reviewer would likely cite as rejection reason. | YES |
| **minor** | Real but addressable without changing core approach. Not rejection-worthy alone. | No |
| **slight** | Cosmetic or polish-level. Improves paper but not blocking. | No |

Issue statuses: `open` → `addressed` (with resolution note) or `wontfix` (with justification).

#### 8.2 Decision Matrix

| Advisor | VP | Decision |
|---------|-----|----------|
| APPROVE | APPROVE | **APPROVE** -- only if ALL severe/major issues are addressed |
| APPROVE | REFINE | **REFINE** -- address VP's severe/major issues |
| REFINE | APPROVE | **REFINE** -- address Advisor's severe/major issues |
| REFINE | REFINE | **REFINE** -- address both sets of severe/major issues |
| PIVOT | any | **PIVOT** -- replace idea, back to Stage 2 |
| DROP | any | **DROP** -- permanently removed |
| any | DROP | **DROP** -- permanently removed |

**CRITICAL RULE**: The decision matrix is necessary but NOT sufficient. All decisions are further gated by the **review tracker**: no idea transitions to APPROVED if any severe/major issue remains open, regardless of reviewer verdicts. Even if both reviewers say "APPROVE", any open severe/major issue forces REFINE. Minor and slight issues do not block approval but are noted as caveats in the final output.

**VP DROP override**: When the VP issues DROP, it overrides Advisor APPROVE because the VP's DROP implies severe issues that become open entries in the review tracker, blocking approval regardless.

#### 8.3 Student Revision Loop

For each REFINE idea:
1. The orchestrator identifies all open severe/major issues from the review tracker.
2. **Up to 2 Student agents may be spawned per idea** in parallel if the issues are independent (e.g., one handles theory/novelty issues, another handles experiment design issues). This speeds up revision without sacrificing quality.
3. Each Student receives: the current plan, the specific issues to address (with IDs), both reviewer comments, and the literature landscape.
4. After revision, the orchestrator updates the review tracker: marks each addressed issue with `"status": "addressed"`, `"addressed_in": "R{round}_revision"`, and a resolution note.
5. Revised plans are re-submitted to **both** Advisor and VP for re-review.
6. Reviewers check each previously-open issue, confirm addressed or still-open, and may flag NEW issues introduced by the revision (with severity).
7. Repeat until: all severe/major issues addressed (→ APPROVE) or max refine cycles reached (3 per idea → **DROP** -- the idea is dead).

**Routing**:
- Issues about **hypothesis/theory/novelty** -> back to Stage 3
- Issues about **experiment design** only -> back to Stage 4

**Output**: Updated `state.json`, `review_tracker.json` with per-issue resolution

### Convergence Check (between Stage 8 and Stage 9)

The convergence check happens in Stage 8, **after all reviews, revisions, and re-reviews for this round are complete**. If `check_convergence()` returns True (>= 3 approved), proceed to Stage 9. Any remaining REFINE ideas at this point are abandoned (they do not carry over unless a new round starts).

If convergence is not met:
- `record_round_history()`, then `start_new_round()` (increments round, tightens quality standard)
- Go back to Stage 3 (if refine ideas exist) or Stage 9 (if no refine ideas, forced convergence)

### Stage 9: Final Filtering & Output

**Actor**: Orchestrator + Student (Sonnet for writing) + Advisor (Opus for ranking)
**Entry**: `check_convergence()` returned True, OR max rounds reached
**Process**:

1. Collect all APPROVED plans (only proposals with no open severe/major issues)
2. If > 5: Advisor ranks and selects top 5 with justification
3. If 1-2 approved: output what exists with a note that the pipeline could not produce a full set
4. If 0 approved (safety net): trigger **TOPIC_INFEASIBLE** termination

5. **CRITICAL: Render each final plan as a SELF-CONTAINED document.** Each output file must be readable and understandable WITHOUT any other file from the pipeline. No pointers, no "see file X", no cross-references. ALL content must be inlined in full.

   For each approved idea, the orchestrator reads ALL source material (hypothesis, experiment plan, advisor reviews, VP reviews, review tracker, literature landscape) and passes it as **inline content** to a Student agent (Sonnet), which writes a comprehensive, standalone research proposal.

   Each proposal follows the **14-section template** with FULL SUBSTANTIVE CONTENT in every section:

   1. Title (paper-like)
   2. One-sentence thesis (what mechanism + why current methods fail + what improvement)
   3. Research area classification (specific sub-field, relevant venues)
   4. Closest prior work (5-8 papers with full comparison table: similarity / difference / why-not-just-a-variant)
   5. Problem gap (what is unsolved, why now, why this gap is deep enough)
   6. Theoretical basis (specific framework, verifiable propositions with formal statements, assumptions, guarantees)
   7. Method sketch (inputs -> signals -> algorithm -> objective, pseudocode or algorithmic steps, detailed enough to implement)
   8. Method variants (2-4 variants as multi-level framework, each removing one limitation, each described in full)
   9. Implementation plan (MVP timeline, full version, engineering complexity, most likely failure mode, mitigation, compute estimate by phase)
   10. Experimental plan (MVE with kill criteria, full 3-phase plan, baselines with code availability, ablation table, specific datasets with sizes, metrics, success criteria with specific numbers, risk register with top-3 risks)
   11. Paper storyline (written as a draft abstract: hook -> insight -> method -> empirical -> contribution)
   12. Novelty risk assessment (most similar work, likely "incremental" criticism, specific mitigation, scooping check results)
   13. Quality checklist (each item marked PASS/FAIL with evidence)
   14. Final verdict (confidence level, recommended venue, 9-dimension score summary)
   + Appendix A: Review history (all issues, how each was resolved)
   + Appendix B: Key references (full citations with arXiv IDs)

6. **Self-containment verification**: Grep each output file for "see ", "refer to", "proposal_space". If found, the document is NOT self-contained and must be regenerated.

7. Produce summary comparison table

**Output**: Final `.md` files in `output/research_ideate/<topic_slug>/<YYYYMMDD>/`

---

## 5. Communication Protocol

### File-Based Contracts

All agent communication goes through `proposal_space/`. Sub-agents return structured text via stdout (following the `job-match` skill pattern); the orchestrator writes these to disk.

**State file** (`proposal_space/state/state.json`):
```json
{
  "topic": "Use contrastive decoding to improve reasoning in small LMs",
  "paper_titles": ["Contrastive Decoding (Li et al. 2023)"],
  "constraints": {
    "max_gpus": 8,
    "gpu_model": "H100",
    "focus_areas": ["LLM", "reasoning", "decoding"],
    "target_venues": ["ICML", "NeurIPS", "ICLR"]
  },
  "current_round": 2,
  "current_stage": "stage_7_vp_review",
  "quality_standard": "moderate",
  "ideas": {
    "contrastive-cot": {
      "status": "in_review",
      "round_created": 1,
      "refine_count": 0,
      "advisor_verdicts": [{"round": 1, "verdict": "REFINE", "issues": ["..."]}],
      "vp_verdicts": []
    },
    "token-level-contrast": {
      "status": "approved",
      "round_created": 1,
      "round_approved": 2,
      "refine_count": 1
    }
  },
  "pivot_count": 0,
  "max_pivots": 3,
  "max_rounds": 3,
  "iteration_history": [
    {"round": 1, "ideas_submitted": 8, "approved": 2, "refined": 4, "pivoted": 1, "dropped": 1}
  ]
}
```

### Handoff Pattern

```
Orchestrator:
  1. Load state.json -> determine next stage
  2. Read relevant input files for this stage
  3. Construct agent prompt with:
     - Role prompt (from ri-student.md / ri-advisor.md / ri-visiting-prof.md)
     - Stage-specific task description
     - File contents to review (embedded or as file paths)
     - Current quality standard + rubrics
     - Prior review text (if applicable)
  4. Spawn Agent(subagent_type="general-purpose", prompt=<constructed_prompt>)
  5. Receive agent output text
  6. Write output to proposal_space/<appropriate_dir>/
  7. Log interaction via Python helper
  8. Update state.json via Python helper
  9. Proceed to next stage or loop
```

### Output Format Markers

Agent prompts instruct each role to include structured markers in their output for machine parsing:

```
=== IDEA: contrastive-cot ===
VERDICT: REFINE
SCORE_NOVELTY: 4
SCORE_THEORY: 3
SCORE_FEASIBILITY: 4
ISSUES:
1. [theory] The claim that contrastive signals preserve... (explanation)
2. [experiment] Missing comparison with... (explanation)
SUGGESTIONS:
1. Consider adding... (specific fix)
2. The baseline set should include... (specific fix)
=== END IDEA ===
```

The `parse_review.py` helper extracts these into structured dicts.

---

## 6. Quality Gates & Progressive Standards

### Gate Summary

| Gate | After Stage | Pass Criteria | Fail Action | Max Retries |
|------|------------|--------------|-------------|-------------|
| Literature | 1 | >= 10 papers with abstracts + landscape table with gaps | Re-search with broader terms | 2 |
| **Viability Checkpoint 1** | 1 (post) | Advisor deems topic VIABLE or VIABLE_WITH_CAVEATS | **INFEASIBLE → pipeline terminates with viability report** | 0 |
| Idea Volume | 2 | >= 8 ideas (aspirational), hard floor >= 3 | Generate more ideas | 1 |
| Advisor Hypothesis | 3 | >= 3 ideas with DEVELOP verdict (hard floor) | Generate replacement ideas + revise; if < 3 after retries → Checkpoint 2 | 2 |
| **Viability Checkpoint 2** | 3 (if all DROP after retries) | At least 1 idea is DEVELOP-worthy | **INFEASIBLE → pipeline terminates with viability report** | 1 (Advisor-guided retry) |
| Dual Review | 8 | Both reviewers APPROVE (or APPROVE + soft REFINE) | REFINE/PIVOT/DROP per idea | 3 rounds |
| Final Volume | 9 | >= 1 approved plan | If 0 approved: TOPIC_INFEASIBLE. If < 3: output what exists with note. | 0 |

### Progressive Quality Standards

The quality standard escalates with each review round. Both the Advisor and VP receive explicit rubrics matching the current standard.

#### Round 1: Lenient

The goal is to avoid premature rejection. Cast a wide net.

| Dimension | Criteria |
|-----------|----------|
| Novelty | "Plausibly novel" -- not an obvious duplicate of existing work. Overlapping ideas survive if they have a distinct angle. |
| Theory | "Plausibly sound" -- no obvious logical contradictions. Hand-wavy reasoning is OK at this stage. |
| Experiments | "Plausibly sufficient" -- experiments could test the claim. Missing baselines or ablations are noted but not blocking. |
| Verdict threshold | DEVELOP unless fatally flawed or clearly not novel |

#### Round 2: Moderate

Refined ideas must show clear substance.

| Dimension | Criteria |
|-----------|----------|
| Novelty | "Clearly novel" -- concrete, specific differentiation from closest prior work. "We do X differently because Y" must be defensible. |
| Theory | "Sound" -- theoretical claims are correct, assumptions are stated explicitly, key propositions are verifiable. |
| Experiments | "Sufficient" -- all necessary baselines present, ablations cover key design choices, metrics are appropriate for the claim. |
| Verdict threshold | APPROVE only if all three dimensions are at least "adequate". REFINE for specific fixable issues. |

#### Round 3: Strict (Top-Conference Bar)

Final round applies reviewer-level scrutiny.

| Dimension | Criteria |
|-----------|----------|
| Novelty | "Publishably novel" -- would survive a skeptical ICML/NeurIPS/ICLR reviewer's novelty challenge. Clear delta from all known prior work including very recent papers. |
| Theory | "Rigorous" -- claims are provable or strongly supported. Assumptions are reasonable and stated. Attack vectors are preemptively addressed. |
| Experiments | "Convincing" -- strong baselines (including latest SOTA), meaningful ablations (each isolates one design choice), clear success criteria, failure modes acknowledged. |
| Verdict threshold | APPROVE only for genuinely top-conference quality. Be harsh. |

---

## 7. Iteration Mechanics

### Round Numbering

- `current_round` only increments when `start_new_round()` is called (between rounds).
- **REFINE sub-loops within Stage 8 do NOT increment `current_round`**. All reviews, revisions, and re-reviews within a single pass through Stages 3-8 share the same round number.
- Verdicts recorded during REFINE sub-loops use the current round number for tracking purposes.

### refine_count Scope

`refine_count` is **cumulative across all stages and all rounds**. It is a single counter per idea that increments each time the idea transitions to `refine` status, regardless of which stage triggered it. An idea refined 2 times in Stage 3 has only 1 remaining refine attempt in Stage 8. This matches the implementation in `state_manager.py`.

### REFINE (Revision Required)

- **Trigger**: At least one reviewer marks a plan as REFINE, OR any severe/major issue remains open in the review tracker
- **Routing**:
  - Issues about hypothesis/theory/novelty -> back to **Stage 3** (revise hypothesis, go through Advisor gate again)
  - Issues about experiment design only -> back to **Stage 4** (revise plan only)
- **Data passed to Student**: Both reviewer comments, numbered issue list with IDs and severities, current plan version, prior literature landscape, review tracker showing which issues are open
- **Parallel Students**: Up to 2 Student agents may be spawned per idea if the issues are independent (e.g., one handles theory issues, another handles experiment design). This accelerates revision without sacrificing quality.
- **Max per idea**: 3 REFINE cycles (cumulative). After the 3rd, idea is either APPROVED (all severe/major addressed) or **DROPPED** (if any severe/major issues remain, the idea is dead).
- **can_refine() gate**: If the Advisor issues REFINE but `can_refine()` returns False (refine_count >= MAX), the idea is automatically **DROPPED**. No further revision is allowed.
- **New issues from revision**: If a Student revision introduces a NEW severe/major issue and `can_refine()` returns False (refine_count already at max), the idea is automatically **DROPPED**. The new issue is recorded in the review tracker for audit purposes.
- **Approval gate**: An idea exits REFINE status ONLY when ALL severe and major issues in the review tracker have status `addressed`. Minor and slight issues may remain open.

**All proposals dead**: If all active ideas reach DROPPED or PIVOTED status:
- If pivot budget remains (< 3 pivots used) AND current_round < max_rounds: return to **Stage 2** with the Advisor's guidance on what directions to try instead. All DROP reasons are passed to the Student. This counts as a PIVOT (increments pivot_count).
- If pivot budget exhausted OR max rounds reached: trigger **TOPIC_INFEASIBLE** termination with a viability report (see §7 TOPIC_INFEASIBLE Checkpoint 2).

**Critical REFINE instruction for the Student** (based on proven iteration patterns):
1. **Do NOT defend the original approach.** Acknowledge the weakness, then fix it.
2. **Turn every counterexample into an innovation point.** Ask: "What mechanism would make this criticism invalid?" The mechanism becomes a new feature.
3. **Escalate from heuristic to framework.** If a reviewer says "this is just X", acknowledge it as Level 1, then systematically remove its limitations: each removed limitation = a new Level. Each Level's ablation answers one scientific question.
4. **Upgrade observational claims to actionable mechanisms.** If a reviewer says "the cross-over claim is weak", find a concrete closed-loop feedback where output of component A improves input of component B.
5. **Search adjacent fields.** When a reviewer draws a cross-domain analogy, immediately search that field for recent techniques that could strengthen the method.

### PIVOT (Major Direction Change)

- **Trigger**: Advisor marks a plan as PIVOT at **Stage 6 or later** (PIVOT is not available at Stage 3)
- **Action**: Idea status becomes `pivoted` (terminal). Student returns to **Stage 2** to generate a replacement idea. The replacement is a **new entry** in `state["ideas"]` with its own slug, `round_created` set to current round, and `refine_count` starting at 0.
- **Data passed**: PIVOT reason, what to avoid, what direction to explore instead, which landscape gaps remain open
- **Max per run**: 3 PIVOTs total across all ideas (global, cumulative). Prevents infinite exploration.
- **Tracking**: The pivoted idea and its replacement are separate entries. They are not linked in the state machine, but the interaction log records the pivot relationship.

### DROP (Permanent Removal)

- **Trigger**: Any of these conditions:
  1. Both reviewers say DROP
  2. One says DROP and the other says REFINE with severe issues
  3. Idea fails to pass review after 3 REFINE cycles (refine_count >= MAX with open severe/major)
  4. Advisor issues REFINE but `can_refine()` returns False
  5. Ideas stuck in `refine` status after Stage 3 sub-loop completes without achieving DEVELOP
- **Action**: Idea is permanently removed. Status becomes `dropped` (terminal). No replacement generated (PIVOTs handle replacements).

### TOPIC_INFEASIBLE (Early Termination)

The pipeline can terminate early if the topic itself is assessed as unlikely to produce top-conference-worthy research. This prevents the user from investing hours of compute and attention on a direction that experienced reviewers would reject outright.

**There are two viability checkpoints**, each with distinct evidence and criteria:

#### Checkpoint 1: Post-Literature Viability Assessment (after Stage 1)

**Actor**: Advisor (Opus)
**Trigger**: Automatically runs after Stage 1 completes.
**Input**: The completed landscape table from Stage 1.

The Advisor evaluates the topic on 5 viability dimensions:

| Dimension | Red Flag (signals infeasibility) |
|-----------|--------------------------------|
| **Saturation** | The area is so crowded that any reasonable idea is already published or under review. The landscape table shows 10+ papers in the last 12 months all solving the same problem with marginal deltas. |
| **Foundation gap** | The topic lacks sufficient theoretical or empirical grounding. There are fewer than 3 credible papers to build on, and the field hasn't established evaluation standards. |
| **Scope mismatch** | The topic is either too broad to yield a focused contribution (e.g., "improve LLMs") or too narrow to sustain a full paper (e.g., a hyperparameter tuning trick). |
| **Conceptual incoherence** | The user's proposed combination of concepts is fundamentally incompatible -- the ideas being combined solve problems in domains with non-overlapping assumptions, or the extension requested contradicts known results. |
| **Timing** | The window has closed (key results already established, community has moved on) or hasn't opened (prerequisite capabilities don't exist yet). |

**Viability verdict**:
- **VIABLE**: Proceed to Stage 2. No issues found.
- **VIABLE_WITH_CAVEATS**: Proceed, but with specific warnings about areas to avoid or reframe. The caveats are injected into the Student's Stage 2 prompt as constraints.
- **INFEASIBLE**: Pipeline terminates with a detailed explanation (see output format below).

**Quality bar for INFEASIBLE**: The Advisor must provide **concrete evidence** from the landscape table, not just a hunch. At least 2 of the 5 dimensions must show clear red flags, with specific papers or facts cited. A single minor concern is NOT sufficient for INFEASIBLE -- the default is to proceed.

#### Checkpoint 2: Post-Hypothesis Viability Reassessment (after Stage 3)

**Trigger**: All ideas receive DROP verdict at the Stage 3 Advisor gate, AND the replacement idea generation retry (mini Stage 2 loop) also fails to produce any DEVELOP-worthy ideas.
**Evidence**: The Advisor has now seen the landscape AND evaluated concrete hypotheses -- this is much stronger evidence than Checkpoint 1 alone.

When this happens, the Orchestrator triggers a **Topic Viability Reassessment** by the Advisor:
- The Advisor reviews: the landscape table, all proposed ideas (including dropped ones), and the reasons for every DROP verdict.
- The Advisor determines whether the failures are due to (a) the Student's execution (fixable), or (b) fundamental limitations of the topic (not fixable by better ideation).
- If (b): INFEASIBLE verdict with a synthesis of why no viable idea could emerge from this topic.
- If (a): The Orchestrator allows one more mini Stage 2 retry with the Advisor's guidance on what direction to explore.

#### INFEASIBLE Output

When the pipeline terminates with INFEASIBLE, it produces a structured report instead of research plans:

**Output file**: `output/research_ideate/<topic_slug>/<YYYYMMDD>/viability_assessment.md`

```markdown
# Topic Viability Assessment

**Topic**: {topic}
**Assessment Date**: {date}
**Checkpoint**: {1 or 2}
**Verdict**: INFEASIBLE

## Executive Summary

{2-3 sentence explanation in plain, respectful language. Frame as "the evidence suggests"
rather than "your idea is bad". Focus on structural reasons, not the user's judgment.}

## Evidence

### Dimension Assessments

| Dimension | Assessment | Key Evidence |
|-----------|-----------|-------------|
| Saturation | {RED / YELLOW / GREEN} | {specific papers or facts} |
| Foundation | {RED / YELLOW / GREEN} | {specific papers or facts} |
| Scope | {RED / YELLOW / GREEN} | {specific papers or facts} |
| Coherence | {RED / YELLOW / GREEN} | {specific papers or facts} |
| Timing | {RED / YELLOW / GREEN} | {specific papers or facts} |

### Detailed Analysis

{For each RED dimension, a paragraph explaining:
- What the evidence shows
- Why this makes top-conference acceptance unlikely
- What would need to change for this dimension to become viable}

{If Checkpoint 2: include a section on "Ideas Attempted and Why They Failed" summarizing
the dropped hypotheses and their fatal flaws, showing that the pipeline did give the
topic a fair shot.}

## Alternative Directions

{The Advisor suggests 2-3 related but more promising research directions that the user
could explore instead. These should be:
- Genuinely related to the user's interests (not generic)
- Specific enough to be actionable (not "try a different area")
- Grounded in gaps identified during the literature review}

## What Would Make This Topic Viable

{Specific conditions under which the topic COULD work. E.g.:
- "If a new dataset for X became available..."
- "If the scope were narrowed to Y specifically..."
- "If combined with Z instead of W..."
This gives the user actionable paths to revisit the topic later.}
```

**Tone guidelines for INFEASIBLE output**:
- Never say "your idea is bad" or "this topic is worthless."
- Frame as: "Based on the current literature landscape, this specific direction faces significant structural challenges for top-conference acceptance."
- Acknowledge what IS interesting about the topic -- the user chose it for a reason.
- The alternative directions section is mandatory -- don't just reject, redirect.
- If the user's topic involves combining concepts, acknowledge the creative intent before explaining why the specific combination is problematic.

#### State Machine Integration

The pipeline state gains a new terminal status:

```
Pipeline-level terminal states:
  - COMPLETED (normal: produced final plans)
  - INFEASIBLE (early termination: topic not viable)
```

In `state.json`:
```json
{
  "pipeline_status": "infeasible",
  "infeasible_checkpoint": 1,
  "infeasible_reason": "saturation + timing",
  "infeasible_evidence": "See viability_assessment.md"
}
```

### Convergence Guarantee

The system always terminates because:

```
Max rounds:           3
Max REFINEs per idea: 3 (3 strikes → DROP, idea is dead)
Max PIVOTs total:     3
Viability checkpoint: After Stage 1 (can terminate early)
Viability checkpoint: After Stage 3 if all ideas DROP (can terminate early)
All ideas dead:       If pivot budget remains → back to Stage 2 with new ideas
                      If pivot budget exhausted → TOPIC_INFEASIBLE termination
After Round 3:        All non-APPROVED ideas forcibly dropped
If 0 approved:        TOPIC_INFEASIBLE termination (pipeline could not produce viable plans)
If < 3 approved:      Output what exists with a note
```

### Iteration State Machine (Per Idea)

```
                    ┌──────────────────┐
                    │   CANDIDATE      │  (created in Stage 2)
                    └────────┬─────────┘
                             │ Advisor DEVELOP
                    ┌────────v─────────┐
            ┌──────│   PLANNING       │  (Stage 4: experiment plan)
            │      └────────┬─────────┘
            │               │ Stage 5: submission
            │      ┌────────v─────────┐
            │  ┌───│   IN_REVIEW      │◄────── REFINE (from Stage 8)
            │  │   └────────┬─────────┘
            │  │            │ Both APPROVE + no severe/major open
            │  │   ┌────────v─────────┐
            │  │   │   APPROVED       │──────── → Final output (Stage 9)
            │  │   └──────────────────┘
            │  │
            │  └──► REFINE → back to PLANNING (exp issues)
            │               or back to CANDIDATE (hypothesis issues)
            │               refine_count++ (cumulative, max 3)
            │
            └──► DROPPED (fatal flaw, 3 strikes, or can_refine=False)
                    or
                 PIVOTED (Advisor PIVOT at Stage 6+, replaced by new idea)
```

**Valid statuses**: `candidate`, `planning`, `in_review`, `approved`, `refine`, `dropped`, `pivoted`
**Terminal statuses**: `approved`, `dropped`, `pivoted`

---

## 8. Skill Definitions

### 8.1 `research-ideate/SKILL.md` -- Orchestrator

```yaml
---
name: research-ideate
description: >
  Multi-agent research ideation and experiment design tool. Takes a research
  topic and autonomously produces 3-5 top-conference-level research plans
  through iterative advisor-student-reviewer cycles. Invoke when the user
  wants to brainstorm research directions, generate research proposals,
  or design experiments for a research topic.
user_invocable: true
---
```

**Responsibilities**:
- Parse user input: topic text, paper titles, constraints (compute, focus areas, venues)
- Initialize workspace: create `proposal_space/` directory structure, `state.json`
- Execute the 9-stage pipeline by spawning role agents
- After each agent returns: write output to files, log interaction, update state
- At quality gates: check pass criteria, decide retry/proceed
- At Stage 8: aggregate reviews, decide per-idea fate
- At Stage 9: compile final output

**Model**: Opus (this is the main conversation)
**Tools**: Agent, Bash (Python helpers), Read, Write, Glob

### 8.2 `research-ideate/ri-student.md` -- Student Role Reference

Not a standalone skill. This file contains the **role prompt template** that the orchestrator injects into Agent calls for the Student role.

**Key sections**:
- Role definition: "You are a motivated ML PhD student..."
- Anti-hallucination instructions: "Only cite papers you have found via WebSearch. Include arXiv IDs."
- Stage-specific task templates (parameterized by the orchestrator)
- Output format requirements (structured markers for parsing)
- Revision instructions (how to address reviewer feedback)

**Model**: Sonnet (specified in Agent call by orchestrator)
**Tools needed**: WebSearch, WebFetch, Read

### 8.3 `research-ideate/ri-advisor.md` -- Advisor Role Reference

**Key sections**:
- Role definition: "You are a tenured professor (指導教授)..."
- Constructive critic stance: "Help the student succeed. Kill ideas only when fundamentally flawed."
- Quality rubrics: parameterized by current standard (lenient/moderate/strict)
- Cross-review instructions: "Read the VP's prior review. Provide a different perspective."
- Decision format: APPROVE / REFINE / PIVOT / DROP with required justification

**Model**: Opus
**Tools needed**: Read, WebSearch (occasional)

### 8.4 `research-ideate/ri-visiting-prof.md` -- VP Role Reference

**Key sections**:
- Role definition: "You are a visiting professor (客座教授) from a different institution..."
- Adversarial stance: "Find weaknesses. What would a skeptical top-venue reviewer say?"
- Cross-review instructions: "Read the Advisor's review. Deliberately look for issues they missed."
- Attack vector requirement: "For each plan, identify top-3 likely reviewer attacks + defenses."
- Recent work check: "Use WebSearch to check for concurrent/scooping work from last 3 months."

**Model**: Opus
**Tools needed**: Read, WebSearch

---

## 9. Prompt Design

### 9.1 Student -- Literature Search (Stage 1)

```
You are a highly motivated ML PhD student working on the following research topic:
"{topic}"

{if paper_titles}
Your advisor has pointed you to these papers as starting points:
{paper_titles_list}
Find each paper via WebSearch. Read their abstracts and key contributions.
{/if}

YOUR TASK: Build a comprehensive prior-art landscape for this topic.

1. Search for 15-25 related papers using WebSearch. Try multiple query variations:
   - Direct topic keywords
   - Key method names from the field
   - "survey" or "benchmark" + topic for overview papers
   - Recent papers (2024-2026) for current state-of-the-art

2. For each paper found, extract:
   - Title, authors, year, venue
   - arXiv ID (required -- if you cannot find one, note it)
   - Core contribution (2-3 sentences)
   - Method summary
   - Key results/claims

3. Build a prior-art landscape table:
   | Paper | Core Claim | What It Solves | What It Does NOT Solve | Why Naive Follow-up = Low Novelty | Remaining Gap |

4. Summarize: which sub-areas are crowded? Which gaps are underexplored? What recent trends could be leveraged?

IMPORTANT:
- Only include papers you actually found via WebSearch. Never fabricate titles or results.
- If you cannot find a paper the advisor mentioned, say so explicitly.
- Prefer papers with arXiv IDs or DOIs for verifiability.
```

### 9.1b Advisor -- Topic Viability Assessment (Checkpoint 1, after Stage 1)

```
You are a tenured professor (指導教授) evaluating whether a research topic
has sufficient potential to produce work publishable at top venues (ICML,
NeurIPS, ICLR, or equivalent).

RESEARCH TOPIC: "{topic}"

{if paper_titles}
The student was also asked to build on these papers:
{paper_titles_list}
{/if}

LITERATURE LANDSCAPE (from Stage 1):
{landscape_content}

YOUR TASK: Assess this topic's viability for top-conference research.

Evaluate on these 5 dimensions:

1. SATURATION: Is the area so crowded that any reasonable idea is already
   published? Count papers from the last 12 months solving essentially the
   same problem. >10 with marginal deltas = RED flag.

2. FOUNDATION: Does this topic have sufficient theoretical/empirical grounding?
   Are there credible papers to build on? Are evaluation standards established?
   <3 foundation papers = RED flag.

3. SCOPE: Is the topic appropriately sized? Too broad ("improve LLMs") or too
   narrow (a hyperparameter trick) cannot sustain a full paper. Either extreme
   = RED flag.

4. CONCEPTUAL COHERENCE: If the topic asks to combine or extend concepts,
   are these concepts actually compatible? Do their underlying assumptions
   overlap? Does the proposed extension contradict known results?
   Fundamental incompatibility = RED flag.

5. TIMING: Has the window closed (results established, community moved on)?
   Or hasn't it opened (prerequisite capabilities don't exist)?
   Bad timing = RED flag.

OUTPUT FORMAT:

VIABILITY_VERDICT: {VIABLE | VIABLE_WITH_CAVEATS | INFEASIBLE}

DIMENSION_SATURATION: {GREEN | YELLOW | RED}
EVIDENCE_SATURATION: {specific papers or facts from landscape}

DIMENSION_FOUNDATION: {GREEN | YELLOW | RED}
EVIDENCE_FOUNDATION: {specific papers or facts from landscape}

DIMENSION_SCOPE: {GREEN | YELLOW | RED}
EVIDENCE_SCOPE: {specific reasoning}

DIMENSION_COHERENCE: {GREEN | YELLOW | RED}
EVIDENCE_COHERENCE: {specific reasoning, especially if user asked to combine concepts}

DIMENSION_TIMING: {GREEN | YELLOW | RED}
EVIDENCE_TIMING: {specific papers or trends}

{if VIABLE_WITH_CAVEATS}
CAVEATS:
1. {specific area to avoid or reframe, with reason}
2. ...
{/if}

{if INFEASIBLE}
INFEASIBLE_SUMMARY: {2-3 sentence explanation. Be respectful. Focus on
structural reasons, not the user's judgment. Acknowledge what IS interesting
about the topic.}

ALTERNATIVE_DIRECTIONS:
1. {related but more promising direction, specific enough to be actionable}
2. {another direction}
3. {another direction}

WHAT_WOULD_MAKE_VIABLE: {specific conditions under which the topic COULD work}
{/if}

GUIDELINES:
- The default is VIABLE. Only issue INFEASIBLE with strong evidence.
- At least 2 dimensions must be RED to justify INFEASIBLE.
- Cite specific papers or facts from the landscape table, not gut feelings.
- If the topic is unusual but has potential, err on the side of VIABLE_WITH_CAVEATS.
- Remember: your job is to save the user time on hopeless directions,
  not to be a gatekeeper against creative ideas.
```

### 9.1c Advisor -- Topic Viability Reassessment (Checkpoint 2, after Stage 3 failure)

```
You are a tenured professor (指導教授). Your student has been unable to develop
ANY viable hypothesis for the following research topic, even after multiple
attempts.

RESEARCH TOPIC: "{topic}"

LITERATURE LANDSCAPE:
{landscape_content}

ALL IDEAS PROPOSED AND DROPPED:
{for each dropped idea:}
IDEA: {title}
DROP REASON: {advisor's reason for DROP verdict}
{end for}

YOUR TASK: Determine whether the failure is due to:
(a) The student's execution -- they could find viable ideas with better guidance
(b) Fundamental limitations of the topic -- no amount of better ideation would help

If (a): Provide specific guidance for one more attempt.
If (b): Issue INFEASIBLE verdict.

OUTPUT FORMAT:

REASSESSMENT_VERDICT: {RETRY_WITH_GUIDANCE | INFEASIBLE}

{if RETRY_WITH_GUIDANCE}
FAILURE_ANALYSIS: {what the student kept getting wrong}
GUIDANCE:
1. {specific unexplored direction in the landscape}
2. {specific methodological angle to try}
3. {what to avoid based on past failures}
{/if}

{if INFEASIBLE}
FAILURE_PATTERN: {synthesis of why every idea failed -- what structural property
of this topic makes it resistant to top-conference-level ideation}
INFEASIBLE_SUMMARY: {respectful 2-3 sentence summary}
ALTERNATIVE_DIRECTIONS:
1. {related but more promising direction}
2. {another direction}
3. {another direction}
WHAT_WOULD_MAKE_VIABLE: {specific conditions}
{/if}
```

### 9.2 Student -- Idea Generation (Stage 2)

```
Based on the literature landscape below, generate 8-10 candidate research ideas.

{landscape_content}

For each idea, provide:

=== IDEA: {short_slug} ===
TITLE: {paper-like title}
DESCRIPTION: {one paragraph -- what's new, why it matters}
GAP_ADDRESSED: {which row in the landscape table this targets}
CLOSEST_PRIOR: {most similar existing work + how this differs}
NOVELTY_CONFIDENCE: {HIGH / MEDIUM / LOW}
FEASIBILITY: {compute needs, data needs, rough complexity}
=== END IDEA ===

GUIDELINES:
- Each idea must address a SPECIFIC gap from the landscape table.
- Ideas should be diverse -- don't generate 8 variations of the same approach.
- Include at least 2 "ambitious but feasible" ideas and at least 2 "safe and solid" ideas.
- It's OK to have rough ideas at this stage. Volume > polish.
{if round > 1}

IDEAS ALREADY TRIED (avoid repeating or trivially extending these):
{dropped_and_pivoted_ideas}
{/if}
```

### 9.3 Advisor -- Hypothesis Gate (Stage 3)

```
You are a tenured professor (指導教授) advising a PhD student on their research.

Your student has developed hypotheses for {N} research ideas. Review each one.

CURRENT QUALITY STANDARD: {quality_standard}
{quality_rubric_for_standard}

{if vp_prior_review}
The Visiting Professor reviewed the prior round. Their comments:
{vp_prior_review_content}
Consider their perspective but provide your OWN independent assessment.
{/if}

For each hypothesis below, evaluate and output:

=== IDEA: {slug} ===
VERDICT: {DEVELOP | REFINE | DROP}
SCORE_NOVELTY: {1-5}
SCORE_THEORY: {1-5}
SCORE_FEASIBILITY: {1-5}
{if REFINE}
ISSUES:
1. [{category}] {specific issue}
2. [{category}] {specific issue}
SUGGESTIONS:
1. {specific actionable fix}
2. {specific actionable fix}
{/if}
{if DROP}
FATAL_FLAW: {why this is unsalvageable}
{/if}
=== END IDEA ===

AFTER ALL IDEAS, provide:
RANKING: {ordered list of ideas by promise, with 1-line justification each}

GUIDELINES:
- Your goal is to help the student succeed. Be constructive.
- Kill ideas only when they have fundamental flaws (e.g., the approach provably cannot work, or the exact method was already published).
- For REFINE, be specific: "The theoretical claim in paragraph 3 assumes X, but Y contradicts this. Consider Z instead."
- Do not give vague feedback like "needs more work" or "not novel enough."

EVALUATION TECHNIQUES YOU MUST APPLY:
1. CROSS-DOMAIN ANALOGY TEST: For each idea, identify the closest known method from ANY field.
   Can this idea be reduced to that method in one sentence? If yes, note it as a critical issue.
   Example: "This is essentially Naive Bayes applied to trajectory scoring."
2. COUNTEREXAMPLE PRESSURE TEST: For each idea, find 3 concrete scenarios where the method
   would fail or produce wrong results. Check if the method design addresses these.
3. CIRCULARITY CHECK: Look for bootstrap estimation loops. Does any step estimate X using Y
   where Y itself depends on X? Flag and require a fix.
4. MULTI-LEVEL FRAMEWORK TEST: Is this a single-trick heuristic? If so, suggest how to
   escalate it into a multi-level framework (each level removes one limitation).
5. CROSS-OVER ACTIONABILITY: If the idea claims to bridge two areas, demand a concrete
   closed-loop feedback mechanism. "Shared math tools" is not cross-over.
```

### 9.4 Visiting Professor -- External Review (Stage 7)

```
You are a visiting professor (客座教授) from a different institution, invited to
review research proposals. You have no stake in these ideas succeeding.

The Advisor has already reviewed these proposals. Their review:
{advisor_review_content}

YOUR TASK: Stress-test each proposal from an independent, external perspective.
Deliberately find issues the Advisor has NOT raised. Do not merely agree with their assessment.

CURRENT QUALITY STANDARD: {quality_standard}
{quality_rubric_for_standard}

For each proposal:

1. CHECK NOVELTY: Use WebSearch to look for very recent papers (last 3 months) that might
   scoop or closely overlap with this idea. Search for the specific method name + application area.

2. CHECK THEORY: Are the theoretical claims logically sound? Are there hidden assumptions?
   Could a reviewer poke holes in the reasoning?

3. CHECK EXPERIMENTS: Do the experiments actually test the hypothesis? Are the baselines
   the strongest available? Is anything missing from the ablation?

4. IDENTIFY TOP-3 REVIEWER ATTACKS: What would a skeptical ICML/NeurIPS/ICLR reviewer say?
   For each attack, suggest a specific preemptive defense.

Output per idea:

=== IDEA: {slug} ===
VERDICT: {APPROVE | REFINE | DROP}
RECENT_WORK_CHECK: {papers found that might overlap, or "no close overlap found"}
ISSUES:
1. [{severity: critical|major|minor}] {specific issue the Advisor missed}
ATTACK_VECTORS:
1. ATTACK: {what a reviewer would say}
   DEFENSE: {how to preempt this in the paper}
2. ...
3. ...
=== END IDEA ===
```

### 9.5 Student -- Revision After REFINE

```
You are revising your research proposal based on reviewer feedback.

REVIEWER FEEDBACK:
{combined_advisor_and_vp_feedback}

YOUR PREVIOUS SUBMISSION:
{previous_hypothesis_or_plan}

REVISION GUIDELINES:

1. DO NOT DEFEND the original approach. If a reviewer found a weakness, acknowledge it.
   Then fix it. Defending weak points wastes time and loses trust.

2. TURN EVERY COUNTEREXAMPLE INTO AN INNOVATION POINT.
   For each concrete failure case the reviewers raised, ask: "What mechanism would make
   this criticism invalid?" That mechanism becomes a new feature of your method.
   Example: "correct formula wrongly penalized" → add causal discrimination conditioning
   on prefix context.

3. ESCALATE FROM HEURISTIC TO FRAMEWORK.
   If a reviewer says "this is just X", acknowledge it:
   - Level 1 = your current method (essentially X)
   - Level 2 = remove limitation A of X (specific fix)
   - Level 3 = remove limitation B (specific fix)
   - Level 4 = remove limitation C (specific fix)
   Each level's ablation answers one independent scientific question.

4. UPGRADE OBSERVATIONAL CLAIMS TO ACTIONABLE MECHANISMS.
   If a reviewer says "the cross-over claim is weak", find a concrete closed-loop:
   output of component A → improves input of component B → improves output of A.
   If no closed loop exists, honestly downgrade the claim.

5. SEARCH FOR ADJACENT-FIELD TECHNIQUES.
   When a reviewer draws a cross-domain analogy ("this is like MMR in RecSys"),
   use WebSearch to find the latest work in that adjacent field. Borrow specific
   techniques to strengthen your method.

6. CHECK FOR CIRCULARITY after revision.
   Did your fix introduce a new circular dependency? Verify.

Address EACH numbered issue from the reviewers specifically.
Mark which issues you addressed and how.
```

---

## 10. Python Helpers

Located at `.claude/skills/research-ideate/helpers/`.

### 10.1 `state_manager.py`

```python
"""Pipeline state management for research-ideate."""

import json
from pathlib import Path
from datetime import datetime

QUALITY_STANDARDS = {1: "lenient", 2: "moderate", 3: "strict"}

def init_state(workspace: Path, topic: str, paper_titles: list[str],
               constraints: dict) -> dict:
    """Initialize a new pipeline state."""

def load_state(workspace: Path) -> dict:
    """Load state from state.json."""

def save_state(workspace: Path, state: dict) -> None:
    """Write state to state.json with timestamp."""

def advance_stage(workspace: Path, next_stage: str) -> dict:
    """Move pipeline to next stage. Returns updated state."""

def update_idea_status(workspace: Path, slug: str, status: str,
                       reason: str = "") -> dict:
    """Update a single idea's status (approved/refine/pivot/drop)."""

def get_quality_standard(round_num: int) -> str:
    """Return quality standard name for given round."""

def check_convergence(state: dict) -> bool:
    """Check if pipeline should proceed to Stage 9."""

def get_ideas_by_status(state: dict, status: str) -> list[str]:
    """Return idea slugs with given status."""
```

### 10.2 `log_interaction.py`

```python
"""Interaction logging for complete audit trail."""

from pathlib import Path
from datetime import datetime

def log_interaction(workspace: Path, stage: str, round_num: int,
                    role: str, input_summary: str, full_output: str,
                    decision: str | None = None) -> Path:
    """
    Append an interaction to the log directory.

    Writes to: interaction_log/{stage}_{role}_round{N}.md
    Format:
      # {Stage} -- {Role} (Round {N})
      **Timestamp**: ...
      **Input context**: {input_summary}
      ## Output
      {full_output}
      ## Decision
      {decision or "N/A"}
    """
```

### 10.3 `parse_review.py`

```python
"""Extract structured data from reviewer text output."""

import re

def parse_review(review_text: str) -> dict:
    """
    Parse structured markers from review text.

    Returns:
    {
      "ideas": {
        "slug": {
          "verdict": "APPROVE|REFINE|PIVOT|DROP",
          "scores": {"novelty": int, "theory": int, "feasibility": int},
          "issues": [{"category": str, "description": str}],
          "suggestions": [str],
          "attack_vectors": [{"attack": str, "defense": str}]
        }
      },
      "ranking": [{"slug": str, "justification": str}]
    }
    """

def extract_idea_blocks(text: str) -> list[tuple[str, str]]:
    """Extract (slug, block_content) pairs from === IDEA: slug === markers."""

def extract_verdict(block: str) -> str:
    """Extract VERDICT: line from an idea block."""

def extract_scores(block: str) -> dict:
    """Extract SCORE_* lines into {dimension: int} dict."""

def extract_issues(block: str) -> list[dict]:
    """Extract numbered ISSUES into structured list."""
```

### 10.4 `format_final_plan.py`

```python
"""Render final research plan .md from structured data."""

def format_plan(idea_slug: str, hypothesis: str, plan: str,
                reviews: list[str], rank: int) -> str:
    """
    Render a comprehensive 12-section research plan.

    Template sections:
    1. Title
    2. One-sentence thesis
    3. Research area
    4. Closest prior work (3-5 papers)
    5. Problem gap
    6. Theoretical basis
    7. Method sketch
    8. Implementation plan (MVP + full)
    9. Experimental plan
    10. Paper storyline
    11. Novelty risk assessment
    12. Final verdict + recommended venue
    + Appendix: Review history summary
    """

def format_summary_table(plans: list[dict]) -> str:
    """
    Render comparison table:
    | Rank | Title | Area | Novelty | Feasibility | Confidence | Venue |
    """
```

---

## 11. Logging Strategy

**Requirement**: ALL intermediate interactions must be recorded -- advisor reviews, student ideas, revisions, decisions. The user reviews results after the run completes.

### Log Directory Structure

```
proposal_space/interaction_log/
├── stage1_student_literature_round1.md
├── stage2_student_ideation_round1.md
├── stage3_student_hypothesis_idea1_round1.md
├── stage3_student_hypothesis_idea2_round1.md
├── ...
├── stage3_advisor_gate_round1.md
├── stage3_student_revision_idea3_round1.md    (if REFINE at gate)
├── stage3_advisor_gate_revision_round1.md     (re-review after revision)
├── stage4_student_plan_idea1_round1.md
├── ...
├── stage6_advisor_review_round1.md
├── stage7_vp_review_round1.md
├── stage8_orchestrator_decision_round1.md
├── stage3_student_hypothesis_idea3_round2.md  (REFINE from Round 1)
├── ...
├── stage9_final_ranking.md
└── pipeline_summary.md                        (auto-generated at end)
```

### What Each Log Contains

```markdown
# Stage 6: Advisor Review -- Round 2

**Timestamp**: 2026-03-27T14:23:45
**Role**: Advisor (Opus)
**Quality Standard**: moderate
**Input Context**: 5 experiment plans (idea1-idea5), VP review from Round 1

---

## Full Output

{complete, unedited agent output}

---

## Decisions Made

- idea1: APPROVE (strong novelty + sound theory)
- idea2: REFINE (issues: missing baseline X, ablation Y)
- idea3: APPROVE (addressed all Round 1 concerns)
- idea4: DROP (novelty claim invalidated by Chen et al. 2026)
- idea5: REFINE (experiment doesn't test the actual hypothesis)
```

### Pipeline Summary (Auto-Generated)

At the end of the run, the orchestrator generates `proposal_space/interaction_log/pipeline_summary.md`:

```markdown
# Pipeline Summary

**Topic**: {topic}
**Run Date**: 2026-03-27
**Total Rounds**: 2
**Total Agent Calls**: 23 (Student: 14, Advisor: 6, VP: 3)

## Idea Lifecycle

| Idea | Created | Round 1 | Round 2 | Final Status |
|------|---------|---------|---------|-------------|
| contrastive-cot | R1 | REFINE | APPROVE | Final Plan #1 |
| token-contrast | R1 | APPROVE | -- | Final Plan #2 |
| meta-decode | R1 | PIVOT | -- | Replaced by adaptive-contrast |
| ...

## Key Decision Points

1. Round 1, Stage 3: Advisor dropped "naive-ensemble" (fatal: exact method in Li 2025)
2. Round 1, Stage 8: VP found concurrent work for "meta-decode", triggered PIVOT
3. Round 2, Stage 6: All remaining ideas approved under moderate standard

## Review Highlights

{key excerpts from advisor/VP reviews that drove decisions}
```

---

## 12. File & Directory Structure

### Skill Files

```
.claude/skills/research-ideate/
├── SKILL.md                      # Orchestrator skill definition
├── ri-student.md                 # Student role prompt template
├── ri-advisor.md                 # Advisor role prompt template
├── ri-visiting-prof.md           # VP role prompt template
└── helpers/
    ├── state_manager.py
    ├── log_interaction.py
    ├── parse_review.py
    └── format_final_plan.py
```

### Output Structure (Per Run)

```
output/research_ideate/
└── contrastive-decoding-small-lm/          # topic slug
    └── 20260327/                            # run date
        ├── plan_1_contrastive_cot.md        # Final plan #1
        ├── plan_2_token_contrast.md         # Final plan #2
        ├── plan_3_adaptive_contrast.md      # Final plan #3
        ├── summary.md                       # Comparison table + recommendations
        └── proposal_space/                  # Complete workspace (audit trail)
            ├── state/
            │   ├── state.json
            │   └── submission_round{N}.json
            ├── literature/
            │   └── landscape_round{N}.md
            ├── ideas/
            │   └── candidates_round{N}.md
            ├── hypotheses/
            │   └── hypothesis_{slug}_round{N}.md
            ├── plans/
            │   └── plan_{slug}_round{N}.md
            ├── reviews/
            │   ├── advisor_hypothesis_round{N}.md
            │   ├── advisor_round{N}.md
            │   └── vp_round{N}.md
            └── interaction_log/
                ├── stage1_student_literature_round1.md
                ├── ...
                └── pipeline_summary.md
```

---

## 13. Cost Estimate

### Per-Agent-Call Cost

| Agent Call | Model | Input (est.) | Output (est.) | Cost |
|-----------|-------|-------------|--------------|------|
| Student: literature search | Sonnet | ~5K | ~8K | ~$0.05 |
| Student: idea generation | Sonnet | ~10K | ~12K | ~$0.08 |
| Student: hypothesis (per idea) | Sonnet | ~15K | ~10K | ~$0.10 |
| Student: experiment plan (per idea) | Sonnet | ~20K | ~15K | ~$0.15 |
| Student: revision (per idea) | Sonnet | ~25K | ~12K | ~$0.15 |
| Advisor: hypothesis gate (all ideas) | Opus | ~30K | ~8K | ~$1.20 |
| Advisor: full review (all plans) | Opus | ~40K | ~10K | ~$1.50 |
| VP: full review (all plans) | Opus | ~45K | ~10K | ~$1.70 |
| Advisor: final ranking | Opus | ~30K | ~5K | ~$1.00 |

### Full Run Scenarios

| Scenario | Rounds | Agent Calls | Estimated Cost |
|----------|--------|------------|---------------|
| **Best case** (most approve Round 2) | 2 | ~20 | $60-80 |
| **Typical** (some REFINE, 1 PIVOT) | 2.5 avg | ~25 | $80-120 |
| **Worst case** (heavy iteration) | 3 full | ~35 | $120-180 |

**Sonnet cost savings**: Using Sonnet for the Student (who makes ~50-60% of all calls by volume) saves approximately 60-70% vs. all-Opus.

---

## 14. Future Extensibility

### Extension Points for Experiment Execution

The design explicitly supports adding experiment execution after ideation:

1. **State machine extension**: `state.json` can add Stages 10-15 (code generation, sandbox execution, result analysis) without modifying existing stages.

2. **New role skill**: `ri-engineer.md` (Research Engineer) reads from `plans/` and writes to:
   ```
   proposal_space/
   ├── code/{slug}/          # Generated experiment code
   │   ├── main.py
   │   └── requirements.txt
   ├── experiments/{slug}/   # Execution results
   │   ├── run_log.txt
   │   ├── metrics.json
   │   └── figures/
   └── analysis/{slug}/      # Result analysis
       └── analysis_round{N}.md
   ```

3. **Self-healing loop**: Adopt AutoResearchClaw's Stage 12-13 pattern (run -> diagnose -> repair -> re-run, max 10 iterations).

4. **Result feedback**: Experiment results feed back into the review loop. Advisor and VP can evaluate whether results support the hypothesis, potentially triggering REFINE on the method.

5. **VerifiedRegistry**: Anti-hallucination for experiment results. Only results traced to actual code execution are marked as verified.

### Extension Points for Cross-Run Learning (MetaClaw-Inspired)

1. **Lesson extraction**: After each run, extract lessons from PIVOTs, DROPs, and REFINE cycles.
2. **Skill generation**: Convert lessons into reusable prompt overlays (e.g., "In this research area, always check for X baseline").
3. **Skill injection**: Inject relevant skills into future runs based on topic similarity.
4. **Skill tracking**: Track which skills correlate with approved vs. dropped ideas.

This is a future enhancement, not part of the initial implementation.

---

## 15. Implementation Sequencing

### Phase 1: Python Helpers (Pure Utility)

1. `state_manager.py` -- state read/write, stage advancement, quality standard lookup
2. `log_interaction.py` -- interaction logging
3. `parse_review.py` -- structured data extraction from review text
4. `format_final_plan.py` -- 12-section template rendering

**Testing**: Unit tests under `tests/research_ideate/` for all helpers.

### Phase 2: Minimal Pipeline (Stages 1-2)

1. `SKILL.md` orchestrator -- input parsing, workspace initialization, Stages 1-2 only
2. `ri-student.md` -- literature search + idea generation prompts

**Verification**: Run with a test topic, verify literature landscape and idea list quality.

### Phase 3: Advisor Integration (Stage 3 Gate)

1. `ri-advisor.md` -- hypothesis review prompt
2. Orchestrator: Stage 3 with Advisor gate and REFINE sub-loop

**Verification**: Run through Stage 3, verify Advisor gives structured reviews, REFINE loop works.

### Phase 4: Full Review Loop (Stages 4-8)

1. Student: experiment planning prompts
2. `ri-visiting-prof.md` -- adversarial review prompt
3. Orchestrator: Stages 4-8 with dual review, decision logic, iteration

**Verification**: Run full pipeline with 2+ rounds, verify iteration mechanics.

### Phase 5: Final Output (Stage 9)

1. `format_final_plan.py` integration
2. Summary table generation
3. Pipeline summary log

**Verification**: End-to-end run producing 3-5 final research plans.

### Phase 6: Polish & Testing

1. Edge cases: insufficient literature, all ideas dropped, max iterations hit
2. Full test suite for Python helpers
3. Documentation
