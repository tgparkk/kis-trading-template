"""composable_position 테이블 영속성 — 라이브 포지션 메모리 round-trip."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from psycopg2.extras import Json

from RoboTrader_template.db.connection import DatabaseConnection

logger = logging.getLogger(__name__)


@dataclass
class StoredPosition:
    """composable_position 한 행을 표현."""

    symbol: str
    paramset_id: str
    entry_price: float
    atr_at_entry: Optional[float]
    lock_step: int
    held_days: int
    entry_signal_json: Optional[dict]
    pending_scale_qty: float
    last_updated: datetime


def save_position(
    symbol: str,
    paramset_id: str,
    entry_price: float,
    atr_at_entry: Optional[float] = None,
    lock_step: int = 0,
    held_days: int = 0,
    entry_signal: Optional[dict] = None,
    pending_scale_qty: float = 0.0,
) -> None:
    """UPSERT — 같은 (symbol, paramset_id) 있으면 갱신."""
    with DatabaseConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO composable_position
                   (symbol, paramset_id, entry_price, atr_at_entry,
                    lock_step, held_days, entry_signal_json, pending_scale_qty,
                    last_updated)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                   ON CONFLICT (symbol, paramset_id) DO UPDATE SET
                       entry_price       = EXCLUDED.entry_price,
                       atr_at_entry      = EXCLUDED.atr_at_entry,
                       lock_step         = EXCLUDED.lock_step,
                       held_days         = EXCLUDED.held_days,
                       entry_signal_json = EXCLUDED.entry_signal_json,
                       pending_scale_qty = EXCLUDED.pending_scale_qty,
                       last_updated      = NOW()""",
                (
                    symbol,
                    paramset_id,
                    entry_price,
                    atr_at_entry,
                    lock_step,
                    held_days,
                    Json(entry_signal) if entry_signal is not None else None,
                    pending_scale_qty,
                ),
            )


def load_all() -> list:
    """모든 보유 포지션 반환. 라이브 봇 재시작 시 호출."""
    with DatabaseConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT symbol, paramset_id, entry_price, atr_at_entry,
                          lock_step, held_days, entry_signal_json,
                          pending_scale_qty, last_updated
                   FROM composable_position
                   ORDER BY paramset_id, symbol"""
            )
            rows = cur.fetchall()

    return [_row_to_stored(row) for row in rows]


def load_by_symbol(symbol: str) -> list:
    """특정 종목의 모든 paramset 포지션."""
    with DatabaseConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT symbol, paramset_id, entry_price, atr_at_entry,
                          lock_step, held_days, entry_signal_json,
                          pending_scale_qty, last_updated
                   FROM composable_position
                   WHERE symbol = %s
                   ORDER BY paramset_id""",
                (symbol,),
            )
            rows = cur.fetchall()

    return [_row_to_stored(row) for row in rows]


def update_held_days(symbol: str, paramset_id: str, held_days: int) -> None:
    """매일 +1 갱신. last_updated도 함께."""
    with DatabaseConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE composable_position
                   SET held_days = %s, last_updated = NOW()
                   WHERE symbol = %s AND paramset_id = %s""",
                (held_days, symbol, paramset_id),
            )


def update_lock_step(symbol: str, paramset_id: str, lock_step: int) -> None:
    """락인 단계 진행."""
    with DatabaseConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE composable_position
                   SET lock_step = %s, last_updated = NOW()
                   WHERE symbol = %s AND paramset_id = %s""",
                (lock_step, symbol, paramset_id),
            )


def update_pending_scale_qty(
    symbol: str, paramset_id: str, pending_qty: float
) -> None:
    """분할매수 잔여 수량 갱신."""
    with DatabaseConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE composable_position
                   SET pending_scale_qty = %s, last_updated = NOW()
                   WHERE symbol = %s AND paramset_id = %s""",
                (pending_qty, symbol, paramset_id),
            )


def delete_position(symbol: str, paramset_id: str) -> bool:
    """청산 시 호출."""
    with DatabaseConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM composable_position
                   WHERE symbol = %s AND paramset_id = %s""",
                (symbol, paramset_id),
            )
            return cur.rowcount > 0


def _row_to_stored(row: tuple) -> StoredPosition:
    """DB row → StoredPosition 변환."""
    (
        symbol,
        paramset_id,
        entry_price,
        atr_at_entry,
        lock_step,
        held_days,
        entry_signal_json,
        pending_scale_qty,
        last_updated,
    ) = row
    return StoredPosition(
        symbol=symbol,
        paramset_id=paramset_id,
        entry_price=float(entry_price),
        atr_at_entry=float(atr_at_entry) if atr_at_entry is not None else None,
        lock_step=int(lock_step),
        held_days=int(held_days),
        entry_signal_json=entry_signal_json,
        pending_scale_qty=float(pending_scale_qty),
        last_updated=last_updated,
    )
