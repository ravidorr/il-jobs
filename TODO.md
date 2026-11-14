# TODO

- [ ] Review the Node 26 and Python 3.12 pins when a newer LTS is released
- [ ] Fix the Israel location filter: the bare `IL` token also matches Illinois (for example "Chicago, IL"); about 5% of "Israel" matches are US jobs
- [ ] Browser crawler: follow Eightfold pagination (Next button labelled "Next jobs") to unlock Nvidia, Microsoft, Qualcomm, Citi, PayPal and Applied Materials
- [ ] Browser crawler: parse cards that put the location or team above the title (Oligo, Weka, Overwolf, Freightos and about ten more)
- [ ] Browser crawler: monday.com pagination sometimes stops early (60 of 125 jobs on one run); wait for the page to settle before the next click
- [ ] Add adapters for the feeds found but not readable: teamme.link (Silverfort), Overwolf and Freightos JSON feeds, JazzHR (Tower), Teamtailor
- [ ] Decide how to handle large multinational boards: ServiceNow, MongoDB, Datadog, Snowflake, Zscaler and Okta add about 2,700 open jobs, mostly outside Israel, which tripled the dashboard size to 2.5 MB
- [ ] `data/unresolved_candidates.csv` lists 160 researched companies with no usable job feed yet; revisit as adapters are added
