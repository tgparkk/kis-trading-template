"""부록 C DDL 출력 · 쓰기 역할 연결(§4 · Q10).

    python -m backtest.concept_axes.candidate_ledger.llm_shadow.ddl        # ddl.sql 을 그대로 출력(비밀번호 없음)

쓰기 연결 = `db/connection.py` 기본값(host·port·db env 그대로) + user `llm_shadow_writer`
+ 비밀번호 `config/key.ini [LLM_SHADOW] db_password`(라이브 트리 · 읽기만 · 출력 금지).
"""
from __future__ import annotations

import configparser
import os
import sys
from pathlib import Path

from . import settings as S

DDL_PATH = Path(__file__).with_name("ddl.sql")
WRITER_ROLE = "llm_shadow_writer"


def ddl_text() -> str:
    return DDL_PATH.read_text(encoding="utf-8")


def writer_password() -> str:
    cp = configparser.ConfigParser()
    cp.read(S.key_ini_path(), encoding="utf-8")
    pw = cp.get("LLM_SHADOW", "db_password", fallback="")
    if not pw:
        raise RuntimeError("config/key.ini [LLM_SHADOW] db_password 없음 — 먼저 추가할 것")
    return pw


def writer_dsn() -> dict:
    return dict(host=os.getenv("TIMESCALE_HOST", "localhost"), port=int(os.getenv("TIMESCALE_PORT", "5433")),
                dbname=os.getenv("TIMESCALE_DB", "kis_template"), user=WRITER_ROLE, password=writer_password())


def connect_writer():
    import psycopg2
    return psycopg2.connect(**writer_dsn())


if __name__ == "__main__":
    sys.stdout.write(ddl_text())
