---
name: job-match
description: Search LinkedIn for recent job postings and match them against the user's CV. Fetches jobs by keyword, reads the CV, analyzes fit, and outputs a ranked table of matching roles to an md file.
user_invocable: true
---

# LinkedIn Job Match Skill

You are helping the user find and match recent LinkedIn job postings against their CV. Follow the steps below carefully and in order.

---

## Step 1: Collect User Inputs

Ask the user for the following information. Be concise — present all questions at once, noting the defaults. Do NOT proceed until you have confirmed all inputs.

1. **Search keywords** (default: read from `.claude/skills/job-match/keywords` file — one keyword phrase per line; if the file is empty or missing, default to `"Machine Learning"`). The user may provide a comma-separated list or just press enter to accept defaults.
2. **Companies** (default: read from `.claude/skills/job-match/companies` file — one company name per line). If the file exists and is non-empty, these companies will be used for additional targeted searches (see Step 2). The user may override with a comma-separated list.
3. **Country / Location** (default: read from `.claude/skills/job-match/location` file; if missing, default to `"United Kingdom"`). Must be a **full country or region name** (e.g. `"United Kingdom"`, `"United States"`, `"Germany"`), NOT a country code or abbreviation (e.g. do NOT use `"UK"` or `"US"`). This is passed as the `location` parameter to LinkedIn's API for all searches. If the user provides a new value, update the `location` file so it becomes the new default for future runs.
4. **CV file path** (default: look for files in `applications/jobsearch/cv/` with extensions `.pdf`, `.md`, `.txt`, `.docx`). If exactly one file is found, use it automatically. If **multiple** CV files are found, list them and ask the user to choose one. If the directory is empty or missing, ask the user for the path.
5. **Lookback days** — how many days back to search (default: `7`).
6. **Acceptable seniority levels** — collected in Step 3 after reading the CV (not now). Mention to the user that you will ask about this after analyzing their CV.
7. **Hard requirements** (optional) — non-negotiable filters. Jobs that fail ANY hard requirement will be **discarded** during matching. Examples: "remote only", "minimum 80k GBP", "visa sponsorship required", "no defence/military". This can be left blank.
8. **Soft preferences** (optional) — nice-to-have criteria that influence ranking but don't disqualify jobs. Jobs that satisfy more soft preferences rank higher. Examples: "prefer startups", "interested in robotics", "bonus if Python-heavy". This can be left blank.

Once all inputs are confirmed, summarize them back to the user and ask for a final "go ahead" before proceeding.

---

## Step 2: Fetch Jobs from LinkedIn

Run the **single pipeline script** `.claude/skills/job-match/run_search.py` which handles Phase 1 (keyword searches), Phase 2 (company-targeted searches), detail fetching, deduplication, and JSON output — all in one invocation.

**IMPORTANT**: Use the jobsearch virtual environment. Do NOT install packages globally.

```bash
source applications/jobsearch/.venv/bin/activate && python .claude/skills/job-match/run_search.py \
    --keywords "Machine Learning" "Deep Learning" ... \
    --companies "Google" "Microsoft" ... \
    --location "United Kingdom" \
    --lookback 7 \
    --output /tmp/linkedin_jobs_YYYY-MM-DD.json
```

This is a **single Bash call** with a long timeout (e.g. `timeout=600000`). The script prints progress updates and a compact job summary at the end. Do NOT write inline Python scripts or run multiple fetch commands — use this script.

**IMPORTANT**: The `location` parameter must be a **full country or region name** (e.g. `"United Kingdom"`, not `"UK"`). Do NOT embed location in keywords.

---

## Step 2.5: Split Jobs into Batches

After fetching, split the full JSON into batch files for parallel processing:

```bash
source applications/jobsearch/.venv/bin/activate && python .claude/skills/job-match/split_jobs.py \
    --input /tmp/linkedin_jobs_YYYY-MM-DD.json \
    --output-dir /tmp/job_batches_YYYY-MM-DD \
    --batch-size 50
```

This produces:
- `batch_001.json`, `batch_002.json`, ... (each containing up to 50 jobs)
- `manifest.json` (metadata: total jobs, batch count, file list)

Read the `manifest.json` to determine how many batches were created and their filenames.

---

## Step 3: Read and Understand the CV

Read the CV file. Extract and internalize:

- **Current and past roles** (titles, companies, durations)
- **Technical skills** (languages, frameworks, tools, platforms)
- **Domain expertise** (NLP, computer vision, reinforcement learning, etc.)
- **Education** (degrees, institutions, relevant coursework)
- **Publications or notable projects** (if any)
- **Seniority level** (junior, mid, senior, lead, principal, director)
- **Location preferences** (if mentioned)

Also extract the **candidate's name** from the CV — this will be used in the output filename and report header.

Do NOT output the full CV — just confirm you have read and understood it, and give a 2-3 sentence summary of the candidate's profile.

### Seniority Level Selection

After summarizing the CV, present the detected seniority level and ask the user which levels to include in the search. Available levels: `Entry`, `Mid`, `Mid-Senior`, `Senior`, `Staff`, `Principal`, `Director`, `VP`. Default to the detected level and one level below (e.g. if detected as Staff, default to `Staff + Senior`). The user may select any combination — for example, a Staff-level candidate may want to also see Mid-Senior roles. Do NOT proceed to Step 4 until the user confirms their seniority selection.

---

## Step 4: Parallel Agent Matching

Launch one Agent per batch file to filter and evaluate jobs in parallel. **All filtering and matching intelligence is in the agents** — they use full LLM reasoning to assess seniority, employment type, role fit, hard requirements, and domain relevance. There is NO rule-based pre-filter.

### Data passing strategy

Subagents **cannot write files** (they lack Bash/Write permissions). Instead, each agent must **return its results as text output** — specifically, it must print the full JSON array as its final message. The main agent then collects results from each agent's completion result.

To keep agent output focused and parseable:
- Agents must output **only** the JSON array as their final message — no preamble, no explanation, no markdown fencing around the JSON.
- Before the JSON, agents should print a one-line summary: `Batch X: Y matches out of Z jobs`
- The main agent parses each agent's result text to extract the JSON array.

### How to launch agents

For each batch file listed in `manifest.json`, launch an Agent with `subagent_type=Research` and the following prompt (fill in the placeholders):

```
You are a job matching agent. Your task is to evaluate a batch of LinkedIn job postings against a candidate's CV and return only the matching jobs.

## Candidate Profile
<paste the CV summary you created in Step 3, including: name, current role, seniority, key skills, domains, publications>

## Matching Criteria

### Seniority filter
Accepted levels: <list from Step 3, e.g. "Staff, Senior">
Use your judgment to determine each job's TRUE seniority level. Do NOT rely solely on LinkedIn's seniority field — it is often inaccurate. Instead, consider:
- The job title (e.g. "Executive Director" at a bank = Staff, "Member of Technical Staff" = Staff, "Lead" = Senior)
- The years of experience required
- The compensation level if mentioned
- The company's leveling conventions (e.g. Google L5 = Senior, L6 = Staff)
- The scope of responsibilities described
Discard jobs whose true seniority falls outside the accepted levels.

### Hard requirements
<list from Step 1, e.g. "Full-time only, no contractor, no consultant">
Use your judgment to identify contractor/consultant roles even when not explicitly labeled — e.g. "Outside IR35", consulting firms posting roles, fixed-term contracts. Discard jobs failing ANY hard requirement.

### Soft preferences
<list from Step 1, e.g. "Also match senior-level jobs">
Jobs matching more soft preferences should receive higher scores.

### Employment type
Only include full-time permanent roles. Discard: contract, part-time, freelance, internship, temporary, volunteer, apprenticeship.

### Relevance
Discard jobs that are clearly irrelevant to the candidate's field (e.g. unrelated industry, wrong discipline entirely, non-technical roles).

## Instructions
1. Read the batch file: <batch file path>
2. For EACH job in the batch, decide: MATCH or DISCARD.
3. For each MATCH, create a JSON object with these fields:
   - "title": job title
   - "company": company name
   - "location": job location
   - "url": LinkedIn URL
   - "seniority": your assessed seniority level
   - "compensation": compensation if mentioned, else "Not listed"
   - "interest": one of Excellent/Strong/Good/Fair
   - "cv_match": one of Excellent/Strong/Good/Fair
   - "prestige": one of Excellent/Strong/Good/Fair
   - "key_skills": list of 3-5 matching skills from the CV
   - "job_essence": 1-2 sentence summary of what this role actually does day-to-day
   - "why_fits": 1-2 sentence explanation of why this is a good match
   - "soft_pref_met": list of which soft preferences this job satisfies

## Output format — CRITICAL
Do NOT attempt to write files. You do not have file-write permissions.

Instead, your ENTIRE final response must be EXACTLY this format (no other text):

Batch <N>: <Y> matches out of <Z> jobs

<JSON_ARRAY>

Where <JSON_ARRAY> is the complete JSON array of match objects (or [] if no matches).
Do NOT wrap the JSON in markdown code fences. Do NOT add any explanation before or after.
This is critical because the main agent will parse your response text to extract the JSON.
```

**IMPORTANT**: Launch ALL agents in parallel (use `run_in_background=true`) — do NOT wait for one to finish before starting the next. Each agent is independent and processes its own batch file.

**IMPORTANT**: The agent prompt must include the full CV summary (not just "read the CV file") so the agent has the candidate context without needing to re-read the PDF.

---

## Step 5: Aggregate Agent Results

After all agents complete, collect results from their **completion result text** (the `result` field in each agent's task notification):

1. For each completed agent, extract the JSON array from its result text. The result text has the format:
   ```
   Batch N: Y matches out of Z jobs

   [... JSON array ...]
   ```
   Parse the JSON array from the text after the summary line. If parsing fails (e.g. the agent hit an error or the JSON is malformed), log a warning and skip that batch.
2. Combine all successfully parsed match arrays into a single list.
3. Deduplicate by URL (in case the same job appeared in multiple batches — unlikely but possible).
4. Read the `manifest.json` to get the total job count for the summary stats.

**IMPORTANT**: Do NOT try to read results from files — the agents return results in their response text, not as files. The main agent must parse the agent completion results directly.

---

## Step 6: Rank, Present Results, and Save to File

Rank the combined matches using these criteria (roughly equal weight):

| Criterion | Description |
|---|---|
| **Interest** | How interesting/exciting would this role be to an AI/ML expert? Novel problems, cutting-edge tech, impactful work score higher. |
| **CV Match** | How well does the candidate's specific background (skills, experience, seniority) fit the job requirements? |
| **Company Prestige** | Reputation and tier of the company in the AI/ML space. Top-tier labs and well-known tech companies rank higher. |
| **Skill Overlap** | Specific skills and experience from the CV that directly match the job description. |
| **Soft Preferences** | Tie-breaker: jobs satisfying more of the user's soft preferences rank higher among otherwise equal matches. |

### Output Format

Present results as a **markdown table**, grouped by company tier (most prestigious first), with the following columns:

| Company | Role | Location | Compensation | Seniority | Interest | CV Match | Prestige | Key Matching Skills | Job Essence | Why This Fits | URL |
|---|---|---|---|---|---|---|---|---|---|---|---|

- **Interest, CV Match, Prestige**: Rate each as one of: `Excellent`, `Strong`, `Good`, `Fair`
- **Compensation**: Include if mentioned in the job description; otherwise write "Not listed"
- **Key Matching Skills**: 3-5 specific skills/experiences from the CV that match
- **Job Essence**: 1-2 sentences summarizing what this role actually does day-to-day — the core work, not marketing language
- **Why This Fits**: 1-2 sentences explaining why this job is a good match for the candidate
- **URL**: The LinkedIn job posting URL, formatted as a clickable markdown link `[Link](url)`

After the table, provide:
1. A **summary** of the search: total jobs fetched, how many matched, top themes/patterns observed.
2. **Top 3 recommendations** with a brief paragraph each explaining why they stand out.
3. Any **gaps noticed** — skills that appeared frequently in job postings but are missing from the CV.
4. **Notable absences** — any companies from the companies list that had no relevant ML/AI roles posted in the search period.

### Save to File

Write the complete results to a markdown file at `applications/jobsearch/job_matches_<Name>_<YYYY-MM-DD>.md` (e.g. `job_matches_Frost_2026-03-21.md`). Use the candidate's name (or a short recognizable form of it) extracted from the CV. The report header must also include the **applicant's name** and **date of search**. This file is the primary deliverable of this skill.

---

## Important Notes

- If LinkedIn blocks requests mid-fetch, report what you have and proceed with the partial results.
- If the CV is a PDF, read it using the Read tool (which supports PDFs).
- Keep the user informed of progress throughout — this process involves many HTTP requests and may take a few minutes.
- **Hard requirements are strict**: if a job fails any hard requirement, it is excluded from results with no exceptions.
- **Soft preferences are flexible**: if a job doesn't meet a soft preference, still include it — just note the mismatch and rank it lower.
- Always use the `location` parameter for geographic filtering. Never embed location names (e.g. "UK", "US") into the keyword string — this produces unreliable results.
- When fetching large numbers of jobs, save intermediate results to a JSON file to avoid data loss from output truncation.
- The batch split + parallel agent architecture scales horizontally: doubling the jobs doubles the agents but NOT the wall-clock time (they run in parallel).
