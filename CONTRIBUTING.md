# Contributing

## Setup

```bash
nvm install && nvm use
npm ci
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## Workflow

1. Branch from `main`.
2. Make changes. Hooks run lint on commit and the full suite on push; never bypass them.
3. Commit subjects are at least 15 characters.
4. If the PR changes `package.json`, `pyproject.toml`, or a Python module, update `CHANGELOG.md` and bump the version in `package.json` (one SemVer bump per PR).
5. Open a **draft** PR. Link an issue with `Closes #<issue>` only when the PR resolves one.

## Standards

- Strict ruff, mypy, ESLint, Stylelint, html-validate, and markdownlint must pass.
- Python test coverage must be 100% (lines and branches). It is enforced on push and in CI; never lower `fail_under` or add blanket omits.
- There is no UI; the dashboard is generated from `templates/dashboard.html`.
- See [AGENTS.md](./AGENTS.md) for the full rule list.

## Release policy

When a PR or push to `main` changes `package.json`, `pyproject.toml`, or a Python module, CI runs the release gate: the package version must increase (SemVer) and `CHANGELOG.md` must have a non-empty section for that version. PRs that only touch docs, tests, workflows, or tooling do not need a bump. Tagged releases (`vX.Y.Z`) must match `package.json` and have non-empty notes extracted from the changelog.
