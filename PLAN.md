# Pokémon Team Builder — Plan

## 1. Overview

An end-to-end Pokémon team-building application:

- A responsive, searchable, filterable **catalog** of all Pokémon (name, types, stats, sprite).
- Persistent, multi-team **CRUD** — create, rename, delete teams of up to 6 Pokémon, with add / remove / drag-to-reorder (order matters), persisted across sessions.
- **Auto-fill** the remaining team slots subject to a no-overlapping-types constraint.
- **Counter-team** generation against a given opponent team (open-ended optimization).
- A background **change alerter** that detects PokéAPI data changes affecting a user's Pokémon and surfaces an alert if the change occurred within the last 7 days.

Data comes from [PokéAPI](https://pokeapi.co). The **frontend never calls PokéAPI directly** — the backend mirrors the data and is the single source of truth for both the UI and the change-detection job.

This plan is time-boxed to roughly **8 hours**. The goal is a working vertical slice of *every* required feature behind clean, swappable boundaries, with documented decisions — not maximal feature polish. Non-goals and next steps are in §11, and the full decision log (with alternatives considered) lives in [`DECISIONS.md`](./DECISIONS.md).

---

## 2. Technology stack

| Layer | Choice | Why (summary — see `DECISIONS.md` for alternatives) |
|---|---|---|
| Frontend | **Vite + React + TypeScript** | Fast dev loop, typed end-to-end |
| Server state | **TanStack Query** | Caching, refetch, optimistic updates with little code |
| Styling | **Tailwind CSS** | Minimal but clean UI without a heavy component library |
| Drag & drop | **dnd-kit** | Accessible, lightweight reorder |
| API | **FastAPI (async)** | Async I/O for the PokéAPI fan-out, typed Pydantic contracts, free OpenAPI docs |
| HTTP client | **httpx + tenacity** | Async client with exponential-backoff retry for transient failures |
| Persistence | **SQLite via SQLAlchemy 2.x** | Zero-config, ships in a single container, runs anywhere; the ORM keeps the engine swappable |
| Packaging | **uv** | Fast, reproducible (`uv.lock`), one tool for env + dependencies |
| Scheduler | **APScheduler (in-process)** | Simple background job; the work is also a manually triggerable endpoint |
| Run | **docker compose (local)** | Single-command startup for the reviewer; mirrors a real multi-service topology |

---

## 3. Architecture

A classic **3-tier** application (presentation → API → data) with clean, directional layering inside the backend: thin FastAPI routers → services / domain (pure business logic) → adapters (concrete infrastructure). The swap seam is **FastAPI dependency injection**, wired in `app/api/deps.py`: routers depend on injected providers, not on hand-written interfaces. Every part the case study is likely to want swapped (database, PokéAPI client, identity, counter-team algorithm) is selected in one place and overridable in tests. (We started with a formal `Protocol`-based ports layer and removed it — see ADR-022; the domain stays framework-agnostic regardless.)

```
React (Vite + TS, TanStack Query)              ── presentation
        │  HTTP / JSON  (same-origin via proxy)
FastAPI routers + Pydantic schemas             ── API / transport (thin)
        │  Depends(...)  ← deps.py selects the implementation
Services / domain (use-cases, pure logic)      ── business logic, framework-agnostic
        │  hold / call ↓
Adapters: httpx client · SQLAlchemy repos ·
          cookie identity · greedy strategy            ── infrastructure
        │
SQLite (file, persisted; in-memory for tests)  ── data
```

**What the DI seam buys us** (each swap is a one-line change in `deps.py`, plus the new implementation):

- **Swap SQLite → Postgres** for production: write a new repository class and change the connection string. The routers and domain do not change.
- **Swap anonymous cookie → real auth (OAuth/JWT)**: write a new identity provider and point `_identity` at it. Routers and domain do not change.
- **Swap greedy → simulated annealing / ILP** for the counter-team: write a new strategy and return it from `get_counter_strategy()`. The endpoint does not change.
- **Tests** override these dependency providers — a duck-typed `FakePokeApiClient` and an in-memory SQLite database — so they are fast and hermetic (no network, no shared state). No `Protocol` is needed for the fake to substitute.

---

## 4. Data model

SQLAlchemy models over SQLite. JSON columns use SQLAlchemy's portable `JSON` type (TEXT in SQLite, upgradeable to JSONB in Postgres).

```
users         id (UUID, pk), created_at
pokemon       id (int, pk = PokéAPI id), name, types (JSON list[str]),
              stats (JSON dict: hp/attack/defense/sp_atk/sp_def/speed),
              sprite_url, snapshot (JSON: the normalized fields, used for diffing),
              fetched_at
teams         id (UUID, pk), user_id (fk → users), name, created_at, updated_at
team_members  team_id (fk → teams, cascade delete), pokemon_id (fk → pokemon),
              slot (int 0..5), pk (team_id, slot)        # slot encodes order
change_events id (UUID, pk), pokemon_id (fk → pokemon), detected_at,
              diff (JSON: per-field old → new)
type_chart    attacking_type (pk), multipliers (JSON: defending_type → float)
```

Notes:

- The change detector **diffs the normalized `snapshot`** (the handful of fields the app uses), not the full PokéAPI payload — otherwise irrelevant fields (cries, game indices, move lists) would generate noisy false alerts.
- **User alerts are computed at query time**: `change_events ⋈ team_members ⋈ teams`, filtered by `user_id` and `detected_at > now() − 7 days`. There is no separate alerts table; events are the source of truth.

---

## 5. API surface

```
GET    /api/pokemon                 list — ?q= &type= &sort= &limit= &offset=
GET    /api/pokemon/{id}            single Pokémon detail
GET    /api/teams                   current user's teams
POST   /api/teams                   create team
GET    /api/teams/{id}              team detail
PUT    /api/teams/{id}              rename / set members / reorder
DELETE /api/teams/{id}              delete team
POST   /api/teams/{id}/autofill     fill empty slots, no overlapping types
POST   /api/counter-team            body: opponent team → counter team + score breakdown
GET    /api/me/alerts               recent change events affecting current user
POST   /admin/scan-changes          manually trigger the change-detection job
POST   /admin/simulate-change       dev hook: mutate a stored snapshot to demo an alert
GET    /healthz                     liveness
```

All user-scoped endpoints derive `user_id` from the identity cookie; there are no cross-user reads. `/admin/simulate-change` exists so a reviewer can actually *see* a change alert without waiting for the real PokéAPI to change (it rarely does) — a deliberate demoability and testability hook.

---

## 6. Counter-team & auto-fill (one engine)

Both features share a single solver built on a type-effectiveness matrix.

- **TypeChart** — `effectiveness(attacking_type, defender_types) → float`, from the 18×18 matrix derived from PokéAPI's `/type/{name}` `damage_relations` (so it isn't hand-transcribed).
- **Objective function** (weights returned in the API response for transparency):
  - *Offensive coverage* — does the team have a super-effective attacker for each opponent?
  - *Defensive resistance* — do team members resist the opponent's attacking types?
  - *Stat edge* — base-stat-total comparison.
  - *Shared-weakness penalty* — discourage many members sharing one weakness.
- **Counter-team** — greedy: fill each slot with the candidate that maximizes the marginal objective. Returns the team **and** the per-component score breakdown.
- **Auto-fill** — the same engine with a constrained objective: candidates whose types overlap any current team member are rejected; greedy fills the remaining slots.

Greedy is fast, deterministic, and explainable. A simulated-annealing refinement is documented as a next step (§11), not built — at this team size the quality gain does not justify the time and tuning within the budget.

---

## 7. Change alerter

- An in-process **APScheduler** job runs periodically; the same logic is exposed at `POST /admin/scan-changes` for on-demand runs. The job body is a pure function — the scheduler is just one caller, so the work could be extracted to a separate worker later without changing it.
- Each run re-fetches **only the Pokémon that appear in some team** (not all ~1350 — wasteful given how rarely the data changes), diffs the normalized snapshot against what's stored, and writes a `change_events` row with a structured `old → new` diff for any changed field (name, types, stats, sprite).
- The frontend polls `GET /api/me/alerts` and shows a banner for events from the last 7 days that touch the user's Pokémon.

---

## 8. Identity

A persistent **anonymous user**: on first request the backend issues a UUID in an HTTP-only cookie; subsequent requests reuse it. This satisfies the requirements that teams persist across sessions and that multiple users be supported, without putting an authentication wall in front of the reviewer.

This is deliberately *identity* without *authentication*. The cookie identity provider is injected via `deps.py`, so adding real auth later (email + provider id, a login flow that re-associates the anonymous id) is a localized change — a new provider class selected in one place.

---

## 9. PokéAPI integration & seeding

- The backend keeps a **local mirror** of the normalized Pokémon fields plus a snapshot for diffing. One source of truth for the UI and the change detector; the app keeps working if PokéAPI is down.
- For reviewer reproducibility, a **pre-fetched normalized fixture** (`data/pokemon_seed.json`, ~1350 Pokémon) is committed to the repo and loaded on startup, so `docker compose up` is fast and works offline.
- A `seed.py` script (async httpx + tenacity, bounded concurrency) re-pulls live data and regenerates that fixture on demand — the live-fetch path is real and tested, but the reviewer's startup never depends on PokéAPI uptime.
- Sprite *images* are referenced by URL (raw.githubusercontent.com); the JSON data loads offline, but rendering sprites needs internet. A backend sprite cache is a documented next step (§11).

---

## 10. Testing strategy

Critical-path first, all hermetic (FakePokeApiClient + in-memory SQLite):

1. **Type effectiveness** — multiplier correctness (e.g. fire→grass = 2×, fire→water = 0.5×, dual-type stacking).
2. **Counter-team / auto-fill** — golden cases (a mono-Fire opponent yields counters skewing Water/Rock/Ground) and invariants (≤ 6 members, no duplicates, auto-fill never overlaps existing types).
3. **Change detection** — table-driven over synthetic before/after snapshots (stat change, type change, sprite change, and a no-op that must *not* alert).
4. **Identity** — cookie issued on first request, reused after, teams scoped per user, no cross-user leakage.

A single React Testing Library test on the team-builder interaction (add / remove / reorder) is included if time allows.

---

## 11. Running it

**Single command (intended path):**

```
docker compose up
```

Brings up the frontend, backend, and a seeded SQLite database. No network required for data (sprite images excepted). The app is served at the URL printed in the README.

**Native dev (no Docker):** run the backend with `uv run uvicorn` and the frontend with `npm run dev`; SQLite is a local file.

---

## 12. Non-goals & next steps

Deliberately out of scope for the time-box, with a clear upgrade path:

- **Real authentication** — anonymous identity today; OAuth/JWT via a new identity provider selected in `deps.py`.
- **Postgres in production** — SQLite locally; swap the repository implementation + connection string.
- **Simulated-annealing / ILP counter-team** — greedy today; a stronger strategy returned from `get_counter_strategy()`, with a benchmark to justify it.
- **WebSocket push for alerts** — currently polled.
- **Sprite caching/proxy** — to make the app fully offline-complete.
- **Team sharing** (public URLs) and broader frontend test coverage.
