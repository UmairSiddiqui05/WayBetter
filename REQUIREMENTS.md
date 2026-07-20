# Launch Requirements

Distilled, numbered requirements for the **launch build**. Sources: [multimodal_park_and_ride_prd.md](multimodal_park_and_ride_prd.md) as amended by [PLAN.md](PLAN.md) (PLAN.md governs conflicts — see its "Launch-scope amendments" section). Use these IDs in tests, commits, and PROGRESS.md entries for traceability.

Legend: **[M]** must-have for launch · **[S]** should-have for launch · **[FF]** fast-follow (explicitly not launch)

## F — Functional

- **F-01 [M]** User enters origin (manual or current location) + destination (address/place autocomplete) + time (`leave_now` | `leave_at` | `arrive_by`).
- **F-02 [M]** System returns ranked multimodal route options including: park-and-ride hybrids (~top finalists), drive-all-the-way baseline, and pure-transit baseline.
- **F-03 [M]** Each route option reports: total time, total cost, drive/transit/walk/wait minutes, drive miles, transfer count, parking info + confidence, delay risk, per-component cost breakdown (gas/EV, parking, fares, tolls incl. congestion fee), and an explanation.
- **F-04 [M]** Candidate stations are generated corridor-wide (drive-time isochrone × precomputed transit accessibility, diversity quotas, destination-adjacent included), pruned to ~20; ~5 finalists get full geometry.
- **F-05 [M]** `arrive_by` plans backward per the canonical time model (OTP native arrive-by → boarding time → per-station parking buffer → Directions `arrive_by` drive leg).
- **F-06 [M]** Sorts: Best Overall, Fastest, Cheapest, Least Driving, Most Driving, Fewest Transfers, Best Parking. Engine additionally implements the remaining PRD modes (incl. emissions) behind the API even though UI defers them.
- **F-07 [M]** Filters: avoid tolls (toll-blind pruning skipped; `exclude=toll` on all candidates), avoid city driving (region `city_driving_zone` polygons, PostGIS intersection on driving legs, destination-in-zone behavior defined), max walk minutes.
- **F-08 [M]** Natural-language trip input → LLM → validated `TripRequest` (Pydantic schema; unknown fields rejected; missing critical fields → follow-up or safe defaults). LLM cannot invent stations, prices, schedules.
- **F-09 [M]** Route explanations generated only from computed metrics for top 3–5 routes; template-grounded.
- **F-10 [M]** Parking data shown per station: lot name, location, prices, payment method, restrictions, confidence, last-verified, source license — "unknown" honestly labeled; unknown-parking stations remain candidates (only known-unusable excluded).
- **F-11 [M]** GTFS-RT service alerts: polled per agency, matched by route/stop ID, shown sanitized/escaped/truncated (never HTML), reliability score penalized. Scheduled ETAs are **never** arithmetically adjusted from alert text.
- **F-12 [M]** Fares from effective-dated data files with source URLs (zone-pair NJT/LIRR/MNR with peak/off-peak; flat subway/PATH; CT tables). **Zero fare literals in code.** Adult profile at launch; enum extensible.
- **F-13 [M]** Tolls computed geometrically: route polyline × versioned direction-aware crossing geometries, E-ZPass/cash by payment profile, NYC congestion-zone entry detection.
- **F-14 [M]** Vehicle profiles: compact/sedan/SUV/hybrid/EV/custom (MPG or kWh/mi) driving gas/EV cost and emissions estimates.
- **F-15 [S]** Anonymous parking feedback (worked / full / closed) with rate limiting and sanitization.
- **F-16 [S]** Saved home/work + default preferences, device-local via `PreferenceStore` (no accounts).
- **F-17 [S]** Apple Maps / Google Maps handoff deep links for the driving leg.
- **F-18 [M]** Web client (Next.js + MapLibre): search form, NL input, route comparison table, route detail with map polylines, sort/filter controls, feedback.
- **F-19 [M]** iOS client (SwiftUI + MapKit), immediately post-web: same API, thin renderer, App Store submission.
- **F-20 [FF]** Local buses (MTA/CTtransit/NICE/Bee-Line), GBFS micromobility + bike/scooter toggle, TripUpdates-based ETA adjustment and delay-aware rerouting, accounts/sync, Android.

## N — Non-functional

- **N-01 [M]** All routing/scoring/labeling/explanation logic server-side; clients render display-ready JSON only.
- **N-02 [M]** Every user-facing data point carries provenance: `live | scheduled | estimated | unknown | user_reported | ai_generated` (+ `last_verified_at` where applicable). Required disclaimers per PRD §20.
- **N-03 [M]** Regions are data: region config = bounding box, timezone, feed registry, fare/toll/parking files, `city_driving_zone` polygons, agency rule modules. No agency conditionals in business logic; canonical station IDs mapped from `(region, feed_id, agency_id, gtfs_stop_id, feed_version)`.
- **N-04 [M]** Provider-agnostic interfaces: `DrivingProvider`, `TransitProvider`, `GeocodingProvider`, `LLMProvider`, `PreferenceStore`. Vendor swap = config + one adapter.
- **N-05 [M]** Request validation before any paid provider call (region bounds, radius/candidate caps, sane time window); rate limiting per IP + server-issued anonymous session token; provider keys server-side; Mapbox tokens domain-restricted; spend/quota alerts.
- **N-06 [M]** No client-supplied user identifiers pre-auth; nullable `user_id` in schema only.
- **N-07 [M]** Privacy: coordinates/request text excluded from prompts where possible, log redaction + short retention window, third-party processors documented.
- **N-08 [M]** Ops: OTP graph + precompute + feed metadata + cache version deploy as one atomic versioned bundle, built off-box, blue/green cutover after health-check trips; nightly encrypted off-box Postgres backups + documented restore drill; health checks + uptime monitoring.
- **N-09 [M]** Parking/fare/toll data recorded with source license/permission; no ToS-restricted scraping; OSM data ODbL-attributed.
- **N-10 [M]** Test floor: unit tests per scoring mode/filter; golden-fixture regression trips; edge/failure-injection suite (midnight, DST, holidays, no-route, provider timeout/null, permit-only parking, alert flood) — before human QA of 20–50 real trips vs Google/Apple.
- **N-11 [M]** Costs: single VPS ≈ $30/mo; external APIs within free tiers at portfolio scale.
