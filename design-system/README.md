# Design System

misra has no user interface, so there are no tokens or components to maintain.

## Status

No UI. This directory exists so the project always has a `/design-system` entry point.

## If UI is added later

1. Replace this README with the contents of the standard design system: `tokens.css`, `components/`, `index.html`, and `showcase.css`.
2. Keep it plain HTML and CSS (no Storybook): components live under `components/` with a usage example and are shown on `index.html`.
3. Enforce tokens with Stylelint (no hard-coded colors outside `tokens.css`).
4. Update `AGENTS.md` and `CHANGELOG.md`.
