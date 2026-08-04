# data/

Regions are data, not code (N-03, D-08). Everything an agency or a region knows
about itself lives here — not in `backend/app`. **Zero fare or toll literals in
code, ever** (F-12, F-13).

| Directory | Contents | Owner |
|---|---|---|
| `regions/` | Region configs: bounding box, timezone, feed registry, graph bundle reference, `city_driving_zone` polygons, pointers to the fare/toll/parking files below | A2 |
| `gtfs/` | Downloaded GTFS static feeds plus a metadata record per feed (source URL, license, retrieved-at, feed version) — N-09 | A2 |
| `osm/` | OSM extracts for the region, ODbL-attributed | A2 |
| `otp-graphs/` | Built OTP graph bundles. `current/` is the symlink or directory the `otp` Compose service serves; bundles are built **off-box** and version together with precompute tables and feed metadata (N-08) | A2 |
| `parking/` | Seed parking facilities: prices, restrictions, capacity, source URL, license, `last_verified_at`. Every row needs human spot-check before it is trusted (D-09) | A5 |
| `fares/` | Effective-dated fare tables with source URLs (zone-pair and flat) | A5 |
| `tolls/` | Direction-aware toll-crossing geometries, E-ZPass/cash rates, congestion-zone polygon | A5 |
| `gbfs/` | Micromobility feeds — fast-follow, empty at launch (F-20) | — |

## Rules

- Every file records **source URL, license/permission, and retrieval or
  verification date**. No ToS-restricted scraping (N-09).
- Feed archives and graph artifacts are fetched by scripts, not committed —
  `.gitignore` excludes `*.zip`, `*.pbf`, and built graphs. Metadata files
  describing them *are* committed.
- Fare and toll tables are effective-dated; a refresh job flags tables past
  their verification window (E-12).
