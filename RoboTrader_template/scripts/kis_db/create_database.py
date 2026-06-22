"""kis_template DB 생성(멱등). postgres 관리DB에 autocommit 연결해 CREATE DATABASE.

usage: python -m scripts.kis_db.create_database
"""
import os
import sys

import psycopg2
from psycopg2 import sql

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402


def database_exists(conn, dbname: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        return cur.fetchone() is not None


def create_database_if_absent() -> bool:
    cfg = KisDbConnection.get_config()
    dbname = cfg["database"]
    admin = dict(cfg, database="postgres")
    conn = psycopg2.connect(**admin)
    try:
        conn.autocommit = True
        if database_exists(conn, dbname):
            print(f"DB 이미 존재: {dbname}")
            return False
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
        print(f"DB 생성 완료: {dbname}")
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    create_database_if_absent()
