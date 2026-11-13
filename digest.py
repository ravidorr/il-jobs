"""Build the digest of new, relevant jobs. `python3 digest.py` previews; `--commit` marks them reported."""

import html
import re
import sqlite3
import sys
import time
from typing import Any

from discover import ISRAEL

DB = "data/jobs.db"
# title must match one of these (product-focused + entry level + student)
ROLE = re.compile(
    r"product|\bPM\b|\bAPM\b|intern\b|internship|student|junior|\bjr\b|graduate|entry|trainee|סטודנט|מוצר", re.I
)
# drop clearly irrelevant senior or non-product matches
EXCLUDE = re.compile(
    r"sales|counsel|architect|partnerships|\b(senior|sr\.?|staff|principal|director|head|vp|lead)\b"
    r"|product (marketing|designer|design|security|support)|software (engineer|developer)",
    re.I,
)
PM_CORE = re.compile(r"product|\bPM\b|\bAPM\b|מוצר", re.I)


def select(c: sqlite3.Connection, only_unreported: bool = True) -> list[dict[str, Any]]:
    q = "SELECT company,title,team,location,url,first_seen FROM jobs WHERE status='open'"
    if only_unreported:
        q += " AND reported=0"
    out: list[dict[str, Any]] = []
    for r in c.execute(q + " ORDER BY company, title"):
        company, title, team, loc, url, _fs = r
        if not ISRAEL.search(loc or ""):
            continue
        if not ROLE.search(title) or (
            EXCLUDE.search(title) and not re.search(r"intern|student|junior|graduate", title, re.I)
        ):
            continue
        out.append(
            {
                "company": company,
                "title": title,
                "team": team,
                "location": loc,
                "url": url,
                "pm": bool(PM_CORE.search(title)),
            }
        )
    return out


def render(jobs: list[dict[str, Any]]) -> tuple[str, str]:
    today = time.strftime("%Y-%m-%d")
    pm = [j for j in jobs if j["pm"]]
    other = [j for j in jobs if not j["pm"]]

    def block(title: str, items: list[dict[str, Any]]) -> str:
        if not items:
            return ""
        h = f"<h3>{title} ({len(items)})</h3><ul>"
        for j in items:
            h += (
                f'<li><b>{html.escape(j["company"])}</b>: <a href="{html.escape(j["url"] or "")}">'
                f"{html.escape(j['title'])}</a> <i>({html.escape(j['location'] or '')})</i></li>"
            )
        return h + "</ul>"

    body = f"<h2>New Israel jobs, {today}</h2>"
    body += block("Product roles", pm) + block("Student / junior / intern (non-product titles)", other)
    if not jobs:
        body += "<p>No new matching jobs today.</p>"
    return f"New Israel jobs: {len(jobs)} ({today})", body


def main() -> None:
    c = sqlite3.connect(DB)
    jobs = select(c)
    subject, body = render(jobs)
    with open("data/digest.html", "w") as fh:
        fh.write(body)
    print(subject)
    for j in jobs:
        print(("PM  " if j["pm"] else "    ") + f"{j['company']:18s} {j['title'][:60]:60s} {j['location'][:30]}")
    if "--commit" in sys.argv:
        c.execute("UPDATE jobs SET reported=1 WHERE status='open'")
        c.commit()
        print("marked reported")


if __name__ == "__main__":
    main()
