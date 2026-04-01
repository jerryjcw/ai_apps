# Research Ideation Pipeline — Flow Diagram

```
┌─────────────────────┐
│   User Input        │
│   topic, papers,    │
│   compute, venues   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────────────┐
│  Step 0: Initialize         │
│  state.json + workspace dirs│
└─────────────┬───────────────┘
              │
              ▼
┌──────────────────────────┐
│ Step 1a: Breadth         │
│ Literature Search        │
│ (Student, Sonnet)        │
│                          │
│ WebSearch 15-25 papers   │
│                          │
│ WRITE: literature/       │
│ landscape_round{N}       │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ Step 1b: Citation        │
│ Chain Depth Pass         │
│ (Student, Sonnet)        │
│                          │
│ READ: landscape          │
│ WebFetch top-5 papers'   │
│ references               │
│ Find 5-10 missed papers  │
│ (diff terms)             │
│                          │
│ APPEND: landscape        │
│ (Depth Pass section)     │
└────────┬─────────────────┘
         │
         │  gate: ≥15 papers,
         │  ≥3 diff terminology
         ▼
┌──────────────────────────┐
│ Step 2: Idea Gen         │  ◄── PIVOT from 8f (all ideas dead, budget remains)
│ (Student, Sonnet)        │  ◄── Diversity Gap from 3b (retry ≤5x total)
│                          │
│ READ: landscape          │
│ WebSearch to verify      │
│ Generate 10+ ideas       │
│                          │
│ WRITE: ideas/            │
│ candidates_round{N}      │
└────────┬─────────────────┘
         │
         │  gate: ≥10 ideas,
         │  ≤3 per sub-topic (retry ≤5x)
         ▼
┌──────────────────────────────────┐
│ Step 3a: Hypothesis Dev          │
│ (Student, Sonnet, per idea)      │
│                                  │
│ READ: ideas, landscape           │
│ Thesis + theory + method +       │
│ variants + prior work +          │
│ circularity check                │
│                                  │
│ WRITE: hypotheses/               │
│ hypothesis_{slug}_round{N}       │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│ Step 3b: Advisor Hypothesis Gate │
│ (Advisor, Opus, per idea)        │
│                                  │
│ READ: hypothesis files           │
│ 9-dimension filter               │
│ Diversity audit (≤3/subtopic)    │
│ Triviality gate                  │
│                                  │
│ WRITE: reviews/advisor_{slug}_   │
│        round{N} (via save_review)│
│ UPDATE: review_tracker.json      │
│                                  │
│ Verdicts: DEVELOP / REFINE / DROP│
└────────┬─────────────────────────┘
         │
         ├── DEVELOP ───────────────────┐
         │                              │
         └── REFINE ──┐                 │
                      ▼                 │
      ┌──────────────────────────┐      │
      │ Step 3c: REFINE Loop     │      │
      │ (max 3 sub-iters)        │      │
      │                          │      │
      │ Student revises          │      │
      │ hypothesis               │      │
      │ WRITE: hypothesis_       │      │
      │ {slug}_round{N}_revised  │      │
      │                          │      │
      │ Advisor re-reviews       │      │
      │ WRITE: advisor_{slug}    │      │
      │ _round{N}_cycle{C}       │      │
      │                          │      │
      │ STILL_OPEN? ──► loop ◄───┤      │
      │ max iters (3)? ──► DROP  │      │
      └────────┬─────────────────┘      │
               │ RESOLVED               │
               └──────────┬─────────────┘
                          │ (DEVELOP + RESOLVED merge)
                          │
                          │  gate: ≥3 in planning
                          ▼
┌──────────────────────────────────────────┐
│ Step 4: Experiment Planning              │
│ (Student, Sonnet, per idea)              │
│                                          │
│ READ: hypothesis (latest), landscape,    │
│       review_tracker, advisor review     │
│ WebSearch: baselines, datasets, SOTA     │
│                                          │
│ MVE + 3-phase plan + baselines +         │
│ ablations + metrics + risk register +    │
│ falsification plan + limitations         │
│                                          │
│ WRITE: plans/plan_{slug}_round{N}        │
└────────┬─────────────────────────────────┘
         │
         ▼
┌──────────────────────┐
│ Step 5: Submission   │
│ (automatic)          │
│                      │
│ Verify plans exist   │
│ Skip already-approved│
│ WRITE: submission_   │
│ round{N}.json        │
│ Status → in_review   │
└────────┬─────────────┘
         │
         ▼
┌───────────────────────────────────────────┐
│ Step 6: Advisor Review — Internal Quality │
│ (Advisor, Opus, ONE idea at a time)       │
│                                           │
│ READ: plan (latest), VP prior review,     │
│       review_tracker                      │
│ WebSearch/Fetch to VERIFY claims          │
│                                           │
│ Theory + depth + triviality gate +        │
│ experimental design + reproducibility     │
│                                           │
│ 1. WRITE review (save_review, write-first)│
│ 2. THEN parse issues                      │
│ 3. THEN update tracker                    │
│ 4. THEN log interaction                   │
│                                           │
│ Verdict: APPROVE / REFINE / PIVOT / DROP  │
└────────┬──────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────┐
│ Step 7: VP Review — External Validity     │
│ (VP, Opus, ONE idea at a time)            │
│                                           │
│ READ: plan (latest), Advisor review       │
│       (THIS round), review_tracker        │
│ WebSearch: scooping, recent baselines     │
│ WebFetch: verify competing papers         │
│                                           │
│ Scooping + significance (SO WHAT? +       │
│ TRIVIALITY + SURPRISE) + top-3 attacks    │
│ (Theorist/Empiricist/Area Chair) +        │
│ missing baselines + cross-domain          │
│                                           │
│ 1. WRITE review (save_review, write-first)│
│ 2. THEN parse issues                      │
│ 3. THEN update tracker                    │
│ 4. THEN log interaction                   │
│                                           │
│ Verdict: APPROVE / REFINE / DROP          │
└────────┬──────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────┐
│ Step 8: Decision (orchestrator logic)     │
│                                           │
│ 8a: Build/update review tracker           │
│ 8b: Apply decision matrix                 │
│     APPROVE+APPROVE → APPROVE             │
│     any REFINE → REFINE                   │
│     any DROP → DROP                       │
│     any PIVOT → PIVOT                     │
│     (blocked if open severe/major)        │
│                                           │
│ 8c: Route REFINE ideas                    │
│     theory/novelty → back to Stage 3      │
│     experiment only → back to Stage 4     │
└────────┬──────────────────────────────────┘
         │
         ├── APPROVE ──────────────────────────────┐
         │                                         │
         ├── DROP ──► remove from active           │
         │                                         │
         └── REFINE ──┐                            │
                      ▼                            │
         ┌─────────────────────────────────┐       │
         │ 8d: Student Revision            │       │
         │ (Student, Sonnet, per idea)     │       │
         │                                 │       │
         │ READ: plan (latest), tracker,   │       │
         │   FULL review files (verbatim), │       │
         │   landscape                     │       │
         │ WebSearch for new info          │       │
         │ validate_student_revision()     │       │
         │ (manipulation check)            │       │
         │                                 │       │
         │ WRITE: plan_{slug}_round{N}_    │       │
         │        revised.md               │       │
         │                                 │       │
         │ DO NOT update tracker           │       │
         │ (Student has no authority)      │       │
         └────────┬────────────────────────┘       │
                  │                                │
                  ▼                                │
         ┌─────────────────────────────────┐       │
         │ 8e: Re-review                   │       │
         │ (REVIEWER IS SOLE AUTHORITY)    │       │
         │                                 │       │
         │ Advisor + VP each re-review     │       │
         │ READ: revised plan, prior       │       │
         │   review, tracker               │       │
         │                                 │       │
         │ Per issue: RESOLVED / STILL_OPEN│       │
         │ Only reviewer can close issues  │       │
         │ resolve_review_issue(           │       │
         │   resolved_by="advisor"/"vp")   │       │
         │ log_review_event() for          │       │
         │   STILL_OPEN                    │       │
         │                                 │       │
         │ WRITE: review files with        │       │
         │   cycle suffix (_cycle2, etc)   │       │
         │   (write-first rule)            │       │
         └────────┬────────────────────────┘       │
                  │                                │
                  │ can_approve()? ──yes───────────┤
                  │ STILL_OPEN? ──► loop 8d→8e     │
                  │ max cycles (3)? ──► DROP       │
                  │                                │
                  ▼                                │
         ┌────────────────────────────────────┐    │
         │ 8f: All-proposals-dead check       │    │
         │                                    │    │
         │ Any active ideas left?             │    │
         │ NO + can_pivot → PIVOT ──► Step 2  │    │
         │ NO + no budget → INFEASIBLE (end)  │    │
         │ YES → continue                     │    │
         └────────┬───────────────────────────┘    │
                  │                                │
                  ▼                                │
         ┌───────────────────────────────────┐     │
         │ 8g: Check convergence             │     │
         │                                   │     │
         │ ≥3 ideas approved at STRICT       │     │
         │ quality? ──yes──► Stage 9 ────────┤     │
         │                                   │     │
         │ Max rounds reached?               │     │
         │ ──yes──► Stage 9 (best effort) ───┤     │
         │                                   │     │
         │ Otherwise: start_new_round()      │     │
         │   • round N++                     │     │
         │   • quality: lenient→mod→strict   │     │
         │   • demote provisional approvals  │     │
         │     (approved at <strict)         │     │
         │     → status becomes "in_review"  │     │
         │                                   │     │
         │ Route back:                       │     │
         │   refine ideas exist? → Stage 3   │     │
         │   only provisionals?  → Stage 6   │     │
         └───────────────────────────────────┘     │
                                                   │
                  ┌────────────────────────────────┘
                  │
                  ▼
┌───────────────────────────────────────────────────┐
│ Step 9: Final Output                              │
│                                                   │
│ 9a: Ranking + Portfolio Coherence Analysis        │
│     (Advisor, Opus)                               │
│     READ: all approved plans (latest per slug)    │
│     Ranking + synergies + merge candidates +      │
│     execution order + coherent narrative +        │
│     redundancy check                              │
│     WRITE: portfolio_analysis.md                  │
│                                                   │
│ 9b: Render Self-Contained Final Plans             │
│     (Student, Sonnet, per idea)                   │
│     READ: hypothesis, plan, ALL reviews,          │
│           tracker, landscape (all from files)     │
│     14-section template + Appendix A/B            │
│     Including: Limitations + Falsification Plan   │
│     WRITE: plan_{rank}_{slug}.md                  │
│     VERIFY: no file references in output          │
│                                                   │
│ 9c: Summary table                                 │
│     WRITE: summary.md                             │
│                                                   │
│ 9d: Pipeline summary                              │
│     WRITE: interaction_log/pipeline_summary.md    │
│                                                   │
│ 9e: Brief versions (繁體中文)                      │
│     (Student, Sonnet, per idea)                   │
│     4 sections: 直覺/研究構想/核心演算法/主要實驗對照   │
│     WRITE: plan_{rank}_{slug}_brief.md            │
│                                                   │
│ 9f: Report to user                                │
└───────────────────────────────────────────────────┘
```

## Key Invariants (apply at every step)

```
┌──────────────────────────────────────────────────────────────┐
│ FILE-BASED TRUTH                                             │
│                                                              │
│  READ from files ──► not from conversation context           │
│  WRITE before proceeding ──► write-first rule                │
│  Per-idea, per-round files ──► no merging ideas into one     │
│  Tracker is DERIVED from review files ──► files win          │
│  Glob for reading ──► don't hardcode round N                 │
│  Current round N for writing ──► from state.json             │
│  Cycle suffix for same-round re-reviews ──► _cycle2, etc     │
├──────────────────────────────────────────────────────────────┤
│ REVIEWER AUTHORITY                                           │
│                                                              │
│  Only Advisor/VP can resolve issues                          │
│  resolved_by="advisor"/"vp" required                         │
│  Student cannot self-declare issues fixed                    │
│  Orchestrator is scribe, not judge                           │
│  Severe/major cannot be wontfix                              │
│  Every resolution has history trail                          │
├──────────────────────────────────────────────────────────────┤
│ STUDENT CONSTRAINTS                                          │
│                                                              │
│  Cannot address/persuade/argue with reviewers                │
│  validate_student_revision() on every revision               │
│  2 consecutive manipulation failures → DROP                  │
│  Has WebSearch/WebFetch for research (not for lobbying)      │
├──────────────────────────────────────────────────────────────┤
│ REVIEW QUALITY                                               │
│                                                              │
│  save_review() validates: >500 bytes + required sections     │
│  Full review file = authoritative record                     │
│  Student reads VERBATIM review text(not orchestrator summary)│
│  Review format: Assessment + Per-Section + Issues + Verdict  │
│  Issues: full paragraph + fix direction + citations          │
└──────────────────────────────────────────────────────────────┘
```

## File Map

```
output/research_ideate/<topic>/<date>/
├── plan_1_{slug}.md                    ← final self-contained proposal (9b)
├── plan_1_{slug}_brief.md              ← 繁體中文 brief (9e)
├── plan_2_{slug}.md
├── plan_2_{slug}_brief.md
├── ...
├── summary.md                          ← comparison table (9c)
│
└── proposal_space/
    ├── literature/
    │   └── landscape_round1.md         ← breadth + depth pass (1a+1b)
    │
    ├── ideas/
    │   └── candidates_round1.md        ← 10+ ideas (2), new on PIVOT
    │
    ├── hypotheses/
    │   ├── hypothesis_{slug}_round1.md          ← initial (3a)
    │   └── hypothesis_{slug}_round1_revised.md  ← after 3c refine
    │
    ├── plans/
    │   ├── plan_{slug}_round1.md                ← initial (4)
    │   ├── plan_{slug}_round1_revised.md        ← after 8d revision
    │   ├── plan_{slug}_round2_revised.md        ← after round 2 revision
    │   └── ...
    │
    ├── reviews/
    │   ├── advisor_{slug}_round1.md             ← Stage 6 initial
    │   ├── vp_{slug}_round1.md                  ← Stage 7 initial
    │   ├── advisor_{slug}_round1_cycle2.md      ← Stage 8e re-review
    │   ├── vp_{slug}_round1_cycle2.md           ← Stage 8e re-review
    │   ├── advisor_{slug}_round2.md             ← Round 2 review
    │   └── ...
    │
    ├── interaction_log/
    │   ├── stage1_literature_student_round1.md
    │   ├── stage2_ideation_student_round1.md
    │   ├── ...
    │   └── pipeline_summary.md
    │
    └── state/
        ├── state.json                           ← pipeline state
        ├── review_tracker.json                  ← issue tracking + history
        ├── submission_round1.json               ← submission manifest
        └── portfolio_analysis.md                ← portfolio coherence (9a)
```
