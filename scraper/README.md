# TABUU Metrics Scraper

Pulls Ditto Music dashboard metrics into `../metrics.json` so the tier dashboard can read them.

## Setup (once)

```bash
pip3 install playwright
python3 -m playwright install chromium
```

## First-time login

```bash
python3 scrape_ditto.py --login
```

Browser opens. Log into Ditto manually (handles 2FA / reCAPTCHA fine — it's you logging in). Close the window when done. Session is saved to `~/.tabuu-scraper-profile/`.

## Regular runs

```bash
python3 scrape_ditto.py            # headless, fast
python3 scrape_ditto.py --headed   # visible browser, for debugging selectors
```

Writes `metrics.json` next to `index.html`.

## What's stored

- `~/.tabuu-scraper-profile/` — browser profile (cookies, localStorage). Don't share, don't commit.
- `../metrics.json` — the scraped data. Safe to read from the dashboard.

## Schedule

Add to crontab to run every morning:

```
0 8 * * * cd /Users/a1111/Downloads/tabuu-tier-evolution/scraper && /opt/homebrew/bin/python3 scrape_ditto.py
```
