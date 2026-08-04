# City-driving zone polygons — NOT YET SOURCED

`data/regions/nyc-metro.yaml` declares three `city_driving_zones`, and the
`avoid_city_driving` filter (F-07) intersects driving-leg polylines against them
in PostGIS. **None of the GeoJSON files exist yet**, so the filter has nothing to
test against and fixture G-07 cannot pass.

They are deliberately absent rather than approximated. A hand-drawn "close
enough" Manhattan outline is a fabricated value that produces confidently wrong
filter results — exactly what CLAUDE.md's "when data is unknown, say unknown"
rule exists to prevent. `make check-region` reports them as missing.

## What to fetch

| File | Source | Notes |
|---|---|---|
| `manhattan.geojson` | NYC Open Data — *Borough Boundaries* (Department of City Planning) | Take the Manhattan feature. Decide explicitly whether Marble Hill and the islands belong in the driving zone. |
| `downtown-newark.geojson` | Newark / NJGIN open data, or an OSM-derived boundary (ODbL attribution required, N-09) | "Downtown" is not an administrative boundary — draw it deliberately and write down the definition used. |
| `downtown-jersey-city.geojson` | Jersey City open data, or OSM-derived (ODbL) | Same caveat. |

The NYC congestion-relief zone is a **separate** polygon and belongs with the
toll data (F-13), not here: entering it costs money, which is not the same
question as whether a driver wants to be in city traffic.

## Requirements for each file

- WGS84 (EPSG:4326), a GeoJSON `Polygon` or `MultiPolygon` `Feature`.
- A sibling `<name>.source.json` recording source URL, licence, and retrieval
  date (N-09) — the same discipline every other data file follows.
- The choices behind a non-administrative boundary written down, so the next
  person can tell a deliberate line from a sloppy one.
