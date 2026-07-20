# CLAUDE.md — Standing instructions for AI coding agents

You are building **WayBetter**, the park-and-ride trip planner. Read this file fully before any work.

## Document precedence (conflicts resolve top-down)

1. **[PLAN.md](PLAN.md)** — approved implementation plan. Authoritative for the launch build, including its PRD amendments section.
2. **[REQUIREMENTS.md](REQUIREMENTS.md)** — numbered launch requirements. Cite IDs (F-xx/N-xx) in commits and tests.
3. **[DECISIONS.md](DECISIONS.md)** — locked decisions. Do not relitigate; raise evidence to the human instead.
4. **[multimodal_park_and_ride_prd.md](multimodal_park_and_ride_prd.md)** — long-term product vision. Context, not launch spec.

## Workflow (non-negotiable)

- **Before work:** read [PROGRESS.md](PROGRESS.md); claim your item there.
- **After work:** update PROGRESS.md (checklist + append-only work log entry: date, role, what changed, files, requirement IDs, surprises). Work that isn't logged didn't happen.
- **Scope discipline:** new work discovered mid-task → PROGRESS.md backlog, not silent scope growth. Material deviation from PLAN.md → stop, write it up, ask the human.
- **Verification:** "done" means exercised end-to-end, not "compiles" or "tests pass." Routing outputs need a sanity-checked real itinerary (e.g., Princeton Jct → NYU arrive-by 9am returns plausible NEC trips). Anything touching parking prices, fares, or tolls needs a human spot-check before it's marked done.
- **Commits:** small, scoped, message references requirement IDs (e.g., `F-04: candidate generator isochrone query`).

## Hard architecture rules

- **All logic server-side.** Clients render display-ready JSON. If you're writing scoring/labeling/explanation logic in TypeScript or Swift, you're in the wrong layer (N-01).
- **Providers behind interfaces.** External services (driving, transit, geocoding, LLM, preference storage) are only touched through `DrivingProvider` / `TransitProvider` / `GeocodingProvider` / `LLMProvider` / `PreferenceStore`. No vendor SDK calls in business logic (N-04).
- **Regions are data.** No agency names or region facts (fares, tolls, timezones, zone polygons) in code — they live in region config + data files + per-agency rule modules (N-03). **Zero fare/toll literals in code, ever** (F-12).
- **LLM boundaries.** The LLM parses input into Pydantic-validated `TripRequest`s and phrases explanations from computed metrics. It never generates routes, prices, schedules, or availability. All LLM output is schema-validated; unknown fields rejected (F-08, F-09, D-11).
- **Provenance everywhere.** Every user-facing datum carries its status enum (`live|scheduled|estimated|unknown|user_reported|ai_generated`) (N-02). When data is unknown, say unknown — never fabricate a plausible value.
- **Paid calls are guarded.** Validate region bounds/caps before any Mapbox/Gemini call; respect rate limits; keys stay server-side (N-05).
- **No client-supplied identity.** Anonymous session tokens are server-issued; `user_id` is schema-only until auth exists (N-06).

## Data rules

- Transit/parking/fare/toll data comes only from official agency sources, municipal open data, OSM (with ODbL attribution), or human-entered facts — with source URL + license + last-verified date recorded (N-09). No scraping ToS-restricted sources.
- GTFS feeds, graph artifacts, precompute tables, and feed metadata version together as one atomic bundle (N-08).

## Stack quick reference

Python 3.12+ / FastAPI / Pydantic v2 / SQLAlchemy + PostGIS / Redis / OTP 2.x (Java, Docker) / Next.js + MapLibre (web) / SwiftUI + MapKit (iOS) / Docker Compose. Tests: pytest (backend). TS client generated from OpenAPI — never hand-written.

## Secrets

Via environment / `.env` (gitignored; keep `.env.example` current). Never commit keys, never log them, never put them in client code.
