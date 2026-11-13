# il-jobs (MVP)

    python3 discover.py        # seed_companies.csv -> companies.json (careers URL + ATS)
    python3 run.py             # crawl, diff into data/jobs.db
    python3 digest.py          # preview digest (data/digest.html)
    python3 digest.py --commit # mark as reported (do this after the email is sent)

Adapters: Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Comeet.
Not covered yet: companies on custom career pages (see status=careers_page_only in data/companies.json).
