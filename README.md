# WayBetter — Park-and-Ride Trip Planner (NYC Metro)

A multimodal trip-decision engine for commuters: given where you are, where you're going, and when, it compares **driving all the way vs. taking transit vs. driving to a station, parking, and riding in** — across the tradeoffs regular map apps ignore: total cost (gas + parking + fares + tolls + congestion fee), parking confidence, driving exposure, transfers, walking, and reliability.

> "I don't want to drive into Manhattan. Which station should I drive to, will I get a parking spot, and what does the whole trip actually cost?"

**Status: planning complete, pre-build.** The implementation plan survived a 6-round adversarial cross-model review (Claude ↔ GPT-5.5) and is approved for build.

## How it works (one paragraph)

The backend generates ~20 candidate park-and-ride stations along your corridor, prices the drive to each (live-traffic API), routes the transit leg from each (self-hosted OpenTripPlanner over official GTFS schedules), attaches parking data from a hand-verified database, computes true door-to-door cost and time, scores everything against your preferences, and returns a ranked comparison — with plain-English explanations generated *after* the math, never instead of it.

## Launch scope

- **Region:** NYC metro — NJ Transit rail + commuter bus, LIRR, Metro-North, NYC Subway, PATH, CT rail. (Local buses, bike/scooter share: fast-follow.)
- **Clients:** Web app first (Next.js + MapLibre), iOS immediately after (SwiftUI + MapKit), Android later. All clients are thin renderers over one backend API.
- **Sorting:** Best Overall, Fastest, Cheapest, Least Driving, Most Driving, Fewest Transfers, Best Parking + filters (avoid tolls, avoid city driving, max walk).
- **AI:** natural-language trip requests ("get me to NYU by 9, no city driving") parsed to structured constraints; route explanations grounded in computed metrics. The LLM never invents routes, prices, or schedules.

## Stack

FastAPI (Python) · PostgreSQL/PostGIS · Redis · OpenTripPlanner 2.x · Mapbox (traffic/geocoding, swappable) · Gemini 2.5 Flash-Lite (swappable via `LLMProvider`) · Docker Compose on a single Hetzner VPS · Next.js web · SwiftUI iOS.

Every external dependency sits behind a provider interface (`DrivingProvider`, `TransitProvider`, `GeocodingProvider`, `LLMProvider`) — swapping vendors is a config change plus one adapter. Regions are data, not code: new metro = new config + feeds, zero logic changes.

## Documentation map

| File | What it is | Read it if you are… |
|---|---|---|
| [README.md](README.md) | This overview | anyone new to the project |
| [multimodal_park_and_ride_prd.md](multimodal_park_and_ride_prd.md) | Full product vision (long-term) | understanding the *why* and the roadmap |
| [PLAN.md](PLAN.md) | **Approved implementation plan — authoritative for the launch build**; supersedes the PRD where they conflict (see its amendments section) | deciding *how* anything gets built |
| [REQUIREMENTS.md](REQUIREMENTS.md) | Numbered launch requirements distilled from PRD + plan | verifying scope or writing tests |
| [PROGRESS.md](PROGRESS.md) | Live status board + work log — what's done, in progress, next | an AI agent (or human) picking up work |
| [DECISIONS.md](DECISIONS.md) | Locked decisions with rationale | tempted to relitigate a choice |
| [PLAN-REVIEW-LOG.md](PLAN-REVIEW-LOG.md) | Full transcript of the adversarial plan review | curious how the plan was hardened |
| [CLAUDE.md](CLAUDE.md) | Standing instructions for AI coding agents | an AI agent, before touching anything |

## Project intent

Solo-built portfolio project (AI agents as workforce) targeting a live public web app ≈ Sept 2026 and an iOS App Store release after. Not monetized.
