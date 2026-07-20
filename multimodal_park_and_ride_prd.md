# PRD: Multimodal Park-and-Ride Trip Planner

## 1. Product Summary

Build a multimodal navigation and route-comparison app focused on trips where users combine driving, parking, public transit, walking, biking, scooters, and possibly rideshare.

The core use case is:

> “I do not want to drive all the way. Find me the best station or park-and-ride lot to drive to, then tell me which transit route to take, while factoring in traffic, parking cost/risk, fares, walking time, transfers, gas, and reliability.”

The product should work across three client surfaces:

1. **iOS native app using SwiftUI + MapKit**
2. **Android app, likely Kotlin, React Native, or Flutter**
3. **Web app**

The backend should remain consistent across all platforms. Client apps should mostly handle UI, location permission, map display, and user interaction. Routing, scoring, parking logic, fare estimation, AI interpretation, and multimodal itinerary generation should live in the backend.

---

## 2. Apple Developer Program Clarification

The **$99/year Apple Developer Program** lets you publish apps on the App Store and use Apple developer services, including MapKit and Apple Maps-related tooling.

However, it **does not give you unlimited free traffic/navigation data** or a raw traffic-data feed for custom backend optimization.

Useful Apple facts for this project:

- Apple Developer Program costs **$99/year**.
- Apple Maps Server API provides a daily service-call allowance per developer team.
- MapKit JS also provides daily map-view and service-call allowances.
- MapKit can show traffic overlays in iOS apps.
- Apple ETA responses can account for traffic delays.

Recommended use of Apple:

- iOS map display
- Native Apple Maps look and feel
- Traffic overlay on iOS
- Apple Maps handoff for turn-by-turn driving navigation
- Place/search support if desired

Do **not** rely on Apple as the full backend routing engine for advanced multimodal park-and-ride planning.

---

## 3. Primary Problem

Existing maps apps are good at showing driving or transit routes, but they are weak at complex commuter decisions like:

- Should I drive all the way or park near a station?
- Which station has the best parking chance?
- Which option is cheapest after gas, parking, tolls, and fare?
- Which option avoids city driving?
- Which route has the fewest transfers?
- Which route has the least walking?
- Which route has the least driving?
- Which route is most reliable if transit is delayed?
- Should I bike/scooter the last mile after transit?
- Is it worth driving farther to a better station?

The app should solve this as a route-comparison and decision-support tool, not just a map.

---

## 4. Target Users

### 4.1 Primary User: Suburban Commuter

A user in NJ/NY/CT/PA who drives part of the way and takes transit into NYC, Newark, Jersey City, Philadelphia, Stamford, New Haven, etc.

Needs:

- Avoid city driving
- Save money
- Find parking
- Avoid unreliable transfers
- Compare driving vs transit vs hybrid trips
- Understand real-world tradeoffs quickly

### 4.2 Secondary User: Occasional Traveler

A user going to a concert, airport, school, city event, sports game, or office visit.

Needs:

- One-time trip optimization
- Avoid unfamiliar city parking
- Know where to park and which train/subway/bus to take
- Choose cheapest or easiest route

### 4.3 Tertiary User: Eco/Cost-Conscious Traveler

A user who wants to reduce gas, emissions, tolls, and driving distance.

Needs:

- Sort by gas usage
- Sort by least driving
- Sort by lowest total cost
- Compare car-heavy vs transit-heavy routes

---

## 5. Product Goals

### 5.1 MVP Goals

1. Support origin-to-destination route search.
2. Generate multiple park-and-ride station candidates.
3. Compute driving leg to station.
4. Compute transit leg from station to destination.
5. Estimate walking time and transfer count.
6. Estimate gas cost, parking cost, transit fare, and total cost.
7. Rank routes by fastest, cheapest, least driving, lowest gas, fewest transfers, least walking, and best parking confidence.
8. Provide AI natural-language trip planning for complex user preferences.
9. Support iOS, Android, and web through a shared backend API.
10. Start with one region: NJ Transit + MTA / NYC metro area.

### 5.2 Long-Term Goals

1. Add CTtransit, CTrail, Metro-North, LIRR, PATH, SEPTA, Amtrak, ferries, bikeshare, scooters, and rideshare.
2. Add live traffic-aware driving estimates.
3. Add live transit delays and service alerts.
4. Add parking availability prediction.
5. Add user-reported parking success/failure.
6. Add last-mile bike/scooter routing.
7. Add personalized route preference learning.
8. Add live rerouting when traffic/transit changes.
9. Add Apple Maps / Google Maps / Waze handoff for turn-by-turn navigation.

---

## 6. Non-Goals for MVP

Do not build these in the first version:

1. Full turn-by-turn navigation inside the app.
2. Payment for parking, transit, scooters, or bikes.
3. Real-time guaranteed parking availability.
4. Full national coverage.
5. AI-generated routes without validation from routing APIs.
6. Complex fare systems for every agency.
7. User accounts unless needed for saved preferences.
8. Real-time vehicle tracking UI for every bus/train.
9. Reservation integration with parking providers.

---

## 7. Core Product Concept

The app should return a ranked list of complete multimodal itineraries.

Example:

| Option | Route | Time | Cost | Driving | Transfers | Parking Risk | Best For |
|---|---|---:|---:|---:|---:|---|---|
| A | Drive to Metropark → NJT → Subway | 74 min | $24.35 | 22 min | 1 | Medium | Balanced |
| B | Drive to Princeton Junction → NJT | 88 min | $31.20 | 9 min | 0 | Low | Least Driving |
| C | Drive to Newark → PATH | 68 min | $18.40 | 41 min | 1 | High | Cheapest |
| D | Drive all the way | 61 min | $45.80 | 61 min | 0 | High | Fastest Today |

The app should not simply say “best route.” It should show tradeoffs.

---

## 8. Main User Stories

### 8.1 Route Search

As a user, I want to enter an origin and destination so I can compare full driving, full transit, and park-and-ride options.

Acceptance criteria:

- User can enter origin manually or use current location.
- User can enter destination by address/place name.
- User can choose leave now, leave at, or arrive by.
- App returns multiple route options.
- Each option includes total time, cost, drive time, transit time, walking time, transfers, parking info, and confidence score.

### 8.2 Park-and-Ride Optimization

As a user, I want the app to suggest the best station to drive to and park at.

Acceptance criteria:

- Backend generates candidate stations/lots within a configurable radius.
- Backend computes drive time to each candidate.
- Backend computes transit route from each candidate to destination.
- Backend ranks candidates using user preferences.
- Backend excludes candidates with known parking restrictions when relevant.

### 8.3 Sorting and Filtering

As a user, I want to sort routes by my real priorities.

Required sort modes:

- Fastest total time
- Lowest total cost
- Least driving distance
- Least driving time
- Lowest gas cost
- Least walking
- Fewest transfers
- Most reliable arrival
- Best parking chance
- Lowest emissions
- Avoid tolls
- Avoid city driving
- Prefer rail
- Prefer subway
- Avoid buses
- Include biking/scooters
- Exclude biking/scooters

### 8.4 Natural Language AI Planning

As a user, I want to type a complex request in plain English.

Example requests:

- “I need to get to NYU by 9 AM tomorrow, do not make me drive into Manhattan, and I want reliable parking.”
- “Find the cheapest option, but I am okay with 15 extra minutes.”
- “I hate transfers, so give me a route with one train if possible.”
- “I can bike up to 10 minutes after the train.”
- “I want the least amount of driving and gas.”

Acceptance criteria:

- LLM converts request into structured trip constraints.
- Backend validates missing fields.
- LLM never invents route data.
- Routing engine computes actual options.
- LLM explains why top routes were chosen.

### 8.5 Route Explanation

As a user, I want to understand why one route is recommended.

Example explanation:

> “I’m recommending Metropark over Princeton Junction because it adds 9 minutes of driving but saves 22 minutes on transit and has a lower transfer risk. I’m not recommending Newark because parking confidence is low at your requested time.”

Acceptance criteria:

- Explanation references actual route metrics.
- Explanation does not hallucinate unavailable data.
- Explanation is concise and user-friendly.
- Each recommendation has a “why this route” section.

### 8.6 Parking Info

As a user, I want to know if the suggested station has usable parking.

Acceptance criteria:

- Each candidate station shows parking lot name, location, price estimate, payment method if known, restrictions if known, and confidence level.
- Parking confidence can be based on static rules, user reports, and later ML prediction.
- App clearly labels estimated/unknown data.

### 8.7 Bike and Micromobility

As a user, I want to include biking, e-bikes, scooters, or bikeshare in first-mile or last-mile segments.

Acceptance criteria:

- App can show nearby GBFS vehicles/stations where feeds exist.
- App can include bike/scooter last-mile estimates.
- App can deep-link to operator apps where available.
- App must not claim it can unlock vehicles unless an official partner API supports that.

---

## 9. Data Sources and APIs

### 9.1 Apple

Use Apple primarily for iOS map display, traffic visualization, ETA support, and Apple Maps handoff.

Use cases:

- iOS map display
- iOS route previews
- Traffic overlay
- Apple Maps deep link for driving navigation
- Place search/autocomplete on Apple surfaces if desired

Do not rely on Apple as the main multimodal backend.

### 9.2 Google

Potential use cases:

- Places autocomplete
- Geocoding
- Driving route with traffic
- Transit route query
- Google Maps handoff

Risks:

- Can get expensive if every search checks many candidate stations.
- Google data/display terms can restrict combining Google route data with non-Google maps.
- Better as optional provider, not the default low-cost backend.

### 9.3 OpenTripPlanner

Use as the preferred low-cost multimodal routing engine.

Use cases:

- Transit routing
- Walking routing
- Bike routing
- Park-and-ride style routing
- GTFS/GTFS-Realtime ingestion
- OpenStreetMap road/path graph

### 9.4 OpenStreetMap

Use as base data for:

- Road/path graph
- Parking lots
- Park-and-ride tags
- Bicycle parking
- Footpaths
- Station surroundings

Do not overload public OSM tile servers. Use a tile provider, cache, or host tiles if public usage grows.

### 9.5 GTFS Static

Use for transit schedules.

Agencies to target first:

- NJ Transit
- MTA Subway
- MTA Bus
- PATH, if available
- Metro-North
- LIRR
- CTtransit
- CTrail / Hartford Line / Shore Line East
- SEPTA later

### 9.6 GTFS-Realtime

Use for:

- Delays
- Trip updates
- Vehicle positions
- Service alerts
- Cancellations
- Disruptions

### 9.7 Parking Data

MVP sources:

- Manual station parking database
- Transit agency station pages
- Municipal open data
- OpenStreetMap parking tags
- User reports

Later sources:

- ParkMobile partner API, if available
- SpotHero
- ParkWhiz
- Parkopedia
- TomTom parking availability
- Parking operator partnerships

### 9.8 Bike/Scooter Data

Use GBFS feeds where available.

Data to ingest:

- Available bikes
- Available e-bikes
- Available scooters
- Docks/stations
- Vehicle type
- Battery level if provided
- Geofencing/restrictions if provided
- Deep links to operator app if provided

---

## 10. Route Data Model

### 10.1 TripRequest

Fields:

- `request_id`
- `user_id` optional
- `origin`
- `destination`
- `departure_time`
- `arrival_time`
- `time_mode`: `leave_now`, `leave_at`, `arrive_by`
- `allowed_modes`: car, walk, transit, bike, scooter, rideshare
- `excluded_modes`
- `max_drive_minutes`
- `max_drive_miles`
- `max_walk_minutes`
- `max_bike_minutes`
- `max_scooter_minutes`
- `max_transfers`
- `avoid_tolls`
- `avoid_city_driving`
- `prefer_reliable_parking`
- `optimize_for`
- `sort_mode`
- `vehicle_profile`
- `user_preferences`

### 10.2 RouteOption

Fields:

- `route_id`
- `summary`
- `legs`
- `total_minutes`
- `drive_minutes`
- `transit_minutes`
- `walk_minutes`
- `bike_minutes`
- `scooter_minutes`
- `wait_minutes`
- `transfer_count`
- `drive_miles`
- `walk_miles`
- `bike_miles`
- `scooter_miles`
- `gas_cost`
- `parking_cost`
- `transit_fare`
- `bike_scooter_cost`
- `tolls`
- `total_cost`
- `emissions_estimate`
- `parking_confidence`
- `delay_risk`
- `arrival_reliability_score`
- `overall_score`
- `explanation`
- `warnings`

### 10.3 RouteLeg

Fields:

- `leg_id`
- `mode`: car, transit, walk, bike, scooter, rideshare
- `start_location`
- `end_location`
- `start_time`
- `end_time`
- `duration_minutes`
- `distance_miles`
- `provider`
- `route_name`
- `headsign`
- `polyline`
- `instructions`
- `fare`
- `realtime_status`
- `alerts`

### 10.4 ParkingFacility

Fields:

- `parking_id`
- `station_id`
- `name`
- `lat`
- `lng`
- `type`: park_and_ride, garage, lot, street, bike_parking
- `capacity`
- `price_daily`
- `price_hourly`
- `payment_methods`
- `operator`
- `overnight_allowed`
- `permit_required`
- `accessible`
- `ev_charging`
- `source`
- `source_url`
- `last_verified_at`
- `confidence_score`
- `predicted_availability`

### 10.5 StationCandidate

Fields:

- `station_id`
- `name`
- `agency`
- `lat`
- `lng`
- `available_modes`
- `parking_facilities`
- `drive_time_from_origin`
- `drive_distance_from_origin`
- `transit_options_to_destination`
- `candidate_score`

---

## 11. Scoring and Optimization

The backend should generate many candidate route options and score them.

### 11.1 Base Score Formula

Use a configurable scoring engine:

```text
score =
  total_minutes * time_weight
  + total_cost * cost_weight
  + drive_minutes * drive_weight
  + walk_minutes * walking_weight
  + transfer_count * transfer_penalty
  + parking_risk_penalty
  + delay_risk_penalty
  + toll_penalty
  + mode_switch_penalty
```

Lower score is better.

### 11.2 Sorting Modes

Each sorting mode adjusts weights.

#### Fastest

- Highest weight on total time
- Low weight on cost
- Medium penalty for risk

#### Cheapest

- Highest weight on total cost
- Medium weight on time
- Include gas, parking, tolls, transit fares, micromobility cost

#### Least Driving

- Highest penalty for drive minutes and drive miles
- Accept longer transit time

#### Lowest Gas

- Sort by estimated gas cost
- Secondary sort by total time

#### Fewest Transfers

- High transfer penalty
- Prefer one-seat routes

#### Most Reliable

- High penalty for tight transfers, known delays, low-frequency service, parking risk

#### Best Parking

- High penalty for low parking confidence
- Prefer larger/known commuter lots

#### Least Walking

- High penalty for walking minutes and walking distance

### 11.3 Gas Cost

Formula:

```text
gas_cost = drive_miles / vehicle_mpg * gas_price_per_gallon
```

Support user vehicle profiles:

- compact
- sedan
- SUV
- hybrid
- EV
- custom MPG
- custom EV kWh/mile

### 11.4 EV Cost

Formula:

```text
ev_cost = drive_miles * kWh_per_mile * electricity_price_per_kWh
```

### 11.5 Total Cost

Formula:

```text
total_cost =
  gas_or_ev_cost
  + parking_cost
  + transit_fare
  + tolls
  + bike_scooter_cost
  + rideshare_cost
```

### 11.6 Reliability Score

Inputs:

- GTFS-Realtime delay
- Service alerts
- Transfer buffer
- Frequency of next train/bus
- Historical delay data later
- Parking confidence
- Traffic volatility later

---

## 12. AI Layer

Use AI only where it is genuinely helpful.

### 12.1 Recommended Model

Use a cheap fast model such as **Gemini Flash-Lite** or another low-cost structured-output model.

### 12.2 AI Use Case 1: Natural Language Constraint Extraction

Input:

> “I need to get to Manhattan by 9, avoid driving in the city, and I want cheap parking.”

Output JSON:

```json
{
  "destination": "Manhattan",
  "arrival_time": "09:00",
  "avoid_city_driving": true,
  "prefer_cheap_parking": true,
  "optimize_for": ["arrival_time", "cost", "avoid_city_driving"]
}
```

Rules:

- AI must output structured JSON only.
- Backend validates all fields.
- AI must not invent stations, prices, or schedules.
- If critical info is missing, backend asks follow-up or uses safe defaults.

### 12.3 AI Use Case 2: Route Explanation

Input:

- Top route options
- Metrics
- User preferences

Output:

- Short explanation of why each route is recommended
- Tradeoffs
- Warnings

Example:

> “This is the cheapest route because it avoids tolls and uses PATH after parking in Newark. However, parking confidence is lower than Metropark, so choose this only if you are leaving early.”

### 12.4 AI Use Case 3: Preference Profiles

Allow user to say:

> “From now on, I prefer fewer transfers even if it takes 10 minutes longer.”

Convert to stored preference weights:

```json
{
  "transfer_penalty": "high",
  "max_extra_minutes_for_fewer_transfers": 10
}
```

### 12.5 AI Use Case 4: Live Rerouting Assistant

Later feature.

Example:

> “My train is delayed. What should I do?”

Backend checks current route, delay feeds, alternate stations, traffic, and transit departures. AI explains options.

### 12.6 AI Non-Goals

AI must not:

- Generate routes from memory
- Guess real-time traffic
- Guess live parking
- Invent fares
- Replace the routing engine
- Replace official data sources

---

## 13. Backend Architecture

Use a modular service-oriented backend.

### 13.1 Recommended Stack

- Language: Python FastAPI or Node.js/NestJS
- Database: PostgreSQL + PostGIS
- Cache: Redis
- Background jobs: Celery/RQ/BullMQ
- Routing engine: OpenTripPlanner
- Transit ingestion: GTFS + GTFS-Realtime jobs
- Object storage: S3-compatible storage for feed archives
- Deployment: Docker Compose initially, then AWS/GCP/Fly.io/Render/DigitalOcean

### 13.2 Core Backend Modules

#### 1. API Gateway / Backend API

Responsibilities:

- Authenticate requests if needed
- Accept trip requests
- Return route options
- Serve station/parking data
- Serve user preferences

Endpoints:

- `POST /trip/search`
- `POST /trip/ai-parse`
- `GET /trip/{trip_id}`
- `GET /stations/search`
- `GET /stations/{station_id}`
- `GET /parking/{station_id}`
- `POST /feedback/parking`
- `POST /feedback/route`
- `GET /providers/status`

#### 2. Routing Orchestrator

Responsibilities:

- Receive normalized TripRequest
- Generate candidate stations
- Call driving provider
- Call transit provider
- Call walking/biking provider
- Combine legs
- Create RouteOptions
- Send options to scoring engine

Interface:

```python
class RoutingOrchestrator:
    def plan_trip(self, request: TripRequest) -> list[RouteOption]:
        pass
```

#### 3. Candidate Station Generator

Responsibilities:

- Find stations near origin, destination corridor, or logical commuting network
- Filter by parking availability
- Filter by max drive time/radius
- Rank preliminary candidates

Interface:

```python
class StationCandidateService:
    def get_candidates(self, origin, destination, constraints) -> list[StationCandidate]:
        pass
```

#### 4. Driving Provider Interface

Responsibilities:

- Return drive time, distance, polyline, toll presence, traffic-aware ETA if supported

Interface:

```python
class DrivingProvider:
    def get_route(self, origin, destination, options) -> DrivingRoute:
        pass
```

Implementations:

- `OpenStreetMapDrivingProvider`
- `AppleETAProvider`
- `GoogleRoutesProvider`
- `MapboxDrivingProvider`
- `TomTomDrivingProvider`

#### 5. Transit Provider Interface

Responsibilities:

- Return transit itineraries using schedules and realtime

Interface:

```python
class TransitProvider:
    def get_itineraries(self, origin, destination, time_options) -> list[TransitItinerary]:
        pass
```

Implementations:

- `OpenTripPlannerTransitProvider`
- `GoogleTransitProvider`
- `AgencySpecificProvider`

#### 6. Parking Service

Responsibilities:

- Return parking lots near station
- Estimate price
- Estimate availability/risk
- Store user reports
- Store source confidence

Interface:

```python
class ParkingService:
    def get_station_parking(self, station_id) -> list[ParkingFacility]:
        pass

    def estimate_parking_confidence(self, parking_id, arrival_time) -> ParkingConfidence:
        pass
```

#### 7. Fare Service

Responsibilities:

- Estimate transit fares
- Use GTFS fares when available
- Use manual fare tables for NJT/MTA/CTrail when needed

Interface:

```python
class FareService:
    def estimate_fare(self, itinerary: TransitItinerary, rider_profile) -> FareEstimate:
        pass
```

#### 8. Cost Estimator

Responsibilities:

- Gas cost
- EV cost
- Toll estimate
- Parking cost
- Transit fare
- Bike/scooter estimate
- Total cost

Interface:

```python
class CostEstimator:
    def estimate_total_cost(self, route_option, user_vehicle_profile) -> CostBreakdown:
        pass
```

#### 9. Scoring Engine

Responsibilities:

- Apply user preferences
- Rank routes
- Produce labels like “Cheapest,” “Fastest,” “Least Driving”

Interface:

```python
class RouteScoringEngine:
    def score(self, route: RouteOption, preferences: UserPreferences) -> ScoredRoute:
        pass
```

#### 10. AI Planner Service

Responsibilities:

- Parse natural-language trip requests
- Explain route options
- Convert preferences to structured weights

Interface:

```python
class AIPlannerService:
    def parse_request(self, text: str, context: UserContext) -> TripRequestDraft:
        pass

    def explain_routes(self, routes: list[RouteOption], preferences: UserPreferences) -> list[str]:
        pass
```

#### 11. Micromobility Service

Responsibilities:

- Ingest GBFS feeds
- Return nearby bikes/scooters
- Estimate last-mile bike/scooter travel time
- Provide deep links

Interface:

```python
class MicromobilityService:
    def get_nearby_options(self, location, radius_meters) -> list[MicromobilityOption]:
        pass
```

---

## 14. Client Architecture

The backend should expose platform-neutral JSON. Clients should not duplicate routing logic.

### 14.1 Shared Client Responsibilities

All clients:

- Collect origin/destination
- Request location permission
- Display route list
- Display route details
- Display map polylines
- Let user sort/filter
- Submit feedback
- Deep-link to Apple Maps/Google Maps/operator apps

### 14.2 iOS SwiftUI Client

Use:

- SwiftUI
- MapKit
- CoreLocation
- URL schemes for Apple Maps/Google Maps handoff

iOS-specific features:

- Apple Maps native map display
- Traffic overlay using MapKit where appropriate
- Apple Maps driving handoff
- Native widgets/live activity later

Do not put core scoring logic in Swift.

### 14.3 Android Client

Use:

- Kotlin + Jetpack Compose, React Native, or Flutter
- Google Maps SDK, Mapbox, or MapLibre
- Location services
- Google Maps handoff

Do not put core scoring logic in Android.

### 14.4 Web Client

Use:

- React/Next.js
- MapLibre/Mapbox/Apple MapKit JS depending on provider choice
- Responsive mobile-first layout

Do not put core scoring logic in frontend.

---

## 15. Recommended MVP Region

Start with:

- NJ Transit rail
- NJ Transit station parking
- MTA subway
- PATH if possible
- NYC destination support
- Optional: MTA bus later

Initial user flow:

1. User enters NJ origin.
2. User enters NYC destination.
3. App suggests NJT station park-and-ride options.
4. App compares:
   - drive all the way
   - nearest station
   - better/farther station
   - cheaper station
   - least driving option
5. App includes subway/walk final leg.
6. App sorts by time, cost, least driving, gas, transfers, and parking confidence.

---

## 16. MVP Features

### 16.1 Must Have

- Origin/destination input
- Leave now / arrive by
- Candidate park-and-ride station generation
- Multimodal route generation
- Route ranking
- Cost estimate
- Gas estimate
- Parking lot database
- Transit schedule support
- Basic live transit alerts if available
- AI natural-language parser
- Route explanation
- iOS app
- Web app or Android app, depending on launch priority

### 16.2 Should Have

- User preferences
- Save home/work/school
- Parking feedback
- Fare estimate
- Traffic-aware driving through one provider
- Apple/Google Maps handoff
- Basic bike/scooter last-mile support

### 16.3 Could Have

- Push notifications
- Live rerouting
- Parking prediction
- Account sync
- Calendar integration
- Event-based routing
- Weather-aware routing
- Accessibility routing

### 16.4 Won’t Have Initially

- Payment integration
- Guaranteed parking
- In-app scooter unlock
- Full turn-by-turn navigation
- Nationwide coverage

---

## 17. Agentic Coding Plan

Use multiple agents with clear ownership.

### Agent 1: Product/Architecture Agent

Tasks:

- Finalize system architecture
- Define API contracts
- Define data models
- Maintain PRD consistency
- Ensure cross-platform backend-first design

Outputs:

- OpenAPI spec
- Entity relationship diagram
- Service boundaries
- Folder structure

### Agent 2: Backend API Agent

Tasks:

- Build FastAPI/NestJS backend
- Implement `POST /trip/search`
- Implement station and parking endpoints
- Implement DTOs and validation
- Add error handling and logging

Outputs:

- Working backend API
- Tests for core endpoints
- API documentation

### Agent 3: Routing Engine Agent

Tasks:

- Set up OpenTripPlanner
- Load OSM + GTFS
- Build transit route provider
- Build driving/walking/biking provider adapter
- Return normalized route legs

Outputs:

- OTP integration
- Provider interface
- Example route outputs

### Agent 4: Data Ingestion Agent

Tasks:

- Download GTFS feeds
- Ingest station data
- Ingest parking data
- Ingest GBFS feeds
- Schedule refresh jobs

Outputs:

- Ingestion scripts
- Database tables
- Data validation reports

### Agent 5: Parking/Fare Agent

Tasks:

- Build parking database schema
- Add manual NJT station parking seed data
- Build fare estimation module
- Add cost calculation
- Add parking confidence rules

Outputs:

- Parking service
- Fare service
- Cost estimator
- Seed data files

### Agent 6: Scoring/Optimization Agent

Tasks:

- Implement route scoring formula
- Implement sorting modes
- Implement preference weights
- Add route labels

Outputs:

- Scoring engine
- Unit tests for ranking
- Sample route comparison outputs

### Agent 7: AI Agent

Tasks:

- Implement LLM structured extraction
- Implement route explanation
- Add prompt templates
- Add guardrails against hallucination
- Add JSON schema validation

Outputs:

- AI planner service
- Prompt files
- Test cases for natural-language requests

### Agent 8: iOS SwiftUI Agent

Tasks:

- Build iOS UI
- Integrate MapKit
- Display routes
- Display route details
- Add sorting/filtering
- Add Apple Maps handoff

Outputs:

- SwiftUI app
- API client
- Map screen
- Route list screen
- Route detail screen

### Agent 9: Web Frontend Agent

Tasks:

- Build responsive web UI
- Integrate map display
- Display route list/detail
- Add AI text input
- Add sorting/filtering

Outputs:

- React/Next.js app
- API client
- Map component
- Route comparison table

### Agent 10: QA/Test Agent

Tasks:

- Create test scenarios
- Validate route scoring
- Validate cost estimates
- Validate AI parsing
- Validate cross-platform consistency
- Catch hallucinated explanations

Outputs:

- Test plan
- Unit tests
- Integration tests
- Manual QA checklist

---

## 18. Suggested Repository Structure

```text
multimodal-parkride/
  backend/
    app/
      api/
      core/
      models/
      services/
        routing/
        parking/
        fares/
        cost/
        scoring/
        ai/
        micromobility/
      providers/
        driving/
        transit/
        maps/
      db/
      jobs/
      tests/
    Dockerfile
    docker-compose.yml

  ios/
    ParkRidePlanner/
      App/
      Views/
      ViewModels/
      Models/
      Services/
      Map/
      API/

  web/
    app/
    components/
    lib/
    api/
    styles/

  data/
    gtfs/
    parking/
    fares/
    osm/
    gbfs/

  docs/
    prd.md
    architecture.md
    api-spec.yaml
    agent-tasks.md
```

---

## 19. Backend API Contract: Example

### 19.1 POST `/trip/search`

Request:

```json
{
  "origin": {
    "lat": 40.3173,
    "lng": -74.6199,
    "label": "Princeton Junction, NJ"
  },
  "destination": {
    "lat": 40.7306,
    "lng": -73.9973,
    "label": "NYU"
  },
  "time_mode": "arrive_by",
  "target_time": "2026-07-13T09:00:00-04:00",
  "allowed_modes": ["car", "transit", "walk", "bike", "scooter"],
  "preferences": {
    "sort_mode": "best_overall",
    "avoid_city_driving": true,
    "max_walk_minutes": 12,
    "max_transfers": 1,
    "prefer_reliable_parking": true,
    "cost_sensitivity": "medium",
    "driving_penalty": "high"
  },
  "vehicle_profile": {
    "type": "sedan",
    "mpg": 28,
    "fuel_price_per_gallon": 3.50
  }
}
```

Response:

```json
{
  "request_id": "trip_123",
  "routes": [
    {
      "route_id": "route_1",
      "label": "Best Overall",
      "summary": "Drive to Metropark, park, take NJ Transit, then subway/walk",
      "total_minutes": 74,
      "total_cost": 24.35,
      "drive_minutes": 22,
      "drive_miles": 13.4,
      "transit_minutes": 41,
      "walk_minutes": 8,
      "transfer_count": 1,
      "parking_confidence": "medium",
      "delay_risk": "low",
      "cost_breakdown": {
        "gas": 1.68,
        "parking": 7.00,
        "transit": 15.50,
        "tolls": 0.00,
        "micromobility": 0.00
      },
      "legs": [],
      "explanation": "Recommended because it balances reasonable drive time, lower city-driving exposure, and reliable rail service."
    }
  ],
  "sort_options": [
    "fastest",
    "cheapest",
    "least_driving",
    "lowest_gas",
    "fewest_transfers",
    "best_parking",
    "most_reliable"
  ]
}
```

---

## 20. Guardrails and Accuracy

The app must clearly distinguish:

- Live data
- Scheduled data
- Estimated data
- Unknown data
- User-reported data
- AI-generated explanation

Never show an AI claim as fact unless backed by route data, official data, or stored database values.

Required disclaimers:

- “Fare estimate”
- “Parking availability not guaranteed”
- “Traffic and transit conditions may change”
- “Check official agency/payment app before parking”

---

## 21. Monetization Ideas Later

Do not focus on monetization in MVP, but possible future options include:

- Freemium route planning
- Premium live alerts
- Premium parking prediction
- Commuter subscription
- Affiliate parking booking
- Employer commuter tool
- University commuter version
- Transit agency analytics dashboard
- White-label park-and-ride planner

---

## 22. MVP Build Order

### Phase 0: Research and Data Setup

- Pick first region
- Gather GTFS feeds
- Gather station list
- Build manual parking seed database
- Confirm available realtime feeds

### Phase 1: Backend Prototype

- Implement TripRequest model
- Implement candidate station generator
- Integrate OpenTripPlanner
- Return basic multimodal routes
- Add simple scoring

### Phase 2: Cost and Parking

- Add gas estimate
- Add parking cost
- Add fare estimate
- Add total cost
- Add parking confidence

### Phase 3: AI Layer

- Add natural-language parser
- Add structured JSON extraction
- Add route explanation

### Phase 4: iOS/Web UI

- Build route search screen
- Build route comparison screen
- Build map display
- Build route detail screen
- Add sort/filter controls

### Phase 5: Beta Testing

- Test 20–50 real trips
- Compare results with Google/Apple
- Collect feedback on parking accuracy
- Tune scoring weights

---

## 23. Technical Philosophy

The system should be:

- Backend-first
- Modular
- Provider-agnostic
- Object-oriented
- Easy to swap data providers
- Consistent across iOS, Android, and web
- Cheap to run at low scale
- Honest about uncertain data
- AI-assisted, not AI-dependent

The core backend should not care whether the user is on iOS SwiftUI, Android, or web. Every client should call the same route-planning API and receive the same route options.

---

## 24. Key Differentiator

The product is not:

> “Google Maps with AI.”

The product is:

> A park-and-ride decision engine that understands the real commuter tradeoffs normal maps ignore: parking risk, traffic, transit reliability, gas, tolls, fares, walking, biking, transfers, and user preferences.

That decision layer is the moat.

---

## 25. References to Verify During Implementation

These should be checked directly during build because pricing, API quotas, and terms can change.

- Apple Developer Program
- Apple MapKit
- Apple Maps Server API
- Apple MapKit JS
- Google Maps Platform Routes API
- OpenTripPlanner
- OpenStreetMap
- GTFS Static
- GTFS-Realtime
- NJ Transit Developer Portal
- MTA Developer Resources
- CTtransit Developer Resources
- GBFS / MobilityData
- ParkMobile Developer Portal
- SpotHero Developer Resources
- ParkWhiz Developer Portal
- Parkopedia Business Data
- TomTom Parking / Traffic APIs
