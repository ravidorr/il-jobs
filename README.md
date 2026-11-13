# il-jobs (MVP)

    python3 discover.py        # seed_companies.csv -> companies.json (careers URL + ATS)
    python3 run.py             # crawl, diff into data/jobs.db
    python3 digest.py          # preview digest (data/digest.html)
    python3 digest.py --commit # mark as reported (do this after the email is sent)

Adapters: Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Comeet (public hosted pages), and a generic
Playwright crawler (`browser_crawl.py`, JSON-LD or job-looking links) for custom career pages.
`data/overrides.json` pins a company to an ATS/slug or to a career page URL (`"ats": "browser"`).
`survey.py` is a dev tool that sniffs which ATS a custom career page uses.
A company seen for the first time is baselined silently, so adding companies never floods the digest.
Not covered yet: see status=careers_page_only / not_found in data/companies.json.

## Daily run (GitHub Actions)
`.github/workflows/daily.yml` runs at 04:30 UTC: crawl, email new jobs, commit `data/jobs.db`.
Repo secrets: `GMAIL_USER`, `GMAIL_APP_PASSWORD` (Gmail app password), `DIGEST_TO` (optional recipient).
Manual run: Actions tab, "daily-job-digest", Run workflow.

## Dashboard
`python3 build_dashboard.py` writes `docs/index.html` (all open jobs, filters, per-job Discard saved in the browser).
The daily workflow rebuilds and commits it. Serve it with GitHub Pages: Settings, Pages, Deploy from a branch, `main`, `/docs`.
