# 🛰️ Offline Land Ownership & Access Classification (Nevada v1)

**MIT Licensed**

---

## Overview

A practical system for determining **what land you’re on** and **how (or if) you can legally access it** using only local data—no internet required.

---

## Why This Exists

If you travel across the western U.S.—especially Nevada—you routinely cross:

- Bureau of Land Management (BLM)
- National Forest (USFS)
- Tribal lands
- Military reservations
- Department of Energy restricted areas
- State lands
- Private parcels

On the ground, boundaries are invisible.

Online tools exist, but they fail when:

- you have no signal
- you need automation
- you want integration into a control system (Node-RED, vehicle UI, etc.)

This project solves that with a **fully offline spatial lookup engine**.

---

## Background: Public Land & Access

### Land Ownership vs. Access

Two separate questions:

1. Who owns or manages the land?
2. Can you legally get to or use it?

These are not the same.

**Example:**

- A parcel may be BLM land (public)
- but completely inaccessible due to surrounding private land

### U.S. Public Lands (Simplified)

- **BLM** – multiple-use land (often open, not always accessible)
- **USFS** – National Forest (regulated access)
- **NPS** – National Parks (restricted use)
- **FWS** – Wildlife refuges (restricted/seasonal)
- **DOD / DOE** – restricted or prohibited
- **BIA / Tribal** – sovereign land
- **State / County / City**
- **Private (PVT)**

### PLAD (Public Lands Access Data)

BLM’s PLAD dataset tracks:

- legal access routes (roads, trails, easements)
- access rights (public, restricted, seasonal)
- access areas

PLAD answers:

> “Can I legally get there?”

This project uses PLAD alongside ownership data to provide a more complete answer.

---

## What This System Does

Given a GPS coordinate:

```text
lat, lon
```

It returns:

- land ownership classification
- managing agency
- access context (area + nearest route)
- distance to nearest known legal access route
- interpreted access summary

All offline.

---

## Data Sources (Nevada v1)

### 1. Nevada Surface Management Agency (SMA)

**Primary ownership layer**

Source:
<https://gbp-blm-egis.hub.arcgis.com>

Provides statewide classification:

- BLM
- Private (PVT)
- DOD
- DOE
- USFS (FS)
- NPS
- FWS
- State (NVST)
- BIA
- Water

This is the **backbone dataset**.

### 2. PAD-US (USGS Protected Areas Database)

Fallback and enrichment layer.

Source:
<https://www.usgs.gov/programs/gap-analysis-project/pad-us-data-download>

Layer used:

```text
PADUS4_1Comb_DOD_Trib_NGP_Fee_Desig_Ease_State_NV
```

Purpose:

- fallback classification
- additional public land detail
- supplemental context

### 3. PLAD (BLM Public Lands Access Data)

Source:
<https://gbp-blm-egis.hub.arcgis.com/search?q=plad>

Two layers:

- `plad_routes_raw` (lines)
  - roads, trails, easements

- `plad_areas_raw` (polygons)
  - designated access areas

Purpose:

- determine legal access conditions

---

## Architecture

SQLite + SpatiaLite database:

```text
nevada_land.sqlite
```

Tables:

- `blm_sma_raw` → ownership (primary)
- `padus_raw` → fallback
- `plad_areas_raw` → access zones
- `plad_routes_raw` → access routes

All geometries normalized to:

```text
EPSG:4326 (WGS84)
```

---

## How It Works

### 1. Ownership Lookup

```sql
ST_Contains(blm_sma_raw.shape, point)
```

- if hit → classify via `ABBR`
- else → fallback to `padus_raw`

### 2. Access Area Check

```sql
ST_Contains(plad_areas_raw.shape, point)
```

- determines if inside known access area

### 3. Nearest Access Route

```sql
ORDER BY ST_Distance(plad_routes_raw.shape, point)
LIMIT 1
```

Returns:

- route name
- legal use
- access rights
- distance

### 4. Access Interpretation

| Distance | Meaning |
|----------|---------|
| 0–250 m | Nearby Access |
| 250 m–2 km | Possible Access Nearby |
| 2–10 km | Distant Access |
| >10 km | No Meaningful Nearby Access |

---

## Example Output

```json
{
  "ok": true,
  "state": "NV",
  "land_class": "BLM",
  "land_code": "BLM",
  "land_name": "Bureau of Land Management",
  "access_area_hit": false,
  "nearest_route_name": "SUNRISE PASS ROAD",
  "nearest_access_rights": "Public",
  "nearest_legal_use": "Road",
  "nearest_access_distance_m": 18387.2,
  "access_proximity": "No Meaningful Nearby Access",
  "access_summary": "No meaningful nearby public access route"
}
```

---

## How the Data Was Obtained

This Nevada build used four source datasets.

### 1. Nevada Surface Management Agency (SMA)

This became the primary ownership layer.

Downloaded as:

- File Geodatabase (`.gdb`)

Purpose:

- statewide land classification
- one dissolved ownership/status polygon per class

Classes discovered in the Nevada dataset:

- `BIA` → Bureau of Indian Affairs
- `BLM` → Bureau of Land Management
- `BR` → Bureau of Reclamation
- `DOD` → Department of Defense
- `DOE` → Department of Energy
- `FS` → Forest Service
- `FWS` → Fish and Wildlife Service
- `NPS` → National Park Service
- `NVST` → Nevada State
- `PVT` → Private
- `WTR` → Water

This was the backbone because it provided clean statewide ownership/status coverage.

### 2. PAD-US (Nevada)

This became the fallback / enrichment layer.

Downloaded as:

- Nevada File Geodatabase (`.gdb`)

Used layer:

```text
PADUS4_1Comb_DOD_Trib_NGP_Fee_Desig_Ease_State_NV
```

Purpose:

- fallback classification
- extra public-land detail
- additional context when primary ownership data is incomplete

### 3. PLAD Polygon Layer

This became the access area layer.

Downloaded as:

- File Geodatabase (`.gdb`)

Used layer:

```text
plad_poly
```

Purpose:

- identify whether a point falls inside a known public-access area

### 4. PLAD Line Layer

This became the access route layer.

Downloaded as:

- File Geodatabase (`.gdb`)

Used layer:

```text
plad_ln
```

Purpose:

- locate the nearest known legal access route
- evaluate access context

---

## Directory Layout

A clean local working layout was used:

```text
~/landdb/
  src/       raw downloaded source data
  data/      final SQLite database
  scripts/   Python lookup scripts
```

Example contents:

```text
~/landdb/src/
  PADUS4_1_StateNV.gdb
  _ags_data56A2302FA61B49B4B84EDC050DD7C48D.gdb
  8f9bb745-0699-44e8-a5a7-e6114edfbcc8.gdb
  bdf2ce83-9c19-411a-9812-fe34304e66bc.gdb
```

---

## Procedure: Building the Database

### 1. Install Required Packages

```bash
sudo apt update
sudo apt install -y \
  python3 python3-pip python3-venv \
  sqlite3 spatialite-bin libsqlite3-mod-spatialite \
  gdal-bin python3-gdal python3-shapely python3-requests \
  unzip curl
```

### 2. Create the Working Directories

```bash
mkdir -p ~/landdb/{src,data,scripts}
```

### 3. Put All Raw GIS Data in `src/`

Example:

```bash
mv ~/Downloads/*.zip ~/landdb/src/
cd ~/landdb/src
unzip '*.zip'
```

### 4. Inspect Each Dataset Before Import

Used `ogrinfo` to identify:

- layer names
- geometry type
- field names
- projection

Examples:

```bash
ogrinfo ./PADUS4_1_StateNV.gdb
ogrinfo ./PADUS4_1_StateNV.gdb PADUS4_1Comb_DOD_Trib_NGP_Fee_Desig_Ease_State_NV -so

ogrinfo ./_ags_data56A2302FA61B49B4B84EDC050DD7C48D.gdb
ogrinfo ./_ags_data56A2302FA61B49B4B84EDC050DD7C48D.gdb Land_Status_Dis -so

ogrinfo ./8f9bb745-0699-44e8-a5a7-e6114edfbcc8.gdb
ogrinfo ./8f9bb745-0699-44e8-a5a7-e6114edfbcc8.gdb plad_poly -so

ogrinfo ./bdf2ce83-9c19-411a-9812-fe34304e66bc.gdb
ogrinfo ./bdf2ce83-9c19-411a-9812-fe34304e66bc.gdb plad_ln -so
```

### 5. Create the SQLite / SpatiaLite Database

The first import creates the database.

#### First import: PAD-US

```bash
ogr2ogr \
  -f SQLite ~/landdb/data/nevada_land.sqlite \
  ./PADUS4_1_StateNV.gdb \
  PADUS4_1Comb_DOD_Trib_NGP_Fee_Desig_Ease_State_NV \
  -dsco SPATIALITE=YES \
  -nln padus_raw \
  -nlt PROMOTE_TO_MULTI \
  -t_srs EPSG:4326
```

#### Second import: Nevada ownership backbone

```bash
ogr2ogr \
  -update \
  -append \
  -f SQLite ~/landdb/data/nevada_land.sqlite \
  ./_ags_data56A2302FA61B49B4B84EDC050DD7C48D.gdb \
  Land_Status_Dis \
  -nln blm_sma_raw \
  -nlt PROMOTE_TO_MULTI \
  -t_srs EPSG:4326
```

#### Third import: PLAD access areas

```bash
ogr2ogr \
  -update \
  -append \
  -f SQLite ~/landdb/data/nevada_land.sqlite \
  ./8f9bb745-0699-44e8-a5a7-e6114edfbcc8.gdb \
  plad_poly \
  -nln plad_areas_raw \
  -nlt PROMOTE_TO_MULTI \
  -t_srs EPSG:4326
```

#### Fourth import: PLAD access routes

```bash
ogr2ogr \
  -update \
  -append \
  -f SQLite ~/landdb/data/nevada_land.sqlite \
  ./bdf2ce83-9c19-411a-9812-fe34304e66bc.gdb \
  plad_ln \
  -nln plad_routes_raw \
  -nlt PROMOTE_TO_MULTI \
  -t_srs EPSG:4326
```

### 6. Verify the Database

```bash
sqlite3 ~/landdb/data/nevada_land.sqlite
```

Inside SQLite:

```sql
SELECT load_extension('mod_spatialite');
.tables
SELECT COUNT(*) FROM padus_raw;
SELECT COUNT(*) FROM blm_sma_raw;
SELECT COUNT(*) FROM plad_areas_raw;
SELECT COUNT(*) FROM plad_routes_raw;
SELECT * FROM geometry_columns;
```

Expected result:

- `padus_raw` → 2750
- `blm_sma_raw` → 11
- `plad_areas_raw` → 86
- `plad_routes_raw` → 4556

All geometry columns normalized to:

- `shape`
- SRID `4326`

---

## Procedure: Building the Script

### 1. Create the Script File

```bash
nano ~/landdb/scripts/nv_land_lookup.py
```

### 2. Script Inputs

The script accepts:

```text
nv_land_lookup.py <lat> <lon>
```

Example:

```bash
~/landdb/scripts/nv_land_lookup.py 38.906517476261875 -119.68544478005626
```

### 3. Script Logic

The script performs three lookups.

#### Ownership lookup

Primary:

- `blm_sma_raw`

Fallback:

- `padus_raw`

The Nevada ownership layer uses `ABBR` codes mapped into human-readable classes:

- `BIA` → Reservation / Tribal
- `BLM` → BLM
- `FS` → National Forest
- `NPS` → National Park
- `FWS` → Fish & Wildlife
- `DOD` → Military
- `DOE` → DOE / Federal Restricted
- `BR` → Bureau of Reclamation
- `NVST` → State Land
- `PVT` → Private
- `WTR` → Water

#### Access-area lookup

Checks whether the point falls inside a PLAD access polygon.

#### Nearest-route lookup

Finds the nearest PLAD line feature and reports:

- route name
- route number
- access rights
- legal use
- seasonal restrictions
- approximate distance

### 4. Script Output

Returns JSON such as:

```json
{
  "ok": true,
  "state": "NV",
  "lat": 38.906517476261875,
  "lon": -119.68544478005626,
  "land_class": "BLM",
  "land_code": "BLM",
  "land_name": "Bureau of Land Management",
  "land_source": "blm_sma_raw",
  "fallback_unit_name": null,
  "access_area_hit": false,
  "access_area_name": null,
  "access_area_rights": null,
  "access_area_legal_use": null,
  "access_area_seasonal_use": null,
  "access_area_travel_plan": null,
  "nearest_route_name": "SUNRISE PASS ROAD",
  "nearest_route_no": null,
  "nearest_access_rights": "Public",
  "nearest_legal_use": "Road",
  "nearest_seasonal_use": "NONE",
  "nearest_travel_plan": "NO",
  "nearest_access_distance_m": 18387.2,
  "nearest_access_distance_km": 18.39,
  "access_proximity": "No Meaningful Nearby Access",
  "access_summary": "No meaningful nearby public access route"
}
```

### 5. Make the Script Executable

```bash
chmod +x ~/landdb/scripts/nv_land_lookup.py
```

### 6. Test With Known Points

Examples used during validation:

```bash
# BLM
~/landdb/scripts/nv_land_lookup.py 38.906517476261875 -119.68544478005626

# Private
~/landdb/scripts/nv_land_lookup.py 38.89611342721037 -119.71250308866239

# DOE
~/landdb/scripts/nv_land_lookup.py 36.66243585267991 -115.99712026985536

# Military
~/landdb/scripts/nv_land_lookup.py 36.23491075978155 -115.03403636331069
```

These validated that the ownership logic was working correctly.

---

## Key Build Lessons

### 1. Use File Geodatabase When Available

Preferred download order:

1. File Geodatabase
2. Shapefile
3. GeoJSON
4. avoid SQLite Geodatabase

### 2. Import Behavior Matters

The first SQLite import creates the database.

Subsequent imports must use:

```text
-update -append
```

Otherwise later imports can overwrite the database.

### 3. Normalize Everything to EPSG:4326

This makes GPS lookups straightforward.

### 4. Keep Ownership and Access Separate

Ownership tells you what the land is.

PLAD tells you how access is documented.

They are related, but not the same thing.

---

## Result

The Nevada build now supports:

- offline land ownership classification
- offline access-area detection
- offline nearest-route access context
- clean JSON output suitable for Node-RED or other automation systems

---

## Important Notes

- This is not a legal determination tool
- PLAD data is incomplete in some regions
- Distance calculations are approximate (not survey-grade)
- Ownership ≠ access

This system provides situational awareness, not legal advice.

---

## Scope

This implementation is:

- Nevada only
- based on Nevada-specific datasets and schemas

---

## Extending to Other States

The concept generalizes, but the data does not.

Each state may have:

- different datasets
- different schemas
- different field names
- different classification codes

Recommended approach:

- separate SQLite database per state:
  - `nv_land.sqlite`
  - `ca_land.sqlite`
  - `ut_land.sqlite`
- normalize outputs to a common schema
- keep state-specific mapping logic isolated

---

## Integration

The lookup is exposed as a CLI tool:

```text
nv_land_lookup.py <lat> <lon>
```

This makes it easy to integrate with:

- Node-RED (exec node)
- vehicle dashboards
- embedded systems
- offline automation workflows

---

## Summary

This project builds a practical offline geospatial engine that:

- identifies land ownership
- evaluates access context
- works without network connectivity
- integrates cleanly into automation systems

Nevada is the first implementation.

The architecture supports expansion to any state with appropriate data normalization.

---

## Future Work

- multi-state support
- better tribal boundary accuracy (AIANNH)
- access confidence scoring
- route filtering (motorized vs non-motorized)
- performance optimization (caching, persistent service)
- UI integration (map overlays, alerts)

---

## Author Notes

Built for real-world use:

- off-grid travel
- vehicle-based systems
- embedded control environments

Designed for reliability, not elegance.
