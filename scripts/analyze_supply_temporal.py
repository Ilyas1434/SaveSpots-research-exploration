#!/usr/bin/env python3
"""
SaveSpots — Supply / Temporal / Reachability analysis  (Phase A)
================================================================
Derives three context layers straight from the LIVE Cook County ME API:

  1. reachability.json     — how often overdose death occurs in the victim's home ZIP
                             (proxy for "died at/near home, likely alone"). Supports the
                             take-home distribution model (naloxone travels with the person).
  2. supply_composition.json — adulterant trend (xylazine / nitazene / carfentanil) over time
                             + top community areas. Drives the box-CONTENTS recommendation
                             (naloxone does not reverse xylazine -> add test strips + wound care).
  3. temporal.json         — hour-of-day / day-of-week / month of fatal overdose. Drives
                             restocking + outreach timing.

All counts come from Socrata SoQL aggregation (no full download). Run:
    python3 scripts/analyze_supply_temporal.py
"""
import json, os, time, urllib.parse, urllib.request

API = "https://datacatalog.cookcountyil.gov/resource/cjeq-bs86.json"
CLEAN = "data/clean"
CHI = "opioids=true AND chi_commarea IS NOT NULL"   # overdoses occurring in Chicago
os.makedirs(CLEAN, exist_ok=True)


def soql(select=None, where=None, group=None, order=None, limit=50000):
    p = {}
    if select: p["$select"] = select
    if where:  p["$where"] = where
    if group:  p["$group"] = group
    if order:  p["$order"] = order
    if limit:  p["$limit"] = limit
    url = f"{API}?{urllib.parse.urlencode(p)}"
    req = urllib.request.Request(url, headers={"User-Agent": "SaveSpots/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(1.5)


def count(where):
    return int(soql(select="count(1)", where=where)[0]["count_1"])


# ---------------------------------------------------------------------------
# 1. Reachability — incident ZIP == residence ZIP
# ---------------------------------------------------------------------------
def reachability():
    print("[1] Reachability (incident ZIP vs residence ZIP) ...")
    base = f"{CHI} AND incident_zip IS NOT NULL AND residence_zip IS NOT NULL"
    total = count(base)
    same = count(base + " AND incident_zip = residence_zip")
    pct = round(100 * same / total, 1) if total else 0
    out = {
        "total_with_both_zips": total,
        "died_in_home_zip": same,
        "pct_home_zip": pct,
        "pct_away": round(100 - pct, 1),
        "interpretation": (
            f"{pct}% of Chicago opioid deaths occur in the victim's home ZIP code — consistent "
            "with using at/near home, often alone. This is exactly the scenario a fixed box "
            "cannot reach in time, and why TAKE-HOME distribution (carry it with you) is the "
            "right mechanism: the naloxone goes home with the person who picked it up."
        ),
        "caveat": "ZIP-match is a coarse proxy; residence street address is not public.",
    }
    json.dump(out, open(f"{CLEAN}/reachability.json", "w"), indent=2)
    print(f"    {pct}% died in home ZIP ({same}/{total})")


# ---------------------------------------------------------------------------
# 2. Supply composition — adulterants over time
# ---------------------------------------------------------------------------
SUBSTANCES = {
    "xylazine": "XYLAZINE",
    "nitazene": "NITAZENE",          # also catches metonitazene etc. via LIKE
    "carfentanil": "CARFENTANIL",
    "fentanyl": "FENTANYL",
    "heroin": "HEROIN",
    "cocaine": "COCAINE",
}


def supply():
    print("[2] Supply composition (adulterant trend) ...")
    def cause_like(kw):
        return (f"(upper(primarycause) like '%{kw}%' OR upper(secondarycause) like '%{kw}%' "
                f"OR upper(primarycause_linea) like '%{kw}%')")

    yearly = {}
    for name, kw in SUBSTANCES.items():
        rows = soql(select="date_extract_y(death_date) as yr, count(1)",
                    where=f"{CHI} AND {cause_like(kw)}", group="yr", order="yr")
        yearly[name] = {r["yr"]: int(r["count_1"]) for r in rows if r.get("yr")}
        print(f"    {name:12} {yearly[name]}")

    # xylazine by community area (where naloxone alone is insufficient) — settled years
    xyl_ca = soql(select="chi_commarea, count(1)",
                  where=f"{CHI} AND {cause_like('XYLAZINE')} AND death_date between "
                        "'2022-01-01' and '2024-12-31T23:59:59'",
                  group="chi_commarea", order="count_1 DESC", limit=15)
    out = {
        "yearly": yearly,
        "xylazine_top_areas_2022_2024": [
            {"community_area": r["chi_commarea"], "deaths": int(r["count_1"])} for r in xyl_ca
        ],
        "box_contents_recommendation": (
            "Xylazine ('tranq') is an adulterant in the fentanyl supply and is NOT reversed by "
            "naloxone. Given its rise, SaveSpots boxes should include xylazine test strips and "
            "wound-care info alongside naloxone + fentanyl test strips, with signage: 'still give "
            "naloxone, still call 911 — they may not fully wake.'"
        ),
        "note": "Recent years (2025-26) undercount due to ME toxicology reporting lag.",
    }
    json.dump(out, open(f"{CLEAN}/supply_composition.json", "w"), indent=2)


# ---------------------------------------------------------------------------
# 3. Temporal patterns
# ---------------------------------------------------------------------------
def temporal():
    print("[3] Temporal patterns ...")
    hour = soql(select="date_extract_hh(incident_date) as h, count(1)",
                where=CHI, group="h", order="h")
    dow = soql(select="date_extract_dow(incident_date) as d, count(1)",
               where=CHI, group="d", order="d")
    month = soql(select="date_extract_m(incident_date) as m, count(1)",
                 where=CHI, group="m", order="m")
    out = {
        "by_hour": {int(r["h"]): int(r["count_1"]) for r in hour if r.get("h") is not None},
        "by_dow": {int(r["d"]): int(r["count_1"]) for r in dow if r.get("d") is not None},
        "by_month": {int(r["m"]): int(r["count_1"]) for r in month if r.get("m") is not None},
        "dow_labels": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "note": ("Hour 0 is inflated by unknown-time records defaulting to midnight; daytime "
                 "10am-4pm is the genuine peak. Use for restocking + outreach timing."),
    }
    json.dump(out, open(f"{CLEAN}/temporal.json", "w"), indent=2)
    peak_h = max(out["by_hour"], key=lambda k: out["by_hour"][k] if k != 0 else -1)
    print(f"    peak hour (excl. midnight artifact): {peak_h}:00")


if __name__ == "__main__":
    reachability()
    supply()
    temporal()
    print("\nWrote reachability.json, supply_composition.json, temporal.json")
