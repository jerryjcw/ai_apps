---
name: research-survey
description: >
  Daily AI research survey pipeline: scrapes trending papers from alphaxiv.org,
  filters by user-defined criteria, generates research proposals, and writes
  detailed paper essences for rapid researcher consumption.
  Use this skill whenever the user asks to survey recent AI/ML papers, scan
  alphaxiv or arxiv for trending work, filter papers by research interest,
  generate research directions or proposals from papers, or create paper
  summaries/essences targeted at researchers. Also trigger when the user
  mentions "daily paper scan", "research survey", "what's new on arxiv",
  "paper digest", "research landscape", or wants to find promising papers
  to extend or build on. This skill is the full end-to-end pipeline —
  invoke it even if the user only wants a single step (e.g., "just filter
  today's papers" or "write an essence for this paper").
---

# Research Survey Pipeline

An end-to-end pipeline for discovering, filtering, analyzing, and deeply
understanding trending AI/ML research papers. Designed for AI researchers
(Meta IC5/6 level or equivalent) who want to stay on top of the field and
identify promising research directions.

---

## Environment Setup: Playwright Browser Automation

This pipeline uses **Playwright** (Python) for all browser automation:
scraping alphaxiv (Step 1a), and extracting paper content from arxiv HTML
pages (Step 1c, and deeper reads in Steps 3-4).

### Prerequisites

Playwright must be installed in the project's Python environment. Check with:
```bash
python3 -c "from playwright.async_api import async_playwright; print('OK')"
```

If not installed:
```bash
pip install playwright && playwright install chromium
```

### When Playwright is not available

If Playwright cannot be installed (e.g., restricted environment):

- **Step 1a (alphaxiv scrape):** Cannot proceed. Ask the user to provide
  a previously scraped `titles_<YYYYMMDD>.md` file.
- **Step 1b (arxiv API):** Works fine — uses `urllib` only.
- **Step 1c (paper content extraction):** Falls back to `WebFetch` +
  `WebSearch` for blog posts, GitHub READMEs, and community breakdowns.
  Mark papers as "abstract-only" where full content was not accessible.
- **Steps 2-4:** Work normally — Step 2 uses enriched Step 1 data +
  `WebSearch`; Steps 3-4 can use `WebFetch` for arxiv HTML if available.

---

## Before You Begin: Gather Parameters

Before starting any work, collect the parameters this pipeline needs. How
you ask depends on the environment:

**In Cowork** (has `AskUserQuestion` tool): Use `AskUserQuestion` to
collect all parameters in a single multi-question prompt.

**In Claude Code** (no `AskUserQuestion`): Ask the user directly in
conversation. Present the parameters as a numbered list and let them
respond with their choices. Keep it to one message — don't ask questions
one at a time.

### Parameters to collect

1. **Root folder** — Where should all outputs be saved?
   - Default: `~/Documents/cowork/alphaxiv/` (or the user's currently
     mounted folder in Cowork)
   - The user may want a different location — always ask.
   - Example alternatives: `~/research/papers/`, a project-specific
     folder, an existing alphaxiv folder from a prior run.

2. **Number of papers to retrieve** — How many papers to scrape from
   alphaxiv?
   - 50 = quick scan (~5 min)
   - 100 = standard (recommended, ~10 min)
   - 200 = comprehensive (~20 min)
   - Default: 100.

3. **Filtering criteria revisions** — Present the default criteria
   (see Step 2) and ask if the user wants to modify any:
   - Different compute budget (e.g., "I only have 4x A100" or "I have
     a full cluster")
   - Different research area (e.g., "vision+language" instead of
     "LLM only")
   - Different maturity preference (e.g., "I want established topics
     with clear baselines")
   - Specific topics to include or exclude (e.g., "no MoE papers" or
     "only reasoning-related")

4. **Number of top papers** for deep-dive (proposals + essences).
   Default: 5. Range: 3-10.

5. **Which steps to run:**
   - Full pipeline: Steps 1→2→3→4 (recommended)
   - Scan & filter only: Steps 1→2
   - Proposals only: Step 3 (needs existing filtered file or specific
     paper IDs)
   - Essences only: Step 4 (needs existing filtered file or specific
     paper IDs)

If the user has already specified some of these in their message (e.g.,
"scan the top 50 papers from alphaxiv and filter for RL-related work"),
extract those values and only ask about the remaining unknowns.

### After parameters are confirmed

1. **Check Playwright availability** (see Environment Setup above)
2. **Create the root folder** if it doesn't exist
3. **Create a TodoList** tracking each step to run
4. **Begin Step 1** (or whichever step the user requested)

---

## Pipeline Overview

The pipeline has **four steps** that build on each other. Each step produces
files in a structured directory hierarchy:

```
<root_folder>/
├── <YYYYMMDD>/
│   ├── raw_popular_papers_<YYYYMMDD>.txt    # Step 1 output (flat text)
│   ├── titles_<YYYYMMDD>.md                 # Step 1 output (enriched markdown)
│   └── filtered_<YYYYMMDD>.md               # Step 2 output
├── proposals/
│   └── <YYYY>/
│       └── <Paper_Title>.md                  # Step 3 output (one per paper)
└── essence/
    └── <YYYY>/
        └── <MM>/
            └── <Paper_Title>.md              # Step 4 output (one per paper)
```

---

## Step 1: Scrape and Enrich Trending Papers

**Goal:** Extract the top N papers from alphaxiv.org, then enrich each
paper with full abstracts, authors, categories (from the arxiv API), and
method/experiments/contributions (from arxiv HTML pages). This produces a
comprehensive dataset that Step 2 can filter on without needing additional
web lookups for basic paper content.

Step 1 has three sub-steps that run sequentially:

```
Step 1a: Alphaxiv scrape (Playwright)     → IDs, titles, AI summaries, tags, likes   ~10s
Step 1b: Arxiv API batch                  → full abstracts, authors, categories       ~5s
Step 1c: Arxiv HTML extraction            → method, experiments, contributions        ~30s
         + fallback for no-HTML papers    → WebSearch for blog posts/READMEs          ~2min
```

### Preparation

1. Create the date directory: `<root_folder>/<YYYYMMDD>/`
2. Check if output files already exist for today. If they do, ask the user
   whether to re-scrape or reuse existing data.
3. Activate the Python environment that has Playwright installed.

---

### Step 1a: Scrape AlphaXiv Trending Papers

AlphaXiv renders dynamically (React) — `WebFetch` and `curl` only return
the first ~20 server-rendered papers. Use Playwright to scroll and load
all papers.

**Playwright scraping script pattern:**

```python
import asyncio, json
from playwright.async_api import async_playwright

async def scrape_alphaxiv(target=100):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://alphaxiv.org', wait_until='networkidle', timeout=30000)

        # Scroll to load papers (~20 per scroll)
        prev_count = 0
        no_change_rounds = 0
        for i in range(30):
            count = await page.evaluate('''() => {
                const links = document.querySelectorAll('a[href*="/abs/"]');
                const ids = new Set();
                for (const a of links) {
                    const m = a.href.match(/abs\\/(\\d+\\.\\d+)/);
                    if (m) ids.add(m[1]);
                }
                return ids.size;
            }''')
            if count >= target:
                break
            if count == prev_count:
                no_change_rounds += 1
                if no_change_rounds >= 3:
                    break
            else:
                no_change_rounds = 0
            prev_count = count
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(2)

        # Extract paper data from cards
        papers = await page.evaluate('''() => {
            // Paper cards use this class pattern (may change over time)
            const cards = document.querySelectorAll(
                'div[class*="rounded-xl"][class*="border-border"][class*="bg-panel"]');
            const results = [];
            const seen = new Set();

            for (const card of cards) {
                const link = card.querySelector('a[href*="/abs/"]');
                if (!link) continue;
                const m = link.href.match(/abs\\/(\\d+\\.\\d+)/);
                if (!m || seen.has(m[1])) continue;
                seen.add(m[1]);

                // Title: first /abs/ link with substantial text
                const titleLinks = card.querySelectorAll('a[href*="/abs/"]');
                let title = '';
                for (const tl of titleLinks) {
                    const t = tl.textContent.trim();
                    if (t && !t.match(/^\\d/) && t.length > 5) { title = t; break; }
                }

                // AI summary (not the real abstract)
                let aiSummary = '';
                const summarySpan = card.querySelector('p.line-clamp-4 > span');
                if (summarySpan) aiSummary = summarySpan.textContent.trim();

                // Date
                const dateEl = card.querySelector('span.text-sm.font-medium');
                const date = dateEl ? dateEl.textContent.trim() : '';

                // Authors
                const authorEls = card.querySelectorAll(
                    'div.flex.items-center.gap-1\\.5.font-normal');
                const authors = Array.from(authorEls).map(
                    a => a.textContent.trim()).filter(a => a.length > 1);

                // Tags/topics (category links)
                const tagLinks = card.querySelectorAll(
                    'a[href*="customCategories="], a[href*="categories="]');
                const tags = Array.from(tagLinks).map(
                    a => a.textContent.trim().replace('#', ''));

                // Likes count
                const likeBtn = card.querySelector('button span');
                const likes = likeBtn ? parseInt(likeBtn.textContent.trim()) || 0 : 0;

                // GitHub link
                const ghLink = card.querySelector('a[href*="github.com"]');
                const github = ghLink ? ghLink.href : '';

                results.push({
                    arxiv_id: m[1], title, ai_summary: aiSummary,
                    date, authors, tags, likes, github
                });
            }
            return JSON.stringify(results);
        }''')

        await browser.close()
        return json.loads(papers)
```

**Important notes:**
- AlphaXiv's DOM structure may change. If selectors return empty results,
  use `page.content()` to inspect the current HTML and adjust selectors.
- Each scroll loads ~20 papers. 5 scrolls = 100 papers in ~10 seconds.
- The AI summary shown on cards is NOT the real abstract — it's an
  alphaxiv-generated summary. The real abstract comes from Step 1b.

---

### Step 1b: Batch Fetch from ArXiv API

The arxiv API provides full abstracts, complete author lists, and arxiv
categories. It supports batch queries of up to ~100 IDs per request.

**ArXiv API query pattern:**

```python
import urllib.request
import xml.etree.ElementTree as ET

def fetch_arxiv_metadata(arxiv_ids):
    """Batch fetch metadata for up to 100 papers from arxiv API."""
    ns = {"atom": "http://www.w3.org/2005/Atom",
          "arxiv": "http://arxiv.org/schemas/atom"}
    id_list = ",".join(arxiv_ids)
    url = f"http://export.arxiv.org/api/query?id_list={id_list}&max_results={len(arxiv_ids)}"

    req = urllib.request.Request(url, headers={"User-Agent": "ResearchSurvey/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read().decode()

    root = ET.fromstring(data)
    results = {}

    for entry in root.findall("atom:entry", ns):
        arxiv_id_full = entry.find("atom:id", ns).text.split("/")[-1]
        # Strip version suffix (e.g., "2603.19461v1" -> "2603.19461")
        arxiv_id = arxiv_id_full.split("v")[0]

        title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
        abstract = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
        authors = [a.find("atom:name", ns).text
                    for a in entry.findall("atom:author", ns)]
        categories = list(set(
            [c.get("term") for c in entry.findall("arxiv:primary_category", ns)] +
            [c.get("term") for c in entry.findall("atom:category", ns)]
        ))
        published = entry.find("atom:published", ns).text
        # Comments field (often has page count, GPU info, code links)
        comment_el = entry.find("arxiv:comment", ns)
        comment = comment_el.text.strip() if comment_el is not None else ""

        results[arxiv_id] = {
            "title": title, "abstract": abstract, "authors": authors,
            "categories": categories, "published": published, "comment": comment
        }

    return results
```

**Merge strategy:** For each paper from Step 1a, look up its arxiv_id in
the API results. Replace the alphaxiv AI summary with the real abstract.
Merge author lists (API has complete list). Add categories and comments.

If a paper ID is not found in the API (e.g., wrong ID from alphaxiv),
flag it for later verification in Step 1c.

---

### Step 1c: Extract Paper Content from ArXiv HTML

For each paper, attempt to read the arxiv HTML version to extract:
- **Contributions** (from Introduction)
- **Method summary** (from the method/approach section)
- **Experiments & compute details** (from experiments/evaluation section —
  GPU counts, model sizes, training duration, dataset sizes)

This is the critical enrichment that enables informed filtering in Step 2.

**HTML availability:** ~60% of recent papers have HTML versions. For the
~40% that don't, use the fallback strategy below.

**Playwright extraction pattern:**

```python
async def extract_paper_content(page, arxiv_id):
    """Extract method, experiments, and contributions from arxiv HTML."""
    result = {
        "arxiv_id": arxiv_id,
        "html_available": False,
        "contributions": "",
        "method": "",
        "experiments": "",
        "headings": []
    }

    url = f"https://arxiv.org/html/{arxiv_id}"
    try:
        resp = await page.goto(url, wait_until='domcontentloaded', timeout=10000)
        if resp and resp.status == 404:
            return result
    except:
        return result

    sections_count = await page.evaluate(
        'document.querySelectorAll("section.ltx_section").length')
    if sections_count == 0:
        return result

    result["html_available"] = True

    data = await page.evaluate('''() => {
        const sections = document.querySelectorAll('section.ltx_section');
        const output = {method: "", experiments: "", contributions: "", headings: []};
        let foundRelatedWork = false;
        let methodCaptured = false;

        for (const s of sections) {
            const h = s.querySelector('h2');
            if (!h) continue;
            const headText = h.textContent.trim();
            const lower = headText.toLowerCase();
            output.headings.push(headText);

            const getText = (section, maxLen) => {
                const paras = section.querySelectorAll('p');
                let text = '';
                for (const p of paras) {
                    text += p.textContent.trim() + '\\n';
                    if (text.length > maxLen) break;
                }
                return text.substring(0, maxLen);
            };

            // Method: match by keywords OR by position (after Related Work)
            const methodKW = ['method', 'approach', 'framework', 'architecture',
                'proposed', 'our ', 'model', 'system', 'design', 'technique',
                'algorithm'];
            const skipKW = ['related', 'introduction', 'conclusion', 'discussion',
                'acknowledgement', 'appendix', 'experiment', 'result',
                'evaluation', 'ablation', 'limitation'];

            if (!methodCaptured && !skipKW.some(k => lower.includes(k))) {
                if (foundRelatedWork || methodKW.some(k => lower.includes(k))) {
                    output.method = '## ' + headText + '\\n' + getText(s, 3000);
                    methodCaptured = true;
                }
            }

            if (lower.includes('related')) foundRelatedWork = true;

            // Experiments & compute details
            if (['experiment', 'evaluation', 'result', 'setup',
                 'training detail', 'implementation'].some(k => lower.includes(k))) {
                output.experiments += '## ' + headText + '\\n' + getText(s, 3000) + '\\n\\n';
            }

            // Contributions from Introduction
            if (lower.includes('introduction') || lower.includes('intro')) {
                const paras = s.querySelectorAll('p');
                let contribs = '';
                for (const p of paras) {
                    const t = p.textContent.trim().toLowerCase();
                    if (t.includes('contribut') || t.includes('we propose') ||
                        t.includes('we present') || t.includes('we introduce') ||
                        t.includes('our key') || t.includes('our main') ||
                        t.includes('in this paper') || t.includes('in this work') ||
                        t.includes('specifically,')) {
                        contribs += p.textContent.trim() + '\\n';
                    }
                }
                if (!contribs) {
                    const allParas = Array.from(paras);
                    for (const p of allParas.slice(-3)) {
                        contribs += p.textContent.trim() + '\\n';
                    }
                }
                output.contributions = contribs.substring(0, 2000);
            }
        }

        output.experiments = output.experiments.substring(0, 5000);
        return JSON.stringify(output);
    }''')

    parsed = json.loads(data)
    result.update(parsed)
    return result
```

**Performance:** ~0.3 seconds per paper with HTML. Process sequentially
using a single browser page (reuse across papers). Total ~30s for 100
papers (only ~60 will have HTML).

**Processing all papers:**

```python
async def enrich_all_papers(papers):
    """Extract content from arxiv HTML for all papers."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for paper in papers:
            result = await extract_paper_content(page, paper["arxiv_id"])
            paper["html_available"] = result["html_available"]
            paper["contributions"] = result["contributions"]
            paper["method_summary"] = result["method"]
            paper["experiments_summary"] = result["experiments"]
            paper["section_headings"] = result.get("headings", [])

        await page.close()
        await browser.close()
```

---

### Step 1c Fallback: Papers Without HTML

For papers where arxiv HTML returns 404 (~40% of recent papers), gather
what information is available through alternative sources:

1. **Abstract** (already fetched from arxiv API in Step 1b) — always available
2. **AlphaXiv AI summary** (from Step 1a) — provides a condensed overview
3. **WebSearch** for the paper title — look for:
   - GitHub repo README (often has method descriptions and result tables)
   - Blog post breakdowns (emergentmind.com, substacks, etc.)
   - Author threads on X/Twitter
   - HuggingFace model/dataset cards
4. **ArXiv comments field** (from Step 1b) — sometimes mentions page count,
   code URLs, or hardware used

Mark these papers with `"enrichment_source": "fallback"` (vs `"arxiv_html"`
for papers with full HTML). This flag tells Step 2 to weight the filtering
decision accordingly — less confidence in compute/method estimates for
fallback papers.

**Important:** Do NOT skip fallback papers entirely. A paper without HTML
may still be a gold-mine research opportunity. The abstract + AI summary +
WebSearch results are often sufficient for Pass 1 triage and even rough
compute estimation.

---

### Step 1 Output Files

**`raw_popular_papers_<YYYYMMDD>.txt`** — Flat text, one paper per block:
```
=== PAPER 1 ===
Title: <title>
ArXiv: <arxiv_id>
Date: <date>
Authors: <full author list>
Categories: <arxiv categories>
Tags: <alphaxiv tags>
Likes: <count>
GitHub: <url or N/A>
HTML Available: <yes/no>
Abstract: <full abstract from arxiv API>

AI Summary: <alphaxiv AI summary>

Contributions: <extracted from introduction, or "N/A">

Method Summary: <extracted from method section, or "N/A">

Experiments & Compute: <extracted from experiments section, or "N/A">

=== PAPER 2 ===
...
```

**`titles_<YYYYMMDD>.md`** — Enriched formatted markdown:
```markdown
# AlphaXiv Popular Papers — YYYY/MM/DD

Total papers extracted: **N**
Papers with full HTML content: **M** (X%)
Papers with fallback enrichment: **K**

---

## 1. <Paper Title>

**ArXiv:** [<id>](https://arxiv.org/abs/<id>)
**Date:** <date>
**Authors:** <full author list>
**Categories:** <arxiv categories>
**Tags:** <alphaxiv tags>
**Likes:** <count> | **GitHub:** <url or N/A>
**Enrichment:** <arxiv_html | fallback>

### Abstract
<full abstract from arxiv API>

### Key Contributions
<extracted contributions from introduction, or alphaxiv AI summary if no HTML>

### Method Overview
<extracted method summary, or "Not available — paper has no HTML version" >

### Experiments & Compute Details
<extracted experiments/compute info, or "Not available — paper has no HTML version">

---
```

### Validation

After writing both files, verify:
- Paper count matches the target (report actual count if fewer)
- Each paper has at minimum: title, arxiv ID, and full abstract
- No duplicate entries
- HTML enrichment percentage is reported
- Files are saved to the correct directory

Report to the user: "Scraped X papers from alphaxiv. Enriched with
abstracts (X/X), full paper content (M/X via HTML, K/X via fallback).
Saved to `<YYYYMMDD>/`. Ready for filtering."

---

## Step 2: Filter Papers by Research Criteria

**Goal:** Read through all scraped papers, and filter down to papers
matching the user's criteria. Step 1's enriched data provides method
summaries, experiment details, and compute requirements for most papers,
enabling well-informed filtering without heavy web searching.

### Filtering criteria

Use the criteria confirmed in the parameter-gathering step. If the user
didn't customize, use these defaults:

1. **Compute:** Medium — 8-16x NVIDIA H200 GPUs (roughly $50K-$150K per
   experiment). Exclude papers requiring massive compute (100+ GPUs) or
   trivially small experiments.
2. **Scope:** LLM or agent related. Must have theoretical, model
   architecture, loss function, or training methodology contributions.
   Exclude pure engineering / infrastructure / benchmark-only papers.
3. **Maturity:** Not a fully mature topic. There should be room for
   follow-up work publishable at top venues (ICLR, NeurIPS, ICML, ACL,
   EMNLP, UAI, etc.).
4. **Novelty:** Prefer papers introducing new frameworks, theoretical
   connections, or paradigm shifts over incremental improvements.

### Process: Two-pass filtering

**Pass 1 — Quick triage (title + abstract + enrichment data):**
Read through all papers from `titles_<YYYYMMDD>.md`. For each paper,
make a quick keep/maybe/exclude decision based on title, abstract, key
contributions, and method overview. Papers with HTML enrichment have
method and experiment data — use this to quickly assess compute
requirements and method complexity. This pass should categorize all N
papers in one go. The goal is to reduce the candidate set from ~100 to
~25-30 "maybe or keep" papers.

**Pass 2 — Deep research (for candidates only):**
For each "keep" or "maybe" paper from Pass 1:
1. Review the enriched experiments & compute details from Step 1. For
   papers with HTML content, this should already contain GPU counts,
   model sizes, training duration, and dataset info.
2. For fallback-enriched papers (no HTML), use `WebSearch` to find:
   the paper's actual contribution, author track record, lab/affiliation,
   code availability, community reception (Twitter/X, Reddit, HuggingFace)
3. Make a confident keep/exclude decision
4. For kept papers, fill in the full analysis table (topic, importance,
   directions, compute, data, datasets, venue probability)

This two-pass approach avoids wasting web searches on papers that are
obviously outside scope (e.g., robotics, video generation, autonomous
driving when the user wants LLM theory). The enriched Step 1 data means
Pass 2 primarily needs WebSearch only for fallback papers and for
supplementary context (author reputation, community reception).

### Cross-referencing between papers

After filtering, look for thematic connections between kept papers.
Papers that address the same phenomenon from different angles (e.g.,
one theoretical and one empirical) make strong cross-domain proposal
candidates in Step 3. Note these connections.

### Output: `filtered_<YYYYMMDD>.md`

```markdown
# AlphaXiv Filtered Papers — YYYY/MM/DD

## Filtering Criteria

1. **Compute:** <criteria as confirmed with user>
2. **Scope:** <criteria>
3. **Maturity:** <criteria>
4. **Novelty:** <criteria>

---

## Filtered Papers (N / total)

---

### 1. <Paper Title>

**Paper #<original_number> — ArXiv [<id>](https://arxiv.org/abs/<id>) — <authors> — <date>**

<2-3 sentence summary of the paper's contribution>

| Field | Details |
|---|---|
| **Topic Category** | <e.g., LLM Architecture / Attention Mechanism> |
| **Importance** | <star rating 1-5 stars> — <why it matters> |
| **Possible Directions** | (a) ...; (b) ...; (c) ...; (d) ...; (e) ... |
| **Compute Estimate** | <e.g., 8-16x H200> |
| **Data Estimate** | <e.g., 100-300B tokens> |
| **Datasets** | <relevant benchmarks and data sources> |
| **Top-Venue Probability** | **<X>%** — <brief justification> |

---

### 2. <Next paper...>
...

---

## Top N Recommendations (Ranked)

### 1. <Paper Title> (Paper #N) — **<X>%**
<2-3 sentences on why this is the top pick and what follow-ups look like>

### 2. ...
### 3. ...
### 4. ...
### 5. ...

(Adjust count to match user's requested top-N.)

---

## Exclusion Summary (M papers excluded)

| # | Paper | Exclusion Reason |
|---|---|---|
| 1 | <title> | <brief reason> |
| 2 | ... | ... |
```

**Completeness check:** Every single paper from Step 1 must appear
somewhere — either in the filtered list with full analysis, or in the
exclusion table with a reason. No paper should be silently dropped. If
the total (filtered + excluded) doesn't equal the Step 1 count, you have
a gap.

### Step transition

After writing the filtered file, present the top N recommendations to the
user as a brief summary. Ask: "These are the top N papers I'd recommend
for deep-dive proposals and essences. Would you like to adjust the list
before I proceed?" This checkpoint prevents wasted work if the user
disagrees with the ranking.

---

## Step 3: Research Proposals

**Goal:** For each of the top N recommended papers, produce a detailed
research proposal document with actionable follow-up directions.

### Prerequisite check

Before starting, verify:
- `filtered_<YYYYMMDD>.md` exists and has a top-N recommendation list
- For each paper in the list, check if
  `proposals/<YYYY>/<Paper_Title>.md` already exists. If it does, skip
  that paper (don't overwrite unless the user explicitly asks).

### Process per paper

For each paper that needs a proposal:

1. **Deep-dive the paper:**
   - Start with the enriched data from Step 1 (method summary,
     experiments, contributions). This gives a strong foundation.
   - For papers with HTML: open `https://arxiv.org/html/<arxiv_id>` in
     Playwright for additional section-by-section extraction if needed
     (e.g., related work, detailed ablations, theoretical proofs)
   - For papers without HTML: use `WebFetch` on the abstract page
     `/abs/<id>` + GitHub README + `WebSearch` for blog posts
   - Goal: understand the full method, experiments, and limitations

2. **Survey related work:**
   - Search for 5-10 closely related papers via WebSearch
   - Look for: direct competitors, foundational work being extended,
     concurrent/independent work on similar topics
   - Build a landscape table: what's been done, what gaps remain

3. **Generate 3 extension proposals:**
   - Direct follow-ups building on the paper's core contribution
   - Each should address a specific gap identified in the related work
   - Each should have a clear path to a top-venue publication
   - Include: motivation, rationale, phased implementation plan,
     experiment table, compute/cost estimate, venue probability

4. **Generate 2 cross-domain proposals:**
   - Combine this paper's ideas with other papers from the filtered
     list (preferred) or from the broader literature
   - Label these clearly as "x <Other Paper Title>"
   - Cross-domain proposals often have the highest novelty since they
     connect ideas that no one else has connected yet

5. **Rank all 5 proposals:**
   - Comparative table with: venue probability, compute cost, risk
     level, novelty score, and recommendation
   - Pick a single top recommendation with justification

### Output: `proposals/<YYYY>/<Paper_Title>.md`

Use underscores in filenames (e.g., `Transformers_are_Bayesian_Networks.md`).
Create the `<YYYY>/` subdirectory if it doesn't exist.

```markdown
# Research Proposals: <Paper Title>

**Base Paper:** [<arxiv_id>](https://arxiv.org/abs/<arxiv_id>) — <authors> — <date>

## Paper Summary

<Concise 3-5 sentence summary>

---

## Related Work Landscape

| Work | Year | Relation | What's Left Open |
|---|---|---|---|
| <paper name> | <year> | <how it relates> | <gap remaining> |
| ... | ... | ... | ... |

**Key Gaps:** (1) ...; (2) ...; (3) ...

---

## Proposal A: <Title>

### Why This Proposal
<1-2 paragraphs on motivation>

### Rationale & Feasibility
- **Rationale:** <why this direction makes sense>
- **Feasibility:** <HIGH/MEDIUM/LOW with justification>

### Detailed Implementation
1. **Phase 1 — <name> (Months X-Y)** — <what to do and expected outcome>
2. **Phase 2 — <name> (Months X-Y)** — <what to do and expected outcome>
3. **Phase 3 — <name> (Months X-Y)** — <what to do and expected outcome>

### Experiment Plan

| Experiment | Model Size | Data | GPUs | Duration |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

### Data & Compute
- **Data:** <sources and scale>
- **Compute:** <GPU count and duration>
- **Total Cost:** <estimated cloud compute cost>

### Top-Venue Probability: **<X>%**
<Risk/reward assessment and 2-3 target venues>

---

## Proposal B: <Title>
... (same structure)

## Proposal C: <Title>
... (same structure)

## Proposal D (Cross-domain): <Title> x <Other Paper>
... (same structure, but explain the cross-pollination)

## Proposal E (Cross-domain): <Title> x <Other Paper>
... (same structure)

---

## Comparative Assessment

| Proposal | Venue Prob | Compute | Risk | Novelty | Recommendation |
|---|---|---|---|---|---|
| A | X% | ... | LOW/MED/HIGH | 1-5 stars | ... |
| B | X% | ... | ... | ... | ... |
| C | X% | ... | ... | ... | ... |
| D | X% | ... | ... | ... | ... |
| E | X% | ... | ... | ... | ... |

**Top Recommendation:** Proposal <X> — <2-3 sentence justification>
```

### Parallelization

If subagents are available, process multiple papers in parallel. Each
paper's proposal is independent — there's no dependency between them
except for cross-domain proposals (which reference other filtered papers
by name, not by content that would need to be generated first).

---

## Step 4: Paper Essences

**Goal:** For each top-recommended paper, produce a detailed explanation
document that lets a senior AI researcher rapidly understand the paper's
contribution, method, and significance — without needing to read the
full paper.

### Critical rules — non-negotiable

1. **Ground every claim in the actual paper.** Use the enriched data from
   Step 1 as a starting point, then read additional paper content via
   Playwright (arxiv HTML) or WebFetch. If HTML is unavailable, use the
   abstract page + WebSearch for detailed analyses.
2. **Cite referenced work.** When mentioning prior work the paper builds
   on, include the citation (author, year, venue if known).
3. **Never fabricate methods or results.** If you cannot verify a detail
   from the paper, say so explicitly. Mark unverified claims:
   `[from abstract only — not independently verified]`.
4. **Distinguish your interpretation from the paper's claims.** If you're
   drawing an inference the paper doesn't explicitly make, flag it.

### Prerequisite check

Before starting, verify:
- For each paper, check if `essence/<YYYY>/<MM>/<Paper_Title>.md` already
  exists. Skip if so (unless user asks for a rewrite).
- Create `essence/<YYYY>/<MM>/` if it doesn't exist.

### Process per paper

1. **Start with Step 1 enrichment data:**
   The enriched `titles_<YYYYMMDD>.md` already contains method summary,
   experiments/compute details, and contributions for papers with HTML.
   Use this as the foundation — it eliminates redundant paper fetching.

2. **Deep-read via arxiv HTML (if available):**
   Open `https://arxiv.org/html/<arxiv_id>` in Playwright. Extract
   remaining sections not covered in Step 1c: Related Work (for
   positioning), detailed subsections of the method, ablation studies,
   theoretical proofs, conclusion/limitations.

3. **Supplement with web sources:**
   - `WebSearch` for: GitHub repo (README often has clear method
     descriptions), blog posts / breakdowns, author threads on X/Twitter
   - `WebFetch` the GitHub repo README if found

4. **Fallback if no HTML and no good web sources:**
   - Use the abstract + Step 1 enrichment data + whatever WebSearch surfaces
   - Clearly label the essence as "based on abstract and secondary
     sources" at the top
   - This is acceptable but not ideal — the user should know

5. **Write the essence** following the template below.

6. **Self-review before saving:** Re-read what you wrote and check:
   - Did you fabricate any methods or results not in the paper?
   - Are all prior work citations real? (Don't invent paper titles)
   - Are the experimental numbers sourced from the actual paper?
   - Is the intuition section genuinely insightful, or just a restatement
     of the abstract?

### Output: `essence/<YYYY>/<MM>/<Paper_Title>.md`

```markdown
# <Paper Title>

**Paper:** [arXiv <id>](https://arxiv.org/abs/<id>)
**Authors:** <authors> (<affiliation>)
**Date:** <date>
**Code:** [<repo>](<url>) (if available)

---

## 1. Intuition: Why This Works

Start with the core insight in plain language. Why does this approach
work? What's the key idea that makes it non-obvious? Use analogies if
helpful. A senior researcher reading this section should immediately
grasp the "aha moment" of the paper.

Don't just restate the abstract. Explain the *mechanism* — why does
this method produce better results? What prior assumption does it
challenge? 3-4 paragraphs.

---

## 2. Previous Work & Positioning

| Work | What It Does | How This Paper Differs |
|---|---|---|
| <Prior work 1> (<Author>, <Year>) | <what it does> | <how this paper goes further> |
| <Prior work 2> ... | ... | ... |

End with a paragraph: "Why this paper is distinctive: ..."

---

## 3. Method: Detailed Walkthrough

Break into numbered subsections (3.1, 3.2, ...) following the paper's
own structure. Include:
- Key definitions and formulas (use code blocks for math)
- Algorithm descriptions with enough detail to reimplement
- Design choices and their justification (why X over Y?)
- Reference specific sections/theorems from the paper

This is the longest section. A researcher should be able to understand
the full method from this section alone, without reading the original
paper. Aim for 5-10 subsections depending on the paper's complexity.

---

## 4. Key Experiments

For each of the 3-5 most informative experiments:

### Experiment N: <Descriptive Name> (Section X.Y)
- **Setup:** Model sizes, datasets, baselines, compute budget
- **Result:** Key numbers in a comparison table where appropriate
- **Interpretation:** What does this tell us? What's surprising?

Focus on experiments that: (a) validate the core claim, (b) reveal
surprising properties, (c) compare against strong baselines, or
(d) include ablations that explain what matters and what doesn't.

---

## 5. Additional Notes for Researchers

Include any of:
- Open questions or limitations acknowledged by the paper
- Community reception and criticism
- Connections to other recent work (especially other papers from this
  survey's filtered list)
- Practical deployment considerations
- Key references cited (with full author, year, venue)
- Caveats (wrong arxiv IDs, missing HTML, unverified claims, etc.)

---

*Citation: <Author(s)>. (<Year>). <Title>. arXiv:<id>.*
```

### Parallelization

Like Step 3, paper essences are independent and can be processed in
parallel via subagents if available. Each essence only needs access to
its own paper's content.

---

## Step Transitions and Resumability

### Between steps

After each step completes, briefly report what was produced:
- Step 1: "Scraped X papers. Enriched M via HTML, K via fallback. Saved to `<YYYYMMDD>/`."
- Step 2: "Filtered to X papers. Top N: [list]. Proceed with proposals?"
- Step 3: "Proposals written for X papers. Proceed with essences?"
- Step 4: "Essences complete for all X papers."

The Step 2 -> Step 3 transition is the key checkpoint — the user should
confirm the top-N list before you invest time in deep-dive proposals.

### Resuming a partial run

The pipeline may be interrupted (context limit, browser crash, user
stepping away). To resume:

1. Check which output files already exist in `<root_folder>/`
2. For Step 1: if `titles_<YYYYMMDD>.md` exists, reuse it
3. For Step 2: if `filtered_<YYYYMMDD>.md` exists, reuse it
4. For Step 3: check each `proposals/<YYYY>/<Paper_Title>.md` — only
   process papers that don't have proposal files yet
5. For Step 4: check each `essence/<YYYY>/<MM>/<Paper_Title>.md` — only
   process papers that don't have essence files yet

This means you can always pick up where the last session left off.

### Running individual steps

The user may ask for just one step. Common requests and what to do:

| User says | Run | Prerequisites |
|---|---|---|
| "Scan today's papers" | Step 1 | Playwright installed |
| "Filter these papers" | Step 2 | Step 1 output exists |
| "What's interesting today?" | Steps 1+2 | Playwright installed |
| "Write proposals for paper X" | Step 3 (single paper) | Arxiv ID or title |
| "Write an essence for paper X" | Step 4 (single paper) | Arxiv ID or title |
| "Run the full pipeline" | Steps 1->2->3->4 | Playwright installed |

For Steps 3 and 4 on a single paper (given by arxiv ID or title), you
don't need prior steps — just research the paper directly and produce the
output. Still save to the same directory structure.

---

## Technical Notes

### ArXiv access patterns

- **ArXiv API:** `http://export.arxiv.org/api/query?id_list=<ids>` — batch
  fetch metadata for up to ~100 papers. Returns XML with titles, abstracts,
  authors, categories, comments. Rate limit: ~1 request per 3 seconds.
- **Direct HTML:** `https://arxiv.org/html/<arxiv_id>` — full paper content.
  Not always available (~60% of recent papers). Returns 404 if not converted.
- **Abstract page:** `https://arxiv.org/abs/<arxiv_id>` — always available,
  has title, authors, abstract, and links.
- **Egress proxy blocks:** In some environments, `arxiv.org` is blocked
  for `WebFetch`/`curl` but accessible via Playwright. Always prefer
  Playwright for arxiv access.

### Playwright tips

- **Reuse browser pages:** Create one `browser` and one `page`, reuse the
  page across multiple paper extractions. Don't create/destroy pages per
  paper — it adds overhead.
- **Timeout handling:** Use `wait_until='domcontentloaded'` (not
  `'networkidle'`) for arxiv HTML pages — networkidle can hang on ad/tracker
  requests. Set timeout to 10-15 seconds.
- **Headless mode:** Always use `headless=True` for automated pipeline runs.
- **Error recovery:** If a page load fails, log the error and continue to
  the next paper. Don't let one failure stop the entire batch.

### Handling broken arxiv IDs

AlphaXiv occasionally lists wrong arxiv IDs (the ID maps to a completely
different paper). When this happens:
1. Note the discrepancy in the output file
2. Search for the paper by its exact title via `WebSearch`
3. If found under a different ID, use the correct one
4. If not found at all, write the essence/proposal based on the abstract
   from alphaxiv + whatever WebSearch surfaces, clearly marking it as
   "based on abstract and secondary sources"

### Fallback strategy when a paper is inaccessible

Sometimes you can't get full paper content — HTML doesn't exist, and web
searches only return the abstract. In this case:

1. Use the abstract (from arxiv API in Step 1b)
2. Use the alphaxiv AI summary (from Step 1a)
3. Search for the GitHub repo README — these often contain method
   descriptions, architecture diagrams, and result tables
4. Search for blog post breakdowns (sites like emergentmind.com,
   various substacks, etc.)
5. Search for author threads on X/Twitter
6. Write what you can, clearly marking the depth of sourcing at the top
   of the document

A partially-sourced essence with honest attribution is far more valuable
than a fabricated one.

---

## Reference: Example Outputs

For concrete examples of what good output looks like at each step (format,
depth, quality), read `references/example_outputs.md` in this skill's
directory. Consult it if you're unsure about the expected format or
quality bar for any step.
