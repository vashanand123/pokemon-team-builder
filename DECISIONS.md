# Architecture Decision Records

One-paragraph entries per design choice. Status values: `Accepted`, `Superseded by ADR-NNN`,
`Partially superseded`. Where a decision was driven by an explicit reviewer prompt, a
**Human-in-the-loop** note attributes it.

---

## ADR-001 — Backend framework: FastAPI
**Status:** Accepted

Async-native (the seed/scan fan out HTTP), Pydantic-typed contracts double as docs, `/docs` is free. Flask needs async + validation as bolt-ons; Django is sync-first and too heavy for an API-only app of this size.

---

## ADR-002 — Packaging: uv + committed `uv.lock`
**Status:** Accepted

One fast tool for venv + dependency resolution + lockfile. Faster than Poetry, simpler than pip+venv+pip-tools, deterministic across machines.

---

## ADR-003 — Database: file-based SQLite via SQLAlchemy
**Status:** Accepted

Zero setup, persists across restarts, ships inside one container — reviewer runs one command. The ORM keeps the engine abstracted; Postgres is a connection-string swap. Production needs Alembic (named, not built); `create_all` is enough while the schema is greenfield.

---

## ADR-004 — Repository pattern over SQLAlchemy
**Status:** Accepted (extended by ADR-038)

Services depend on repository classes, SQLAlchemy lives in adapters. Engine swap and hermetic testing become local changes — worth the small per-entity boilerplate.

---

## ADR-005 — Anonymous UUID-cookie identity (no auth)
**Status:** Superseded by ADR-039

UUID in an HttpOnly cookie *is* the identity. Multi-user semantics without a signup wall for reviewer demo; real auth was named as a localized future change behind the same seam. (Replaced when ADR-039 added required login.)

---

## ADR-006 — Backend mirror + committed seed fixture
**Status:** Accepted

Backend mirrors PokéAPI; the catalog ships as a committed JSON fixture loaded on first boot. Instant, offline, deterministic startup — and the live-fetch code path still exists for the change alerter, so it stays exercised.

---

## ADR-007 — Type chart derived from PokéAPI
**Status:** Accepted

Derive the 18×18 effectiveness matrix from `/type` at seed time; don't hand-code. Single source of truth, no transcription errors.

---

## ADR-008 — Counter-team algorithm v1: greedy + weighted objective
**Status:** Superseded by ADR-019 → ADR-020 → ADR-028 → ADR-032

Greedy selection over (coverage, defense, stat edge, diversity). Fast and explainable but the BST term dominated — the objective was iterated four times and ultimately replaced by the sbgames-2020 GA (ADR-032).

---

## ADR-009 — Background job: in-process APScheduler
**Status:** Accepted

APScheduler in-process; scan logic also exposed at `POST /admin/scan-changes` so the scheduler is just one caller. One process to run for a reviewer; the job is a pure function the scheduler delegates to, so it externalizes cleanly to a worker later.

---

## ADR-010 — Local `docker compose` (no hosting)
**Status:** Accepted

One command, no hosting flakiness during a review window, faithful multi-service topology under the reviewer's control. Hosted is a straightforward follow-up.

---

## ADR-011 — Frontend stack: Vite + React + TS + TanStack Query + Tailwind + dnd-kit
**Status:** Accepted

Server-state caching (TanStack), minimal styling system (Tailwind), accessible drag-and-drop (dnd-kit). No component library, no Redux — most state here is server state.

---

## ADR-012 — `httpx` + `tenacity` for PokéAPI calls
**Status:** Accepted

Async client with declarative retry (exponential backoff + jitter on transient 5xx / 429 / network errors) and bounded concurrency. Robust seeding without bespoke retry loops.

---

## ADR-013 — SQLite PRAGMAs: `foreign_keys`, WAL, `busy_timeout`
**Status:** Accepted

SQLite ignores FKs by default (so `ON DELETE CASCADE` wouldn't fire); WAL + `busy_timeout=5000` let the background scan write while requests serve. Applied per-connection on the SQLite backend only.

---

## ADR-014 — Test isolation
**Status:** Refined by ADR-031, then ADR-040

Unit tests against in-memory SQLite + `FakePokeApiClient`; API tests against a throwaway file DB via `DATABASE_URL`; Playwright e2e with its own DB and the scheduler off. Hermetic, repeatable.

---

## ADR-015 — Base-species pool for counter/autofill (id ≤ 1025)
**Status:** Accepted

The catalog includes alternate forms / megas / gmax (PokéAPI ids > 10000), which dominate stat-aware optimization and clutter suggestions. Counter and autofill draw from base species only; the catalog UI still shows everything. Forms can be opted in via ADR-029's toggle.

---

## ADR-016 — Admin demo hooks (`/admin/scan-changes`, `/admin/simulate-change`)
**Status:** Accepted

Real PokéAPI changes are rare — the alerter would be invisible during a review. Endpoints are unauthenticated and dev-only (named for future gating with the admin role added in ADR-039).

---

## ADR-017 — Same-origin via reverse proxy
**Status:** Accepted

Frontend and API share one origin: Vite proxy in dev, nginx in the container. HttpOnly + SameSite=Lax cookie just works, no CORS config.

---

## ADR-018 — Normalized persistence (columns over JSON blobs)
**Status:** Accepted

`pokemon` got real columns (`type1`/`type2` + six stats) so search/filter/sort run in SQL on indexable values. Read-only `types`/`stats`/`snapshot` views preserve the convenient shape. JSON is kept where it's genuinely document-shaped (`counter_teams.member_ids`, `change_events.diff`).

---

## ADR-019 — Counter objective: matchup-first (4 terms)
**Status:** Superseded by ADR-020 → ADR-032

Replaced ADR-008's BST-driven score with `threat_coverage + defensive_resilience + speed_control + type_synergy`. ADR-008 had the BST term dominate → counter teams were always legendaries. Itself replaced when ADR-020 collapsed threat/defense into a single damage-race.

---

## ADR-020 — Counter objective: 1v1 damage-race (stats made decisive)
**Status:** Superseded by ADR-032

`advantage(c, o) = damage_rate(c→o) / (damage_rate(c→o) + damage_rate(o→c))` folds in type effectiveness both ways AND the stat gap. A frail super-effective pick correctly loses to a bulky hard-hitter. (Replaced when ADR-032 adopted the sbgames-2020 GA's fitness.)

---

## ADR-021 — Data scope: name/types/stats/sprite + species flags
**Status:** Accepted

Store the four fields the spec names plus `is_legendary`/`is_mythical` from `/pokemon-species` (one cheap extra fetch at seed time only). Movesets/abilities/items would need their effects (`/move`, `/ability`) and a turn-resolution engine — a separate, larger project the brief didn't ask for.

---

## ADR-022 — Drop the ports layer; DI-only
**Status:** Accepted (reaffirmed in ADR-024; refined by ADR-037)

Removed `app/ports` Protocols. They were unenforced documentation — Python ignores type hints at runtime and we run no type checker. Swappability was always provided by FastAPI DI (`app/api/deps.py`), not by the Protocols; SQLite→Postgres / cookie→OAuth is still a one-line change in `deps.py`.

---

## ADR-023 — Three counter modes (freeform / no_legendaries / stat_capped)
**Status:** Superseded by ADR-033

`CounterMode` enum routed to one engine via different `(pool, max_total_bst)` pairs. (Later removed at the reviewer's request — too many concepts for niche value.)

---

## ADR-024 — Revisited: DI-only vs Protocols (given planned swaps + AI-assisted dev)
**Status:** Accepted (reaffirms ADR-022)

Keep DI-only; do not adopt pyright/Protocols now. A Protocol's payoff requires a static type checker — adopting pyright is the real upgrade if we want machine-checked contracts for AI agents. Named upgrade trigger: when a checker lands, introduce targeted Protocols on the genuine swap seams (identity, strategy, PokéAPI client) — not a blanket ports layer.

---

## ADR-025 — Persist counter teams (team-scoped + saved)
**Status:** Accepted

Counters are tied to their source team via FK CASCADE and persisted. New endpoints: `POST /api/teams/{id}/counters` (save), `GET /…/counters` (list), `DELETE /api/counters/{id}`. Members stored as ordered JSON — a saved counter is a read-only algorithm snapshot, never queried relationally (same JSON-vs-relational call as ADR-018).

---

## ADR-026 — Resource caps on user-created data
**Status:** Accepted

20 teams/user, ≤10 counters/team, 6 members/team, catalog `limit ≤ 2000`. Anonymous identity (then) meant anyone could create data → bound the *stored* shape. Request rate-limiting + admin auth named as deployment-hardening, not built.

---

## ADR-027 — Lazy user creation (defuse the cookieless-flood DoS)
**Status:** Superseded by ADR-039

Identity was stateless on read — UUID cookie issued without a DB write; the `users` row was created lazily on first write. Bounded the DoS surface to writes, not requests. (Superseded once real auth landed — every user now has a row at signup.)

---

## ADR-028 — Counter v2: stochastic + generate/save split + 5-term objective
**Status:** Partially superseded (objective by ADR-032; generate/save split still stands)

`counter_team(top_k, rng)` gives variety per regeneration; `POST .../generate` is an ephemeral preview, `POST .../counters` persists with the score recomputed from members. Added `resist_coverage` + `role_balance` to the objective.

---

## ADR-029 — Neutral-coverage floor + `include_forms` toggle
**Status:** Partially superseded (floor by ADR-032; `include_forms` still stands)

Without a floor a type-immune frail mon scored ~1.0 and falsely beat legendaries. The floor required the pick to also survive the opponent's raw power. `include_forms=True` opens the pool to megas/primals so a counter can match a forms-heavy opponent team.

---

## ADR-030 — Hybrid coverage gate (soft, not hard constraint)
**Status:** Superseded by ADR-032

Multiplicative soft gate on the weighted score (rather than a hard set-cover formulation) — preferred coverage strongly without an infeasibility cliff. Removed when ADR-032 replaced the bespoke objective entirely.

---

## ADR-031 — Engine-agnostic test fixture (one `DATABASE_URL` knob)
**Status:** Refined by ADR-040

Single `session` fixture in `conftest.py` built from `settings.database_url` — the one engine knob. Point `DATABASE_URL` at a Postgres test DB and the same suite runs unchanged. Real way to close ADR-014's "won't catch Postgres-specific bugs" blind spot.

---

## ADR-032 — Counter engine rewritten to the sbgames-2020 Genetic Algorithm
**Status:** Accepted (supersedes the objectives of ADR-008/019/020/028/029/030)

**Human-in-the-loop.** Reviewer directive to follow the [sbgames-2020 paper](https://www.sbgames.org/proceedings2020/ComputacaoFull/208698.pdf).

Replace the hand-iterated 5-axis objective with the paper's fitness = Σ over (counter × rival) pairings of `CP × type-effectiveness`, optimised by the GA the paper recommends (50 individuals, 20 generations, 80% crossover, 20% mutation, elitism). Honest tradeoff: the paper's fitness is CP-leaning — mitigated by type-diversity (ADR-034) but it's a faithful implementation, not a best-possible objective.

---

## ADR-033 — Remove the counter modes
**Status:** Accepted (supersedes ADR-023)

**Human-in-the-loop.** Reviewer: *"remove the options for remove legendaries and level cap, it just adds complexity."*

Dropped `CounterMode` from schemas/router/frontend; the stat-cap budget is gone from the GA. The `mode` column is kept for back-compat (written `"freeform"`) to avoid a destructive migration.

---

## ADR-034 — Counter teams: unique + type-diverse ("one of each type")
**Status:** Accepted (softened by ADR-043)

**Human-in-the-loop.** Reviewer: *"leave in the ability to wiggle … when generating multiple counter teams must be unique and have only one of each type."*

GA takes a fresh RNG per `generate` for variety; saved teams feed `exclude` so subsequent generations are guaranteed unique; every GA operator enforces type-diversity. Mitigates ADR-032's CP-dominance (no six similar bruisers).

---

## ADR-035 — Catalog faceted filter (multi-type Any/All + per-stat ranges)
**Status:** Accepted

**Human-in-the-loop.** Reviewer proposed a richer cascading classifier instead of the smaller min-stat addition originally floated.

Client-side bounded faceted filter — multi-select type chips with Any/All toggle (Any=OR, All=dual-type AND, e.g. `[Fire, Flying]`→Charizard), min/max per stat. Pure helper `lib/filter.ts`; ~90% of a query-builder's value at ~30% of the cost. Closes the spec's "filter by stats" gap.

---

## ADR-036 — Change scan widened: discover + whole catalog + new types
**Status:** Accepted (refines ADR-006/009)

**Human-in-the-loop.** Reviewer probe: *"is there an edge case where if a whole new generation of pokémon were added we would miss it?"* → *"do all 3."*

Three passes orchestrated by `scan_all`: `discover_new_pokemon` (catches new generations PokéAPI lists we don't have), `scan_for_changes` widened to the *whole catalog* (was team-members-only — a stat tweak to an unteamed Pokémon was invisible), `detect_new_types` (warns when PokéAPI lists a battle type our chart doesn't have).

---

## ADR-037 — Flatten the backend to 3 folders (`api/` → `business/` → `db/`)
**Status:** Accepted (refines ADR-022/024; deletes `domain/` + `services/`)

**Human-in-the-loop.** Reviewer: *"the project structure is too complicated and has too many layers … The Mon class shouldn't exist."*

Delete `app/domain/` and `app/services/`; merge into `app/business/`. `adapters/` is the ORM↔business translation boundary. The `Mon` solver-shim is gone — the GA operates on business `Pokemon` directly. **DI seam in `deps.py` preserved** — every adapter is still constructed by a `Depends(...)` provider; Postgres / OAuth / Redis-backed sessions / Celery all remain one-line swaps. The rule "business code never imports from `app.db`" is enforced by code review (one grep), with one documented carve-out for the change-scan orchestrator.

---

## ADR-038 — Repos return business objects; ORM renamed `*Row`
**Status:** Accepted (extends ADR-004)

**Human-in-the-loop.** Reviewer: *"the repository pattern is good but you should have them return the business objects. Business objects don't need to know where the data came from."*

ORM classes suffixed `*Row` (`PokemonRow`, `TeamRow`, `UserRow`, …). Each adapter has a private `_to_business(row)` helper and returns business dataclasses only. The wire contract is unchanged because Pydantic's `from_attributes` reads either shape — but business code is now structurally prevented from reaching into ORM rows.

---

## ADR-039 — Required username + password login (argon2id + opaque server-side sessions)
**Status:** Accepted (supersedes ADR-005 + ADR-027)

**Human-in-the-loop.** Reviewer: *"Add a simple username and pw login."*

`UserRow` gets `email`/`password_hash` (later `email`→`username` per ADR-041). New `SessionRow` — the row's PK *is* the cookie token. Argon2id via `argon2-cffi`. `POST /api/auth/{signup,login,logout}` + `GET /api/auth/me`. Wrong-pw and unknown-user return identical 401 detail (no existence oracle). Catalog stays public. The hasher and session store are both behind `deps.py` providers — bcrypt or a Redis-backed store are one-line swaps; OAuth/OIDC slots in behind a different `get_current_user`. (An `is_admin` placeholder column was also added here; removed in ADR-046 as dead weight.)

---

## ADR-040 — Tests split unit/integration; per-test fresh state
**Status:** Accepted (refines ADR-014/031)

**Human-in-the-loop.** Reviewer: *"Tests are 2 categories: unit tests, integration tests where data moves between components. If you don't start the test from a consistent state every time it can cause problems."*

`tests/unit/` (no DB, no HTTP) + `tests/integration/` (real DB + `TestClient` via the `api_client` fixture which drops the schema, lets the lifespan re-seed, drops again on teardown). Markers `unit` + `integration` registered. Twice-in-a-row pytest gives identical output without external `rm test.db`.

---

## ADR-041 — Username (not email) for signup + confirm-password on the form
**Status:** Accepted (refines ADR-039)

**Human-in-the-loop.** Reviewer: *"can we not use email and just use simple username … note that we didn't use email for ease of making multiple users."*

`UserRow.email` → `username` (unique, indexed, case-insensitive via lowercase store). The demo wants multiple throwaway accounts on the spot without owning N inboxes. No email column = nowhere to send a reset link; the confirm-password field on signup (frontend-only typo defense) reduces "a typo bricks the account" risk.

---

## ADR-042 — Apply the type-diversity rule to user teams too
**Status:** Accepted (extends ADR-034)

**Human-in-the-loop.** Reviewer: *"i think we enforce uniqueness on the user generated teams as well note it down in the decisions and note how its unequal and not comparing apples to apples."*

User teams enforce the same type-diversity rule as counter teams via `_validate_members`. Catalog cards show an amber "Type clash" disabled CTA when adding would violate it. Honest caveat: the constraint costs raw firepower against type-concentrated opponents and is more biting on the counter side (which searches the full pool) than on the team side (which usually picks from a small set of favourites), so the comparison is *closer to* apples-to-apples but not perfectly so.

---

## ADR-043 — Soften the rule: "no identical type *sets*" (replaces "no shared types")
**Status:** Accepted (softens ADR-034 + ADR-042)

**Human-in-the-loop.** Reviewer: *"make the typing barrier less strict … dragon flying and dragon ice would be fine."*

New `has_duplicate_type_sets` predicate — Charizard (fire/flying) + Pidgeot (normal/flying) are now allowed on the same team (different sets, shared single type is fine); Bulbasaur + Ivysaur (both grass/poison) is still rejected. Used by the team/counter save validators and the GA's operators. **Autofill deliberately keeps the strict `has_overlapping_types` rule** (its job is "complete my team with type *variety*"); a pinning test prevents a future "consolidate the rule" refactor from flipping it. Matches real competitive teams, grows the search space, mostly retires the V-25 fitness gap.

---

## ADR-044 — Alert dismissal persistence: localStorage, per-user, by timestamp
**Status:** Accepted

**Human-in-the-loop.** Reviewer: *"when the change alerter loads up, even if you close it out its persistent, meaning once you reload the page it stays."*

The dismiss state was `useState(false)` — component-local, lost on remount/reload, so closing the banner did nothing past the next refresh. Fixed client-side via `localStorage.setItem('ptb_alerts_dismissed_until:<userId>', isoTimestamp)`. The banner filters `alerts.filter(a => a.detected_at > dismissedUntil)` so a *new* alert (a fresh `simulate-change` with a later `detected_at`) re-opens the banner naturally, while previously-seen alerts stay hidden. The key is scoped by user id so logging out and signing in as someone else doesn't inherit dismissals (per-user feed → per-user dismiss state). The stored mark is the **max `detected_at`** of the currently-visible alerts, not `Date.now()`, so a server-clock-ahead-of-client edge case can't silently hide a future alert. Chose localStorage over a server-side `dismissed_at` column because (a) the dismissal is per-browser semantics already and (b) the schema cost (a `user_alert_dismissals(user_id, change_event_id, dismissed_at)` table since one event affects many users) wasn't worth it for this size. Documented next step if it ever matters: lift to server-side per-user dismissals.

---

## ADR-045 — Autofill: pure random over the strict-type pool (no BST / dual-type preference)
**Status:** Accepted (reverses the "strongest non-overlapping" framing inherited from ADR-008, for the autofill helper only)

**Human-in-the-loop.** Reviewer: *"the auto team creator seems to choose the same teams or the same types of pokemon frequently … isn't it better to just randomly sort and pick pokemon arbitrarily accounting for type sameness this way you can get variety creating a team isn't about winning its just about getting a diverse team?"*

Autofill was a deterministic greedy argmax over `(num_types, bst)` — always picked dual-types over mono-types, then the highest-BST among them. Same starting team → same six Pokémon every click. The reviewer's point lands: autofill is a *team-builder helper*, not an optimizer — its job is "give me a diverse team to play with," not "find the strongest team." Rewrote it as **shuffle pool with a fresh per-request `random.Random()` → walk → admit first non-clashing candidate → repeat to 6**. Same shape as the GA's `_random_team` initial-population builder, just using the strict type rule (no shared types at all — the ADR-043 carve-out for autofill is preserved) instead of the GA's soft rule. Same RNG-per-request pattern the counter endpoint already uses. Result: real variety across clicks (Bulbasaur and Eternatus are now equally likely), much smaller code, the pinning test (`test_autofill_never_overlaps_types_strict_rule_preserved`) still passes because it asserts on set-equality of the resulting ids — not on the order or strength of picks.

---

## ADR-046 — Drop the `is_admin` placeholder column (no admin role)
**Status:** Accepted (reverses the `is_admin` part of ADR-039)

**Human-in-the-loop.** Reviewer: *"is admin? there is no admin account is there?"* — caught that `is_admin` was a forward-looking column nobody could set to True and no code read to make a decision. The README's "placeholder for a future `Depends` gate" claim was technically true but practically vacuous: the column existed, defaulted to `False` on every user, and the `/admin/*` endpoints (ADR-016) ignored it entirely.

Dropped `is_admin` from `UserRow`, from the business `User` dataclass, from `UserOut`, from `_to_business`, from the frontend `User` type, and the one test assertion that referenced it. README + ADR-039 in-line mentions updated. The `/admin/*` endpoints remain unauthenticated for the demo (still ADR-016); the README now says that honestly instead of suggesting a placeholder gate exists. When a real admin role lands, it should come back as a proper role model (e.g. a `roles` table with many-to-many, or an `is_admin` column with an actual `Depends(require_admin)` gate AND a bootstrap script to elevate a user) — not just a column that's always False with no code path to flip it. **Schema impact:** the `users.is_admin` column will still exist in any existing SQLite file (SQLite + `create_all` doesn't drop columns); it's harmless dead data until a `docker compose down -v` (or `rm pokemon.db*`) recreates the schema.
