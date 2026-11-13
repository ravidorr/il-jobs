"""One adapter per ATS. fetch(slug) -> list of job dicts, or None on failure
(None means 'could not crawl'; [] means 'crawled, no jobs')."""
import json, re, html
from common import get


def _job(job_id, title, location, url, team="", posted=""):
    return dict(job_id=str(job_id), title=(title or "").strip(), location=(location or "").strip(),
                url=url, team=(team or "").strip(), posted=posted or "")


def greenhouse(slug):
    r = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if r is None or r.status_code != 200:
        return None
    return [_job(j["id"], j["title"], (j.get("location") or {}).get("name"), j["absolute_url"],
                 posted=j.get("updated_at", "")) for j in r.json().get("jobs", [])]


def lever(slug):
    r = get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if r is None or r.status_code != 200:
        return None
    out = []
    for j in r.json():
        c = j.get("categories") or {}
        out.append(_job(j["id"], j["text"], c.get("location") or ", ".join(c.get("allLocations") or []),
                        j["hostedUrl"], team=c.get("team"), posted=str(j.get("createdAt", ""))))
    return out


def ashby(slug):
    r = get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    if r is None or r.status_code != 200:
        return None
    return [_job(j["id"], j["title"], j.get("location"), j.get("jobUrl"), team=j.get("team"),
                 posted=j.get("publishedAt", "")) for j in r.json().get("jobs", []) if j.get("isListed", True)]


def workable(slug):
    r = get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
    if r is None or r.status_code != 200:
        return None
    out = []
    for j in r.json().get("jobs", []):
        loc = ", ".join(x for x in (j.get("city"), j.get("country")) if x)
        out.append(_job(j["shortcode"], j["title"], loc, j.get("url") or j.get("application_url"),
                        team=j.get("department"), posted=j.get("published_on", "")))
    return out


def smartrecruiters(slug):
    out, offset = [], 0
    while True:
        r = get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}")
        if r is None or r.status_code != 200:
            return None if offset == 0 else out
        d = r.json()
        for j in d.get("content", []):
            loc = j.get("location") or {}
            out.append(_job(j["id"], j["name"], ", ".join(x for x in (loc.get("city"), loc.get("country")) if x),
                            f"https://jobs.smartrecruiters.com/{slug}/{j['id']}",
                            team=(j.get("department") or {}).get("label"), posted=j.get("releasedDate", "")))
        offset += 100
        if offset >= d.get("totalFound", 0):
            return out


def comeet(slug):
    """slug is '<name>/<uid>' taken from comeet.com/jobs/<name>/<uid>. Job data is embedded in the page."""
    r = get(f"https://www.comeet.com/jobs/{slug}")
    if r is None or r.status_code != 200 or "COMPANY_POSITIONS_DATA" not in r.text:
        return None
    m = re.search(r"COMPANY_POSITIONS_DATA\s*=\s*(\[.*?\]);", r.text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    out = []
    for j in data:
        loc = j.get("location") or {}
        out.append(_job(j.get("uid"), j.get("name"), ", ".join(x for x in (loc.get("city"), loc.get("country")) if x),
                        j.get("url_active_page") or j.get("url_comeet_hosted_page"),
                        team=j.get("department"), posted=j.get("time_updated", "")))
    return out


ADAPTERS = dict(greenhouse=greenhouse, lever=lever, ashby=ashby, workable=workable,
                smartrecruiters=smartrecruiters, comeet=comeet)
