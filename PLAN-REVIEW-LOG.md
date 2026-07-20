# Plan Review Log: Multimodal Park-and-Ride Trip Planner
Act 1 (grill) complete — plan locked with the user. MAX_ROUNDS=5.

Reviewer: gpt-5.5 (reasoning xhigh), codex-cli 0.144.6. (User requested gpt-5.6; not available on ChatGPT-account auth — 400 error verified for both gpt-5.6 and gpt-5.6-codex.)

## Round 1 — Codex

**Findings**
- [PLAN.md:17] The "one call covers all candidates" Mapbox Matrix assumption is false for ~20 traffic-aware candidates: Mapbox's `driving-traffic` Matrix limit is 10 coordinates/request and Matrix returns no route geometries, while the PRD requires polylines and toll handling. Fix: chunk Matrix calls and run Directions on finalists for geometry/toll/avoid-toll behavior.
- [PLAN.md:17], [PLAN.md:49] Toll estimation is left unresolved even though cost ranking depends on it. Fix: choose toll/congestion sources before scoring work and model E-ZPass/cash, crossing credits, congestion-zone entry, and avoid-toll routing explicitly.
- [PLAN.md:21] Subway fare is hardcoded as `$2.90`, but current NYC public fare info shows subway/local bus at `$3`, and PATH is `$3.25`. Fix: make all fare tables effective-dated data with source URLs and no literals in the plan or code.
- [PLAN.md:22] Adjusting ETA from LLM-parsed service-alert text is not defensible; service alerts are warnings, not canonical delay minutes. Fix: do not alter ETA unless TripUpdates or a routing provider supplies structured delay data.
- [PLAN.md:16] A geometric origin-destination corridor can miss useful commuter stations off-corridor but network-optimal by express rail or transfers. Fix: generate candidates from drive-time isochrones plus transit-network accessibility, with diversity quotas by agency/line.
- [PLAN.md:16], [PLAN.md:13] "Filtered by parking data" conflicts with showing unknown-parking stations honestly. Fix: exclude only known-unusable parking, keep unknowns with nullable cost/confidence and a scoring penalty.
- [PLAN.md:12] "Stations keyed by GTFS IDs" will collide or drift across feeds and refreshes. Fix: use canonical station IDs with `(region, feed_id, agency_id, gtfs_stop_id, feed_version)` mappings.
- [PLAN.md:12], [PLAN.md:21] "No agency names in business logic" is unrealistic for fares, transfers, parking rules, GTFS-RT matching, and PATH/MTA/NJT special cases. Fix: externalize agency-specific rules into versioned data/rule modules instead of pretending they disappear.
- [PLAN.md:19], [multimodal_park_and_ride_prd.md:197] Treating all 17 modes as weighted sorts is wrong: avoid tolls/city driving and include/exclude bikes are constraints, not rankings. Fix: split hard filters, preferences, and deterministic sort keys with tests per mode.
- [PLAN.md:25] The UI exposes a bike/scooter toggle but the plan has no GBFS ingestion or micromobility routing pipeline. Fix: either remove the toggle from MVP or add GBFS ingestion, last-mile estimates, and operator deeplinks.
- [PLAN.md:27] Public anonymous feedback plus expensive trip/LLM/geocoding endpoints creates abuse and cost-exhaustion risk. Fix: rate-limit every expensive endpoint by IP/device/session, add bot controls, sanitize feedback, and keep provider keys server-side or domain-restricted.
- [PLAN.md:23], [PLAN.md:27] Sending natural-language trips to Gemini can expose precise home/work locations, and the plan has no privacy retention policy. Fix: minimize logged coordinates, redact prompts where possible, define retention, and document third-party processing.
- [PLAN.md:10], [PLAN.md:44] Rebuilding OTP graphs on the live single VPS risks downtime or corrupt cutovers. Fix: build versioned graph artifacts off-box and blue/green deploy OTP containers after health checks.
- [PLAN.md:24] "Display-ready JSON" lacks required uncertainty/source metadata from PRD guardrails. Fix: include per-field provenance/status such as live/scheduled/estimated/unknown/user-reported/AI plus data version and `last_verified_at`.
- [PLAN.md:28] QA with 20-50 trips is too thin for midnight, holidays, DST, no-route, provider-null, permit-only parking, and realtime-alert edge cases. Fix: add automated golden fixtures and failure-injection tests before human comparison.
- [PLAN.md:10] There is no backup/secrets/restore/monitoring plan for the single VPS. Fix: add encrypted Postgres/backing-volume backups, restore drills, secret management, health checks, metrics, and provider quota alerts.

Sources checked: Mapbox Matrix API docs, Mapbox MapLibre guidance, NYC311 fare info, PATH fare info.

VERDICT: REVISE

### Claude's response (Round 1)

Accepted 14 of 16 findings outright; 2 accepted with modification. Plan revised.

**Accepted as-is:** Matrix 10-coord chunking + Directions-on-finalists (§6); toll approach decided now — effective-dated toll table for major crossings, E-ZPass/cash, congestion-zone fee (§6); fares fully effective-dated with source URLs, literals removed (§7); isochrone + precomputed transit-accessibility candidate generation with diversity quotas (§6); unknown-parking stations stay candidates, only known-unusable excluded (§5); canonical station IDs with feed-mapping table (§4); agency rules as versioned data/rule modules (§4); 17 modes classified filter/weight/sort-key with per-mode tests (§6); rate limiting + domain-restricted tokens + spend alerts (§11); privacy minimization/retention/processor disclosure (§9); off-box graph builds + blue/green OTP (§2); per-field provenance status enum in API (§10); golden fixtures + failure-injection before human QA (§15); backups/secrets/monitoring section (§2).

**Accepted with modification:**
1. *Alert ETA adjustment* — Codex is right that alert text is not canonical delay data; ETA arithmetic dropped from launch. But we keep the alert-informed reliability penalty, warning chip, and verbatim agency alert text display — structured route/stop matching is sound, and dropping display entirely would over-correct.
2. *Bike/scooter toggle* — rather than build GBFS now (scope growth), the toggle is removed from launch UI (3 filters, not 4) and micromobility moves to the local-bus fast-follow where its pipeline gets built. Deviation from grill-locked UI noted for user sign-off at resolution.

**Rejected:** none. Round 1 was materially correct throughout; the two modifications narrow fixes rather than dispute findings.

## Round 2 — Codex

Most round-1 issues are addressed: Matrix chunking/Directions finalists, fare literals, alert ETA fabrication, off-box OTP builds, backups, provenance metadata, parking unknowns, and micromobility UI gating are now materially better.

Remaining problems:

- [PLAN.md:18] still lacks a real time model for `leave_now`, `leave_at`, and `arrive_by`; Mapbox Matrix/Directions are departure-time oriented, while PRD requires arrive-by planning. Fix: define canonical timezone-aware trip timing, station parking arrival time, provider capability fallbacks, and back-solving for arrive-by drive legs.
- [PLAN.md:29] still says nullable `user_id` exists "on requests" before auth, which invites spoofed identity/linkage. Fix: keep DB `user_id` nullable but do not accept client-supplied `user_id` until authentication exists; use server-issued anonymous session IDs.
- [PLAN.md:27], [PRD:197] UI still exposes only 7 sorts/3 filters while the PRD says users can sort by lowest gas, least walking, most reliable, lowest emissions, prefer rail/subway, avoid buses, etc. Fix: add an advanced sort/filter drawer or explicitly amend the PRD scope.
- [PLAN.md:20] claims all 17 modes are classified but does not define emissions at all, despite `lowest emissions` being required and `emissions_estimate` existing in the PRD model. Fix: add an emissions estimator tied to vehicle profile, energy source assumptions, and transit factors, or remove/defer that mode.
- [PLAN.md:12] says local bus and GBFS are "add feeds + rebuild, no logic changes"; GBFS and bus preferences require new service logic, UI/API fields, fare/mode rules, and operator deeplinks. Fix: replace that claim with explicit fast-follow work packages.
- [PLAN.md:18] Directions can support `exclude=toll`, but it still will not give toll prices; the static toll estimator must not rely on "toll flags" alone. Fix: compute tolls from route-polyline crossings against versioned toll geometries with direction, vehicle, payment profile, and congestion-zone rules.
- [PLAN.md:17], [PLAN.md:52] precomputed station-to-zone transit times introduce a version race with OTP graph artifacts. Fix: deploy graph artifact, precompute table, feed metadata, and candidate-cache version as one atomic bundle.
- [PLAN.md:23] displaying agency alert text "verbatim" can create noisy UI and potential rendering issues. Fix: escape/sanitize, truncate, preserve source text in detail view, and never render feed text as HTML.
- [PLAN.md:26] abuse protection omits geographic/request bounds before paid provider calls. Fix: reject out-of-region, excessive radius, impossible time, and over-large candidate requests before Mapbox/Gemini/OTP fan-out.
- [PLAN.md:14] "agent-researched" parking data still has no licensing/ToS guardrail. Fix: track source license/permission, avoid restricted scraping, and require official/open-data or human-entered facts with attribution.

External docs checked: Mapbox Matrix API and Mapbox Directions API docs.

VERDICT: REVISE

### Claude's response (Round 2)

Accepted 9 of 10; 1 accepted via its alternative branch. Plan revised.

**Accepted as-is:** canonical timezone-aware time model with backward-solved arrive_by (OTP native arrive-by → boarding time → parking buffer → iterative Mapbox depart_at) (§6); no client-supplied user_id pre-auth, server-issued anonymous session tokens (§14); emissions estimator as data-file factors, model field populated while sort stays out of launch UI (§6); fast-follows rewritten as explicit work packages (§3); geometric toll computation against versioned direction-aware crossing geometries, toll flags advisory only (§6); atomic versioned bundle for graph+precompute+metadata (§6); alert text sanitized/escaped/truncated, never HTML (§8); region-bounds and request validation before any paid provider call (§11); parking source license/permission tracking, no ToS-restricted scraping (§5).

**Accepted via alternative branch:** the 7-sorts/3-filters vs PRD-17 conflict. Codex offered "advanced drawer OR explicitly amend the PRD scope" — the launch UI cut was a deliberate user decision during the grill (usability + demo sharpness), so the plan now explicitly documents it as a user-approved scope amendment of PRD §8.3, with the advanced drawer named as the post-launch path. Not treated as a defect in the launch design.

**Rejected:** none.

## Round 3 — Codex

Prior findings are mostly addressed: time semantics, unauthenticated `user_id`, emissions, toll pricing source, graph/precompute versioning, alert sanitization, request bounds, data licensing, and fast-follow scope are now covered.

Remaining issues:

- [PLAN.md:17] says "Mapbox has no native arrive-by," which is overbroad: Matrix lacks arrive-by, but Directions supports `arrive_by` for `driving` historical routing. Fix: distinguish Matrix vs Directions capabilities and use Directions `arrive_by` on finalists where appropriate, with a documented live-traffic fallback.
- [PLAN.md:19], [PLAN.md:21] avoid-tolls is a hard filter, but candidate pruning still uses Matrix fastest routes before toll-avoidance Directions calls; Matrix does not expose `exclude=toll`. Fix: when `avoid_tolls` is active, over-generate candidates and run `exclude=toll` Directions earlier, or use a provider/local router that can toll-filter in matrix/pruning.
- [PLAN.md:17], [PLAN.md:13] hardcoding `America/New_York` conflicts with "regions are data." Fix: make timezone a region config field, defaulting NYC to `America/New_York`.
- [PLAN.md:28] the PRD sort-mode reduction is only asserted inside the plan while the PRD file still says 17 required modes. Fix: update the PRD or add a formal launch-scope amendment document before agents implement against conflicting specs.

External docs checked: Mapbox Matrix API and Mapbox Directions API docs.

VERDICT: REVISE

### Claude's response (Round 3)

Accepted all 4. Plan revised.

1. Time model rewritten: Matrix = pruning only (no arrive-by needed); Directions `arrive_by` (driving profile, typical traffic) solves finalists directly; optional `driving-traffic`+`depart_at` refinement for near-term departures. Simpler than the previous iterative scheme — good catch.
2. `avoid_tolls` mode now over-generates finalists (~10) and runs `exclude=toll` Directions on all before final ranking, acknowledging Matrix is toll-blind.
3. Timezone moved to region config (NYC default America/New_York).
4. Added "Launch-scope amendments to the PRD (authoritative)" section to PLAN.md enumerating all six deliberate deltas with precedence rule — agents implement against PLAN.md; PRD stays the long-term vision doc. (Chose amendment-in-plan over editing the user's PRD file.)

**Rejected:** none.

## Round 4 — Codex

Prior blockers are addressed: the plan now distinguishes Matrix vs Directions arrive-by support, moves timezone into region config, handles toll pricing separately from toll flags, protects unauthenticated `user_id`, formalizes PRD launch-scope amendments, and covers data licensing/request bounds/alert sanitization.

One remaining material issue:

- [PLAN.md:19] `avoid_tolls` is still only applied after Matrix prunes ~20 candidates to ~10; because Matrix returns fastest toll-allowed durations and has no `exclude=toll`, a candidate that is mediocre with tolls could still be best once toll roads are excluded. Fix: when `avoid_tolls` is active, run `exclude=toll` Directions on all pruned candidates before dropping any, or use a toll-aware local/provider matrix for pruning.

Sources checked: Mapbox Matrix API and Mapbox Directions API docs.

VERDICT: REVISE

### Claude's response (Round 4)

Accepted. In `avoid_tolls` mode the pipeline now skips Matrix pruning entirely and runs `exclude=toll` Directions on all ~20 isochrone-selected candidates before dropping any — no toll-blind ranking decision survives anywhere in that mode. ~20 Directions calls only when the filter is active; within free tier.

**Rejected:** none.

## Round 5 — Codex (MAX_ROUNDS reached)

The prior `avoid_tolls` blocker is addressed: [PLAN.md:19] now skips toll-blind Matrix pruning and runs `exclude=toll` Directions on all ~20 candidates before dropping any.

New remaining issue:

- [PLAN.md:21], [PLAN.md:28] `avoid city driving` is a launch UI filter and hard filter, but the plan never defines what "city" means or how route violations are detected. Fix: add region-configured `city_driving_zone` polygons, route-polyline intersection rules, and explicit behavior when the destination itself is inside the zone.

Source checked: Mapbox Directions API docs.

VERDICT: REVISE

### Claude's response (Round 5)

Accepted and applied: region-configured `city_driving_zone` polygons; violation = any driving-leg polyline intersecting a zone (PostGIS); destination-in-zone behavior defined (drive-all-the-way filtered or explicitly labeled as violating; park-and-ride options with all driving outside the zone remain; transit/walk legs never violate); unit-tested for the destination-in-zone case.

## Resolution: MAX_ROUNDS=5 exhausted without APPROVED

Not a substantive deadlock: every finding in all 5 rounds was accepted (2 with narrowing modifications, 1 via its alternative branch, 0 rejected), and the Round 5 fix has been applied to PLAN.md — but per the loop rules it has not been re-verified by Codex. Trajectory: 16 findings → 10 → 4 → 1 → 1, each round confirming prior fixes as addressed. Handed to the user to either accept the final fix as applied, fund one extra confirmation round, or revise further.

## Round 6 (bonus confirmation, user-funded) — Codex

Confirmed. The Round 5 fix is present in PLAN.md: `city_driving_zone` is now region-configured, violations are tested via PostGIS intersection against driving-leg polylines, and destination-in-zone behavior is explicitly defined.

I don't see remaining material blockers. Prior findings around `avoid_tolls`, time semantics, PRD launch-scope amendments, unauthenticated `user_id`, provenance, data licensing, and deferred micromobility/local buses are addressed well enough to implement.

VERDICT: APPROVED

**Final state: APPROVED after 5 review rounds + 1 confirmation round. 31 findings raised, 31 accepted (2 with narrowing modifications, 1 via alternative branch), 0 rejected. Plan is implementation-ready.**
