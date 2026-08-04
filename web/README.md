# web/ — placeholder

The Next.js + MapLibre client is **A8's** brief (see
[docs/agent-tasks.md](../docs/agent-tasks.md)). Nothing is scaffolded here yet
on purpose: CI's `web` job activates the moment `web/package.json` exists, and
an empty scaffold would turn that job green without proving anything.

Two rules A8 inherits from [CLAUDE.md](../CLAUDE.md):

- **No business logic in TypeScript** (N-01). No fare, score, label, or
  explanation computation client-side — the API returns display-ready JSON.
- **The TS client is generated** from the OpenAPI document
  (`/api/v1/openapi.json`, mirroring [docs/api-spec.yaml](../docs/api-spec.yaml)),
  never hand-written.

The browser map uses `MAPBOX_PUBLIC_TOKEN` / `MAPTILER_API_KEY` — domain-restricted
public tokens. Every secret token stays server-side (N-05).
