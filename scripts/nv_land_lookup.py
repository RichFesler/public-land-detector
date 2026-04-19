#!/usr/bin/env python3
import json
import math
import sqlite3
import sys

STATE_CODE = "NV"
DB_PATH = "/home/pi/landdb/data/nevada_land.sqlite"

TABLES = {
    "ownership": "blm_sma_raw",
    "padus": "padus_raw",
    "plad_areas": "plad_areas_raw",
    "plad_routes": "plad_routes_raw",
}

OWNERSHIP_SQL = f"""
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
FROM {TABLES["ownership"]}
WHERE ST_Contains(shape, MakePoint(?, ?, 4326))
LIMIT 1;
"""

PLAD_AREA_SQL = f"""
SELECT
    ACS_RGHTS_TYPE,
    LEGAL_USE_TYPE,
    SSNL_USE_TYPE,
    TRVL_PLAN_YN,
    GEO_NAME,
    ROUTE_NO
FROM {TABLES["plad_areas"]}
WHERE ST_Contains(shape, MakePoint(?, ?, 4326))
LIMIT 1;
"""

PLAD_ROUTE_SQL = f"""
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
FROM {TABLES["plad_routes"]}
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


def get_table_columns(cur: sqlite3.Cursor, table_name: str) -> list[str]:
    cur.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cur.fetchall()]


def pick_column(columns: list[str], candidates: list[str]) -> str | None:
    lookup = {col.lower(): col for col in columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def build_padus_sql(cur: sqlite3.Cursor) -> str | None:
    columns = get_table_columns(cur, TABLES["padus"])

    unit_col = pick_column(columns, [
        "Unit_Nm", "UNIT_NM", "unit_nm",
        "Unit_Name", "UNIT_NAME", "unit_name",
        "Name", "NAME", "name",
    ])
    own_col = pick_column(columns, [
        "Own_Name", "OWN_NAME", "own_name",
        "Own_Type", "OWN_TYPE", "own_type",
        "Owner", "OWNER", "owner",
    ])
    mang_col = pick_column(columns, [
        "Mang_Name", "MANG_NAME", "mang_name",
        "Mang_Type", "MANG_TYPE", "mang_type",
        "Manager", "MANAGER", "manager",
    ])

    if not unit_col or not own_col or not mang_col:
        return None

    return f"""
    SELECT
        {unit_col},
        {own_col},
        {mang_col},
        CASE
            WHEN {own_col} = 'TRIB' OR {mang_col} = 'TRIB' THEN 'Reservation / Tribal'
            WHEN {own_col} = 'BLM'  OR {mang_col} = 'BLM'  THEN 'BLM'
            WHEN {own_col} = 'USFS' OR {mang_col} = 'USFS' THEN 'National Forest'
            WHEN {own_col} = 'DOD'  OR {mang_col} = 'DOD'  THEN 'Military'
            WHEN {own_col} = 'DOE'  OR {mang_col} = 'DOE'  THEN 'DOE / Federal Restricted'
            WHEN {own_col} = 'USBR' OR {mang_col} = 'USBR' THEN 'Bureau of Reclamation'
            WHEN {own_col} = 'CNTY' OR {mang_col} = 'CNTY' THEN 'County Land'
            WHEN {own_col} = 'CITY' OR {mang_col} = 'CITY' THEN 'City Land'
            ELSE 'Public / Protected'
        END AS land_class
    FROM {TABLES["padus"]}
    WHERE ST_Contains(shape, MakePoint(?, ?, 4326))
    LIMIT 1;
    """


def main() -> None:
    if len(sys.argv) != 3:
        fail("usage: land_lookup.py <lat> <lon>")

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

        padus_sql = build_padus_sql(cur)

        result = {
            "ok": True,
            "state": STATE_CODE,
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
            result["land_source"] = TABLES["ownership"]
        elif padus_sql:
            cur.execute(padus_sql, (lon, lat))
            row = cur.fetchone()
            if row:
                result["fallback_unit_name"] = row[0]
                result["land_code"] = row[1] or row[2]
                result["land_name"] = row[0]
                result["land_class"] = row[3]
                result["land_source"] = TABLES["padus"]

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
