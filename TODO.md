# TODO

- [ ] Review the Node 26 and Python 3.12 pins when a newer LTS is released
- [ ] Browser crawler: follow Eightfold pagination (Next button labelled "Next jobs") to unlock Nvidia, Microsoft, Qualcomm, Citi, PayPal and Applied Materials
- [ ] Browser crawler: parse cards that put the location or team above the title (Oligo, Weka, Overwolf, Freightos and about ten more)
- [ ] Workable rate-limits this network (429): Nuvei and Vayyar fail intermittently; CropX is waiting on the same limit (slug `cropx`)
- [ ] Add adapters for the feeds found but not readable: teamme.link (Silverfort), Overwolf and Freightos JSON feeds, JazzHR (Tower), Teamtailor
- [ ] Re-check boards that currently list no jobs: Capitolis, Torii, Hunters, Explorium
- [ ] De-duplicate Armis roles that also appear under ServiceNow
- [ ] `data/unresolved_candidates.csv` lists 165 researched companies with no usable job feed yet; revisit as adapters are added
