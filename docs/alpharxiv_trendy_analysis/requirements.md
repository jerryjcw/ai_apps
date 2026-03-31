# Requirements: AlphaRxiv Trendy Paper Analysis

## 1. Problem Statement

The user manually discovers trending AI research papers on alphaxiv.org, then iteratively works with Claude (via cowork) to: (1) parse raw page content into structured paper lists, (2) filter and analyze papers against personal research criteria, (3) perform literature reviews on selected papers. This process is time-consuming and repetitive. The system must automate this entire pipeline while matching the output quality of the interactive cowork sessions.

---

## 2. Functional Requirements

### FR-1: Scraping

| ID | Requirement |
|----|-------------|
| FR-1.1 | The system must scrape trending papers from alphaxiv.org without requiring user login. |
| FR-1.2 | The system must handle alphaxiv's React SPA by rendering JavaScript (not relying on static HTTP). |
| FR-1.3 | The user must be able to configure a **minimum bookmark count** threshold; papers below this threshold are discarded. |
| FR-1.4 | The user must be able to configure a **minimum view count** threshold; papers below this threshold are discarded. |
| FR-1.5 | The user must be able to configure sort order ("Hot" or "Likes"). |
| FR-1.6 | The user must be able to optionally filter by categories, subcategories, and custom topic categories (e.g., "agents", "attention-mechanisms"). |
| FR-1.7 | The system must scroll/paginate to capture all visible papers, not just the first viewport. |

### FR-2: Parsing

| ID | Requirement |
|----|-------------|
| FR-2.1 | The system must parse raw alphaxiv page text into structured paper records containing: title, date, authors, abstract, hashtags, bookmark count, view count. |
| FR-2.2 | The primary parser must be deterministic (regex-based, no LLM dependency). |
| FR-2.3 | If the regex parser extracts fewer than 3 papers (indicating a page format change), the system must automatically fall back to an LLM-based parser. |
| FR-2.4 | The system must produce two output formats: machine-readable JSON (`papers.json`) and human-readable markdown (`titles.md`). |
| FR-2.5 | The `titles.md` format must match the reference output: numbered papers with title, date, and abstract. (Reference: `/Users/jerry/Documents/cowork/alphaxiv/20260318/titles.md`) |

### FR-3: Enrichment

| ID | Requirement |
|----|-------------|
| FR-3.1 | The system must enrich each paper with metadata from the arXiv API: full abstract, confirmed arXiv ID, author list, categories, and PDF URL. |
| FR-3.2 | The system must respect the arXiv API rate limit (1 request/second). |
| FR-3.3 | Papers not found on arXiv must retain their original data and be marked as "not_found" (not dropped). |

### FR-4: Analysis (LLM-Powered)

| ID | Requirement |
|----|-------------|
| FR-4.1 | The system must evaluate each paper against user-configured research criteria and classify it as INCLUDED or EXCLUDED. |
| FR-4.2 | For each included paper, the system must produce all of the following analysis fields: arXiv ID, Topic Category, Core Contribution, Importance (1–5 stars with justification), 4 Research Directions (a–d) each with feasibility, Compute Estimate, Data Estimate, Datasets, and Top Conference Probability (percentage with reasoning). |
| FR-4.3 | For each excluded paper, the system must provide a **specific** exclusion reason (e.g., "Pure CV/video generation, not LLM-related" — not just "not relevant"). |
| FR-4.4 | The system must produce a Top 5 summary table ranked by conference probability. |
| FR-4.5 | The system must produce output in **both Chinese (Traditional) and English**, as separate files. |
| FR-4.6 | The output format must match the reference cowork output, including: markdown tables with field labels, star ratings (⭐ repeated), colored probability emojis (🟢 >= 65%, 🟡 50–64%, 🔴 < 50%), and 4 research direction sub-items per paper. (Reference: `/Users/jerry/Documents/cowork/alphaxiv/20260318/filtered.md`) |

### FR-5: Literature Review (LLM-Powered)

| ID | Requirement |
|----|-------------|
| FR-5.1 | The user must be able to select specific papers from the filtered output for deeper review (e.g., `--papers 1,3,5`). |
| FR-5.2 | For each selected paper, the system must produce: a deep summary (contribution, methodology, results, limitations), a literature landscape map (prior work, active frontiers, gaps), and 2–3 concrete research proposals. |
| FR-5.3 | Each research proposal must include: problem statement, proposed technical approach, compute/data requirements, feasibility assessment against user's constraints, expected impact, and target venue. |
| FR-5.4 | Literature review output must be produced in both Chinese and English. |

### FR-6: Research Criteria (Configurable)

| ID | Requirement |
|----|-------------|
| FR-6.1 | The user must be able to configure maximum compute (GPU count and model). |
| FR-6.2 | The user must be able to configure focus areas (e.g., LLM, Agent, Reasoning). |
| FR-6.3 | The user must be able to require theoretical/model/training contributions (exclude pure engineering). |
| FR-6.4 | The user must be able to configure target venues for feasibility assessment. |
| FR-6.5 | All criteria must be stored in `config.toml` so they persist across runs. |

### FR-7: Trend Tracking

| ID | Requirement |
|----|-------------|
| FR-7.1 | The system must track papers across runs in a database. |
| FR-7.2 | The system must be able to report papers that have been trending for N+ days. |
| FR-7.3 | The user must be able to view past run history via the CLI. |

### FR-8: Experiment Planning & Novel Approach Synthesis (LLM-Powered)

This stage bridges the gap between "interesting research direction" (FR-5) and "I can start running experiments Monday morning." The current pipeline identifies *what* to work on; this stage determines *how* to work on it, whether the idea is actually novel, what the fastest way to validate it is, and what will go wrong.

| ID | Requirement |
|----|-------------|
| FR-8.1 | The user must be able to select one or more research proposals from Stage 3 output for deep experiment planning (e.g., `--proposal 1` from paper 3's review). |
| FR-8.2 | **Novelty Verification**: For each selected proposal, the system must assess whether the proposed approach already exists in published work. It must search for closely related methods using Semantic Scholar and the model's knowledge, and produce a **novelty delta** — what specifically is new about this proposal vs. the closest existing work. If the approach is not novel, it must flag this and suggest a modification that would make it novel. |
| FR-8.3 | **Novel Approach Synthesis**: The system must go beyond directions suggested in the reviewed paper. It must synthesize genuinely new approaches by combining techniques, insights, or frameworks from **different subfields or papers** encountered during the analysis pipeline. Each synthesized approach must explain: (a) which ideas are being combined and from where, (b) why this combination hasn't been tried (or why now is the right time), and (c) what the expected advantage is over doing either technique alone. |
| FR-8.4 | **Minimum Viable Experiment (MVE)**: For each proposal, the system must design the smallest, fastest experiment that tests the core hypothesis — typically 1–2 GPU-days, a single dataset, and one baseline. The MVE must include: (a) the specific hypothesis being tested, stated as a falsifiable claim, (b) the exact model/dataset/metric triple, (c) expected runtime and compute, (d) the success criterion (what quantitative result would validate continuing), and (e) the failure criterion (what result means the idea doesn't work and should be abandoned or pivoted). |
| FR-8.5 | **Full Experiment Plan**: Conditioned on MVE success, the system must produce a phased experiment plan: Phase 1 (core validation, 1–2 weeks), Phase 2 (scaling and ablations, 2–3 weeks), Phase 3 (benchmarks and paper-ready results, 2–4 weeks). Each phase must specify: concrete experiments to run, expected GPU-hours, datasets, baselines, and go/no-go criteria before proceeding to the next phase. |
| FR-8.6 | **Ablation Design**: The system must identify the 3–5 most important design choices in the proposed approach and produce an ablation table: which components to remove/vary, what each ablation tests, and what the expected outcome is if that component matters vs. doesn't matter. |
| FR-8.7 | **Baseline Selection**: The system must select specific, reproducible baselines with justification. For each baseline: (a) the exact method and reference, (b) whether public code exists (with repo URL if known), (c) expected performance on the target benchmark, and (d) why this baseline is the right comparison (what claim it helps establish). |
| FR-8.8 | **Risk Register & Failure Mode Analysis**: The system must identify the top 3–5 risks that could cause the project to fail, ranked by likelihood × impact. For each risk: (a) description, (b) early warning signs (what you'd observe in the first week that suggests this risk is materializing), (c) mitigation strategy, and (d) pivot plan if mitigation fails. |
| FR-8.9 | **Issue Anticipation**: The system must flag practical issues the researcher is likely to encounter: known instabilities in the training setup, dataset licensing or availability concerns, reproducibility pitfalls (e.g., "this method is sensitive to learning rate warmup schedule"), hardware-specific constraints (e.g., "attention variant X requires custom CUDA kernels not available in standard PyTorch"), and dependency version conflicts. |
| FR-8.10 | The experiment plan output must be produced in both Chinese and English. |
| FR-8.11 | The system must save all intermediate reasoning (extended thinking logs) for the experiment planning stage to enable quality review and debugging. |

### FR-9: CLI

| ID | Requirement |
|----|-------------|
| FR-9.1 | The system must provide individual commands for each stage: `scrape`, `parse`, `analyze`, `review`, `plan`. |
| FR-9.2 | The system must provide a `run` command that executes the full automated pipeline (scrape → parse → enrich → analyze). |
| FR-9.3 | The system must provide a `history` command to view past runs. |
| FR-9.4 | Each run must produce all outputs in a timestamped directory (`data/runs/YYYY-MM-DD/`). |
| FR-9.5 | The `plan` command must accept a paper index and proposal index from a completed review (e.g., `plan --paper 3 --proposal 1`), and produce the full experiment plan output. |

---

## 3. Quality Requirements

### QR-1: LLM Output Quality

These requirements ensure the LLM-powered stages match cowork-session quality rather than producing shallow single-shot output.

| ID | Requirement |
|----|-------------|
| QR-1.1 | All LLM analysis calls must use **extended thinking** (Anthropic's `thinking` parameter) to enable deep internal reasoning before producing output. |
| QR-1.2 | The Stage 2 analysis prompt must instruct the model to **read ALL papers before assigning any ratings**, to ensure relative scoring (not anchored to the first paper seen). |
| QR-1.3 | Importance ratings must use the **full 1–5 star range** with meaningful differentiation. The prompt must explicitly prevent score clustering (e.g., all papers rated 3–4 stars). |
| QR-1.4 | Research directions must be **specific enough to start a project** — not generic suggestions like "explore more datasets" or "apply to other domains". Each direction must include a concrete technical approach. |
| QR-1.5 | Conference probability estimates must include **reasoning** grounded in venue acceptance rates, paper novelty, and competitive landscape — not just a number. |
| QR-1.6 | The Stage 3 literature review must use a **multi-turn conversation** (not single-shot) to progressively deepen analysis: read → landscape → proposals. |
| QR-1.7 | Literature landscape analysis must **cite specific papers, methods, and research groups** — not generic descriptions like "there has been growing interest in..." |
| QR-1.8 | Research proposals must be **grounded in the user's compute constraints** with explicit feasibility calculations (e.g., "8×H200 for ~48h gives us N FLOPS, sufficient for..."). |
| QR-1.9 | All LLM prompts must include **few-shot examples** from historical cowork sessions to calibrate output depth and style. |
| QR-1.10 | Extended thinking content must be **logged to disk** for debugging and quality review. |
| QR-1.11 | Novelty verification (FR-8.2) must produce a **specific side-by-side comparison** between the proposal and the closest existing work — not just "this is novel" or "this exists." The delta must be technical and concrete (e.g., "Proposal uses information bottleneck for uncertainty estimation in decoding; closest existing work [Author 2025] uses it for representation learning — the application to decoding-time uncertainty is new"). |
| QR-1.12 | The Minimum Viable Experiment (FR-8.4) must be **completable in under 48 GPU-hours** on the user's configured hardware. If the core hypothesis cannot be tested within this budget, the system must decompose it into a simpler sub-hypothesis that can be. |
| QR-1.13 | Risk register items (FR-8.8) must be **grounded in known failure patterns** — not generic risks like "training might diverge." Each risk must reference a specific technical mechanism (e.g., "KL collapse in VAE training when β schedule is too aggressive, as observed in [Bowman et al., 2016]"). |
| QR-1.14 | Ablation design (FR-8.6) must be **minimal and decisive** — each ablation must answer exactly one question. The system must not propose ablations that test obvious components (e.g., "remove the entire model") or redundant variations. |
| QR-1.15 | Novel approach synthesis (FR-8.3) must produce at least one approach that **combines ideas from two or more papers analyzed in the current pipeline run**, creating cross-pollination the user would not have seen by reading each paper in isolation. |

### QR-2: Output Format Quality

| ID | Requirement |
|----|-------------|
| QR-2.1 | Chinese output must use Traditional Chinese (繁體中文) with the specific field labels from the reference: 項目, 內容, 核心貢獻, 重要性預估, 可做的大方向, 計算量預估, Data 量預估, 衝擊頂會機率. |
| QR-2.2 | The filtering criteria section must appear at the top of the output document, listing all active criteria in a numbered list. |
| QR-2.3 | Each included paper must be formatted as a markdown table with consistent field ordering matching the reference. |
| QR-2.4 | The excluded papers section must be a compact table (not per-paper blocks) with index, title, and specific reason. |
| QR-2.5 | The Top 5 summary must be a single table with columns: rank, paper, probability, compute, rationale. |

---

## 4. Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | No web UI for v1. CLI-only interface. |
| NFR-2 | No login or authentication required for alphaxiv scraping. |
| NFR-3 | The ANTHROPIC_API_KEY must be stored in `.env`, never in `config.toml` or source code. |
| NFR-4 | Configuration must be file-based (`config.toml` + `.env`), not requiring code changes to adjust criteria or thresholds. |
| NFR-5 | The system must be runnable via a simple cron job for daily automation. |
| NFR-6 | All intermediate artifacts (raw text, parsed JSON, enriched JSON, analysis JSON) must be saved so any stage can be re-run independently. |
| NFR-7 | The Stage 3 (review) and Stage 4 (experiment planning) steps must remain user-initiated — the `run` command does not include them. |
| NFR-8 | All intermediate and final outputs (`titles.md`, `filtered_zh.md`, `filtered_en.md`, etc.) must **match or surpass** the quality of the reference files produced by Anthropic Cowork at `/Users/jerry/Documents/cowork/alphaxiv/20260318/`. This is the acceptance bar — if automated output is shallower, less specific, or worse-formatted than the cowork baseline, it is not acceptable. |

---

## 5. Data Sources

| Source | Access | Auth | Rate Limit |
|--------|--------|------|------------|
| alphaxiv.org | Playwright (JS rendering required) | None | None observed |
| arXiv API | httpx REST | None | 1 req/sec |
| Semantic Scholar API | httpx REST | None (optional API key for higher limits) | 100 req/sec |
| Claude API | Anthropic Python SDK | API key | Per-plan limits |

---

## 6. Reference Outputs

The following files from a manual cowork session define the target output quality and format:

| File | Defines |
|------|---------|
| `/Users/jerry/Documents/cowork/alphaxiv/20260318/titles.md` | Stage 1 output format: numbered paper list with title, date, abstract |
| `/Users/jerry/Documents/cowork/alphaxiv/20260318/filtered.md` | Stage 2 output format: filtering criteria header, per-paper analysis tables, excluded papers table, Top 5 summary |
| `/Users/jerry/Documents/cowork/alphaxiv/20260318/raw_popular_papers.txt` | Raw input format: what the alphaxiv page text looks like |
