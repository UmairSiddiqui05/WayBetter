# Overnight / Unattended Run Prompts

Copy-paste work orders for running an agent while nobody is watching. Designed so an unattended agent **proposes** (branch + pull request) and the human **approves** (merge) in the morning — nothing lands on `main` without review.

Standing rules baked into every prompt below: branch-only, PR-not-merge, no spending, no account creation, no fabricated verification.

---

## Run 1 — A1 Scaffold (+ keyless parts of A2)

Paste this into a Claude Code session pointed at this repo:

```
Read CLAUDE.md, PROGRESS.md, and docs/agent-tasks.md (brief A1), then execute brief A1 — Scaffold & Infrastructure.

Rules for this unattended run:

1. Work on a new branch `agent/a1-scaffold`. Never commit to main, never merge, never force-push.
2. Follow CLAUDE.md's architecture rules exactly. No secrets in code — all config from environment, and keep .env.example current if you add a variable.
3. Any Pydantic model or endpoint you create must mirror docs/api-spec.yaml exactly. That file is the contract; if you believe it is wrong, stop and write the disagreement in PROGRESS.md instead of deviating.
4. Definition of done is in the A1 brief. Meet it, then open a PR titled "A1: scaffold & infrastructure" whose body lists: what you built, what you actually verified (with the command output), and what you could NOT verify in this environment.
5. If Docker is unavailable in your sandbox, still write the compose and config files, verify everything you can (imports, lint, type check, pytest, FastAPI boots, OpenAPI parity with docs/api-spec.yaml), and clearly label the unverified parts in both the PR body and PROGRESS.md. Do not claim verification you did not perform.
6. Update PROGRESS.md before you finish: check off completed items and append a work-log entry (date, role, what changed, files touched, requirement IDs, surprises).
7. If A1 is done and you have time left, continue with brief A2 but ONLY the parts needing no API keys, credentials, or payment: keyless public feeds (MTA subway, LIRR, Metro-North, PATH), OSM extract tooling, region config schema and loader, canonical station ID mapping tables. Skip NJ Transit entirely — it needs portal credentials the human must create. Put that work on a separate branch `agent/a2-ingestion` with its own PR.
8. Never spend money, create accounts, accept terms, or enter credentials. If you are blocked on any of those, record the blocker in PROGRESS.md and move to the next unblocked task.
9. If reality conflicts with PLAN.md, stop and write it up in PROGRESS.md rather than improvising.
```

---

## Run 2+ — Generic "next item" prompt

Once A1/A2 are merged, this prompt self-advances through the board:

```
Read CLAUDE.md and PROGRESS.md. Pick the next unclaimed item in the earliest incomplete phase, then read its brief in docs/agent-tasks.md and execute it.

Same unattended rules as always: work on a branch named `agent/<brief-id>-<slug>`, never commit to main, never merge, open a PR when the brief's definition of done is met, and state in the PR body exactly what you verified versus what you could not. Satisfy the docs/verification.md fixtures your brief cites. Update PROGRESS.md (checklist + work-log entry) before finishing. Never spend money, create accounts, or enter credentials — record such blockers in PROGRESS.md and move to the next unblocked task. If reality conflicts with PLAN.md, stop and write it up instead of improvising.
```

---

## Human checklist for the morning

1. Open the PR; read the "what I could not verify" section first.
2. Pull the branch and run it yourself if it touches routing, parking, fares, or tolls (CLAUDE.md requires a human spot-check on those).
3. Confirm CI is green.
4. Merge, or leave review comments and re-run the agent against the same PR.
5. Skim the PROGRESS.md work-log entry — if it says something surprising, believe it and investigate.
