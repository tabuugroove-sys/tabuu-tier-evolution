#!/usr/bin/env python3
"""
Royalty monitor + claim drafter — fully DETERMINISTIC (no LLM in the loop).

Reads:
  ../royalties_raw.json   — scraped/seeded source data (SENSITIVE, gitignored)
  ../farm_metrics.json    — farm output (optional; "is the farm active" signal)
  claim_templates/*.md    — boilerplate claim letters with {{placeholders}}

Writes:
  ../royalties.json       — what royalties.html renders (SENSITIVE, gitignored)
  ../claims/<slug>.md      — ready-to-send claim drafts (SENSITIVE, gitignored)

Token cost: zero. Claims are template-filled, discrepancies are arithmetic.
An optional LLM "polish" step lives ONLY behind a manual button in the page.
"""
import datetime
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
RAW_IN = ROOT / "royalties_raw.json"
OUT = ROOT / "royalties.json"
FARM = ROOT / "farm_metrics.json"
TEMPLATES = Path(__file__).parent / "claim_templates"
CLAIMS_OUT = ROOT / "claims"

# Ditto's royalty reports lag ~2 months. Past this, a missing royalty for a
# track that HAS matched views is a real problem, not just reporting delay.
ROYALTY_LAG_DAYS = 75


def classify(rel, farm_active):
    """Return (status, claim_type) for one release. Pure rules, no LLM.

    yt_matched_views / royalty_total may be None (= not scraped yet) which is
    treated differently from an explicit 0 (= confirmed zero → a real gap).
    """
    cid = rel.get("cid_status", "unknown")          # active | active_no_match | disabled | unknown
    yt = rel.get("yt_matched_views")                 # None = unknown, int = known
    royalty = rel.get("royalty_total")               # None = unknown, number = known
    farm_used = rel.get("farm_used", farm_active)    # is the farm posting this track
    days = rel.get("days_since_first_match") or 0

    # 1) CID switched off entirely → ask Ditto to enable + deliver reference.
    if cid == "disabled":
        return "cid_disabled", "ditto_enable_cid"

    # 2) CID confirmed active but per-track detail not scraped yet → earning.
    if cid == "active" and yt is None:
        return "ok_earning", None

    # 3) CID "active" but a CONFIRMED zero matches while the farm pushes it →
    #    the audio reference never reached YouTube CMS (or YT isn't attributing).
    if cid in ("active", "active_no_match") and yt == 0 and farm_used:
        return "yt_not_matching", "ditto_enable_cid"

    # 4) Matches exist but no royalty long past the reporting lag → chase Ditto.
    if (yt or 0) > 0 and (royalty or 0) == 0 and days > ROYALTY_LAG_DAYS:
        return "royalty_missing", "ditto_royalty_missing"

    # 5) Matches exist, royalty not in yet but still inside the lag → just wait.
    if (yt or 0) > 0 and (royalty or 0) == 0:
        return "waiting_royalty", None

    # 6) Everything flowing.
    if (yt or 0) > 0 and (royalty or 0) > 0:
        return "ok_earning", None

    return "no_usage", None


def fill_template(name, ctx):
    """Render claim_templates/<name>.md with {{key}} / {{#each list}} blocks."""
    path = TEMPLATES / f"{name}.md"
    if not path.exists():
        return None
    text = path.read_text()

    # {{#each rows}}...{{title}}...{{/each}} → repeated per row
    def each(m):
        block = m.group(2)
        rows = ctx.get(m.group(1), [])
        out = []
        for r in rows:
            chunk = block
            for k, v in r.items():
                chunk = chunk.replace("{{" + k + "}}", str(v))
            out.append(chunk)
        return "".join(out)

    text = re.sub(r"\{\{#each (\w+)\}\}(.*?)\{\{/each\}\}", each, text, flags=re.DOTALL)
    for k, v in ctx.items():
        if not isinstance(v, list):
            text = text.replace("{{" + k + "}}", str(v))
    return text


# One trigger can produce several letters (e.g. a Ditto ticket + a parallel
# YouTube pressure letter for the same set of releases).
CLAIM_TEMPLATES = {
    "ditto_enable_cid": ["ditto_enable_cid", "youtube_attribution"],
    "ditto_royalty_missing": ["ditto_royalty_missing"],
}


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main():
    if not RAW_IN.exists():
        print(f"[royalty] No {RAW_IN.name} yet — scrape Ditto/YouTube first. Writing empty shell.")
        raw = {"scraped_at": None, "releases": [], "totals": {}, "sources": {}}
    else:
        raw = json.loads(RAW_IN.read_text())

    farm_active = False
    if FARM.exists():
        try:
            ft = json.loads(FARM.read_text()).get("totals", {})
            farm_active = (ft.get("views_7d") or 0) > 0
        except Exception:
            pass

    releases = raw.get("releases", [])
    for rel in releases:
        st, claim = classify(rel, farm_active)
        rel["status"] = st
        rel["claim_type"] = claim

    # ── Group flagged releases by claim type and draft one letter each ──
    groups = {}
    for rel in releases:
        if rel.get("claim_type"):
            groups.setdefault(rel["claim_type"], []).append(rel)

    CLAIMS_OUT.mkdir(exist_ok=True)
    drafted = []
    for claim_type, rels in groups.items():
        rows = [{
            "title": r.get("title", "?"),
            "isrc": r.get("isrc") or "—",
            "streams": r.get("streams_other") or 0,
            "yt_matched_views": r.get("yt_matched_views") or 0,
        } for r in rels]
        ctx = {
            "date": str(datetime.date.today()),
            "count": len(rels),
            "channel_id": raw.get("sources", {}).get("youtube_channel_id", ""),
            "artist_id": raw.get("sources", {}).get("youtube_artist_id", ""),
            "ditto_account": raw.get("sources", {}).get("ditto_account", ""),
            "rows": rows,
        }
        for tmpl in CLAIM_TEMPLATES.get(claim_type, [claim_type]):
            body = fill_template(tmpl, ctx)
            if not body:
                continue
            slug = slugify(tmpl)
            (CLAIMS_OUT / f"{slug}.md").write_text(body)
            drafted.append({
                "claim_type": claim_type,
                "template": tmpl,
                "slug": slug,
                "target": "ditto" if tmpl.startswith("ditto") else "youtube",
                "releases": [r.get("title") for r in rels],
                "count": len(rels),
                "body": body,
            })

    # ── Status roll-up for the page ──
    by_status = {}
    for rel in releases:
        by_status[rel["status"]] = by_status.get(rel["status"], 0) + 1

    totals = raw.get("totals", {})
    out = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scraped_at": raw.get("scraped_at"),
        "is_stale": raw.get("scraped_at") is None,
        "currency": totals.get("currency", "BRL"),
        "totals": totals,
        "by_status": by_status,
        "releases": releases,
        "claims": drafted,
        "sources": raw.get("sources", {}),
        "royalty_periods": raw.get("royalty_periods", []),
        "method": {
            "royalty_lag_days": ROYALTY_LAG_DAYS,
            "rules": "deterministic; see classify() in royalty_monitor.py",
            "no_llm": True,
        },
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"[royalty] Wrote {OUT}")
    print(f"  releases={len(releases)}  by_status={by_status}")
    print(f"  claims drafted: {[d['claim_type'] + ' (' + str(d['count']) + ')' for d in drafted]}")


if __name__ == "__main__":
    main()
