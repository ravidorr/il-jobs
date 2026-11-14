"""Send the digest of new jobs via Gmail SMTP, then mark them reported.
Env: GMAIL_USER, GMAIL_APP_PASSWORD, DIGEST_TO (optional, defaults to GMAIL_USER).
`--dry-run` prints what would be sent and changes nothing."""

import os
import smtplib
import sqlite3
import sys
from email.message import EmailMessage

from digest import DB, mark_alerted, render, safe_coverage_gaps, select


def send(dry: bool) -> str:
    """Send the digest; returns the error text when the coverage check failed (the jobs go out regardless)."""
    c = sqlite3.connect(DB)
    jobs = select(c)
    gaps, gap_error = safe_coverage_gaps(c)
    if not jobs and not any(g["new"] for g in gaps):  # a gap already in an earlier email is not news
        print("no new matching jobs or new coverage gaps, nothing sent")
        return gap_error
    subject, body = render(jobs, gaps, gap_error)
    if dry:
        print(f"[dry-run] would send: {subject}")
        return gap_error
    user, pw = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"]
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, os.environ.get("DIGEST_TO") or user
    msg.set_content("Open this email in an HTML-capable client.")
    msg.add_alternative(body, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(user, pw)
        s.send_message(msg)
    # only after a successful send: jobs are reported and gaps are alerted, so a failed send tries them again
    c.execute("UPDATE jobs SET reported=1 WHERE status='open'")
    mark_alerted(c, gaps)
    c.commit()
    print(f"sent: {subject}")
    return gap_error


def main() -> None:
    if send("--dry-run" in sys.argv):
        sys.exit(1)  # the step goes red so a broken coverage check is noticed, after the jobs were sent


if __name__ == "__main__":
    main()
