#!/usr/bin/env python3
"""
Fetch Upload-Post analytics via official API.

API key in Bitwarden: "TABUU Upload-Post API" (password field).
Output: ../upload_post_metrics.json

Endpoints used (from https://docs.upload-post.com/openapi.json):
  GET /uploadposts/me              — current user info
  GET /uploadposts/users           — list of social-media profiles managed
  GET /uploadposts/history         — recent uploads
  GET /analytics/{profile}         — engagement metrics per profile
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import urllib.request
import urllib.parse
import urllib.error

OUTPUT_FILE = Path(__file__).parent.parent / "upload_post_metrics.json"
BW_ITEM_NAME = "TABUU Upload-Post API"
API_BASE = "https://api.upload-post.com/api"


def load_api_key():
    """
    Priority:
      1. UPLOAD_POST_API_KEY env var (set by daily_pull.sh from Keychain)
      2. macOS Keychain directly
      3. Bitwarden CLI (fallback)
    """
    # 1) env
    if os.environ.get("UPLOAD_POST_API_KEY"):
        return os.environ["UPLOAD_POST_API_KEY"], "env"
    # 2) keychain
    import subprocess
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-a", "tabuu",
             "-s", BW_ITEM_NAME, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip(), "keychain"
    except Exception:
        pass
    # 3) bitwarden
    from secrets import get_secret
    return get_secret(BW_ITEM_NAME), "bitwarden"


def call(path, api_key, params=None):
    url = f"{API_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Apikey {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, {"_non_json": body[:500]}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"error": body[:500]}
    except Exception as e:
        return 0, {"error": str(e)}


def main():
    api_key, src = load_api_key()
    print(f"[upload-post] API key loaded from {src} (length: {len(api_key)})")

    out = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "upload-post",
        "me": None,
        "users": [],
        "history": None,
        "analytics": {},
    }

    # 1. Current account
    status, me = call("/uploadposts/me", api_key)
    print(f"[upload-post] /uploadposts/me → HTTP {status}")
    out["me"] = me

    # 2. Profiles (social accounts being managed)
    status, users = call("/uploadposts/users", api_key)
    print(f"[upload-post] /uploadposts/users → HTTP {status}")
    out["users"] = users

    # 3. History of uploads
    status, history = call("/uploadposts/history", api_key, params={"limit": 50})
    print(f"[upload-post] /uploadposts/history → HTTP {status}")
    out["history"] = history

    # 4. Analytics per profile — extract username + connected platforms from /users
    profiles = []
    if isinstance(users, dict):
        arr = users.get("profiles") or users.get("users") or users.get("data") or []
        for u in arr:
            if isinstance(u, dict) and u.get("username"):
                connected = []
                for plat, info in (u.get("social_accounts") or {}).items():
                    if info and not info.get("reauth_required"):
                        connected.append(plat)
                profiles.append({"username": u["username"], "platforms": connected, "handles": u.get("social_accounts")})

    print(f"[upload-post] {len(profiles)} profiles found")
    for p in profiles:
        if not p["platforms"]:
            continue
        # Some platforms (facebook) need page_id; skip for now.
        plats = [x for x in p["platforms"] if x not in ("facebook", "linkedin", "pinterest", "reddit")]
        if not plats:
            continue
        params = {"platforms": ",".join(plats)}
        status, analytics = call(f"/analytics/{urllib.parse.quote(p['username'])}", api_key, params=params)
        print(f"[upload-post] /analytics/{p['username']}?platforms={','.join(plats)} → HTTP {status}")
        out["analytics"][p["username"]] = {
            "platforms_requested": plats,
            "handles": p["handles"],
            "data": analytics,
        }

    OUTPUT_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"[upload-post] Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
