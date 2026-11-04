from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TABLES_MISSING_TRIGGER = text("""
    SELECT c.table_name
    FROM information_schema.columns AS c
    WHERE c.table_schema = 'public'
      AND c.column_name = 'updated_at'
      AND NOT EXISTS (
          SELECT 1
          FROM pg_trigger AS t
          WHERE t.tgrelid = format('%I.%I', c.table_schema, c.table_name)::regclass
            AND t.tgfoid = 'public.set_updated_at'::regproc
            AND NOT t.tgisinternal
      )
    ORDER BY c.table_name
""")


async def test_every_updated_at_table_has_the_trigger(
    db_test_session: AsyncSession,
) -> None:
    result = await db_test_session.execute(TABLES_MISSING_TRIGGER)

    assert result.scalars().all() == []


async def test_guard_query_detects_a_missing_trigger(
    db_test_session: AsyncSession,
) -> None:
    await db_test_session.execute(
        text("CREATE TABLE guard_probe (id int, updated_at timestamptz)")
    )

    before = await db_test_session.execute(TABLES_MISSING_TRIGGER)

    assert "guard_probe" in before.scalars().all()

    await db_test_session.execute(
        text("""
            CREATE TRIGGER trg_guard_probe_set_updated_at
            BEFORE UPDATE ON guard_probe
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """)
    )

    after = await db_test_session.execute(TABLES_MISSING_TRIGGER)

    assert "guard_probe" not in after.scalars().all()
