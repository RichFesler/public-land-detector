#!/usr/bin/env python3
import json, sqlite3, sys

DB_PATH = "./data/nevada_land.sqlite"

if len(sys.argv) != 3:
    print(json.dumps({"ok": False}))
    exit()

lat = float(sys.argv[1])
lon = float(sys.argv[2])

conn = sqlite3.connect(DB_PATH)
conn.enable_load_extension(True)
conn.load_extension("mod_spatialite")
cur = conn.cursor()

cur.execute("""
SELECT NAME, ABBR
FROM blm_sma_raw
WHERE ST_Contains(shape, MakePoint(?, ?, 4326))
LIMIT 1;
""", (lon, lat))

row = cur.fetchone()

print(json.dumps({
    "ok": True,
    "land_name": row[0] if row else None,
    "land_code": row[1] if row else None
}, indent=2))
