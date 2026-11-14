"""Email a short alert that the daily workflow failed. `python3 send_alert.py <run url>`.
Standard library only, so it still works when the dependencies were never installed.
Env: GMAIL_USER, GMAIL_APP_PASSWORD, DIGEST_TO (optional, defaults to GMAIL_USER)."""

import os
import smtplib
import sys
import time
from email.message import EmailMessage


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "(no link to the run was given)"
    today = time.strftime("%Y-%m-%d")
    user, pw = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"]
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = f"Job crawl failed ({today})", user, os.environ.get("DIGEST_TO") or user
    msg.set_content(f"The daily job workflow failed on {today}, so today's digest may be missing or late.\n\n{url}\n")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(user, pw)
        s.send_message(msg)
    print(f"sent: {msg['Subject']}")


if __name__ == "__main__":
    main()
