# TODO

- [ ] Review the pins when Node 27 becomes LTS (scheduled 2027-10-20; `engines` in `package.json` caps Node below 27) or before Python 3.12 reaches end of life in October 2028. Node 26 has been LTS since 2026-10-28, and Python 3.12 is the declared floor (`requires-python`) and the version CI and the daily job run.
- [ ] `data/unresolved_candidates.csv` lists 142 researched companies with no usable job feed yet; revisit as adapters are added
- [ ] When the "Crawl and diff" step fails, the daily workflow sends no email at all, so nothing in the inbox says the crawl itself broke; GitHub's failed-run notice is the only signal
