"""Build the digest of new, relevant jobs. `python3 digest.py` previews; `--commit` marks them reported."""
import re, sqlite3, sys, time, html, json
from discover import ISRAEL

DB = "data/jobs.db"
# title must match one of these (product-focused + entry level + student)
ROLE = re.compile(r"product|\bPM\b|\bAPM\b|intern\b|internship|student|junior|\bjr\b|graduate|entry|trainee|סטודנט|מוצר", re.I)
# drop clearly irrelevant senior or non-product matches
EXCLUDE = re.compile(r"sales|counsel|architect|partnerships|\b(senior|sr\.?|staff|principal|director|head|vp|lead)\b|product (marketing|designer|design|security|support)|software (engineer|developer)", re.I)
PM_CORE = re.compile(r"product|\bPM\b|\bAPM\b|מוצר", re.I)


def select(c, only_unreported=True):
    q = "SELECT company,title,team,location,url,first_seen FROM jobs WHERE status='open'"
    if only_unreported:
        q += " AND reported=0"
    out = []
    for r in c.execute(q + " ORDER BY company, title"):
        company, title, team, loc, url, fs = r
        if not ISRAEL.search(loc or ""):
            continue
        if not ROLE.search(title) or (EXCLUDE.search(title) and not re.search(r"intern|student|junior|graduate", title, re.I)):
            continue
        out.append(dict(company=company, title=title, team=team, location=loc, url=url, pm=bool(PM_CORE.search(title))))
    return out


def render(jobs):
    today = time.strftime("%Y-%m-%d")
    pm = [j for j in jobs if j["pm"]]
    other = [j for j in jobs if not j["pm"]]

    def block(title, items):
        if not items:
            return ""
        h = f"<h3>{title} ({len(items)})</h3><ul>"
        for j in items:
            h += f'<li><b>{html.escape(j["company"])}</b>: <a href="{html.escape(j["url"] or "")}">{html.escape(j["title"])}</a> <i>({html.escape(j["location"] or "")})</i></li>'
        return h + "</ul>"
    body = f"<h2>New Israel jobs, {today}</h2>"
    body += block("Product roles", pm) + block("Student / junior / intern (non-product titles)", other)
    if not jobs:
        body += "<p>No new matching jobs today.</p>"
    return f"New Israel jobs: {len(jobs)} ({today})", body


if __name__ == "__main__":
    c = sqlite3.connect(DB)
    jobs = select(c)
    subject, body = render(jobs)
    open("data/digest.html", "w").write(body)
    print(subject)
    for j in jobs:
        print(("PM  " if j["pm"] else "    ") + f'{j["company"]:18s} {j["title"][:60]:60s} {j["location"][:30]}')
    if "--commit" in sys.argv:
        c.execute("UPDATE jobs SET reported=1 WHERE status='open'")
        c.commit()
        print("marked reported")
