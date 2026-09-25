"""DuckDB connections to the catalog.

Connections are short-lived on purpose: DuckDB lets only one process hold the file
for writing, so the API server and a pipeline script can both work as long as
neither keeps a connection open between operations.
"""
from contextlib import contextmanager
from typing import Iterator

import duckdb

from core.config import settings


@contextmanager
def connect(read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    con = duckdb.connect(str(settings.catalog_path), read_only=read_only)
    try:
        con.execute("LOAD spatial")
        yield con
    finally:
        con.close()


def install_extensions() -> None:
    """One-time download of the spatial extension into DuckDB's local extension cache."""
    con = duckdb.connect(str(settings.catalog_path))
    try:
        con.execute("INSTALL spatial")
    finally:
        con.close()
