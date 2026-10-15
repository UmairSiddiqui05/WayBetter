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

- **DEMO SPRINT (D-18)** (Claude, 2026-10-14) — see [DEMO-SPRINT.md](DEMO-SPRINT.md). Corridor:
  **NJ Transit Northeast Corridor → NY Penn** (human switched from the Harlem Line once NJT portal
  access arrived, 2026-10-14). **All 7 steps done** (2026-10-14). Follow-up: daily round-trip view (API v0.2.0) added 2026-10-14. Demo guide: [DEMO.md](DEMO.md). Remaining human items: price spot-check; close the sprint after the interview.

- **A2 — Data Ingestion** (Claude, 2026-08-04) — *keyless subset only*, on branch `agent/a2-ingestion`.
  Region config + loader, GTFS fetch/validate/provenance, and canonical station IDs are done and
  exercised against the three real MTA feeds. Still open: PATH + CT rail feed URLs (hosts
  unreachable here), NJ Transit (B-3), the three city-driving zone polygons, the OSM extract,
  and the OTP graph build. A2 is **not** done.

- **A1 — Scaffold & Infrastructure** (Claude, 2026-08-04) — code complete, one item unverified.
  **Human action needed:** run `make up` on a machine with Docker Hub access and confirm
  `/readyz` reports every required component `ok`. The agent environment's egress policy
  denies `production.cloudfront.docker.com`, so **no container image could be pulled** and
  `docker compose up` was never executed. Everything not requiring an image pull was
  verified — see the work-log entry below for exactly what.

## Phase 0 — Repo + data foundations
- [x] Repo scaffold per PLAN §1 / PRD §18 (backend/, web/, ios/, data/, docs/) — `web/` and `ios/` are documented placeholders; their scaffolds belong to A8/A9 (a stub `web/package.json` would turn the CI web job green without proving anything)
- [ ] Docker Compose: FastAPI skeleton + Postgres/PostGIS + Redis boot locally — **compose/Dockerfile/init SQL written and statically validated; never booted (image pulls blocked). Unverified until a human runs `make up`.**
- [ ] NJ Transit developer-portal registration; confirm GTFS access + terms (PLAN risk item) — **blocker B-3, human only**
- [ ] Download + validate all launch GTFS feeds (NJT rail/bus, LIRR, MNR, subway, PATH, CT rail) — **3 of 6 done and verified end-to-end** (subway, LIRR, MNR: downloaded, validated, provenance recorded). PATH + CT rail unreachable from the agent environment; NJT needs the portal account. Tooling handles all six.
- [ ] OSM extract for NY metro region — **`osm-plan` generates the pipeline from region config; never run** (download.geofabrik.de denied by egress policy)
- [ ] First OTP graph build (off-box) + serve locally; sample trip queries verified by human — blocked by B-2 (no OTP image) and by the missing OSM extract
- [x] Region config schema (bounding box, timezone, feed registry, city_driving_zone polygons) — schema, loader, and `data/regions/nyc-metro.yaml` shipped. **Zone polygons themselves are not sourced** (see `data/regions/zones/README.md`); `make check-region` reports them missing.
- [x] Canonical station ID mapping tables — 737 stations across three feeds in `data/regions/nyc-metro-stations.csv`, keyed `(region, feed_id, agency_id, gtfs_stop_id, feed_version)`. Grows as the remaining feeds land.
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

- **Ranking with unknown costs** (found 2026-10-14, `demo/nl-parse`): an option whose total excludes an unknown component (e.g. drive-in to Javits, parking unknown) is ranked and badged on its partial total. Consider ranking complete-cost options ahead for `cheapest`/`best_overall`, or withholding the Cheapest badge from incomplete options. Needs a human product call.
- **Send total statuses from the server (N-02):** `CostBreakdown.total` and `RouteOption.total_minutes`
  carry no provenance, so the demo page rolls up the parts' statuses for display. Add
  `total_provenance` (and a minutes status) in the next API version so the client renders it
  instead (found 2026-10-14 during the page redesign).
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

## Blockers needing a human (2026-08-04)

- **B-1 — This session cannot push. A1's commits exist only as patch files.**
  `git push` returns `403` on `git-receive-pack`, and the GitHub API returns
  `403 Resource not accessible by integration` for branch creation, so the agent could
  neither push `agent/a1-scaffold` nor open the PR the run asked for. Reads work fine
  (`git fetch` succeeds); the integration is read-only. Fix: grant the Claude GitHub App
  write access to `UmairSiddiqui05/WayBetter` (Claude GitHub settings), then apply the
  patches the run handed over — `git am` the four-commit series, or fetch from the bundle,
  and push `agent/a1-scaffold`. **Nothing is lost as long as those patch files are saved:
  the container is ephemeral and its local commits go away with it.**
- **B-2 — No container image can be pulled here.** Egress policy answers 403 for
  `production.cloudfront.docker.com`. Blocks the last A1 checkbox (below) and will block
  A2's OTP graph build.
- **B-3 — NJ Transit developer portal.** Needs an account and terms acceptance; this run is
  not permitted to create accounts or accept terms. Human task, unchanged from Phase 0.
- **B-4 — Agency websites are unreachable from the agent environment.** Egress policy denies
  `panynj.gov`, `cttransit.com`, `mta.info`, and `download.geofabrik.de`; only the MTA feed
  bucket (`rrgtfsfeeds.s3.amazonaws.com`) is allowed. Consequences: PATH and CT rail feed URLs
  are unconfirmed, the OSM extract cannot be built, and **no feed licence could be read**, so
  every `license.verified` in the region config is `false`. A human with a browser resolves all
  of these in about ten minutes.
- **B-5 — City-driving zone polygons are unsourced.** `avoid_city_driving` (F-07) and fixture
  G-07 cannot work until `data/regions/zones/*.geojson` exist. They were left absent rather than
  approximated; see `data/regions/zones/README.md` for the datasets to fetch.

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

- **2026-10-14 — Claude (DEMO SPRINT extension, plain-words box on the demo page):** Fast-forwarded
  `main` to `demo/nl-parse` (it already contained main's page round 4; the redesign chat was idle with
  its work committed). The `#ask` slot on the page is now a text box ("Or say it in plain words",
  Enter or **Read it**) that posts `{text}` to `POST /api/v1/trip/ai-parse` with `X-Session-Token`
  (401 → new session, retried once, same as search). It renders the response as "Here's what I
  understood": one row per `interpretation` item with `value_label` in the page's status type
  (dashed = ai_generated, dotted = estimated, red = unknown), the status word, a **default** marker
  when `is_default`, then `clarifying_question`, `missing_fields` and `parser` / `parser_note`. Place
  notes (how the place was found plus the ODbL attribution) stay on screen; the other notes ("Default:
  …", "Read from your words") are in the row tooltip, to keep the results near the top. When
  `missing_fields` is empty the page copies `draft` into the form (a place goes to the preset with the
  same coordinates, otherwise it's added to the list as the server labelled it; `target_time` to Leave
  at; `return_time` (or the corridor default the interpretation reports) and `toll_payment` to the
  Home / Tolls chips for this page view only, not saved; `sort_mode` to the rank tab) and runs the
  normal search. Otherwise it shows the question and leaves the form alone. No parsing, defaults or
  place logic in the page (N-01). **Also changed:** a row's single tag is now the server label that
  matches the active rank tab when the row has one (else its first label, as before), so under
  Cheapest Metropark shows "Cheapest" instead of "Best overall"; the tag is green for the active
  tab's winner. **Verified** on port 8020 (new `waybetter-api-dev` entry in `.claude/launch.json`):
  the DeLucia's sentence → Ollama qwen3:8b → origin Raritan (town center), approximate, with the
  question; destination Javits; leave 7:00 AM (default); Cheapest tab, row 1 **Metropark, tag
  Cheapest, $29.40**, Drive all the way $30.55 with parking unknown. At 375 px: no horizontal scroll;
  "from somewhere to the office tomorrow at 8" shows From/To unknown, the question and "Needs: From,
  To", and the form stays untouched. No console errors. `make check` green: ruff, mypy, pytest 220
  (`test_natural_language_slot_is_reserved` replaced by `test_plain_words_box_posts_to_ai_parse`;
  the placeholder avoids the sort-mode words the no-hard-coded-sorts test forbids).
  Files: `backend/app/web/index.html`, `backend/tests/test_web_page.py`, `.claude/launch.json`.
  Requirements: F-08, F-18, N-01, N-02. **Surprise:** after a plain-words search the results are
  below the understood box and the form, so on a laptop screen the presenter scrolls down to see them.

- **2026-10-14 — Claude (DEMO SPRINT extension, branch `demo/nl-parse` — human-approved items 1, 12, 13, 14, 23):**
  Plain-words trip requests. **Status: all 5 steps done**; branch pushed, not merged (a later chat merges).
  (1) Startup preload: the trip service (GTFS load) plus one preset warm-up search run on a daemon
  thread at startup, so `/healthz` answers at once (18 ms measured) and the first search is fast
  (9 ms vs 3.3 s cold, port 8010); skipped when `ENVIRONMENT=test` or the GTFS zip is missing.
  (2) **API v0.3.0** (`docs/api-spec.yaml` + `app/__init__.py`): `POST /trip/ai-parse` implemented
  (session required, text 1–1000 chars). Additive response fields `interpretation` (field,
  value_label, provenance, is_default, note), `parser`, `parser_note`. **Contract deviation, logged:**
  the spec's `draft` was `$ref TripSearchRequest`, whose origin/destination are required, so an
  unresolved place could not be represented without guessing; added `TripSearchDraft` (same field
  names, places nullable; unresolved ones go to `missing_fields`). `LLMProvider` protocol (N-04) in
  `providers/base.py`; deterministic `RulesParser` adapter; one `TripParseService` resolves places,
  dates and defaults for whichever parser ran. Arrive-by goes to `missing_fields` (search doesn't
  support it). Corridor data gained `commute.default_departure_time` (07:00, marked default).
  Also: `tests/conftest.py` sets `ENVIRONMENT=test` at import — locally, `.env` was leaking into the
  settings singleton during collection and `test_healthz_is_dependency_free` failed on main too.
  (3) Verified places: corridor `Place` gained `aliases`, `town`, `source`. Added origin **Raritan
  (town center)** 40.5671, -74.6347 (one Nominatim lookup, borough relation 170844, ODbL) and
  destination **Javits Center (429 11th Ave)** 40.7584, -74.0022 (OSM, ODbL). Javits
  `in_congestion_relief_zone: true` — **human-confirmed 2026-10-14** against the MTA zone text
  (11th Ave is a local street south of 60 St); `parking_area: null` — **human decision
  2026-10-14**, no sourced rate, so drive-in parking shows unknown. Resolution: normalized name /
  alias / town match, small typos via difflib (≥ 0.88), filler words ignored; "<business> in
  <known town>" → that town, `estimated`, value labelled approximate, plus a clarifying question;
  anything else → `missing_fields` + question. `make warm-cache` now covers 4 × 3 presets (66 routes).
  **Surprise (backlog):** with Javits parking unknown, the drive option's total excludes parking,
  so under `best_overall` "Drive all the way" can rank first (Princeton → Javits $42.01*, flagged
  "Some costs are unknown"). `cheapest` still ranks Metropark first for every Javits pair.
  (4) Local model (**D-19**): `OllamaProvider` (`providers/ollama.py`, plain httpx to `/api/chat`)
  with `format` = `ParsedTrip` JSON schema (extra=forbid), temperature 0, `think: false`, 20 s
  timeout, `keep_alive` 30 m, `model_validate_json`. Ollama 0.40.4 via Homebrew (`brew services`),
  model `qwen3:8b` (5.2 GB). Settings/.env/.env.example: `OLLAMA_BASE_URL`, `OLLAMA_MODEL` (empty =
  rules only). Startup preload also warms the model. Measured on port 8010: 2.4–4.6 s per parse
  warm (cold load ~5 s happens at startup); with Ollama stopped the endpoint answers in 50 ms via
  rules, and `parser_note` says why. **Surprise:** even at temperature 0, qwen3:8b filled fields
  nobody mentioned (toll "cash", priority "fastest") and read "home by 6:30" as arrive-by 18:30. So
  the model's answer is now checked against the words by deterministic code
  (`checked_against_words`): exact rules reads win; model-only values survive only with backing
  words (place words present in the text, the hour typed, a toll/money/speed word present);
  every override is listed in `parser_note`. Run the server from the repo root with
  `--env-file .env` (settings read `.env` relative to the working directory).
  (5) Address lookup: `GeocodingProvider` protocol (N-04) + `NominatimGeocoder`
  (`providers/nominatim.py`): ≤ 1 request/s (lock + monotonic clock, shared across threads),
  `NOMINATIM_USER_AGENT` setting (identifying UA; empty = verified places only), disk cache
  `data/cache/nominatim/` (gitignored), `viewbox` = region bounding box + `bounded=1`, results
  outside the box dropped (N-05), ODbL attribution in every interpretation note. Order: verified
  places → lookup → town fallback. A lookup result is accepted only when its distinctive name
  words (or its "<number> <street>") AND one of its address localities agree with the words;
  generic words (pizza, brick, oven…) don't count, so "Brick Oven Pizza, Metuchen" is rejected
  for "DeLucia's Brick Oven Pizza in Raritan" (unit-tested; live OSM has no DeLucia's, so it uses
  Raritan, approximate). A result within 250 m of a verified place becomes that place (its
  checked facts apply). Unknown business in a findable town → that town's center, `estimated`,
  plus a question; a bare town → "(town center)", `estimated`; a business with no town is not
  accepted (asks "What town is it in?"). Lookup unreachable → verified places only, and the note
  says so. Verified end-to-end on port 8010: words → ai-parse → draft posted to /trip/search;
  Princeton → "350 5th Ave, Manhattan" (Empire State Building, geocoded) returns drive-in
  congestion **unknown** and parking **unknown**; the DeLucia's sentence ranks Metropark
  park-and-ride Best overall + Cheapest ($29.40) over driving ($30.55 + unknown parking).
  `make check`-equivalent green: ruff, mypy strict (54 files), pytest 220.
  Files: `backend/app/parsing/*`, `backend/app/api/v1/trip.py`, `backend/app/trips/{factory,corridor}.py`,
  `backend/app/main.py`, `backend/app/providers/base.py`, `data/regions/nyc-metro-demo-corridor.yaml`,
  `backend/app/providers/{ollama,nominatim}.py`, `backend/app/config.py`, `.env.example`, `DECISIONS.md` (D-19),
  `docs/api-spec.yaml`, tests `test_preload.py`, `test_ai_parse.py`, `test_ollama_provider.py`, `test_geocoding.py`.
  Requirements: F-01, F-08, N-02, N-04, N-05, N-07. **Not done / for the merging chat:** the demo page
  (`backend/app/web/**`, owned by the other chat) has no text box yet — the endpoint is ready for it;
  the main checkout's `.env` gained `OLLAMA_*` and `NOMINATIM_USER_AGENT` lines (shared via symlink).

- **2026-10-14 — Claude (DEMO SPRINT, page round 4 — human feedback):** A Street / Simple switch on
  the map (top right) replaces needing a second tab for the plain basemap: Street (OpenStreetMap
  tiles) is always the default; Simple removes the tiles so only the bundled Natural Earth outlines
  show; `?offline` opens on Simple. The time-vs-cost chart from round 3 is removed: the human found
  it packed and unintuitive, and each row's time bar and cost bar (same scale across rows) already
  make that comparison. Verified: default Street with tiles, Simple shows none, numbers unchanged,
  375 px no sideways scroll, network-blocked server opens on Simple with no outside requests, no
  console errors. `make check` green (128). Files: `backend/app/web/index.html`. Requirement: F-18.

- **2026-10-14 — Claude (DEMO SPRINT, page redesign round 3 — "less generic", human-approved):**
  Page only (`backend/app/web/index.html`); no API change. (1) Data status is carried by each
  number's own type instead of an icon after every number: plain = scheduled/live, dotted
  underline = estimated, red = unknown; tooltip and screen-reader text give the word; sentences
  (trip home, explanation, monthly note) get a small status word instead of an underline; the
  detail view still prints the word beside every figure (N-02). (2) Transit-signage palette:
  solid black header, signal-yellow "Better", black buttons/tabs; blue is now only the rail mode.
  (3) The legs line is merged into the time bar (minutes or train times under each segment).
  (4) Row title is the boarding station from the server's train leg (title-cased), with the
  server summary underneath; drive rows show miles. (5) A cost bar under the time bar (gas,
  parking, train, tolls, congestion, same scale on every row) with a colour key. (6) A small
  time-vs-cost chart above the list (one dot per option, labels in a leader-line column, click a
  dot to open it; options with an unknown cost are listed as not plotted). (7) One tag per row:
  the server's first label. (8) The page runs a comparison on load; `?from=<preset>&to=<preset>&at=
  YYYY-MM-DDTHH:MM` pins it (no date in code). Verified: Scenario A matches DEMO.md in Trip / Day /
  Month including per-day cost parts; Fastest tab puts Drive first; home 7:15 PM gives $47.74/day
  saved and reset restores $50.31; 375 px no sideways scroll; no console errors; the network-
  blocked server (8001, `?offline`) auto-runs with no outside requests. `make check` green (128).
  Demo URL: `http://localhost:8000/?at=2026-10-15T07:00`. Requirements: F-18, N-01, N-02.

- **2026-10-14 — Claude (DEMO SPRINT, page redesign round 2 — human feedback):**
  The human found the grey map too bare, the panel too plain and the rows too thin. Changes,
  page only (`backend/app/web/index.html`): (a) map tiles back to full-colour OpenStreetMap (the
  grey CSS filter is gone; the offline basemap uses its original colours); (b) brand colour
  again: navy-to-blue header with the blue "Better" logo, blue Compare button, tabs, Trip/Day/Month
  toggle, chips and selected row; Best overall rows tinted green, Cheapest / Fastest tags teal /
  purple; (c) a middle ground of detail on each row: the selected number (Trip by default) plus
  the other two server numbers beside it, the time bar, the legs as coloured mode icons with
  minutes or train times, depart–arrive + minutes + savings, the cost parts behind the number
  (one way, or per day under Day / Month; zero-cost parts left to the detail view), and the trip
  home line. Every number still carries its status icon. A new Compare always returns to Trip.
  Fixes found while verifying: the search card's `.rail` class collided with the rail-mode class
  (padded train items and the train step icon) — renamed `.route-rail`; time ranges use an en dash
  because Public Sans has no arrow glyph; a ResizeObserver keeps map tiles aligned when the map box
  changes size. `make check` green (128). Verified in the browser: Scenario A matches DEMO.md in
  Trip / Day / Month including the per-day cost parts and the 7:33 PM home time; 375 px has no
  sideways scroll; no console errors; the network-blocked server (8001, `?offline`) renders with no
  outside requests. Requirements: F-18, N-01, N-02.

- **2026-10-14 — Claude (DEMO SPRINT, calmer page redesign — human-approved scope extension, page only):**
  Safety tag `demo-safe-1014-roundtrip` pushed on the pre-redesign main. The page
  (`backend/app/web/index.html`) is now a Google-Maps-style layout: a search card (From / To with
  swap, Leave at, settings chips, an empty `id="ask"` slot reserved for the natural-language input),
  then compact ranked rows (badges, name, ONE number, a time bar built from the server's legs with
  the gaps between legs drawn as waiting, one meta line). A row opens a detail view: badges, the
  server's "why", one-trip / per-day / per-month tiles, morning steps, evening trip (expandable),
  the daily cost breakdown with a "Split by trip" Morning / Home / Day expander (notes kept there),
  month / year / savings and the monthly-pass note, and collapsible warnings. Sort tabs render from
  `response.sort_options` and re-request with `preferences.sort_mode` (ranking stays server-side);
  the Trip / Day / Month toggle only picks which server field a row shows. A menu drawer holds Plan
  a trip, Settings (head-home time + E-ZPass/cash, saved in localStorage with every access in
  try/catch; sent as `return_time` / `vehicle_profile.toll_payment`, both already in the contract),
  Data sources, and About and limitations (server disclaimers moved there; one-line footer).
  Provenance is a small icon with an accessible label and tooltip, one legend line, and full words
  in the detail view. Map behaviour unchanged except grey tiles (CSS filter on the tile pane only).
  Vendored for offline: Public Sans variable woff2 (`static/fonts/`, OFL) and a 30-icon Lucide
  v1.48.0 subset as one SVG sprite (`static/icons/`, ISC). `page.py` now also injects the data-source
  list (category, name, source, URL, retrieved, status, human_verified) from the pricing loader,
  the corridor file and the GTFS feed metadata — no new API path, no API change.
  New tests: `backend/tests/test_web_page.py` (data sources injected with status/date/URL, no `$`
  literals and no hard-coded sort modes in the page, scripts/fonts/icons local, every icon used
  exists in the sprite, the `ask` slot exists). `make check` green (128 tests).
  **Verified in the browser:** Princeton → Times Square, Thu 10/15 7:00 AM, home 5:30 PM matches
  DEMO.md section 3 for every row in Trip / Day / Month (one-way, day, month, saves/month, minutes,
  trains) and the Drive breakdown line by line; head home 7:15 PM gives $47.74/day saved; Scenario B
  matches; cash tolls re-request works; settings reset works and the page works with localStorage
  throwing; 375 px wide has no sideways scroll; no console errors; the network-blocked
  `waybetter-api-offline` (port 8001, `?offline`) renders with zero non-local requests.
  **Deviations / notes:** (a) The API sends `CostBreakdown.total` and `total_minutes` without a
  status, so the page shows the least certain status of the parts beside them (a display roll-up of
  server labels, commented in the page) — see backlog. (b) Swap exchanges the two preset lists; a
  reversed trip (Manhattan → suburb) returns drive-only with parking and congestion toll honestly
  *unknown*, because the corridor models inbound park-and-ride only. (c) DEMO.md still describes the
  old cards and the Rank-by dropdown; left for the chat that owns DEMO.md.
  Files: `backend/app/web/{index.html,page.py}`, `backend/app/web/static/{fonts,icons}/`,
  `backend/tests/test_web_page.py`. Requirements: F-18, N-01, N-02, N-09.

- **2026-10-14 — Claude (DEMO SPRINT, daily round trip — page, cache, DEMO.md, verification):**
  Cards now show **one-way vs round trip / day** side by side, a Morning | Home | Day cost table
  with provenance chips, the trip-home timeline, and Month / Year / savings-vs-driving (all
  server-supplied; the page only formats, N-01). New "Head home at" input, defaulted from the
  corridor file via the server-injected presets (`backend/app/web/{index.html,page.py}`); a
  round-trip disclaimer was added server-side. `app/trips/warm.py` now also fails when an option
  has no trip home; `make warm-cache` → **36 cached routes** (18 morning + 18 evening), all six
  preset pairs return 5 options each with a round trip.
  **Verified:** `make check` green (ruff, mypy strict, **122 tests**); browser on :8000, Princeton →
  Times Square Thu 10/15 07:00 / home 17:30 matches DEMO.md exactly (Metropark $27.60 one-way,
  $45.20/day, $773.92/month, saves $1,215.87/month; drive $76.17 / $95.51 / $1,989.79); return
  19:15 re-plans later trains and the Turnpike goes off-peak (Metropark saves $47.74/day); return
  06:30 is rejected with a readable error; no console errors; 375 px wide has no horizontal
  scroll; **network-blocked server (:8001) returns identical numbers** from the cache.
  DEMO.md: talk track steps 5-6 (daily commute, toll rules), expected-results tables with day /
  month / savings for all three scenarios, data-source rows, limitations, two new Q&A answers.
  Requirement IDs: F-12, F-13, F-18, N-01, N-02, N-09.
  **Backlog:** model monthly garage contracts / lot permits (driving's monthly cost is likely
  overstated); let the user set commute days per week; consider ranking on the daily total
  (today it ranks on the morning trip — the order is identical for all presets).

- **2026-10-14 — Claude (DEMO SPRINT, daily round trip — backend + API v0.2.0):** Costs were
  one-way while parking is a full-day charge, so the comparison ignored the trip home. Added a
  daily round-trip view, computed server-side (N-01):
  - **API contract v0.1.0 → v0.2.0** (`docs/api-spec.yaml` + `backend/app/__init__.py`; additive).
    New request field `TripSearchRequest.return_time` ("HH:MM", null = corridor default) and new
    response field `RouteOption.round_trip` (`RoundTrip`: evening legs, evening/daily
    `CostBreakdown`, `monthly_cost`, `annual_cost`, `savings_vs_drive` as `Savings`
    daily/monthly/annual). `test_openapi_parity.py` passes. `backend/pyproject.toml` still says
    0.1.0 (package metadata, not the contract; left alone to avoid an editable reinstall the
    night before the demo).
  - **Toll rules (F-13):** the Lincoln Tunnel stays eastbound-only (existing direction check);
    the NJ Turnpike is charged on the drive home with its own peak windows (by entry time,
    4:30-6:30 p.m.); the congestion toll is charged once per day (`charged_once_per_day` in the
    MTA file) so the evening shows $0 with that note; garage/lot parking is counted once. Gas,
    rail fare and subway fare are paid on both trips.
  - **Data (F-12, N-09):** Turnpike return rows 16E/15X → 9/8A and interchanges 16E/15X added to
    `data/tolls/njta_turnpike.yaml`, read from the same NJTA 2026 PDF (grid is symmetric; checked
    against the existing 9→16E $10.29 and 9→15X $9.42). New `data/tolls/njta_garden_state_parkway.yaml`
    (`kind: barrier_toll`, NJTA 2026 GSP E-ZPass PDF): the Metropark drive home uses ~1 mi of the
    Parkway (131→130), which crosses no plaza, so it now prices to a **sourced $0** instead of
    being silently ignored; Parkway trips outside mileposts 125.5-142.5 report `unknown`.
    NJ TRANSIT monthly passes added to `data/fares/njt_rail.yaml` from the fare chart PDF already
    cited there (Hamilton $563, Princeton Jct $549, Metropark $376, Secaucus $152).
    `data/regions/nyc-metro-demo-corridor.yaml` gains `commute:` (default return 17:30;
    250 working days/yr = OPM 2026: 261 weekdays − 11 federal holidays, `status: estimated`) and
    `hub_boarding_buffer_minutes: 5` (estimated).
  - **Rules in code:** evening P&R = walk/subway to Penn → next scheduled train out → walk to car →
    drive home. Parking is re-checked against the actual stay (a stay past the lot's longest
    published tier is `unknown`). Monthly = working days/12 × daily, except rail uses the monthly
    pass when it beats two tickets a day; annual = 12 × monthly. Monthly/annual/savings are
    `unknown` (amount null) whenever any daily component is unknown — a partial sum is never
    presented as a total. Ranking still uses the morning trip (unchanged behaviour).
  - Files: `backend/app/trips/{service,costs,models,corridor}.py`, `backend/app/pricing/{models,loader}.py`,
    tests in `test_trip_costs.py`, `test_trip_search.py`, `test_pricing_data.py`
    (101 → 122 tests). Requirement IDs: F-01, F-12, F-13, F-14, N-01, N-02, N-03, N-09.
  - **Human spot-check needed (CLAUDE.md):** the new Turnpike rows, the GSP plaza list, and the
    four monthly pass prices.

- **2026-10-14 — Claude (DEMO SPRINT, CI fix):** CI's backend job failed on every push since
  step 4 (`30e3654`..`39dc873`; 100/101 passed). Cause: `test_unknown_request_fields_are_rejected`
  did not override `get_trip_service`, so FastAPI built the real service, which opens
  `data/gtfs/njt_rail.zip` — gitignored and only fetchable with the NJT portal login, so absent on
  CI runners. Fixed by injecting the fake-provider service like the other API tests. Verified
  locally with the zip moved aside (CI conditions): 101 passed. No app code changed.

- **2026-10-14 — Claude (DEMO SPRINT step 7, DEMO.md):** Wrote [DEMO.md](DEMO.md): start command
  (verified from a clean `env -i` shell on a spare port: health, page, docs, and a search that
  matches the documented numbers), first-time setup, morning-of checklist, a ~6-minute talk
  track for three scenarios, expected results for all three origins (Thu 10/15 07:00),
  one-paragraph architecture + diagram, a data-source table with each value's status,
  limitations, Phase 2, and short answers to likely questions. Human note: the interview is
  virtual on home internet, so the step 6 offline path is a backup only.
  **Bug found while collecting expected results:** Plainsboro routes enter the Turnpike at
  **Exit 8A**, which had rates but no snap coordinates, so its toll came back `unknown`
  (correctly flagged, not guessed). Added 8A (40.3550, -74.4711, taken from the routing engine's
  merge point) to `data/tolls/njta_turnpike.yaml`; Plainsboro → Times Square drive is now $77.08
  with Turnpike 8A→16E $11.45. 101 tests green. **Open for the human:** spot-check fares, lot
  rates and Turnpike rates (CLAUDE.md); set DEMO-SPRINT.md to CLOSED after the interview.

- **2026-10-14 — Claude (DEMO SPRINT step 6, offline):** `make warm-cache`
  (`app/trips/warm.py`) runs every preset origin × destination and caches the 18 driving routes
  in gitignored `data/cache/osrm/` (OSRM is free-flow, so one pass covers every departure time);
  all 6 preset pairs return the full 5 options. Leaflet 1.9.4 vendored under
  `backend/app/web/static/leaflet/` (byte-identical to unpkg — same SRI hashes — with its BSD-2
  LICENSE), served via `/static`. **Map tiles are NOT cached:** OSM tiles return
  `Cache-Control: no-cache` and the OSM tile policy forbids bulk pre-downloading, so instead a
  Natural Earth 1:10m state-outline basemap (public domain, NY/NJ/CT/PA, 37 KB) sits in a pane
  *below* the tiles — online it is hidden by OSM tiles, offline it shows through. `?offline=1`
  skips the tile layer to show that view on purpose. **Verified offline:** ran uvicorn under
  `sandbox-exec` with all outbound network denied except localhost (`waybetter-api-offline` in
  `.claude/launch.json`); confirmed outbound blocked (curl to OSRM fails), all preset searches
  return 5 options from cache, the page renders cards + routes + basemap, and the browser's
  network log shows only localhost requests. An uncached origin offline degrades cleanly (no
  crash; disclaimers explain; page says "No options could be computed"). **Not verified:** a
  physical Wi-Fi-off run on the presenter's laptop (human, before the interview). 101 tests.
  IDs: N-04, N-05, N-09.

- **2026-10-14 — Claude (DEMO SPRINT step 5, demo page):** One static page,
  `backend/app/web/index.html`, served at `/` by `app/web/page.py` (outside `/api/v1`,
  `include_in_schema=False`, so the contract is untouched). Origin/destination presets and the
  default departure (next weekday 07:00 local) are injected server-side from
  `nyc-metro-demo-corridor.yaml`, so no new API path was needed. Leaflet 1.9.4 from unpkg with SRI
  hashes (verified against the served files), OSM tiles with attribution. The page only renders
  the API payload (N-01): server ranking order, server labels, server explanation text, every
  cost row with its provenance chip (scheduled / estimated / unknown), the leg timeline, notes
  and disclaimers. Clicking a card redraws the map for that option (drive orange, NJT rail blue,
  walk/subway dotted, P markers for lots). `.claude/launch.json` runs the API for the app's
  browser pane. **Verified in the browser** at 1440×900: Princeton → Times Square and
  Lawrenceville → Bryant Park both render, no console errors. Also fixed the "Fuel only: Fuel
  only." disclaimer wording. 100 tests green. IDs: F-18 (subset), N-01, N-02.

- **2026-10-14 — Claude (DEMO SPRINT step 4, providers + trip search):** `POST /api/v1/session`
  and `POST /api/v1/trip/search` live, both already in docs/api-spec.yaml (no contract change, no
  version bump). **Providers behind interfaces (N-04):** `app/providers/base.py` protocols;
  `osrm.py` (public OSRM demo server, 10 s timeout, on-disk cache under gitignored
  `data/cache/osrm/`); `gtfs_transit.py` (reads the NJT zip directly: calendar/calendar_dates,
  after-midnight times, pickup/drop-off flags; picks the trip that *arrives first*, so a later
  express beats an earlier local; shapes loaded lazily per trip). **Trip service**
  (`app/trips/`): drive-all-the-way vs each lot (drive → 7-min park/walk buffer from region config
  → next train → walk or subway), cost rules in `costs.py` (pure, no literals), ranking
  (best overall = equal weight to cost and time relative to the best option; fastest; cheapest),
  server-side labels and a one-line explanation from the computed numbers (N-01).
  **Tolls:** NJ Turnpike priced from the official NJTA 2026 Class 1 schedule
  (`data/tolls/njta_turnpike.yaml`; entry snapped to interchange coordinates, exit from the
  routing engine's posted exit number; unlisted pairs → `unknown`); Lincoln Tunnel eastbound-only,
  now **human-verified** from the PANYNJ July 2026 sheet; Congestion Relief Zone with the peak
  tunnel credit. Human-supplied: Secaucus ~$30/12 h and Midtown garage $33.92 (SpotHero quote
  for an *overnight* window) — both `estimated` with caveats. CRZ membership is a human-checked
  flag on preset destinations (`data/regions/nyc-metro-demo-corridor.yaml`) because zone polygons
  are still unsourced (B-5); non-preset destinations report the fee as `unknown`.
  **Verified end-to-end** against the real feed + OSRM: Princeton → Times Square, Thu 07:00 —
  Metropark $27.60/115 min (best overall, cheapest), Princeton Jct $32.11/113, Hamilton $34.49/113,
  Secaucus $53.04/126, drive $76.17/82 (Turnpike 9→16E $10.29 + Lincoln $16.79 + CRZ $6 + garage
  $33.92 + gas $9.17). 99 tests, ruff, mypy strict green. IDs: F-01, F-02, F-03, F-12, F-13, F-14,
  N-01, N-02, N-03, N-04, N-05, N-06.
  **Not done / caveats:** drive times are free-flow (no traffic); `arrive_by` returns 422;
  `/readyz` still 503 without Postgres/Redis; prices still need the human spot-check.

- **2026-10-14 — Claude (DEMO SPRINT step 3, price data):** Effective-dated YAML price files,
  each with source URL + retrieval date + `status` + `human_verified: false` (F-12, F-13, F-14,
  N-02, N-09): `data/fares/njt_rail.yaml` (official NJT NY Penn fare chart PDF, effective
  2026-07-01: Hamilton $19.75, Princeton Jct $19.50, Metropark $13.05, Secaucus $5.05),
  `data/fares/mta_subway.yaml` ($3.00, mta.info), `data/tolls/mta_congestion_relief_zone.yaml`
  ($9 peak / $2.25 overnight, up-to-$3 peak crossing credit incl. Lincoln Tunnel, mta.info),
  `data/tolls/panynj_lincoln_tunnel.yaml` ($16.79 / $14.79 / $23.30 — **secondary source**:
  panynj.gov renders via JS and could not be read), `data/parking/njt_nec_demo_lots.yaml`
  (Hamilton $13/16h, Metropark $10/16h from NJT station pages; Princeton Jct $12/24h from WWPA),
  `data/parking/manhattan_destination.yaml`, `data/vehicle/defaults.yaml` (EIA PADD 1B regular
  $4.347 wk 2026-10-12; 25.5 mpg derived from EPA Trends MY2024 27.2 incl. EVs minus 1.7).
  **Two values are `unknown` with null amounts, not guessed:** Secaucus daily parking (operator
  LAZ page returns 403; NJT lists none) and Midtown garage parking (no current public source).
  New `app/pricing/` (strict Pydantic schemas + kind-dispatched loader); `DataFiles.vehicle_dir`.
  Validation enforces: unknown ⇔ null amount, scheduled/estimated ⇒ source URL, files in effect
  on the demo day, every fare/lot references a real canonical station. 79 tests green.
  **Human spot-check required (CLAUDE.md) before any of this is "done":** all fares, the Lincoln
  Tunnel toll on panynj.gov, the lot rates, and the two unknowns.

- **2026-10-14 — Claude (DEMO SPRINT, NJT feed ingested + corridor):** Human switched the demo
  corridor to **NJ Transit Northeast Corridor → New York Penn Station** and entered their portal
  login in `.env` themselves. **Surprise:** production `getToken` answers HTTP 500
  `{"errorMessage": "Missing user account."}`; the same login authenticates on
  **`testraildata.njtransit.com`**, so both NJT URLs in `nyc-metro.yaml` point at the test host
  (comment says how to flip back once NJT provisions production). Feed: 6.3 MB, validates clean,
  230 stations, agencies `NJT` + `NJB`, service calendar 2026-10-01 → 2027-03-29, 113 NEC trips
  on 2026-10-15. **No `fare_attributes`/`fare_rules` in the feed** — rail fares must come from
  NJ TRANSIT's published fare tables (human spot-check required). Station map rebuilt: 967
  stations (230 NJT). AM-peak (arrive NY Penn 07:00–09:30, 10/15) ride times from the feed:
  Hamilton 60–66 min, Princeton Jct 53–80 (express vs local), New Brunswick 50–53, Metuchen
  41–44, Metropark 36–38, Secaucus Upper Level 12–13. Files: `data/regions/nyc-metro.yaml`,
  `data/regions/nyc-metro-stations.csv`, `data/gtfs/*.meta.json` (new `njt_rail.meta.json`).
  IDs: N-08, N-09.

- **2026-10-14 — Claude (DEMO SPRINT, NJ Transit feed wiring):** Human got NJT developer-portal
  access (GTFS-RAIL, GTFS-BUS, RailData, BUSDATA all *Active*) — B-3 partly resolved. Claude in
  Chrome was not connected, so the portal page was not read; instead the public spec
  `https://raildata.njtransit.com/swagger/GTFS/swagger.json` gave the flow: `POST getToken`
  (multipart `username`/`password` → `{"Authenticated","UserToken"}`), then `POST getGTFS`
  (multipart `token`) → zip. **What changed:** `TokenAuth` block on `FeedSource` (endpoint and
  field names are config, N-03); `fetchable_feeds()` now includes a credentialed feed once its
  env vars hold real (non-`placeholder`) values; `download_feed` does the token exchange and
  refuses any non-zip response so an API error can never replace a good archive; `waybetter-ingest
  fetch` loads `.env` (env vars win). `njt_rail` enabled in `nyc-metro.yaml`; `njt_bus` stays
  disabled (out of sprint scope). Credentials are read from the environment only — never logged,
  never in the provenance sidecar (tested). **Files:** `backend/app/regions/schema.py`,
  `backend/app/ingestion/{feeds,cli}.py`, `backend/tests/{test_feed_download,test_region_config}.py`,
  `data/regions/nyc-metro.yaml`. 70 tests, ruff, mypy green. **Not yet exercised against the real
  API:** the human must put `NJT_DEVELOPER_USERNAME`/`NJT_DEVELOPER_PASSWORD` in `.env` first.
  NJT licence stays `verified: false` until the human confirms the portal terms. IDs: N-03, N-04,
  N-08, N-09.

- **2026-10-14 — Claude (DEMO SPRINT step 2, local run):** Human chose Metro-North Harlem Line →
  Grand Central. No code changed. Created `backend/.venv` with **Python 3.13** (no 3.12 on this
  Mac; pyproject allows ≥3.12) via `make install PYTHON=/opt/miniconda3/bin/python3.13`, and
  `.env` via `make env`. uvicorn boots locally without Docker: `/healthz` 200, `/api/v1/docs`
  200; `/readyz` 503 `not_ready` (no Postgres/Redis running — expected under D-18; the demo path
  does not use them). `make fetch-feeds` re-downloaded subway/LIRR/MNR (no per-feed flag exists);
  sidecars updated to today's feed versions, and `make station-map` rebuilt the station table to
  match (N-08) — diff verified to touch only `feed_version`/`retrieved_at`, no stop changes.
  Sanity check: MNR feed spans 2026-10-09 → 2027-05-23; 482 Harlem Line trips run on 10/14–10/15.
  ruff, mypy strict, 63 tests green. Files: `data/gtfs/*.meta.json`,
  `data/regions/nyc-metro-stations.csv`, `PROGRESS.md`. IDs: N-08, N-09.

- **2026-10-14 — Claude (DEMO SPRINT step 1, inventory):** Fast-forwarded local `main` 10 commits
  to `ec72f11` (PRs #1/#2), then committed the sprint docs (`a7efccb`, D-18). No code changed.
  **What ingestion produces — files only, no DB tables:** GTFS zips in `data/gtfs/*.zip`
  (gitignored — *not on disk in this clone*, must be re-fetched), committed provenance sidecars
  `data/gtfs/{mta_subway,mta_lirr,mta_mnr}.meta.json`, and the canonical station table
  `data/regions/nyc-metro-stations.csv` (737 stations). Ingestion validates feeds and extracts
  stations only; it does **not** read `stop_times`/`calendar_dates`, so the demo's GTFS
  `TransitProvider` is new code. `data/fares`, `data/tolls`, `data/parking` are empty.
  **Checked live:** all three MTA feed URLs return 200 (MNR and LIRR republished today, so a
  re-fetch will produce new feed versions than the committed sidecars); the public OSRM demo
  server answered a Westchester → Midtown route. **Contract note:** `/trip/search` requires the
  `sessionToken` scheme, so a minimal `POST /session` is needed (as DEMO-SPRINT.md anticipates).
  **Recommendation:** Metro-North Harlem Line → Grand Central unless NJT portal access exists.

- **2026-08-04 — Claude (A2, Data Ingestion — keyless subset):** Branch `agent/a2-ingestion`,
  built on `agent/a1-scaffold`. Requirement IDs: **N-03, N-08, N-09**. Scope was deliberately
  limited to work needing no API key, credential, or payment.

  **What changed.** Region config as data (N-03): `app/regions/schema.py` (Pydantic, `extra=forbid`
  so a typo fails loudly, IANA timezone validated, bounding box ordering enforced, feed registry
  with a licence block per feed) + `app/regions/loader.py` + `data/regions/nyc-metro.yaml`.
  Ingestion (`app/ingestion/`): `gtfs.py` (archive reader, structural validation, station
  extraction, feed versioning), `feeds.py` (downloader writing a committed provenance sidecar),
  `stations.py` (canonical station IDs), `cli.py` (`waybetter-ingest` with `check-region`,
  `fetch`, `build-station-map`, `osm-plan`). Makefile targets and 42 new tests.

  **Files:** `backend/app/regions/{__init__,schema,loader}.py`,
  `backend/app/ingestion/{__init__,gtfs,feeds,stations,cli}.py`,
  `backend/tests/{test_region_config,test_gtfs_ingestion,test_station_mapping}.py`,
  `backend/pyproject.toml` (console script), `backend/README.md`, `Makefile`,
  `data/regions/nyc-metro.yaml`, `data/regions/zones/README.md`,
  `data/regions/nyc-metro-stations.csv`, `data/gtfs/mta_{subway,lirr,mnr}.meta.json`, `PROGRESS.md`.

  **Verified against real feeds.** MTA subway (496 stations), LIRR (127), Metro-North (114)
  downloaded, structurally validated, and provenance recorded; re-running reports "unchanged"
  rather than re-downloading; `build-station-map` produced 737 canonical IDs and rebuilding is a
  byte-identical diff. ruff, mypy strict, and 63 tests all clean.

  **Surprises — all found by running against real data, none anticipated.**
  (a) **The canonical-ID design is not theoretical:** LIRR `stop_id=1` is *Albertson* and
  Metro-North `stop_id=1` is *Grand Central*. Two launch feeds collide on their very first stop
  ID. There is now a test asserting exactly that pair stays distinct.
  (b) **LIRR and Metro-North ship no `calendar.txt`** — service is entirely `calendar_dates.txt`.
  Requiring `calendar.txt` would have rejected two launch feeds, so it is a warning. Fixtures
  E-01/E-03 (midnight, holiday) depend on reading `calendar_dates` correctly.
  (c) **Metro-North ships no `feed_info.txt`**, so it publishes no `feed_version`. Ingestion falls
  back to a content hash. Anything that keys on a publisher version needs to tolerate this.
  (d) **Subway uses `location_type=1` parent stations; LIRR and MNR are flat.** Station extraction
  handles both, and drops platforms — you drive to a station, not a track.
  (e) **The first bounding box I wrote included Philadelphia.** My own test caught it. Corners are
  now driven by named corridor endpoints and exclude Philadelphia at `min_lat: 40.00`, which also
  puts NJT's Atlantic City and River lines outside the region — a product call flagged for review,
  not a fact.
  (f) LIRR's `feed_info.txt` declares `feed_timezone: "America/New York"` — a space where the IANA
  name has an underscore, so it is not a loadable zone name. Harmless today (region timezone comes
  from config, N-03) but it will bite anyone who trusts that field.

  **NOT verified / still open.** PATH and CT rail: `panynj.gov`, the Trillium mirror, and
  `cttransit.com` are all denied by the build environment's egress policy, so **no feed URL could
  be confirmed** — both are registered as disabled with the reason recorded, and the config states
  `license: UNCONFIRMED` rather than guessing. NJ Transit: untouched (blocker B-3). **Every MTA
  licence is `verified: false`** — `mta.info/developers` was unreachable, so the agent read no
  terms and asserted nothing about them; a human must confirm and flip the flag (N-09). The three
  `city_driving_zone` polygons are **not sourced** — deliberately absent rather than approximated,
  because a hand-drawn Manhattan outline produces confidently wrong `avoid_city_driving` results
  (G-07); `data/regions/zones/README.md` names the datasets to fetch. `osm-plan` prints an
  **unverified** pipeline. No OTP graph was built, so the A2 definition of done — OTP answering a
  Princeton Junction → NY Penn query — is untouched.

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
