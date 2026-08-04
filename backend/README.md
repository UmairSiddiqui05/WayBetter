# WayBetter backend

FastAPI service for the park-and-ride decision engine. All routing, scoring,
labeling, and explanation logic lives here — clients are thin renderers (N-01).

## Layout

```
app/
  main.py            application factory, router wiring, OpenAPI metadata
  config.py          settings (environment only; secrets as SecretStr)
  logging.py         structlog setup
  api/
    health.py        ops liveness/readiness — root paths, off the versioned contract
    v1/router.py     the /api/v1 surface defined by docs/api-spec.yaml (A3 fills it)
  db/session.py      async SQLAlchemy engine/session; `Base` for A3/A5 models
  cache/client.py    Redis client (cache + rate-limit store)
  health/probes.py   Postgres/PostGIS, Redis, OTP infra probes
  regions/           region config schema + loader (regions are data, N-03)
  ingestion/         GTFS download, validation, canonical station IDs; `cli.py`
tests/               pytest suite
```

Directories that later agents own — `providers/` (N-04 interfaces + adapters,
A4/A7) and `scoring/` (A6) — are created by those briefs, not pre-stubbed here.

## Ingestion CLI

Installed as `waybetter-ingest` (also `make check-region`, `fetch-feeds`,
`station-map`, `osm-plan`):

| Command | Does |
|---|---|
| `check-region` | Validates the region config and reports every missing zone polygon, missing data directory, and unverified feed licence. |
| `fetch` | Downloads enabled feeds, validates them structurally, and writes a committed `data/gtfs/<feed>.meta.json` provenance record (source URL, licence, retrieved-at, SHA-256, feed version). Re-runs report "unchanged" rather than rewriting. |
| `build-station-map` | Assigns canonical station IDs and writes `data/regions/<region>-stations.csv`. Deterministic — rebuilding is a no-op diff. |
| `osm-plan` | Prints the OSM extract pipeline with the clip box derived from the region config. Prints rather than runs; the commands are unverified. |

## Endpoints in this scaffold

| Path | Purpose |
|---|---|
| `GET /healthz` | Liveness. Dependency-free, so a dead datastore cannot cause a restart loop. |
| `GET /readyz` | Readiness. Probes Postgres (+PostGIS) and Redis; `503` when either is down. OTP is reported but does not gate — it has no graph until A2. |
| `GET /api/v1/docs`, `GET /api/v1/openapi.json` | Generated contract docs. Empty of paths until A3. |

Health endpoints are excluded from the generated OpenAPI on purpose:
[docs/api-spec.yaml](../docs/api-spec.yaml) is the contract and does not define
them, so keeping them off `/api/v1` lets the generated schema stay an exact
subset of the contract. `tests/test_openapi_parity.py` enforces that.

## Local development

From the repo root, `make up` runs everything in Docker. To run the API on the
host instead:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env      # then edit
uvicorn app.main:app --reload
```

## Checks

```bash
ruff check . && ruff format --check .   # lint + format
mypy                                    # strict, config in pyproject
pytest -q                               # no datastore required
```

The test suite deliberately runs without Postgres, Redis, or OTP: readiness
probes are injected in tests, and no fixture opens a real connection.
