# TODO

- [ ] Review the pins when Node 27 becomes LTS (scheduled 2027-10-20; `engines` in `package.json` caps Node below 27) or before Python 3.12 reaches end of life in October 2028. Node 26 has been LTS since 2026-10-28, and Python 3.12 is the declared floor (`requires-python`) and the version CI and the daily job run.
- [ ] `data/unresolved_candidates.csv` lists 142 researched companies with no usable job feed yet; revisit as adapters are added
- [ ] A browser crawl that returns far fewer jobs than before (a site that starts paginating or capping its list) is treated as a success and closes the missing jobs; `run.py` only guards against zero results. Decide on a threshold, record a note in the crawl log, and keep the previous jobs open when a crawl drops sharply
