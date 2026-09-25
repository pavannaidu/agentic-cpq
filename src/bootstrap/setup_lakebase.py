"""One-time setup: create an explicitly named Postgres database inside a Lakebase instance.

Schema creation and product seeding intentionally live in the app's startup
(src/app/server/lakebase.py, run as the app's service principal) so the SP owns
the tables and has full access. This script only ensures the database exists.

Run locally against a configured workspace:

    DATABRICKS_CONFIG_PROFILE=DEFAULT python src/bootstrap/setup_lakebase.py \
        --instance YOUR_INSTANCE --database YOUR_DATABASE

The database name must match the app's configured PGDATABASE.
"""

from __future__ import annotations

import argparse
import sys
import uuid

import psycopg
from psycopg import sql
from databricks.sdk import WorkspaceClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Postgres database inside a Lakebase instance.")
    parser.add_argument("--instance", required=True, help="Lakebase database instance name.")
    parser.add_argument("--database", required=True, help="Postgres database to create.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    workspace = WorkspaceClient()

    instance = workspace.database.get_database_instance(name=args.instance)
    host = instance.read_write_dns
    me = workspace.current_user.me().user_name
    token = workspace.database.generate_database_credential(
        request_id=str(uuid.uuid4()), instance_names=[args.instance]
    ).token

    print(f"Connecting to {host} as {me} (database=databricks_postgres)…")
    with psycopg.connect(
        host=host,
        port=5432,
        dbname="databricks_postgres",
        user=me,
        password=token,
        sslmode="require",
        autocommit=True,
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (args.database,))
        if cur.fetchone():
            print(f"Database '{args.database}' already exists — nothing to do.")
        else:
            # CREATE DATABASE cannot run inside a transaction; autocommit handles that.
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(args.database)))
            print(f"Created database '{args.database}'.")

    print("Done. The app will create tables + seed products on startup.")


if __name__ == "__main__":
    sys.exit(main())
