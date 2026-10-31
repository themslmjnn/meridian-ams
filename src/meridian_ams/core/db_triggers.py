from alembic import op


def add_updated_at_trigger(table: str) -> None:
    op.execute(f"""
        CREATE TRIGGER trg_{table}_set_updated_at
        BEFORE UPDATE ON {table}
        FOR EACH ROW
        WHEN (OLD.* IS DISTINCT FROM NEW.*)
        EXECUTE FUNCTION set_updated_at();
    """)


def drop_updated_at_trigger(table: str) -> None:
    op.execute(f"DROP TRIGGER trg_{table}_set_updated_at ON {table};")
