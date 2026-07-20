# Progress Board

The single source of truth for **what is done, what is in progress, and what comes next**. Every AI agent (and the human) reads this before starting work and updates it after finishing.

## Protocol (agents: follow exactly)

1. Before working: read this file, [CLAUDE.md](CLAUDE.md), your brief in [docs/agent-tasks.md](docs/agent-tasks.md), and the relevant [PLAN.md](PLAN.md) section.
2. Claim work by moving an item to **In progress** with your agent role + date.
3. When done: move it to the checklist as `[x]`, and append a dated entry to the **Work log** (what changed, files touched, requirement IDs, anything the next agent must know — especially surprises and deviations).
4. Never delete log entries. Never mark something done that isn't verified (tests passing ≠ verified; see CLAUDE.md verification rules).
5. New work discovered mid-task goes to **Backlog / discovered**, not silently into scope.

## Status: pre-build. Planning approved (see PLAN-REVIEW-LOG.md). No code exists yet.

## In progress

_(nothing — build not started)_

## Phase 0 — Repo + data foundations
- [ ] Repo scaffold per PLAN §1 / PRD §18 (backend/, web/, ios/, data/, docs/)
- [ ] Docker Compose: FastAPI skeleton + Postgres/PostGIS + Redis boot locally
- [ ] NJ Transit developer-portal registration; confirm GTFS access + terms (PLAN risk item)
- [ ] Download + validate all launch GTFS feeds (NJT rail/bus, LIRR, MNR, subway, PATH, CT rail)
- [ ] OSM extract for NY metro region
- [ ] First OTP graph build (off-box) + serve locally; sample trip queries verified by human
- [ ] Region config schema (bounding box, timezone, feed registry, city_driving_zone polygons)
- [ ] Canonical station ID mapping tables
- [ ] Parking seed database: schema + first 10 NJT stations (human-verified)

## Phase 1 — Routing core
- [ ] TripRequest/RouteOption/RouteLeg Pydantic models + provenance enums (N-02)
- [ ] Provider interfaces + OTP transit adapter + Mapbox driving adapter (Matrix chunking, Directions finalists)
- [ ] Candidate station generator (isochrone × precomputed accessibility, quotas) (F-04)
- [ ] Time model incl. arrive_by backward solve (F-05)
- [ ] Baselines (drive-all, pure-transit) + route assembly
- [ ] POST /trip/search returns real itineraries end-to-end

## Phase 2 — Cost, parking, scoring
- [ ] Fare tables (effective-dated) + fare service (F-12)
- [ ] Toll geometries + congestion zone + toll estimator (F-13)
- [ ] Gas/EV/emissions estimators (F-14)
- [ ] Parking service + confidence rules + remaining seed stations (~60–75 total)
- [ ] Scoring engine: filters/weights/sort keys + all 7 launch sorts + unit tests (F-06, F-07)
- [ ] Golden-fixture regression suite (N-10)

## Phase 3 — AI layer
- [ ] LLMProvider interface + Gemini 2.5 Flash-Lite adapter
- [ ] NL → TripRequest extraction + validation + follow-up handling (F-08)
- [ ] Grounded route explanations (F-09)
- [ ] GTFS-RT alert poller + matching + scoring penalty (F-11)

## Phase 4 — Web client
- [ ] Next.js scaffold + generated TS client from OpenAPI
- [ ] Search form + NL input + results table + route detail + map polylines (F-18)
- [ ] Sort/filter controls; provenance labels + disclaimers (N-02)
- [ ] Rate limiting / session tokens / request validation live (N-05)
- [ ] Deploy: domain + HTTPS + monitoring + backups (N-08)

## Phase 5 — Verify + iOS
- [ ] Edge/failure-injection suite (N-10)
- [ ] Human QA: 20–50 real trips vs Google/Apple; scoring-weight tuning
- [ ] SwiftUI app: same API, map, list, detail, handoff (F-19)
- [ ] App Store submission

## Backlog / discovered
- Fast-follow package: local buses + GBFS micromobility (F-20)
- v1.1: TripUpdates → OTP, ETA adjustment, delay-aware rerouting
- Advanced sort/filter drawer (remaining PRD modes)
- Accounts (Sign in with Apple / magic link) when sync earns it

## Work log (append-only, newest first)

- **2026-07-19 — Claude (planning):** Pre-build tooling added: `.env.example` (env template, no hardcoded keys), `docs/api-spec.yaml` (contract-first OpenAPI v0.1 — the API contract until FastAPI generates the real one), `docs/agent-tasks.md` (per-agent work orders A1–A10 with definitions of done), `docs/verification.md` (G/E fixtures + human QA script and launch gate), `.github/workflows/ci.yml` (backend/web jobs skip gracefully until code exists; OpenAPI lint + secret-pattern guard active now). Repo pushed to https://github.com/UmairSiddiqui05/WayBetter. Build not started.

- **2026-07-19 — Claude (planning):** PLAN.md approved after 6-round adversarial Codex review (31/31 findings accepted; see PLAN-REVIEW-LOG.md). Created README.md, REQUIREMENTS.md, PROGRESS.md, DECISIONS.md, CLAUDE.md. No code written. Next: Phase 0 scaffold.
