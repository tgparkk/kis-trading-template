"""오늘자(단일일자) 진입 시뮬 — 8 라이브 전략.

목적: 봇이 특정 거래일 D 에 '매수'했을 종목/체결가/수량을 사후 재현한다.

원리(라이브 on_tick 충실):
  - 매수 신호는 D-1 확정 일봉까지만 본다(on_tick 이 당일 미확정봉 drop).
    → 후보·진입신호 모두 scan_date=D-1 기준.
  - D 분봉으로 진입 지정가밴드[entry_min, entry_max] 충족 시점의 체결가를 결정.
  - 사이징: yaml paper_investment_per_stock(미설정=100만), 자본 1천만/전략,
    max_positions 와 자본한도 중 작은 값으로 매수 종목수 제한(score 내림차순).

미모델(주의): 시장방향/regime/서킷브레이커/VI 가드(ctx.buy 내장), 쿨다운,
  실시간 호가 슬리피지. → 실제 라이브보다 체결이 관대할 수 있음(상한 추정).

usage:
  python -m scripts.discovery.entry_sim_day --date 2026-06-19
  python -m scripts.discovery.entry_sim_day --date 2026-06-19 --prev 2026-06-18
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import psycopg2

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from runners._adapter_factory import build_adapter
from strategies.base import SignalType
from strategies.config import StrategyLoader
from scripts.discovery.live_strategy_signals import _backtest_market_context
from db.quant_daily_reader import QuantDailyReader

STRATEGIES = [
    "elder_ema_pullback", "minervini_volume_dryup", "deep_mr_dev20",
    "daytrading_3methods_breakout", "rs_leader", "book_envelope_200d",
    "book_pullback_ma20", "book_pullback_ma5",
]

CAPITAL_PER_STRATEGY = 10_000_000
PG = dict(host="127.0.0.1", port=5433, dbname="robotrader", user="postgres", password="")


def _load_cfg(folder: str) -> Tuple[float, int]:
    """(per_stock_amount, max_positions) — config.yaml 직접 파싱."""
    import yaml
    cfg = yaml.safe_load((ROOT / "strategies" / folder / "config.yaml").read_text(encoding="utf-8"))
    risk = (cfg or {}).get("risk_management", {}) or {}
    amount = float(risk.get("paper_investment_per_stock", 1_000_000))
    mp = risk.get("max_positions") or (cfg or {}).get("max_positions") or 10
    return amount, int(mp)


def _minute_bars(conn, code: str, d8: str) -> pd.DataFrame:
    q = ("SELECT time, open, high, low, close FROM minute_candles "
         "WHERE stock_code=%s AND trade_date=%s ORDER BY time")
    df = pd.read_sql(q, conn, params=[code, d8])
    return df


def _daily_bar(qr, code: str, d: date) -> Optional[pd.DataFrame]:
    """분봉 없는 종목용 fallback — quant 일봉 D 의 OHLC 1행(time='일봉')."""
    df = qr.get_daily_prices(code, end_date=d, days=3)
    if df is None or df.empty:
        return None
    last = df.iloc[-1]
    return pd.DataFrame([{"time": "일봉", "open": float(last["open"]), "high": float(last["high"]),
                          "low": float(last["low"]), "close": float(last["close"])}])


def _simulate_fill(bars: pd.DataFrame, emin: Optional[float], emax: Optional[float]
                   ) -> Tuple[Optional[str], Optional[float]]:
    """D 분봉을 시간순으로 보며 밴드[emin,emax]에 처음 닿는 체결가를 반환."""
    lo_b = emin if emin is not None else float("-inf")
    hi_b = emax if emax is not None else float("inf")
    for _, b in bars.iterrows():
        lo, hi, o = float(b.low), float(b.high), float(b.open)
        if hi >= lo_b and lo <= hi_b:  # 밴드와 봉 범위 교차
            if lo_b <= o <= hi_b:
                return str(b.time), o
            if o > hi_b:                # 위에서 밴드로 하락 진입(눌림) → 밴드 상단 체결
                return str(b.time), hi_b
            return str(b.time), lo_b    # 아래에서 밴드로 상승 진입(돌파) → 밴드 하단 체결
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="시뮬 대상 거래일 YYYY-MM-DD (매수 발생일)")
    ap.add_argument("--prev", default=None, help="직전 거래일 YYYY-MM-DD (신호 기준일, 기본=자동 직전영업일 추정)")
    ap.add_argument("--max-candidates", type=int, default=10)
    args = ap.parse_args()

    d = datetime.strptime(args.date, "%Y-%m-%d").date()
    d8 = d.strftime("%Y%m%d")
    qr = QuantDailyReader()
    if args.prev:
        d1 = datetime.strptime(args.prev, "%Y-%m-%d").date()
    else:
        # quant daily 에서 d 직전 거래일 자동 추정
        d1 = qr.prev_trading_day(d) if hasattr(qr, "prev_trading_day") else None
        if d1 is None:
            print("[오류] --prev (직전 거래일) 를 지정하세요.", file=sys.stderr)
            return 2

    conn = psycopg2.connect(**PG)

    print("=" * 96)
    print(f"오늘자 진입 시뮬  매수발생일 D={d}  신호기준일 D-1={d1}  자본 {CAPITAL_PER_STRATEGY:,}원/전략")
    print("=" * 96)

    grand_cost = 0.0
    grand_n = 0
    grand_mtm = 0.0

    for folder in STRATEGIES:
        amount, max_pos = _load_cfg(folder)
        cap_by_money = int(CAPITAL_PER_STRATEGY // amount)
        buyable = min(max_pos, cap_by_money)

        adapter = build_adapter(folder)
        if adapter is None:
            print(f"\n[{folder}] 어댑터 로드 실패"); continue
        params = adapter.default_params()
        if "max_candidates" in params:
            params = {**params, "max_candidates": args.max_candidates}
        candidates = adapter.scan(d1, params)[:args.max_candidates]

        strat = StrategyLoader.load_strategy(folder)
        strat.on_init(None, None, None)

        rows = []
        with _backtest_market_context():
            for c in candidates:
                df = qr.get_daily_prices(c.code, end_date=d1, days=260)
                if df is None or len(df) < 10:
                    continue
                try:
                    sig = strat.generate_signal(c.code, df, "daily")
                except Exception:
                    sig = None
                if sig is None or sig.signal_type not in (SignalType.BUY, SignalType.STRONG_BUY):
                    continue
                emin, emax = sig.entry_min_price, sig.entry_max_price
                bars = _minute_bars(conn, c.code, d8)
                src = "분봉"
                if bars.empty:
                    bars = _daily_bar(qr, c.code, d)
                    src = "일봉"
                    if bars is None:
                        rows.append((c.code, c.score, emin, emax, None, None, "D데이터없음", src, None))
                        continue
                day_close = float(bars["close"].iloc[-1])
                t, fill = _simulate_fill(bars, emin, emax)
                if fill is None:
                    rows.append((c.code, c.score, emin, emax, None, None, "밴드미충족", src, day_close))
                else:
                    rows.append((c.code, c.score, emin, emax, t, fill, "FILL", src, day_close))

        # score 내림차순, FILL 우선 정렬 후 buyable 만큼 실매수
        # (1주도 못 사는 고가주는 자금부족으로 제외)
        rows.sort(key=lambda r: (r[6] != "FILL", -r[1]))
        affordable = [r for r in rows if r[6] == "FILL" and r[5] and int(amount // r[5]) >= 1]
        bought = affordable[:buyable]
        bought_codes = {r[0] for r in bought}

        n_fill = sum(1 for r in rows if r[6] == "FILL")
        print(f"\n[{folder}]  종목당 {amount:,.0f}원 · max_pos={max_pos} · 매수가능 {buyable}종목 "
              f"· 신호 {len(rows)} · 체결가능 {n_fill}  [swing→당일청산 없음, 6/19종가 평가손익]")
        if not rows:
            print("   (진입신호 0건)")
        strat_cost = 0.0
        strat_mtm = 0.0
        for code, score, emin, emax, t, fill, status, src, dclose in rows:
            band = f"[{emin:,.0f}~{emax:,.0f}]" if (emin and emax) else \
                   (f"[~{emax:,.0f}]" if emax else (f"[{emin:,.0f}~]" if emin else "[무제한]"))
            if status == "FILL" and code in bought_codes:
                sh = int(amount // fill)
                cost = sh * fill
                mtm = (dclose - fill) * sh if dclose else 0.0
                pct = (dclose / fill - 1.0) * 100.0 if (dclose and fill) else 0.0
                grand_cost += cost; grand_n += 1; grand_mtm += mtm
                strat_cost += cost; strat_mtm += mtm
                print(f"   ✅ 매수 {code}  체결 {fill:,.0f}({t},{src})  {sh}주  종가 {dclose:,.0f}  "
                      f"평가손익 {mtm:+,.0f}원({pct:+.1f}%)")
            elif status == "FILL" and fill and int(amount // fill) < 1:
                print(f"   ✗ 자금부족 {code}  체결가 {fill:,.0f}({src}) > 예산 {amount:,.0f}  밴드{band}")
            elif status == "FILL":
                print(f"   ⏸  한도초과 {code}  체결가 {fill:,.0f}({src})  밴드{band} (score낮아 제외)")
            else:
                print(f"   ✗ 미체결 {code}  {status}  밴드{band}")
        if strat_cost > 0:
            print(f"   └ 소계: 투입 {strat_cost:,.0f}원 · 평가손익 {strat_mtm:+,.0f}원 "
                  f"({strat_mtm / strat_cost * 100:+.2f}%)")

    print("\n" + "=" * 96)
    roi = (grand_mtm / grand_cost * 100.0) if grand_cost else 0.0
    print(f"합계: 실매수 {grand_n}종목 · 투입 {grand_cost:,.0f}원 · "
          f"6/19 종가 평가손익 {grand_mtm:+,.0f}원 ({roi:+.2f}%)")
    print("(전 전략 swing이라 당일 실현청산 0건 — 위는 전부 미실현 평가손익)")
    print("=" * 96)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
