# WayBetter — Demo Guide (Deloitte GPS portfolio interview, 2026-10-15)

**What it is, in one breath:** a commuter picks a New Jersey suburb and a Midtown destination.
WayBetter compares **driving all the way into Manhattan** against **four park-and-ride options on
NJ TRANSIT's Northeast Corridor**, using real timetables and official toll, fare and parking
prices. It ranks the options and draws them on a map, and every number shows where it came from.
It also prices the **whole commute**: the trip home at 5:30 PM, the daily total, and what that
adds up to per month and per year compared with driving.

---

## 1. Start it (fresh terminal)

```bash
cd ~/Desktop/TransitApp
backend/.venv/bin/uvicorn app.main:app --app-dir backend --port 8000 --env-file .env
```

Open **http://localhost:8000**. Leave the terminal running; `Ctrl+C` stops it.

Health check, if you want it: http://localhost:8000/healthz → `{"status":"ok"}`.
API docs to show in Q&A: http://localhost:8000/api/v1/docs.
`/readyz` says *not ready* because Postgres and Redis aren't running. That's expected for the
demo, which needs neither.

### First-time setup only (already done on this laptop)

```bash
make install PYTHON=/opt/miniconda3/bin/python3.13   # Python venv + dependencies
make env                                             # creates .env; put your NJT portal login in it
make fetch-feeds                                     # downloads MTA + NJ TRANSIT timetables (GTFS)
make warm-cache                                      # caches the 36 demo driving routes (morning + home)
make check                                           # ruff + mypy + 122 tests
```

### Morning-of checklist (2 minutes)

1. Start the server as above and open the page.
2. Set **Leave at = 10/15/2026, 7:00 AM**. The page defaults to the *next* weekday, which on
   the day itself is Friday 10/16. Friday's results differ by a few minutes, which is fine.
   Leave **Head home at = 5:30 PM** (the default, read from the corridor data file).
3. Run Scenario A and confirm the numbers match the table below.
4. Keep the API docs tab open for the technical questions.

---

## 2. Demo script (~7 minutes)

**Scenario A: Princeton → Times Square, leave 7:00 AM.** Click **Compare**.

1. *"Five options. Driving all the way is fastest at 82 minutes, but costs **$76**. Parking at
   Metropark and taking the train costs **$27.60**, about $48 less, for roughly half an hour
   more door to door."*
2. Click the **Drive all the way** card. *"Here's why driving costs $76: the NJ Turnpike from
   Exit 9 to the Lincoln Tunnel is $10.29, the tunnel is $16.79, the congestion toll is $9 minus
   the $3 tunnel credit, a Midtown garage is about $34, plus gas. The system read the actual
   route to see which toll roads you'd use, then priced each one from the official schedules."*
3. Point at the colored labels. *"Every number is labeled **scheduled** (a published price or
   timetable), **estimated** (an average or a derived figure), or **unknown**. When we don't
   have a sourced number, the app says unknown instead of guessing. For a public-sector client,
   a confidently wrong price destroys trust faster than an honest gap."*
4. Click **Princeton Jct.** *"The 7:38 is an express that reaches Penn at 8:36. The 7:20 local
   leaves earlier but arrives later, so the system picks the train that **arrives first**, not
   the one that leaves first."*
5. **The daily commute.** Point at the two numbers on the Metropark card, then its table.
   *"A one-way number isn't fair, because you pay for parking for the whole day. So the system
   also plans the trip home: the 6:00 PM train from Penn, back to the car, home by 7:33. In the
   Day column, the train fare and gas count twice, but parking counts once. A day costs
   **$45.20** against **$95.51** for driving. That's about **$1,216 a month** and **$14,590 a
   year**, and monthly uses the NJ TRANSIT pass because it's cheaper than 42 one-way tickets."*
6. Back on **Drive all the way**, point at the Tolls row. *"Each toll follows its own real rule.
   The Lincoln Tunnel only charges going *into* New York, so the drive home pays nothing there.
   The Turnpike charges both ways, and it's the 4:30–6:30 peak at that hour. The congestion
   toll is charged once a day. These rules come from the agencies' published schedules and
   live in data files, not in code."*
   Optional: change **Head home at** to 7:15 PM and Compare. The drive home misses the Turnpike
   peak, so driving gets a little cheaper and the savings drop to $47.74 a day. *"Time of day
   changes the answer, and the system knows why."*
7. Switch **Rank by → Fastest**, then **Cheapest**. *"Same data, different priorities. The
   ranking happens on the server, so a future iPhone app gives identical answers."*

**Scenario B: Lawrenceville → Bryant Park.** *"Lawrenceville is next to Hamilton station, but
Hamilton isn't the cheapest choice: its fare is $19.75 and parking is $13, against $13.05 and
$10 at Metropark. Over a month that's $882 versus $815. The closest station isn't automatically
the best one, and that's the insight a commuter or a transit agency actually needs."*

**Scenario C (optional): Plainsboro → Times Square.** This route enters the Turnpike at a
different interchange (8A) and is priced correctly from the same official table.

---

## 3. Expected results (Thursday 10/15/2026, leave 7:00 AM, head home 5:30 PM, E-ZPass)

**A. Princeton (Nassau St) → Times Square**

| Option | Morning train | Train home | One-way | Day (round trip) | Month | Saves / month vs driving |
|---|---|---|---|---|---|---|
| ⭐ Park at Metropark *(Best overall · Cheapest)* | 7:59 → 8:38 | 6:00 PM, home 7:33 | **$27.60** | **$45.20** | $773.92 | **$1,215.87** |
| Park at Princeton Jct. | 7:38 → 8:36 | 5:55 PM, home 7:04 | $32.11 | $52.20 | $824.00 | $1,165.79 |
| Park at Hamilton | 7:30 → 8:36 | 5:55 PM, home 7:22 | $34.49 | $55.96 | $905.92 | $1,083.87 |
| Park at Secaucus | 8:37 → 8:49 | 5:55 PM, home 7:18 | $53.04 | $75.42 | $1,512.83 | $476.96 |
| Drive all the way *(Fastest)* | — | leave 5:30, home 6:47 | **$76.17** | **$95.51** | $1,989.79 | — |

Door to door one-way: 115 / 113 / 113 / 126 / 82 min. Per year: Metropark $9,287.04 vs driving
$23,877.48, so it saves **$14,590.44 a year**.

Drive breakdown, morning: Turnpike 9→16E $10.29 + Lincoln Tunnel $16.79 + congestion toll $6.00
+ garage $33.92 + gas $9.17 = $76.17. Home: Turnpike 16E→9 $10.29 (peak, entered 5:38 PM) +
gas $9.05 = $19.34. Lincoln Tunnel westbound $0 (tolled into New York only), congestion toll $0
(once a day), garage $0 (day rate already paid). Day = **$95.51**.

Metropark day: gas $4.55 + $4.55, parking $10.00 once, rail $13.05 + $13.05 = $45.20 (walks
to Times Square, no subway). The drive home uses one mile of the Garden State Parkway (131→130),
which passes no toll plaza: shown as a sourced $0.00. Monthly = 20.8 days × $19.10 +
$376.00 NJ TRANSIT monthly pass (cheaper than 42 one-way tickets at $543.75).

**B. Lawrenceville → Bryant Park:** one-way / day / month / saves-per-month: Metropark $28.62 /
$47.16 / $814.75 / $1,216.50 (best, cheapest) · Princeton Jct $33.12 / $54.15 / $864.62 /
$1,166.63 · Hamilton $33.89 / $54.79 / $881.54 / $1,149.71 · Secaucus $54.05 / $77.37 /
$1,553.46 / $477.79 · Drive $77.16 / $97.50 / $2,031.25 (fastest, 89 min).

**C. Plainsboro → Times Square:** Metropark $27.17 / $44.36 / $756.42 / $1,273.58 (best,
cheapest) · Princeton Jct $31.96 / $52.29 / $825.88 / $1,204.12 · Hamilton $34.76 / $56.47 /
$916.54 / $1,113.46 · Secaucus $54.08 / $77.60 / $1,558.25 / $471.75 · Drive $77.08 / $97.44 /
$2,030.00 (fastest, 77 min; Turnpike 8A→16E $11.45 in, 16E→8A $11.45 home).

Bryant Park and Times Square give the same costs; only the final walk differs. Ranking uses the
morning trip, and in all three scenarios the daily totals rank the options in the same order.

---

## 4. How it works (the one-paragraph architecture)

A **FastAPI** backend does all the work, and the web page only draws what the API returns.
`POST /api/v1/trip/search` (defined in the API contract, `docs/api-spec.yaml`) validates the
request against the region's boundaries, then asks two **providers** for data. Each provider
sits behind an interface: a `DrivingProvider` (tonight the free OSRM routing server, with a disk
cache) and a `TransitProvider` (tonight a reader that pulls next-train answers straight from NJ
TRANSIT's official GTFS timetable). A pure-Python **cost engine** prices each option from
**effective-dated data files** (`data/fares`, `data/tolls`, `data/parking`, `data/vehicle`), each
recording its source URL and retrieval date, with no prices written into code. The engine then
ranks the options and writes the labels and the one-line explanation. Switching to production
means swapping in Mapbox and OpenTripPlanner adapters; the cost engine and the page don't change.

```
Browser (Leaflet page) ──POST /trip/search──▶ FastAPI
                                               ├─ TripSearchService (rank, label, explain)
                                               ├─ cost engine ◀── data/*.yaml (sourced, dated)
                                               ├─ DrivingProvider ── OSRM (→ Mapbox later)
                                               └─ TransitProvider ── NJT GTFS (→ OTP later)
```

### Where every number comes from

| Data | Source | Status |
|---|---|---|
| Train times | NJ TRANSIT GTFS via the developer portal (test host) | scheduled |
| Rail fares | NJ TRANSIT fare chart, effective 2026-07-01 | scheduled |
| NJ Turnpike (both directions) | NJTA 2026 Class 1 toll schedule (PDF) | scheduled |
| Garden State Parkway plazas | NJTA 2026 Parkway E-ZPass rates (PDF) | scheduled |
| NJ TRANSIT monthly passes | Same NJ TRANSIT fare chart PDF | scheduled |
| Lincoln Tunnel | PANYNJ July 2026 toll sheet (**human-verified**) | scheduled |
| Congestion toll + credit | mta.info | scheduled |
| Hamilton / Metropark parking | NJ TRANSIT station pages | scheduled |
| Princeton Jct parking | West Windsor Parking Authority | scheduled |
| Secaucus parking (~$30 / 12 h) | Human-entered from a search summary | estimated |
| Midtown garage ($33.92) | Human-entered SpotHero quote (overnight window) | estimated |
| Gas $4.347/gal | EIA weekly, Central Atlantic | estimated |
| 25.5 mpg | EPA Trends 2024 (27.2 minus 1.7 for EVs) | estimated |
| Drive times | OSRM / OpenStreetMap, free-flow | estimated |
| 250 working days a year (20.8 a month) | OPM 2026 federal holidays: 261 weekdays − 11 holidays | estimated |
| Head home at 5:30 PM | Corridor data file (a default the user can change) | — |

---

## 5. Limitations (say these before you're asked)

- **Drive times assume no traffic.** The free routing server has no live data, and real rush
  hour makes driving look *worse*, so the park-and-ride advantage is understated.
- **Scheduled, not real-time.** No delay or alert data yet.
- **One corridor, four lots, preset places.** "Inside the congestion zone" is a checked flag on
  each preset, not a map test. Any other destination reports that toll as *unknown*.
- **Parking availability isn't modeled.** The app knows the price but not whether the lot is
  full (Princeton Junction's permit waitlist is about 9 years).
- **Two prices are estimates:** Secaucus and the Midtown garage. The garage quote is for an
  overnight window, so the real daytime price is probably higher.
- **NJ TRANSIT data comes from the portal's *test* server**, because production access isn't
  provisioned yet. Switching is one line in `data/regions/nyc-metro.yaml`.
- **Not yet human-spot-checked:** the rail fares, lot rates and Turnpike rates were read from
  official documents, but CLAUDE.md requires a human check before they count as verified.
- "Arrive by" planning isn't implemented in the demo; it uses "leave at".
- **Monthly and annual figures assume you commute every working day** (250 a year, no
  vacation or remote days) and use daily garage and lot rates. Monthly garage contracts and lot
  permits are not modeled; a Midtown monthly garage contract would narrow driving's gap.
- The ranking and badges use the morning trip. The daily totals happen to rank the options the
  same way in all three scenarios.
- The Garden State Parkway is modeled only between its Raritan and Union plazas (mileposts
  125.5–142.5); a Parkway trip outside that stretch shows its toll as unknown.

## 6. Phase 2 (what comes next)

1. **OpenTripPlanner** for multi-agency transit routing (transfers, PATH, subway, buses),
   replacing the single-line GTFS reader through the same interface.
2. **Mapbox** driving with live traffic (and toll flags) replacing OSRM.
3. **More feeds and corridors:** NJ TRANSIT production access, PATH, Metro-North, LIRR (already
   ingested), 60–75 human-verified lots.
4. **Real-time:** GTFS-RT delays and alerts folded into ranking.
5. **Agency view:** lot utilization and demand by origin, so a transit agency can see where
   park-and-ride capacity is short. This is the government-client angle.
6. **Deployment:** the Docker Compose stack (already written) on a small Hetzner box with
   Postgres/PostGIS and Redis, HTTPS, monitoring and backups.

## 7. Likely questions, short answers

- **"How do you know the prices are right?"** Every price file records its official source URL
  and retrieval date, and the app shows a status label on each number. Anything without a
  source shows as unknown.
- **"Why not just use Google Maps?"** It doesn't put parking, rail fares, tolls and the
  congestion toll side by side as one cost comparison, and commercial map APIs restrict storing
  results. Because providers sit behind interfaces, any of them (Google, Mapbox, or an agency's
  own systems) can be plugged in.
- **"How does it scale to other cities?"** Regions are data: a new metro is a new config plus
  data files, with no code changes. NJ TRANSIT was added today almost entirely as data; the
  one code change was a generic "log in, get a token" download step that any agency can reuse.
- **"Where's the AI?"** Deliberately out of scope tonight. The plan uses an LLM only to *parse*
  requests into a validated schema and to *phrase* explanations from computed numbers, never to
  invent routes or prices.
- **"What did you test?"** 122 automated tests (cost math, toll detection in both directions,
  once-a-day charges, monthly-pass math, ranking, unknown handling, session tokens, API
  contract), plus end-to-end runs against the real NJ TRANSIT feed, including one with all
  network access blocked.
- **"How do you get the monthly savings?"** Daily cost × 20.8 working days, where 20.8 comes
  from the federal holiday calendar and is labeled *estimated*. For rail, the system compares a
  monthly pass with two tickets a day and uses whichever is cheaper. If any daily cost is
  unknown, the monthly figure and the savings show *unknown* too, so a partial sum never poses
  as a total.
- **"Why did the API version change?"** Adding the trip home added a request field and a
  response field, so the API contract went from 0.1.0 to 0.2.0. A test fails the build if the
  code and the contract disagree.
