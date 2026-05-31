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

    # Snapshot the raw per-platform figures from THIS pull *before* we override
    # them with history-based values — kept for the provenance / cross-check
    # block so anyone can see the published number next to its raw source.
    current_pull = {
        plat: {
            "reach_30d_this_pull_raw": int(s.get("views_30d", 0)),
            "api_impressions_field_raw": int(s.get("views_total", 0)),
        }
        for plat, s in by_platform.items()
    }

    # ── Reach windows recomputed from accumulated daily history ──────────
    # Source of truth = farm_history.json (max value per date, every day since
    # tracking began). This guarantees 7d <= 30d <= total and that "total"
    # only ever grows. The raw API `impressions` field is a rolling ~30-day
    # window and must NOT be summed and labelled "all-time" (that produced the
    # bug where all-time < 30d and the number shrank daily).
    tracking_starts = []
    for plat, series in hist["timeseries"].items():
        if series:
            tracking_starts.append(series[0]["date"])
        s7 = s30 = sall = 0
        for pt in series:
            dt = datetime.date.fromisoformat(pt["date"])
            v = pt["value"]
            sall += v
            if dt >= cutoff_30:
                s30 += v
            if dt >= cutoff_7:
                s7 += v
        by_platform[plat]["views_7d"] = int(s7)
        by_platform[plat]["views_30d"] = int(s30)
        by_platform[plat]["views_total"] = int(sall)
    tracking_since = min(tracking_starts) if tracking_starts else None

    # Guard: a platform with profiles but no daily history must not keep a
    # stale impressions-based number (that would silently re-mix metrics and
    # could break the invariant below).
    history_plats = set(hist["timeseries"].keys())
    for plat in by_platform:
        if plat not in history_plats:
            by_platform[plat]["views_7d"] = 0
            by_platform[plat]["views_30d"] = 0
            by_platform[plat]["views_total"] = 0

    # Rebuild reach figures in totals from the corrected per-platform values.
    totals["views_7d"] = sum(p["views_7d"] for p in by_platform.values())
    totals["views_30d"] = sum(p["views_30d"] for p in by_platform.values())
    totals["views_total"] = sum(p["views_total"] for p in by_platform.values())
    totals["tracking_since"] = tracking_since

    # Hard invariant tripwire — refuse to publish numbers that cannot be true.
    # (7d window ⊆ 30d window ⊆ all dates, and every reach value is >= 0.)
    if not (totals["views_7d"] <= totals["views_30d"] <= totals["views_total"]):
        raise RuntimeError(
            "Reach invariant violated — refusing to publish: "
            f"7d={totals['views_7d']:,} 30d={totals['views_30d']:,} "
            f"total={totals['views_total']:,}"
        )

    # ── Provenance / proof block (non-sensitive — shipped in the public JSON) ──
    provenance = {
        "source": "Upload-Post API (api.upload-post.com)",
        "cross_check_dashboard": "https://app.upload-post.com",
        "endpoints": [
            "GET /uploadposts/users",
            "GET /analytics/{profile}?platforms=tiktok,instagram,youtube",
            "GET /uploadposts/history",
        ],
        "raw_pulled_at": d.get("scraped_at"),
        "pull_schedule": "daily 08:00 (LaunchAgent com.tabuu.farm-metrics)",
        "tracking_since": tracking_since,
        "method": {
            "reach_daily": "per-platform daily reach = sum across all profiles of the API reach_timeseries value for that date",
            "history": "farm_history.json keeps the MAX value ever seen per (platform, date) across all daily pulls, so the API's rolling 30d window cannot erase older days",
            "reach_7d": "sum of daily reach for dates >= today-7",
            "reach_30d": "sum of daily reach for dates >= today-30",
            "reach_total": "sum of all daily reach since tracking_since",
            "followers_likes_comments": "current snapshot from the API analytics window (not cumulative)",
        },
        "invariant": "reach_7d <= reach_30d <= reach_total — checked every run; the build fails if violated",
        "invariant_passed": True,
    }
    verification = {
        "note": "published reach (history-based) shown next to the raw single-pull values it is derived from, per platform",
        "per_platform": {
            plat: {
                "reach_7d_published": by_platform[plat]["views_7d"],
                "reach_30d_published": by_platform[plat]["views_30d"],
                "reach_total_published": by_platform[plat]["views_total"],
                "reach_30d_this_pull_raw": current_pull.get(plat, {}).get("reach_30d_this_pull_raw"),
                "api_impressions_field_raw": current_pull.get(plat, {}).get("api_impressions_field_raw"),
            }
            for plat in by_platform
        },
    }

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
        "provenance": provenance,
        "verification": verification,
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
            "tracking_since": totals.get("tracking_since"),
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
        "provenance": provenance,
        "verification": verification,
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
