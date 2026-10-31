# ADR-0001: Compose model columns from mixins

- **Status:** Accepted
- **Date:** 2026-10-31

## Context

Most tables in Meridian AMS share a few structural columns, but not the same few:

| Column | Which tables |
|---|---|
| `id` (internal integer PK, used for foreign keys) | all |
| `public_id` (identifier exposed outside the system) | only entities exposed through the API, not join tables |
| `created_at` | all |
| `updated_at` | only tables whose rows are edited, not append-only tables such as audit logs |

An earlier project handled this with a two-class chain: `ImmutableBase` (`id`, `created_at`) and `MutableBase(ImmutableBase)`, which adds `updated_at`. It worked, but the chain is linear while the needs vary independently. Adding `public_id` to the chain forces a choice: put it on every table, or create more base classes (mutable with and without `public_id`, immutable with and without it, and so on).

## Options considered

**A. Two-class chain (`ImmutableBase` -> `MutableBase`).**
Simple and familiar, with two names to learn. Weaknesses: it cannot express "has `public_id`" without more classes, and `MutableBase` is-a `ImmutableBase`, so `isinstance` checks and the names point the wrong way.

**B. One base with every column on every table.**
Simplest of all. Weaknesses: join tables carry a `public_id` nobody uses, and append-only tables carry an `updated_at` that falsely implies rows are edited.

**C. One `Base` plus composable mixins (`IdMixin`, `PublicIdMixin`, `CreatedAtMixin`, `UpdatedAtMixin`).**
Each model declares exactly the columns it needs. `Base` owns only the metadata and naming convention.

## Decision

We use option C.

Rules of thumb:
- Every table uses `IdMixin` and `CreatedAtMixin`.
- Entities exposed through the API add `PublicIdMixin`.
- Tables whose rows are edited add `UpdatedAtMixin`. Append-only tables do not.

Append-only intent is expressed by the absence of `UpdatedAtMixin`. It is a convention, not enforcement.

## Consequences

**Positive**
- The declaration shows the table's nature: `class AuditLog(IdMixin, CreatedAtMixin, Base)`.
- New combinations cost nothing, and future concerns (soft delete, tenant id) become one more mixin.
- A single `Base` means a single `MetaData`, which Alembic autogenerate reads.

**Negative / accepted**
- Class declarations have longer base lists, and mixins must be listed before `Base` (MRO order).
- Omission is silent. Forgetting `UpdatedAtMixin` yields a valid table without `updated_at`. We rely on review and convention.
- `UpdatedAtMixin` sets `__mapper_args__` (`eager_defaults`). A model that defines its own `__mapper_args__` must merge them.

**Honest note:** at the expected size of this project (tens of tables) option A would also have worked. The choice is for clarity and extensibility at a small cost.

**Revisit if** mixin combinations become repetitive enough that a few named composite bases would read better.
