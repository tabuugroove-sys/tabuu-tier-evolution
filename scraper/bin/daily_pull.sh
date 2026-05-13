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

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done"
} >> "$LOG" 2>&1
