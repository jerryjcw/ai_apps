# 03 — LLM Integration & Extended Thinking

## Overview

This document covers the Anthropic SDK wrapper, extended thinking configuration, and how each LLM-powered stage uses the client. The goal is to produce output matching the depth and quality of interactive cowork sessions with Claude.

---

## Module: `src/analysis/llm_client.py`

### Client Design

```python
import anthropic
import json
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class LLMResponse:
    """Structured response from an LLM call."""
    content: str                    # the text response
    thinking: str | None = None     # extended thinking content (if enabled)
    raw_content_blocks: list = None # full API response content blocks (for multi-turn)
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0


class LLMClient:
    """Wrapper around anthropic SDK with extended thinking support."""

    def __init__(self, config: LLMConfig, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._config = config

    def call(
        self,
        messages: list[dict],
        system: str = "",
        thinking_budget: int | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Single-turn or continuation LLM call with extended thinking.

        Args:
            messages: Conversation messages in Anthropic format.
            system: System prompt.
            thinking_budget: Override thinking budget. None = use default for stage.
            max_tokens: Override max output tokens.
            model: Override model. None = use config default.

        Returns:
            LLMResponse with content, thinking, and token usage.
        """
        params = {
            "model": model or self._config.model_analyze,
            "max_tokens": max_tokens or self._config.max_tokens,
            "messages": messages,
        }
        if system:
            # Enable prompt caching on system prompt
            params["system"] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}},
            ]

        # Extended thinking
        if thinking_budget and thinking_budget > 0:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }
            # temperature must be 1.0 when thinking is enabled
            params["temperature"] = 1.0

        response = self._client.messages.create(**params)

        # Extract content and thinking from response blocks
        content_text = ""
        thinking_text = ""
        for block in response.content:
            if block.type == "thinking":
                thinking_text += block.thinking
            elif block.type == "text":
                content_text += block.text

        return LLMResponse(
            content=content_text,
            thinking=thinking_text or None,
            # Preserve the raw response content blocks for multi-turn context
            raw_content_blocks=response.content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            thinking_tokens=getattr(response.usage, "thinking_tokens", 0),
        )

    def multi_turn(
        self,
        system: str,
        turns: list[str],
        thinking_budget: int | None = None,
        model: str | None = None,
    ) -> list[LLMResponse]:
        """Multi-turn conversation with context accumulation.

        Used by Stage 3 (literature review) where each turn builds on previous.

        IMPORTANT: When extended thinking is enabled, the Anthropic API requires
        that the full response content blocks (including thinking blocks) are
        preserved in the conversation history. Stripping thinking blocks causes
        the model to "forget" its deep reasoning from previous turns.

        Args:
            system: System prompt (constant across turns).
            turns: List of user messages, sent sequentially.
            thinking_budget: Thinking budget for each turn.
            model: Override model for all turns.

        Returns:
            List of LLMResponse, one per turn. Each response includes
            the model's thinking and content for that turn.
        """
        messages = []
        responses = []

        for user_msg in turns:
            messages.append({"role": "user", "content": user_msg})

            resp = self.call(
                messages=messages,
                system=system,
                thinking_budget=thinking_budget,
                model=model,
            )
            responses.append(resp)

            # CRITICAL: Preserve full response content blocks (including thinking)
            # in the conversation history. This is required by the Anthropic API
            # for multi-turn extended thinking conversations.
            messages.append({"role": "assistant", "content": resp.raw_content_blocks})

        return responses
```

### Thinking Log Writer

```python
def save_thinking_log(
    thinking_text: str,
    stage: str,
    run_dir: Path,
    label: str = "",
):
    """Save extended thinking output for debugging and quality review.

    Args:
        thinking_text: Raw thinking content from the model.
        stage: e.g. "stage2_analysis", "stage3_paper_1_turn_2".
        run_dir: The run's output directory.
        label: Optional additional label.
    """
    logs_dir = run_dir / THINKING_LOGS_DIR
    logs_dir.mkdir(exist_ok=True)
    filename = f"{stage}{'_' + label if label else ''}.txt"
    (logs_dir / filename).write_text(thinking_text, encoding="utf-8")
```

---

## Extended Thinking: Why and How

### Why Extended Thinking Is Critical

In a cowork session, the human iterates with Claude — asking follow-up questions, pushing for specificity, challenging shallow assessments. Without that iteration, a single-shot API call tends to produce:
- Surface-level paper summaries instead of deep analysis
- Generic research directions ("explore more data augmentation")
- Ratings that cluster at 3–4 stars without differentiation
- Conference probability estimates that are all "moderate-high"

Extended thinking compensates by giving the model internal reasoning space equivalent to the multi-turn iteration. The model can:
- Read all papers before committing to relative ratings
- Reason about compute feasibility against specific GPU constraints
- Consider the competitive landscape of each research direction
- Self-correct shallow initial assessments

### Budget Allocation Per Stage

| Stage | Model | Budget | Rationale |
|-------|-------|--------|-----------|
| Parse fallback | Sonnet | 5,000 tokens | Structural reasoning only — figure out the text format |
| Stage 2 analysis | **Opus** | **40,000 tokens** | Must compare ~60 papers relatively (~660 tokens reasoning per paper), do comparative ranking, feasibility calculations, and self-correction |
| Stage 3 review | **Opus** | 16,000 tokens **per turn** (3 turns × 16K = 48K per paper) | Deepest analysis — synthesize knowledge about an entire research area |
| Stage 3 translation | Sonnet | N/A (no thinking) | Simple translation of English output to Chinese |

### Quality Indicators

To verify extended thinking is producing quality output, check the thinking logs for:
- **Comparative reasoning**: "Paper A is more novel than Paper B because..."
- **Specific citations**: "This relates to [Author et al., 2025] which showed..."
- **Self-correction**: "Initially I rated this 4 stars, but comparing with..."
- **Constraint checking**: "16×H200 for 2 weeks gives us... which is enough for..."

If thinking logs show mostly restating the prompt or paper abstracts, the thinking budget may need to be increased.

---

## Structured JSON Output via Tool Use

For Stage 2 Phase A (analysis), the model must return structured JSON. Instead of prompt-based JSON extraction (which requires manual parsing and can fail), use Anthropic's **tool use** feature to get guaranteed-valid JSON:

```python
def call_with_tool(
    self,
    messages: list[dict],
    system: str,
    thinking_budget: int,
    tool_schema: dict,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict:
    """Call with tool use for guaranteed structured JSON output.

    Args:
        messages: Conversation messages.
        system: System prompt.
        thinking_budget: Extended thinking budget.
        tool_schema: JSON schema for the tool's input_schema.
        model: Model override.
        max_tokens: Max output tokens override.

    Returns:
        Parsed dict matching the tool schema.

    The tool is defined with the analysis output schema. The model
    is forced to use it via tool_choice={"type": "tool", "name": "..."}.
    This eliminates JSON parsing failures entirely.
    """
    tool_def = {
        "name": "submit_analysis",
        "description": "Submit the paper analysis results",
        "input_schema": tool_schema,
    }
    params = {
        "model": model or self._config.model_analyze,
        "max_tokens": max_tokens or self._config.max_tokens_analyze,
        "messages": messages,
        "tools": [tool_def],
        "tool_choice": {"type": "tool", "name": "submit_analysis"},
    }
    if system:
        params["system"] = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}},
        ]
    if thinking_budget > 0:
        params["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
        params["temperature"] = 1.0

    response = self._client.messages.create(**params)

    # Extract tool use result
    for block in response.content:
        if block.type == "tool_use":
            return block.input  # already parsed dict

    raise LLMError("Model did not return tool use result")
```

---

## Output Validation — `src/analysis/validator.py`

After Phase A returns structured JSON, validate the output before proceeding to rendering. Critical failures trigger an automatic retry with increased thinking budget.

```python
def validate_analysis_result(
    result: dict,
    input_papers: list,
    max_retries: int = 1,
) -> list[str]:
    """Validate LLM analysis output for completeness and quality.

    Args:
        result: Parsed JSON from Phase A (included_papers + excluded_papers + top5_summary).
        input_papers: Original enriched papers list (to check all are accounted for).
        max_retries: Max retry attempts on critical failure.

    Returns:
        List of warning strings. Empty list = all checks passed.

    Critical warnings (trigger auto-retry):
        - Missing papers (not in included or excluded)
        - Top 5 summary incomplete

    Quality warnings (logged but no retry):
        - Rating range too narrow (all clustered at 3-4)
        - Vague exclusion reasons (< 20 chars or generic)
    """
    warnings = []

    # Check all papers accounted for
    all_indices = {p.index for p in input_papers}
    included_indices = {p["index"] for p in result.get("included_papers", [])}
    excluded_indices = {p["index"] for p in result.get("excluded_papers", [])}
    result_indices = included_indices | excluded_indices
    if missing := all_indices - result_indices:
        warnings.append(f"CRITICAL: Papers {missing} not in output — re-run required")

    # Check for duplicates between included and excluded
    duplicates = included_indices & excluded_indices
    if duplicates:
        warnings.append(f"WARNING: Papers {duplicates} appear in both included and excluded")

    # Check rating distribution
    ratings = [p["importance"] for p in result.get("included_papers", [])]
    if ratings and max(ratings) - min(ratings) < 2:
        warnings.append(
            f"QUALITY: Rating range too narrow: {min(ratings)}-{max(ratings)}. "
            f"Expected 1-5 spread."
        )

    # Check exclusion reason specificity
    for p in result.get("excluded_papers", []):
        reason = p.get("reason", "")
        if len(reason) < 20 or reason.lower() in ["not relevant", "irrelevant", "not related"]:
            warnings.append(
                f"QUALITY: Paper {p['index']} has vague exclusion reason: '{reason}'"
            )

    # Check Top 5 exists and is complete
    top5 = result.get("top5_summary", [])
    if len(top5) < 5 and len(result.get("included_papers", [])) >= 5:
        warnings.append("CRITICAL: Top 5 summary incomplete")

    return warnings


def has_critical_warnings(warnings: list[str]) -> bool:
    """Check if any warnings are critical (require retry)."""
    return any(w.startswith("CRITICAL:") for w in warnings)
```

### Auto-Retry Strategy

When critical validation failures occur:
1. Log the specific failure and thinking content for debugging
2. Increase thinking budget by 50% (e.g., 40K → 60K)
3. Re-run Phase A with the same prompt
4. If retry also fails, save the best result with warnings and continue

This ensures silent quality failures (like truncated output) are caught and corrected.

---

## Stage 3 Proposal Validation — `src/analysis/validator.py` (extended)

```python
def validate_review_proposals(proposals: list) -> list[str]:
    """Validate Stage 3 Turn 3 proposals have all required fields per FR-5.3.

    Args:
        proposals: List of ReviewProposal objects from Turn 3 tool use.

    Returns:
        List of warning strings. Empty = all checks passed.
    """
    warnings = []
    required_fields = [
        "problem_statement", "approach", "target_task",
        "compute_requirements", "target_venue",
    ]
    for p in proposals:
        idx = getattr(p, "index", "?")
        for field in required_fields:
            val = getattr(p, field, None) or ""
            if len(val.strip()) < 10:
                warnings.append(f"QUALITY: Proposal {idx} has empty/vague '{field}'")

        # Check compute_requirements mentions specific GPU config
        compute = getattr(p, "compute_requirements", "") or ""
        if not any(kw in compute.lower() for kw in ["gpu", "h200", "h100", "a100", "tpu"]):
            warnings.append(f"QUALITY: Proposal {idx} compute_requirements lacks GPU specifics")

    return warnings
```

## Stage 4 Plan Validation — `src/planning/validator.py`

```python
def validate_experiment_plan(plan, run_paper_count: int = 0) -> list[str]:
    """Validate Stage 4 experiment plan meets quality requirements.

    Args:
        plan: ExperimentPlan dataclass.
        run_paper_count: Number of papers in the current pipeline run
                         (for cross-pollination validation).

    Returns:
        List of warning strings.
    """
    warnings = []

    # QR-1.12: MVE should mention GPU-hours and target < 48
    mve = plan.mve or ""
    if "gpu" not in mve.lower() and "hour" not in mve.lower():
        warnings.append("QUALITY: MVE does not include GPU-hour estimate (QR-1.12)")

    # QR-1.15: Novel synthesis must reference 2+ papers from the run
    synthesis = plan.novel_approaches or ""
    # Count distinct "Paper #N" references
    import re
    paper_refs = set(re.findall(r"Paper\s*#?\s*(\d+)", synthesis, re.IGNORECASE))
    if len(paper_refs) < 2 and run_paper_count > 1:
        warnings.append(
            f"QUALITY: Novel synthesis references {len(paper_refs)} run papers, "
            f"expected 2+ for cross-pollination (QR-1.15)"
        )

    # QR-1.11: Novelty assessment should contain a side-by-side comparison
    novelty = plan.novelty_assessment or ""
    if "closest existing work" not in novelty.lower() and "novelty delta" not in novelty.lower():
        warnings.append("QUALITY: Novelty assessment may lack specific side-by-side comparison (QR-1.11)")

    # Check all major sections are non-empty
    sections = {
        "novelty_assessment": "Novelty Assessment",
        "mve": "Minimum Viable Experiment",
        "full_plan": "Full Experiment Plan",
        "ablation_design": "Ablation Design",
        "baseline_selection": "Baseline Selection",
        "risk_register": "Risk Register",
    }
    for field, label in sections.items():
        val = getattr(plan, field, None) or ""
        if len(val.strip()) < 50:
            warnings.append(f"CRITICAL: {label} section is empty or too short")

    return warnings
```

---

### Expected JSON Schema for Stage 2

```json
{
    "included_papers": [
        {
            "index": 1,
            "title": "...",
            "arxiv_id": "2603.15031",
            "topic_category": "LLM Architecture — Residual Connection Improvement",
            "core_contribution": "...",
            "importance": 4,
            "importance_justification": "...",
            "research_directions": [
                {"label": "a", "direction": "...", "feasibility": "..."},
                {"label": "b", "direction": "...", "feasibility": "..."},
                {"label": "c", "direction": "...", "feasibility": "..."},
                {"label": "d", "direction": "...", "feasibility": "..."}
            ],
            "compute_estimate": "8–16×H200, ~48h per scaling law experiment",
            "data_estimate": "100B–500B tokens (public pretraining corpora)",
            "datasets": ["SlimPajama", "FineWeb", "C4", "MMLU", "HellaSwag"],
            "conference_probability_pct": 75,
            "conference_probability_reasoning": "..."
        }
    ],
    "excluded_papers": [
        {
            "index": 3,
            "title": "Mamba-3",
            "reason": "Already published at ICLR 2026; SSM architecture is mature with limited incremental space",
            "cross_ref": null
        },
        {
            "index": 31,
            "title": "Reasoning Strategic Info Allocation",
            "reason": "Duplicate — same content as included paper #9",
            "cross_ref": 9
        }
    ],
    "top5_summary": [
        {
            "rank": 1,
            "title": "...",
            "conference_probability": "75–85%",
            "compute": "low–medium",
            "rationale": "..."
        }
    ]
}
```
