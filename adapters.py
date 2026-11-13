"""One adapter per ATS. fetch(slug) -> list of job dicts, or None on failure
(None means 'could not crawl'; [] means 'crawled, no jobs')."""

import json
import re
from collections.abc import Callable
from typing import Any

from common import get

HTTP_OK = 200
Job = dict[str, Any]


def _job(  # noqa: PLR0913, PLR0917
    job_id: Any, title: Any, location: Any, url: Any, team: Any = "", posted: Any = ""
) -> Job:
    return {
        "job_id": str(job_id),
        "title": (title or "").strip(),
        "location": (location or "").strip(),
        "url": url,
        "team": (team or "").strip(),
        "posted": posted or "",
    }


def greenhouse(slug: str) -> list[Job] | None:
    r = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if r is None or r.status_code != HTTP_OK:
        return None
    return [
        _job(
            j["id"],
            j["title"],
            (j.get("location") or {}).get("name"),
            j["absolute_url"],
            posted=j.get("updated_at", ""),
        )
        for j in r.json().get("jobs", [])
    ]


def lever(slug: str) -> list[Job] | None:
    host = "api.lever.co"
    if slug.startswith("eu:"):
        host, slug = "api.eu.lever.co", slug[3:]
    r = get(f"https://{host}/v0/postings/{slug}?mode=json")
    if r is None or r.status_code != HTTP_OK:
        return None
    out: list[Job] = []
    for j in r.json():
        c = j.get("categories") or {}
        out.append(
            _job(
                j["id"],
                j["text"],
                c.get("location") or ", ".join(c.get("allLocations") or []),
                j["hostedUrl"],
                team=c.get("team"),
                posted=str(j.get("createdAt", "")),
            )
        )
    return out


def ashby(slug: str) -> list[Job] | None:
    r = get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    if r is None or r.status_code != HTTP_OK:
        return None
    return [
        _job(
            j["id"], j["title"], j.get("location"), j.get("jobUrl"), team=j.get("team"), posted=j.get("publishedAt", "")
        )
        for j in r.json().get("jobs", [])
        if j.get("isListed", True)
    ]


def workable(slug: str) -> list[Job] | None:
    r = get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
    if r is None or r.status_code != HTTP_OK:
        return None
    out: list[Job] = []
    for j in r.json().get("jobs", []):
        loc = ", ".join(x for x in (j.get("city"), j.get("country")) if x)
        out.append(
            _job(
                j["shortcode"],
                j["title"],
                loc,
                j.get("url") or j.get("application_url"),
                team=j.get("department"),
                posted=j.get("published_on", ""),
            )
        )
    return out


def smartrecruiters(slug: str) -> list[Job] | None:
    out: list[Job] = []
    offset = 0
    while True:
        r = get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}")
        if r is None or r.status_code != HTTP_OK:
            return None if offset == 0 else out
        d = r.json()
        for j in d.get("content", []):
            loc = j.get("location") or {}
            out.append(
                _job(
                    j["id"],
                    j["name"],
                    ", ".join(x for x in (loc.get("city"), loc.get("country")) if x),
                    f"https://jobs.smartrecruiters.com/{slug}/{j['id']}",
                    team=(j.get("department") or {}).get("label"),
                    posted=j.get("releasedDate", ""),
                )
            )
        offset += 100
        if offset >= d.get("totalFound", 0):
            return out


def comeet(slug: str) -> list[Job] | None:
    """slug is '<name>/<uid>' taken from comeet.com/jobs/<name>/<uid>. Job data is embedded in the page."""
    r = get(f"https://www.comeet.com/jobs/{slug}")
    if r is None or r.status_code != HTTP_OK or "COMPANY_POSITIONS_DATA" not in r.text:
        return None
    m = re.search(r"COMPANY_POSITIONS_DATA\s*=\s*(\[.*?\]);", r.text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    out: list[Job] = []
    for j in data:
        loc = j.get("location") or {}
        out.append(
            _job(
                j.get("uid"),
                j.get("name"),
                ", ".join(x for x in (loc.get("city"), loc.get("country")) if x),
                j.get("url_active_page") or j.get("url_comeet_hosted_page"),
                team=j.get("department"),
                posted=j.get("time_updated", ""),
            )
        )
    return out


def greenhouse_url(url: str) -> list[Job] | None:
    """Company site proxies a Greenhouse board as JSON ({"jobs": [...]}, Greenhouse field names)."""
    r = get(url)
    if r is None or r.status_code != HTTP_OK:
        return None
    try:
        jobs = r.json().get("jobs", [])
    except ValueError:
        return None
    return [
        _job(
            j["id"],
            j["title"],
            (j.get("location") or {}).get("name"),
            j["absolute_url"],
            posted=j.get("updated_at", ""),
        )
        for j in jobs
    ]


ADAPTERS: dict[str, Callable[[str], list[Job] | None]] = {
    "greenhouse_url": greenhouse_url,
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "workable": workable,
    "smartrecruiters": smartrecruiters,
    "comeet": comeet,
}
