# Example Outputs Reference

This file shows snippets of actual outputs from a successful pipeline run
on 2026-03-23, so you can match the format and quality level.

---

## Step 1 Example: raw_popular_papers entry

```
=== PAPER 12 ===
Title: Neural Thickets: Diverse Task Experts Are Dense Around Pretrained Weights
ArXiv: 2603.12228
Date: 12 Mar 2026
Tags: #computer-science #artificial-intelligence
Abstract: This paper finds that after pretraining, the story changes. With a reasonable number of random guesses, one can sample parameter perturbations that substantially improve pretrained large language models (LLMs) across a broad set of tasks...
```

## Step 1 Example: titles entry

```markdown
## 12. Neural Thickets: Diverse Task Experts Are Dense Around Pretrained Weights

**ArXiv:** 2603.12228
**Date:** 12 Mar 2026
**Tags:** #computer-science #artificial-intelligence

**Abstract:** This paper finds that after pretraining...
```

---

## Step 2 Example: filtered paper entry

```markdown
### 4. Transformers are Bayesian Networks

**Paper #12 — ArXiv [2603.17063](https://arxiv.org/abs/2603.17063) — Greg Coppola (coppola.ai) — 17 Mar 2026**

Establishes that sigmoid Transformers are Bayesian networks via five formal claims...

| Field | Details |
|---|---|
| **Topic Category** | LLM Theory / Probabilistic Inference |
| **Importance** | ★★★★★ — Potentially groundbreaking theoretical unification. Formally verified proofs. |
| **Possible Directions** | (a) Extend to softmax Transformers; (b) Leverage Bayesian interpretation for uncertainty quantification; (c) Design new architectures guided by BN theory; (d) Applications to calibration and hallucination reduction; (e) Study implications for interpretability |
| **Compute Estimate** | 8–12× H200 (mostly theoretical + moderate-scale validation) |
| **Data Estimate** | Moderate — synthetic BN samples + standard pretraining corpora |
| **Datasets** | Synthetic BN inference tasks, SlimPajama, TruthfulQA, MMLU |
| **Top-Venue Probability** | **88%** — Novel theoretical unification with formal verification |
```

## Step 2 Example: exclusion entry

```markdown
| 1 | Schrödinger Bridges for Generative Modeling | Not LLM/agent — generative model theory (diffusion/flow) |
| 2 | Memento-Skills | Pure engineering — skill memory system without theoretical contribution |
| 5 | FASTER | VLA/robotics — not core LLM |
```

---

## Step 3 Example: proposal structure

A good proposal has all of these:
- **Paper Summary:** 3-5 sentences
- **Related Work Landscape:** 6-10 entries with "What's Left Open" column
- **Key Gaps:** explicit numbered list
- **Each proposal (A-E):** Why, Rationale & Feasibility (HIGH/MED/LOW),
  3-phase implementation, experiment table with GPU counts, cost estimate,
  venue probability with target venues
- **Comparative Assessment:** side-by-side table of all 5 proposals
- **Top Recommendation:** single pick with justification

---

## Step 4 Example: essence quality markers

A good essence has:
- **Intuition section** that goes beyond the abstract — explains the
  *mechanism* (e.g., "sigmoid's log-odds addition is exactly how belief
  propagation combines evidence")
- **Previous Work table** with 5-8 entries, each with specific author/year
  and a "How This Paper Differs" column
- **Method walkthrough** with 5+ subsections, formulas in code blocks,
  algorithm descriptions detailed enough to reimplement
- **Experiments** with actual numbers in comparison tables, not just
  "outperforms baselines"
- **Researcher notes** with open questions, community reception, and
  honest caveats about limitations

Bad signs to avoid:
- Restating the abstract as the "intuition"
- Citing papers that don't exist (hallucinated references)
- Claiming specific numbers without having extracted them from the paper
- Writing "the paper shows X improves Y" without the actual number
