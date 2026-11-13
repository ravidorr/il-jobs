"""Build docs/index.html: every open job embedded as JSON in a single self-contained page."""
import json, re, sqlite3, time
from digest import ROLE, PM_CORE, DB
from discover import ISRAEL

JUNIOR = re.compile(r"intern\b|internship|student|junior|\bjr\b|graduate|entry|trainee|סטודנט", re.I)


def reason(note):
    n = note or ""
    if re.search(r"HTTP 40[13]|blocked page|Access Denied|Just a moment", n, re.I):
        return "its site blocks automated access from GitHub's servers"
    return n[:120] or "the last crawl failed"


def main():
    c = sqlite3.connect(DB)
    # latest crawl per company, and the last time it worked
    latest = {}
    has_note = any(r[1] == "note" for r in c.execute("PRAGMA table_info(crawl_log)"))
    note_col = "COALESCE(note, '')" if has_note else "''"
    q = "SELECT company, ts, ok, " + note_col + " FROM crawl_log ORDER BY ts"
    recent = {}
    for company, ts, ok, note in c.execute(q):
        latest[company] = (ts, ok, note)
        recent.setdefault(company, []).append(ok)
    last_good = dict(c.execute("SELECT company, MAX(substr(ts,1,10)) FROM crawl_log WHERE ok=1 GROUP BY company"))
    # failing = the last two crawls both failed (one-off errors do not count)
    failing = {co: v for co, v in latest.items() if not any(recent[co][-2:])}
    companies = json.load(open("data/companies.json"))
    untracked = sorted(x["name"] for x in companies if x["status"] != "ok")
    gaps = dict(blocked=[dict(c=co, why=reason(v[2]), last=last_good.get(co, "never")) for co, v in sorted(failing.items())],
                untracked=untracked)
    first = dict(c.execute("SELECT company, MIN(substr(first_seen,1,10)) FROM jobs GROUP BY company"))
    jobs = []
    for company, job_id, title, team, loc, url, fs in c.execute(
            "SELECT company, job_id, title, team, location, url, first_seen FROM jobs WHERE status='open'"):
        f = (fs or "")[:10]
        kind = "pm" if PM_CORE.search(title) else ("junior" if JUNIOR.search(title) else "other")
        if kind == "pm" and JUNIOR.search(title):
            kind = "pm"
        jobs.append(dict(c=company, i=job_id, t=title.strip(), m=(team or "").strip(), l=(loc or "").strip()[:80],
                         u=url, f=f, k=kind, il=bool(ISRAEL.search(loc or "")),
                         n=bool(f and f > first.get(company, f)), s=company in failing))
    payload = json.dumps(dict(jobs=jobs, gaps=gaps, generated=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())),
                         ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = open("templates/dashboard.html", encoding="utf-8").read().replace("__DATA__", payload)
    open("docs/index.html", "w", encoding="utf-8").write(html)
    print(f"gaps: {[g['c'] for g in gaps['blocked']]} failing, {len(untracked)} untracked")
    print(f"dashboard: {len(jobs)} open jobs, {sum(j['il'] for j in jobs)} in Israel, {len(html)//1024} KB")


if __name__ == "__main__":
    main()
