# Changelog

All notable changes are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

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
