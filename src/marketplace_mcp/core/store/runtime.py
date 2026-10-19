"""Open the shared store for one operation and close it afterward."""

import sqlite3
from collections.abc import Callable
from typing import TypeVar

from marketplace_mcp.core.store import connect
from marketplace_mcp.settings import get_server_settings

T = TypeVar("T")


def run_with_store[T](work: Callable[[sqlite3.Connection], T]) -> T:
    """Run one store operation with a connection to the shared database."""
    connection = connect(get_server_settings().store_path)
    try:
        return work(connection)
    finally:
        connection.close()
