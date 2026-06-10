"""전략별 일별 equity 트래커 — virtual_trading_records 리플레이 + mark-to-market.

배경(2026-06-10): paper_trading_state.eod_balance 는 '현금만' 저장(보유포지션
평가액 미포함)이라 전략 비교/자산곡선용으로 부적합. 이 스크립트가 체결기록을
전략별로 리플레이해 일별 equity(현금+보유평가액)를 paper_strategy_equity 에
UPSERT 한다(멱등·백필 가능). 수수료 모델은 봇(virtual_trading_manager)과 동일:
  BUY:  cash -= qty*price*(1+COMMISSION_RATE)
  SELL: cash += qty*price*(1-COMMISSION_RATE-SECURITIES_TAX_RATE)
주의: records 의 price 는 체결가 기준이라 봇 실장부와 ±0.02% 내 드리프트 가능
(체결>예약 추가차감 등). 랭킹/곡선 용도로 충분, 원장 SSOT 는 여전히 봇.

에포크: 2026-06-08(7전략 x 1천만 배분 시점). 이전 레코드는 무시.

사용:
  python scripts/paper_strategy_equity.py                # 에포크~오늘 백필+저장
  python scripts/paper_strategy_equity.py --no-write     # 콘솔 리더보드만
"""
import os
import sys
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE  # noqa: E402

DEFAULT_EPOCH = date(2026, 6, 8)
DEFAULT_CAPITAL = 10_000_000
SOURCE = "kis_template"


def replay_strategy_equity(
    records: List[dict],
    initial_capital: float,
    dates: List[date],
    closes: Dict[Tuple[str, date], float],
    commission_rate: float = COMMISSION_RATE,
    tax_rate: float = SECURITIES_TAX_RATE,
) -> List[dict]:
    """단일 전략 레코드를 dates 달력으로 리플레이해 일별 equity 행을 반환.

    records: [{trade_date, action, stock_code, quantity, price}] (단일 전략분)
    dates: 에포크 이후 EOD 달력(오름차순). 달력 밖 날짜의 레코드는 무시.
    closes: {(stock_code, date): close} — 없으면 직전 종가, 그것도 없으면 평단 fallback.
    """
    date_set = set(dates)
    by_date: Dict[date, List[dict]] = defaultdict(list)
    for r in records:
        if r["trade_date"] in date_set:
            by_date[r["trade_date"]].append(r)

    cash = float(initial_capital)
    positions: Dict[str, dict] = {}  # code -> {qty, avg_cost}
    last_close: Dict[str, float] = {}
    realized_cum = 0.0
    rows: List[dict] = []

    for d in sorted(dates):
        for r in by_date.get(d, []):
            code = r["stock_code"]
            qty = int(r["quantity"])
            price = float(r["price"])
            if r["action"] == "BUY":
                cash -= qty * price * (1.0 + commission_rate)
                pos = positions.get(code)
                if pos:
                    total_qty = pos["qty"] + qty
                    pos["avg_cost"] = (pos["avg_cost"] * pos["qty"] + price * qty) / total_qty
                    pos["qty"] = total_qty
                else:
                    positions[code] = {"qty": qty, "avg_cost": price}
            elif r["action"] == "SELL":
                pos = positions.get(code)
                if pos is None:
                    # 에포크 이전 매수분 등 고아 SELL — 현금/실현손익 미반영(보수적 스킵)
                    continue
                sell_qty = min(qty, pos["qty"])
                cash += sell_qty * price * (1.0 - commission_rate - tax_rate)
                realized_cum += (price - pos["avg_cost"]) * sell_qty
                pos["qty"] -= sell_qty
                if pos["qty"] <= 0:
                    positions.pop(code)

        position_value = 0.0
        for code, pos in positions.items():
            px = closes.get((code, d))
            if px is not None:
                last_close[code] = px
            else:
                px = last_close.get(code, pos["avg_cost"])
            position_value += pos["qty"] * px

        rows.append({
            "trade_date": d,
            "cash": cash,
            "position_value": position_value,
            "equity": cash + position_value,
            "realized_pnl_cum": realized_cum,
            "n_open": len(positions),
        })
    return rows


# ── DB 연동 (CLI 전용) ─────────────────────────────────────────────────────

def _db_conn():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("TIMESCALE_HOST", "localhost"),
        port=int(os.getenv("TIMESCALE_PORT", 5433)),
        database=os.getenv("TIMESCALE_DB", "robotrader"),
        user=os.getenv("TIMESCALE_USER", "robotrader"),
        password=os.getenv("TIMESCALE_PASSWORD", "robotrader_secure_pw_2024"),
    )


def _load_records(conn, epoch: date) -> Dict[str, List[dict]]:
    """에포크 이후 kis_template 레코드를 전략별로 로드."""
    sql = (
        "SELECT timestamp::date, action, stock_code, quantity, price, strategy "
        "FROM virtual_trading_records "
        "WHERE source=%s AND timestamp::date >= %s AND strategy IS NOT NULL "
        "ORDER BY timestamp"
    )
    out: Dict[str, List[dict]] = defaultdict(list)
    with conn.cursor() as cur:
        cur.execute(sql, (SOURCE, epoch))
        for d, action, code, qty, price, strategy in cur.fetchall():
            out[strategy].append({
                "trade_date": d, "action": action, "stock_code": str(code),
                "quantity": int(qty), "price": float(price),
            })
    return out


def _load_calendar(conn, epoch: date) -> List[date]:
    """EOD 달력 = paper_trading_state 저장일(>=epoch) ∪ 레코드 존재일 ∪ 오늘(거래일이면)."""
    days = set()
    with conn.cursor() as cur:
        cur.execute("SELECT trade_date FROM paper_trading_state WHERE trade_date >= %s", (epoch,))
        days.update(r[0] for r in cur.fetchall())
        cur.execute(
            "SELECT DISTINCT timestamp::date FROM virtual_trading_records "
            "WHERE source=%s AND timestamp::date >= %s", (SOURCE, epoch))
        days.update(r[0] for r in cur.fetchall())
    return sorted(days)


def _load_closes(codes: List[str], dates: List[date]) -> Dict[Tuple[str, date], float]:
    """quant 일봉에서 종목별 종가 로드 (보유평가용)."""
    from db.quant_daily_reader import QuantDailyReader
    reader = QuantDailyReader()
    closes: Dict[Tuple[str, date], float] = {}
    if not dates:
        return closes
    span = max(30, (max(dates) - min(dates)).days + 10)
    for code in codes:
        try:
            df = reader.get_daily_prices(code, end_date=max(dates), days=span)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            d = row["date"].date() if hasattr(row["date"], "date") else row["date"]
            closes[(str(code), d)] = float(row["close"])
    return closes


def _ensure_table(conn):
    ddl = """
    CREATE TABLE IF NOT EXISTS paper_strategy_equity (
        trade_date date NOT NULL,
        strategy varchar(50) NOT NULL,
        source varchar(50) NOT NULL DEFAULT 'kis_template',
        cash numeric(15,2) NOT NULL,
        position_value numeric(15,2) NOT NULL,
        equity numeric(15,2) NOT NULL,
        realized_pnl_cum numeric(15,2) NOT NULL,
        n_open integer NOT NULL,
        updated_at timestamptz DEFAULT now(),
        PRIMARY KEY (trade_date, strategy, source)
    )
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def _upsert_rows(conn, strategy: str, rows: List[dict]):
    sql = (
        "INSERT INTO paper_strategy_equity "
        "(trade_date, strategy, source, cash, position_value, equity, realized_pnl_cum, n_open, updated_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now()) "
        "ON CONFLICT (trade_date, strategy, source) DO UPDATE SET "
        "cash=EXCLUDED.cash, position_value=EXCLUDED.position_value, equity=EXCLUDED.equity, "
        "realized_pnl_cum=EXCLUDED.realized_pnl_cum, n_open=EXCLUDED.n_open, updated_at=now()"
    )
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(sql, (
                r["trade_date"], strategy, SOURCE,
                round(r["cash"], 2), round(r["position_value"], 2), round(r["equity"], 2),
                round(r["realized_pnl_cum"], 2), r["n_open"],
            ))
    conn.commit()


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="전략별 일별 equity 백필/저장")
    parser.add_argument("--epoch", default=DEFAULT_EPOCH.isoformat())
    parser.add_argument("--capital", type=float, default=DEFAULT_CAPITAL)
    parser.add_argument("--no-write", action="store_true", help="DB 저장 없이 출력만")
    args = parser.parse_args(argv)
    epoch = date.fromisoformat(args.epoch)

    conn = _db_conn()
    try:
        per_strategy = _load_records(conn, epoch)
        dates = _load_calendar(conn, epoch)
        if not dates:
            print("달력 없음 — 종료")
            return 0
        all_codes = sorted({r["stock_code"] for recs in per_strategy.values() for r in recs})
        closes = _load_closes(all_codes, dates)
        print(f"에포크 {epoch} | 달력 {len(dates)}일 | 전략 {len(per_strategy)}개 | "
              f"종가 {len(closes)}건/{len(all_codes)}종목")

        if not args.no_write:
            _ensure_table(conn)

        results = {}
        for strategy, recs in sorted(per_strategy.items()):
            rows = replay_strategy_equity(recs, args.capital, dates, closes)
            results[strategy] = rows
            if not args.no_write:
                _upsert_rows(conn, strategy, rows)

        # 리더보드 (마지막 날 기준)
        last_d = dates[-1]
        print(f"\n== 전략별 equity 리더보드 ({last_d}) — 초기자본 {args.capital:,.0f} ==")
        board = sorted(results.items(), key=lambda kv: -kv[1][-1]["equity"])
        total_cash = total_eq = 0.0
        for strategy, rows in board:
            r = rows[-1]
            ret = (r["equity"] / args.capital - 1) * 100
            total_cash += r["cash"]
            total_eq += r["equity"]
            print(f"{strategy:30s} equity {r['equity']:>13,.0f} ({ret:+.2f}%) | "
                  f"cash {r['cash']:>13,.0f} | 보유 {r['n_open']}종목 평가 {r['position_value']:>11,.0f} | "
                  f"실현누적 {r['realized_pnl_cum']:>+10,.0f}")
        # 교차검증: 거래 없는 전략 자본 포함 합계 vs paper_trading_state
        with conn.cursor() as cur:
            cur.execute("SELECT eod_balance FROM paper_trading_state WHERE trade_date=%s", (last_d,))
            row = cur.fetchone()
        if row:
            n_idle_guess = 7 - len(results)
            est_total_cash = total_cash + n_idle_guess * args.capital
            print(f"\n[교차검증] 리플레이 현금합(거래전략) {total_cash:,.0f} "
                  f"+ 무거래 {n_idle_guess}전략x{args.capital:,.0f} = {est_total_cash:,.0f} "
                  f"vs paper_trading_state {float(row[0]):,.0f} "
                  f"(차이 {est_total_cash - float(row[0]):+,.0f})")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
