"""Build the digest of new, relevant jobs. `python3 digest.py` previews; `--commit` marks them reported."""

import html
import re
import sqlite3
import sys
import time
from typing import Any

from common import DROP_BELIEVED, DROP_NOTE
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


GAP_LABEL = {
    "closed": "all its jobs were closed after an empty crawl",
    "held": "crawl held, nothing closed",
    "failing": "not crawled",
}
GAP_NOTE_MAX = 160
FAILING_RUNS = 2  # a company is failing when its last two crawls failed, as in the dashboard (one-offs do not count)


def coverage_gaps(c: sqlite3.Connection) -> list[dict[str, Any]]:
    """Companies whose latest crawls need a person's attention, one dict each (company, kind, note, last_good, new).

    kind is "closed" (the crawl that believed an empty page and closed the jobs), "held" (a crawl held back as a
    sharp drop: nothing closed) or "failing" (the last two crawls failed, as in the dashboard's coverage gaps).
    `new` marks what started today: a believed close, a company's first held crawl, a company that just started
    failing. Only new gaps are worth an email of their own."""
    columns = [r[1] for r in c.execute("PRAGMA table_info(crawl_log)")]
    if not columns:
        return []
    note_col = "COALESCE(note, '')" if "note" in columns else "''"
    history: dict[str, list[tuple[int, str]]] = {}
    for company, ok, note in c.execute(f"SELECT company, ok, {note_col} FROM crawl_log ORDER BY ts, rowid"):
        history.setdefault(company, []).append((ok, note))
    last_good = dict(c.execute("SELECT company, MAX(substr(ts,1,10)) FROM crawl_log WHERE ok=1 GROUP BY company"))
    gaps: list[dict[str, Any]] = []
    for company, seq in sorted(history.items()):
        ok, note = seq[-1]
        if note.startswith(DROP_BELIEVED):
            kind, new = "closed", True
        elif not ok and note.startswith(DROP_NOTE):
            kind, new = "held", len(seq) <= 1 or not seq[-2][1].startswith(DROP_NOTE)
        elif not any(ok for ok, _ in seq[-FAILING_RUNS:]):
            kind, new = "failing", len(seq) <= FAILING_RUNS or bool(seq[-FAILING_RUNS - 1][0])
        else:
            continue
        gaps.append(
            {"company": company, "kind": kind, "note": note, "last_good": last_good.get(company, "never"), "new": new}
        )
    return gaps


def render(jobs: list[dict[str, Any]], gaps: list[dict[str, Any]] | None = None) -> tuple[str, str]:
    gaps = gaps or []
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
    if gaps:
        body += f"<h3>Not crawled properly ({len(gaps)})</h3><ul>"
        for g in gaps:
            tag = " <b>new</b>" if g["new"] else ""
            why = f": {html.escape(g['note'][:GAP_NOTE_MAX])}" if g["note"] else ""
            body += (
                f"<li><b>{html.escape(g['company'])}</b>{tag}: {GAP_LABEL[g['kind']]}{why} "
                f"<i>(last good crawl {html.escape(g['last_good'])})</i></li>"
            )
        body += "</ul>"
    new_gaps = sum(1 for g in gaps if g["new"])
    if jobs or not new_gaps:
        return f"New Israel jobs: {len(jobs)} ({today})", body
    return f"Job crawl alert: {new_gaps} new ({today})", body


def main() -> None:
    c = sqlite3.connect(DB)
    jobs = select(c)
    gaps = coverage_gaps(c)
    subject, body = render(jobs, gaps)
    with open("data/digest.html", "w") as fh:
        fh.write(body)
    print(subject)
    for j in jobs:
        print(("PM  " if j["pm"] else "    ") + f"{j['company']:18s} {j['title'][:60]:60s} {j['location'][:30]}")
    for g in gaps:
        print(f"GAP {'new' if g['new'] else '   '} {g['company']:18s} {g['kind']:8s} {g['note'][:60]}")
    if "--commit" in sys.argv:
        c.execute("UPDATE jobs SET reported=1 WHERE status='open'")
        c.commit()
        print("marked reported")


if __name__ == "__main__":
    main()
