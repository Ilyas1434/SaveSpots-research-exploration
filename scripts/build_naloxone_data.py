#!/usr/bin/env python3
"""
Build naloxone location dataset from all known public sources.
Geocodes using US Census Bureau geocoder (free, no key needed).
Outputs: data/clean/naloxone_locations.geojson
"""
import json, csv, time, os, urllib.parse, urllib.request, sys

CLEAN_DIR = "data/clean"
os.makedirs(CLEAN_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# KNOWN NALOXONE LOCATIONS (compiled from: Cook County Health, CDPH, CTA pilot,
# Chicago Recovery Alliance, Cook County circuit courts, and existing txt file)
# ---------------------------------------------------------------------------
LOCATIONS = [
    # --- Cook County Health hospital vending machines ---
    {"name":"Stroger Hospital Lobby","address":"1969 W Ogden Ave","city":"Chicago","state":"IL","zip":"60612","type":"vending_machine","operator":"Cook County Health","source":"CCH website 2025"},
    {"name":"CORE Center (CCDPH)","address":"2020 W Harrison St","city":"Chicago","state":"IL","zip":"60612","type":"vending_machine","operator":"Cook County Health","source":"CCH website 2025"},
    {"name":"Provident Hospital","address":"500 E 51st St","city":"Chicago","state":"IL","zip":"60615","type":"vending_machine","operator":"Cook County Health","source":"CCH website 2025"},
    {"name":"Domestic Violence Courthouse","address":"555 W Harrison St","city":"Chicago","state":"IL","zip":"60607","type":"vending_machine","operator":"Cook County Health","source":"CCH website 2025"},
    {"name":"Leighton Criminal Courthouse","address":"2650 S California Ave","city":"Chicago","state":"IL","zip":"60608","type":"vending_machine","operator":"Cook County Health","source":"CCH website 2025"},
    {"name":"Cook County DOC Post 5","address":"2700 S California Ave","city":"Chicago","state":"IL","zip":"60608","type":"vending_machine","operator":"Cook County DOC","source":"CCH website 2025"},
    {"name":"Cook County DOC Division 10","address":"2950 S California Ave","city":"Chicago","state":"IL","zip":"60608","type":"vending_machine","operator":"Cook County DOC","source":"CCH website 2025"},
    {"name":"Cook County DOC Division 11","address":"3015 S California Ave","city":"Chicago","state":"IL","zip":"60608","type":"vending_machine","operator":"Cook County DOC","source":"CCH website 2025"},
    # --- CTA vending machines (pilot 2025, Cook County Health) ---
    {"name":"Jefferson Park Blue Line Station","address":"4917 N Milwaukee Ave","city":"Chicago","state":"IL","zip":"60630","type":"vending_machine","operator":"Cook County Health / CTA","source":"CCH press release Sep 2025"},
    {"name":"Harlem/Lake Green Line Station","address":"1 Harlem Ave","city":"Oak Park","state":"IL","zip":"60130","type":"vending_machine","operator":"Cook County Health / CTA","source":"CCH press release Sep 2025"},
    {"name":"47th Street Red Line Station","address":"220 W 47th St","city":"Chicago","state":"IL","zip":"60609","type":"vending_machine","operator":"Cook County Health / CTA","source":"CCH press release Sep 2025"},
    {"name":"Howard Red Line Station","address":"7519 N Paulina St","city":"Chicago","state":"IL","zip":"60626","type":"vending_machine","operator":"Cook County Health / CTA","source":"CCH press release Sep 2025"},
    {"name":"Central Park Pink Line Station","address":"721 N Central Park Ave","city":"Chicago","state":"IL","zip":"60624","type":"vending_machine","operator":"Cook County Health / CTA","source":"CCH press release Sep 2025"},
    # --- CDPH vending machines ---
    {"name":"Uptown Library (CDPH vending)","address":"929 W Buena Ave","city":"Chicago","state":"IL","zip":"60613","type":"vending_machine","operator":"CDPH","source":"CDPH vending machine brief Dec 2025"},
    {"name":"Garfield Community Service Center","address":"10 S Kedzie Ave","city":"Chicago","state":"IL","zip":"60612","type":"vending_machine","operator":"CDPH","source":"CDPH vending machine brief Dec 2025"},
    {"name":"Harold Washington Library","address":"400 S State St","city":"Chicago","state":"IL","zip":"60605","type":"vending_machine","operator":"CDPH","source":"CDPH vending machine brief Dec 2025"},
    {"name":"95th/Dan Ryan Red Line Station (CDPH)","address":"14 W 95th St","city":"Chicago","state":"IL","zip":"60628","type":"vending_machine","operator":"CDPH / CTA","source":"CDPH vending machine brief Dec 2025"},
    {"name":"Roseland Community Triage Center","address":"200 E 115th St","city":"Chicago","state":"IL","zip":"60628","type":"vending_machine","operator":"CDPH","source":"CDPH vending machine brief Dec 2025"},
    # --- Cook County suburban courthouses vending machines ---
    {"name":"Bridgeview Courthouse","address":"10220 S 76th Ave","city":"Bridgeview","state":"IL","zip":"60455","type":"vending_machine","operator":"Cook County Health","source":"CCH website 2025"},
    {"name":"Markham Courthouse","address":"16501 Kedzie Ave","city":"Markham","state":"IL","zip":"60428","type":"vending_machine","operator":"Cook County Health","source":"CCH website 2025"},
    {"name":"Maywood Courthouse","address":"1311 Maybrook Dr","city":"Maywood","state":"IL","zip":"60153","type":"vending_machine","operator":"Cook County Health","source":"CCH website 2025"},
    {"name":"Rolling Meadows Courthouse","address":"2121 Euclid Ave","city":"Rolling Meadows","state":"IL","zip":"60008","type":"vending_machine","operator":"Cook County Health","source":"CCH website 2025"},
    {"name":"Skokie Courthouse","address":"5600 Old Orchard Rd","city":"Skokie","state":"IL","zip":"60077","type":"vending_machine","operator":"Cook County Health","source":"CCH website 2025"},
    # --- Cook County Circuit Court distribution boxes ---
    {"name":"Cook County Circuit Court - Flournoy","address":"3150 W Flournoy St","city":"Chicago","state":"IL","zip":"60612","type":"distribution_box","operator":"Cook County Health","source":"CCH website 2025"},
    {"name":"Cook County Circuit Court - Grand Ave","address":"5555 W Grand Ave","city":"Chicago","state":"IL","zip":"60639","type":"distribution_box","operator":"Cook County Health","source":"CCH website 2025"},
    {"name":"Cook County Circuit Court - 111th St","address":"727 E 111th St","city":"Chicago","state":"IL","zip":"60628","type":"distribution_box","operator":"Cook County Health","source":"CCH website 2025"},
    {"name":"Cook County Circuit Court - 69th St","address":"845 W 69th St","city":"Chicago","state":"IL","zip":"60621","type":"distribution_box","operator":"Cook County Health","source":"CCH website 2025"},
    # --- Chicago Recovery Alliance ---
    {"name":"Chicago Recovery Alliance HQ","address":"3110 W Taylor St","city":"Chicago","state":"IL","zip":"60612","type":"harm_reduction_org","operator":"Chicago Recovery Alliance","source":"CRA website 2025"},
    # --- CDPH newsstands (2025) ---
    {"name":"Narcan Newsstand - Uptown (Lakeview)","address":"4120 N Sheridan Rd","city":"Chicago","state":"IL","zip":"60613","type":"newsstand","operator":"CDPH","source":"Block Club Chicago Aug 2025"},
    {"name":"Narcan Newsstand - Uptown 2","address":"4624 N Broadway","city":"Chicago","state":"IL","zip":"60640","type":"newsstand","operator":"CDPH","source":"Block Club Chicago Aug 2025"},
    # --- Existing Cook County suburban boxes (from txt file in repo) ---
    {"name":"Ajeeba Hair Design","address":"1254 Burnham Ave","city":"Calumet City","state":"IL","zip":"60409","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"AristaCare","address":"1056 W Golf Rd","city":"Hoffman Estates","state":"IL","zip":"60169","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Bellwood Liquor and Grocery","address":"5001 Saint Charles Rd","city":"Bellwood","state":"IL","zip":"60104","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Blue Island Public Library","address":"2433 York Street","city":"Blue Island","state":"IL","zip":"60406","type":"library","operator":"Cook County","source":"Cook County map"},
    {"name":"Center of Concern","address":"1665 Elk Blvd","city":"Des Plaines","state":"IL","zip":"60016","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Chicago Ridge Library","address":"10400 Oxford Ave","city":"Chicago Ridge","state":"IL","zip":"60415","type":"library","operator":"Cook County","source":"Cook County map"},
    {"name":"Corazon Community Services","address":"5339 W 25th St","city":"Cicero","state":"IL","zip":"60804","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"DA Candy Corner","address":"1117 Madison St","city":"Maywood","state":"IL","zip":"60153","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Debbie's Darn Good Deals","address":"1950 S Ruby Street","city":"Melrose Park","state":"IL","zip":"60160","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Drama Beauty Cicero","address":"4909 W 14th St","city":"Cicero","state":"IL","zip":"60804","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Express Food Mart","address":"7026 16th St","city":"Berwyn","state":"IL","zip":"60402","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Healthy Soul Talk LLC","address":"1701 S 1st Ave","city":"Maywood","state":"IL","zip":"60153","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Lansing Public Library","address":"2750 Indiana Ave","city":"Lansing","state":"IL","zip":"60438","type":"library","operator":"Cook County","source":"Cook County map"},
    {"name":"Maine Township","address":"1700 Ballard Road","city":"Park Ridge","state":"IL","zip":"60068","type":"government","operator":"Cook County","source":"Cook County map"},
    {"name":"New Era Restaurant","address":"15 N 5th Ave","city":"Maywood","state":"IL","zip":"60153","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Niles-Maine District Library","address":"6960 W Oakton St","city":"Niles","state":"IL","zip":"60714","type":"library","operator":"Cook County","source":"Cook County map"},
    {"name":"Oak Lawn Public Library","address":"9427 Raymond Avenue","city":"Oak Lawn","state":"IL","zip":"60453","type":"library","operator":"Cook County","source":"Cook County map"},
    {"name":"Perros Brothers - South Chicago Heights","address":"2601 Chicago Rd","city":"South Chicago Heights","state":"IL","zip":"60411","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Perros Brothers - Olympia Fields","address":"3770 Lincoln Highway","city":"Olympia Fields","state":"IL","zip":"60461","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"PLCCA","address":"411 Madison St","city":"Maywood","state":"IL","zip":"60153","type":"harm_reduction_org","operator":"Cook County","source":"Cook County map"},
    {"name":"RayMil Consulting","address":"518 S 7th Avenue","city":"Maywood","state":"IL","zip":"60153","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Respond Now","address":"1250 Portland Ave","city":"Chicago Heights","state":"IL","zip":"60411","type":"harm_reduction_org","operator":"Cook County","source":"Cook County map"},
    {"name":"Riverdale Public Library","address":"208 W 144th St","city":"Riverdale","state":"IL","zip":"60827","type":"library","operator":"Cook County","source":"Cook County map"},
    {"name":"Salvation Army Community Ctr","address":"2337 S Laramie Ave","city":"Cicero","state":"IL","zip":"60804","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Self-Help Closet & Pantry Des Plaines","address":"769 Holiday Ln","city":"Des Plaines","state":"IL","zip":"60016","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"South Suburban College Oak Forest","address":"16333 S Kilbourn Ave","city":"Oak Forest","state":"IL","zip":"60452","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"South Suburban College South Holland","address":"15800 State St","city":"South Holland","state":"IL","zip":"60473","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"South Suburban Council","address":"1909 Cheker Square","city":"Hazel Crest","state":"IL","zip":"60429","type":"harm_reduction_org","operator":"Cook County","source":"Cook County map"},
    {"name":"Steger Library","address":"54 E 31st St","city":"Steger","state":"IL","zip":"60475","type":"library","operator":"Cook County","source":"Cook County map"},
    {"name":"The Print Labb","address":"1819 Roosevelt Rd","city":"Broadview","state":"IL","zip":"60155","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Thornton Public Library","address":"115 E Margaret St","city":"Thornton","state":"IL","zip":"60476","type":"library","operator":"Cook County","source":"Cook County map"},
    {"name":"Tinley Park Apothecary","address":"17320 Oak Park Ave","city":"Tinley Park","state":"IL","zip":"60477","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Tinley Park Public Library","address":"7851 Timber Dr","city":"Tinley Park","state":"IL","zip":"60477","type":"library","operator":"Cook County","source":"Cook County map"},
    {"name":"Tony's Food & Liquor","address":"1709 E Sauk Trl","city":"Chicago Heights","state":"IL","zip":"60411","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Towncare Pharmacy LLC","address":"13805 S Cicero Ave","city":"Midlothian","state":"IL","zip":"60455","type":"pharmacy","operator":"Cook County","source":"Cook County map"},
    {"name":"Triton College","address":"2000 North 5th Avenue","city":"River Grove","state":"IL","zip":"60171","type":"distribution_box","operator":"Cook County","source":"Cook County map"},
    {"name":"Village of Bellwood","address":"3200 Washington Blvd","city":"Bellwood","state":"IL","zip":"60104","type":"government","operator":"Cook County","source":"Cook County map"},
    {"name":"Village of Maywood","address":"40 Madison St","city":"Maywood","state":"IL","zip":"60153","type":"government","operator":"Cook County","source":"Cook County map"},
    {"name":"Village of Maywood Masonic Temple","address":"200 S 5th Ave","city":"Maywood","state":"IL","zip":"60153","type":"government","operator":"Cook County","source":"Cook County map"},
    {"name":"William Leonard Library of Robbins","address":"13820 Central Park Ave","city":"Robbins","state":"IL","zip":"60472","type":"library","operator":"Cook County","source":"Cook County map"},
    {"name":"Commissioner Kevin Morrison Office","address":"1325 Wiley Road Suite 141","city":"Schaumburg","state":"IL","zip":"60173","type":"government","operator":"Cook County","source":"Cook County map"},
    {"name":"Commissioner Kisha McCaskill Office","address":"3039 W 159th Street","city":"Markham","state":"IL","zip":"60428","type":"government","operator":"Cook County","source":"Cook County map"},
]

def geocode(address, city, state, zip_):
    """Census Bureau geocoder - free, no key."""
    params = urllib.parse.urlencode({
        "street": address, "city": city, "state": state, "zip": zip_,
        "benchmark": "Public_AR_Current", "format": "json"
    })
    url = f"https://geocoding.geo.census.gov/geocoder/locations/address?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"SaveSpots/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        matches = d.get("result", {}).get("addressMatches", [])
        if matches:
            c = matches[0]["coordinates"]
            return float(c["x"]), float(c["y"])  # lon, lat
    except Exception:
        pass
    return None, None

def main():
    # Fetch all Chicago library branches from City data portal
    lib_url = "https://data.cityofchicago.org/resource/x8fc-8rcq.json?$limit=200"
    req = urllib.request.Request(lib_url, headers={"User-Agent":"SaveSpots/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        libs = json.loads(r.read())
    print(f"  fetched {len(libs)} Chicago library branches")
    for lib in libs:
        name = lib.get("name_") or lib.get("name") or "Chicago Public Library"
        LOCATIONS.append({
            "name": name,
            "address": lib.get("address", ""),
            "city": "Chicago",
            "state": "IL",
            "zip": lib.get("zip", ""),
            "type": "library",
            "operator": "Chicago Public Library",
            "source": "City of Chicago Data Portal (all 81 CPL branches have naloxone since 2022)"
        })

    # Geocode all
    features = []
    print(f"\nGeocoding {len(LOCATIONS)} locations...")
    for i, loc in enumerate(LOCATIONS):
        lon, lat = geocode(loc["address"], loc["city"], loc["state"], loc["zip"])
        status = "✓" if lon else "✗"
        print(f"  {status} [{i+1}/{len(LOCATIONS)}] {loc['name']}")
        if lon and lat:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "name": loc["name"],
                    "address": f"{loc['address']}, {loc['city']}, {loc['state']} {loc['zip']}",
                    "city": loc["city"],
                    "zip": loc["zip"],
                    "type": loc["type"],
                    "operator": loc["operator"],
                    "source": loc["source"],
                    "in_chicago": loc["city"].lower() == "chicago",
                }
            })
        time.sleep(0.15)  # be polite to Census API

    out = {
        "type": "FeatureCollection",
        "metadata": {"total": len(features), "sources": ["Cook County Health", "CDPH", "CTA", "Chicago Public Library", "Chicago Recovery Alliance", "Cook County suburban map"]},
        "features": features
    }
    path = os.path.join(CLEAN_DIR, "naloxone_locations.geojson")
    with open(path, "w") as f:
        json.dump(out, f)
    print(f"\n  wrote {path} ({len(features)} geocoded locations)")
    failed = len(LOCATIONS) - len(features)
    if failed: print(f"  {failed} locations failed geocoding")

if __name__ == "__main__":
    main()
