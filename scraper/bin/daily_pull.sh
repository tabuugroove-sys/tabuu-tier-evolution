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

  # Publish anonymized public metrics to GitHub Pages dashboard.
  # Only farm_metrics_public.json is tracked; private files stay gitignored.
  if ! git diff --quiet -- farm_metrics_public.json; then
    git add farm_metrics_public.json
    git -c user.name="TABUU farm bot" -c user.email="tabuugroove@gmail.com" \
        commit -m "Auto-update public farm metrics ($(date +%Y-%m-%d))" -- farm_metrics_public.json
    if git push origin main; then
      echo "Pushed public metrics to GitHub Pages"
    else
      echo "WARN: git push failed (will retry next run)"
    fi
  else
    echo "No change in public metrics — nothing to push"
  fi

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done"
} >> "$LOG" 2>&1
