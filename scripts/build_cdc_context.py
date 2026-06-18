#!/usr/bin/env python3
"""
SaveSpots — CDC live context layers  (Phase A)
==============================================
Two LIVE national-source layers that the Cook County ME data alone can't give:

  1. cdc_vsrr.json         — CDC VSRR provisional drug-overdose counts for Cook County
                             (12-month-ending, monthly) WITH `percentage_of_records_pending`.
                             Used for a real, sourced reporting-lag correction instead of a guess.
  2. tract_overdose.geojson — CDC "Mapping Injury, Overdose & Violence" census-tract Drug_OD
                             RATES (per 100k), joined onto Chicago tract polygons. A
                             rate-normalized surface finer than community areas.

Run: python3 scripts/build_cdc_context.py
"""
import json, os, urllib.parse, urllib.request

CLEAN = "data/clean"
VSRR = "https://data.cdc.gov/resource/gb4e-yj24.json"
TRACT = "https://data.cdc.gov/resource/4day-mt2f.json"
TRACT_GEO = "https://data.cityofchicago.org/resource/74p9-q2aq.geojson"
os.makedirs(CLEAN, exist_ok=True)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "SaveSpots/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


def vsrr():
    print("[1] CDC VSRR provisional (Cook County, lag correction) ...")
    p = {"$where": "countyname='Cook' AND state_name='Illinois'",
         "$select": "monthendingdate,provisional_drug_overdose,percentage_of_records_pending",
         "$order": "monthendingdate DESC", "$limit": 24}
    rows = get(f"{VSRR}?{urllib.parse.urlencode(p)}")
    series = [{
        "month_ending": r["monthendingdate"][:10],
        "count_12mo": int(r["provisional_drug_overdose"]) if r.get("provisional_drug_overdose") else None,
        "pct_pending": round(float(r.get("percentage_of_records_pending", 0) or 0) * 100, 1),
    } for r in rows]
    latest = series[0] if series else {}
    out = {
        "county": "Cook County, IL",
        "metric": "Provisional drug-overdose deaths, 12-month-ending (all drugs, CDC VSRR)",
        "series_desc_recent_first": series,
        "latest": latest,
        "lag_note": (
            f"Most recent 12-mo-ending value ({latest.get('month_ending')}) has "
            f"{latest.get('pct_pending')}% of records still pending — i.e. it is an UNDERCOUNT "
            "that will rise. Treat recent months as a floor, not a final number."
        ),
    }
    json.dump(out, open(f"{CLEAN}/cdc_vsrr.json", "w"), indent=2)
    print(f"    latest 12mo-ending {latest.get('month_ending')}: {latest.get('count_12mo')} "
          f"({latest.get('pct_pending')}% pending)")


def tract_surface():
    print("[2] CDC census-tract Drug_OD rate surface (Cook) ...")
    p = {"$where": "st_name='Illinois' AND intent='Drug_OD'",
         "$select": "name,rate,count_sup,period,data_as_of", "$limit": 5000}
    rows = get(f"{TRACT}?{urllib.parse.urlencode(p)}")
    # CDC merges small tracts; `name` lists the constituent 11-digit FIPS sharing one rate.
    rate_by_tract, period, as_of = {}, None, None
    for r in rows:
        period = period or r.get("period")
        as_of = as_of or (r.get("data_as_of") or "")[:10]
        try:
            rate = float(r.get("rate", 0) or 0)
        except ValueError:
            continue
        for t in (r.get("name") or "").split(","):
            t = t.strip()
            if t.startswith("17031"):   # Cook County FIPS
                rate_by_tract[t] = rate
    print(f"    {len(rate_by_tract)} Cook tracts with Drug_OD rates (period {period})")

    print("    fetching Chicago tract polygons + joining ...")
    geo = get(f"{TRACT_GEO}?{urllib.parse.urlencode({'$limit': 900})}")
    matched = 0
    for f in geo.get("features", []):
        props = f.get("properties", {})
        gid = props.get("geoid10")
        rate = rate_by_tract.get(gid)
        props["od_rate"] = rate
        props["community_area"] = props.get("commarea_n")
        if rate is not None:
            matched += 1
        # trim heavy unused props
        for k in ("name10", "namelsad10", "notes", "statefp10", "countyfp10", "tractce10"):
            props.pop(k, None)
    geo["metadata"] = {"source": "CDC Mapping I/O/V census-tract Drug_OD rate (per 100k)",
                       "period": period, "data_as_of": as_of, "tracts_with_rate": matched}
    json.dump(geo, open(f"{CLEAN}/tract_overdose.geojson", "w"))
    print(f"    wrote tract_overdose.geojson ({matched} tracts carry a rate)")


if __name__ == "__main__":
    vsrr()
    tract_surface()
    print("\nWrote cdc_vsrr.json, tract_overdose.geojson")
