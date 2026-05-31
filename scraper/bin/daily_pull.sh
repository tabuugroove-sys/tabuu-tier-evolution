#!/bin/bash
# Daily TABUU farm metrics pull.
# Loads API key from macOS Keychain (no Bitwarden unlock required).
# Run by LaunchAgent ~ com.tabuu.farm-metrics.plist

set -e
LOG_DIR="$HOME/Library/Logs/tabuu-farm"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"

PROJECT_DIR="/Users/a1111/Downloads/tabuu-tier-evolution"

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting daily pull"

  # Get API key from Keychain
  KEY=$(security find-generic-password -a tabuu -s "TABUU Upload-Post API" -w 2>/dev/null)
  if [ -z "$KEY" ]; then
    echo "ERROR: no API key in Keychain (a=tabuu, s='TABUU Upload-Post API')"
    exit 1
  fi
  export UPLOAD_POST_API_KEY="$KEY"

  cd "$PROJECT_DIR"
  /opt/homebrew/bin/python3 scraper/fetch_upload_post.py
  /opt/homebrew/bin/python3 scraper/aggregate.py

  # Royalty monitor: deterministic recompute of claim drafts / statuses from
  # the last-scraped royalties_raw.json (no network, no LLM). Raw data itself
  # is refreshed out-of-band by a browser scrape (Ditto + YouTube are login-only).
  /opt/homebrew/bin/python3 scraper/royalty_monitor.py || echo "WARN: royalty_monitor failed"

  # Publish anonymized public metrics to GitHub Pages dashboard.
  # Only farm_metrics_public.json is tracked; private files stay gitignored.
  PUBLIC_FILES=""
  for f in farm_metrics_public.json royalties.json; do
    git diff --quiet -- "$f" 2>/dev/null || PUBLIC_FILES="$PUBLIC_FILES $f"
  done
  if [ -n "$PUBLIC_FILES" ]; then
    git add $PUBLIC_FILES
    if git -c user.name="TABUU farm bot" -c user.email="tabuugroove@gmail.com" \
         commit -m "Auto-update public metrics ($(date +%Y-%m-%d))" -- $PUBLIC_FILES; then
      # Reconcile with remote first so a non-fast-forward can't wedge the push.
      git pull --rebase origin main || { git rebase --abort 2>/dev/null; true; }
      if git push origin main; then
        echo "Pushed to GitHub Pages:$PUBLIC_FILES"
      else
        echo "WARN: git push failed (will retry next run)"
      fi
    else
      echo "WARN: commit failed — skipping push this run"
    fi
  else
    echo "No change in public files — nothing to push"
  fi

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done"
} >> "$LOG" 2>&1
