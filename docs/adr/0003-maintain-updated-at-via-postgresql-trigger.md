# ADR-0003: Maintain `updated_at` with a PostgreSQL trigger

- **Status:** Accepted
- **Date:** 2026-11-02

## Context

Tables with `UpdatedAtMixin` need an `updated_at` value that is correct after
every change. SQLAlchemy's `onupdate=func.now()` is applied by the ORM only
when the ORM issues the UPDATE. Raw SQL, data-fix scripts, manual edits in
`psql`, and any other service writing to the database bypass it. This system
stores student records, and the usual reason to look at `updated_at` is to
investigate a suspicious change, which is exactly when such out-of-band writes
matter.

## Options considered

**A. ORM-level `onupdate=func.now()`.**
No extra moving parts and works with Alembic autogenerate. Does not cover
writes that bypass the ORM.

**B. A `BEFORE UPDATE` trigger on every table with `updated_at`.**
Covers every writer. Needs migration code, a convention, and a guard against
forgetting it on a new table.

**C. Both.**
Two sources of truth for the same value. Rejected.

## Decision

We use option B.

- One shared function, `set_updated_at()`, created in the first migration.
- One trigger per table, created in the migration that creates the table, by
  `add_updated_at_trigger(table)` from `meridian_ams/database/triggers.py`.
- The trigger only fires when the row actually changed
  (`WHEN (OLD.* IS DISTINCT FROM NEW.*)`), so no-op updates do not bump the
  timestamp.
- The ORM column uses `server_default=func.now()`,
  `server_onupdate=FetchedValue()`, and `eager_defaults=True`, so SQLAlchemy
  fetches the trigger-written value instead of expiring it. This matters in
  async code, where a lazy reload raises an error.
- **The helper's output is frozen.** Existing migrations call it, and the test
  suite rebuilds the schema from them. If the trigger ever has to change, add a
  new helper (`..._v2`) for new migrations and leave the old one alone.
- **A test guards against forgetting.** It lists every table with an
  `updated_at` column that has no trigger calling `set_updated_at()`, and fails
  if the list is not empty. It matches on the function, not the trigger name,
  so a renamed or truncated trigger does not cause a false result.

## Consequences

**Positive**
- `updated_at` is correct regardless of who wrote the row.

**Negative / accepted**
- Alembic autogenerate does not detect triggers. They are written by hand in
  migrations, through the helper.
- Logic lives outside the model. The column carries a comment pointing here.
- The test database must be built with `alembic upgrade head`, not
  `metadata.create_all()`, or the triggers will be missing.
- The whole-row comparison fails on columns of type `json` (no equality
  operator). Use `jsonb`.
- `now()` returns the transaction start time, so all rows changed in one
  transaction share a timestamp.
- Tests need real PostgreSQL. SQLite shortcuts are off the table.
- The guard test sees only tables that exist in the migrated schema. A model
  that has no migration is not checked, and a missing migration is caught
  elsewhere (autogenerate or a schema comparison).

**What this does not provide:** `updated_at` says when, not who or what. Grade,
attendance and role changes need a separate audit log. Concurrent edit
protection needs a version column, not timestamps.

**Revisit if** the project ever needs a trigger with different behaviour for
some tables (for example `clock_timestamp()` instead of `now()`).