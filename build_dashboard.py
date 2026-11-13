"""Build docs/index.html: every open job embedded as JSON in a single self-contained page."""
import json, re, sqlite3, time
from digest import ROLE, PM_CORE, DB
from discover import ISRAEL

JUNIOR = re.compile(r"intern\b|internship|student|junior|\bjr\b|graduate|entry|trainee|סטודנט", re.I)


def main():
    c = sqlite3.connect(DB)
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
                         n=bool(f and f > first.get(company, f))))
    payload = json.dumps(dict(jobs=jobs, generated=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())),
                         ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = open("templates/dashboard.html", encoding="utf-8").read().replace("__DATA__", payload)
    open("docs/index.html", "w", encoding="utf-8").write(html)
    print(f"dashboard: {len(jobs)} open jobs, {sum(j['il'] for j in jobs)} in Israel, {len(html)//1024} KB")


if __name__ == "__main__":
    main()
