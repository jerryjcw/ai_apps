# 06 — Experiment Planning & Novel Approach Synthesis (Stage 4)

## Overview

Stage 4 takes a research proposal from Stage 3 and produces a complete, actionable experiment plan. This is the most complex LLM stage — it requires both broad research (searching literature for novelty, baselines, related methods) and deep coherent planning (MVE → phased plan → ablations → risks, where each component depends on the previous).

---

## Multi-Agent Architecture Decision

### Why Not Full Multi-Agent?

Stage 4's planning tasks are **deeply interdependent**: the ablation design depends on the experiment plan, which depends on the MVE, which depends on the novelty assessment. Splitting these across independent agents fragments the reasoning chain and forces expensive context duplication. In our testing of SOTA multi-agent patterns:

- **AutoGen/CrewAI-style role teams**: Each "agent" needs the same proposal context (~20K tokens), so 4 agents = 4× context cost for marginal quality gain. Coordination failures add latency and error surface.
- **LangGraph DAG orchestration**: Adds a framework dependency for ~6 LLM calls. The pipeline shape is simple enough to express as Python async code.
- **Full debate/Society-of-Mind**: Overkill. The bottleneck is quality of reasoning about a single proposal, not diversity of perspectives on it.

### What Does Help: Adversarial Critic

The one multi-agent pattern that provides genuine, measurable quality improvement is the **Adversarial Critic** (Reflection/Reflexion pattern). The planning agent has confirmation bias toward its own plan — asking it to self-critique produces weaker criticism than an independent agent with an explicit "find problems" directive.

This mirrors the research peer review process: the author (planning agent) and the reviewer (critic agent) bring fundamentally different cognitive stances to the same artifact. The reviewer's job is not to agree but to stress-test.

### Adopted Architecture: Orchestrator + Parallel Research + Planner + Critic

```
User selects proposal (paper #3, proposal #1)
         │
         ▼
  ┌──────────────────────┐
  │  Python Orchestrator  │  (not an LLM — plain code)
  │  Load proposal +      │  Load review context from Stage 3
  │  all run papers        │  Load all papers from the run (for FR-8.3 cross-pollination)
  └──────┬───────────────┘
         │
    ┌────┼──────────────────┐     Parallel async API calls
    ▼    ▼                  ▼     (Semantic Scholar, ~5-10s)
  ┌────────┐  ┌──────────┐  ┌──────────┐
  │ S2:    │  │ S2:      │  │ S2:      │
  │ Novelty│  │ Baseline │  │ Related  │
  │ Search │  │ Search   │  │ Methods  │
  └───┬────┘  └────┬─────┘  └────┬─────┘
      │            │              │
      └────────────┼──────────────┘
                   ▼
         research_context (grounded data)
                   │
                   ▼
  ┌────────────────────────────┐
  │  Planning Agent (Opus)      │  Multi-turn, extended thinking
  │                             │
  │  Turn 1: Novelty +          │  thinking: 24K
  │          Novel Synthesis    │  Input: proposal + S2 results + all run papers
  │                             │
  │  Turn 2: MVE +              │  thinking: 24K
  │          Full Experiment    │  Builds on Turn 1 context
  │          Plan               │
  │                             │
  │  Turn 3: Ablations +        │  thinking: 24K
  │          Baselines +        │  Builds on Turn 1+2 context
  │          Risk Register +    │
  │          Issue Anticipation │
  └──────────┬─────────────────┘
             │  draft_plan (English)
             ▼
  ┌────────────────────────────┐
  │  Critic Agent (Opus)        │  SEPARATE conversation
  │                             │  thinking: 16K
  │  Persona: "Experienced      │
  │  reviewer who has seen      │
  │  many projects fail"        │
  │                             │
  │  Reviews: novelty claims,   │
  │  timeline realism, missing  │
  │  baselines, overlooked      │
  │  risks, MVE validity        │
  └──────────┬─────────────────┘
             │  critique (specific issues + suggestions)
             ▼
  ┌────────────────────────────┐
  │  Planning Agent Turn 4      │  CONTINUATION of planning conversation
  │  (Opus)                     │  thinking: 16K
  │                             │
  │  Revise plan addressing     │
  │  each critic point          │
  └──────────┬─────────────────┘
             │  final_plan (English)
             ▼
  ┌────────────────────────────┐
  │  Deterministic Rendering    │  Python code (no LLM)
  └──────────┬─────────────────┘
             │  experiment_plan_en.md
             ▼
  ┌────────────────────────────┐
  │  Translation (Sonnet)       │  Single LLM call, no thinking
  └──────────┬─────────────────┘
             │  experiment_plan_zh.md
             ▼
           Done
```

**Total LLM calls per proposal**: 4 Opus (3 planning + 1 critic) + 1 Opus (revision) + 1 Sonnet (translation) = **5 Opus + 1 Sonnet**

### Why This Architecture Works

1. **Coherent planning chain**: Turns 1-3 share a single conversation, so the model's thinking from novelty assessment directly informs MVE design, which informs ablation choices. No context loss.
2. **Independent critique**: The critic starts fresh with only the draft plan — no sunk-cost bias from the reasoning that produced it. It evaluates the plan as a reviewer would evaluate a paper.
3. **Grounded research**: Parallel S2 calls provide real papers, real baselines, real citation data. The planning agent reasons over facts, not hallucinations.
4. **Cross-pollination**: Loading ALL papers from the current pipeline run into the planning context enables FR-8.3 (novel approach synthesis from multiple papers).
5. **No framework dependency**: Pure Python + Anthropic SDK. No LangGraph, no AutoGen, no CrewAI.
6. **S2 failure transparency**: If Semantic Scholar is unavailable, the pipeline warns the user (CLI + markdown banner) and `research_context["s2_available"]` is set to `False`. The planning agent is told its novelty search may be incomplete, and the output is flagged for manual verification.

---

## Module: `src/planning/experiment_planner.py`

### Public Interface

```python
@dataclass
class ExperimentPlan:
    """Complete experiment plan output for one proposal."""
    paper_index: int
    proposal_index: int
    paper_title: str
    proposal_summary: str

    # Planning outputs
    novelty_assessment: str        # Turn 1: novelty delta + existing work comparison
    novel_approaches: str          # Turn 1: synthesized approaches from cross-pollination
    mve: str                       # Turn 2: minimum viable experiment
    full_plan: str                 # Turn 2: phased experiment plan
    ablation_design: str           # Turn 3: ablation table
    baseline_selection: str        # Turn 3: baselines with code availability
    risk_register: str             # Turn 3: ranked risks with early warnings
    issue_anticipation: str        # Turn 3: practical gotchas

    # Critic outputs
    critique: str                  # Critic's review
    revision_notes: str            # How the plan was revised in response

    # Metadata
    thinking_logs: list[str]       # One per turn + critic + revision
    research_context: dict         # S2 search results used


async def run_experiment_planning(
    paper_index: int,
    proposal_index: int,
    run_dir: Path,
    config: AppConfig,
    llm: LLMClient,
) -> ExperimentPlan:
    """Run full Stage 4 pipeline for a selected proposal.

    Steps:
    1. Load proposal from Stage 3 review output.
    2. Load all papers from the current run (for cross-pollination).
    3. Run parallel Semantic Scholar searches (novelty, baselines, related).
    4. Run planning agent (Opus, 3 turns).
    5. Run critic agent (Opus, separate conversation).
    6. Run revision turn (Opus, continuation of planning conversation).
    7. Render to markdown + translate.
    """
```

---

## Phase 1: Parallel Research Context Assembly

Before any LLM call, gather grounded data from Semantic Scholar. These are independent API calls that run concurrently.

### `src/enrichment/semantic_scholar.py` (extended)

```python
async def gather_planning_research_context(
    proposal: dict,
    paper_arxiv_id: str,
    client: httpx.AsyncClient,
) -> dict:
    """Gather all research context needed for experiment planning.

    Runs multiple searches in parallel:
    1. Novelty search: 2-3 focused queries for similar methods/approaches
    2. Baseline search: established methods on the target task/benchmark
    3. Related methods: broader landscape via citation context

    Returns dict with "novelty_papers", "baseline_papers", "related_methods",
    and "s2_available" (bool indicating whether S2 returned data).
    """
    # Build focused search queries from structured proposal fields
    novelty_queries = _build_novelty_queries(proposal)
    baseline_query = _build_baseline_query(proposal)

    # Launch all searches in parallel
    novelty_tasks = [_search_s2(q, client, max_results=10) for q in novelty_queries]
    baseline_task = _search_s2(baseline_query, client, max_results=15, sort_by_citations=True)
    related_task = fetch_citation_context(paper_arxiv_id, client)

    all_results = await asyncio.gather(
        *novelty_tasks, baseline_task, related_task,
        return_exceptions=True,
    )

    # Merge novelty results from multiple queries, deduplicate by title
    novelty_results = []
    seen_titles = set()
    for result in all_results[:len(novelty_queries)]:
        if isinstance(result, Exception):
            continue
        for paper in result:
            title_key = paper["title"].lower().strip()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                novelty_results.append(paper)

    baselines = all_results[len(novelty_queries)] if not isinstance(all_results[len(novelty_queries)], Exception) else []
    related = all_results[-1] if not isinstance(all_results[-1], Exception) else {"references": [], "citations": []}

    s2_available = bool(novelty_results or baselines or related.get("references"))

    return {
        "novelty_papers": novelty_results,
        "baseline_papers": baselines,
        "related_methods": related,
        "s2_available": s2_available,
    }


def _build_novelty_queries(proposal: dict) -> list[str]:
    """Extract 2-3 focused search queries from a structured research proposal.

    Uses the structured fields from Stage 3's tool use output (not raw text)
    to build precise queries that find genuinely related work.

    Strategy:
    1. Combine approach keywords + target task (most specific)
    2. Core method/technique name alone (broader)
    3. Problem domain + key technique (alternative framing)

    No LLM needed — the structured proposal fields provide clean inputs.
    """
    # Common filler phrases to strip from approach text
    FILLER = [
        "we propose", "novel approach", "new method", "framework for",
        "by combining", "that leverages", "which enables", "designed to",
    ]

    approach = proposal.get("approach", "")
    target_task = proposal.get("target_task", "")
    problem = proposal.get("problem_statement", "")

    # Strip filler from approach to get core method terms
    clean_approach = approach
    for filler in FILLER:
        clean_approach = clean_approach.lower().replace(filler, "")
    # Take first ~100 chars of cleaned approach (core method description)
    method_terms = clean_approach.strip()[:100]

    queries = []
    # Query 1: method + target task (most specific)
    if target_task:
        queries.append(f"{method_terms} {target_task}")
    # Query 2: method terms alone (broader)
    queries.append(method_terms)
    # Query 3: problem framing + key technique
    if problem:
        problem_short = problem[:80]
        queries.append(problem_short)

    return queries[:3]  # max 3 queries


def _build_baseline_query(proposal: dict) -> str:
    """Build a baseline search query focused on the target task/benchmark.

    Looks for well-established methods on the same benchmark,
    not methods similar to the proposal.
    """
    target_task = proposal.get("target_task", "")
    datasets = proposal.get("datasets", [])
    dataset_str = " ".join(datasets[:3]) if datasets else ""
    return f"{target_task} {dataset_str} state-of-the-art".strip()


async def _search_s2(
    query: str,
    client: httpx.AsyncClient,
    max_results: int = 15,
    sort_by_citations: bool = False,
) -> list[dict]:
    """Generic Semantic Scholar search.

    Args:
        query: Search query string.
        client: httpx async client.
        max_results: Max papers to return.
        sort_by_citations: If True, sort by citation count (for baselines).

    Returns:
        List of paper dicts with title, authors, year, venue, abstract, citations.
    """
    S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
    fields = "title,authors,year,venue,abstract,citationCount,externalIds,openAccessPdf"

    params = {
        "query": query,
        "fields": fields,
        "limit": max_results,
    }
    if sort_by_citations:
        params["sort"] = "citationCount:desc"

    resp = await client.get(S2_SEARCH_URL, params=params)
    if resp.status_code != 200:
        return []

    results = []
    for paper in resp.json().get("data", []):
        results.append({
            "title": paper.get("title", ""),
            "authors": [a["name"] for a in paper.get("authors", [])[:4]],
            "year": paper.get("year"),
            "venue": paper.get("venue", ""),
            "abstract": (paper.get("abstract") or "")[:300],
            "citations": paper.get("citationCount", 0),
            "arxiv_id": (paper.get("externalIds") or {}).get("ArXiv"),
            "has_pdf": paper.get("openAccessPdf") is not None,
        })
    return results
```

---

## Phase 2: Planning Agent (Opus, Multi-Turn)

### System Prompt — `build_plan_system_prompt(criteria)`

```python
def build_plan_system_prompt(criteria: CriteriaConfig) -> str:
    return f"""You are a principal AI researcher designing a concrete experiment plan.
You have published 50+ papers at top venues and mentored dozens of students through
the full research cycle from idea to publication. You know what makes projects succeed
and — more importantly — what makes them fail.

## Lab Constraints
- Compute: up to {criteria.max_compute_gpus}x {criteria.gpu_model} GPUs
- Timeline: 3-4 months to submission
- Target venues: {', '.join(criteria.target_venues)}
- Focus: {', '.join(criteria.focus_areas)}

## Your Standards
- Every claim of novelty must be backed by specific evidence of what exists and what doesn't
- Every experiment must have explicit success/failure criteria BEFORE running it
- Every timeline estimate must account for debugging, failed runs, and iteration
- Feasibility means "can MY lab do this with OUR constraints", not "is this theoretically possible"
- Baselines must be reproducible — if there's no public code, note the reproduction risk

You are having a multi-turn conversation. Each turn builds on the previous.
Think deeply before responding."""
```

### Tool Schemas for Structured Output

Each planning turn uses **tool use** to guarantee structured field extraction. The model still gets full thinking budget for deep reasoning, but outputs into a schema that maps directly to `ExperimentPlan` fields.

```python
PLAN_TURN1_TOOL = {
    "name": "submit_novelty_and_synthesis",
    "description": "Submit novelty assessment and novel approach synthesis",
    "input_schema": {
        "type": "object",
        "properties": {
            "novelty_assessment": {"type": "string", "description": "Side-by-side comparison with closest existing work"},
            "novel_approaches": {"type": "string", "description": "1-2 synthesized approaches from cross-pollination"},
        },
        "required": ["novelty_assessment", "novel_approaches"],
    },
}

PLAN_TURN2_TOOL = {
    "name": "submit_experiment_design",
    "description": "Submit MVE and full experiment plan",
    "input_schema": {
        "type": "object",
        "properties": {
            "mve": {"type": "string", "description": "Minimum viable experiment with hypothesis, setup, success/failure criteria"},
            "full_plan": {"type": "string", "description": "3-phase experiment plan with go/no-go criteria"},
        },
        "required": ["mve", "full_plan"],
    },
}

PLAN_TURN3_TOOL = {
    "name": "submit_plan_details",
    "description": "Submit ablations, baselines, risks, and practical issues",
    "input_schema": {
        "type": "object",
        "properties": {
            "ablation_design": {"type": "string", "description": "3-5 ablations, each answering one question"},
            "baseline_selection": {"type": "string", "description": "Selected baselines with code availability"},
            "risk_register": {"type": "string", "description": "Top 3-5 risks ranked by likelihood x impact"},
            "issue_anticipation": {"type": "string", "description": "Practical issues researcher will encounter"},
        },
        "required": ["ablation_design", "baseline_selection", "risk_register", "issue_anticipation"],
    },
}
```

Each turn calls `llm.call_with_tool()` with the appropriate schema. The conversation context from previous turns is still passed via `messages` (with thinking blocks preserved), so the model maintains coherent reasoning across turns. The tool use response is parsed directly into the `ExperimentPlan` dataclass fields — no section-header parsing needed.

### Turn 1 — Novelty Assessment + Novel Approach Synthesis

```python
def build_plan_novelty_prompt(
    proposal: dict,
    novelty_papers: list[dict],
    all_run_papers: list[dict],
) -> str:
    """Turn 1: Assess novelty and synthesize new approaches.

    Args:
        proposal: The selected proposal from Stage 3.
        novelty_papers: S2 search results for similar methods.
        all_run_papers: All papers analyzed in this pipeline run (for cross-pollination).
    """
    # Format S2 novelty search results
    novelty_context = _format_paper_list(novelty_papers, "Potentially Similar Existing Work")

    # Format all papers from the current run (titles + core contributions from Stage 2)
    run_papers_context = _format_run_papers(all_run_papers)

    return f"""## Research Proposal to Evaluate

{proposal['problem_statement']}

**Proposed approach:** {proposal['approach']}
**Target task/benchmark:** {proposal.get('target_task', 'see approach')}

## Part A: Novelty Verification

The following papers were found via Semantic Scholar search and may overlap with
this proposal. For each relevant paper, assess how closely it matches the proposal:

{novelty_context}

Produce a **novelty delta** — a specific, technical side-by-side comparison between
this proposal and the closest existing work. Structure as:

1. **Closest existing work**: [paper] by [authors] ([year])
2. **What they did**: [specific method]
3. **What this proposal does differently**: [specific technical difference]
4. **Is this difference meaningful?**: [why the delta matters for results/insights]

If the proposal is NOT novel, suggest a specific modification that would make it novel.

## Part B: Novel Approach Synthesis

Here are ALL papers analyzed in this pipeline run. Look for opportunities to combine
ideas from DIFFERENT papers into approaches the user would not have seen by reading
each paper individually:

{run_papers_context}

Synthesize 1-2 genuinely new approaches by combining techniques from different papers.
For each:
1. Which ideas are being combined, and from which papers
2. Why this combination hasn't been tried (or why now is the right time)
3. What the expected advantage is over doing either technique alone
4. A concrete technical sketch (not vague — specific enough to implement)"""
```

### Turn 2 — MVE + Full Experiment Plan

```python
def build_plan_experiment_prompt() -> str:
    return """Based on your novelty assessment, design the experiments.

## Part A: Minimum Viable Experiment (MVE)

Design the SMALLEST experiment that tests the core hypothesis. Target: completable
in under 48 GPU-hours on the lab's hardware.

For the MVE, provide:
1. **Hypothesis**: A specific, falsifiable claim (e.g., "Method X improves metric Y
   by at least Z% on dataset D compared to baseline B")
2. **Setup**: The exact model, dataset, and metric triple
3. **Expected runtime**: GPU type x count x hours
4. **Success criterion**: What quantitative result validates continuing?
5. **Failure criterion**: What result means the idea doesn't work?
   Be specific — "no improvement" is not enough. What magnitude of failure
   should trigger a pivot vs. debugging?

If the core hypothesis cannot be tested in 48 GPU-hours, decompose it into a
simpler sub-hypothesis that can be.

## Part B: Full Experiment Plan (conditioned on MVE success)

Design a phased plan:

### Phase 1: Core Validation (1-2 weeks)
- What experiments to run beyond MVE
- What variations to test
- Go/no-go criteria for Phase 2

### Phase 2: Scaling & Ablations (2-3 weeks)
- Scale to full model/dataset
- Run ablation studies (detailed in Turn 3)
- Go/no-go criteria for Phase 3

### Phase 3: Benchmarks & Paper-Ready Results (2-4 weeks)
- Full benchmark evaluation
- Comparison with all baselines
- Analysis and visualization for paper figures

For each phase: specific experiments, expected GPU-hours, datasets, and deliverables."""
```

### Turn 3 — Ablations + Baselines + Risks + Issues

```python
def build_plan_details_prompt(
    baseline_papers: list[dict],
    criteria: CriteriaConfig,
) -> str:
    baseline_context = _format_paper_list(baseline_papers, "Candidate Baselines from Literature")

    return f"""Complete the experiment plan with ablations, baselines, risks, and practical issues.

## Part A: Ablation Design

Identify the 3-5 most important design choices in the proposed approach.
For each, create an ablation:

| Component | What to vary | What it tests | Expected outcome if it matters | Expected outcome if it doesn't |
|-----------|-------------|---------------|-------------------------------|-------------------------------|
| ... | ... | ... | ... | ... |

Each ablation must answer exactly ONE question. Do not propose ablations that test
obvious components or redundant variations.

## Part B: Baseline Selection

Select specific, reproducible baselines from the following candidates and your knowledge:

{baseline_context}

For each selected baseline:
1. **Method + reference**: Exact paper
2. **Public code**: Is there an official or well-maintained repo? URL if known
3. **Expected performance**: On the target benchmark, what does this method achieve?
4. **Why this baseline**: What claim does comparing against it establish?
5. **Reproduction risk**: If no public code, estimate effort to reimplement

## Part C: Risk Register

Identify the top 3-5 risks ranked by likelihood x impact.

For each risk:
1. **Description**: What could go wrong (specific technical mechanism, not generic)
2. **Early warning signs**: What would you observe in the FIRST WEEK that suggests
   this risk is materializing
3. **Mitigation**: What to do if you see the early warning signs
4. **Pivot plan**: If mitigation fails, what's plan B?

Ground each risk in known failure patterns. Not "training might diverge" but
"attention entropy collapse when scaling beyond 2B parameters without proper
initialization, as documented in [specific work]."

## Part D: Issue Anticipation

Flag practical issues the researcher will likely encounter:
- Known training instabilities for this type of approach
- Dataset licensing or availability concerns
- Reproducibility pitfalls (hyperparameter sensitivity, random seed variance)
- Hardware-specific constraints (custom CUDA kernels, memory requirements)
- Dependency version conflicts (e.g., specific PyTorch/transformers versions needed)
- Common debugging dead-ends for this class of methods

Be specific. "Learning rate matters" is useless. "This method is sensitive to warmup
schedule — [Author 2024] reports 5x performance variance between linear and cosine
warmup for similar architectures" is useful."""
```

---

## Draft Plan Assembly

After the 3 planning turns complete, the orchestrator assembles their structured outputs into a single document for the critic. Since planning turns use tool use, each field is cleanly separated.

```python
def _assemble_draft_plan(turn_results: list[dict]) -> str:
    """Assemble planning turn outputs into a structured draft for critic review.

    Args:
        turn_results: List of 3 dicts from tool use (Turn 1, 2, 3 outputs).

    Returns:
        Formatted markdown string with clear section structure.
    """
    t1, t2, t3 = turn_results
    return f"""# Novelty Assessment

{t1['novelty_assessment']}

# Novel Synthesized Approaches

{t1['novel_approaches']}

---

# Minimum Viable Experiment

{t2['mve']}

# Full Experiment Plan

{t2['full_plan']}

---

# Ablation Design

{t3['ablation_design']}

# Baseline Selection

{t3['baseline_selection']}

# Risk Register

{t3['risk_register']}

# Practical Issues

{t3['issue_anticipation']}"""
```

---

## Phase 3: Adversarial Critic (Opus, Separate Conversation)

The critic runs in a **separate conversation** — it does not share the planning agent's context or reasoning. This ensures independent evaluation without confirmation bias.

The critic receives both the assembled draft plan AND the raw S2 novelty search results. This enables the critic to independently verify novelty claims — if the planner cherry-picked favorable S2 results and ignored closer matches, the critic can catch this.

### Critic System Prompt

```python
def build_critic_system_prompt() -> str:
    return """You are an experienced AI research reviewer and project advisor. You have
reviewed hundreds of research proposals and experiment plans. You have seen projects
fail in every possible way: unrealistic timelines, missing baselines, overlooked
confounds, overclaimed novelty, compute estimates that were off by 10x, and ideas
that were already published.

Your job is to STRESS-TEST this experiment plan. You are not trying to be supportive —
you are trying to find every way this plan could fail, every claim that doesn't hold up,
and every gap the planner missed.

Be specific and constructive. For each issue you find, suggest a concrete fix."""
```

### Critic Prompt

```python
def build_critic_prompt(
    draft_plan: str,
    criteria: CriteriaConfig,
    s2_novelty_papers: list[dict],
) -> str:
    """Build critic prompt with draft plan AND raw S2 search results.

    The S2 results let the critic independently verify novelty claims —
    it can check whether the planner missed closer existing work.
    """
    s2_context = _format_paper_list(s2_novelty_papers, "Raw Novelty Search Results from Semantic Scholar")

    return f"""Review the following experiment plan. The researcher has
{criteria.max_compute_gpus}x {criteria.gpu_model} GPUs and targets
{', '.join(criteria.target_venues)}.

## Experiment Plan to Review:

{draft_plan}

## Raw Semantic Scholar Novelty Search Results

The following papers were returned by Semantic Scholar when searching for work
similar to this proposal. The planner used these to assess novelty. Check whether
the planner's novelty claims hold up — did they miss a closer match?

{s2_context}

## Review Checklist

Evaluate each dimension. For each, state whether it passes or fails, and why:

1. **Novelty claim validity**: Is the claimed novelty delta actually novel? Could
   the "closest existing work" comparison be missing a closer match? Are there
   concurrent/recent papers the planner may have missed?

2. **MVE soundness**: Is the hypothesis actually falsifiable? Are the success/failure
   criteria meaningful (not too easy to pass, not impossible)? Can the MVE really
   run in the stated GPU-hours?

3. **Timeline realism**: Account for debugging time, failed runs, reviewer response
   cycles. Is each phase achievable in the stated time? Where is the plan most likely
   to slip?

4. **Baseline completeness**: Are the strongest competing methods included? Is there
   a baseline that would be an obvious reviewer objection if missing?

5. **Ablation coverage**: Do the ablations actually isolate the contribution? Is there
   a confound that no ablation addresses?

6. **Risk completeness**: Are there risks the planner missed? Especially: is the
   proposed approach sensitive to any hyperparameter or design choice that isn't in
   the ablation table?

7. **Practical feasibility**: Any hardware, data, or dependency issues not flagged?

For each issue found, provide:
- **Issue**: What's wrong
- **Severity**: Critical / Major / Minor
- **Suggested fix**: Specific action to address it"""
```

---

## Phase 4: Revision (Planning Agent Turn 4)

The critic's output is fed back into the **original planning conversation** (continuation, not new conversation). This preserves the full reasoning chain from Turns 1-3.

```python
def build_revision_prompt(critique: str) -> str:
    return f"""An independent reviewer has critiqued your experiment plan. Address each
issue raised below. For each:

1. If the critic is right: revise the relevant section of your plan
2. If the critic is wrong or the issue is already addressed: explain why, citing
   your earlier reasoning

## Reviewer Critique:

{critique}

## Instructions

Produce a **revised plan summary** that integrates the valid critique points.
Do not rewrite the entire plan — focus on the sections that changed and explain
what changed and why. This will be appended to the original plan as a "Revisions
After Review" section."""
```

---

## Phase 5: Output Rendering

### Deterministic Markdown — `src/output/formatter.py` (extended)

```python
def render_experiment_plan_markdown(
    plan: ExperimentPlan,
    run_date: str,
) -> str:
    """Render experiment plan into structured markdown.

    Sections:
    1. Proposal Summary
    2. Novelty Assessment (with delta table)
    3. Novel Synthesized Approaches
    4. Minimum Viable Experiment
    5. Full Experiment Plan (3 phases)
    6. Ablation Design (table)
    7. Baseline Selection (table with code availability)
    8. Risk Register (ranked table)
    9. Practical Issues
    10. Reviewer Critique & Revisions
    """
```

### Translation

Same strategy as Stage 3: English is the primary output, Chinese is produced by a single Sonnet translation call.

---

## Output Files

```
data/runs/2026-03-20/
├── ...existing files...
├── experiment_plan_p3_r1_en.md      # Paper 3, Proposal 1, English
├── experiment_plan_p3_r1_zh.md      # Paper 3, Proposal 1, Chinese
├── experiment_plan_p3_r1.json       # Structured data (all fields)
└── thinking_logs/
    ├── ...existing logs...
    ├── stage4_p3_r1_plan_turn1.txt
    ├── stage4_p3_r1_plan_turn2.txt
    ├── stage4_p3_r1_plan_turn3.txt
    ├── stage4_p3_r1_critic.txt
    └── stage4_p3_r1_revision.txt
```

File naming: `p{paper_index}_r{proposal_index}` to disambiguate when multiple proposals are planned.

---

## Cost Estimate Per Proposal

**Important**: Multi-turn extended thinking requires preserving thinking blocks in conversation history. These accumulated thinking tokens count as input tokens in subsequent turns, significantly increasing cost for later turns.

| Call | Model | Input Tokens | Output Tokens | Thinking Tokens | Est. Cost |
|------|-------|-------------|---------------|-----------------|-----------:|
| Planning Turn 1 (novelty + synthesis) | Opus | ~30,000 | ~4,000 | ~24,000 | ~$1.20 |
| Planning Turn 2 (MVE + plan) | Opus | ~60,000 | ~5,000 | ~24,000 | ~$2.10 |
| Planning Turn 3 (ablations + risks) | Opus | ~100,000 | ~6,000 | ~24,000 | ~$3.00 |
| Critic review | Opus | ~26,000 | ~3,000 | ~16,000 | ~$0.90 |
| Planning Turn 4 (revision) | Opus | ~135,000 | ~3,000 | ~16,000 | ~$3.50 |
| Translation | Sonnet | ~15,000 | ~12,000 | — | ~$0.15 |
| **Total per proposal** | | | | | **~$10–11** |

**Token accumulation breakdown** (why later turns cost more):
- Turn 2 input = Turn 1 input (~30K) + Turn 1 thinking (~24K, preserved) + Turn 1 output (~4K) + Turn 2 prompt (~2K) = ~60K
- Turn 3 input = Turn 2 accumulated (~60K) + Turn 2 thinking (~24K) + Turn 2 output (~5K) + Turn 3 prompt (~6K with baselines) = ~95-105K
- Revision input = Turn 3 accumulated (~100K) + Turn 3 thinking (~24K) + Turn 3 output (~6K) + critic output (~3K) + revision prompt (~2K) = ~135K

**Cost optimization note**: The Anthropic API requires thinking block preservation for multi-turn extended thinking. If future API versions allow stripping thinking from history while keeping text outputs, input costs for Turns 2-4 would drop by ~50%.

---

## Configuration

New fields in `[llm]` section of `config.toml`:

```toml
model_plan = "claude-opus-4-6"           # Stage 4 planning agent
model_critic = "claude-opus-4-6"         # Stage 4 adversarial critic
thinking_budget_plan = 24000             # per planning turn (4 turns max)
thinking_budget_critic = 16000           # critic review
```

---

## Integration with Stage 3

Stage 4 reads Stage 3's **structured JSON output** to obtain the proposal being planned. It expects:
- `literature_review.json` — structured proposals from Turn 3 tool use (reliable extraction)
- `filter_result.json` — to load all papers from the run (for cross-pollination)
- `enriched_papers.json` — to get arXiv IDs for S2 lookups

The proposal is identified by `(paper_index, proposal_index)` where `paper_index` refers to the paper number in the review and `proposal_index` is 1-indexed within that paper's proposals (typically 1-3).

### Proposal Extraction

```python
def load_proposal(
    review_json_path: Path,
    paper_index: int,
    proposal_index: int,
) -> dict:
    """Load a specific proposal from Stage 3 structured JSON output.

    Reads literature_review.json (produced by Turn 3 tool use) and
    returns the proposal dict with all required fields:
    problem_statement, approach, target_task, compute_requirements,
    datasets, feasibility_assessment, risks, expected_impact, target_venue.

    No markdown parsing needed — Stage 3 Turn 3 uses tool use to
    guarantee structured output.

    Raises:
        PlanningError: If paper_index or proposal_index not found.
    """
    data = json.loads(review_json_path.read_text())
    for paper in data["papers"]:
        if paper["paper_index"] == paper_index:
            for prop in paper["proposals"]:
                if prop["index"] == proposal_index:
                    return prop
    raise PlanningError(
        f"Proposal {proposal_index} for paper {paper_index} not found in {review_json_path}"
    )
```
