"""The store opens new files and preserves data from its v1 schema."""

import sqlite3
from pathlib import Path

from marketplace_mcp.core.store import connect


def test_empty_database_has_current_schema_and_reopens(tmp_path: Path) -> None:
    path = tmp_path / "store.db"
    first = connect(path)
    tables = {row[0] for row in first.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"items", "orders", "parcels", "order_items", "sync_runs", "price_observations"} <= tables
    assert "marketplace" in {row[1] for row in first.execute("PRAGMA table_info(orders)")}
    assert first.execute("PRAGMA user_version").fetchone()[0] == 2
    first.close()

    second = connect(path)
    assert second.execute("PRAGMA user_version").fetchone()[0] == 2
    second.close()


def test_v1_rows_migrate_as_ozon_and_keep_values(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE items (sku TEXT PRIMARY KEY, title TEXT, image TEXT, url TEXT, seller TEXT, "
        "first_seen TEXT NOT NULL, last_seen TEXT NOT NULL)"
    )
    old.execute("INSERT INTO items VALUES ('123', 'Tea', NULL, 'https://example.test', NULL, 'a', 'b')")
    old.execute("PRAGMA user_version = 1")
    old.commit()
    old.close()

    connection = connect(path)
    row = connection.execute("SELECT marketplace, sku, title, first_seen, last_seen FROM items").fetchone()
    assert tuple(row) == ("ozon", "123", "Tea", "a", "b")
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    connection.close()

    reopened = connect(path)
    assert reopened.execute("SELECT count(*) FROM items").fetchone()[0] == 1
    reopened.close()
