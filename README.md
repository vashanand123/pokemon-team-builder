# Pokémon Team Builder

An end-to-end Pokémon team-building app: browse a searchable catalog with a faceted filter
(multi-type Any/All + per-stat min/max), sign up, build and persist multiple teams (drag to reorder),
auto-fill a team with non-overlapping types, generate a counter team that beats an opponent's team
(genetic algorithm following [sbgames-2020](https://www.sbgames.org/proceedings2020/ComputacaoFull/208698.pdf)),
and get alerted when PokéAPI data affecting one of your Pokémon changes.

Design rationale lives in [PLAN.md](./PLAN.md) and [DECISIONS.md](./DECISIONS.md) (43 short
ADRs — one paragraph each, with the reviewer-driven decisions carrying a **Human-in-the-loop**
attribution).

## Run it

### Option A — Docker (single command)

```bash
docker compose up --build
```

Then open **http://localhost:8080**. No network needed for data (the ~1,350-Pokémon
catalog is a committed fixture loaded into SQLite on startup); sprite *images* load from
GitHub if you're online. API docs at http://localhost:8080/docs.

> **Re-running after a schema change?** SQLite + `create_all` can't add columns to an existing
> table — drop the volume and let it re-seed: `docker compose down -v && docker compose up --build`.
> (Alembic is the documented production path.)

### Option B — Native dev (two terminals)

Prereqs: [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
# backend → http://localhost:8000
cd backend && uv sync && uv run python -m uvicorn app.main:app --reload --port 8000

# frontend → http://localhost:5173 (proxies /api + /healthz to :8000)
cd frontend && npm install && npm run dev
```

## Features

| Feature | Notes |
|---|---|
| Auth | Username + password (argon2id, opaque server-side sessions). Sign up, log in, log out. Catalog is public; everything else requires a session. Username is deliberate vs email so multiple throwaway demo accounts don't need N inboxes (ADR-041). |
| Catalog | All ~1,350 Pokémon; name search with autocomplete + a **faceted filter** — multi-select types with **Any/All** (Any = OR; All = dual-type AND, e.g. Fire+Flying ⇒ Charizard) + **min/max per stat** (ADR-035); sort by any stat asc/desc; responsive grid; stat bars on each card. |
| Teams | Create / rename / delete multiple teams; add, remove, drag-reorder up to 6 members. Catalog cards show an amber "Type clash" CTA when adding would duplicate an existing member's type set (ADR-043). Explicit Save button on new-team creation. |
| Auto-fill | Fills empty slots with the strongest Pokémon whose types don't overlap *any* existing member (uses the strict no-shared-types rule even though the save validators use the softer no-identical-sets rule — see ADR-043). |
| Counter team | **Genetic algorithm** over the sbgames-2020 CP × type-effectiveness fitness (ADR-032), constrained to **no duplicate type *sets*** (ADR-043). Repeated "generate" calls "wiggle" to different teams; saved counters render as tabs over a single card so multiple don't stack vertically. |
| Change alerter | Hourly in-process job (and `POST /admin/scan-changes`): **discovers new species**, **diffs the whole catalog** for stat/name/type/sprite changes, and **detects new battle types** (ADR-036). Users see an amber banner for changes touching their Pokémon in the last 7 days. |

## Architecture

Classic **3-tier** (React → FastAPI → SQLite) with a flat 3-folder backend (post-ADR-037):

- **`app/api/`** — thin HTTP routers; one composition root (`deps.py`) for DI providers.
- **`app/business/`** — pure logic: the GA strategy, type chart, snapshots, change-scan
  orchestrator, password hasher, business dataclasses (`Pokemon`, `Team`, `CounterTeam`,
  `User`, `Alert`). No DB imports.
- **`app/adapters/`** — ORM↔business translation: SQL repos, the httpx PokéAPI client,
  password-hash + session-store adapters. Each repo's `_to_business(row)` helper is the
  one boundary where ORM rows become business dataclasses (ADR-038).
- **`app/db/`** — SQLAlchemy ORM rows (suffixed `*Row` so a stray un-suffixed reference
  outside `adapters/` is visually a tell), async engine, seed pipeline.

Swappability comes from **FastAPI dependency injection** in `deps.py`, not from `Protocol`
interfaces (ADR-022/024). Swapping an implementation — SQLite→Postgres, argon2→bcrypt,
DB-backed sessions→Redis, OAuth/OIDC for auth, a different counter solver — is a one-line
change in `deps.py`. Tests override those dependencies with fakes or an in-memory DB.

**Stack:** FastAPI (async) · SQLAlchemy 2.x · SQLite · uv · argon2-cffi · httpx + tenacity ·
APScheduler · React + Vite + TypeScript · TanStack Query · Tailwind · dnd-kit.

## API

```
# Auth (ADR-039/041)
POST   /api/auth/signup            body: {username, password}  → 201 + Set-Cookie session
POST   /api/auth/login             body: {username, password}  → 200 + Set-Cookie session
POST   /api/auth/logout                                        → 204; revokes session + clears cookie
GET    /api/auth/me                                            → current user or 401

# Catalog (public)
GET    /api/pokemon                ?q= &type= &sort= &limit= &offset=
GET    /api/pokemon/{id}

# Teams (session-scoped)
GET    /api/teams                  current user's teams
POST   /api/teams                  create (body: {name, member_ids})
GET/PUT/DELETE /api/teams/{id}     detail / update (name, members, order) / delete
POST   /api/teams/{id}/autofill    fill empty slots, no overlapping types

# Counters (session-scoped)
POST   /api/teams/{id}/counters/generate  body: {include_forms?} → GA preview (stochastic, unique vs saved)
POST   /api/teams/{id}/counters           body: {member_ids}      → save (must pass ADR-043 + not be a duplicate)
GET    /api/teams/{id}/counters           list saved counters for the team
DELETE /api/counters/{id}                 delete a saved counter

# Alerts (session-scoped)
GET    /api/me/alerts              recent change events affecting current user's teams (last 7 days)

# Admin (dev hooks — unauthenticated, see ADR-016)
POST   /admin/scan-changes                       run discover + diff + new-type detection now
POST   /admin/simulate-change?pokemon_id=ID      inject a synthetic change to demo the alert

GET    /healthz · /docs
```

Wrong-password and unknown-username return identical `401` detail (no existence oracle).
Cross-user access returns `404`, not `403` (no existence leak on team/counter ids).

## Seeing the change alerter

Real PokéAPI data rarely changes, so there's a dev hook. With the app running (`docker compose up`):

1. Open **http://localhost:8080**, sign up as any user, and add **Pikachu** (#25) to one of your
   teams. The alert feed is scoped to "Pokémon on a team you own," so this step is what makes the
   change visible *to you*.
2. From any shell — no cookie needed; the admin hook is intentionally unauthenticated for the demo
   (ADR-016):
   ```bash
   curl -X POST "http://localhost:8080/admin/simulate-change?pokemon_id=25"
   ```
3. Back in the browser, reload (or wait ≤60 s — the alert feed polls on an interval) → an amber
   banner reports the synthetic change for Pikachu.

`POST /admin/scan-changes` runs the real PokéAPI diff + new-species discovery + new-type detection
(ADR-036); the in-process scheduler also runs it hourly.

## Tests

```bash
cd backend
uv run pytest -q             # 64 tests (full suite, ~11 s)
uv run pytest -m unit -q     # 22 unit tests (no DB, no HTTP — ~0.5 s)
uv run pytest -m integration # 42 integration tests (real DB + TestClient via api_client fixture)

cd ../frontend && npx playwright install chromium && npx playwright test   # browser e2e (optional)
```

The Playwright e2e clicks through the whole flow: sign up → build a team → persist across reload →
auto-fill → counter team → simulate change → alert banner.

## Assumptions & known limitations

- **No email column** — username only (ADR-041). No verification email, no password-reset link.
  The signup confirm-password field is the only typo defense; a forgotten password means
  creating a new account. Documented as a "when this goes public" item.
- **Catalog includes alternate forms / megas** (PokéAPI ids > 10000); the counter / auto-fill
  pool draws from base species only (id ≤ 1025 — ADR-015) for sensible suggestions. An
  `include_forms` toggle opens the pool when you need a forms-heavy answer (ADR-029).
- **Counter team uses types + base stats only** — no movesets, abilities, items, or status.
  Fitness is `Σ CP × type-effectiveness` over every (counter × rival) pairing (ADR-032). The
  diversity constraint (ADR-043 soft rule: no identical type sets) keeps teams sensible without
  the strict rule's over-restriction. Honest tradeoff carried forward: the paper's fitness is
  unbounded and CP-leaning; a bounded coverage-aware objective is the next iteration if winning
  real battles mattered.
- **Sprites are external URLs** — data works offline, images need internet.
- **SQLite + in-process scheduler** — right for a local, single-process deployment; see
  DECISIONS.md ADR-009 for the Postgres / external-worker path at scale.
- **Resource caps** — 20 teams per user, 6 members per team, up to 10 saved counters per source
  team. Rate limiting and admin auth (`is_admin` is a placeholder column, ready for a `Depends`
  gate) are documented as deployment hardening (ADR-026 / ADR-016).
- **Change-scan load** — hourly, ~1,300 PokéAPI fetches with bounded concurrency + tenacity
  backoff; fine for one instance. A rolling slice (oldest-`fetched_at` first, plus
  always-team-members) is the named next step (ADR-036).
- **Alert delivery is polling** (`refetchInterval: 60_000`) → up to a minute of visibility lag.
  SSE → Redis pub/sub is the named upgrade ladder once the scan externalizes to a worker.
