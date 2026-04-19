#!/usr/bin/env python3
import json
import math
import sqlite3
import sys

DB_PATH = "/home/pi/landdb/data/nevada_land.sqlite"

OWNERSHIP_SQL = """
SELECT
    NAME,
    ABBR,
    CASE
        WHEN ABBR = 'BIA'  THEN 'Reservation / Tribal'
        WHEN ABBR = 'BLM'  THEN 'BLM'
        WHEN ABBR = 'FS'   THEN 'National Forest'
        WHEN ABBR = 'NPS'  THEN 'National Park'
        WHEN ABBR = 'FWS'  THEN 'Fish & Wildlife'
        WHEN ABBR = 'DOD'  THEN 'Military'
        WHEN ABBR = 'DOE'  THEN 'DOE / Federal Restricted'
        WHEN ABBR = 'BR'   THEN 'Bureau of Reclamation'
        WHEN ABBR = 'NVST' THEN 'State Land'
        WHEN ABBR = 'PVT'  THEN 'Private'
        WHEN ABBR = 'WTR'  THEN 'Water'
        ELSE 'Unknown'
    END AS land_class
FROM blm_sma_raw
WHERE ST_Contains(shape, MakePoint(?, ?, 4326))
LIMIT 1;
"""

PADUS_SQL = """
SELECT
    Unit_Nm,
    Own_Name,
    Mang_Name,
    CASE
        WHEN Own_Name = 'TRIB' OR Mang_Name = 'TRIB' THEN 'Reservation / Tribal'
        WHEN Own_Name = 'BLM'  OR Mang_Name = 'BLM'  THEN 'BLM'
        WHEN Own_Name = 'USFS' OR Mang_Name = 'USFS' THEN 'National Forest'
        WHEN Own_Name = 'DOD'  OR Mang_Name = 'DOD'  THEN 'Military'
        WHEN Own_Name = 'DOE'  OR Mang_Name = 'DOE'  THEN 'DOE / Federal Restricted'
        WHEN Own_Name = 'USBR' OR Mang_Name = 'USBR' THEN 'Bureau of Reclamation'
        WHEN Own_Name = 'CNTY' OR Mang_Name = 'CNTY' THEN 'County Land'
        WHEN Own_Name = 'CITY' OR Mang_Name = 'CITY' THEN 'City Land'
        ELSE 'Public / Protected'
    END AS land_class
FROM padus_raw
WHERE ST_Contains(shape, MakePoint(?, ?, 4326))
LIMIT 1;
"""

PLAD_AREA_SQL = """
SELECT
    ACS_RGHTS_TYPE,
    LEGAL_USE_TYPE,
    SSNL_USE_TYPE,
    TRVL_PLAN_YN,
    GEO_NAME,
    ROUTE_NO
FROM plad_areas_raw
WHERE ST_Contains(shape, MakePoint(?, ?, 4326))
LIMIT 1;
"""

PLAD_ROUTE_SQL = """
SELECT
    ACS_RGHTS_TYPE,
    LEGAL_USE_TYPE,
    SSNL_USE_TYPE,
    TRVL_PLAN_YN,
    GEO_NAME,
    ROUTE_NO,
    ST_Distance(
        shape,
        MakePoint(?, ?, 4326)
    ) AS dist_deg
FROM plad_routes_raw
ORDER BY dist_deg ASC
LIMIT 1;
"""


def deg_to_meters(lat: float, dist_deg: float) -> float:
    meters_per_deg_lat = 111320.0
    meters_per_deg_lon = 111320.0 * math.cos(math.radians(lat))
    avg_meters_per_deg = (meters_per_deg_lat + max(meters_per_deg_lon, 1.0)) / 2.0
    return dist_deg * avg_meters_per_deg


def classify_access_proximity(distance_m: float | None) -> str | None:
    if distance_m is None:
        return None
    if distance_m <= 250:
        return "Nearby Access"
    if distance_m <= 2000:
        return "Possible Access Nearby"
    if distance_m <= 10000:
        return "Distant Access"
    return "No Meaningful Nearby Access"


def build_access_summary(
    area_hit: bool,
    area_rights: str | None,
    area_legal_use: str | None,
    route_rights: str | None,
    route_legal_use: str | None,
    distance_m: float | None,
) -> str:
    if area_hit:
        parts = ["Within PLAD access area"]
        if area_rights:
            parts.append(area_rights)
        if area_legal_use:
            parts.append(area_legal_use)
        return " | ".join(parts)

    proximity = classify_access_proximity(distance_m)
    if proximity is None:
        return "No PLAD access data"

    if proximity == "No Meaningful Nearby Access":
        return "No meaningful nearby public access route"

    parts = [proximity]
    if route_rights:
        parts.append(route_rights)
    if route_legal_use:
        parts.append(route_legal_use)
    return " | ".join(parts)


def fail(message: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": message}))
    sys.exit(code)


def main() -> None:
    if len(sys.argv) != 3:
        fail("usage: nv_land_lookup.py <lat> <lon>")

    try:
        lat = float(sys.argv[1])
        lon = float(sys.argv[2])
    except ValueError:
        fail("invalid latitude/longitude")

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        fail("latitude/longitude out of range")

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.enable_load_extension(True)
        conn.load_extension("mod_spatialite")
        cur = conn.cursor()

        result = {
            "ok": True,
            "state": "NV",
            "lat": lat,
            "lon": lon,
            "land_class": "Unknown",
            "land_code": None,
            "land_name": None,
            "land_source": None,
            "fallback_unit_name": None,
            "access_area_hit": False,
            "access_area_name": None,
            "access_area_rights": None,
            "access_area_legal_use": None,
            "access_area_seasonal_use": None,
            "access_area_travel_plan": None,
            "nearest_route_name": None,
            "nearest_route_no": None,
            "nearest_access_rights": None,
            "nearest_legal_use": None,
            "nearest_seasonal_use": None,
            "nearest_travel_plan": None,
            "nearest_access_distance_m": None,
            "nearest_access_distance_km": None,
            "access_proximity": None,
            "access_summary": None,
        }

        cur.execute(OWNERSHIP_SQL, (lon, lat))
        row = cur.fetchone()
        if row:
            result["land_name"] = row[0]
            result["land_code"] = row[1]
            result["land_class"] = row[2]
            result["land_source"] = "blm_sma_raw"
        else:
            cur.execute(PADUS_SQL, (lon, lat))
            row = cur.fetchone()
            if row:
                result["fallback_unit_name"] = row[0]
                result["land_code"] = row[1] or row[2]
                result["land_name"] = row[0]
                result["land_class"] = row[3]
                result["land_source"] = "padus_raw"

        cur.execute(PLAD_AREA_SQL, (lon, lat))
        row = cur.fetchone()
        if row:
            result["access_area_hit"] = True
            result["access_area_rights"] = row[0]
            result["access_area_legal_use"] = row[1]
            result["access_area_seasonal_use"] = row[2]
            result["access_area_travel_plan"] = row[3]
            result["access_area_name"] = row[4] or row[5]

        cur.execute(PLAD_ROUTE_SQL, (lon, lat))
        row = cur.fetchone()
        if row:
            result["nearest_access_rights"] = row[0]
            result["nearest_legal_use"] = row[1]
            result["nearest_seasonal_use"] = row[2]
            result["nearest_travel_plan"] = row[3]
            result["nearest_route_name"] = row[4]
            result["nearest_route_no"] = row[5]

            dist_m = round(deg_to_meters(lat, row[6]), 1)
            result["nearest_access_distance_m"] = dist_m
            result["nearest_access_distance_km"] = round(dist_m / 1000.0, 2)
            result["access_proximity"] = classify_access_proximity(dist_m)

        result["access_summary"] = build_access_summary(
            result["access_area_hit"],
            result["access_area_rights"],
            result["access_area_legal_use"],
            result["nearest_access_rights"],
            result["nearest_legal_use"],
            result["nearest_access_distance_m"],
        )

        conn.close()
        print(json.dumps(result, indent=2))

    except Exception as e:
        fail(str(e))


if __name__ == "__main__":
    main()
