# 🛰️ Offline Land Ownership & Access Classification (Nevada v1)

MIT Licensed

## Overview
Offline system that converts GPS coordinates into land ownership classification and access context using local GIS data, with no internet required.

## Why
Determines if you are on public land, private land, or restricted land, and whether documented access exists nearby.

## Data Sources

### Nevada Surface Management Agency (Primary)
https://gbp-blm-egis.hub.arcgis.com

### PAD-US (Fallback)
https://www.usgs.gov/programs/gap-analysis-project/pad-us-data-download

Layer:
PADUS4_1Comb_DOD_Trib_NGP_Fee_Desig_Ease_State_NV

### PLAD (Access Data)
https://gbp-blm-egis.hub.arcgis.com/search?q=plad

Layers:
- plad_ln (routes)
- plad_poly (areas)

## Directory Structure

landdb/
  src/       raw GIS data
  data/      SQLite database
  scripts/   lookup script

## Build

### Install
sudo apt install sqlite3 spatialite-bin libsqlite3-mod-spatialite gdal-bin python3 unzip

### Create dirs
mkdir -p ~/landdb/{src,data,scripts}

### Import

# PAD-US (create DB)
ogr2ogr -f SQLite ~/landdb/data/nevada_land.sqlite \
  ./PADUS4_1_StateNV.gdb \
  PADUS4_1Comb_DOD_Trib_NGP_Fee_Desig_Ease_State_NV \
  -dsco SPATIALITE=YES -nln padus_raw -t_srs EPSG:4326

# SMA
ogr2ogr -update -append -f SQLite ~/landdb/data/nevada_land.sqlite \
  ./SMA.gdb Land_Status_Dis -nln blm_sma_raw -t_srs EPSG:4326

# PLAD poly
ogr2ogr -update -append -f SQLite ~/landdb/data/nevada_land.sqlite \
  ./PLAD_poly.gdb plad_poly -nln plad_areas_raw -t_srs EPSG:4326

# PLAD line
ogr2ogr -update -append -f SQLite ~/landdb/data/nevada_land.sqlite \
  ./PLAD_line.gdb plad_ln -nln plad_routes_raw -t_srs EPSG:4326

## Verify

sqlite3 ~/landdb/data/nevada_land.sqlite

SELECT load_extension('mod_spatialite');
.tables

## Script

scripts/nv_land_lookup.py <lat> <lon>

## Output

{
  "land_class": "BLM",
  "access_summary": "No meaningful nearby public access route"
}

## Notes

- Nevada only
- Ownership != Access
- PLAD is advisory, not complete

## Extend

Use same model for other states with new datasets.
