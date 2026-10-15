# DEMO SPRINT — Deloitte GPS portfolio demo (2026-10-14 → 2026-10-15)

**Status: CLOSED (2026-10-15, confirmed by the human).** PLAN.md is back on top of the
precedence list; this file no longer overrides anything and is kept as history (D-18, D-20). The
demo build it produced (OSRM + direct-GTFS adapters, the static Leaflet page, local uvicorn) keeps
running until the Mapbox/OTP/Next.js work replaces it; post-sprint work follows the normal plan
(first batch: D-21).

> **Scope extension (D-20, approved 2026-10-14):** the "LLM layer" row below is partly lifted
> for the demo: plain-words trip entry (`POST /trip/ai-parse`, local model per D-19, confirm
> before search) and voice by dictation (Handy, a separate app). Alerts, sessions UI and the
> rest stay out of scope. Everything under "Rules that STILL apply" still applies.

## Goal
One reliable, explainable, screen-shareable demo by **~7pm ET on 2026-10-14**, for a 30-minute
Deloitte Government & Public Services project-portfolio interview the next day (live demo +
technical Q&A, explained so a non-technical government client follows it). Reliability and
explainability beat completeness. The human must be able to explain every line.

## The demo
A commuter picks an origin in the suburbs and a Manhattan destination. WayBetter compares
**driving all the way in** against **2–4 park-and-ride options** on one rail corridor, with
door-to-door **time and total cost** for each (gas, congestion toll, parking, rail fare,
subway fare), ranks them, and draws them on a map.

## Scope overrides (temporary)
| Normal plan | Demo sprint |
|---|---|
| Docker Compose stack (`make up`) | **No Docker.** Run uvicorn locally. Keep all Docker files untouched for later. |
| Postgres/PostGIS + Redis required for readiness | Use only what the demo path needs. If no table is needed, don't add one. Make Redis optional, don't remove it. Readiness may report degraded. |
| OTP transit routing (D-05) | **Not tonight.** A `TransitProvider` adapter that reads the GTFS zip directly (next departure + ride time between two stations on one line). OTP adapter stays the Phase 2 plan. |
| Mapbox driving (D-05) | `DrivingProvider` adapter for the **public OSRM demo server** (`router.project-osrm.org`), with a timeout and an on-disk response cache so the demo works offline once warmed. Mapbox stays the production plan. |
| Next.js + MapLibre web client (A8) | **One static HTML page** served by FastAPI, Leaflet from a CDN, OSM tiles, no API keys. Calls the API and renders display-ready JSON only (N-01 still holds). |
| All 6 feeds, full region | **One corridor.** NJ Transit only if the human has portal access tonight; otherwise Metro-North (Westchester → Grand Central) or LIRR (Long Island → Penn/GCM). Feeds we already support: subway, LIRR, MNR. |
| ~60–75 human-verified parking stations | **3–6 lots** on the chosen corridor in `data/parking/`, each with source URL or `status: estimated` + a note. |
| LLM layer, alerts, sessions, sorts/filters | Out of scope. |

## Rules that STILL apply (these make the demo stronger — do not drop them)
- **API contract:** implement the existing `POST /api/v1/trip/search` from
  `docs/api-spec.yaml` (`TripSearchRequest` → `TripSearchResponse`, `RouteOption`,
  `RouteLeg`, `CostBreakdown`, `MoneyEstimate`, `Provenance`). A subset of fields is fine;
  **do not invent new paths** — `test_openapi_parity.py` fails on any path not in the contract.
  If the contract's session-token requirement blocks the demo, implement `POST /session`
  minimally rather than removing security from the spec. Any spec change = version bump +
  PROGRESS.md entry.
- **Providers behind interfaces (N-04):** OSRM and the GTFS reader sit behind
  `DrivingProvider` / `TransitProvider`. This is the interview answer to "how does this
  become production" (swap in Mapbox / OTP without touching business logic).
- **Zero fare/toll/price literals in code (F-12, D-13):** gas price, MPG, $9 congestion toll,
  Manhattan parking, rail fares, $3 subway fare all live in effective-dated files under
  `data/fares/`, `data/tolls/`, `data/parking/` with source + date.
- **Provenance (N-02):** every cost and time carries `scheduled | estimated | unknown`.
  Unknown stays unknown; never fabricate.
- Keep ruff/mypy/pytest green. Add focused tests for cost math and ranking.

## Order of work (stop and report after each step, 2–3 plain-English sentences)
1. `git pull` (local clone may be behind origin — PRs #1/#2 are already merged on GitHub; there
   are no branches to merge). Read PROGRESS.md, `backend/`, `data/regions/nyc-metro.yaml`,
   `docs/api-spec.yaml`. Report: what ingestion produces (files only, no DB tables), what's
   on disk, corridor recommendation.
2. Local run without Docker: venv, `make install`, uvicorn up, `/api/v1/docs` loads.
   `make fetch-feeds` for the corridor feed (GTFS zips are gitignored, so re-download).
3. Data files: lots, fares, tolls, gas/vehicle defaults.
4. Providers (OSRM driving, GTFS transit) + trip search service + `POST /trip/search`
   + tests.
5. Leaflet page: origin preset dropdown + destination, Compare button, map with drive leg,
   rail leg, lot markers; side panel of option cards (time, cost breakdown, winner
   highlighted). Clean, legible at screen-share size.
6. Warm the cache for 2–3 demo scenarios; confirm the demo runs with Wi-Fi off.
7. `DEMO.md`: start commands from a fresh terminal, demo scenarios + expected results,
   one-paragraph architecture, limitations, Phase 2 (OTP, Mapbox, NJT/PATH feeds,
   real-time, agency view of lot utilization, Docker/Hetzner deploy).

## Timeboxes
- Any single step > 45 min → stop and propose a simpler path.
- If `/trip/search` is not returning a real comparison by **~7pm ET**, stop; the human
  switches demos.
- No refactoring of working code, no features beyond this file.
- Commit after each step (`DEMO: …` + requirement IDs), push to `main`, log in PROGRESS.md.
