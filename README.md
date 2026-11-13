# il-jobs (MVP)

    python3 discover.py        # seed_companies.csv -> companies.json (careers URL + ATS)
    python3 run.py             # crawl, diff into data/jobs.db
    python3 digest.py          # preview digest (data/digest.html)
    python3 digest.py --commit # mark as reported (do this after the email is sent)

Adapters: Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Comeet.
Not covered yet: companies on custom career pages (see status=careers_page_only in data/companies.json).

## Daily run (GitHub Actions)
`.github/workflows/daily.yml` runs at 04:30 UTC: crawl, email new jobs, commit `data/jobs.db`.
Repo secrets: `GMAIL_USER`, `GMAIL_APP_PASSWORD` (Gmail app password), `DIGEST_TO` (optional recipient).
Manual run: Actions tab, "daily-job-digest", Run workflow.
