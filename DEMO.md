# WayBetter — Demo Guide (Deloitte GPS portfolio interview, 2026-10-15)

**What it is, in one breath:** a commuter picks a New Jersey suburb and a Midtown destination.
WayBetter compares **driving all the way into Manhattan** against **four park-and-ride options on
NJ TRANSIT's Northeast Corridor**, using real timetables and official toll, fare and parking
prices. It ranks the options and draws them on a map, and every number shows where it came from.
It also prices the **whole commute**: the trip home at 5:30 PM, the daily total, and what that
adds up to per month and per year compared with driving. You can also **type or say the trip in
plain English**: a local AI model reads it, the page shows what it understood and where each
value came from, and nothing is searched until you press **Show options**.

> **Updated 2026-10-15 (demo sprint closed, D-21, API v0.8.0):** seven
> ranking tabs (adds Most driving, Fewest transfers, Cleanest), badges only for a unique winner,
> CO₂ per option from EPA factors, your own mpg and gas price in Settings, two filters (avoid
> tolls, longest walk) that list what they hide and why, "Open in Google Maps / Apple Maps" on
> every drive step, and a **Compare options** view in the menu. See step 9 and §3 E.
>
> **Redesign 2026-10-15 (D-22):** option cards with a rank bullet, coloured badges and the trip
> drawn as a line diagram; click a card to expand it in place (cost bar, other periods, trip
> home), click again or **Full details** for the step-by-step view, which now opens on a green
> savings banner and the lot's facts. **≈** marks an estimate (it replaced the dotted
> underline). Avoid tolls is a chip under the trip; **Cards | Table** replaces the menu's
> Compare. A departure after the head-home time plans one way and says why (it used to error).

---

## 1. Start it (fresh terminal)

```bash
brew services start ollama          # the local AI model server (already set to start at login)
curl -s localhost:11434/api/tags    # should list qwen3:8b; if it errors, Ollama isn't running
cd ~/Desktop/TransitApp
backend/.venv/bin/uvicorn app.main:app --app-dir backend --port 8000 --env-file .env
```

Open **http://localhost:8000**. Leave the terminal running; `Ctrl+C` stops it. On startup the
server loads the timetable, runs one warm-up comparison and loads the AI model into memory in
the background (about 5 s), so the first real request is fast.

**Restart the server after pulling new code.** uvicorn here doesn't auto-reload, so a server
started earlier keeps serving the old page.

For voice: open **Handy** (in /Applications; it lives in the menu bar). There is no voice
button on the page: click in the **Type your trip** box, hold **`⌥ Option + Space`** (Handy's
shortcut on this laptop; tap once to start / again to stop also works), speak, release; the
words appear in the box a second later. Handy transcribes on this laptop with the **Parakeet
Unified EN 0.6B** model, offline. **Glance at the box before pressing Read it:** speech-to-text
can mishear place names (tested 2026-10-14: "Raritan" → "Rareton", "Javits" → "Jaffbit"). Fix
the word, or just press Read it and let the app ask: it won't guess a town it can't confirm.

Health check, if you want it: http://localhost:8000/healthz → `{"status":"ok"}`.
API docs to show in Q&A: http://localhost:8000/api/v1/docs.
`/readyz` says *not ready* because Postgres and Redis aren't running. That's expected for the
demo, which needs neither.

### First-time setup only (already done on this laptop)

```bash
make install PYTHON=/opt/miniconda3/bin/python3.13   # Python venv + dependencies
make env                                             # creates .env; put your NJT portal login in it
make fetch-feeds                                     # downloads MTA + NJ TRANSIT timetables (GTFS)
make warm-cache                                      # caches the demo driving routes (morning + home)
brew install ollama && brew services start ollama    # local AI model server
ollama pull qwen3:8b                                 # the model (5.2 GB, one time)
make check                                           # ruff + mypy + 304 tests
```

Handy (voice, optional): installed 2026-10-14 from the official GitHub release
(`cjpais/Handy` v0.9.8, MIT licence, Apple-notarized). First launch asks for **Microphone** and
**Accessibility** permission and a speech model (chosen: **Parakeet Unified EN 0.6B**, 697 MB,
fast English). In Handy's settings, add the demo's place names to **Custom Words** so they're
transcribed right: Raritan, Javits, Metropark, Secaucus, Princeton, Hamilton, Lawrenceville,
Plainsboro. This is Handy's vocabulary list, not WayBetter code; no business is ever
hard-coded (an unconfirmed business falls back to the town it's in).

### Morning-of checklist (3 minutes)

1. `curl -s localhost:11434/api/tags` lists `qwen3:8b` (else `brew services start ollama`).
2. Start the server as above (a fresh start, so it serves today's code) and open the page.
3. **Warm the model:** type `from Princeton to Times Square` in **Type your trip** and press
   Enter. The first reading can take ~5–10 s if the model was unloaded; after that it's 2–5 s.
   (The server keeps the model loaded for 30 minutes after each use, so do this shortly before
   the call, or repeat it.)
4. Open Handy, dictate one sentence into the box with `⌥ Option + Space`, and check the words
   land there spelled right (especially "Raritan" and "Javits").
5. Set **Leave at = 10/15/2026, 7:00 AM**. The page defaults to the *next* weekday, which on
   the day itself is Friday 10/16. Friday's results differ by a few minutes, which is fine.
   Leave **Head home at = 5:30 PM** (the default, read from the corridor data file).
6. Run Scenario A and confirm the numbers match the table below.
7. Run the plain-words example (section 2, step 8) once and check it against section 3.
8. Keep the API docs tab open for the technical questions.

---

## 2. Demo script (~7 minutes)

**Scenario A: Princeton → Times Square, leave 7:00 AM.** Click **Compare**.

1. *"Five options. Driving all the way is fastest at 82 minutes, but costs **$76**. Parking at
   Metropark and taking the train costs **$27.60**, about $48 less, for roughly half an hour
   more door to door."*
2. Click the **Drive all the way** card; it expands with its cost bar (gas, garage, tolls,
   congestion). *"Here's why driving costs $76: the NJ Turnpike from
   Exit 9 to the Lincoln Tunnel is $10.29, the tunnel is $16.79, the congestion toll is $9 minus
   the $3 tunnel credit, a Midtown garage is about $34, plus gas. The system read the actual
   route to see which toll roads you'd use, then priced each one from the official schedules."*
3. Point at the key above the cards. *"Every number carries its status. **≈** means estimated
   (an average or a derived figure), a plain number comes from a published price or timetable,
   and red **unknown** means we don't have a sourced number, so the app says so instead of
   guessing. The detail's cost table spells it out in words. For a public-sector client,
   a confidently wrong price destroys trust faster than an honest gap."*
4. Click **Princeton Jct.** *"The 7:38 is an express that reaches Penn at 8:36. The 7:20 local
   leaves earlier but arrives later, so the system picks the train that **arrives first**, not
   the one that leaves first."*
5. **The daily commute.** Click **Metropark**, then **Full details**: the green banner leads with
   the savings, and the day's cost table is below.
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

8. **Type or say a trip.** Click in **Type your trip** and type (or dictate with Handy):
   *"I have to get from DeLucia's Brick Oven Pizza in Raritan to the Javits Center, as cheaply
   as possible."* Press Enter.
   *"A local AI model running on this laptop reads the sentence, but it only fills in a form.
   It never picks a route or a price. Here's what it understood: Raritan, marked approximate,
   because it can't confirm the pizzeria itself, so it asks me whether the town center is close
   enough. The Javits Center is a place we've verified. Cheapest first came from my words. And
   the time, home time and toll payment are labelled as defaults because I didn't say them."*
   Point at the note under the card: *"Code then checks the model's answer against my actual
   words and drops anything I didn't say."* Click **Show options**. *"Nothing runs until I
   confirm. Now it's the normal comparison: Metropark is cheapest at $29.40, and driving shows
   parking as unknown, because we don't have a sourced garage price near the Javits Center."*
   If anything's wrong, click **Change** next to that row; it jumps to the field to fix.

9. **Priorities, filters, side by side (D-21).** Click the **Cleanest** tab. *"Princeton
   Junction wins on CO₂: a 9-minute drive, then the train. The factors are EPA's, per gallon
   and per passenger-mile, in a data file with the source, and the number is labeled estimated."*
   Point at the badges: *"A badge goes only to an outright winner. All five options have zero
   transfers, so nobody gets 'Fewest transfers'. A tie is not a win."* Tap the **Avoid
   tolls** chip under the trip. *"Driving all the way and Secaucus disappear, but not silently: under
   the list it says why, with the exact tolls, and Secaucus is hidden because its drive **home**
   uses the Turnpike."* Switch **Cards → Table**: every option in one table. In
   any option's detail, the drive step has **Open in Google Maps / Apple Maps**. Tap the chip again
   afterwards.
   Tip: drag the thin bar between the list and the map to give either more room (double-click
   it to reset); the page remembers the width.

**Scenario B: Lawrenceville → Bryant Park.** *"Lawrenceville is next to Hamilton station, but
Hamilton isn't the cheapest choice: its fare is $19.75 and parking is $13, against $13.05 and
$10 at Metropark. Over a month that's $882 versus $815. The closest station isn't automatically
the best one, and that's the insight a commuter or a transit agency actually needs."*

**Scenario C (optional): Plainsboro → Times Square.** This route enters the Turnpike at a
different interchange (8A) and is priced correctly from the same official table.

---

## 3. Expected results (Thursday 10/15/2026, leave 7:00 AM, head home 5:30 PM, E-ZPass)

**A. Princeton (Nassau St) → Times Square**

| Option | Morning train | Train home | One-way | Day (round trip) | Month | Saves / month vs driving | CO₂ one way |
|---|---|---|---|---|---|---|---|
| ⭐ Park at Metropark *(Best overall · Cheapest)* | 7:59 → 8:38 | 6:00 PM, home 7:33 | **$27.60** | **$45.20** | $773.92 | **$1,215.87** | 12.6 kg |
| Park at Princeton Jct. *(Least driving · Cleanest)* | 7:38 → 8:36 | 5:55 PM, home 7:04 | $32.11 | $52.20 | $824.00 | $1,165.79 | 7.7 kg |
| Park at Hamilton | 7:30 → 8:36 | 5:55 PM, home 7:22 | $34.49 | $55.96 | $905.92 | $1,083.87 | 10.8 kg |
| Park at Secaucus | 8:37 → 8:49 | 5:55 PM, home 7:18 | $53.04 | $75.42 | $1,512.83 | $476.96 | 18.2 kg |
| Drive all the way *(Fastest)* | — | leave 5:30, home 6:47 | **$76.17** | **$95.51** | $1,989.79 | — | 18.7 kg |

CO₂ (all *estimated*): drive miles ÷ 25.5 mpg × 8.887 kg/gal, plus train miles (from the GTFS
shape: Metropark 24.6 mi) × 0.133 kg per passenger-mile. No option gets *Fewest transfers*
(all 0: a tie). Verified on Friday 10/16 with the dev server; same trains and prices.

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

**D. Plain words:** *"I have to get from DeLucia's Brick Oven Pizza in Raritan to the Javits
Center, as cheaply as possible"* (Thursday 10/15, read on Wednesday evening).

Understood card: From **Raritan (town center) (approximate for DeLucia's Brick Oven Pizza)**,
*estimated* · To **Javits Center (429 11th Ave)**, *AI generated* · When **Leave Thu Oct 15,
7:00 AM**, default · Home **5:30 PM**, default · Rank by **Cheapest first**, *AI generated* ·
Tolls **E-ZPass**, default. Question: *"I couldn't find "DeLucia's Brick Oven Pizza" exactly,
so I started from Raritan (town center). Is that close enough, or what's the street address?"*
Footer: "Read by a local AI model (qwen3:8b) · Checked the model against your words: used the
destination read exactly from your text; dropped the toll payment you didn't mention." Reading
takes 2–5 s warm. With Ollama stopped the card is identical but says "Read by the rules parser"
(~0.3 s).

After **Show options** (Cheapest tab):

| Option | Morning train | Door to door | One-way | Day | Month |
|---|---|---|---|---|---|
| ⭐ Park at Metropark *(Cheapest)* | 7:59 → 8:38 | 111 min | **$29.40** | $48.88 | $850.58 |
| Park at Princeton Jct. | 7:47 → 8:52 | 125 min | $38.03 | $64.09 | $1,071.71 |
| Park at Hamilton | 8:36 → 9:39 | 172 min | $40.41 | $67.85 | $1,153.62 |
| Park at Secaucus | 8:16 → 8:28 | 101 min | $45.46 | unknown | unknown |
| Drive all the way *(Fastest)* | — | 63 min | $30.55 + unknown parking | unknown | unknown |

Javits has no sourced garage price, so driving's total excludes parking and ranks after the
complete totals. Secaucus's trip home crosses a Turnpike pair that isn't in the toll data
(15X → 14-14C), so its day and month show unknown.

**E. Filters and your car (Scenario A, D-21).**
- **Avoid tolls:** Metropark, Princeton Jct. and Hamilton remain. *Hidden by your filters (2)*:
  Drive all the way (Turnpike 9→16E $10.29 + Lincoln Tunnel $16.79 = $27.08; congestion toll
  $6.00; trip home Turnpike 16E→9 $10.29) and Secaucus (trip home Turnpike 15X→9 $9.42). The
  free routing server offered no toll-free alternative for either.
- **Longest walk 8 min:** only Drive all the way remains; every park-and-ride is hidden with
  "Walks 24 min on the morning trip; your limit is 8 min" (7 min park-and-walk + 17 min to
  Times Square).
- **32 mpg:** gas reads "… at 32 mpg (your value)" and is labeled *user reported*; Metropark
  one-way drops to $26.68 and its CO₂ to 10.7 kg.

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
ranks the options, awards badges (unique winners only), applies the filters (listing what they
hide and why), estimates CO₂ from EPA factors in `data/emissions`, and writes the one-line
explanation. Switching to production
means swapping in Mapbox and OpenTripPlanner adapters; the cost engine and the page don't change.

The plain-words box uses the same rule. `POST /api/v1/trip/ai-parse` sends the sentence to an
`LLMProvider`: tonight a local model (qwen3:8b through Ollama), with a deterministic rules
parser as the fallback. The model must answer in a fixed schema (no extra fields). Code then
checks every value against the user's words, resolves places (verified places first, then an
OpenStreetMap address lookup that must agree on name and town, then an approximate town
center), and returns a draft request with a provenance label on each value. The page shows it
and waits for the user to confirm.

```
Browser (Leaflet page) ──POST /trip/search──▶ FastAPI
                                               ├─ TripSearchService (filter, rank, badge, explain)
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
| CO₂ 8.887 kg per gallon of gasoline | EPA "Greenhouse Gas Emissions from a Typical Passenger Vehicle" | estimated |
| CO₂ 0.133 kg / passenger-mile (commuter rail), 0.093 (subway) | EPA GHG Emission Factors Hub 2025, Table 10 (US averages) | estimated |
| Your mpg / gas price (Settings) | What you typed | user reported |
| Google / Apple Maps links | URL templates in `data/regions/nyc-metro.yaml` | — |
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
- A departure after the head-home time (default 5:30 PM) is planned one way only, and the page
  says why; set a later head-home time to see daily, monthly and yearly figures.
- **Monthly and annual figures assume you commute every working day** (250 a year, no
  vacation or remote days) and use daily garage and lot rates. Monthly garage contracts and lot
  permits are not modeled; a Midtown monthly garage contract would narrow driving's gap.
- The ranking and badges use the morning trip. The daily totals happen to rank the options the
  same way in all three scenarios.
- The Garden State Parkway is modeled only between its Raritan and Union plazas (mileposts
  125.5–142.5); a Parkway trip outside that stretch shows its toll as unknown.
- **Plain words only know verified places plus what the address lookup can confirm.** A
  business it can't confirm in a known town (DeLucia's in Raritan) falls back to that town's
  center, marked *approximate*, with a question. Anything else is left blank with a question,
  never guessed. New addresses need the internet (OpenStreetMap); with Wi-Fi off, only verified
  places and previously looked-up addresses work.
- **No Raritan Valley Line and no transfers yet.** A Raritan trip drives to a Northeast
  Corridor station (Metropark), although Raritan has its own station on the Raritan Valley
  Line. That needs a second line and, for most trains, a transfer at Newark Penn, which is Phase 2
  (OpenTripPlanner).
- **Javits Center facts that are unknown:** no sourced parking rate nearby, so driving's parking
  shows *unknown*. Its location inside the congestion zone was human-confirmed.
- "Arrive by …" in plain words is recognized but not planned. The page asks for a leave time.
- **Avoid tolls can only hide, not reroute, in most cases.** The free routing server refuses
  "exclude tolls", so the server prices the alternative routes it offers and uses a $0 one when
  there is one; otherwise the option is hidden with its tolls listed. Every Hudson crossing
  into Manhattan is tolled, so driving all the way is always hidden. Mapbox's exclude-toll
  routing is the production plan.
- **CO₂ is tailpipe CO₂ only**, from US national-average factors (not NJ TRANSIT's or MTA's own
  figures), and does not count upstream fuel or power-plant emissions. **Not yet
  human-spot-checked.**
- The **longest walk** filter counts the 7-minute park-and-walk allowance plus the walk at the
  city end of the morning trip.
- **Map-app links** hand the drive to Google or Apple Maps; their route and timing can differ
  from ours (they may pick a different toll road).
- Voice is dictation into the text box (Handy, a separate app), not a feature of WayBetter.
  Misheard place names aren't corrected by the app; an unknown town is reported as not found
  with a question, never matched to a "close" town.

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
- **"Where's the AI?"** Only in reading the request. A local model fills a validated form, code
  checks it against the user's words, and the user confirms before any search. It never
  invents routes, prices or places. It runs on the laptop (no API key, no per-call cost; only a
  place name it doesn't know goes to OpenStreetMap's address lookup), and if it's down a rules
  parser takes over. The production
  plan (D-10) swaps in a cloud model behind the same interface.
- **"What did you test?"** 304 automated tests (cost math, toll detection in both directions,
  once-a-day charges, monthly-pass math, every sort, filter and badge tie rule, CO₂, unknown
  handling, session tokens, API contract), plus end-to-end runs against the real NJ TRANSIT feed, including one with all
  network access blocked.
- **"How do you get the monthly savings?"** Daily cost × 20.8 working days, where 20.8 comes
  from the federal holiday calendar and is labeled *estimated*. For rail, the system compares a
  monthly pass with two tickets a day and uses whichever is cheaper. If any daily cost is
  unknown, the monthly figure and the savings show *unknown* too, so a partial sum never poses
  as a total.
- **"Why did the API version change?"** Adding the trip home added a request field and a
  response field, so the API contract went from 0.1.0 to 0.2.0; it is now 0.8.0 (badges
  replaced the single label, plus CO₂, filters and map links). A test fails the build if the
  code and the contract disagree.
