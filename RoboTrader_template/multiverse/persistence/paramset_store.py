"""ParamSet → composable_paramset 테이블 영속성."""
from __future__ import annotations

import logging
from typing import Optional

from psycopg2.extras import Json

from RoboTrader_template.db.connection import DatabaseConnection
from RoboTrader_template.multiverse.composable.paramset import ParamSet

logger = logging.getLogger(__name__)

CODE_VERSION = "multiverse-1.0.0"


def save_paramset(paramset: ParamSet, code_version: str = CODE_VERSION) -> str:
    """paramset_id 반환. 이미 존재하면 무시(멱등).

    SQL: INSERT INTO composable_paramset (paramset_id, json_blob, config_hash, code_version)
         VALUES (%s, %s, %s, %s) ON CONFLICT (paramset_id) DO NOTHING
    """
    paramset.validate()
    paramset_id = paramset.paramset_id()
    config_hash = paramset.config_hash()
    json_blob = paramset.to_dict()

    with DatabaseConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO composable_paramset
                   (paramset_id, json_blob, config_hash, code_version)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (paramset_id) DO NOTHING""",
                (paramset_id, Json(json_blob), config_hash, code_version),
            )
    return paramset_id


def load_paramset(paramset_id: str) -> Optional[ParamSet]:
    """없으면 None.

    config_hash 검증: DB의 config_hash와 ParamSet.from_dict 후 재계산이 다르면
    경고 로그 + 그대로 반환.
    """
    with DatabaseConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT json_blob, config_hash, code_version
                   FROM composable_paramset WHERE paramset_id = %s""",
                (paramset_id,),
            )
            row = cur.fetchone()

    if row is None:
        return None

    json_blob, db_config_hash, db_code_version = row
    paramset = ParamSet.from_dict(json_blob)
    current_hash = paramset.config_hash()
    if current_hash != db_config_hash:
        logger.warning(
            "config_hash 불일치 — paramset_id=%s, DB=%s, 재계산=%s. "
            "ParamSet 스키마 변경 가능성. 보수적 청산 모드 진입 권장.",
            paramset_id,
            db_config_hash,
            current_hash,
        )
    return paramset


def exists_paramset(paramset_id: str) -> bool:
    """paramset_id 존재 여부 확인."""
    with DatabaseConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM composable_paramset WHERE paramset_id = %s",
                (paramset_id,),
            )
            return cur.fetchone() is not None


def all_paramset_ids() -> list:
    """저장된 모든 paramset_id 반환 (created_at 오름차순)."""
    with DatabaseConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT paramset_id FROM composable_paramset ORDER BY created_at"
            )
            return [r[0] for r in cur.fetchall()]


def delete_paramset(paramset_id: str) -> bool:
    """관리/테스트 cleanup용. composable_position이 FK 잡고 있으면 ON DELETE RESTRICT로 raise."""
    with DatabaseConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM composable_paramset WHERE paramset_id = %s",
                (paramset_id,),
            )
            deleted = cur.rowcount > 0
    return deleted
