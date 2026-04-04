"""
Full LinkedIn job search pipeline: Phase 1 (keywords) + Phase 2 (companies) + detail fetching.
Outputs a JSON file with all job data including full descriptions.

Usage:
    python run_search.py --location "United Kingdom" --lookback 7 --output /tmp/linkedin_jobs.json \
        --keywords "Machine Learning" "Deep Learning" "AI Engineer" \
        --companies "Google" "Microsoft" "Amazon"
"""

import argparse
import json
import sys
import time

import requests
from bs4 import BeautifulSoup

GUEST_JOBS_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

COMPANY_SUFFIXES = [
    "",                  # plain company name — catches all roles, paginated
    "software engineer",
    "machine learning",
    "AI engineer",
    "research scientist",
    "research engineer",
]


def parse_cards(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", class_="base-search-card")
    jobs = []
    for card in cards:
        title_el = card.find("h3", class_="base-search-card__title")
        company_el = card.find("h4", class_="base-search-card__subtitle")
        location_el = card.find("span", class_="job-search-card__location")
        link_el = card.find("a", class_="base-card__full-link")
        time_el = card.find("time")
        jobs.append({
            "title": title_el.get_text(strip=True) if title_el else None,
            "company": company_el.get_text(strip=True) if company_el else None,
            "location": location_el.get_text(strip=True) if location_el else None,
            "url": link_el["href"].split("?")[0] if link_el and link_el.get("href") else None,
            "posted": time_el.get("datetime", time_el.get_text(strip=True)) if time_el else None,
        })
    return jobs


def fetch_page(keywords: str, location: str, start: int = 0, time_filter: str = "r604800") -> list[dict]:
    params = {
        "keywords": keywords,
        "location": location,
        "start": start,
        "f_TPR": time_filter,
    }
    resp = requests.get(GUEST_JOBS_URL, params=params, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        return []
    return parse_cards(resp.text)


def fetch_keyword(keywords: str, location: str, time_filter: str, max_results: int = 100) -> list[dict]:
    all_jobs = []
    start = 0
    while len(all_jobs) < max_results:
        page = fetch_page(keywords, location, start, time_filter)
        if not page:
            break
        all_jobs.extend(page)
        start += 25
        if len(page) < 25:
            break
        time.sleep(1.5)
    return all_jobs[:max_results]


def fetch_job_details(job_url: str) -> dict:
    resp = requests.get(job_url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        return {}
    soup = BeautifulSoup(resp.text, "html.parser")
    details = {}
    desc_el = soup.find("div", class_="show-more-less-html__markup")
    if desc_el:
        details["description"] = desc_el.get_text(strip=True, separator="\n")
    for item in soup.find_all("li", class_="description__job-criteria-item"):
        label = item.find("h3")
        value = item.find("span")
        if label and value:
            key = label.get_text(strip=True).lower().replace(" ", "_")
            details[key] = value.get_text(strip=True)
    return details


def run(keywords: list[str], companies: list[str], location: str, lookback_days: int, output: str):
    time_filter = f"r{lookback_days * 86400}"
    seen_urls: set[str] = set()
    all_jobs: list[dict] = []

    def add_jobs(jobs: list[dict], source: str):
        new = 0
        for j in jobs:
            if j["url"] and j["url"] not in seen_urls:
                seen_urls.add(j["url"])
                j["search_source"] = source
                all_jobs.append(j)
                new += 1
        return new

    # --- Phase 1: keyword searches ---
    print("=== Phase 1: Keyword searches ===", flush=True)
    for kw in keywords:
        jobs = fetch_keyword(kw, location, time_filter)
        new = add_jobs(jobs, f"keyword:{kw}")
        print(f"  [{kw}] {len(jobs)} found, {new} new (total: {len(all_jobs)})", flush=True)
        time.sleep(1.5)

    # --- Phase 2: company-targeted searches ---
    if companies:
        print("\n=== Phase 2: Company-targeted searches ===", flush=True)
        for company in companies:
            company_new = 0
            for suffix in COMPANY_SUFFIXES:
                kw = f"{company} {suffix}".strip()
                # Paginate: fetch up to 50 results per company+suffix combo
                jobs = fetch_keyword(kw, location, time_filter, max_results=50)
                company_new += add_jobs(jobs, f"company:{company}")
                time.sleep(1.5)
            print(f"  [{company}] {company_new} new (total: {len(all_jobs)})", flush=True)

    # --- Phase 3: fetch details for every job ---
    print(f"\n=== Fetching details for {len(all_jobs)} jobs ===", flush=True)
    fetched = 0
    failed = 0
    for i, job in enumerate(all_jobs):
        if not job.get("url"):
            continue
        try:
            details = fetch_job_details(job["url"])
            if details:
                job.update(details)
                fetched += 1
            else:
                failed += 1
        except Exception:
            failed += 1
        if (i + 1) % 50 == 0:
            print(f"  Progress: {i + 1}/{len(all_jobs)} (ok: {fetched}, fail: {failed})", flush=True)
        time.sleep(1.0)

    print(f"\n=== Done: {len(all_jobs)} unique jobs, {fetched} details fetched, {failed} failed ===", flush=True)

    # --- Save ---
    with open(output, "w") as f:
        json.dump(all_jobs, f, indent=2)
    print(f"Saved to {output}")

    # --- Print compact summary for Claude to analyze ---
    print("\n=== JOB SUMMARIES ===")
    for i, j in enumerate(all_jobs):
        desc = (j.get("description") or "")[:250]
        emp = j.get("employment_type", "N/A")
        sen = j.get("seniority_level", "N/A")
        print(f"[{i}] {j['title']} | {j['company']} | {j['location']} | Seniority: {sen} | Type: {emp}")
        print(f"    URL: {j['url']}")
        print(f"    {desc}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Full LinkedIn job search pipeline")
    parser.add_argument("--keywords", nargs="+", required=True, help="Search keyword phrases")
    parser.add_argument("--companies", nargs="*", default=[], help="Target companies for Phase 2")
    parser.add_argument("--location", default="United Kingdom", help="Full country/region name")
    parser.add_argument("--lookback", type=int, default=7, help="Days to look back")
    parser.add_argument("--output", default="/tmp/linkedin_jobs.json", help="Output JSON path")
    args = parser.parse_args()

    run(args.keywords, args.companies, args.location, args.lookback, args.output)


if __name__ == "__main__":
    main()
