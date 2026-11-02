# ADR-0002: Compose model columns from mixins

- **Status:** Accepted
- **Date:** 2026-11-02

## Context

Most tables in Meridian AMS share a few structural columns, but not the same
few, and the needs vary independently of each other:

| Column | Which tables |
|---|---|
| `id` (internal integer PK, used for foreign keys) | all |
| `public_id` (identifier exposed outside the system) | only entities exposed through the API, not join tables |
| `created_at` | all |
| `updated_at` | only tables whose rows are edited, not append-only tables such as audit logs |

An earlier project handled this with a two-class chain: `ImmutableBase`
(`id`, `created_at`) and `MutableBase(ImmutableBase)`, which adds `updated_at`.
It worked, but a chain is linear and these needs are not. Adding `public_id`
forces a choice: put it on every table, or create more base classes (mutable
with and without `public_id`, immutable with and without it, and so on), where
the number of classes doubles with every new optional column.

## Options considered

**A. Two-class chain (`ImmutableBase` -> `MutableBase`).**
Simple and familiar. Weaknesses: it cannot express "has `public_id`" without
more classes, and it combines two unrelated concerns (immutability and
identifier exposure) into one inheritance line.

**B. One base with every column on every table.**
Simplest of all. Weaknesses: join tables carry a `public_id` nobody uses, and
append-only tables carry an `updated_at` that falsely implies rows are edited.

**C. One `Base` plus composable mixins (`IdMixin`, `PublicIdMixin`,
`CreatedAtMixin`, `UpdatedAtMixin`).**
Each model declares exactly the columns it needs. `Base` owns only the
metadata and the constraint naming convention.

## Decision

We use option C.

- `Base` holds a single `MetaData` with a naming convention for indexes,
  unique, check, foreign key and primary key constraints. The convention is
  fixed from the first migration, because changing it later means renaming
  existing constraints.
- Rules of thumb:
  - Every table uses `IdMixin` and `CreatedAtMixin`.
  - Entities exposed through the API add `PublicIdMixin`.
  - Tables whose rows are edited add `UpdatedAtMixin`. Append-only tables do
    not.
- Mixins are listed before `Base`: `class AuditLog(IdMixin, CreatedAtMixin, Base)`.
- Defaults are server-side (`server_default`), so values are the same whether a
  row is inserted through the ORM or by other means. How `public_id` is
  generated is covered in the public ID ADR; how `updated_at` is maintained is
  covered in the `updated_at` ADR. This ADR only decides how the columns are
  composed.
- `UpdatedAtMixin` marks the column as database-maintained
  (`server_onupdate=FetchedValue()`) and sets `eager_defaults=True`, so the new
  value is fetched after an UPDATE instead of left stale or lazily loaded.

Append-only intent is expressed by the absence of `UpdatedAtMixin`. It is a
convention, not enforcement.

## Consequences

**Positive**
- The declaration shows the table's nature at a glance.
- New combinations cost nothing, and future concerns (soft delete, tenant id)
  become one more mixin.
- A single `Base` means a single `MetaData`, which Alembic autogenerate reads.

**Negative / accepted**
- Class declarations have longer base lists, and mixins must be listed before
  `Base` (MRO order).
- Omission is silent. Forgetting `UpdatedAtMixin` yields a valid table without
  `updated_at`. We rely on review and convention.
- The reverse mistake is also silent: a table that uses `UpdatedAtMixin` but
  whose migration lacks the trigger keeps a stale `updated_at`, and
  autogenerate does not detect triggers. The `updated_at` ADR names a test as
  the guard.
- `UpdatedAtMixin` sets `__mapper_args__`. A model that defines its own
  `__mapper_args__` must merge them.

**Honest note:** at the expected size of this project (tens of tables) option A
would also have worked. The choice is for clarity and extensibility at a small
cost.

**Revisit if** mixin combinations become repetitive enough that a few named
composite bases would read better.