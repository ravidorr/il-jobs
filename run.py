"""Crawl all companies with a working ATS, diff against SQLite, mark new/closed."""
import json, sqlite3, time, sys
from concurrent.futures import ThreadPoolExecutor
from adapters import ADAPTERS

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
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(crawl, companies))
    failed = []
    for co, jobs in results:
        name = co["name"]
        c.execute("INSERT INTO crawl_log VALUES(?,?,?,?,?)", (now, name, co["ats"], jobs is not None, len(jobs or [])))
        if jobs is None:
            failed.append(name)      # never close jobs when the crawl failed
            continue
        seen = set()
        for j in jobs:
            seen.add(j["job_id"])
            cur = c.execute("SELECT 1 FROM jobs WHERE company=? AND job_id=?", (name, j["job_id"])).fetchone()
            if cur:
                c.execute("UPDATE jobs SET last_seen=?, status='open', title=?, location=?, url=? WHERE company=? AND job_id=?",
                          (now, j["title"], j["location"], j["url"], name, j["job_id"]))
            else:
                # first ever run: mark everything as already reported so the baseline is not a 'new' flood
                c.execute("INSERT INTO jobs(company,job_id,title,team,location,url,posted,first_seen,last_seen,reported) VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (name, j["job_id"], j["title"], j["team"], j["location"], j["url"], j["posted"], now, now, 0))
        for (jid,) in c.execute("SELECT job_id FROM jobs WHERE company=? AND status='open'", (name,)).fetchall():
            if jid not in seen:
                c.execute("UPDATE jobs SET status='closed' WHERE company=? AND job_id=?", (name, jid))
    c.commit()
    n_open = c.execute("SELECT COUNT(*) FROM jobs WHERE status='open'").fetchone()[0]
    print(f"crawled {len(companies)} companies, failed {len(failed)} {failed}, open jobs {n_open}, first_run={first_run}")


if __name__ == "__main__":
    main()
