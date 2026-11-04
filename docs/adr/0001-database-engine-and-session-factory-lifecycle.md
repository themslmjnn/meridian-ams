# ADR-0001: Database engine and session factory lifecycle

- **Status:** Accepted
- **Date:** 2026-11-04

## Context

The app needs an async SQLAlchemy engine and a session factory. The common
pattern is to create both at module level (`engine = create_async_engine(...)`
in `connection.py`) and import them everywhere.

That pattern has three problems for this project:

1. **Import-time side effects.** Importing `connection.py` reads settings and
   builds the engine, so tests cannot choose configuration before import.
2. **Hidden global state.** Any module can import the engine, so ownership and
   shutdown are unclear.
3. **No clean shutdown.** Nothing is responsible for `engine.dispose()`.

## Decision

- `connection.py` only contains **factory functions**: `build_engine(settings)`
  and `build_session_factory(engine)`. Nothing is created at import time.
- The engine and session factory are created in the FastAPI **lifespan** and
  stored on `app.state` as `engine` and `session_factory`. The lifespan owns
  their whole lifetime. They are attached only after the startup checks pass,
  so a half-started app never exposes them.
- **Fail fast:** startup runs `SELECT 1`. If PostgreSQL is unreachable, the app
  does not start. The database is mandatory, so there is no degraded mode.
- **Guaranteed cleanup:** `engine.dispose()` runs in `finally`, so it also runs
  when the startup check fails. Workers are cancelled before the engine is
  disposed, because they use the session factory.
- **Engine settings.** The pool behaviour depends on the environment:
  - Outside tests (default pool):
    - `pool_pre_ping=True`: detects connections dropped by the server or
      network before they are used.
    - `pool_timeout=DB_POOL_TIMEOUT`: requests fail instead of waiting forever
      when the pool is exhausted.
  - In tests (`ENVIRONMENT == "test"`): `NullPool`. Every connection is opened
    and closed per use, so no pooled connection outlives the event loop it was
    created in. Tests are slower but isolated. `pool_pre_ping` and
    `pool_timeout` are pool options and are not passed here, because with no
    pool they have nothing to act on.
  - All environments: `connect_args={"timeout": DB_CONNECT_TIMEOUT}`. An
    unreachable database fails in bounded time instead of hanging (asyncpg's
    connect timeout, not the pool timeout).
- **Session factory settings:**
  - `expire_on_commit=False`: after `commit()`, objects stay readable. With async
    sessions, an expired attribute triggers an implicit lazy load, which raises
    `MissingGreenlet`.
  - `autoflush=False`: the session never writes to the DB behind our back. Code
    calls `flush()` explicitly when it needs generated values (e.g. an id).
- **One session per request**, provided by the `get_db_session` dependency in
  `core/dependencies.py`. It reads `session_factory` from `request.app.state`
  and yields a session inside `async with`, so the session is always closed.
  - The dependency never commits. The code that knows the operation is complete
    (the service or use case) calls `commit()` explicitly.
  - Closing the session returns its connection to the pool and discards any
    uncommitted transaction. An exception during the request therefore rolls
    everything back.
  - A session borrows a connection on its first statement, not when it is
    created, and releases it when the transaction ends.
- **Settings are resolved once, in `create_app(settings=None)`**, and stored on
  `app.state.settings`. The lifespan reads them from there and never calls
  `get_settings()` itself. Tests pass their own `Settings` to `create_app`
  instead of relying on environment variables being set before import.
- **Typing `app.state`:** `app.state` is untyped, so every read site annotates
  the value it reads, e.g.
  `session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory`.
  The attribute names (`engine`, `session_factory`, `redis`, `settings`) are the
  contract between the lifespan and its readers and must match exactly.

## Options considered

| Option | Why not |
|---|---|
| Module-level engine and session | Problems listed in Context. |
| Cached singleton (`@lru_cache` getter) | Hides the same global state behind a function. Still no owner for `dispose()`, and it is awkward to reset in tests. |
| DI container / `dependency-injector` | New concept and dependency for a single shared resource. |
| Commit automatically in `get_db_session` after the `yield` | Convenient, but hides when writes become permanent. Explicit commits in services keep transaction boundaries visible. |

## Consequences

**Good**
- No import-time side effects. Tests build their own engine with test settings.
- Startup either has a working database or does not complete.
- One place owns create and dispose.
- Tests build an app with explicit settings, so they do not depend on import
  order or on environment variables set beforehand.
- A failed request cannot leave uncommitted data behind: closing the session
  discards it.

**Bad / costs**
- Code cannot `import engine`. It must receive the session factory via
  `request.app.state` (through `get_db_session`) or as an argument.
  Background workers outside a request need the factory passed in explicitly.
- `app.state` is untyped. Annotations at read sites help the type checker
  with the value's type, but a wrong attribute name still fails at runtime
  (`AttributeError`), not at type-check.
- Because the dependency never commits, a service that forgets `commit()` loses
  its writes silently.
- `autoflush=False` means a query after an un-flushed change will not see it.
  This is an easy bug to hit until it becomes a habit.
- `NullPool` in tests does not exercise real pool behaviour. Pool exhaustion,
  `pool_pre_ping` and `pool_timeout` need a separate test with the pool
  enabled, or are accepted as untested.
- The module-level `app = create_app()` still calls `get_settings()` at import
  time. This is accepted for now. If it causes trouble, switch to running
  uvicorn with `--factory`.

## What would change this decision

- If we run multiple workers that need different engines, revisit the single
  `app.state` slot.
- If `app.state` typing becomes painful, wrap it in a small typed container.
- If forgotten commits become a recurring bug, revisit committing in the
  dependency or introducing a unit-of-work wrapper.