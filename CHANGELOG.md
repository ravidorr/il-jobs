# Changelog

All notable changes are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.2.5] - 2026-11-14

### Added

- Pin for Tower Semiconductor: its career site has no feed, but one search page lists every open position (73, 24 of them in Israel, when this was added), so the browser crawler reads that page.

### Changed

- The browser crawler recognises `?job_id=N` job links and keeps the `job_id` when it tells jobs apart, instead of treating every such link as the same job.
- Table rows split into cells on a single tab, and a row that repeats its title cell no longer fills the team with the title.

## [0.2.4] - 2026-11-14

### Added

- Pins for Silverfort and Overwolf (Comeet boards behind their own career pages) and, now that their cards parse, for Oligo Security, Freightos, Weka, Pecan AI, Lasso Security, Panorays and Komodor.

### Changed

- The browser crawler reads a job card whatever the order of its lines (location, title, type; team, title, location; title, location) instead of taking the first line as the title and the next two as the location. It drops boilerplate such as "Full-time" and "View Role", recognises locations ("TEL AVIV, ISRAEL", "Dallas, US", "REMOTE (US)", "IL"), puts a team line in `team`, and splits a location glued to the title with tabs or a middle dot.

## [0.2.3] - 2026-11-14

### Added

- Eightfold career sites: the browser crawler reads the page's own search results and presses "Next jobs" through every page, stopping when a page has no Israel job. Pinned for Nvidia, Microsoft, Qualcomm, Citi, PayPal and Applied Materials (about 530 Israel roles), all with `israel_only` to drop nearby Palestine and Jordan results.

### Fixed

- The Israel location filter recognises the three-letter country code `ISR` ("Kiryat Gat,ISR"), which Applied Materials uses.

## [0.2.2] - 2026-11-14

### Added

- Optional `israel_only` flag on an override: the crawl then keeps only jobs located in Israel and closes the rest. Set for ServiceNow, MongoDB, Datadog, Snowflake, Zscaler and Okta, whose boards held about 2,700 jobs outside Israel.

## [0.2.1] - 2026-11-14

### Fixed

- The Israel location filter no longer counts US locations that use the code `IL` for Illinois ("Chicago, IL", "US-IL-Remote"). A bare `IL` still counts as Israel for towns written "Caesarea, IL", and the dashboard and digest share the one matcher.
- The browser crawler waits until a pagination click has produced new job links, instead of a fixed 1.5 seconds, so slow pagers such as monday.com no longer stop early, and a pager that empties the list before loading the next page does not end the crawl.

## [0.2.0] - 2026-11-14

### Added

- Design system: tokens with light and dark themes, component stylesheets, and a showcase page (`design-system/index.html`).
- Logo and favicon brief for the graphic designer (`design-system/logo-brief.md`), plus a provisional mark, favicon and apple-touch icon rebuilt from the designer's concept board.
- WebMCP tools on the dashboard (`search_jobs`, `list_new_jobs`, `get_job`, `discard_job`, `restore_job`, `list_coverage_gaps`), schema.org JobPosting JSON-LD, and `data-*` hooks on each role card.

### Changed

- Dashboard redesigned as a mobile-first feed (theme-color, safe-area insets, touch-friendly states) for students and early-career readers, with a theme switch. `build_dashboard.py` inlines the design-system CSS and emits the JSON-LD.

## [0.1.1] - 2026-11-14

### Changed

- Bump Playwright from 1.63.0 to 1.65.0 in `pyproject.toml` and in the daily workflow install step.

## [0.1.0] - 2026-11-14

### Added

- Initial project scaffold.
