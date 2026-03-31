---
name: research-survey
description: Survey recent AI/ML papers, especially alphaxiv or arXiv trending work, then filter, summarize, and turn promising papers into research directions or deep paper essences. Use when the user wants a paper scan, research survey, arXiv digest, paper filtering by interest, proposal generation from papers, or researcher-focused summaries.
---

# Research Survey

Use this skill for end-to-end paper discovery and filtering. Keep the workflow staged and explicit.

## Ask For Parameters Up Front

Collect in one message unless the user already supplied them:

1. Root output folder
2. Number of papers to retrieve
3. Filter criteria or revisions
4. Number of top papers for deep dive
5. Which steps to run:
   - full pipeline
   - scan and filter only
   - proposals only
   - essences only

If the environment lacks browser automation or network access, say so clearly and ask for existing scraped files as input.

## Workflow

### Step 1: Scrape and enrich papers

Goal: produce a dated paper list with titles, abstracts, metadata, and method notes.

- Prefer Playwright-based scraping for alphaxiv if the environment supports it.
- Enrich papers with arXiv metadata and accessible HTML content.
- Save raw and enriched outputs under a dated folder.
- If the full-paper content is unavailable, mark entries as abstract-only rather than pretending the read was complete.

### Step 2: Filter the list

Score papers against the user's criteria:

- domain fit
- novelty potential
- feasibility under compute constraints
- clarity of remaining research gap

Output a filtered markdown file with a short rationale for each retained paper.

### Step 3: Generate proposal directions

For top papers, produce extension ideas that answer:

- what is the real gap
- why now
- what would be the method sketch
- what would be the likely reviewer attack

Keep proposal quality high. Avoid shallow “apply X to Y” variants unless the user explicitly asks for lightweight brainstorming.

### Step 4: Write paper essences

For each selected paper, write a researcher-facing essence:

- problem in one paragraph
- core method in plain language
- what actually matters experimentally
- real strengths
- real weaknesses
- concrete follow-up directions

## Output Layout

Use a dated directory structure under the chosen root. Suggested layout:

```text
<root>/
  <YYYYMMDD>/
    raw_popular_papers_<YYYYMMDD>.txt
    titles_<YYYYMMDD>.md
    filtered_<YYYYMMDD>.md
  proposals/
    <YYYY>/
      <Paper_Title>.md
  essence/
    <YYYY>/
      <MM>/
        <Paper_Title>.md
```

## Codex-Specific Notes

- Prefer local scripts and reproducible shell commands over long inline code.
- Keep the user informed of stage progress.
- If network restrictions block scraping, stop and report exactly which stage is blocked.
- If the user asks only for one stage, still preserve the same file conventions.

## References

- For example output structure and tone, see [references/example_outputs.md](references/example_outputs.md).
