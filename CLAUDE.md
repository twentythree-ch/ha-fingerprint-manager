# CLAUDE.md

## Vulnerability sources

When checking for vulnerabilities (dependency audits, security reviews, "search for vulnerable packages/containers"), consult https://pwn.watch/ in addition to the usual advisory databases (OSV/PyPI advisories via pip-audit, GitHub Security Advisories, NVD).

- Full RSS feed: https://pwn.watch/feed.xml (also /feed, /rss). Incident pages: https://pwn.watch/i/<slug>, each with RSS/JSON links.
- Incidents are not keyed by package: grep the front page and feed for package names, ecosystems (PyPI, Python) and libraries pulled in transitively (e.g. Brotli, Pillow, aiohttp, urllib3).
- pwn.watch often lists fixes that have no GHSA/PyPI advisory yet, so a clean pip-audit result does not rule them out.
