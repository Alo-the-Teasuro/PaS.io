# PaS.io — Project Handoff

**As of:** July 7, 2026, 07:45 UTC  
**Status:** Live at https://alo-the-teasuro.github.io/PaS.io/ (GitHub Pages, public repo)

## What's Built

### Backend (GitHub Actions workflow)
- **Pipeline:** `scripts/fetch_data.py` runs daily at 11:17 UTC, pulls three feeds, commits JSON to `data/`.
- **Feeds:**
  - **EIA** (electricity): US national trend + per-state residential rates (¢/kWh)
  - **FRED** (commodities): trailing 3y of copper (USD/lb) and aluminum (USD/t) monthly
  - **Finnhub** (stocks): real-time quotes for 21 tickers across 7 supply-chain tiers
  - **Stooq** (history): trailing ~1 trading year of daily closes per ticker
- **Data files:** `electricity.json`, `commodities.json`, `stocks.json`, `history.json`, `meta.json`
- **Keys in GitHub Secrets:** `EIA_API_KEY`, `FINNHUB_API_KEY` (FRED needs no key; Stooq keyless)
- **Failure handling:** Each feed degrades independently; one timeout or API hiccup never crashes the run. Exit code 0 always, `meta.json` tracks which feeds actually ran live vs kept seed data.

### Frontend (single-file artifact)
- **File:** `index.html` (root; reads `data/*.json` on load)
- **Fallback:** If `data/` unreachable (preview mode), renders seed data so the page never breaks
- **Sections:**
  1. Hero + stratified stack visualization
  2. Seven supply-chain tiers with live quotes (clickable → 1-yr price chart modal)
  3. US electricity price heatmap (geographic d3 choropleth, falls back to tile grid)
  4. National electricity trend chart (with legend and axis labels)
  5. Copper & aluminum price trends (with axis labels)
  6. Inside-the-package chip cross-section (die layers color-coded, HBM tagged)
- **Design:** dark graphite base (--ink #0e1116), copper and electric-blue accents, Space Grotesk headers, IBM Plex Mono data, Inter body
- **Charts:** Chart.js (no custom code needed), all wrapped in fixed-height containers to prevent page-stretch
- **Modals:** Ticker chart opens on click, ESC/outside click to close, shows daily closes with date x-axis and USD y-axis

## Current Known State

- **Quote timestamps:** Display on the stack section intro, driven by pipeline's `updated_at`
- **History modal:** Appears when clicking a ticker; shows "No history yet — it appears after the next pipeline run" until first Stooq data arrives
- **Map fallback:** Geographic d3 map attempts to load; if it fails (no CDN or sandbox), silently switches to the abstract tile grid
- **Seed data:** All five `data/*.json` files have realistic seed values (anchor points from real 2025–2026 data), so the site looks right even before the first live run

## What's Not Done

1. **Congressional trades integration** — we planned a trades section but didn't wire it. The data is public (House Clerk + Senate efdsearch.senate.gov), structure is simple (name, ticker, date range, amount range), but it wasn't in scope.
2. **Policy catalyst tracker** — we discussed wiring CHIPS Act and state incentive announcements into the money-flow section. Doable but not built.
3. **Comparative analysis** — no "these three tickers are the picks for Q3" ranking or volatility comparison. The site displays, not recommends.
4. **Custom styling** — the palette is intentional but easily tweakable; colors live in CSS vars (--copper, --volt, --ink, etc.) at the top of `<style>`.

## Running It Locally (Claude Code)

```bash
# Clone if you don't have it
git clone https://github.com/Alo-the-Teasuro/PaS.io.git
cd PaS.io

# Test the pipeline (requires EIA_API_KEY and FINNHUB_API_KEY in env)
export EIA_API_KEY=your_key
export FINNHUB_API_KEY=your_key
python3 scripts/fetch_data.py

# Preview the site
# Option 1: spin up a simple server on port 8000
python3 -m http.server 8000
# Then open http://localhost:8000 in your browser

# Option 2: just open index.html directly
# (it'll render seed data since it can't fetch ./data/ from file://)
```

## To Deploy Changes

1. Make changes locally (push to `main` branch in your editor).
2. GitHub Pages auto-rebuilds ~1 min after you push.
3. If you change the Python pipeline, the next scheduled run (or manual Actions trigger) will use the new code.
4. To test pipeline changes locally before pushing, set the env vars and run `python3 scripts/fetch_data.py` — it reads from `./data/` in the working directory and writes back there.

## File Structure

```
PaS.io/
├── index.html              # front end (self-contained)
├── CLAUDE.md               # operating instructions
├── HANDOFF.md              # this file
├── scripts/
│   └── fetch_data.py       # pipeline fetcher
├── data/
│   ├── electricity.json    # EIA
│   ├── commodities.json    # FRED
│   ├── stocks.json         # Finnhub
│   ├── history.json        # Stooq
│   └── meta.json           # pipeline metadata
├── .github/
│   └── workflows/
│       └── update-data.yml # GitHub Actions scheduled job
├── css/                    # (empty, for future)
└── js/                     # (empty, for future)
```

## Key Design Decisions

- **Single HTML file:** no build step, no dependencies beyond Chart.js + d3 (both CDN). Deploy anywhere.
- **Static JSON, not a database:** GitHub as the data store. Commits double as versioning.
- **Graceful degradation:** missing API keys, network timeouts, missing CDN files — none crash the page.
- **Seed data in SEED constant:** matches the live schema, so the site renders even in preview mode.
- **Daily cron for pipeline:** 11:17 UTC is arbitrary; change `cron` in `.github/workflows/update-data.yml` to whatever makes sense for your timezone.

## Next Obvious Moves (If You Want Them)

1. **Congressional trade tracker:** Pull House/Senate filing XMLs, parse, display as a new section ("who's trading what on the hill").
2. **Volatility / correlation:** Add a section showing which tickers move together (suggests sector rotation).
3. **Policy news feed:** RSS/webhook integration to surface relevant announcements (CHIPS Act milestones, state permits, interconnection queue updates).
4. **Export data:** Add a "download CSV" button so users can feed the data into their own analysis.
5. **Mobile responsive tweaks:** the current design works on mobile but could use some UX refinement for small screens.
6. **Dark/light mode toggle:** CSS vars are already set up; just needs a button and localStorage.

## Questions Before You Start

- **What's the goal for the next session?** Refining the existing sections, or adding new ones (trades, policy, etc.)?
- **Do you want to keep the daily cron, or move to on-demand (manual trigger)?**
- **Any styling tweaks in mind?**
