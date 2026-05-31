# Royalty Monitor — how it works & how to refresh

Tracks YouTube Content ID / royalty payout health per TABUU release and
auto-drafts claim letters when a release isn't being credited or paid.

**Token cost: zero in steady state.** Detection is arithmetic (Python rules),
claims are template-filled. No LLM in the loop. An optional "polish" of a
claim is on-demand only (ask the agent), never automatic.

## Data flow

```
[browser scrape, login-only]            [deterministic, in daily cron]
 Ditto Sales  ─┐                          royalty_monitor.py
 YouTube OAC  ─┴─→ royalties_raw.json ──→  + farm_metrics.json  ──→ royalties.json ──→ royalties.html
 Artist Analytics  (SENSITIVE, gitignored)  claim_templates/*.md ──→ claims/*.md       (local only)
```

- **`royalties_raw.json`** (gitignored) — source data. `cid_status`:
  `active` = confirmed matching · `active_no_match` = service on but 0 matches
  (reference likely not delivered) · `disabled` = CID not enabled.
  `yt_matched_views` / `royalty_total`: `null` = not scraped yet, `0` = confirmed zero.
- **`royalty_monitor.py`** — pure rules in `classify()`; groups gaps → fills
  `claim_templates/` → writes `royalties.json` + `claims/`. Runs daily in the
  cron, but only recomputes from whatever `royalties_raw.json` already holds.
- **`royalties.html`** — local-only page (data is gitignored; shows nothing when
  hosted publicly). View via `python3 -m http.server` in the project root.

## Claim rules (classify)

| Condition | Status | Claim drafted |
|---|---|---|
| CID disabled | `cid_disabled` | Ditto: enable CID + deliver reference |
| CID active, **confirmed** 0 matches, farm using it | `yt_not_matching` | Ditto enable + parallel YouTube letter |
| Matches but 0 royalty past ~75d lag | `royalty_missing` | Ditto: chase missing royalty |
| Matches but 0 royalty within lag | `waiting_royalty` | — (just waiting) |
| Matches + royalty flowing | `ok_earning` | — |

## How to REFRESH the data (browser scrape)

Ditto and YouTube Artist Analytics are behind login, so this is run from a
session (not the headless cron). Ask the agent to **"refresh royalty data"**:

1. Make sure you're logged into Ditto Music and YouTube Studio in Chrome.
2. The agent scrapes, via Chrome MCP:
   - **YouTube** → `studio.youtube.com/artist/a_WFbG5pO79yh/analytics/tab-content`
     (Songs view) → per-song matched views.
   - **Ditto** → Sales / royalty report → per-ISRC streams + revenue.
3. Agent writes the figures into `royalties_raw.json` and runs
   `python3 scraper/royalty_monitor.py`.
4. Reload `royalties.html`.

CID on/off status per release comes from Ditto → Services & Extras (set the
`cid_status` field when it changes).
