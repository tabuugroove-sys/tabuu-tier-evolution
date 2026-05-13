#!/usr/bin/env python3
"""
TABUU metrics scraper — Ditto Music dashboard.

First run:
  python3 scrape_ditto.py --login
  → opens browser, you log into Ditto manually, then close.
  Session saved to ~/.tabuu-scraper-profile/

Regular run:
  python3 scrape_ditto.py
  → headless, reuses saved session, scrapes metrics, writes ../metrics.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE_DIR = Path.home() / ".tabuu-scraper-profile"
OUTPUT_FILE = Path(__file__).parent.parent / "metrics.json"
DITTO_METRICS_URL = "https://dashboard.dittomusic.com/trends/metrics"


def login_flow():
    """Open headed browser; user logs in manually; session saved to disk."""
    print(f"[login] Opening Ditto. Log in manually, then close the window.")
    print(f"[login] Profile dir: {PROFILE_DIR}")
    PROFILE_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()
        page.goto("https://login.dittomusic.com/")
        print("[login] Waiting for you to finish login (close window when done)...")
        try:
            page.wait_for_event("close", timeout=0)
        except KeyboardInterrupt:
            pass
        ctx.close()
    print(f"[login] Session saved. You can now run without --login.")


def scrape(headless=True):
    """Headless scrape using saved session."""
    if not PROFILE_DIR.exists():
        print("[scrape] No saved session. Run with --login first.", file=sys.stderr)
        sys.exit(1)

    metrics = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "ditto",
        "raw_text": None,
        "parsed": {},
    }

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            viewport={"width": 1400, "height": 900},
        )
        page = ctx.new_page()
        print(f"[scrape] Opening {DITTO_METRICS_URL}")
        page.goto(DITTO_METRICS_URL, wait_until="domcontentloaded", timeout=60_000)

        if "login" in page.url:
            print("[scrape] Redirected to login — session expired. Run --login again.", file=sys.stderr)
            ctx.close()
            sys.exit(2)

        page.wait_for_timeout(5_000)
        page.wait_for_load_state("networkidle", timeout=30_000)

        body_text = page.inner_text("body")
        metrics["raw_text"] = body_text

        # Best-effort: pull numbers near labels we care about.
        # Adjust selectors after first inspection.
        try:
            metrics["parsed"]["streams_total"] = page.locator("text=/Total streams/i").first.locator("xpath=..").inner_text(timeout=2000)
        except Exception:
            pass
        try:
            metrics["parsed"]["listeners"] = page.locator("text=/Listeners/i").first.locator("xpath=..").inner_text(timeout=2000)
        except Exception:
            pass

        OUTPUT_FILE.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
        print(f"[scrape] Wrote {OUTPUT_FILE}")
        ctx.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="Headed first-time login")
    ap.add_argument("--headed", action="store_true", help="Run scrape with visible browser (debug)")
    args = ap.parse_args()

    if args.login:
        login_flow()
    else:
        scrape(headless=not args.headed)
