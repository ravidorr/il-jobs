# Privacy

Last updated: 2026-11-14

## Data we collect

No personal data is collected. The pipeline reads publicly available job postings from company career pages and stores them in a local SQLite database (`data/jobs.db`). The daily digest is emailed to the repository owner's own address.

## How data is used

No personal data is collected, so none is used or sold. Job postings are used only to produce the digest and the dashboard.

## Third parties

No analytics or tracking. The pipeline makes network calls to public career pages and applicant-tracking systems it crawls, and sends the digest through Gmail SMTP using credentials stored as GitHub Actions secrets.

## Contact

Questions: open a [GitHub issue](https://github.com/ravidorr/misra/issues). For security matters, see [SECURITY.md](./SECURITY.md).
