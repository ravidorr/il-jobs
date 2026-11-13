"""Send the digest of new jobs via Gmail SMTP, then mark them reported.
Env: GMAIL_USER, GMAIL_APP_PASSWORD, DIGEST_TO (optional, defaults to GMAIL_USER).
`--dry-run` prints what would be sent and changes nothing."""

import os
import smtplib
import sqlite3
import sys
from email.message import EmailMessage

from digest import DB, render, select


def main() -> None:
    dry = "--dry-run" in sys.argv
    c = sqlite3.connect(DB)
    jobs = select(c)
    if not jobs:
        print("no new matching jobs, nothing sent")
        return
    subject, body = render(jobs)
    if dry:
        print(f"[dry-run] would send: {subject}")
        return
    user, pw = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"]
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, os.environ.get("DIGEST_TO") or user
    msg.set_content("Open this email in an HTML-capable client.")
    msg.add_alternative(body, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(user, pw)
        s.send_message(msg)
    # only after a successful send
    c.execute("UPDATE jobs SET reported=1 WHERE status='open'")
    c.commit()
    print(f"sent: {subject}")


if __name__ == "__main__":
    main()
