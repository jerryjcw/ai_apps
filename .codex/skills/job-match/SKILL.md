---
name: job-match
description: Search recent job postings and match them against a candidate CV, then rank and report the best roles. Use when the user wants to search jobs by keywords or company, compare jobs against a CV, filter by seniority and hard requirements, and save a ranked markdown report.
---

# Job Match

Use this skill to fetch jobs, read a CV, score fit, and write a ranked report.

## Ask For Inputs Up Front

Collect in one message unless already known:

1. Search keywords
2. Companies
3. Country or full location name
4. CV file path
5. Lookback days
6. Hard requirements
7. Soft preferences

After reading the CV, confirm acceptable seniority levels before final matching.

## Defaults

Read defaults from:

- [references/keywords.txt](references/keywords.txt)
- [references/companies.txt](references/companies.txt)
- [references/location.txt](references/location.txt)

If these are empty or missing:

- keywords: `Machine Learning`
- location: `United Kingdom`

Use full location names, not abbreviations.

## Workflow

Assume the project root is:

```text
/Users/jerry/projects/ai_apps
```

If your current working directory is elsewhere, `cd` to the project root first or use absolute paths.

### Step 1: Fetch jobs

Use the bundled script:

```bash
cd /Users/jerry/projects/ai_apps && \
source applications/jobsearch/.venv/bin/activate && python .codex/skills/job-match/scripts/run_search.py \
  --keywords "Machine Learning" \
  --companies "Google" \
  --location "United Kingdom" \
  --lookback 7 \
  --output /tmp/linkedin_jobs_YYYY-MM-DD.json
```

Do not rewrite the fetch pipeline inline unless the script is broken and you are fixing it.

### Step 2: Split into batches

Use:

```bash
cd /Users/jerry/projects/ai_apps && \
source applications/jobsearch/.venv/bin/activate && python .codex/skills/job-match/scripts/split_jobs.py \
  --input /tmp/linkedin_jobs_YYYY-MM-DD.json \
  --output-dir /tmp/job_batches_YYYY-MM-DD \
  --batch-size 50
```

### Step 3: Read and summarize the CV

Extract:

- candidate name
- current and past roles
- seniority
- skills
- domains
- education
- notable projects or publications

Then confirm which seniority levels to include.

### Step 4: Evaluate jobs

Apply these filters and scores:

- true seniority, not just the site label
- full-time permanent only unless the user says otherwise
- hard requirements are strict filters
- soft preferences influence ranking only
- role relevance to the candidate’s field

Produce for each kept job:

- title
- company
- location
- url
- assessed seniority
- compensation if known
- interest
- cv_match
- prestige
- key_skills
- job_essence
- why_fits
- soft_pref_met

## Codex-Specific Adaptation

The source Claude workflow used many parallel agents for batch scoring. In Codex:

- If the user explicitly asks for delegation or parallel processing, you may use `spawn_agent` to evaluate batches in parallel.
- Otherwise, process batches sequentially in the main thread.
- Do not assume sub-agents are always allowed.

## Final Report

Write a markdown report under:

```text
/Users/jerry/projects/ai_apps/applications/jobsearch/job_matches_<Name>_<YYYY-MM-DD>.md
```

Include:

- ranked markdown table
- search summary
- top 3 recommendations
- skill gaps seen in postings
- notable absences from the target company list

## Bundled Scripts

- [scripts/run_search.py](scripts/run_search.py)
- [scripts/split_jobs.py](scripts/split_jobs.py)
- [scripts/fetch_linkedin_jobs.py](scripts/fetch_linkedin_jobs.py)
