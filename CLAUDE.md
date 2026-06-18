# SaveSpots — Chicago Opioid Overdose Data Exploration

## What SaveSpots is
SaveSpots.org runs a **supplementary harm-reduction model**: instead of (only) traditional
outreach (encampments, drives, hand-to-hand distribution), we place **boxes of naloxone +
fentanyl test strips inside everyday local businesses and community spaces** — barbershops,
liquor stores, gas stations, libraries, community centers — concentrated in neighborhoods
with high opioid-overdose burden.

## The mission of this repo
Build the **data backbone** that tells SaveSpots (and partner initiatives) **where the need
is greatest and where existing naloxone coverage is thinnest** — culminating in a
**live-updating map of Chicago opioid-overdose deaths** that informs placement decisions.

This repo is a **prototype / research sandbox**. Finished tooling will later be **ported to
the SaveSpots.org website repo**, where it must look modern and professional. Here, prioritize
correctness and insight over polish.

## Decisions already made (do not re-litigate)
- **Geographic scope:** **Chicago-first, suburbs-ready.** Build for the 77 Chicago community
  areas now; structure data/code so suburban Cook County can be layered in later. (Note the
  tension: death hotspots are in the *city* — Austin, Humboldt Park, Garfield Park — while the
  *existing* naloxone-box list is almost entirely *suburban* — Cicero, Maywood, Bellwood. The
  coverage gap is itself a finding.)
- **Data posture:** Public sources for now. The user may supply additional/non-public data
  later (coroner, hospital, EMS — TBD). Don't block on it.
- **Agency:** The agent drives the roadmap. You may scour the web for data, hit public APIs,
  and **request the user upload specific data** when it would unblock high-value work.

## The "old data" reframe (important)
The user's premise was that Chicago overdose data is stale. **The raw feed is not stale** — the
Cook County Medical Examiner Case Archive **updates daily** and is **pre-geocoded**. What *is*
stale is the **published dashboards/indicators** (CDPH community-area numbers are 2023; IDPH/CDC
dashboards lag 1–2 years). So: **derive fresh numbers from the ME archive directly** rather than
relying on published summaries.

---

## PRIMARY LIVE DATA SOURCE — Cook County Medical Examiner Case Archive
- **Portal:** https://datacatalog.cookcountyil.gov/Health-Human-Services/Medical-Examiner-Case-Archive/cjeq-bs86
- **Socrata SODA API (JSON):** `https://datacatalog.cookcountyil.gov/resource/cjeq-bs86.json`
- **Coverage:** Aug 2014 → present, **updated daily**. Includes all manner-of-death cases in
  Cook County (not just overdoses).
- **Live opioid count:** ~15,500 opioid-related deaths (15,524 as of 2026-06-17).

### API field names (differ from the CSV export headers!)
| Purpose | **API field** (`.json`) | CSV export header |
|---|---|---|
| Opioid flag | **`opioids`** (boolean) | `Opioid Related` |
| Case id | `casenumber` | `Case Number` |
| Death date | `death_date` | `Date of Death` |
| Incident date | `incident_date` | `Date of Incident` |
| Cause | `primarycause`, `primarycause_linea/b/c`, `secondarycause` | `Primary Cause`, ... |
| Geo | `latitude`, `longitude`, `location` | `latitude`, `longitude` |
| Chicago area | `chi_commarea`, `chi_ward` | `Chicago Community Area`, `Chicago Ward` |
| Place | `incident_street`, `incident_city`, `incident_zip` | `Incident Address`, ... |
| Demographics | `age`, `gender`, `race`, `latino` | same |
| Other flags | `gunrelated`, `cold_related`, `heat_related`, `covid_related` | same |

**Filter opioid deaths:** `?opioids=true`
**Example (latest, geocoded, Chicago):**
`...cjeq-bs86.json?opioids=true&$where=chi_commarea IS NOT NULL&$order=death_date DESC&$limit=50`

### Gotchas (read before trusting numbers)
- **Reporting lag:** recent months undercount — cases stay open pending toxicology. The
  2024–2026 decline is **partly real, partly lag**. Caveat any "latest year" total.
- **Recent records are often un-geocoded** (lat/long/`chi_commarea` null until processed).
  ~93% of historical opioid records have coordinates; brand-new ones may not.
- **City vs suburb:** `chi_commarea` is **null for suburban Cook** records. Chicago-scope =
  `chi_commarea IS NOT NULL` (~10.4k of 15.5k opioid deaths).
- **Socrata omits null fields** in JSON responses — don't assume a key is present per record.
- Default API page size is 1000; paginate with `$limit`/`$offset` or use `$$app_token` for
  higher throughput on big pulls.

---

## Repo data inventory
| File | What it is | Use / state |
|---|---|---|
| `Medical examiner data.csv` | ME Case Archive snapshot, 96,245 rows, 2014→May 2026; 15,455 opioid; 14,319 geocoded | Offline copy of the live API. Prefer the **live API**; keep this as a fallback/snapshot. |
| `Boundaries_-_Community_Areas_20260516.csv` | 77 Chicago community-area polygons (`the_geom` WKT) | Choropleth base layer. Join key = community-area name / number. |
| `Opioid Related mortality.csv` | CDPH indicator: opioid mortality **2023** by community area | Lagging published numbers. Reference only. |
| `Opioid-related overdoses.csv` | CDPH: EMS overdose responses **2023** (NEMSIS) | Non-fatal signal, lagging. |
| `Opioid-related ED Visits.csv` / `...(age adjusted).csv` | CDPH: opioid ED visits **2024** (IDPH hospital discharge) | Non-fatal signal, lagging. |
| `DOSE_dx_Dashboard_03232026.xlsx` | CDC DOSE syndromic ED-visit dashboard export | Non-fatal trend context. |
| `County Mortality _ Morbidity - *.csv` | IDPH dashboard exports (Cook County by cause/age/sex/year) | **UTF-16, garbled, tab-delimited** — re-export or parse carefully before use. |
| `places w naloxone according to cook count.txt` | Existing Cook County naloxone-box locations (mostly **suburban**) | **Needs geocoding** → this is the "supply" side of the coverage-gap analysis. |
| Research PDFs | incl. `ooaf140.pdf` (JAMIA "Mapping the overdose crisis" — maps this exact ME data), geoPIPE pipeline paper, Cook County 2020 opioid report, SUDORS fact sheet | Methods & prior art. Read before reinventing. |
| `Screenshot ...png` | UI/dashboard references | Context. |

---

## Built so far (how to run)
- **`scripts/pull_opioid_data.py`** — Phase 0 ETL. Pulls live opioid records, dedupes, writes:
  - `data/raw/opioid_me_<date>.json` — raw snapshot
  - `data/clean/opioid_deaths_cookcounty.csv` — all Cook (cols incl. `scope`, `geocoded`, `death_year`)
  - `data/clean/opioid_deaths_chicago.geojson` — 10,469 mappable Chicago points
  - `data/clean/deaths_by_community_area.csv` — totals + 2023–25 recency by area
- **`scripts/build_coverage_gap.py`** — deaths÷naloxone per community area → `coverage_gap.json`.
- **`scripts/build_cdc_context.py`** — CDC VSRR provisional (Cook, monthly, `% pending` lag
  correction) → `cdc_vsrr.json`; CDC census-tract Drug_OD rates joined to Chicago tracts →
  `tract_overdose.geojson`.
- **`scripts/analyze_supply_temporal.py`** — from live ME API: `reachability.json` (57.7% die in
  home ZIP → supports take-home), `supply_composition.json` (xylazine/nitazene/carfentanil trend
  → box-contents rec), `temporal.json` (hour/dow/month).
- **`scripts/build_builtenv_index.py`** — LIVE blight surface from 311 vacant/abandoned buildings
  + graffiti (no Google) → `builtenv_index.json` (grid + hotspots + per-CA blight score).
- **`scripts/build_placement_candidates.py`** — ranked in-business candidates by **reach × need**
  (take-home model) → `placement_candidates.geojson`/`.csv` (deduped to 1 per block).
- **`scripts/streetview_fetch.py`** — OPTIONAL: downloads Street View imagery (needs
  `GOOGLE_MAPS_API_KEY`); Claude Code then scores them → `streetview_analysis/batch_gap_analysis.json`.
- **`map/index.html`** — Leaflet dashboard: death heat/points, CDC tract OD-rate choropleth,
  blight hotspots, existing naloxone, ranked candidates; tabs Overview/Placement/Environment/
  Insights; lag-aware trend; shows `last_updated`. Run: `bash scripts/serve.sh` → http://localhost:8000/map/
- **`scripts/refresh.sh`** — daily live pipeline (re-pulls all live sources, regenerates layers,
  stamps `last_updated.json`). `scripts/run_all.sh` = full rebuild incl. naloxone geocode.
- **`.github/workflows/refresh.yml`** — daily GitHub Action running `refresh.sh` (the
  self-updating "constant heatmap"; no secrets — all sources public).

## Roadmap
0. ✅ **Live ETL foundation** — DONE.
1. ✅ **Coverage-gap + placement model** — DONE (`build_coverage_gap.py`, reach×need candidates).
2. ✅ **Live map + context layers + self-updating pipeline** — DONE (`refresh.sh` + Action).
3. **Data-acquisition asks** (flagged, not blocking): live point-level non-fatal/EMS runs
   (CDPH/CFD agreement); wastewater fentanyl/xylazine signal (Biobot/ICPSR); community input
   from people who use drugs (VENDY-style).
4. **Port to SaveSpots.org website repo** — re-skin to modern/professional production quality.

## Conventions
- **Source of truth = the live API**, not the static CSV. Cache pulls to a local file with a
  fetch timestamp so analyses are reproducible.
- Always **state the reporting-lag caveat** on recent-period totals.
- Keep raw downloads separate from derived/cleaned outputs.
- When you need data the user has (non-public sources, a fresh export, a corrected file),
  **ask them to upload it** rather than guessing.
- Today's date for "as of" framing: see the session date.
