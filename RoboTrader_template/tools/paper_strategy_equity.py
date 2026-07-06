"""전략별 일별 equity 트래커 — virtual_trading_records 리플레이 + mark-to-market.

배경(2026-06-10): paper_trading_state.eod_balance 는 '현금만' 저장(보유포지션
평가액 미포함)이라 전략 비교/자산곡선용으로 부적합. 이 스크립트가 체결기록을
전략별로 리플레이해 일별 equity(현금+보유평가액)를 paper_strategy_equity 에
UPSERT 한다(멱등·백필 가능). 수수료 모델은 봇(virtual_trading_manager)과 동일:
  BUY:  cash -= qty*price*(1+COMMISSION_RATE)
  SELL: cash += qty*price*(1-COMMISSION_RATE-SECURITIES_TAX_RATE)
주의: records 의 price 는 체결가 기준이라 봇 실장부와 ±0.02% 내 드리프트 가능
(체결>예약 추가차감 등). 랭킹/곡선 용도로 충분, 원장 SSOT 는 여전히 봇.

에포크: 2026-06-01(첫 kis_template 레코드일). 라이브 봇은 get_strategy_trade_sums
로 **날짜필터 없이 전체 레코드**를 합산해 현금을 재구성하므로, 정확히 일치시키려면
에포크 이후 전 레코드를 포함해야 한다(1천만 배분 자체는 06-08이나, 그 이전 06-01
체결도 라이브 현금식에 반영됨). --epoch 로 더 늦은 부분뷰 산출은 가능.

사용:
  python tools/paper_strategy_equity.py                # 에포크~오늘 백필+저장
  python tools/paper_strategy_equity.py --no-write     # 콘솔 리더보드만
  # 콘솔 한글 깨짐 방지: PYTHONIOENCODING=utf-8 python -X utf8 tools/paper_strategy_equity.py
"""
import os
import sys
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE  # noqa: E402

DEFAULT_EPOCH = date(2026, 6, 1)
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

    현금 모델은 라이브 봇(virtual_trading_manager.restore_strategy_ledger_from_records)
    과 바이트 동일하다 — 현금은 '전체 매수/매도 gross 의 순수 함수':
        cash = initial - Σbuy_gross*(1+commission) + Σsell_gross*(1-commission-tax)
    즉 매도는 추적 포지션 유무·수량과 무관하게 **전량(qty) 현금 반영**한다(라이브가
    get_strategy_trade_sums 로 전체 SELL gross 를 무조건 더하는 것과 동일). 포지션
    추적(qty/avg_cost)은 보유평가(MTM)·n_open·realized fallback 용도로만 쓰며,
    over-sell(보유보다 많이 매도) 시 포지션 qty 는 0 으로 clamp 한다(현금은 이미 전량
    반영했으므로 이중반영 없음). 과거(구버전)의 min(qty,보유) clamp 는 현금을 과소
    계상해 음수현금·라이브 불일치를 유발했다(2026-06-22 수정).

    records: [{trade_date, action, stock_code, quantity, price, profit_loss?}] (단일 전략분)
    dates: EOD 달력(오름차순). 달력 밖 날짜의 레코드는 무시(호출측이 전체 달력 제공 책임).
    closes: {(stock_code, date): close} — 없으면 직전 종가, 그것도 없으면 평단 fallback.
    realized_pnl_cum: 레코드에 profit_loss 가 있으면 그 합(봇 실현손익=권위), 없으면
        avg_cost 기반 gross 차익으로 fallback.
    """
    date_set = set(dates)
    by_date: Dict[date, List[dict]] = defaultdict(list)
    for r in records:
        if r["trade_date"] in date_set:
            by_date[r["trade_date"]].append(r)

    cash = float(initial_capital)
    # net 인벤토리(부호 허용) — 보유 = Σ매수qty - Σ매도qty 의 종목별 net.
    # over-sell 은 net 을 음수로 두고 이후 매수로 상계 → 유령 포지션 방지(=라이브의
    # 실보유 종목수와 일치). 평가/n_open 은 net>0 인 것만 집계.
    inv: Dict[str, dict] = {}  # code -> {net, avg_cost}
    last_close: Dict[str, float] = {}
    realized_cum = 0.0
    rows: List[dict] = []

    for d in sorted(dates):
        for r in by_date.get(d, []):
            code = r["stock_code"]
            qty = int(r["quantity"])
            price = float(r["price"])
            pos = inv.get(code)
            if r["action"] == "BUY":
                cash -= qty * price * (1.0 + commission_rate)
                if pos is None or pos["net"] <= 0:
                    # 신규 양(+) 인벤토리 시작(음수 overhang 상계 포함) — 원가 재설정
                    inv[code] = {"net": (pos["net"] if pos else 0) + qty, "avg_cost": price}
                else:
                    total = pos["net"] + qty
                    pos["avg_cost"] = (pos["avg_cost"] * pos["net"] + price * qty) / total
                    pos["net"] = total
            elif r["action"] == "SELL":
                # 라이브와 동일: 전량 무조건 현금 반영(포지션 추적과 분리)
                cash += qty * price * (1.0 - commission_rate - tax_rate)
                matched = min(qty, pos["net"]) if (pos and pos["net"] > 0) else 0
                pl = r.get("profit_loss")
                if pl is not None:
                    realized_cum += float(pl)
                elif pos is not None and matched:
                    realized_cum += (price - pos["avg_cost"]) * matched
                if pos is None:
                    inv[code] = {"net": -qty, "avg_cost": price}
                else:
                    pos["net"] -= qty

        position_value = 0.0
        n_open = 0
        for code, pos in inv.items():
            if pos["net"] <= 0:
                continue
            n_open += 1
            px = closes.get((code, d))
            if px is not None:
                last_close[code] = px
            else:
                px = last_close.get(code, pos["avg_cost"])
            position_value += pos["net"] * px

        rows.append({
            "trade_date": d,
            "cash": cash,
            "position_value": position_value,
            "equity": cash + position_value,
            "realized_pnl_cum": realized_cum,
            "n_open": n_open,
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
        password=os.getenv("TIMESCALE_PASSWORD", "1234"),
    )


def _load_records(conn, epoch: date) -> Dict[str, List[dict]]:
    """에포크 이후 kis_template 레코드를 전략별로 로드."""
    sql = (
        "SELECT timestamp::date, action, stock_code, quantity, price, strategy, profit_loss "
        "FROM virtual_trading_records "
        "WHERE source=%s AND timestamp::date >= %s AND strategy IS NOT NULL "
        "ORDER BY timestamp"
    )
    out: Dict[str, List[dict]] = defaultdict(list)
    with conn.cursor() as cur:
        cur.execute(sql, (SOURCE, epoch))
        for d, action, code, qty, price, strategy, profit_loss in cur.fetchall():
            out[strategy].append({
                "trade_date": d, "action": action, "stock_code": str(code),
                "quantity": int(qty), "price": float(price),
                "profit_loss": float(profit_loss) if profit_loss is not None else None,
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


class _KisTemplateDailyReader:
    """kis_template.daily_prices 읽기 전용 리더 (보유평가 1순위 소스).

    QuantDailyReader.get_daily_prices 와 동일 인터페이스/스키마(date text 'YYYY-MM-DD',
    close)를 kis_template DB(KisDbConnection)에 대해 제공한다. 봇이 EOD step6
    (collectors.eod_collection.run_data_collection)에서 당일 공식종가를 이 DB로 직접
    수집하므로, 외부 quant ETL 타이밍과 무관하게 당일(T) 종가를 신뢰성 있게 갖는다
    (2026-06-25 stale-equity 버그 수정의 핵심 — A안 자족적 평가소스).
    """

    def get_daily_prices(self, stock_code: str, end_date=None, days: int = 120):
        import pandas as pd
        from db.kis_db_connection import KisDbConnection

        end = None
        if end_date is not None:
            end = end_date if isinstance(end_date, str) else end_date.strftime("%Y-%m-%d")
        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as cur:
                if end:
                    cur.execute(
                        "SELECT date, close FROM daily_prices "
                        "WHERE stock_code = %s AND date <= %s ORDER BY date DESC LIMIT %s",
                        (stock_code, end, int(days)),
                    )
                else:
                    cur.execute(
                        "SELECT date, close FROM daily_prices "
                        "WHERE stock_code = %s ORDER BY date DESC LIMIT %s",
                        (stock_code, int(days)),
                    )
                rows = cur.fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["date", "close"])
        df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
        df = df.dropna(subset=["date"])
        return df.sort_values("date").reset_index(drop=True)


def _default_close_readers():
    """보유평가 종가 소스(우선순위 순). 1순위=kis_template(봇 자체 수집, 당일종가 신뢰),
    2순위=robotrader_quant(과거 폴백). 1순위가 (code,date)를 주면 그 값이 권위."""
    from db.quant_daily_reader import QuantDailyReader
    return [_KisTemplateDailyReader(), QuantDailyReader()]


def _load_closes(codes: List[str], dates: List[date],
                 readers: Optional[List] = None) -> Dict[Tuple[str, date], float]:
    """종목별 종가 로드 (보유평가용). readers 우선순위로 병합 — 먼저 채워진
    (code, date) 가 권위(1순위 미존재시에만 2순위로 폴백)."""
    closes: Dict[Tuple[str, date], float] = {}
    if not dates:
        return closes
    if readers is None:
        readers = _default_close_readers()
    span = max(30, (max(dates) - min(dates)).days + 10)
    for code in codes:
        for reader in readers:
            try:
                df = reader.get_daily_prices(code, end_date=max(dates), days=span)
            except Exception:
                continue
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                d = row["date"].date() if hasattr(row["date"], "date") else row["date"]
                key = (str(code), d)
                # 1순위가 이미 채운 키는 덮어쓰지 않음(우선순위 보존)
                if key not in closes:
                    closes[key] = float(row["close"])
    return closes


def _ensure_table(conn):
    from scripts.kis_db.schema import PAPER_STRATEGY_EQUITY_DDL
    with conn.cursor() as cur:
        cur.execute(PAPER_STRATEGY_EQUITY_DDL)
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


def run_daily_equity_snapshot(conn, epoch: Optional[date] = None,
                              capital: float = DEFAULT_CAPITAL) -> dict:
    """봇 EOD 훅용: 전략별 일별 equity 를 계산해 paper_strategy_equity 에 UPSERT.

    CLI(main) 와 달리 print 없이 결과 요약 dict 를 반환한다(로깅은 호출측 책임).
    conn 은 호출측이 생성·관리(예: db.connection.DatabaseConnection.get_connection()).
    멱등(전 구간 UPSERT)이라 매일·재시작 시 반복 호출해도 안전하다.

    Returns: {ok, trade_date, n_strategies, total_cash, eod_balance, cash_match} —
        cash_match 가 False 면 라이브 SSOT(paper_trading_state)와 현금 불일치(조사필요).
    """
    epoch = epoch or DEFAULT_EPOCH
    per_strategy = _load_records(conn, epoch)
    dates = _load_calendar(conn, epoch)
    if not dates:
        return {"ok": False, "reason": "no_calendar"}
    all_codes = sorted({r["stock_code"] for recs in per_strategy.values() for r in recs})
    closes = _load_closes(all_codes, dates)
    _ensure_table(conn)

    last_d = dates[-1]
    total_cash = 0.0
    n = 0
    for strategy, recs in sorted(per_strategy.items()):
        rows = replay_strategy_equity(recs, capital, dates, closes)
        _upsert_rows(conn, strategy, rows)
        total_cash += rows[-1]["cash"]
        n += 1

    with conn.cursor() as cur:
        cur.execute(
            "SELECT eod_balance FROM paper_trading_state WHERE trade_date=%s", (last_d,))
        row = cur.fetchone()
    eod = float(row[0]) if row else None
    cash_match = eod is not None and abs(total_cash - eod) < 1.0
    return {
        "ok": True, "trade_date": last_d, "n_strategies": n,
        "total_cash": total_cash, "eod_balance": eod, "cash_match": cash_match,
    }


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
        # 교차검증: 리플레이 현금합 vs paper_trading_state.eod_balance(현금 SSOT).
        # 현금식이 라이브 restore_strategy_ledger_from_records 와 동일하므로 ~0 이어야 정상.
        # (거래 없는 전략은 cash=capital 그대로라 total_cash 에 이미 포함됨)
        with conn.cursor() as cur:
            cur.execute("SELECT eod_balance FROM paper_trading_state WHERE trade_date=%s", (last_d,))
            row = cur.fetchone()
        if row:
            eod = float(row[0])
            diff = total_cash - eod
            flag = "✅ 일치" if abs(diff) < 1.0 else f"⚠️ 불일치 {diff:+,.0f}"
            print(f"\n[교차검증] 리플레이 현금합 {total_cash:,.0f} "
                  f"vs paper_trading_state {eod:,.0f} → {flag}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
