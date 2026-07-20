# Agent Work Orders

Per-agent briefs for the WayBetter build. Each agent reads: **this file (its own section), [CLAUDE.md](../CLAUDE.md), and the PLAN.md sections cited in its brief** — not the whole corpus. Requirement IDs refer to [REQUIREMENTS.md](../REQUIREMENTS.md). Before starting, claim your items in [PROGRESS.md](../PROGRESS.md); after finishing, log there.

**Dependency order:** A1 → A2 → (A3 ∥ A5-data) → A4 → A5 → A6 → A7 → A8 → (A9, A10). A3 and later can start once A1's scaffold merges; A8 can start UI shells against [docs/api-spec.yaml](api-spec.yaml) any time after A1.

---

## A1 — Scaffold & Infrastructure
**Reads:** PLAN §1–2. **Covers:** N-08, N-11 groundwork.
**Tasks:** Repo scaffold (backend/, web/, ios/, data/, docs/ per PRD §18); Docker Compose booting FastAPI skeleton + Postgres/PostGIS + Redis + OTP placeholder; `.env` loading (template: [.env.example](../.env.example)); health endpoints; CI green on the skeleton; Makefile or task runner for common commands.
**Done when:** `docker compose up` yields responding FastAPI + Postgres with PostGIS enabled + Redis on a fresh clone with only `.env` created; CI passes; PROGRESS.md updated.

## A2 — Data Ingestion (GTFS / OSM / OTP graph)
**Reads:** PLAN §2–4. **Covers:** N-03, N-08, N-09.
**Tasks:** Scripted, resumable downloads for launch feeds (NJT rail + commuter bus, LIRR, MNR, subway, PATH, CT rail — NJT needs portal credentials); feed validation + license recording; OSM NY-metro extract; **off-box OTP graph build script producing a versioned bundle** (graph + precompute + feed metadata + cache version); region config loader (bounding box, timezone, feed registry, city_driving_zone polygons); canonical station ID mapping tables from `(region, feed_id, agency_id, gtfs_stop_id, feed_version)`.
**Done when:** OTP serves locally from a built bundle and answers a Princeton Junction → NY Penn transit query with plausible NEC itineraries (human sanity-check logged); station mapping tables populated; every feed has license + retrieved-at recorded.

## A3 — Backend API & Models
**Reads:** PLAN §10, docs/api-spec.yaml. **Covers:** F-01, N-01, N-02, N-05, N-06.
**Tasks:** Pydantic models mirroring api-spec.yaml exactly (TripSearchRequest, RouteOption, RouteLeg, CostBreakdown, ParkingFacility, Provenance enum); all endpoints stubbed then wired; anonymous session issuance + rate limiting middleware; request validation (region bounds, caps, sane time window) **before any provider call**; error envelope; OpenAPI parity check against docs/api-spec.yaml in CI.
**Done when:** Every api-spec.yaml endpoint responds with schema-valid payloads (fixtures OK until A4); out-of-region request → 422 with zero provider calls (test proves it); 429 on rate-limit breach.

## A4 — Routing Core
**Reads:** PLAN §6. **Covers:** F-02, F-04, F-05, N-04.
**Tasks:** `DrivingProvider` + `TransitProvider` interfaces; OTP adapter; Mapbox adapter (Matrix chunked ≤10 coords for pruning; Directions on finalists; Directions `arrive_by` for arrive-by; `exclude=toll` path that skips Matrix pruning and runs on all ~20 candidates); candidate generator (isochrone × precomputed station→destination transit times, diversity quotas, destination-adjacent stations); canonical time model (region timezone; backward solve for arrive_by incl. per-station parking buffer); baselines (drive-all, pure-transit); route assembly into RouteOptions.
**Done when:** `POST /trip/search` returns real assembled park-and-ride itineraries + both baselines for the golden fixtures in [docs/verification.md](verification.md) §Fixtures, with correct arrive-by semantics (fixture G-03); all provider calls go through interfaces (grep-provable: no `mapbox`/`otp` imports outside providers/).

## A5 — Parking, Fares, Tolls, Costs
**Reads:** PLAN §5–7. **Covers:** F-10, F-12, F-13, F-14, N-09.
**Tasks:** Parking schema + seed top ~60–75 stations (source URL, license, last-verified; **flag every entry for human spot-check**); parking confidence rules; effective-dated fare tables (NJT/LIRR/MNR zone-pair with peak/off-peak, subway/PATH flat, CT) + GTFS-fares importer + staleness flag job; toll crossing geometries (direction-aware) + congestion-zone polygon + geometric toll estimator; gas/EV/emissions estimators from vehicle profile; CostBreakdown assembly with per-component provenance.
**Done when:** Golden fixtures return believable full cost breakdowns (fixture tolerances in verification.md); zero fare/toll literals in code (grep-provable — data files only); every parking row carries source + license + last_verified_at; human has spot-checked ≥10 parking entries and logged it.

## A6 — Scoring & Ranking
**Reads:** PLAN §6 (scoring), §12 (sort list). **Covers:** F-06, F-07.
**Tasks:** Classify all PRD modes + "Most Driving" into hard filters / preference weights / deterministic sort keys; implement the 7 launch sorts + engine-only modes (incl. emissions); city_driving_zone PostGIS intersection filter with destination-in-zone behavior; labels/badges/warnings; weight config file (tunable without code change).
**Done when:** Unit tests per mode pass, including: Most Driving returns a destination-edge-station route when one exists (fixture G-06); avoid-tolls never ranks on toll-allowed durations (test with mocked matrix); destination-in-Manhattan + avoid-city-driving keeps park-and-ride options and excludes/flags drive-all (fixture G-07).

## A7 — AI Layer & Alerts
**Reads:** PLAN §8–9. **Covers:** F-08, F-09, F-11, N-07.
**Tasks:** `LLMProvider` interface + Gemini 2.5 Flash-Lite adapter; NL → TripSearchRequest extraction with schema validation, unknown-field rejection, missing-critical-field handling (`/trip/ai-parse` contract); explanation generator (template-grounded, metrics-only input, top 3–5); GTFS-RT alert pollers per agency + route/stop matching + reliability penalty + sanitized/truncated display text; prompt logging redaction + retention window.
**Done when:** The 5 NL test cases from PRD §8.4 parse correctly (test suite); adversarial extraction tests pass (prompt-injection in trip text does not escape the schema); explanations cite only metrics present in the RouteOption (validator-enforced); a synthetic alert flood degrades gracefully (fixture E-08); swapping LLM provider is config + one file (prove with a stub provider in tests).

## A8 — Web Client
**Reads:** PLAN §12, docs/api-spec.yaml. **Covers:** F-18, F-16, F-17, N-01, N-02 (display side).
**Tasks:** Next.js scaffold; TS client **generated** from OpenAPI (never hand-written); search form + NL input; comparison table (7 sorts, 3 filters); route detail with MapLibre polylines; provenance labels + server-supplied disclaimers rendered verbatim; device-local saved places/prefs via `PreferenceStore`; Apple/Google Maps handoff links; feedback form; responsive mobile-first.
**Done when:** Full flow works against the real backend for all golden fixtures; no business logic in TS (no fare/score/label computation client-side — review-provable); Lighthouse mobile ≥ 90 performance/accessibility; deployed behind HTTPS domain.

## A9 — iOS Client
**Reads:** PLAN §13, docs/api-spec.yaml. **Covers:** F-19.
**Tasks:** SwiftUI app: search, results list, detail with MapKit polylines, sorts/filters, Apple Maps handoff, UserDefaults `PreferenceStore`; same API payloads rendered without recomputation; App Store metadata + privacy nutrition labels (matches N-07 policy); TestFlight then submission.
**Done when:** Feature parity with web for the golden fixtures on device; App Store submission accepted (review feedback logged).

## A10 — QA & Verification
**Reads:** [docs/verification.md](verification.md) (owns it). **Covers:** N-10.
**Tasks:** Implement golden-fixture regression suite (G-fixtures) as automated tests with recorded provider cassettes; edge/failure-injection suite (E-fixtures: midnight, DST, holiday, no-route, provider timeout/null, permit-only parking, alert flood); cross-client consistency check (web vs iOS render same payload); hallucination checks on explanations; maintain the human QA script and record the 20–50 real-trip comparison results.
**Done when:** CI runs G+E suites on every push; human QA round completed and logged with scoring-weight tuning outcomes.

---

**Standing rule for every agent:** if your brief conflicts with PLAN.md, PLAN.md wins; if reality conflicts with PLAN.md, stop and escalate in PROGRESS.md rather than improvising (CLAUDE.md workflow).
