---
name: research-ideate
description: Generate and refine research ideas, hypotheses, and experiment plans for an AI/ML topic. Use when the user wants research ideation, proposal generation, experiment design, reviewer-style filtering, or a structured path from topic to top-conference-quality plans.
---

# Research Ideation

Use this skill to run a staged ideation pipeline from topic to final plans.

## Ask For Parameters Up Front

Collect in one message unless already known:

1. Research topic
2. Reference papers or anchors
3. Compute constraints
4. Focus areas
5. Target venues

## Default Pipeline

### Stage 0: Initialize workspace

Create a dated output directory and a simple state file if the user wants persistent artifacts.

Suggested layout:

```text
/Users/jerry/projects/ai_apps/output/research_ideate/<topic_slug>/<YYYYMMDD>/
```

### Stage 1: Literature collection

Build a compact research landscape:

- closest papers
- what each actually solved
- what remains open
- crowded directions to avoid

### Stage 2: Idea generation

Generate 8 to 10 candidate ideas first. Do not jump to final plans too early.

Each candidate should have:

- title
- thesis
- novelty claim
- closest prior work
- likely failure mode

### Stage 3: Hypothesis and method development

For each surviving idea, write:

- thesis
- theoretical basis
- method sketch
- variants
- closest prior work table
- circularity or novelty check

### Stage 4: Harsh filtering

Apply a reviewer-style screen:

- novelty
- technical depth
- experimental clarity
- execution risk
- reviewer attack surface

Drop weak ideas early.

### Stage 5: Experiment planning

For the final ideas, write:

- MVE
- full experiment plan
- baselines
- ablations
- datasets and metrics
- compute estimate
- success criteria
- risk register

## Codex-Specific Adaptation

The source Claude workflow was explicitly multi-agent. In Codex:

- If the user explicitly asks for delegation or parallel sub-agents, you may use `spawn_agent` to mirror the student/advisor/professor pattern.
- If the user does not ask for delegation, run the same stages in a single thread and emulate the roles as separate review passes in your own output.
- Keep state on disk only when the user wants persistent outputs.

## Recommended Role Mapping

When doing multi-pass analysis, use these perspectives:

- Student: generate candidate ideas aggressively
- Advisor: harsh filter for novelty and feasibility
- Visiting Professor: external review, attack vectors, and strategic positioning

Use the bundled prompts only as references, not as mandatory verbatim templates.

## References

- [references/ri-student.md](references/ri-student.md)
- [references/ri-advisor.md](references/ri-advisor.md)
- [references/ri-visiting-prof.md](references/ri-visiting-prof.md)
