# ADR-0003: Maintain `updated_at` with a PostgreSQL trigger

- **Status:** Accepted
- **Date:** 2026-11-04

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
  The trigger is named `trg_<table>_set_updated_at`.
- The trigger only fires when the row actually changed
  (`WHEN (OLD.* IS DISTINCT FROM NEW.*)`), so no-op updates do not bump the
  timestamp.
- The ORM column uses `server_default=func.now()`,
  `server_onupdate=FetchedValue()`, and `eager_defaults=True`, so SQLAlchemy
  fetches the trigger-written value instead of expiring it. This matters in
  async code, where a lazy reload raises an error. `server_onupdate` is only
  a declaration to SQLAlchemy; the trigger is what actually changes the value.
- The column carries a database comment pointing to this ADR
  (`comment="Maintained by a trigger, see ADR-0003"` on `updated_at` in
  `UpdatedAtMixin`), so someone reading the schema in `psql` finds the
  explanation.
- **The helper's output is frozen.** Existing migrations call it, and the test
  suite rebuilds the schema from them. If the trigger ever has to change, add a
  new helper (`..._v2`) for new migrations and leave the old one alone.
- **Two tests guard against forgetting the trigger.** They need no dedicated
  table and run against the migrated test database.
  1. *The guard:* a catalog query lists every table in the `public` schema
     that has an `updated_at` column and no trigger calling
     `set_updated_at()`. The test fails if the list is not empty. The query
     matches on the function (`pg_trigger.tgfoid`), not the trigger name, so
     a renamed or truncated trigger does not cause a false result, and it
     ignores internal triggers (`tgisinternal`).
  2. *The detector check:* inside the test, create a throwaway table with an
     `updated_at` column, assert the query reports it, attach the trigger,
     and assert it is no longer reported. The per-test rollback removes the
     table (PostgreSQL DDL is transactional). Without this test, a broken
     query would pass with an empty result and the guard would protect
     nothing.

## Consequences

**Positive**
- `updated_at` is correct regardless of who wrote the row.

**Negative / accepted**
- Alembic autogenerate does not detect triggers. They are written by hand in
  migrations, through the helper.
- Logic lives outside the model, which is why the column carries a comment.
- The test database must be built with `alembic upgrade head`, not
  `metadata.create_all()`, or the triggers will be missing.
- The whole-row comparison fails on columns of type `json` (no equality
  operator). Use `jsonb`.
- `now()` returns the transaction start time, so all rows changed in one
  transaction share a timestamp, and a row inserted and updated in the same
  transaction has `updated_at` equal to `created_at`.
- Tests need real PostgreSQL. SQLite shortcuts are off the table.
- The guard test sees only tables that exist in the migrated schema. A model
  that has no migration is not checked, and a missing migration is caught
  elsewhere (autogenerate or a schema comparison).
- The guard checks that a trigger calling the function exists, not that it is
  `BEFORE UPDATE` and `FOR EACH ROW`. The helper guarantees that shape, and
  the guard only catches a forgotten trigger.
- The guard reads `information_schema.columns`, which also lists views. A view
  with an `updated_at` column would be reported. There are none today.
- If `set_updated_at` does not exist, the guard fails with an error instead of
  passing. This is intended: it means the migrations did not run.

**What this does not provide:** `updated_at` says when, not who or what. Grade,
attendance and role changes need a separate audit log. Concurrent edit
protection needs a version column, not timestamps.

**Revisit if** the project ever needs a trigger with different behaviour for
some tables (for example `clock_timestamp()` instead of `now()`).