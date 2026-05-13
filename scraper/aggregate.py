#!/usr/bin/env python3
"""
Aggregate raw Upload-Post data into a clean farm_metrics.json
the dashboard can read.

Reads:  ../upload_post_metrics.json
Writes: ../farm_metrics.json
"""
import datetime
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
RAW_IN = ROOT / "upload_post_metrics.json"
OUT = ROOT / "farm_metrics.json"


def main():
    d = json.loads(RAW_IN.read_text())
    today = datetime.date.today()
    cutoff_7 = today - datetime.timedelta(days=7)
    cutoff_30 = today - datetime.timedelta(days=30)

    by_platform = defaultdict(lambda: {
        "profiles": 0,
        "followers": 0,
        "views_total": 0,
        "views_7d": 0,
        "views_30d": 0,
        "likes": 0,
        "comments": 0,
        "shares": 0,
        "videos": 0,
    })
    # daily views per platform (summed across all profiles)
    daily = defaultdict(lambda: defaultdict(float))  # daily[plat][YYYY-MM-DD] = views

    by_profile = []
    for username, prof in (d.get("analytics") or {}).items():
        data = prof.get("data", {})
        if not isinstance(data, dict):
            continue
        prof_summary = {"username": username, "handles": {}, "platforms": {}, "views_total": 0, "followers": 0}
        for plat, stats in data.items():
            if not isinstance(stats, dict):
                continue
            handle = (prof.get("handles") or {}).get(plat, {})
            prof_summary["handles"][plat] = handle.get("handle") if isinstance(handle, dict) else None

            by_platform[plat]["profiles"] += 1
            for src, dst in [
                ("followers", "followers"),
                ("impressions", "views_total"),
                ("likes", "likes"),
                ("comments", "comments"),
                ("shares", "shares"),
                ("video_count", "videos"),
            ]:
                v = stats.get(src, 0)
                if isinstance(v, (int, float)):
                    by_platform[plat][dst] += v

            v7 = v30 = 0
            for pt in stats.get("reach_timeseries") or []:
                try:
                    dt = datetime.date.fromisoformat(pt["date"])
                    val = pt.get("value", 0) or 0
                    daily[plat][pt["date"]] += val
                    if dt >= cutoff_7:
                        v7 += val
                    if dt >= cutoff_30:
                        v30 += val
                except Exception:
                    pass
            by_platform[plat]["views_7d"] += v7
            by_platform[plat]["views_30d"] += v30

            prof_summary["platforms"][plat] = {
                "followers": int(stats.get("followers") or 0),
                "views_total": int(stats.get("impressions") or 0),
                "views_7d": int(v7),
                "likes": int(stats.get("likes") or 0),
            }
            prof_summary["views_total"] += int(stats.get("impressions") or 0)
            prof_summary["followers"] += int(stats.get("followers") or 0)

        by_profile.append(prof_summary)

    by_profile.sort(key=lambda x: x["views_total"], reverse=True)

    # Recent post history (last 50) — show cover-trackable items
    history_items = []
    raw_hist = (d.get("history") or {}).get("history") or []
    for h in raw_hist[:50]:
        history_items.append({
            "profile": h.get("profile_username"),
            "platform": h.get("platform"),
            "title": (h.get("post_title") or "").strip()[:120],
            "caption": (h.get("post_caption") or "").strip()[:200],
            "url": h.get("post_url"),
            "at": h.get("upload_timestamp"),
            "success": h.get("success"),
        })

    totals = {
        "profiles": 25,
        "followers": sum(p["followers"] for p in by_platform.values()),
        "views_total": sum(p["views_total"] for p in by_platform.values()),
        "views_7d": sum(p["views_7d"] for p in by_platform.values()),
        "views_30d": sum(p["views_30d"] for p in by_platform.values()),
        "likes": sum(p["likes"] for p in by_platform.values()),
        "comments": sum(p["comments"] for p in by_platform.values()),
        "videos": sum(p["videos"] for p in by_platform.values()),
    }

    # Build daily timeseries per platform as sorted [date, value] arrays
    timeseries = {}
    for plat, by_date in daily.items():
        items = sorted(by_date.items())
        timeseries[plat] = [{"date": dt, "value": int(v)} for dt, v in items]

    # Merge into long-running history file (one snapshot per day per platform)
    HISTORY = ROOT / "farm_history.json"
    if HISTORY.exists():
        hist = json.loads(HISTORY.read_text())
    else:
        hist = {"timeseries": {}}
    for plat, series in timeseries.items():
        h_series = {pt["date"]: pt["value"] for pt in hist["timeseries"].get(plat, [])}
        for pt in series:
            # API window keeps overwriting same dates — take max if a higher value appears
            h_series[pt["date"]] = max(h_series.get(pt["date"], 0), pt["value"])
        hist["timeseries"][plat] = [{"date": d, "value": v} for d, v in sorted(h_series.items())]
    hist["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    HISTORY.write_text(json.dumps(hist, indent=2, ensure_ascii=False))

    out = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "account": d.get("me", {}).get("email"),
        "plan": d.get("me", {}).get("plan"),
        "totals": totals,
        "by_platform": dict(by_platform),
        "top_profiles": by_profile[:10],
        "all_profiles": by_profile,
        "recent_posts": history_items,
        "timeseries": hist["timeseries"],  # full long-running history
    }

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"[aggregate] Wrote {OUT}")
    for plat, series in hist["timeseries"].items():
        print(f"  {plat}: {len(series)} daily points")

    # ── Public, anonymized version ─────────────────────────────────────
    # What it does NOT contain: profile pseudonyms, social-media handles,
    # post URLs/captions, account email, plan name, profile count.
    # What it contains: aggregate KPIs + per-platform aggregates + daily
    # timeseries (already a sum across profiles — not reversible).
    public = {
        "updated_at": out["updated_at"],
        "is_public": True,
        "totals": {
            "followers": int(totals["followers"]),
            "views_total": int(totals["views_total"]),
            "views_7d": int(totals["views_7d"]),
            "views_30d": int(totals["views_30d"]),
            "likes": int(totals["likes"]),
            "comments": int(totals["comments"]),
            "videos": int(totals["videos"]),
        },
        "by_platform": {
            plat: {
                "followers": int(s["followers"]),
                "views_total": int(s["views_total"]),
                "views_7d": int(s["views_7d"]),
                "views_30d": int(s["views_30d"]),
                "likes": int(s["likes"]),
                "comments": int(s["comments"]),
                "videos": int(s["videos"]),
            }
            for plat, s in by_platform.items()
        },
        "timeseries": hist["timeseries"],
    }
    PUBLIC_OUT = ROOT / "farm_metrics_public.json"
    PUBLIC_OUT.write_text(json.dumps(public, indent=2, ensure_ascii=False))
    print(f"[aggregate] Wrote {PUBLIC_OUT} (anonymized for public hosting)")
    print(f"  Total: {totals['profiles']} profiles · "
          f"{totals['followers']} followers · "
          f"{totals['views_total']:,} views all-time · "
          f"{totals['views_7d']:,} views 7d")


if __name__ == "__main__":
    main()
