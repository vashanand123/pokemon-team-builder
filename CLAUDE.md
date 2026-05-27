# CLAUDE.md

# Project Engineering Guidelines & Architectural Principles

This document defines the architectural standards, development philosophy, coding conventions, system boundaries, and operational expectations for this project.

The primary goals of this codebase are:

- Simplicity and clarity
- Strong architectural separation
- Ease of local execution
- Maintainability and testability
- Production-aware design without unnecessary infrastructure complexity

This project is intentionally optimized for evaluator experience and low-friction local execution while preserving clean architectural seams that allow production-grade infrastructure to be introduced later with minimal disruption.

Design rationale lives in:
- `PLAN.md` — overall architecture and implementation plan
- `DECISIONS.md` — ADRs and architectural tradeoffs

Major architectural changes should update both documents.

---

# Engineering Philosophy

## Prefer Simplicity Over Cleverness

Favor straightforward, readable solutions over clever abstractions or dense implementations.

Code should optimize for:
- readability,
- maintainability,
- debuggability,
- and ease of onboarding.

If a solution requires extensive explanation, reconsider the design.

---

## Build for Change, Not Premature Complexity

The system should be designed with clear seams for future evolution, but should avoid introducing infrastructure or abstraction layers that are unnecessary for the current use case.

Examples:
- SQLite is used for portability and zero-friction local execution.
- Cookie/session-based authentication is sufficient for this project.
- In-process scheduling is acceptable for current workload requirements.

However, these concerns should remain isolated behind clean boundaries (the DI seam) so they can evolve independently in production.

These are intentional scope decisions, not architectural limitations.

---

## Prefer Boring Technology

Prefer stable, well-understood tools over novelty.

This project values:
- operational simplicity,
- maintainability,
- predictable behavior,
- and low setup friction

over architectural sophistication.

---

## Avoid Over-Engineering

Do not introduce abstractions preemptively.

Abstractions should exist only where:
- multiple implementations are realistic,
- infrastructure concerns should remain isolated,
- testing materially benefits,
- or core business logic must remain framework-agnostic.

Avoid:
- unnecessary indirection,
- generic frameworks,
- deep inheritance hierarchies,
- speculative abstractions,
- and configuration-heavy designs.

---

# System Architecture

## Architectural Style

The backend follows a clean, directional layered architecture (thin API routers →
services / domain → adapters), with **FastAPI dependency injection** as the swap seam.

This is the primary load-bearing architectural concept of the system. A formal
Ports-and-Adapters layer (hand-written `Protocol` interfaces) was considered and
deliberately removed as preemptive abstraction for this scope — see DECISIONS.md
ADR-022 and ADR-024. Swappability comes from the DI composition root (`app/api/deps.py`),
not from declared interfaces.

Core business logic should remain independent from:
- FastAPI,
- SQLAlchemy,
- HTTP clients,
- authentication mechanisms,
- schedulers,
- and infrastructure concerns.

Infrastructure details should live at the edges of the system.

Endpoints should receive infrastructure through FastAPI dependency injection rather than constructing it directly; the domain/service logic stays framework-agnostic and is called by the thin routers.

The database, authentication system, external API clients, and scheduling implementations should remain replaceable with minimal application-layer changes — selected in one place (`app/api/deps.py`).

---

# Architectural Boundaries

## Domain Layer

Responsible for:
- business rules,
- domain entities,
- application workflows,
- validation that represents business invariants,
- deterministic business logic.

The domain layer must:
- remain framework-agnostic,
- contain no FastAPI imports,
- contain no SQLAlchemy imports,
- contain no infrastructure concerns.

Prefer pure Python objects and deterministic logic.

Business logic should remain highly testable in isolation.

---

## API Layer

Responsible for:
- HTTP routing,
- request/response orchestration,
- dependency injection,
- serialization,
- transport concerns,
- authentication boundaries.

FastAPI-specific logic belongs here.

API routes should remain thin.

Routes should:
- validate requests,
- orchestrate dependencies,
- invoke services/use-cases,
- return responses.

Business logic should not live in routes.

---

## Persistence Layer

Responsible for:
- database models,
- query logic,
- transaction management,
- persistence concerns.

Persistence implementations should remain isolated from business workflows.

SQLAlchemy models are persistence models, not domain models.

Do not tightly couple business workflows to ORM behavior.

---

## Adapters

Adapters contain infrastructure implementations such as:
- SQLite repositories,
- external API clients,
- schedulers,
- authentication providers,
- storage implementations.

Adapters are concrete infrastructure implementations, kept at the edges of the system.

Dependency injection (`app/api/deps.py`) wires a chosen adapter to each injection point at application boundaries.

Swapping implementations should require minimal application-layer changes — ideally a one-line change in the DI providers.

---

# Swappable Infrastructure Design

This project intentionally uses lightweight infrastructure choices to simplify evaluation and local execution.

However, all critical infrastructure concerns should remain replaceable.

| Current Implementation | Production Evolution |
|---|---|
| SQLite | PostgreSQL |
| Cookie Sessions | OAuth / OIDC |
| In-process scheduler | Distributed worker system |
| Local persistence | Managed object storage |
| Single container deployment | Orchestrated deployment |
| Simple logging | Structured observability stack |

Core business logic should not require modification when these implementations evolve.

---

# Operational Design Notes

## Local-First Developer Experience

The project should:
- run locally with minimal setup,
- require minimal external dependencies,
- support deterministic startup,
- and remain easy for evaluators to run.

Favor portability and reproducibility over infrastructure sophistication.

---

## Fixture-Backed Data Where Practical

For demo and evaluation workflows, stable fixture-backed data is preferred over unnecessary runtime external dependencies.

External API calls should remain isolated behind adapters, injected via DI.

Runtime application behavior should remain resilient even when external services are unavailable.

---

## Scheduler & Background Work Philosophy

Background jobs should remain isolated from request/response workflows.

Scheduling infrastructure should:
- remain replaceable,
- avoid leaking implementation details into domain logic,
- and degrade gracefully in local environments.

---

## Same-Origin Simplicity

Favor same-origin frontend/backend deployment patterns where practical to reduce:
- CORS complexity,
- cookie/session issues,
- local setup friction,
- and operational overhead.

---

# Dependency Injection

Use FastAPI dependency injection as the seam between application code and infrastructure.

Routes depend on an injected dependency (via `Depends`), not on infrastructure they construct
themselves. The provider in `app/api/deps.py` is the single place that selects the concrete
implementation, so a swap is localized there. (No hand-written `Protocol` interfaces — see the
Architectural Style section and ADR-022/024 for why.)

Example:
- A route receives a repository via `Depends(get_pokemon_repo)`
- `get_pokemon_repo` returns `SqlPokemonRepository`; swapping to Postgres = return a different
  class from that one provider

Swapping implementations should require minimal changes. Tests substitute fakes / an in-memory DB
via FastAPI dependency overrides (duck-typed — no interface required).

---



Keep boundaries clean and directional.

Lower-level infrastructure should never leak into domain logic.

---

# Backend Technology Standards

## Core Stack

- Python 3.13
- FastAPI (async)
- SQLAlchemy 2.x async
- aiosqlite
- Pydantic v2
- pydantic-settings
- httpx
- tenacity
- APScheduler
- uvicorn

---

# Frontend Technology Standards

## Core Stack

- React 19
- TypeScript
- Vite 8
- TanStack Query v5
- Tailwind CSS v4
- dnd-kit
- native fetch

Do not introduce Axios unless explicitly required.

---

# Package Management

This project standardizes on `uv` for deterministic dependency management and reproducible onboarding.

## Commands

Install packages:
```bash
uv add <package>
```

Install development dependencies:
```bash
uv add --dev <package>
```

Run tooling:
```bash
uv run <tool>
```

Examples:
```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

Avoid:
- pip
- requirements.txt workflows
- unpinned environments
- ad hoc dependency installation

---

# Python Code Standards

## General Principles

Code should prioritize:
- readability,
- explicitness,
- maintainability,
- and testability.

Prefer simple implementations over dense abstractions.

---

## Type Hints

Type hints are required for:
- public functions,
- methods,
- dependency providers (`app/api/deps.py`),
- and core business logic.

Avoid `Any` unless unavoidable.

---

## Naming Conventions

Use:
- `snake_case` for variables/functions
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants

Choose descriptive names.

Favor clarity over brevity.

---

## Functions

Functions should:
- do one thing well,
- remain focused,
- remain reasonably small,
- use early returns when appropriate,
- avoid excessive nesting.

Break apart complex workflows into composable units.

---

## Docstrings

Public APIs and important business workflows should include docstrings explaining:
- intent,
- important behavior,
- constraints,
- architectural rationale,
- or important tradeoffs.

Do not write redundant docstrings that merely restate the function name.

---

## Formatting

Use:
- Ruff for linting and formatting
- maximum line length of 88 characters

---

# API Design Principles

## Validation Boundaries

Use Pydantic at system boundaries:
- API requests,
- API responses,
- configuration parsing.

Avoid leaking Pydantic models deep into core business logic where unnecessary.

---

## Error Handling

Error handling should:
- be explicit,
- produce meaningful API responses,
- avoid leaking internal implementation details,
- and log actionable debugging context.

Avoid broad silent exception handling.

---

# Database Design Principles

## Schema Design

Schemas should prioritize:
- clarity,
- normalization where appropriate,
- explicit relationships,
- and maintainability.

Avoid premature optimization.

---

## Persistence Separation

Persistence concerns should remain isolated from business workflows.

Database-specific optimizations should remain localized to the persistence layer.

---

# Async Guidelines

Use async only where it provides meaningful value:
- database access,
- external HTTP calls,
- concurrent I/O workflows.

Avoid unnecessary async complexity in pure computation paths.

---

# Testing Standards

## Core Principles

Tests should prioritize:
- confidence,
- readability,
- determinism,
- maintainability,
- and isolation.

---

## Required Testing

Every:
- new feature requires tests,
- bug fix requires regression coverage.

Test:
- happy paths,
- edge cases,
- validation failures,
- error handling,
- API boundaries.

---

## Testing Stack

Backend:
- pytest
- pytest-asyncio

Frontend:
- Playwright

---

## Testing Philosophy

Prefer:
- focused unit tests,
- isolated service tests,
- lightweight integration tests.

Mock infrastructure at system boundaries where practical.

Examples:
- mock repositories,
- mock external API clients,
- in-memory test implementations.

Tests should:
- avoid unnecessary external dependencies,
- remain hermetic where practical,
- and avoid shared mutable state between runs.

---

# Frontend Standards

## State Management

Use TanStack Query for:
- server state,
- caching,
- mutations,
- synchronization.

Avoid unnecessary global client state.

---

## Components

Keep components:
- focused,
- composable,
- readable,
- and reusable.

Avoid massive “god components.”

---

## Styling

Use Tailwind CSS.

Prefer:
- composable UI patterns,
- reusable structures,
- semantic component organization.

Avoid excessively long inline utility chains when abstraction improves readability.

---

# Performance Philosophy

Prioritize correctness and readability first.

Optimize performance:
- only after identifying a real bottleneck,
- or when working in known high-throughput paths.

Do not introduce complexity for speculative optimization.

---

# Logging & Observability

Logs should be:
- structured,
- useful,
- concise,
- and actionable.

Avoid noisy logging.

Log meaningful system events and failures.

---

# Docker & Runtime Expectations

The application should:
- run locally with minimal setup,
- support deterministic startup,
- work consistently across environments.

Favor reproducibility and simplicity.

---

# Operational Awareness

Document important operational caveats and environment assumptions when they materially impact system behavior.

Examples:
- SQLite concurrency considerations
- scheduler/runtime interactions
- local environment assumptions
- fixture loading behavior
- testing isolation requirements

Prefer documenting important architectural constraints rather than relying on tribal knowledge.

---

# Git & Commit Standards

Commit messages should:
- be concise,
- descriptive,
- and explain intent.

Prefer small, logically isolated commits.

For user-reported fixes/features:
```bash
git commit --trailer "Reported-by:<name>"
```

For GitHub issue linkage:
```bash
git commit --trailer "Github-Issue:#<number>"
```

Do not include:
- AI references,
- co-authored-by metadata,
- generated-by metadata.

---

# Decision Documentation

Major architectural or technical decisions should be documented as ADRs.

Document:
- rationale,
- tradeoffs,
- alternatives considered,
- operational implications,
- and future evolution paths where relevant.

Keep decisions intentional and explainable.

---

# Final Principle

This project should feel:
- clean,
- intentional,
- easy to understand,
- easy to run,
- and easy to evolve.

Every architectural decision should balance:
- practicality,
- maintainability,
- evaluator experience,
- operational simplicity,
- and long-term extensibility.