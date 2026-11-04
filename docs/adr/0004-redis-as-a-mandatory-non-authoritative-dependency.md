# ADR-0004: Redis as a mandatory, non-authoritative dependency

- **Status:** Accepted
- **Date:** 2026-11-04

## Context

Some work in this system is better done in memory than in PostgreSQL: counting
requests for rate limiting, checking on every authenticated request whether an
access token is still valid, and caching values that are read often.

Three questions need an answer before any code depends on Redis:

1. What is it used for, and what is it never used for?
2. Is the application allowed to run without it?
3. When Redis fails while the application is running, does each use fail open
   (continue without it) or fail closed (refuse the request)?

## Options considered

**A. Redis is mandatory, and never the source of truth.**
One mode of operation. Everything stored in Redis can be rebuilt from
PostgreSQL, or is acceptable to lose.

**B. Redis is optional, with an in-memory fallback.**
The app starts without Redis. Rejected: per-process counters are wrong as soon
as there is more than one process, and every Redis feature would need a second
implementation that also has to be tested.

**C. No Redis, PostgreSQL only.**
Rate limiting and token checks stored in tables. One less service to run.
Costs an extra database read on every authenticated request and a write on
every rate-limited one.

## Decision

We use option A.

**What Redis is used for**
- Rate limiting counters.
- Access-token version checks: the token carries a version, Redis holds the
  current one per session, and a mismatch means the token was revoked. When the
  key is absent, the check falls back to PostgreSQL and repopulates it.
- Read caches for hot values (for example the unread notification count).
- Read cache for idempotency records, if PostgreSQL stays the authoritative
  store for them (decided in the idempotency ADR).

**What it is never used for**
- Anything that must survive a Redis restart. We do not rely on Redis
  persistence.
- Any value that has no copy or derivation in PostgreSQL, except rate-limit
  counters, whose loss only resets the limits.

**Mandatory at startup.** The lifespan builds the client and calls `ping()`.
If Redis is unreachable, startup fails. `/health/ready` checks Redis next to
PostgreSQL.

**Failure behaviour at runtime** depends on the use:

| Use | On Redis error | Why |
|---|---|---|
| Cache reads and writes | Fail open: log a warning, treat as a miss | A miss costs a database query, not correctness |
| Ordinary cache invalidation | Fail open: log a warning | A stale entry disappears when its TTL expires |
| Invalidation of security-relevant keys | Fail closed: 503 | A key that fails to clear could leave a revoked state looking valid |
| Rate limiting | Fail closed: 503 | Failing open silently disables brute-force protection |
| Token version check | Fail closed: 503 | Failing open could accept a revoked token |

This is implemented as two wrapper categories in `core/redis/wrappers.py`:
optional wrappers (`get_cache`, `set_cache`, `delete_cache`) catch `RedisError`
and degrade to a miss or a no-op; critical wrappers (including
`delete_cache_critical`) let it propagate to the global handler, which returns
503. Code chooses a category by what a silent failure would mean for that use.
The two delete functions are separate on purpose, so the failure behaviour is
visible at every call site instead of hidden behind a flag.

**Failing fast.** Fail-open only works if the failure arrives quickly, so the
client sets a 2-second connect timeout and a 2-second read timeout
(`core/redis/client.py`). Without them, an unreachable Redis would hang
requests instead of degrading them.

**Client and keys**
- One async client (`redis.asyncio`) is created in the lifespan, stored on
  `app.state`, and closed on shutdown. The client manages its own connection
  pool and connects lazily, so the startup `ping()` is what verifies it.
- Development uses database 0 and tests use database 1.
- Values are stored as JSON. A value that JSON cannot serialize is a
  programming error and raises to the caller; it is not swallowed as a Redis
  failure. `None` is never cached, so a stored value always means a real
  value and a missing key always means a miss.
- Every key is written with an expiry, because nothing in Redis is meant to
  live forever. `ttl` is a required argument of `set_cache`; callers pass
  `DEFAULT_CACHE_TTL_SECONDS` from `Settings`, which defaults to 300 seconds
  and is validated to stay between 120 and 3600.

## Consequences

**Positive**
- One mode of operation, with no degraded variants to design or test.
- The security-relevant uses cannot silently stop working.
- Losing Redis loses nothing that cannot be rebuilt.

**Negative / accepted**
- A Redis outage makes authenticated endpoints return 503, even though
  PostgreSQL (the source of truth for token versions) is available. We accept
  this to keep the failure rule simple.
- One more service to run in development and in any deployment.
- Restarting Redis resets rate-limit counters and empties caches. Token
  versions are rebuilt from PostgreSQL on the next check.
- Tests need a real Redis. `flushdb()` runs only after the environment guard
  confirms the test database number.
- The cached value and the database can disagree for the length of a TTL. When
  an ordinary invalidation fails open, the worst case is one TTL, at most one
  hour with the configured upper bound.

**Honest note:** at the expected size of this project, option C would also
have worked. Redis is used because per-request checks and rate limiting are
the textbook cases for it, and learning to run it correctly is part of the
project's purpose.

**Revisit if**
- Redis outages become a real operational problem: let the token check fall
  back to PostgreSQL when Redis is down, which is the one safe place to fail
  over.
- A second instance is deployed: confirm all limits and counters still work as
  intended across instances.