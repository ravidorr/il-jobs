"""Crawl all companies with a working ATS, diff against SQLite, mark new/closed."""
import json, sqlite3, time, sys
from concurrent.futures import ThreadPoolExecutor
from adapters import ADAPTERS
from browser_crawl import crawl_many, WHY

DB = "data/jobs.db"


def init():
    c = sqlite3.connect(DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS jobs(
      company TEXT, job_id TEXT, title TEXT, team TEXT, location TEXT, url TEXT, posted TEXT,
      first_seen TEXT, last_seen TEXT, status TEXT DEFAULT 'open', reported INTEGER DEFAULT 0,
      PRIMARY KEY(company, job_id));
    CREATE TABLE IF NOT EXISTS crawl_log(ts TEXT, company TEXT, ats TEXT, ok INTEGER, n_jobs INTEGER);
    """)
    return c


def crawl(co):
    jobs = ADAPTERS[co["ats"]](co["slug"])
    return co, jobs


def main():
    companies = [c for c in json.load(open("data/companies.json")) if c["status"] == "ok"]
    c = init()
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    first_run = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    api = [co for co in companies if co["ats"] != "browser"]
    br = [co for co in companies if co["ats"] == "browser"]
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(crawl, api))
    if br:
        got = crawl_many([co["slug"] for co in br])
        for co in br:
            jobs = got.get(co["slug"])
            prev = c.execute("SELECT COUNT(*) FROM jobs WHERE company=? AND status='open'", (co["name"],)).fetchone()[0]
            if jobs is not None and not jobs and prev:
                jobs = None          # page suddenly yields nothing: assume the extractor broke, do not close jobs
            results.append((co, jobs))
    failed = []
    for co, jobs in results:
        name = co["name"]
        c.execute("INSERT INTO crawl_log VALUES(?,?,?,?,?)", (now, name, co["ats"], jobs is not None, len(jobs or [])))
        if jobs is None:
            failed.append(name)      # never close jobs when the crawl failed
            continue
        seen = set()
        known = c.execute("SELECT COUNT(*) FROM jobs WHERE company=?", (name,)).fetchone()[0]
        for j in jobs:
            seen.add(j["job_id"])
            cur = c.execute("SELECT 1 FROM jobs WHERE company=? AND job_id=?", (name, j["job_id"])).fetchone()
            if cur:
                c.execute("UPDATE jobs SET last_seen=?, status='open', title=?, location=?, url=? WHERE company=? AND job_id=?",
                          (now, j["title"], j["location"], j["url"], name, j["job_id"]))
            else:
                # a company seen for the first time gets a silent baseline (reported=1), so adding companies never floods the digest
                c.execute("INSERT INTO jobs(company,job_id,title,team,location,url,posted,first_seen,last_seen,reported) VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (name, j["job_id"], j["title"], j["team"], j["location"], j["url"], j["posted"], now, now, 0 if known else 1))
        for (jid,) in c.execute("SELECT job_id FROM jobs WHERE company=? AND status='open'", (name,)).fetchall():
            if jid not in seen:
                c.execute("UPDATE jobs SET status='closed' WHERE company=? AND job_id=?", (name, jid))
    c.commit()
    n_open = c.execute("SELECT COUNT(*) FROM jobs WHERE status='open'").fetchone()[0]
    print(f"crawled {len(companies)} companies, failed {len(failed)} {failed}, open jobs {n_open}")
    for co, jobs in results:
        if co["ats"] == "browser":
            print(f"  browser {co['name']:15s} {'FAILED' if jobs is None else len(jobs)}" + (f"  <- {WHY[co['slug']]}" if co["slug"] in WHY else ""))


if __name__ == "__main__":
    main()
