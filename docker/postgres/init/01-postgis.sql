-- Runs once, on first initialisation of the Postgres data volume.
-- PostGIS is not optional: city_driving_zone polygon intersection (F-07),
-- toll-crossing geometry matching (F-13), and station/parking geography all
-- depend on it. /readyz reports "degraded" if this did not run.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Deterministic UUID generation for canonical IDs (N-03).
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
