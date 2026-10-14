# Decision Log

Locked decisions with rationale. **Do not relitigate these during implementation** — if new evidence genuinely breaks one, stop and raise it to the human with the evidence; don't silently deviate. Full debate transcripts: the grill (chat) and [PLAN-REVIEW-LOG.md](PLAN-REVIEW-LOG.md).

| # | Decision | Rationale (short) | Date |
|---|---|---|---|
| D-01 | Project intent: portfolio piece **and** genuinely shipped product (web live, App Store); no monetization | Recruiting value + real users; forces production quality | 2026-07-19 |
| D-02 | Build order: **web → iOS → Android**; iOS immediately after web | Recruiters click URLs; API hardens before Swift freezes against it | 2026-07-19 |
| D-03 | Clients are thin renderers; all logic server-side, display-ready JSON | Makes the iOS port cheap and keeps three clients consistent | 2026-07-19 |
| D-04 | Backend: **Python + FastAPI** (not NestJS) | Data-engineering + Pydantic-as-LLM-guardrail strengths; TS types via generated client | 2026-07-19 |
| D-05 | Routing: **self-hosted OTP** for transit/walk/bike + **Mapbox** for traffic-aware driving ("Option D") | Flat ~$30/mo vs per-search API costs; no Google display-terms conflict; traffic is non-negotiable for drive-vs-park | 2026-07-19 |
| D-06 | Hosting: single **Hetzner** 16GB VPS, Docker Compose | Cheapest adequate; provider-agnostic deploy story | 2026-07-19 |
| D-07 | Launch coverage: **rail-first full NYC metro** (NJT rail+commuter bus, LIRR, MNR, subway, PATH, CT rail); local buses + GBFS fast-follow | Routing breadth is nearly free via GTFS; local-bus feeds triple graph pain for little park-and-ride value | 2026-07-19 |
| D-08 | **Regions are data, not code** (config + feeds + fare/toll/parking files + rule modules; canonical station IDs; timezone in config) | Future cities without logic changes; agency quirks externalized, not hardcoded | 2026-07-19 |
| D-09 | Parking DB: deep seed for top ~60–75 stations; everything else honest "unknown" (still candidates) | Hand-verified parking data is the moat and the scarce resource | 2026-07-19 |
| D-10 | LLM: **Gemini 2.5 Flash-Lite** behind `LLMProvider` interface; ship NL parsing + explanations only | Model is a config detail; provider-agnostic AI layer is a design goal; other AI use cases deferred | 2026-07-19 |
| D-11 | LLM never sits in the routing path: parse before, explain after, always schema-validated | Hallucination guardrail by architecture, not by prompt | 2026-07-19 |
| D-12 | Real-time at launch: alerts inform scoring/warnings only; **no ETA arithmetic from alert text**; TripUpdates→OTP is v1.1 | Alerts aren't canonical delay data (Codex R1); 15% of work, 80% of perceived value | 2026-07-19 |
| D-13 | Fares/tolls: effective-dated data files, zero literals in code; tolls via route-geometry × versioned crossing geometries + congestion zone | Fare hikes are data updates; toll flags don't price anything (Codex R1/R2) | 2026-07-19 |
| D-14 | UI: 7 sorts + 3 filters at launch (PRD §8.3 amended); full mode set lives in engine; "Most Driving" added | Choice paralysis kills the demo; engine completeness preserved (grill + Codex R2/R3) | 2026-07-19 |
| D-15 | No accounts at launch; server-issued anonymous session tokens; nullable `user_id` schema-side only | Auth/PII burden unearned until sync matters; no spoofable client IDs (Codex R2) | 2026-07-19 |
| D-16 | Ops from day one: off-box graph builds, atomic versioned bundle, blue/green OTP, backups + restore drill, spend alerts | Single-box hobby ops are the actual failure mode (Codex R1/R2) | 2026-07-19 |
| D-17 | Reviewer model for plan reviews: gpt-5.5/xhigh (gpt-5.6 unavailable on ChatGPT-account auth — verified 400) | Highest available cross-model reviewer | 2026-07-19 |
| D-18 | **Demo sprint (2026-10-14/15)** for a Deloitte GPS portfolio interview: temporarily supersedes D-05 (OSRM + direct-GTFS adapters instead of Mapbox/OTP), D-06/D-16 (no Docker, local uvicorn), D-02/D-07 (one static Leaflet page, one rail corridor). Interfaces, contract, data-not-code, and provenance rules stay. Details in DEMO-SPRINT.md | One reliable, explainable demo in ~5 hours; provider interfaces make the swap back to Mapbox/OTP a config change | 2026-10-14 |

Add new decisions as rows with the next D-number; never edit old rows — supersede with a new row referencing the old.
