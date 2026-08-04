# Progress Board

The single source of truth for **what is done, what is in progress, and what comes next**. Every AI agent (and the human) reads this before starting work and updates it after finishing.

## Protocol (agents: follow exactly)

1. Before working: read this file, [CLAUDE.md](CLAUDE.md), your brief in [docs/agent-tasks.md](docs/agent-tasks.md), and the relevant [PLAN.md](PLAN.md) section.
2. Claim work by moving an item to **In progress** with your agent role + date.
3. When done: move it to the checklist as `[x]`, and append a dated entry to the **Work log** (what changed, files touched, requirement IDs, anything the next agent must know — especially surprises and deviations).
4. Never delete log entries. Never mark something done that isn't verified (tests passing ≠ verified; see CLAUDE.md verification rules).
5. New work discovered mid-task goes to **Backlog / discovered**, not silently into scope.

## Status: build started. A1 scaffold landed; Docker stack awaits one human verification step.

## In progress

- **A1 — Scaffold & Infrastructure** (Claude, 2026-08-04) — code complete, one item unverified.
  **Human action needed:** run `make up` on a machine with Docker Hub access and confirm
  `/readyz` reports every required component `ok`. The agent environment's egress policy
  denies `production.cloudfront.docker.com`, so **no container image could be pulled** and
  `docker compose up` was never executed. Everything not requiring an image pull was
  verified — see the work-log entry below for exactly what.

## Phase 0 — Repo + data foundations
- [x] Repo scaffold per PLAN §1 / PRD §18 (backend/, web/, ios/, data/, docs/) — `web/` and `ios/` are documented placeholders; their scaffolds belong to A8/A9 (a stub `web/package.json` would turn the CI web job green without proving anything)
- [ ] Docker Compose: FastAPI skeleton + Postgres/PostGIS + Redis boot locally — **compose/Dockerfile/init SQL written and statically validated; never booted (image pulls blocked). Unverified until a human runs `make up`.**
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
- **A1 → A3 handoff:** `backend/tests/test_openapi_parity.py` currently asserts the generated
  schema is a *subset* of docs/api-spec.yaml (A1 ships zero contract endpoints). When A3
  finishes wiring, flip `test_contract_coverage_report` to assert set equality so a dropped
  endpoint fails CI.
- **Remove the mypy escape hatch:** `.github/workflows/ci.yml` runs `mypy app || true`. mypy
  strict passes cleanly on the A1 scaffold, so the `|| true` can go as soon as a second agent
  confirms it stays clean on their code. Left in place — changing CI is not A1's brief.
- **Alembic migrations:** `app/db/session.py` declares `Base` but there is no migration tool
  yet. A3 (first tables) should add Alembic rather than `create_all`, so PostGIS columns and
  indexes are reviewable in version control.
- **Backups + restore drill (N-08):** compose has named volumes but no backup job. Needs the
  nightly encrypted off-box dump and a documented restore drill before launch. Not A1's
  brief (deploy-time work); logged so it is not forgotten.
- **`web/` and `ios/` are empty placeholders** — CI's web job stays skipped until A8 adds
  `web/package.json`.
- Fast-follow package: local buses + GBFS micromobility (F-20)
- v1.1: TripUpdates → OTP, ETA adjustment, delay-aware rerouting
- Advanced sort/filter drawer (remaining PRD modes)
- Accounts (Sign in with Apple / magic link) when sync earns it

## Open questions for human review

1. **Docker Hub egress (blocker for the last A1 checkbox).** The agent sandbox's egress policy
   returns 403 for `production.cloudfront.docker.com`, so `python:3.12-slim`, `postgis/postgis`,
   `redis`, and the OTP image cannot be pulled there. Nothing in the repo needs to change —
   but until someone runs `make up` somewhere with registry access, the compose stack is
   *written and statically validated*, not *proven*. This will bite A2 harder: the OTP graph
   build needs the OTP image.
2. **Health endpoints are not in the API contract.** The A1 brief asks for health endpoints;
   docs/api-spec.yaml defines none, and the run rules say do not deviate from the contract.
   Resolution taken: `/healthz` and `/readyz` live at the **root**, outside `/api/v1`, and are
   excluded from the generated OpenAPI, so the generated schema stays an exact subset of the
   contract (enforced by `test_openapi_parity.py`). The contract's own `/providers/status`
   endpoint — *upstream provider* health, a different question — is left to A3. **No spec
   change was made and no version bump was needed.** Confirm this reading.
3. **Compose file location deviates from PRD §18**, which puts `docker-compose.yml` under
   `backend/`. It is at the repo root here because it orchestrates db/redis/otp alongside the
   API, and PLAN §1–2 treats the stack as a whole-repo concern (PLAN governs conflicts).
   Similarly `backend/tests/` sits beside `app/` rather than inside it. Both are cosmetic;
   flag if you want them moved.
4. **OTP runs behind a compose profile**, so plain `make up` does not start it. It cannot boot
   without a graph bundle, and bundles are built off-box by A2 (N-08). `make up-otp` starts it
   and refuses if `data/otp-graphs/current` is missing. Confirm this is the intended shape for
   the blue/green cutover story.
5. **NJ Transit developer-portal registration is still unstarted** and is blocked on a human:
   it needs an account and terms acceptance, which this run is not permitted to do (PLAN risk
   item, Phase 0 checklist).

## Work log (append-only, newest first)

- **2026-08-04 — Claude (A1, Scaffold & Infrastructure):** First code in the repo. Branch
  `agent/a1-scaffold`. Requirement IDs: **N-08, N-11** (brief scope), touching **N-01, N-02,
  N-03, N-04, N-05, N-06** only as documented seams for later agents — no business logic written.

  **What changed.** FastAPI skeleton (`backend/app/`): application factory with OpenAPI metadata
  mirroring docs/api-spec.yaml; `config.py` reading **every** value from the environment with
  secrets as `SecretStr` and a production guard that refuses to boot on the `.env.example`
  placeholder `SESSION_TOKEN_SECRET`; structlog setup; async SQLAlchemy engine + `Base`;
  Redis client; infra probes for Postgres/PostGIS/Redis/OTP; ops endpoints `/healthz`
  (dependency-free liveness) and `/readyz` (503 when a required component is down). Empty
  `/api/v1` router for A3. Root `docker-compose.yml` (api + db + redis, OTP behind an `otp`
  profile), `backend/Dockerfile` (multi-stage, non-root, healthcheck), PostGIS init SQL,
  `Makefile`, `data/` tree with a README stating the source/license/verification rules (N-09),
  placeholder READMEs for `web/` and `ios/`.

  **Files:** `backend/` (pyproject.toml, Dockerfile, .dockerignore, README.md, app/{__init__,
  config,logging,main}.py, app/api/{__init__,health}.py, app/api/v1/{__init__,router}.py,
  app/db/{__init__,session}.py, app/cache/{__init__,client}.py, app/health/{__init__,probes}.py,
  tests/{conftest,test_health,test_config,test_openapi_parity,test_env_example}.py),
  `docker-compose.yml`, `docker/postgres/init/01-postgis.sql`, `Makefile`, `data/README.md` +
  eight `data/*/` dirs, `web/README.md`, `ios/README.md`, `.env.example` (extended),
  `.gitignore` (extended), `PROGRESS.md`.

  **Verified (commands run, output in the PR body).** ruff lint + format clean; **mypy strict
  clean** (14 source files); **21 pytest tests pass** with no datastore required; uvicorn boots
  and serves `/healthz`, `/readyz`, `/api/v1/docs`, `/api/v1/openapi.json`; `docker compose
  config` validates and resolves `.env` correctly, with `otp` excluded from the default profile;
  redocly lints the contract (warnings only, all pre-existing). The readiness path was then
  exercised against **real Postgres 16 + PostGIS 3.4.2 + Redis** installed natively — the same
  versions `docker-compose.yml` pins — covering four states: all-up → 200 `ready`; PostGIS
  extension missing → 503 `degraded`; Redis stopped → 503 `down`; nothing running → 503. OTP
  down never gates readiness. `docker/postgres/init/01-postgis.sql` was applied verbatim to that
  real database and a PostGIS geometry query returned correctly.

  **NOT verified — do not treat as done.** `docker compose up` was **never executed**. The
  sandbox egress policy answers 403 for `production.cloudfront.docker.com`, so no image
  (`python:3.12-slim`, `postgis/postgis:16-3.4`, `redis:7-alpine`, OTP) could be pulled. That
  means the **Dockerfile has never been built**, the containers have never started, and
  service-to-service networking, `depends_on` healthcheck ordering, and the container
  `HEALTHCHECK` are all unproven. The A1 brief's definition of done ("`docker compose up` yields
  responding FastAPI + Postgres with PostGIS + Redis on a fresh clone") is therefore **not met**
  — the Phase 0 checkbox stays unchecked until a human runs `make up`. CI has also not been
  observed green on the skeleton yet; it runs for the first time on this PR.

  **Surprises / decisions.** (a) Health endpoints are absent from docs/api-spec.yaml while the
  brief requires them — resolved by putting them at the root, outside `/api/v1`, and excluding
  them from the generated OpenAPI, so no contract change or version bump was needed; see Open
  Question 2. (b) Docker Compose's `env_file` parser reads `KEY=   # comment` as the literal
  value `# comment` — `SENTRY_DSN` was silently becoming `"# optional"`. Fixed in `.env.example`
  by moving the comment to its own line; caught by inspecting `docker compose config` output,
  which is why that inspection is worth repeating. (c) `test_env_example.py` now fails the build
  if a `Settings` field or a compose `${VAR}` has no `.env.example` entry (or vice versa) — the
  "fresh clone doesn't start" failure mode, made mechanical. (d) OTP sits behind a compose
  profile because it cannot start without an A2 graph bundle. (e) Compose lives at the repo root
  rather than `backend/` as PRD §18 suggests; PLAN §1–2 governs. (f) No provider interfaces,
  Pydantic contract models, or region loader were written — those are A3/A4/A2's briefs, and
  pre-stubbing them would have been silent scope growth.

- **2026-07-19 — Claude (planning):** Pre-build tooling added: `.env.example` (env template, no hardcoded keys), `docs/api-spec.yaml` (contract-first OpenAPI v0.1 — the API contract until FastAPI generates the real one), `docs/agent-tasks.md` (per-agent work orders A1–A10 with definitions of done), `docs/verification.md` (G/E fixtures + human QA script and launch gate), `.github/workflows/ci.yml` (backend/web jobs skip gracefully until code exists; OpenAPI lint + secret-pattern guard active now). Repo pushed to https://github.com/UmairSiddiqui05/WayBetter. Build not started.

- **2026-07-19 — Claude (planning):** PLAN.md approved after 6-round adversarial Codex review (31/31 findings accepted; see PLAN-REVIEW-LOG.md). Created README.md, REQUIREMENTS.md, PROGRESS.md, DECISIONS.md, CLAUDE.md. No code written. Next: Phase 0 scaffold.
