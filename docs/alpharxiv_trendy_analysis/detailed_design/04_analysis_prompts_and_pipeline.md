# 04 — Analysis Prompts & Pipeline (Stages 2–3)

## Overview

This document specifies the exact prompt design for the two LLM-heavy stages: Stage 2 (filter & analyze) and Stage 3 (literature review). The prompts must produce output matching the quality of the reference cowork sessions.

---

## Stage 2: Filter & Analyze — `src/analysis/filter_analyzer.py`

### Pipeline Flow

```
enriched_papers.json
        │
        ▼
  ┌─────────────────┐
  │  Phase A         │  Model: claude-opus-4-6
  │  Deep Analysis   │  Extended thinking (budget: 40000)
  │  (tool use JSON) │  max_tokens: 32000
  └──────┬──────────┘
         │  filter_result.json
         │
         ▼
  ┌─────────────────┐
  │  Validation      │  validate_analysis_result()
  │  (auto-retry on  │  Check completeness, rating range,
  │   critical fail) │  exclusion specificity, Top 5
  └──────┬──────────┘
         │
    ┌────┴────┐
    ▼         ▼
  ┌────────┐  ┌────────┐
  │ Format │  │ Format │   Deterministic Python code
  │   ZH   │  │   EN   │   render_analysis_markdown()
  └───┬────┘  └───┬────┘
      ▼           ▼
filtered_zh.md  filtered_en.md
```

### Public Interface

```python
@dataclass
class AnalysisResult:
    """Complete analysis output."""
    filter_result: dict           # parsed JSON from Phase A
    filtered_zh: str              # rendered Chinese markdown
    filtered_en: str              # rendered English markdown
    thinking_log_analysis: str    # Phase A thinking
    validation_warnings: list[str]  # any quality warnings from validation


async def run_analysis(
    papers: list[EnrichedPaper],
    config: AppConfig,
    llm: LLMClient,
) -> AnalysisResult:
    """Run full Stage 2 pipeline: analyze + validate + render.

    Phase A: One LLM call (Opus) with extended thinking to analyze all papers.
             Uses tool use for guaranteed valid JSON output.
    Validation: Check completeness and quality; auto-retry on critical failures.
    Phase B: Deterministic Python rendering to zh/en markdown (no LLM).
    """
```

---

### Phase A: Deep Analysis Prompt

#### System Prompt — `build_filter_system_prompt(criteria)`

```python
def build_filter_system_prompt(criteria: CriteriaConfig) -> str:
    return f"""You are a senior AI researcher evaluating trending papers for a research lab.

## Your Lab's Constraints
- Compute budget: up to {criteria.max_compute_gpus}× {criteria.gpu_model} GPUs
- Focus areas: {', '.join(criteria.focus_areas)}
- Theoretical requirement: papers must have theory, model, loss, or training improvements — not pure engineering/systems
- Target venues: {', '.join(criteria.target_venues)}

## Your Task
Evaluate each paper and decide: INCLUDE (worth pursuing as research direction) or EXCLUDE (not relevant).

## Rating Rubrics

### Importance (1–5 stars)
- ⭐ (1): Incremental improvement, marginal novelty
- ⭐⭐ (2): Solid but derivative work
- ⭐⭐⭐ (3): Good contribution with clear technical merit
- ⭐⭐⭐⭐ (4): Strong contribution, novel insight, significant impact potential
- ⭐⭐⭐⭐⭐ (5): Paradigm-shifting, opens entirely new research direction

IMPORTANT: Use the full range. If all papers are 3–4 stars, you are not differentiating enough. Expect roughly: 10% at 5★, 25% at 4★, 35% at 3★, 20% at 2★, 10% at 1★.

### Conference Probability
Base your estimate on: (1) acceptance rates at target venues (typically 20–30%), (2) novelty of the approach, (3) experimental rigor, (4) how crowded the subfield is.
- Green 🟢: >= 65% — strong chance, novel contribution in an active area
- Yellow 🟡: 50–64% — competitive but feasible with good execution
- Red 🔴: < 50% — crowded space, incremental, or niche

### Research Directions
Each direction (a–d) must be:
- Specific enough to start a project (not "explore more X")
- Include a concrete technical approach
- Grounded in the lab's compute constraints

BAD example: "Explore more data augmentation techniques"
GOOD example: "Design uncertainty-aware decoding using the information bottleneck framework from this paper, validated on GSM8K/MATH with a 7B model (8×H200, ~1 week)"

### Exclusion Reasons
Must be specific. Not "not relevant" but "Pure CV/video generation, not LLM-related" or "Already published at ICLR 2026, mature direction with limited incremental space".

## Output Format
Return valid JSON matching the schema provided in the user message. No markdown fences. No preamble."""
```

#### User Prompt — `build_filter_analysis_prompt(papers)`

```python
def build_filter_analysis_prompt(papers: list[EnrichedPaper]) -> str:
    papers_text = ""
    for p in papers:
        abstract = p.arxiv_abstract or p.abstract
        papers_text += f"""
---
Paper #{p.index}: {p.title}
Date: {p.date}
Authors: {p.authors_raw}
arXiv ID: {p.arxiv_id or 'unknown'}
Categories: {', '.join(p.arxiv_categories) if p.arxiv_categories else 'unknown'}
Hashtags: {', '.join(p.hashtags)}
Bookmarks: {p.bookmark_count} | Views: {p.view_count}
Abstract: {abstract}
"""

    return f"""Here are {len(papers)} trending papers from alphaxiv.org. Analyze all of them.

CRITICAL INSTRUCTION: Read ALL papers first before assigning any ratings. Your importance scores and conference probabilities must be relative — differentiate between papers. Do not cluster scores.

{papers_text}

Return your analysis as JSON matching this schema:
{{
    "included_papers": [
        {{
            "index": <int>,
            "title": "<str>",
            "arxiv_id": "<str or null>",
            "topic_category": "<specific sub-area, e.g. 'LLM Architecture — Residual Connection Improvement'>",
            "core_contribution": "<2-3 sentence technical summary of what is actually NEW>",
            "importance": <1-5>,
            "importance_justification": "<why this rating, relative to other papers>",
            "research_directions": [
                {{"label": "a", "direction": "<specific direction>", "feasibility": "<compute/data assessment>"}},
                {{"label": "b", "direction": "...", "feasibility": "..."}},
                {{"label": "c", "direction": "...", "feasibility": "..."}},
                {{"label": "d", "direction": "...", "feasibility": "..."}}
            ],
            "compute_estimate": "<GPU type × count × time>",
            "data_estimate": "<dataset size/type>",
            "datasets": ["<specific dataset names>"],
            "conference_probability_pct": <int 0-100>,
            "conference_probability_reasoning": "<why this probability>"
        }}
    ],
    "excluded_papers": [
        {{
            "index": <int>,
            "title": "<str>",
            "reason": "<specific exclusion reason>"
        }}
    ],
    "top5_summary": [
        {{
            "rank": <1-5>,
            "title": "<str>",
            "conference_probability": "<range like '75-85%'>",
            "compute": "<low/medium/high>",
            "rationale": "<1-line justification>"
        }}
    ]
}}"""
```

---

### Phase B: Deterministic Markdown Rendering — `src/output/formatter.py`

Phase B does **not** use the LLM. It is a deterministic Python function that transforms the structured JSON from Phase A into formatted markdown. This eliminates 2 unnecessary API calls, ensures formatting consistency, and removes the risk of LLM-introduced errors during rendering.

```python
# Field label maps for bilingual output
FIELD_LABELS = {
    "zh": {
        "header": "Filtered Research Topics",
        "item": "項目", "content": "內容",
        "arxiv": "arXiv", "topic": "Topic Category",
        "contribution": "核心貢獻", "importance": "重要性預估",
        "directions": "可做的大方向", "compute": "計算量預估",
        "data": "Data 量預估", "datasets": "Datasets",
        "conference": "衝擊頂會機率",
        "rank": "排名", "probability": "機率",
        "compute_short": "算力", "strength": "核心優勢",
        "exclude_reason": "排除原因",
    },
    "en": {
        "header": "Filtered Research Topics",
        "item": "Item", "content": "Content",
        "arxiv": "arXiv", "topic": "Topic Category",
        "contribution": "Core Contribution", "importance": "Importance",
        "directions": "Research Directions", "compute": "Compute Estimate",
        "data": "Data Estimate", "datasets": "Datasets",
        "conference": "Conference Probability",
        "rank": "Rank", "probability": "Probability",
        "compute_short": "Compute", "strength": "Key Strength",
        "exclude_reason": "Exclusion Reason",
    },
}


def render_analysis_markdown(filter_result: dict, run_date: str, lang: str) -> str:
    """Render structured analysis JSON into formatted markdown.

    Args:
        filter_result: Parsed JSON from Phase A (included_papers, excluded_papers, top5_summary).
        run_date: YYYY-MM-DD.
        lang: "zh" or "en".

    Returns:
        Complete markdown string matching the reference output format.
    """
    labels = FIELD_LABELS[lang]
    lines = [f"# {labels['header']} — AlphaXiv {run_date}\n"]

    # Filtering criteria section
    lines.append("## Filtering Criteria\n")
    # (criteria are embedded in filter_result or passed separately)

    # Included papers
    for paper in filter_result["included_papers"]:
        lines.append(f"### #{paper['index']} {paper['title']}\n")
        stars = "⭐" * paper["importance"]
        prob_pct = paper["conference_probability_pct"]
        prob_emoji = "🟢" if prob_pct >= 65 else ("🟡" if prob_pct >= 50 else "🔴")
        dirs = " ; ".join(
            f"({d['label']}) {d['direction']}" for d in paper["research_directions"]
        )

        lines.append(f"| {labels['item']} | {labels['content']} |")
        lines.append("|------|------|")
        lines.append(f"| **{labels['arxiv']}** | {paper.get('arxiv_id', 'unknown')} |")
        lines.append(f"| **{labels['topic']}** | {paper['topic_category']} |")
        lines.append(f"| **{labels['contribution']}** | {paper['core_contribution']} |")
        lines.append(f"| **{labels['importance']}** | {stars} — {paper['importance_justification']} |")
        lines.append(f"| **{labels['directions']}** | {dirs} |")
        lines.append(f"| **{labels['compute']}** | {paper['compute_estimate']} |")
        lines.append(f"| **{labels['data']}** | {paper['data_estimate']} |")
        lines.append(f"| **{labels['datasets']}** | {', '.join(paper['datasets'])} |")
        lines.append(f"| **{labels['conference']}** | {prob_emoji} **{prob_pct}%** — {paper['conference_probability_reasoning']} |")
        lines.append("")

    # Excluded papers table
    lines.append("## Excluded Papers\n")
    lines.append(f"| # | Paper | {labels['exclude_reason']} |")
    lines.append("|---|-------|---------|")
    for paper in filter_result["excluded_papers"]:
        lines.append(f"| {paper['index']} | {paper['title']} | {paper['reason']} |")
    lines.append("")

    # Top 5 summary table
    lines.append("## Top 5 Summary\n")
    lines.append(f"| {labels['rank']} | Paper | {labels['probability']} | {labels['compute_short']} | {labels['strength']} |")
    lines.append("|------|-------|------|------|---------|")
    for item in filter_result["top5_summary"]:
        lines.append(f"| {item['rank']} | {item['title']} | {item['conference_probability']} | {item['compute']} | {item['rationale']} |")

    return "\n".join(lines)
```

---

## Stage 3: Literature Review — `src/analysis/lit_reviewer.py`

### Pipeline Flow

```
User selects papers (e.g., --papers 1,3,5)
         │
         ▼
  ┌──────────────┐
  │ Fetch full    │  arXiv PDF/HTML content
  │ paper content │
  └──────┬───────┘
         │
  ┌──────┴───────┐
  │ Fetch citation│  Semantic Scholar API (for Turn 2 grounding)
  │ context       │
  └──────┬───────┘
         │
    For each paper (all turns in English):
         │
         ▼
  ┌──────────────┐
  │ Turn 1:       │  Model: claude-opus-4-6
  │ Deep Read     │  Extended thinking (budget: 16000)
  └──────┬───────┘  → Summary, methodology, limitations
         │
         ▼
  ┌──────────────┐
  │ Turn 2:       │  Model: claude-opus-4-6
  │ Literature    │  Extended thinking (budget: 16000)
  │ Landscape     │  + Semantic Scholar citation context
  └──────┬───────┘  → Related work map, frontiers, gaps
         │
         ▼
  ┌──────────────┐
  │ Turn 3:       │  Model: claude-opus-4-6
  │ Research      │  Extended thinking (budget: 16000)
  │ Proposals     │  Tool use → structured JSON proposals
  └──────┬───────┘
         │
    ┌────┴────┐
    ▼         ▼
  ┌────────┐  ┌──────────────────┐
  │Validate│  │ literature_      │  Structured JSON for Stage 4
  │proposal│  │ review.json      │  (proposals with all required fields)
  │ fields │  └──────────────────┘
  └───┬────┘
      ▼
  literature_review_en.md   (English — primary output)
         │
         ▼
  ┌──────────────┐
  │ Translate     │  Model: claude-sonnet-4-6
  │ EN → ZH       │  Single LLM call per paper (no thinking needed)
  └──────┬───────┘
         │
         ▼
  literature_review_zh.md   (Traditional Chinese — translated)
```

### Bilingual Strategy

Stage 3 runs entirely in **English** (the model's strongest language for research analysis). The Chinese version is produced by a single translation LLM call per paper using Sonnet, which is sufficient for translation quality. This approach:
- Costs 4 API calls per paper (3 Opus turns + 1 Sonnet translation) instead of 6 (running the full 3-turn conversation twice)
- Produces higher-quality English analysis (Opus reasoning in its strongest language)
- Keeps Chinese translation quality high (Sonnet is excellent at translation)

### Public Interface

```python
@dataclass
class ReviewProposal:
    """A single structured research proposal from Turn 3."""
    index: int
    problem_statement: str
    approach: str
    target_task: str
    compute_requirements: str
    datasets: list[str]
    feasibility_assessment: str
    risks: str
    expected_impact: str
    target_venue: str


@dataclass
class PaperReview:
    """Full literature review for one paper."""
    paper_index: int
    paper_title: str
    summary: str                          # Turn 1 output (text)
    landscape: str                        # Turn 2 output (text)
    proposals_text: str                   # Turn 3 output (text for markdown rendering)
    proposals_structured: list[ReviewProposal]  # Turn 3 output (structured, for Stage 4)
    s2_grounding_available: bool          # Whether S2 data was available for Turn 2
    thinking_logs: list[str]              # One per turn


async def run_literature_review(
    paper_indices: list[int],
    run_dir: Path,
    config: AppConfig,
    llm: LLMClient,
) -> list[PaperReview]:
    """Run full Stage 3 pipeline for selected papers.

    For each paper:
    1. Load enriched data from run_dir/enriched_papers.json.
    2. Fetch full paper content (arXiv HTML or PDF).
    3. Fetch citation context from Semantic Scholar.
    4. Run Turns 1-2 as text output (multi-turn with thinking preserved).
    5. Run Turn 3 via tool use to produce structured proposals (ReviewProposal).
    6. Validate proposals have all required fields.
    7. Collect and format results.
    """
```

### Turn Prompts

#### System Prompt — `build_review_system_prompt(criteria)`

```python
def build_review_system_prompt(criteria: CriteriaConfig) -> str:
    return f"""You are a senior AI researcher conducting a detailed literature review to identify research opportunities for your lab.

## Lab Constraints
- Compute: up to {criteria.max_compute_gpus}× {criteria.gpu_model} GPUs
- Focus: {', '.join(criteria.focus_areas)}
- Goal: Identify concrete, feasible research projects that can be submitted to {', '.join(criteria.target_venues)}

## Quality Standards
- Cite specific papers, methods, and datasets — never give generic advice
- Every claim about the state of the field must reference a specific work or result
- Research proposals must include concrete technical approaches, not vague directions
- All feasibility assessments must be grounded in your lab's compute constraints

You are having a multi-turn conversation. Each turn builds on the previous. Think deeply before responding."""
```

#### Turn 1 — `build_review_read_prompt(paper_content, paper_metadata)`

```python
def build_review_read_prompt(paper_content: str, paper_metadata: EnrichedPaper) -> str:
    return f"""Read the following paper thoroughly and provide a deep analysis.

**Title:** {paper_metadata.title}
**arXiv ID:** {paper_metadata.arxiv_id}
**Authors:** {paper_metadata.authors_raw}

## Full Paper Content:
{paper_content}

## What to analyze:
1. **Core contribution**: What is genuinely new? Distinguish the novel parts from standard techniques.
2. **Methodology**: What is the technical approach? What are the key design choices and why?
3. **Key results**: What are the main empirical findings? How strong is the evidence?
4. **Limitations**: What are the acknowledged and unacknowledged weaknesses?
5. **Open questions**: What does this paper leave unanswered? Where is there tension with existing work?

Be specific and technical. Do not merely summarize the abstract — analyze the paper's actual methodology and results."""
```

#### Turn 2 — `build_review_landscape_prompt(citation_context)`

Before calling Turn 2, the pipeline fetches real citation data from the Semantic Scholar API (see [02 — Enrichment](02_enrichment_and_database.md#semantic-scholar-citation-fetching-stage-3-turn-2-grounding)). This grounded context is included in the prompt to prevent hallucinated citations.

**S2 failure handling**: If S2 returns empty results (API down, paper not indexed), the pipeline:
1. Sets `s2_grounding_available = False` on the `PaperReview`
2. Logs a CLI warning (see `review` command in 05_cli)
3. Embeds a caveat in the Turn 2 prompt ("citations below are from model knowledge and should be independently verified")
4. Embeds a markdown warning banner in the rendered output

```python
def build_review_landscape_prompt(citation_context: dict) -> str:
    """Build Turn 2 prompt with grounded citation data.

    Args:
        citation_context: Dict from fetch_citation_context() with
            "references" and "citations" lists.
    """
    # Format real citation data as context
    refs_text = ""
    for ref in citation_context.get("references", []):
        authors = ", ".join(ref["authors"][:3])
        refs_text += f"- {authors} ({ref.get('year', '?')}). \"{ref['title']}\". {ref.get('venue', '')}.\n"
        if ref.get("abstract"):
            refs_text += f"  Abstract: {ref['abstract']}\n"

    cites_text = ""
    for cite in citation_context.get("citations", []):
        authors = ", ".join(cite["authors"][:3])
        cites_text += f"- {authors} ({cite.get('year', '?')}). \"{cite['title']}\". {cite.get('venue', '')}.\n"
        if cite.get("abstract"):
            cites_text += f"  Abstract: {cite['abstract']}\n"

    return f"""Based on your deep reading of this paper, map the research landscape around it.

## Grounded Citation Data

The following are REAL papers from Semantic Scholar. Use these as anchors for your analysis. You may supplement with your own knowledge where the data is incomplete, but clearly distinguish between grounded citations and your own additions.

### Papers this work cites (references):
{refs_text or "No reference data available."}

### Papers that cite this work:
{cites_text or "No citation data available (paper may be very recent)."}

## What to cover:
1. **What has been done**: Using the references above and your knowledge, list the key prior works this paper builds on or competes with. For each, note what they achieved and what gap remained.
2. **Active frontiers**: What are the 3–5 most active research questions in this area right now? Who are the key groups working on them?
3. **Gaps and opportunities**: Where does the current body of work fall short? What assumptions remain untested? What combinations of techniques haven't been tried?

IMPORTANT: Cite specific papers, methods, and research groups. Use the grounded citations above as your primary source. For example:
- "Dao et al. (2022) introduced FlashAttention, which solved X but left Y open"
- "The Mamba line of work (Gu & Dao, 2023; 2024) addresses Z but assumes..."

Do NOT give generic descriptions like "there has been growing interest in..." — be concrete about who did what."""
```

#### Turn 3 — `build_review_proposals_prompt(criteria)` (Tool Use)

Turn 3 uses **tool use** to produce structured proposals. This guarantees each proposal has all required fields (FR-5.3) and enables reliable extraction by Stage 4 without markdown parsing.

```python
# Tool schema for Turn 3
PROPOSAL_TOOL_SCHEMA = {
    "name": "submit_proposals",
    "description": "Submit structured research proposals",
    "input_schema": {
        "type": "object",
        "properties": {
            "proposals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "problem_statement": {"type": "string", "description": "1-2 sentence gap/question"},
                        "approach": {"type": "string", "description": "Detailed technical method"},
                        "target_task": {"type": "string", "description": "Primary benchmark/task"},
                        "compute_requirements": {"type": "string", "description": "GPU count x time estimate"},
                        "datasets": {"type": "array", "items": {"type": "string"}},
                        "feasibility_assessment": {"type": "string", "description": "Can this be done with lab constraints? Show calculation"},
                        "risks": {"type": "string", "description": "Main technical risks and mitigations"},
                        "expected_impact": {"type": "string", "description": "What would success look like quantitatively?"},
                        "target_venue": {"type": "string", "description": "Best venue and why"},
                    },
                    "required": ["index", "problem_statement", "approach", "target_task",
                                 "compute_requirements", "datasets", "feasibility_assessment",
                                 "risks", "expected_impact", "target_venue"],
                },
                "minItems": 2,
                "maxItems": 3,
            },
        },
        "required": ["proposals"],
    },
}


def build_review_proposals_prompt(criteria: CriteriaConfig) -> str:
    return f"""Based on your paper analysis and landscape mapping, propose 2–3 concrete research projects.

## Constraints
- Maximum compute: {criteria.max_compute_gpus}x {criteria.gpu_model}
- Must be feasible to complete and submit within 3-4 months
- Target venues: {', '.join(criteria.target_venues)}

## For each proposal, provide all of the following:
1. **Problem Statement**: What specific gap or question does this address? (1-2 sentences)
2. **Approach**: Technical method in detail (not "use technique X" but "modify X by adding Y to handle Z"). Include key insight/hypothesis and baselines to compare against.
3. **Target Task**: The primary benchmark or task to evaluate on.
4. **Compute Requirements**: Specific GPU count x training time estimate.
5. **Datasets**: Specific dataset names needed.
6. **Feasibility Assessment**: Can this be done with {criteria.max_compute_gpus}x {criteria.gpu_model}? Show the calculation. What are the main technical risks and mitigations?
7. **Risks**: Main technical risks with mitigation plans.
8. **Expected Impact**: What would a successful result look like quantitatively?
9. **Target Venue**: Which venue(s) is this best suited for and why?

Be honest about risks. A proposal with known risks and mitigations is more useful than one that glosses over difficulties.

Submit your proposals using the provided tool."""
```

**Note**: Turn 3 uses `call_with_tool()` (same as Stage 2 Phase A) instead of `multi_turn()`. The conversation context from Turns 1-2 is still passed in `messages`, but the output goes through the tool schema for guaranteed structure. The text content of the tool response is also used for the markdown rendering.

#### Translation — `build_review_translation_prompt(english_review)`

```python
def build_review_translation_prompt(english_review: str) -> str:
    """Build prompt to translate the English literature review to Traditional Chinese.

    Uses Sonnet (model_translate) with no extended thinking.
    """
    return f"""Translate the following research literature review from English to Traditional Chinese (繁體中文).

## Translation Guidelines:
- Preserve all technical terms, paper titles, author names, and venue names in English
- Translate section headers, analysis text, and descriptions to natural Traditional Chinese
- Keep mathematical notation, code snippets, and model names unchanged
- Maintain the exact markdown formatting structure

## English Review:
{english_review}"""
```

---

## Few-Shot Examples — `src/analysis/examples/`

### Purpose

Few-shot examples calibrate the model's output depth and style. Without them, the model may produce shallower analysis than the cowork reference output.

### Files

| File | Content | Used By |
|------|---------|---------|
| `example_filter_output.json` | Expected analysis JSON for sample papers (output only) | Stage 2 |
| `example_review_turn1.md` | Sample Turn 1 deep read output | Stage 3 Turn 1 |
| `example_review_turn2.md` | Sample Turn 2 landscape output | Stage 3 Turn 2 |
| `example_review_turn3.md` | Sample Turn 3 proposals output | Stage 3 Turn 3 |

**Note**: We include only **output** examples (not input). The model doesn't need to see the example input papers — it needs to see the **quality bar** of the output. This saves ~2,000 tokens of context that can be used for thinking.

### Sourcing

These examples are extracted from the reference cowork sessions at `/Users/jerry/Documents/cowork/alphaxiv/20260318/`. During development, take the best 2–3 paper analyses from `filtered.md` and format them as the expected JSON output.

### Integration

Few-shot examples are placed in the **user message** (not system prompt) so the system prompt can be cached independently via prompt caching. For Stage 3, each turn includes only its own example (not all 3 turns in the system prompt).

```python
def _load_examples(stage: str, turn: int | None = None) -> str:
    """Load few-shot examples for a given stage.

    Args:
        stage: "filter" or "review".
        turn: For "review" stage, which turn (1, 2, or 3). Each turn
              gets only its own example to minimize context usage.
    """
    examples_dir = Path(__file__).parent / "examples"
    if stage == "filter":
        example_out = (examples_dir / "example_filter_output.json").read_text()
        return f"""
## Reference Quality Bar

Here is an example of the expected output depth and specificity:
{example_out}

Match this depth in your analysis."""

    if stage == "review" and turn:
        example_file = f"example_review_turn{turn}.md"
        example = (examples_dir / example_file).read_text()
        return f"""
## Reference Quality Bar

Here is an example of the expected output for this turn:
{example}

Match this depth and specificity."""
```

---

## Output Rendering — `src/output/formatter.py`

### Public Interface

```python
def render_review_markdown(
    reviews: list[PaperReview],
    run_date: str,
    lang: str,
) -> str:
    """Render literature reviews into a single markdown document.

    Args:
        reviews: List of completed paper reviews.
        run_date: YYYY-MM-DD.
        lang: "zh" or "en".

    Format:
        # Literature Review — AlphaXiv YYYY/MM/DD

        ## Paper 1: {Title}
        ### Summary
        {Turn 1 output}
        ### Research Landscape
        {Turn 2 output}
        ### Research Proposals
        {Turn 3 output}

        ---

        ## Paper 2: ...
    """
```

The rendered markdown for Stage 2 comes from deterministic Python code (`render_analysis_markdown()`). The formatter for Stage 3 is similar — it concatenates the multi-turn outputs with section headers.
