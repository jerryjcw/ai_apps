"""
Quick test script to fetch LinkedIn job listings via the public guest endpoint.
No login/credentials required.

Usage:
    python fetch_linkedin_jobs.py --keywords "machine learning" --location "San Francisco" --num 25
"""

import argparse
import time
import requests
from bs4 import BeautifulSoup


GUEST_JOBS_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
GUEST_JOB_DETAIL_URL = "https://www.linkedin.com/jobs/view"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch_jobs_page(keywords: str, location: str, start: int = 0) -> list[dict]:
    """Fetch a single page (up to 25 results) of LinkedIn job listings."""
    params = {
        "keywords": keywords,
        "location": location,
        "start": start,
        "trk": "guest_homepage-basic_guest_nav_menu_jobs",
    }
    resp = requests.get(GUEST_JOBS_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
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


def fetch_job_details(job_url: str) -> dict:
    """Fetch full description, requirements, and criteria from an individual job page."""
    resp = requests.get(job_url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    details = {}

    # Full description (contains requirements, responsibilities, etc.)
    desc_el = soup.find("div", class_="show-more-less-html__markup")
    if desc_el:
        details["description"] = desc_el.get_text(strip=True, separator="\n")

    # Job criteria (seniority, employment type, job function, industries)
    criteria = soup.find_all("li", class_="description__job-criteria-item")
    for item in criteria:
        label = item.find("h3")
        value = item.find("span")
        if label and value:
            key = label.get_text(strip=True).lower().replace(" ", "_")
            details[key] = value.get_text(strip=True)

    return details


def fetch_jobs(keywords: str, location: str, num: int = 25) -> list[dict]:
    """Fetch up to `num` job listings, paginating as needed."""
    all_jobs = []
    start = 0
    while len(all_jobs) < num:
        page = fetch_jobs_page(keywords, location, start=start)
        if not page:
            break
        all_jobs.extend(page)
        start += 25
        if len(page) < 25:
            break
        time.sleep(1.5)  # be polite
    return all_jobs[:num]


def main():
    parser = argparse.ArgumentParser(description="Fetch LinkedIn jobs (guest endpoint)")
    parser.add_argument("--keywords", default="software engineer", help="Job search keywords")
    parser.add_argument("--location", default="United States", help="Job location")
    parser.add_argument("--num", type=int, default=10, help="Number of jobs to fetch")
    parser.add_argument("--details", action="store_true", help="Fetch full description for each job")
    args = parser.parse_args()

    print(f"Searching LinkedIn for: '{args.keywords}' in '{args.location}'...\n")
    jobs = fetch_jobs(args.keywords, args.location, args.num)

    if not jobs:
        print("No jobs found (LinkedIn may have blocked the request).")
        return

    for i, job in enumerate(jobs, 1):
        print(f"[{i}] {job['title']}")
        print(f"    Company:  {job['company']}")
        print(f"    Location: {job['location']}")
        print(f"    Posted:   {job['posted']}")
        print(f"    URL:      {job['url']}")

        if args.details and job.get("url"):
            print("    Fetching details...")
            try:
                details = fetch_job_details(job["url"])
                job.update(details)
                for key in ("seniority_level", "employment_type", "job_function", "industries"):
                    if key in details:
                        print(f"    {key.replace('_', ' ').title()}: {details[key]}")
                if "description" in details:
                    # Show first 300 chars of description
                    desc_preview = details["description"][:300]
                    print(f"    Description: {desc_preview}...")
                time.sleep(1)  # rate limit between detail fetches
            except Exception as e:
                print(f"    (Failed to fetch details: {e})")

        print()

    print(f"Total: {len(jobs)} jobs fetched.")


if __name__ == "__main__":
    main()
