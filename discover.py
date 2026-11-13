"""Find careers_url + ATS for each seed company. Writes data/companies.json"""
import csv, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from common import get, slug_candidates
from adapters import ADAPTERS

PROBE_ORDER = ["greenhouse", "lever", "ashby", "workable", "smartrecruiters"]
ATS_LINK = [
    ("comeet", re.compile(r"comeet\.com/jobs/([A-Za-z0-9_.\-]+/[A-Z0-9.]+)", re.I)),
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_\-]+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([A-Za-z0-9_\-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.\-%]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/([A-Za-z0-9_\-]+)", re.I)),
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_\-]+)", re.I)),
]
CAREER_PATHS = ["/careers", "/jobs", "/careers/", "/company/careers", "/about/careers", "/join-us", "/careers/jobs"]


def scan_page(url):
    r = get(url)
    if r is None or r.status_code != 200:
        return None, None
    for ats, rx in ATS_LINK:
        m = rx.search(r.text)
        if m and m.group(1).lower() not in ("embed", "jobs", "careers"):
            return ats, m.group(1)
    return None, r.url


ISRAEL = re.compile(r"israel|tel[ -]?aviv|jerusalem|haifa|herzliya|ra'?anana|petah|petach|ramat|netanya|rehovot|yokneam|kfar|beer[ -]?sheva|holon|rishon|hod hasharon|airport city|\bIL\b", re.I)


def israel_count(jobs):
    return sum(1 for j in jobs if ISRAEL.search(j["location"] or ""))


OVERRIDES = json.load(open("data/overrides.json"))


def discover(row):
    name, domain = row["name"], row["domain"]
    res = dict(name=name, domain=domain, careers_url="", ats="", slug="", source="", status="unknown", n_jobs=None, n_israel=None)
    ov = OVERRIDES.get(name)
    if ov:
        res.update(ats=ov["ats"], slug=ov["slug"], source="override", careers_url=ov["slug"] if ov["ats"] == "browser" else "")
        if ov["ats"] == "browser":
            res["status"] = "ok"          # verified at crawl time
            print(f"{name:25s} ok(browser)        {ov['slug']}", flush=True)
            return res
        jobs = ADAPTERS[ov["ats"]](ov["slug"])
        res.update(status="ok" if jobs is not None else "ats_failed", n_jobs=None if jobs is None else len(jobs),
                   n_israel=None if jobs is None else israel_count(jobs))
        print(f"{name:25s} {res['status']:18s} {ov['ats']:15s} {ov['slug']:30s} {res['n_jobs']} il={res['n_israel']} src=override", flush=True)
        return res
    # 1. look at the real career pages first (most reliable, finds comeet)
    for p in ["/"] + CAREER_PATHS:
        for host in (f"https://www.{domain}", f"https://{domain}"):
            ats, val = scan_page(host + p)
            if ats:
                res.update(ats=ats, slug=val, careers_url=host + p, source="page")
                break
            if val and p != "/" and not res["careers_url"]:
                res["careers_url"] = val
        if res["ats"]:
            break
    # 2. probe ATS APIs by guessed slug
    if not res["ats"]:
        for ats in PROBE_ORDER:
            for s in slug_candidates(name, domain):
                jobs = ADAPTERS[ats](s)
                if jobs and israel_count(jobs) > 0:
                    res.update(ats=ats, slug=s, source="guess")
                    break
            if res["ats"]:
                break
    # 3. verify by actually crawling
    if res["ats"]:
        jobs = ADAPTERS[res["ats"]](res["slug"])
        if jobs is None:
            res["status"] = "ats_failed"
        else:
            res.update(status="ok", n_jobs=len(jobs), n_israel=israel_count(jobs))
    elif res["careers_url"]:
        res["status"] = "careers_page_only"
    else:
        res["status"] = "not_found"
    print(f"{name:25s} {res['status']:18s} {res['ats']:15s} {res['slug']:30s} {res['n_jobs']} il={res['n_israel']} src={res['source']}", flush=True)
    return res


if __name__ == "__main__":
    rows = list(csv.DictReader(open("data/seed_companies.csv")))
    seen, uniq = set(), []
    for r in rows:
        if r["domain"] not in seen:
            seen.add(r["domain"]); uniq.append(r)
    with ThreadPoolExecutor(8) as ex:
        out = list(ex.map(discover, uniq))
    json.dump(out, open("data/companies.json", "w"), indent=1, ensure_ascii=False)
    from collections import Counter
    print(Counter(r["status"] for r in out))
