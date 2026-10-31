# ADR-0002: Maintain `updated_at` with a PostgreSQL trigger

- **Status:** Accepted
- **Date:** 2026-10-31

## Context

Tables with `UpdatedAtMixin` need an `updated_at` value that is correct after every change. SQLAlchemy's `onupdate=func.now()` is applied by the ORM only when the ORM issues the UPDATE. Raw SQL, data-fix scripts, manual edits in `psql`, and any other service writing to the database bypass it. This system stores student records, and the usual reason to look at `updated_at` is to investigate a suspicious change, which is exactly when such out-of-band writes matter.

## Options considered

**A. ORM-level `onupdate=func.now()`.**
No extra moving parts and works with Alembic autogenerate. Does not cover writes that bypass the ORM.

**B. A `BEFORE UPDATE` trigger on every table with `updated_at`.**
Covers every writer. Needs migration code, a convention, and a guard against forgetting it on a new table.

**C. Both.**
Two sources of truth for the same value. Rejected.

## Decision

We use option B.

- One shared function, `set_updated_at()`, created in the first migration.
- One trigger per table, created by a helper in the migration that creates the table.
- The trigger only fires when the row actually changed (`WHEN (OLD.* IS DISTINCT FROM NEW.*)`), so no-op updates do not bump the timestamp.
- The ORM column uses `server_default=func.now()`, `server_onupdate=FetchedValue()`, and `eager_defaults=True`, so SQLAlchemy fetches the trigger-written value instead of expiring it. This matters in async code, where a lazy reload raises an error.
- A test fails if any table with an `updated_at` column lacks the trigger.

## Consequences

**Positive**
- `updated_at` is correct regardless of who wrote the row.

**Negative / accepted**
- Alembic autogenerate does not detect triggers. They are written by hand in migrations, through a helper.
- Logic lives outside the model. The column carries a comment pointing here.
- The test database must be built with `alembic upgrade head`, not `metadata.create_all()`, or the triggers will be missing.
- The whole-row comparison fails on columns of type `json` (no equality operator). Use `jsonb`.
- `now()` returns the transaction start time, so all rows changed in one transaction share a timestamp.
- Tests need real PostgreSQL. SQLite shortcuts are off the table.

**What this does not provide:** `updated_at` says when, not who or what. Grade, attendance and role changes need a separate audit log. Concurrent edit protection needs a version column, not timestamps.
