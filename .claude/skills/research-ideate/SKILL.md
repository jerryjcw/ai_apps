---
name: research-ideate
description: >
  Multi-agent research ideation and experiment design tool. Takes a research
  topic and autonomously produces 3-5 top-conference-level research plans
  through iterative advisor-student-reviewer cycles. Invoke when the user
  wants to brainstorm research directions, generate research proposals,
  or design experiments for a research topic. Also trigger on "research ideation",
  "generate research ideas", "design experiments for", "what could I publish on".
user_invocable: true
---

# Research Ideation Pipeline

An end-to-end multi-agent pipeline that takes a research topic and produces
3-5 research plans at top AI conference quality through iterative
advisor-student-reviewer cycles.

**Design document**: `docs/auto_research/high_level_design.md`
**Python helpers**: `applications/auto_research/helpers/`

---

## Before You Begin: Gather Parameters

Ask the user for the following in a single message:

1. **Research topic** — text description of the research direction.
2. **Intent constraints** — what the user ACTUALLY wants as output.
   Ask explicitly: "What kind of result do you want? For example:
   a new algorithm/method, an analysis/understanding of why X works,
   a practical tool, a theoretical result, or a benchmark/evaluation?"
   Record 1-3 **intent constraints** as concrete requirements, e.g.:
   - "Must produce a new optimization algorithm (not just analysis)"
   - "Must demonstrate faster convergence (not just characterization)"
   - "Must result in a deployable tool (not just a paper)"
   These are HARD REQUIREMENTS that every surviving idea must collectively
   satisfy. Store them in `state.json` under the `intent_constraints` field.
3. **Reference papers** (optional) — paper titles the user wants included.
   You will search for these yourself if no URLs are provided.
4. **Compute constraints** (optional) — max GPUs, GPU model.
   Default: 8x H100.
5. **Focus areas** (optional) — e.g., "LLM", "reasoning", "RL".
6. **Target venues** (optional) — e.g., ICML, NeurIPS, ICLR.
   Default: ICML, NeurIPS, ICLR.

---

## File-Based Truth (OVERARCHING PRINCIPLE)

The `proposal_space/` directory is the **single source of truth** for the
entire pipeline. Every agent — Student, Advisor, VP — must read its inputs
from files and write its outputs to files. Conversation context is transient
and unreliable across sessions.

**Rules:**

1. **Read from files, not memory.** When an agent needs the current plan,
   the latest review, or the review tracker, it must read the file on disk.
   Do not pass conversation-context summaries or orchestrator paraphrases.
   Pass either file paths (for agents that can read files) or inline the
   file content verbatim (for agents whose prompts need it).

2. **Write before proceeding.** Every agent output that will be consumed
   by a later step must be written to the appropriate file BEFORE the
   orchestrator moves to the next step. The write-first rule is not just
   for reviews — it applies to plans, hypotheses, literature, and ideas.
   If a file wasn't written, the next step that reads it will fail or
   hallucinate, and the pipeline's integrity is broken.

3. **Files are cumulative across rounds.** Each round produces new files
   (e.g., `plan_{slug}_round2_revised.md`, `advisor_{slug}_round2.md`).
   Prior rounds' files are NOT overwritten — they are the historical record.
   When an agent needs "the latest plan," it reads the highest-round
   revised version. When it needs "all reviews," it reads every
   `reviews/*_{slug}_round*.md` file.

4. **The review tracker is derived, not primary.** `review_tracker.json`
   is a structured index extracted from review files. If there's a conflict
   between the tracker and the review file, the review file wins. The
   tracker exists for programmatic queries (e.g., `can_approve()`); the
   review files exist for full reasoning.

5. **Per-idea, per-round files.** Reviews, plans, and hypotheses are saved
   as `{type}_{slug}_round{N}.md`. Do NOT merge multiple ideas into one
   file (e.g., "all-ideas_round3.md") — this makes it impossible for an
   agent reviewing one idea to read only that idea's review without parsing
   a multi-idea document. One idea per file, one round per file.

---

## Round Numbering and File Resolution

All files use `round{N}` in their names. `N` is the **pipeline round number**
stored in `state.json` as `current_round`. It starts at 1 and increments
when `start_new_round()` is called (after convergence fails and a new
review cycle begins).

### Writing: what N to use

When WRITING a file, always use the CURRENT round number from `state.json`:

```python
state = load_state(workspace)
N = state["current_round"]
```

- Student produces a plan → `plan_{slug}_round{N}.md`
- Student revises a plan → `plan_{slug}_round{N}_revised.md`
- Advisor reviews → `advisor_{slug}_round{N}.md`
- VP reviews → `vp_{slug}_round{N}.md`
- Re-review within the same round → append cycle: `advisor_{slug}_round{N}_cycle{C}.md`
  where C starts at 2 (the initial review for that round has no cycle suffix).

### Reading: which N to use

Different file types have different update frequencies. The reading rule
depends on WHAT you need, not on the current round:

| What you need | Resolution rule | Why |
|---|---|---|
| **The latest plan** | Glob `plans/plan_{slug}_round*` → pick highest-N `_revised.md`, else highest-N `.md` | Plans are revised in every refine cycle; the latest version has the highest N |
| **The latest hypothesis** | Glob `hypotheses/hypothesis_{slug}_round*` → same logic | Hypotheses may be revised in Stage 3c |
| **The latest ideas** | Glob `ideas/candidates_round*` → highest N | **Usually round 1** — ideas only regenerate on PIVOT. Do NOT hardcode N = current_round |
| **The latest literature** | Glob `literature/landscape_round*` → highest N | **Usually round 1** — literature only regenerates on PIVOT |
| **Advisor review from THIS round** | `reviews/advisor_{slug}_round{N}.md` where N = current_round | Exact match — this round's review |
| **VP review from THIS round** | `reviews/vp_{slug}_round{N}.md` where N = current_round | Exact match |
| **Advisor review from PRIOR round** | `reviews/advisor_{slug}_round{N-1}.md` (N-1 = current_round - 1) | For VP to see what Advisor said last round |
| **ALL reviews for an idea** | Glob `reviews/*_{slug}_round*.md` → read all | For final plan generation (Stage 9) |
| **Review tracker** | `state/review_tracker.json` | Always one file, always current |
| **State** | `state/state.json` | Always one file, always current |

**Key insight**: Plans and reviews accumulate new round files every cycle.
Ideas and literature stay at their original round number until a PIVOT
regenerates them. Always glob when reading — never assume the file's N
matches the current round.

---

## Pipeline Constants

```
HELPERS_DIR = applications/auto_research/helpers
VENV_ACTIVATE = source applications/auto_research/.venv/bin/activate
MAX_ROUNDS = 3
MAX_REFINES_PER_IDEA = 3
MAX_PIVOTS = 3
MIN_IDEAS = 10
MAX_SIMILAR_PER_SUBTOPIC = 3
MAX_IDEA_GEN_RETRIES = 5
MIN_APPROVED = 3
```

---

## Step 0: Initialize Workspace

1. Determine the output directory:
   ```
   OUTPUT_BASE = output/research_ideate/<topic_slug>/<YYYYMMDD>/
   ```
2. Run the Python state manager to initialize:
   ```bash
   source applications/auto_research/.venv/bin/activate && python -c "
   from helpers.state_manager import init_workspace, init_state
   from pathlib import Path
   ws = Path('<OUTPUT_BASE>')
   init_workspace(ws)
   init_state(ws, '<topic>', <paper_titles_list>, <constraints_dict>)
   "
   ```
3. Read back `proposal_space/state/state.json` to confirm initialization.

---

## Step 1: Literature Collection (Stage 1)

Literature collection has TWO passes: a breadth search and a depth pass.

### 1a: Breadth Search

**Spawn a Student agent** (Sonnet) with the literature search task.

```
Agent(
  subagent_type="general-purpose",
  model="sonnet",
  prompt=<read ri-student.md Section 1 and fill in: topic, paper_titles>
)
```

**After agent returns:**
1. Write the output to `proposal_space/literature/landscape_round{N}.md`
2. Log the interaction
3. Check quality gate: >= 10 papers with abstracts and landscape table
   with "Remaining Gap" column populated. If not, retry with broader
   search terms (max 2 retries).

### 1b: Citation Chain Depth Pass

**Spawn a second Student agent** (Sonnet) with the depth pass task.
Pass the breadth search output (read from `literature/landscape_round{N}.md`).

The Student must:
1. Pick the 5 most relevant papers from the breadth search.
2. Use WebFetch to read each paper's related work / references section.
3. Extract 5-10 papers that the breadth search MISSED — specifically:
   - Papers that describe the same problem using DIFFERENT terminology
     (these are the most dangerous scooping threats)
   - Foundational papers that the breadth-search papers all cite
   - Very recent papers (last 3 months) cited by the breadth-search papers
4. For each newly found paper, add it to the landscape table with the
   same columns (Core Claim, What It Solves, What It Does NOT Solve,
   Why Naive Follow-up = Low Novelty, Remaining Gap).

**After agent returns:**
1. Merge the depth pass output into the existing landscape file:
   append to `proposal_space/literature/landscape_round{N}.md`
   (add a `## Depth Pass Additions` section at the end — this is a
   same-round, same-step append, which is allowed. Cross-round
   modification of existing files is still prohibited.)
2. Log the interaction
3. Advance state to `stage_2_ideation`

**Quality gate**: Total papers (breadth + depth) >= 15. At least 3 papers
from the depth pass must use different terminology than the breadth search
queries (evidence that the Student actually followed citation chains, not
just re-searched the same keywords).

**Intent-alignment gate**: Check the "Underexplored Gaps (TARGET)" section.
For EACH intent constraint in `state.json["intent_constraints"]`, at least
one gap must directly address it. For example, if the user's intent is
"must produce a new optimization algorithm," but all gaps are about
analysis or merging, the orchestrator must send the Student back with:
"The following intent constraints have no corresponding gap: {list}.
Add at least one gap per missing constraint." Do NOT mark "optimizer
benchmarking" or "Muon variants" as AVOID if the user's intent is to
build a new optimizer — the crowded-area assessment must respect the
user's explicit intent.

---

## Step 2: Idea Generation (Stage 2)

**Spawn a Student agent** (Sonnet) with the idea generation task.

Pass the landscape markdown as context (read from `literature/landscape_round*.md`
→ highest N). Request 10+ candidate ideas using the structured
`=== IDEA: slug ===` format from ri-student.md Section 2.

**After agent returns:**
1. Write to `proposal_space/ideas/candidates_round{N}.md`
2. Log the interaction
3. Parse idea slugs from the output
4. For each idea, register in state:
   ```bash
   python -c "
   from helpers.state_manager import add_idea
   from pathlib import Path
   add_idea(Path('<OUTPUT_BASE>'), '<slug>', '<title>')
   "
   ```
5. Advance state to `stage_3_hypothesis`

**Quality gate — diversity and quantity:**

- **Minimum**: 10 distinct ideas.
- **Diversity rule**: No more than 3 ideas may target the same sub-topic
  or use substantially similar methods. If the Student generates 5 variations
  of "apply technique X to setting Y," only the 3 most distinct survive;
  the rest are discarded before proceeding.
- **Retry loop**: If fewer than 10 ideas after deduplication, send the
  Student back with: "The following sub-topics are already covered by 3
  ideas each: {list}. Generate {10 - current_count} NEW ideas that target
  DIFFERENT sub-topics or use DIFFERENT methods." Max 5 retry attempts.
- **Hard floor**: If after 5 retries the count is still < 10, proceed
  with whatever exists (minimum 3). If < 3, trigger Viability Checkpoint 2.
- **Intent-alignment rule**: For EACH intent constraint in
  `state.json["intent_constraints"]`, at least 2 ideas must directly
  address it. For example, if the user says "must produce a new
  optimization algorithm," at least 2 ideas must propose a new algorithm
  (not just analyze existing ones). If this is not met after initial
  generation, send the Student back with: "The following intent constraints
  have fewer than 2 ideas: {list}. Generate more ideas that DIRECTLY
  address these constraints." This counts toward the 5 retry limit.

---

## Step 3: Hypothesis & Method + Advisor Gate (Stage 3)

### 3a: Student develops hypotheses

For each active idea (or batch them together), **spawn a Student agent**
(Sonnet) with the hypothesis development task from ri-student.md Section 3.
Pass the idea content by reading from `ideas/candidates_round*.md` — glob and
pick the highest N. (Ideas are only regenerated on PIVOT, so this is usually
round 1. Do NOT hardcode N = current_round for reading ideas.)

The Student must produce for each idea:
- Thesis statement
- Theoretical basis with verifiable propositions
- Method sketch (inputs → signals → algorithm → objective)
- 2-4 method variants forming a multi-level framework
- 5-8 closest prior work comparison
- Circularity check

Write each to `proposal_space/hypotheses/hypothesis_{slug}_round{N}.md`

### 3b: Advisor reviews hypotheses

**Spawn an Advisor agent** (Opus) with the hypothesis gate task from
ri-advisor.md. Pass all hypothesis files as context.

The Advisor applies the **9-dimension harsh filter** and outputs structured
verdicts per idea using `=== IDEA: slug ===` format.

**The Advisor MUST perform an INTENT-ALIGNMENT CHECK and a DIVERSITY AUDIT:**

**Intent-alignment check (BEFORE diversity audit):**
Read `state.json["intent_constraints"]`. For each constraint, count how
many surviving (non-dropped) ideas directly address it. If any constraint
has fewer than 2 ideas, the Advisor's output must include:
```
## Intent Alignment Gap
CONSTRAINT: "{constraint text}"
MATCHING_IDEAS: {count} (need >= 2)
REQUEST: Student must generate ideas that directly address this constraint.
```
The orchestrator routes back to Student before proceeding.

This check prevents the pipeline from producing only analysis/characterization
ideas when the user wants a new method, or only theoretical ideas when the
user wants a practical tool.

**Diversity audit (AFTER intent-alignment passes):**
The Advisor groups ideas by sub-topic /
method similarity and checks the diversity rule:
- If > 3 ideas target the same sub-topic or use substantially similar
  methods, the Advisor identifies the most redundant ones (those adding
  the least distinct contribution) and marks them as **DROP** with
  `FATAL_FLAW: "Redundant with {slug_1}, {slug_2}, {slug_3} — this is
  the 4th+ idea in the same sub-topic cluster."`
- The Advisor then checks whether the remaining (non-dropped) ideas
  total >= 10. If not, the Advisor's output must include a section:
  ```
  ## Diversity Gap
  REMAINING_COUNT: {count after dropping redundant ideas}
  SATURATED_TOPICS: {list of sub-topics already covered by 3 ideas}
  REQUEST: Student must generate {10 - count} more ideas avoiding
  the saturated topics listed above.
  ```
  The orchestrator sends the Student back to generate more ideas (up to
  5 retries total across Stage 2 + Stage 3b combined). Only when the
  Advisor confirms >= 10 diverse ideas OR 5 retries are exhausted does
  the pipeline proceed.

**After agent returns:**
1. For EACH idea in the output, extract that idea's review section and
   save it via `save_review(workspace, "advisor", slug, round_num, section_text)`.
   This produces one file per idea: `reviews/advisor_{slug}_round{N}.md`.
   Do NOT save a single merged file for all ideas.
2. If the Advisor flagged a Diversity Gap, route back to Student for
   additional ideas before proceeding to step 3.
3. Parse verdicts:
   ```bash
   python -c "
   from helpers.parse_review import parse_review
   result = parse_review('''<advisor_output>''')
   for slug, idea in result.ideas.items():
       print(f'{slug}: {idea.verdict}')
   "
   ```
4. For each idea, update state based on verdict:
   - DEVELOP → update status to `planning`
   - REFINE → update status to `refine`, check can_refine()
   - DROP → update status to `dropped`
4. Record verdicts in state via `record_verdict()`

### 3c: REFINE sub-loop

If any ideas got REFINE and can_refine() is True:
1. For each REFINE idea, collect open severe/major issues into the review tracker.
2. **Spawn up to 2 Student agents per idea** in parallel if issues are
   independent (e.g., one for theory issues, one for experiment issues).
3. **Do NOT update the review tracker after the Student returns.** Save the
   revised hypothesis to `proposal_space/hypotheses/hypothesis_{slug}_round{N}_revised.md`.
4. Re-run Advisor gate on revised hypotheses only. The Advisor receives
   BOTH the revised hypothesis (read from `hypotheses/hypothesis_{slug}_round{N}_revised.md`)
   AND the review tracker with open issues (read from `state/review_tracker.json`).
   The Advisor checks each idea **individually** and must state for each
   open issue: **RESOLVED** or **STILL_OPEN**. Save the Advisor's re-review
   via `save_review()` using the cycle suffix for sub-iterations:
   `reviews/advisor_{slug}_round{N}_cycle{C}.md` (C = 2, 3, ... for each
   sub-iteration; the initial Stage 3b review has no cycle suffix).
   Write-first rule applies. Only the Advisor's verdict updates the tracker
   (via `resolve_review_issue(resolved_by="advisor")`).
5. Max 3 sub-iterations at this stage.

**Quality gate**: >= 3 ideas must have `planning` status (hard floor).
Target is 5+, but 3 is the minimum to proceed.
- If fewer than 3 after 2 mini-Stage 2 retry attempts: trigger Viability
  Checkpoint 2 (topic reassessment).
- Ideas still in `refine` status after the sub-loop completes without
  DEVELOP are automatically DROPPED.
- If Advisor issues REFINE but `can_refine()` returns False, the idea
  is automatically DROPPED.

Advance to `stage_4_planning`.

---

## Step 4: Experiment Planning (Stage 4)

For each idea with status `planning`, **spawn a Student agent** (Sonnet)
to produce the experiment plan from ri-student.md Section 4.

Pass as context (read from files — see "Round Numbering and File Resolution"):
- The latest hypothesis for this idea (glob `hypotheses/hypothesis_{slug}_round*`
  → pick highest-round `_revised.md` if exists, else highest-round `.md`)
- The literature landscape (glob `literature/landscape_round*` → highest N)
- The review tracker for this idea (read `state/review_tracker.json`)
- Advisor review from the most recent round (glob `reviews/advisor_{slug}_round*`
  → pick highest N)

Each plan must include: MVE, full 3-phase plan, baselines, ablation table,
datasets, metrics, compute estimate, success criteria, risk register, and
paper storyline.

Write each to `proposal_space/plans/plan_{slug}_round{N}.md`
Log interactions. Advance to `stage_5_submission`.

---

## Step 5: Proposal Submission (Stage 5)

This is automatic (no agent needed).

1. Verify all plans exist for ideas with `planning` status.
2. **Ideas already in `approved` status from prior rounds are NOT re-submitted.**
   They retain their approved status and skip Stages 5-8.
3. Create submission manifest (only for newly submitted ideas):
   ```bash
   python -c "
   import json
   from pathlib import Path
   from datetime import datetime
   manifest = {
       'round': <N>,
       'timestamp': datetime.now().isoformat(),
       'quality_standard': '<standard>',
       'ideas_submitted': [<slugs>],
       'status': 'pending_advisor_review'
   }
   Path('<OUTPUT_BASE>/proposal_space/state/submission_round<N>.json').write_text(json.dumps(manifest, indent=2))
   "
   ```
4. Update all submitted ideas to status `in_review`.
5. Advance to `stage_6_advisor_review`.

---

## Step 6: Advisor Review — Internal Quality (Stage 6)

**Advisor's focus**: METHOD SOUNDNESS and DEPTH. The Advisor evaluates the
internal quality of the research — is the theory correct, is the method
deep enough, are the experiments well-designed? The Advisor does NOT check
for scooping, recent competing work, or reviewer attack vectors — that is
the VP's job.

The Advisor reviews proposals **one at a time** — each proposal gets its
own separate agent call. Do NOT batch all proposals into one agent call.

```
For each idea with status `in_review`:
  1. Spawn ONE Advisor agent (Opus) for THIS SINGLE proposal
  2. Pass as context (read ALL from files — see "Round Numbering and File Resolution"):
     - This one experiment plan: glob `plans/plan_{slug}_round*` → pick the
       highest-round `_revised.md` if exists, else highest-round `.md`
     - VP review from prior round, if exists: read `reviews/vp_{slug}_round{N-1}.md`
       where N = current_round from state.json. If N=1, no prior VP review exists.
     - Current quality standard + rubric
     - Review tracker for this idea: read `state/review_tracker.json`, extract
       this slug's issues
  3. The Advisor evaluates INTERNAL QUALITY:
     a. Theoretical soundness — claims correct? assumptions explicit?
        circularity? propositions verifiable?
     b. Method depth — single-trick heuristic or multi-level framework?
        Can each level stand as an independent contribution?
     c. Experimental design — do experiments discriminate the hypothesis?
        Are ablations independent? Each answers one scientific question?
     d. Baseline sufficiency — are the strongest KNOWN baselines included?
        (The Advisor checks known baselines; the VP searches for new ones.)
     e. TRIVIALITY GATE — is the contribution deep enough for the target
        venue, or is it a trivial extension / simple model improvement?
        A boring-but-correct idea with no methodological depth must be
        REFINE'd to add depth, or DROP'd if depth cannot be added.
     - Labels every issue with severity: severe / major / minor / slight
     - Issues verdict: APPROVE / REFINE / PIVOT / DROP
     - APPROVE only if NO severe and NO major issues remain open
  4. After agent returns:
     - **Save the COMPLETE review** to `proposal_space/reviews/advisor_{slug}_round{N}.md`
       (see REVIEW FILE FORMAT below)
     - Parse verdict and issues
     - Update the review tracker: add new issues with severity and IDs.
       For each issue in the tracker, the `description` field must contain
       the FULL review paragraph (not a one-liner). The `suggestion` field
       must contain the reviewer's specific improvement direction.
     - If APPROVE: verify can_approve() (no severe/major in tracker)
     - Log per-proposal interaction
  5. Move to next proposal
```

After all proposals reviewed individually → advance to `stage_7_vp_review`

### Review File Format (MANDATORY for both Advisor and VP)

Every review file (`reviews/advisor_{slug}_round{N}.md` and
`reviews/vp_{slug}_round{N}.md`) must contain the **complete, unabridged
review output** from the reviewer agent. This is the primary record of
the review — the review tracker only stores structured metadata extracted
from it. The review file must include AT MINIMUM:

```markdown
# Round {N} {Advisor|VP} Review — {slug}
**Reviewer**: {role}
**Standard**: {lenient|moderate|strict}
**Date**: {YYYY-MM-DD}
**Proposal file reviewed**: {path to the plan/hypothesis file}

## Overall Assessment
{2-5 paragraph narrative assessment covering the reviewer's scope}

## Per-Section Critique
{For each section of the proposal that has issues:
 quote or reference the specific problematic passage,
 explain what is wrong, and suggest improvement direction}

## Issues Raised
{For each issue — this becomes the review tracker entry:
 ### {issue_id} [{severity}, {category}]
 **Problem**: {full paragraph explaining the issue, including why it matters,
 what is wrong with the current approach, and what evidence supports the criticism}
 **Suggested fix direction**: {specific, actionable improvement direction —
 not "fix this" but "do X because Y"}
 **Relevant citations** (if any): {arXiv IDs, paper titles, URLs found via
 WebSearch that are relevant to this issue — e.g., competing papers, methods
 that should be compared against, theoretical results that contradict the claim}
}

## Evaluation Technique Results (Advisor only)
{Results of the 5 evaluation techniques applied}

## Scooping Check Results (VP only)
{WebSearch queries used, papers found, overlap assessment}

## Reviewer Attack Vectors (VP only)
{Top-3 attacks with preemptive defenses}

## Verdict
{APPROVE | REFINE | PIVOT | DROP}
{9-dimension scores (Advisor) or significance assessment (VP)}
```

**CRITICAL**: The orchestrator must save the ENTIRE agent output to the
review file. Do NOT summarize, truncate, or paraphrase. The review file
is the authoritative record. If the agent output is very long, save it
all — storage is cheap, lost review reasoning is expensive.

### Review Persistence Rule (NON-NEGOTIABLE)

Every time a reviewer agent returns output — whether initial review
(Stage 6-7) or re-review (Stage 8e) — the orchestrator MUST
**immediately write the complete output** to the review file BEFORE
doing anything else (parsing, updating tracker, logging, etc.).

The write-first rule exists because:
- If the orchestrator parses issues first, it may "forget" to save the
  full text afterward (this has happened).
- The review file is the authoritative record. The tracker is derived
  from it, not the other way around.
- The Student reads the review file in the next revision. If it doesn't
  exist, the Student is working blind.

The sequence after a reviewer agent returns is strictly:
1. **Write + validate** via `save_review()`:
   ```python
   from helpers.log_interaction import save_review
   save_review(workspace, "advisor", slug, round_num, agent_output)
   ```
   `save_review()` writes the file AND validates it (file > 500 bytes,
   contains required sections: `## Overall Assessment`, `## Issues Raised`,
   `## Verdict`). If validation fails, it raises `ValueError` — the
   orchestrator must fix the issue (re-prompt the reviewer if needed)
   before proceeding.
2. **Then** parse verdict and issues from the saved file
3. **Then** update the review tracker
4. **Then** log the interaction

Skipping step 1 is a pipeline integrity violation. There is no valid
reason to skip it. "I'll do it later" is not acceptable — do it first.

### Passing Reviews to the Student (Stage 8d)

When the Student receives reviewer feedback, the orchestrator MUST pass:
1. The **file path** to each review file (so the Student agent can read it)
2. OR the **full inline text** of the review file in the prompt

The orchestrator MUST NOT pass its own summary or paraphrase of the review.
The Student must see the reviewer's exact words — their reasoning, their
cited papers, their suggested improvements. If the orchestrator summarizes,
the Student loses critical context and produces lower-quality revisions.

---

## Step 7: VP Review — External Validity and Significance (Stage 7)

**VP's focus**: NOVELTY, SIGNIFICANCE, and EXTERNAL THREATS. The VP
evaluates whether the contribution is novel against the real world of
published work, whether it is significant enough for a top venue, and
what the strongest reviewer attacks would be. The VP does NOT re-check
theory soundness or experimental design in detail — the Advisor already
did that.

The VP reviews proposals **one at a time** — each proposal gets its
own separate agent call.

```
For each idea with status `in_review` or `approved` (VP reviews both):
  1. Spawn ONE VP agent (Opus) for THIS SINGLE proposal
  2. Pass as context (read ALL from files — see "Round Numbering and File Resolution"):
     - This one experiment plan: glob `plans/plan_{slug}_round*` → pick the
       highest-round `_revised.md` if exists, else highest-round `.md`
     - Advisor's review for THIS idea from THIS round: read
       `reviews/advisor_{slug}_round{N}.md` where N = current_round from
       state.json. This file MUST exist because Stage 6 wrote it.
     - Current quality standard
     - Review tracker for this idea: read `state/review_tracker.json`,
       extract this slug's issues
  3. The VP stress-tests EXTERNAL VALIDITY:
     a. Scooping check — use WebSearch to find recent papers (last 6 months)
        that overlap with this idea. Report specific papers found or
        "no overlap found after searching [queries]".
     b. Novelty vs the real field — given what actually exists (not just
        what the student cited), is this contribution genuinely new?
     c. SIGNIFICANCE GATE — is the expected impact large enough for the
        target venue? A technically correct but incremental/trivial idea
        should be flagged as major: "contribution too incremental for
        {venue}". Unless the impact is exceptionally large (e.g., 10x
        speedup, opens a new research direction), simple extensions of
        known methods or straightforward model improvements are not
        sufficient.
     d. Top-3 reviewer attack vectors — what would the toughest Area Chair
        say to reject this? Provide specific preemptive defenses.
     e. Missing baselines from recent work — search for strong baselines
        the Advisor may not know about (published in last 6 months).
     f. Cross-domain threats — work from adjacent fields that could
        undermine or strengthen the contribution.
     - Labels every issue with severity: severe / major / minor / slight
     - Issues verdict: APPROVE / REFINE / DROP
     - APPROVE only if NO severe and NO major issues remain
  4. After agent returns:
     - **Save the COMPLETE review** to `proposal_space/reviews/vp_{slug}_round{N}.md`
       (same REVIEW FILE FORMAT as Advisor — see above)
     - Parse verdict and issues
     - Update the review tracker. For each issue, `description` must contain
       the FULL review paragraph, `suggestion` must be specific and actionable.
       If the VP found papers via WebSearch, include arXiv IDs and URLs in
       both the review file AND the tracker `suggestion` field.
     - Log per-proposal interaction
  5. Move to next proposal
```

**Division of labor summary:**

| Dimension | Advisor (Stage 6) | VP (Stage 7) |
|---|---|---|
| Theory soundness | PRIMARY — checks proofs, assumptions, circularity | Skips (trusts Advisor) |
| Method depth / triviality | PRIMARY — is it deep enough or trivial? | Skips |
| Experimental design | PRIMARY — ablations, controls, metrics | Skips |
| Known baselines | PRIMARY — are standard baselines included? | Supplements with WebSearch |
| Scooping / recent work | Skips | PRIMARY — WebSearch for last 6 months |
| Novelty vs real field | Skips | PRIMARY — novelty given what actually exists |
| Contribution significance | Flags if obviously trivial | PRIMARY — venue-calibrated impact assessment |
| Reviewer attack vectors | Skips | PRIMARY — top-3 attacks with defenses |
| Cross-domain threats | Skips | PRIMARY — adjacent-field perspective |

After all proposals reviewed individually → advance to `stage_8_decision`

---

## Step 8: Decision (Stage 8)

This is orchestrator logic (no agent needed). For each idea, aggregate
both reviews using the **review tracker**.

### 8a: Build Review Tracker

For each idea, collect ALL issues from both Advisor and VP reviews into
a **review tracker** — a structured record of every issue, its severity,
and its resolution status. Store this in `proposal_space/state/review_tracker.json`:

```json
{
  "idea_slug": {
    "issues": [
      {
        "id": "R1-ADV-1",
        "source": "advisor",
        "round": 1,
        "severity": "severe|major|minor|slight",
        "category": "theory|experiment|novelty|baseline|...",
        "description": "FULL review paragraph (not a one-liner)",
        "suggestion": "specific, actionable improvement direction",
        "status": "open|addressed|wontfix",
        "resolved_by": null,
        "addressed_in": null,
        "resolution_note": null,
        "history": [
          {"event": "opened", "timestamp": "...", "by": "advisor", "detail": "..."},
          {"event": "still_open", "timestamp": "...", "by": "vp", "detail": "..."},
          {"event": "addressed", "timestamp": "...", "by": "advisor", "detail": "..."}
        ]
      }
    ]
  }
}
```

Issue IDs follow the pattern: `R{round}-{ADV|VP}-{number}`.

### 8b: Apply Decision Matrix

| Advisor  | VP      | Decision      |
|----------|---------|---------------|
| APPROVE  | APPROVE | **APPROVE** (only if no open severe/major issues) |
| APPROVE  | REFINE  | **REFINE** (address VP's severe/major issues) |
| REFINE   | APPROVE | **REFINE** (address Advisor's severe/major issues) |
| REFINE   | REFINE  | **REFINE** (address both) |
| PIVOT    | any     | **PIVOT** |
| DROP     | any     | **DROP** |
| any      | DROP    | **DROP** |

**CRITICAL RULE**: An idea may ONLY be APPROVED if ALL severe and major
issues in the review tracker have status "addressed". Open minor and
slight issues do not block approval but are noted as caveats.

Even if both reviewers say APPROVE, if they attached severe/major issues
with "mandatory" conditions, the idea is REFINE until those are addressed.

### 8c: Route REFINE ideas

For each REFINE idea:
1. Update status via `update_idea_status()`
2. Determine routing:
   - Issues about **hypothesis/theory/novelty** → back to Stage 3
   - Issues about **experiment design only** → back to Stage 4
3. If PIVOT: check `can_pivot()`.
4. Record decisions in interaction log.

### 8d: Student Revision (REFINE loop)

For each REFINE idea, spawn Student agents to address the open severe
and major issues:

- You may spawn **up to 2 Student agents per idea** in parallel if the
  issues are independent (e.g., one handles theory issues, another handles
  experiment design issues).
- Each Student agent receives (read ALL from files — see "Round Numbering
  and File Resolution" for how to resolve each path):
  - The current plan: glob `plans/plan_{slug}_round*` → pick highest-round
    `_revised.md` if exists, else highest-round `.md`
  - The specific issues to address: read `state/review_tracker.json` →
    extract IDs and severity for this slug
  - The **FULL review files** for this idea from the CURRENT round:
    read `reviews/advisor_{slug}_round{N}.md` and `reviews/vp_{slug}_round{N}.md`
    where N = current_round from state.json. These files MUST exist on disk
    because Stage 6/7/8e wrote them earlier in this round. If a file
    doesn't exist, the pipeline has a persistence bug — stop and fix it
    before continuing. Pass the complete review text verbatim.
  - The literature landscape: glob `literature/landscape_round*` → highest N
- After the Student returns, **validate the revision output** before proceeding:
  1. Call `validate_student_revision(revision_text)` from `parse_review.py`.
  2. If violations are found, **reject the revision and re-prompt** the Student
     with: "Your revision was rejected because it contains language directed at
     reviewers rather than research improvements. Violations: {violations}.
     Rewrite the revision with ONLY improved research content."
  3. If the Student fails validation twice in a row, DROP the idea (the Student
     cannot productively revise it without resorting to manipulation).
  4. Only after validation passes, **save the revised plan** to
     `proposal_space/plans/plan_{slug}_round{N}_revised.md`.

**CRITICAL: Do NOT update the review tracker after the Student returns.**
The Student has no authority to declare its own issues resolved. The
tracker remains unchanged — all issues stay `"open"` until a reviewer
explicitly confirms resolution in Step 8e.

```
Agent(
  subagent_type="general-purpose",
  model="sonnet",
  prompt="<ri-student.md Section 5 revision prompt>
  ISSUES TO ADDRESS:
  {list of open severe/major issues with IDs from review_tracker.json}
  CURRENT PLAN:
  {verbatim text of the latest plan file — read from disk, not summarized}
  ADVISOR REVIEW (verbatim):
  {full text of reviews/advisor_{slug}_round{N}.md — read from disk}
  VP REVIEW (verbatim):
  {full text of reviews/vp_{slug}_round{N}.md — read from disk}"
)
```

**Note**: The prompt passes the FULL review file text verbatim, not a
summary. See "Passing Reviews to the Student" section above.

### 8e: Re-review after revision (REVIEWER IS THE SOLE AUTHORITY)

After Student revision, re-submit the revised plans to both Advisor and
VP for re-review. **Only the reviewers can change the status of issues
in the review tracker.** The orchestrator acts as a scribe, not a judge.

Re-reviews happen WITHIN the same round (the round number only increments
at Step 8g after convergence check). To avoid overwriting the initial
review file, re-reviews use the **cycle suffix**:
- Initial review (Stage 6/7): `reviews/advisor_{slug}_round{N}.md` (no suffix)
- Re-review after 1st revision: `reviews/advisor_{slug}_round{N}_cycle2.md`
- Re-review after 2nd revision: `reviews/advisor_{slug}_round{N}_cycle3.md`

This applies to both Advisor and VP re-review files. The cycle suffix
ensures all reviews are preserved as separate files within the same round.

Each re-reviewer receives (read from files):
- The **revised plan** (read from `plans/plan_{slug}_round{N}_revised.md`)
- The **previous review** for this idea (read from `reviews/advisor_{slug}_round{N}.md`
  or the latest cycle file)
- The **review tracker** (read from `state/review_tracker.json`)

**Save the COMPLETE re-review** to the appropriate per-idea per-round file.
Same REVIEW FILE FORMAT as the initial review. Re-reviews are full review
documents, not abbreviated notes. The reviewer must reference the specific
changes the Student made (quoting revised text) and explain why each issue
is RESOLVED or STILL_OPEN.

**Apply the write-first rule** (same as Stage 6): write the complete
re-review output to the review file BEFORE parsing or updating the tracker.
The Student's next revision (if needed) reads THESE re-review files.
If the files don't exist, the next revision is blind.

Each reviewer must, for EACH previously-open issue:
1. State explicitly: **RESOLVED** or **STILL_OPEN** with explanation.
2. If RESOLVED: the orchestrator calls `resolve_review_issue()` with
   `resolved_by="advisor"` or `resolved_by="vp"` (the reviewer who
   confirmed it) and `resolution_note` from the reviewer's text.
3. If STILL_OPEN: the issue remains `"open"` in the tracker. The
   orchestrator calls `log_review_event()` to record that the reviewer
   re-examined the issue and found it not yet resolved:
   ```python
   log_review_event(workspace, slug, issue_id, "still_open",
                    by="advisor",  # or "vp"
                    detail="<reviewer's explanation of what is still missing>")
   ```
4. Flag any **NEW issues** introduced by the revision (with severity).
   The orchestrator adds these via `add_review_issue()`.

**Review log**: Every issue in `review_tracker.json` carries a `history`
list that records the full lifecycle:
- `opened` → when the reviewer first raised it
- `still_open` → each time a reviewer re-examined and found it unresolved
- `addressed` → when a reviewer confirmed it resolved
- `wontfix` → when a reviewer accepted it won't be fixed (minor/slight only)

This history is the audit trail. It answers: "How many revision cycles
did this issue go through? Who said it was resolved? What was still
missing each time?"

**Resolution rules — who can close what:**

| Issue source | Who can mark RESOLVED |
|---|---|
| Advisor-raised issue (`R{N}-ADV-*`) | Advisor OR VP (either reviewer) |
| VP-raised issue (`R{N}-VP-*`) | Advisor OR VP (either reviewer) |

Any reviewer can confirm any issue as resolved — the point is that a
**reviewer** must confirm it, not the Student or the orchestrator.

**After BOTH reviewers return:**

The orchestrator reads the updated tracker (which now reflects the
reviewers' per-issue verdicts) and applies the decision:

- If `can_approve(workspace, slug)` returns True (no open severe/major)
  AND both reviewers issued APPROVE → **APPROVE**.
- If `can_approve()` returns False (open severe/major remain) →
  **REFINE** (back to 8d for another Student revision cycle).
- If either reviewer issued DROP → **DROP**.

**Loop control:**

Repeat the REFINE loop (8d → 8e) until:
- All severe/major issues are confirmed resolved BY REVIEWERS (→ APPROVE), OR
- Max refine cycles reached (3 per idea → **DROP** — the idea is dead.
  No "include with caveats." Dead ideas are permanently removed.)

A single issue can go through multiple revision→re-review cycles. There
is no limit on how many times a reviewer can say STILL_OPEN for the same
issue — if the Student cannot satisfy the reviewer within the overall
refine budget (3 cycles), the idea is dropped.

### 8f: All-proposals-dead check

After the decision loop, check if any active ideas remain:
```bash
python -c "
from helpers.state_manager import get_active_ideas, can_pivot, load_state
from pathlib import Path
state = load_state(Path('<OUTPUT_BASE>'))
active = get_active_ideas(state)
print(f'Active ideas: {len(active)}')
print(f'Pivot budget remaining: {can_pivot(state)}')
"
```

If **all ideas are dead** (no active ideas remain):
- If `can_pivot(state)` is True (pivot budget remains):
  - Return to **Stage 2** to generate replacement ideas
  - Pass ALL drop reasons to Student so they know what failed and why
  - This counts as a pivot (increment `pivot_count`)
- If `can_pivot(state)` is False (pivot budget exhausted) OR max rounds reached:
  - Trigger **TOPIC_INFEASIBLE** termination
  - Record viability assessment with checkpoint=2
  - Output viability report with alternative directions

### 8g: Check convergence

```bash
python -c "
from helpers.state_manager import check_convergence, load_state
from pathlib import Path
state = load_state(Path('<OUTPUT_BASE>'))
print(check_convergence(state))
"
```

- If converged (>= 3 approved **at strict quality**, or max rounds) → Stage 9
- If not converged:
  - `record_round_history()`
  - `start_new_round()` (increments round, tightens quality standard)
  - **Provisional approvals** (ideas approved at lenient or moderate) are automatically
    demoted to `in_review` by `start_new_round()` so they face re-review at the
    stricter standard. They do NOT go through student revision — only the reviewers
    re-evaluate them at the higher bar.
  - Routing: if `refine` ideas exist → `stage_3_hypothesis`;
    if only provisional re-reviews → `stage_6_advisor_review`;
    otherwise → `stage_9_final_output`

**Why strict-only convergence?** Without this gate, 3 ideas approved at lenient
in Round 1 would skip moderate and strict review entirely, allowing mediocre
ideas into the final output. The progressive quality standards (lenient →
moderate → strict) serve as efficient early-round filters, but every idea in
the final output must survive strict (top-conference) scrutiny.

---

## Step 9: Final Output (Stage 9)

### 9a: Final ranking + Portfolio Coherence Analysis

**Spawn an Advisor agent** (Opus) for ranking and portfolio analysis.
Pass ALL approved plans (read from files: glob `plans/plan_{slug}_round*`
→ latest per slug) as context.

The Advisor must produce TWO outputs:

**Output 1 — Ranking** (if > 5 approved, select top 5):
For each selected plan: rank, confidence, recommended venue, one-sentence contribution.

**Output 2 — Portfolio Coherence Analysis**:
1. **Synergies**: Which ideas share infrastructure (datasets, models,
   compute pipelines)? Which should be run in parallel?
2. **Merge candidates**: Could any 2 ideas be combined into a single
   stronger paper? If so, which ones and what would the combined paper look like?
3. **Execution order**: Which idea should be executed FIRST to de-risk
   the others? (e.g., if Idea 1's MVE fails, which other ideas lose their
   motivation? Run Idea 1 first.)
4. **Coherent narrative**: Do the approved ideas form a coherent research
   program (e.g., "understanding optimizer geometry for post-training"), or
   are they disconnected projects? If disconnected, note this as a
   portfolio weakness.
5. **Redundancy check**: Are any two approved ideas close enough that
   publishing both would be seen as salami-slicing by the community?

Write the output to `proposal_space/state/portfolio_analysis.md`.

### 9b: Render final plans — SELF-CONTAINED DOCUMENTS

**CRITICAL**: Each final research plan MUST be a **self-contained document**
that can be read and understood WITHOUT referencing any other file. No
pointers, no "see file X", no cross-references to proposal_space files.
ALL content must be inlined.

For each approved idea, the orchestrator MUST:

1. **Read ALL source material FROM FILES** into memory BEFORE spawning the agent.
   Do NOT use conversation context — read every file from disk:
   - The hypothesis: glob `hypotheses/hypothesis_{slug}_round*` → pick
     highest-round `_revised.md` if exists, else highest-round `.md`
   - The experiment plan: glob `plans/plan_{slug}_round*` → pick
     highest-round `_revised.md` if exists, else highest-round `.md`
   - ALL advisor reviews: glob `reviews/advisor_{slug}_round*.md` → read all
   - ALL VP reviews: glob `reviews/vp_{slug}_round*.md` → read all
   - The review tracker: read `state/review_tracker.json` and extract
     this idea's issues with full history
   - The literature landscape: glob `literature/landscape_round*` → highest N

2. **Spawn a Student agent (Sonnet)** for EACH approved idea to write
   the final self-contained research proposal. Pass ALL source material
   as inline content in the prompt (not as file paths):

```
Agent(
  subagent_type="general-purpose",
  model="sonnet",
  prompt="Write a complete, self-contained research proposal document.

  IMPORTANT: The output must be a STANDALONE document. A reader should
  be able to understand the full proposal without any other file. Include
  ALL details inline — every method step, every baseline, every ablation,
  every piece of theory, every reviewer concern and how it was addressed.

  Use the following 14-section template. Each section must contain FULL
  SUBSTANTIVE CONTENT, not summaries or pointers.

  ## 1. Title
  {paper-like title}

  ## 2. One-Sentence Thesis
  {what mechanism + why current methods fail + what improvement}

  ## 3. Research Area Classification
  {specific sub-field, relevant venues, where this fits in the landscape}

  ## 4. Closest Prior Work (5-8 papers)
  For each: title, authors, year, venue, similarity, difference,
  why this is NOT just a variant. Include a comparison table.

  ## 5. Problem Gap
  {what is unsolved, why now, why this gap is deep enough for a top venue}

  ## 6. Theoretical Basis
  {specific framework, verifiable propositions with formal statements,
  applicable guarantees, assumptions stated explicitly}

  ## 7. Method Sketch
  {inputs → intermediate signals → algorithm → objective.
  Detailed enough that an engineer could start implementing.
  Include pseudocode or algorithmic steps.
  Key ablation dimensions with what each tests.}

  ## 8. Method Variants (Multi-Level Framework)
  {2-4 variants forming a progression. Each level removes one limitation.
  Each level's ablation answers an independent scientific question.
  Describe each level in full detail.}

  ## 9. Implementation Plan
  {MVP timeline, full version timeline, engineering complexity,
  most likely failure mode, mitigation strategy, compute estimate
  broken down by phase}

  ## 10. Experimental Plan
  {MVE (what result would kill this), full 3-phase plan,
  specific baselines with code availability,
  ablation table (what to vary / hold constant / question answered),
  specific datasets with sizes,
  metrics (primary + secondary diagnostics),
  success criteria (specific numbers),
  risk register (top-3 risks with early warning + mitigation + fallback)}

  ## 11. Paper Storyline
  {hook → core insight → method → empirical → why now → why top-tier
  → biggest reviewer attack → defense. Written as a draft abstract.}

  ## 12. Novelty Risk Assessment
  {most similar published work, likely 'incremental' criticism,
  specific mitigation strategy, recent scooping check results}

  ## 12.5. Limitations
  {2-3 most important method limitations. For each:
  - Is it FUNDAMENTAL (inherent to the approach) or ENGINEERING (solvable
    with more effort/compute)?
  - Honest assessment of scope: what does this method NOT apply to?
  - Which limitations are acceptable for the target venue?}

  ## 12.6. Falsification Plan
  {If the MVE result is negative:
  - Is the negative result publishable? What additional analysis is needed?
  - If not publishable, what is the total risk (compute/time) of failure?}

  ## 13. Quality Checklist
  For each item, state PASS/FAIL with brief evidence:
  - Core method unpacked to implementation-level granularity
  - Cannot be reduced to a known method in one sentence
  - No circular estimation steps
  - Cross-over claims have actionable closed-loop feedback
  - 3+ failure cases addressed in method design
  - Weakest assumption identified with graceful degradation
  - Multi-level framework with independent scientific questions
  - Adjacent-field techniques considered
  - 5-8 prior works with detailed comparison
  - Approximation gaps quantified
  - Theoretical guarantees applicable to use scenario

  ## 14. Final Verdict
  {confidence level, recommended venue, 9-dimension score table,
  remaining minor/slight caveats from review process}

  ## Appendix A: Review History
  {Summary of all reviewer issues, how each was resolved or why it
  was accepted as a caveat. Include issue IDs and resolution notes.}

  ## Appendix B: Key References
  {Full citation list with arXiv IDs for all papers mentioned}

  -----
  SOURCE MATERIAL (use this to write the proposal — inline everything):

  HYPOTHESIS:
  {full hypothesis text}

  EXPERIMENT PLAN:
  {full experiment plan text}

  ADVISOR REVIEWS:
  {all advisor review text for this idea}

  VP REVIEWS:
  {all VP review text for this idea}

  REVIEW TRACKER:
  {issue resolution history for this idea}

  LITERATURE LANDSCAPE:
  {landscape summary}
  "
)
```

3. **Write the agent output** directly to the final plan file:
   `<OUTPUT_BASE>/plan_{rank}_{slug}.md`

4. **Verify** the output is self-contained: grep for "see ", "refer to",
   "proposal_space" — if any are found, the document is NOT self-contained
   and must be regenerated.

### 9c: Summary table

Use the Python helper for the comparison table:
```bash
python -c "
from helpers.format_final_plan import format_summary_table
from pathlib import Path
plans = [<list_of_plan_dicts>]
Path('<OUTPUT_BASE>/summary.md').write_text(format_summary_table(plans))
"
```

### 9d: Pipeline summary

```bash
python -c "
from helpers.log_interaction import write_pipeline_summary
from pathlib import Path
write_pipeline_summary(
    Path('<OUTPUT_BASE>'),
    topic='<topic>',
    total_rounds=<N>,
    agent_calls={'Student': <n>, 'Advisor': <n>, 'VP': <n>},
    idea_lifecycle=<lifecycle_list>,
    key_decisions=<decisions_list>,
    review_highlights='<highlights>',
)
"
```

### 9e: Brief versions

For each approved plan, produce a concise brief version that distills the
proposal into an actionable summary. The brief file is named `<xyz>_brief.md`
where the full plan is `<xyz>.md` (e.g., `plan_1_idea-slug_brief.md`).

**Spawn a Student agent (Sonnet)** for EACH approved plan. Pass the full
plan text as context:

```
Agent(
  subagent_type="general-purpose",
  model="sonnet",
  prompt="Read the full research plan below and produce a BRIEF VERSION.

  LANGUAGE REQUIREMENT: Write the output in Traditional Chinese (繁體中文).
  Technical terms and proper nouns (e.g., Newton-Schulz, Muon, AdamW,
  Fisher information, Hessian, RandOpt, SOAP, SAM, MoE, KFAC, SVD,
  LOO-CV, etc.) MUST remain in their original language — do NOT translate
  them. Pseudocode must stay in English.

  The brief must have exactly these four sections:

  ## 1. 直覺（Intuition）
  Why does this idea make sense? What is the core insight or observation
  that motivates it? Explain in 3-5 sentences that a researcher outside
  the subfield could follow. No jargon without immediate definition.

  ## 2. 研究構想（The Idea）
  What exactly is being proposed? State the method, the claim, or the
  contribution in concrete terms. Include the key equation, objective,
  or architectural choice if there is one. 5-10 sentences.

  ## 3. 核心演算法／架構（Core Algorithm / Architecture）
  Describe the main algorithm or model architecture at a level of detail
  sufficient to begin implementation. Use pseudocode, numbered steps, or
  a clear pipeline diagram (in text). Include input/output types, key
  hyperparameters, and the loss function or objective. This section
  should be the longest — as detailed as needed to be unambiguous.
  Pseudocode itself must stay in English.

  ## 4. 主要實驗對照（Major Alternatives to Experiment）
  List the 3-5 most important experimental comparisons or ablations that
  must be run. For each, state: (a) what is varied, (b) what is held
  constant, (c) what scientific question it answers, and (d) what outcome
  would change the conclusion.

  CONSTRAINTS:
  - Total length: 1-3 pages (roughly 500-1500 words).
  - No filler, no motivation beyond Section 1, no related work.
  - Self-contained: a reader should understand the idea and know what to
    implement without reading the full plan.
  - Do NOT reference the full plan or any external files.

  FULL PLAN:
  {full_plan_text}
  "
)
```

Write each brief to `<OUTPUT_BASE>/<plan_filename_without_.md>_brief.md`.

### 9f: Report to user

Tell the user:
- How many plans were produced (full + brief versions)
- Where the output files are: `<OUTPUT_BASE>/`
- Where the full audit trail is: `<OUTPUT_BASE>/proposal_space/interaction_log/`
- Total rounds and agent calls
- Remind: each plan is a self-contained document that can be shared independently
- Remind: brief versions are available as `*_brief.md` for quick reference

---

## Agent Spawning Reference

### Student (Sonnet)
```
Agent(
  subagent_type="general-purpose",
  model="sonnet",
  prompt="<role prompt from ri-student.md>\n\n<stage-specific task>\n\n<context files>"
)
```

### Advisor (Opus)
```
Agent(
  subagent_type="general-purpose",
  model="opus",
  prompt="<role prompt from ri-advisor.md>\n\n<stage-specific task>\n\n<context files>"
)
```

### Visiting Professor (Opus)
```
Agent(
  subagent_type="general-purpose",
  model="opus",
  prompt="<role prompt from ri-visiting-prof.md>\n\n<stage-specific task>\n\n<context files>"
)
```

---

## Resumability

If the pipeline is interrupted, check `proposal_space/state/state.json`
for `current_stage` and `current_round`. Resume from that point.

Check for existing output files before re-running any stage:
- `landscape_round{N}.md` exists → skip Stage 1
- `candidates_round{N}.md` exists → skip Stage 2
- etc.

---

## Error Handling

- If a Student agent returns insufficient results, retry once with
  adjusted instructions (broader search, more ideas requested).
- If an Advisor/VP agent returns unparseable output (no `=== IDEA:` blocks),
  retry once with explicit format reminder.
- If both retries fail, log the error and ask the user for guidance.
- Never silently skip a quality gate.
