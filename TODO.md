# TODO

- [ ] Review the pins when Node 27 becomes LTS (scheduled 2027-10-20; `engines` in `package.json` caps Node below 27) or before Python 3.12 reaches end of life in October 2028. Node 26 has been LTS since 2026-10-28, and Python 3.12 is the declared floor (`requires-python`) and the version CI and the daily job run.
- [ ] `data/unresolved_candidates.csv` lists 142 researched companies with no usable job feed yet; revisit as adapters are added
- [ ] The digest email says nothing about companies that failed or were held (a held browser crawl, a blocked site): the only signals are the Actions log and the dashboard coverage gaps, which need two failed crawls in a row
- [ ] A browser crawl that returns no jobs while jobs are open is held for good: unlike a sharp drop it is never believed, so a company that really closed every role keeps them open
