from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from server import lakebase

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "bootstrap"))
setup_lakebase = importlib.import_module("setup_lakebase")


def test_lakebase_requires_explicit_database_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGHOST", "pg.example.com")
    monkeypatch.setenv("PGUSER", "app_user")
    monkeypatch.delenv("PGDATABASE", raising=False)

    with pytest.raises(RuntimeError, match="PGDATABASE is required when Lakebase is configured"):
        lakebase.lakebase_configured()

    monkeypatch.setenv("PGDATABASE", "   ")
    with pytest.raises(RuntimeError, match="PGDATABASE is required when Lakebase is configured"):
        lakebase.lakebase_configured()

    monkeypatch.setattr(lakebase._token_cache, "get", lambda: pytest.fail("credential was minted"))
    monkeypatch.setattr(lakebase.psycopg, "connect", lambda **_kwargs: pytest.fail("connection was attempted"))
    with pytest.raises(RuntimeError, match="PGDATABASE is required when Lakebase is configured"):
        lakebase._connect()


def test_lakebase_connect_uses_bound_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGHOST", "pg.example.com")
    monkeypatch.setenv("PGUSER", "app_user")
    monkeypatch.setenv("PGDATABASE", "existing_quote_db")
    monkeypatch.setattr(lakebase._token_cache, "get", lambda: "test-token")
    connect = Mock(return_value=object())
    monkeypatch.setattr(lakebase.psycopg, "connect", connect)

    assert lakebase.lakebase_configured()
    lakebase._connect()

    assert connect.call_args.kwargs["dbname"] == "existing_quote_db"


def test_setup_requires_explicit_database_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["setup_lakebase.py", "--instance", "db-instance"])

    with pytest.raises(SystemExit) as error:
        setup_lakebase.parse_args()

    assert error.value.code == 2


def test_setup_quotes_database_identifier(monkeypatch: pytest.MonkeyPatch) -> None:
    database = 'quote"db; DROP DATABASE other;--'
    monkeypatch.setattr(
        sys,
        "argv",
        ["setup_lakebase.py", "--instance", "db-instance", "--database", database],
    )
    workspace = Mock()
    workspace.database.get_database_instance.return_value.read_write_dns = "pg.example.com"
    workspace.current_user.me.return_value.user_name = "tester@example.com"
    workspace.database.generate_database_credential.return_value.token = "test-token"
    monkeypatch.setattr(setup_lakebase, "WorkspaceClient", lambda: workspace)

    connection = MagicMock()
    cursor = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.return_value = None
    monkeypatch.setattr(setup_lakebase.psycopg, "connect", Mock(return_value=connection))

    setup_lakebase.main()

    cursor.execute.assert_any_call("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
    create_query = cursor.execute.call_args_list[-1].args[0]
    assert create_query.as_string() == 'CREATE DATABASE "quote""db; DROP DATABASE other;--"'
