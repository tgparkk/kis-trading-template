"""한정자본 포트폴리오 멀티버스 드라이버 (재사용 가능).

book_param_multiverse.py 가 "종목당 독립계좌 룰엣지"를 스윕하는 반면, 이 드라이버는
**한정자본·최대보유종목수 K·종목당 한도** 의 단일 포트폴리오 모델 위에서
  매수후보(진입룰 dataclass 필드) × 보유종목수 K × 매도타이밍(sl/tp/mh)
를 동시에 그리드 스윕한다. 포트폴리오 경합(슬롯·현금 부족 skip, turnover 우선순위)이
반영되므로 K 가 결과에 영향을 준다 (book_param 의 종목별 평균과 다른 측정치).

부품은 기존 파일에서 import 재사용 (다른 파일 수정 없음):
- 데이터/유니버스/turnover 로더: book_param_multiverse 의 _load_* (일봉), 본 파일의 분봉 로더.
- 포트폴리오 시뮬: scripts.exit_multiverse.portfolio_sim.run_portfolio.
- 책/룰 로드·그리드분할·병렬워커·콘솔포맷: book_param_multiverse 의 헬퍼.

흐름:
  책/룰 로드 → 데이터 로드(daily=daily_prices/adj, minute=minute_candles→15분 리샘플)
  → 종목별 turnover 계산 → entry 조합별 진입신호 캐시 생성(no-lookahead)
  → exit×K 조합마다 run_portfolio() (캐시 재사용) → 포트폴리오 메트릭.

최적화:
  진입신호 캐시는 **entry 조합이 바뀔 때만** 재생성한다. 같은 entry 의 모든
  exit×K 조합은 동일 캐시를 재사용하므로 신호평가 비용을 entry 조합 수로 한정한다.

목적함수:
- 다구간(분봉 periods / 일봉 다구간은 미지원, 분봉만 다구간):
  pos_periods(pnl>0 구간 수) desc → mean_sharpe desc → mean_pnl desc.
  단 1구간만 양수면 [OVERFIT] 플래그 (book_param 분봉 관례 동일).
- 단일구간(일봉 --start/--end): sharpe desc → pnl desc.

CLI:
  --book --rule --granularity{daily,minute} --start --end --periods
  --entry-grid(JSON 룰필드) --exit-grid(JSON sl/tp/mh) --K-list(공백구분 정수)
  --max-per-stock --initial-capital --universe(top_volume:N) --minute-resample-freq
  --workers --limit --out

출력:
  <out>/book_portfolio_<book>_<rule>.tsv (전 조합 정렬) + 콘솔 top-K + best vs baseline.

usage (일봉, close_betting):
  python scripts/book_portfolio_multiverse.py --book close_betting --rule close_betting_setup \
    --granularity daily --start 2024-01-01 --end 2025-12-31 \
    --entry-grid '{"vol_dryup":[0.3,0.5]}' --exit-grid '{"sl":[0.03],"tp":[0.03],"mh":[1,2]}' \
    --K-list 5 10 --max-per-stock 3000000 --initial-capital 10000000 \
    --universe top_volume:50 --out D:\\tmp\\multiverse\\bpf_smoke

usage (15분봉, surge_fade):
  python scripts/book_portfolio_multiverse.py --book surge_fade --rule surge_fade \
    --granularity minute --periods 2025-10,2026-04,2026-05 \
    --entry-grid '{"vol_dryup_ratio":[0.25,0.4]}' --exit-grid '{"sl":[0.03,0.05],"tp":[0.07],"mh":[16,24]}' \
    --K-list 5 10 --universe top_volume:50 --out D:\\tmp\\multiverse\\surge_fade_canonical
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import math
import os
import sys
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows 콘솔(cp949)에서 비-ASCII 출력 안전화
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

# 부품 재사용 (book_param_multiverse 의 로더·헬퍼). 다른 파일 수정 없음.
from scripts.book_param_multiverse import (  # noqa: E402
    MINUTE_PERIODS,
    _build_strategy,
    _cartesian,
    _load_book,
    _load_daily_adj,
    _load_minute_data,
    _load_top_volume_daily,
    _load_top_volume_minute,
    _daily_minmax_dates,
    _rule_defaults,
    _resolve_rule_cls,
)
from scripts.exit_multiverse.portfolio_sim import run_portfolio  # noqa: E402

LOG = logging.getLogger("book_portfolio_multiverse")

EXIT_KEYS = ("sl", "tp", "mh")


# ===========================================================================
# 범용 sl/tp/mh exit adapter (portfolio_sim.run_portfolio 규약 준수)
#   - entry_mechanism="market": 신호 다음봉 시가 진입 (close_betting/surge_fade 공통).
#   - exit_reason(df, i, position, params): bar i 종가 기준 sl→tp→mh 우선순위 청산.
#     position dict 는 run_portfolio 가 채우는 {entry_idx, entry_price, qty, ...}.
# ===========================================================================

class _SLTPMHAdapter:
    entry_mechanism = "market"

    @staticmethod
    def exit_reason(df, i, position, params) -> Optional[str]:
        entry_price = position["entry_price"]
        cur_close = float(df.iloc[i]["close"])
        ret = (cur_close - entry_price) / entry_price
        hold_bars = i - position["entry_idx"]
        if ret <= -params["stop_loss_pct"]:
            return "stop_loss"
        if ret >= params["take_profit_pct"]:
            return "take_profit"
        if hold_bars >= params["max_hold_bars"]:
            return "max_hold"
        return None


_ADAPTER = _SLTPMHAdapter()


# ===========================================================================
# 급등주(surge) 유니버스 로더 — 책 의도(중소형 급등주) 정합.
#   매수후보 풀 = 기간 내 일간 등락률 ≥ surge_threshold(+15%) 이력 + (시총<cap) 종목.
#   거기서 거래대금 상위 N(결정적 정렬). top_volume:N 정본과 동일하게
#   "기간 전체" 통계로 풀을 고정하는 정적 유니버스 모델(진입 타이밍은 룰의
#   no-lookahead 평가가 보장). 시총은 daily_prices.market_cap(부분·일부 stale)을
#   종목별 최신값으로 사용하고, 데이터 없으면 통과(필터에서 배제하지 않음).
#
# no-lookahead 주: 풀 멤버십은 정적 백테스트의 본질적 선택(baseline top_volume:N
#   도 기간 전체 turnover 로 선정)이라 baseline 과 동일 잣대. 종목 내 진입 시점은
#   df.iloc[:i+1] 만 사용하므로 미래 누설 없음.
# ===========================================================================

SURGE_THRESHOLD = 0.15      # 일간 등락률 ≥ +15% = 급등
SURGE_MARKET_CAP_MAX = 5_000e8   # 시총 < 5,000억 (중소형)


def _surge_smallcap_codes(start: str, end: str,
                          surge_threshold: float = SURGE_THRESHOLD,
                          cap_max: float = SURGE_MARKET_CAP_MAX,
                          require_mc: bool = False) -> Tuple[set, dict]:
    """[start, end] daily_prices 에서 ①+surge_threshold 이상 일간급등 이력 종목 +
    ②시총 게이트 적용 종목코드 set 과 진단 dict 반환.

    시총 게이트(daily_prices.market_cap 종목별 최신값, 부분·stale):
      - require_mc=False(기본): mc<cap_max OR mc 미상 통과 (급등필터 우선, 책 1차 사양).
        단 mc 커버리지가 낮으면(현 98/256) mc미상 대형주가 거래대금 상위로 누수됨.
      - require_mc=True: mc 가 알려져 있고 mc<cap_max 인 종목만 (엄격 중소형, 누수 차단).
    """
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            WITH px AS (
                SELECT stock_code, date, close,
                       LAG(close) OVER (PARTITION BY stock_code ORDER BY date) AS pc
                FROM daily_prices
                WHERE date >= %s AND date <= %s AND close > 0
            )
            SELECT DISTINCT stock_code FROM px
            WHERE pc > 0 AND (close - pc) / pc >= %s
            """,
            (start, end, surge_threshold),
        )
        surged = {r[0] for r in cur.fetchall()}
        # 종목별 최신 market_cap (양수)
        cur.execute(
            """
            SELECT DISTINCT ON (stock_code) stock_code, market_cap
            FROM daily_prices
            WHERE market_cap > 0 AND date <= %s
            ORDER BY stock_code, date DESC
            """,
            (end,),
        )
        last_mc = {r[0]: float(r[1]) for r in cur.fetchall()}
    n_surged = len(surged)
    if require_mc:
        smallcap = {c for c in surged if c in last_mc and last_mc[c] < cap_max}
    else:
        smallcap = {c for c in surged if last_mc.get(c) is None or last_mc[c] < cap_max}
    n_mc_known = sum(1 for c in surged if c in last_mc)
    n_excluded_bigcap = n_surged - len(smallcap)
    diag = dict(n_surged=n_surged, n_mc_known=n_mc_known, require_mc=require_mc,
                n_excluded_bigcap=n_excluded_bigcap, n_pool=len(smallcap))
    return smallcap, diag


def _load_surge_daily(start: str, end: str, top_n: int,
                      require_mc: bool = False) -> Tuple[List[str], dict]:
    """급등주 풀(중소형) ∩ daily 거래대금 상위 N. 결정적(turnover desc, code asc)."""
    pool, diag = _surge_smallcap_codes(start, end, require_mc=require_mc)
    if not pool:
        return [], diag
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT stock_code, SUM(close * volume) AS turnover
            FROM daily_prices
            WHERE date >= %s AND date <= %s AND stock_code = ANY(%s)
            GROUP BY stock_code
            ORDER BY turnover DESC, stock_code ASC
            LIMIT %s
            """,
            (start, end, list(pool), top_n),
        )
        codes = [r[0] for r in cur.fetchall()]
    diag["n_selected"] = len(codes)
    return codes, diag


def _load_surge_minute(period_start: str, period_end: str, top_n: int,
                       surge_lookback_days: int = 120,
                       require_mc: bool = False) -> Tuple[List[str], dict]:
    """분봉 급등주 풀: 풀 산정은 daily_prices(룩백 surge_lookback_days, period_end 까지)로
    급등이력+중소형을 뽑고, 그 풀 ∩ minute_candles 거래대금 상위 N(결정적).

    분봉 구간(1개월)은 급등 이력 측정에 너무 짧아 daily 룩백을 쓴다.
    룩백은 period_end 이전 데이터만 사용 → no-lookahead.
    """
    import datetime as _dt
    end_d = _dt.date.fromisoformat(period_end)
    look_start = (end_d - _dt.timedelta(days=surge_lookback_days)).isoformat()
    pool, diag = _surge_smallcap_codes(look_start, period_end, require_mc=require_mc)
    diag["surge_lookback"] = f"{look_start}~{period_end} ({surge_lookback_days}d)"
    if not pool:
        return [], diag
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        q = """
            SELECT stock_code, SUM(close * volume) AS turnover
            FROM minute_candles
            WHERE datetime >= %s AND datetime < %s::date + INTERVAL '1 day'
              AND stock_code = ANY(%s)
            GROUP BY stock_code
            ORDER BY turnover DESC, stock_code ASC
            LIMIT %s
        """
        df = pd.read_sql(q, conn, params=(period_start, period_end, list(pool), top_n))
    codes = df["stock_code"].tolist()
    diag["n_selected"] = len(codes)
    return codes, diag


# ===========================================================================
# 진입 신호 캐시 (no-lookahead) — entry 조합당 1회 생성, exit×K 가 재사용.
# ===========================================================================

def _precompute_signals(
    data: Dict[str, pd.DataFrame], strategy, warmup_bars: int, granularity: str,
) -> Dict[str, List[int]]:
    """각 종목에서 룰 triggered 인 bar 인덱스 i 목록 (no-lookahead).

    평가: window=df.iloc[:i+1], generate_signal(code, window, timeframe).
    i 범위 [warmup_bars, n-2] (마지막 봉은 다음봉 체결 불가 → run_portfolio 와 정합).
    """
    from strategies.base import SignalType
    timeframe = "daily" if granularity == "daily" else "minute"
    cache: Dict[str, List[int]] = {}
    for code, df in data.items():
        n = len(df)
        sig_bars: List[int] = []
        if n >= warmup_bars + 2:
            for i in range(warmup_bars, n - 1):
                window = df.iloc[: i + 1]
                sig = strategy.generate_signal(code, window, timeframe)
                if sig is not None and sig.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                    sig_bars.append(i)
        cache[code] = sig_bars
    return cache


# ===========================================================================
# 포트폴리오 메트릭 (run_portfolio 반환 → Sharpe/PnL/MaxDD/Calmar/hit).
#   portfolio_sim_elder.compute_portfolio_metrics 는 equity_dates/invested_ratio/
#   n_holdings 키를 요구하나 run_portfolio 는 미반환 → 동일 수식의 경량 메트릭 사용.
# ===========================================================================

def _portfolio_metrics(res: dict, initial: float) -> dict:
    eq = np.asarray(res["equity_curve"], dtype=float)
    if eq.size == 0:
        return dict(n_trades=0, pnl=0.0, sharpe=0.0, calmar=0.0, max_dd=0.0, hit=0.0,
                    max_concurrent=res.get("max_concurrent_positions", 0),
                    n_skipped=res.get("n_skipped", 0))
    pnl = (eq[-1] - initial) / initial
    rets = res["daily_returns"].to_numpy() if hasattr(res["daily_returns"], "to_numpy") \
        else np.asarray(res["daily_returns"], dtype=float)
    rets = rets[np.isfinite(rets)]
    sharpe = float(rets.mean() / rets.std() * math.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = float(-dd.min()) if len(dd) else 0.0
    calmar = float(pnl / max_dd) if max_dd > 1e-9 else 0.0
    sells = [t for t in res["trades"] if t["side"] == "sell"]
    wins = sum(1 for t in sells if t["pnl_pct"] > 0)
    hit = wins / len(sells) if sells else 0.0
    return dict(n_trades=len(sells), pnl=pnl, sharpe=sharpe, calmar=calmar, max_dd=max_dd,
                hit=hit, max_concurrent=res.get("max_concurrent_positions", 0),
                n_skipped=res.get("n_skipped", 0))


# ===========================================================================
# grid 분할 (book_param 의 _split_grid 와 동일 철학; entry/exit 를 별도 인자로 받음)
# ===========================================================================

def _validate_entry_grid(entry_grid: Dict[str, List], rule_cls) -> Dict[str, List]:
    rule_field_names = {f.name for f in dataclass_fields(rule_cls)} - {"name"}
    out: Dict[str, List] = {}
    for k, v in entry_grid.items():
        if k not in rule_field_names:
            raise ValueError(
                f"--entry-grid 키 {k!r} 는 룰 {rule_cls.__name__} 필드가 아님. "
                f"가능: {sorted(rule_field_names)}"
            )
        out[k] = list(v)
    return out


def _normalize_exit_grid(exit_grid: Dict[str, List]) -> Dict[str, List]:
    out: Dict[str, List] = {}
    for k, v in exit_grid.items():
        if k not in EXIT_KEYS:
            raise ValueError(f"--exit-grid 키 {k!r} 는 {EXIT_KEYS} 중 하나여야 함")
        out[k] = list(v)
    out.setdefault("sl", [0.03])
    out.setdefault("tp", [0.05])
    out.setdefault("mh", [5])
    return out


# ===========================================================================
# 15분 리샘플 (분봉 트랙)
# ===========================================================================

def _resample_15(data1m: Dict[str, pd.DataFrame], freq: int) -> Dict[str, pd.DataFrame]:
    from core.timeframe_converter import TimeFrameConverter
    out: Dict[str, pd.DataFrame] = {}
    for code, df in data1m.items():
        r = TimeFrameConverter.convert_to_timeframe(df, freq)
        if r is not None and not r.empty:
            out[code] = r.reset_index(drop=True)
    return out


# ===========================================================================
# entry 조합 평가 (캐시 1회 + 모든 exit×K) — 순차/병렬 공용 picklable 함수
# ===========================================================================

# 워커 전역 (initializer 가 채움)
_W_RULE_CLS = None
_W_RULE_NAME = None
_W_GRANULARITY = None
_W_WARMUP = None
_W_PERIODS: Optional[List[str]] = None
_W_PERIOD_DATA: Optional[Dict[str, Dict[str, pd.DataFrame]]] = None
_W_PERIOD_TURNOVER: Optional[Dict[str, Dict[str, float]]] = None
_W_DATA: Optional[Dict[str, pd.DataFrame]] = None
_W_TURNOVER: Optional[Dict[str, float]] = None
_W_EXIT_COMBOS: Optional[List[Dict[str, Any]]] = None
_W_K_LIST: Optional[List[int]] = None
_W_MAX_PER_STOCK: float = 3_000_000.0
_W_INITIAL: float = 10_000_000.0


def _eval_entry_minute(ro: Dict[str, Any]) -> List[dict]:
    """한 entry 조합 (minute): 캐시 1회/구간 → 모든 exit×K 조합 row 리스트."""
    strat = _build_strategy(_W_RULE_CLS, _W_RULE_NAME, ro)
    # entry 조합당 구간별 캐시 1회 생성 (exit×K 재사용)
    caches: Dict[str, Dict[str, List[int]]] = {}
    for pr in _W_PERIODS:
        caches[pr] = _precompute_signals(_W_PERIOD_DATA[pr], strat, _W_WARMUP, "minute")

    rows: List[dict] = []
    for eo in _W_EXIT_COMBOS:
        params = dict(stop_loss_pct=eo["sl"], take_profit_pct=eo["tp"], max_hold_bars=eo["mh"])
        for K in _W_K_LIST:
            per_period = {}
            for pr in _W_PERIODS:
                res = run_portfolio(
                    data=_W_PERIOD_DATA[pr], signal_cache=caches[pr], adapter=_ADAPTER,
                    params=params, turnover=_W_PERIOD_TURNOVER[pr],
                    initial_capital=_W_INITIAL, max_positions=K,
                    max_per_stock=_W_MAX_PER_STOCK,
                )
                per_period[pr] = _portfolio_metrics(res, _W_INITIAL)
            pnls = [per_period[pr]["pnl"] for pr in _W_PERIODS]
            shs = [per_period[pr]["sharpe"] for pr in _W_PERIODS]
            ntr = sum(per_period[pr]["n_trades"] for pr in _W_PERIODS)
            nskip = sum(per_period[pr]["n_skipped"] for pr in _W_PERIODS)
            mxc = max((per_period[pr]["max_concurrent"] for pr in _W_PERIODS), default=0)
            pos_periods = sum(1 for x in pnls if x > 0)
            mean_sharpe = float(np.mean(shs)) if shs else 0.0
            mean_pnl = float(np.mean(pnls)) if pnls else 0.0
            overfit = (pos_periods == 1 and len(_W_PERIODS) > 1)
            row = {**{f"e_{k}": v for k, v in ro.items()},
                   "sl": eo["sl"], "tp": eo["tp"], "mh": eo["mh"], "K": K,
                   "n_trades": ntr, "pos_periods": pos_periods, "n_periods": len(_W_PERIODS),
                   "sharpe": mean_sharpe, "pnl": mean_pnl, "overfit": overfit,
                   "max_concurrent": mxc, "n_skipped": nskip, "_entry_over": ro}
            for pr in _W_PERIODS:
                row[f"pnl_{pr}"] = per_period[pr]["pnl"]
            rows.append(row)
    return rows


def _eval_entry_daily(ro: Dict[str, Any]) -> List[dict]:
    """한 entry 조합 (daily): 캐시 1회 → 모든 exit×K 조합 row 리스트."""
    strat = _build_strategy(_W_RULE_CLS, _W_RULE_NAME, ro)
    cache = _precompute_signals(_W_DATA, strat, _W_WARMUP, "daily")

    rows: List[dict] = []
    for eo in _W_EXIT_COMBOS:
        params = dict(stop_loss_pct=eo["sl"], take_profit_pct=eo["tp"], max_hold_bars=eo["mh"])
        for K in _W_K_LIST:
            res = run_portfolio(
                data=_W_DATA, signal_cache=cache, adapter=_ADAPTER, params=params,
                turnover=_W_TURNOVER, initial_capital=_W_INITIAL, max_positions=K,
                max_per_stock=_W_MAX_PER_STOCK,
            )
            m = _portfolio_metrics(res, _W_INITIAL)
            row = {**{f"e_{k}": v for k, v in ro.items()},
                   "sl": eo["sl"], "tp": eo["tp"], "mh": eo["mh"], "K": K,
                   "n_trades": m["n_trades"], "sharpe": m["sharpe"], "pnl": m["pnl"],
                   "calmar": m["calmar"], "hit": m["hit"], "max_dd": m["max_dd"],
                   "max_concurrent": m["max_concurrent"], "n_skipped": m["n_skipped"],
                   "_entry_over": ro}
            rows.append(row)
    return rows


# --- 병렬 워커 initializer / wrapper ---

def _winit_minute(rule_cls, rule_name, warmup, periods, period_data, period_turnover,
                  exit_combos, k_list, max_per_stock, initial):
    global _W_RULE_CLS, _W_RULE_NAME, _W_WARMUP, _W_PERIODS, _W_PERIOD_DATA
    global _W_PERIOD_TURNOVER, _W_EXIT_COMBOS, _W_K_LIST, _W_MAX_PER_STOCK, _W_INITIAL
    _W_RULE_CLS = rule_cls; _W_RULE_NAME = rule_name; _W_WARMUP = warmup
    _W_PERIODS = periods; _W_PERIOD_DATA = period_data; _W_PERIOD_TURNOVER = period_turnover
    _W_EXIT_COMBOS = exit_combos; _W_K_LIST = k_list
    _W_MAX_PER_STOCK = max_per_stock; _W_INITIAL = initial


def _winit_daily(rule_cls, rule_name, warmup, data, turnover, exit_combos, k_list,
                 max_per_stock, initial):
    global _W_RULE_CLS, _W_RULE_NAME, _W_WARMUP, _W_DATA, _W_TURNOVER
    global _W_EXIT_COMBOS, _W_K_LIST, _W_MAX_PER_STOCK, _W_INITIAL
    _W_RULE_CLS = rule_cls; _W_RULE_NAME = rule_name; _W_WARMUP = warmup
    _W_DATA = data; _W_TURNOVER = turnover
    _W_EXIT_COMBOS = exit_combos; _W_K_LIST = k_list
    _W_MAX_PER_STOCK = max_per_stock; _W_INITIAL = initial


def _worker_minute(task: Tuple[int, Dict[str, Any]]) -> Tuple[int, List[dict]]:
    idx, ro = task
    return idx, _eval_entry_minute(ro)


def _worker_daily(task: Tuple[int, Dict[str, Any]]) -> Tuple[int, List[dict]]:
    idx, ro = task
    return idx, _eval_entry_daily(ro)


def _run_entry_combos(tasks, workers, worker_fn, init_fn, init_args, seq_fn) -> List[dict]:
    """entry 조합 태스크 평가 → idx 오름차순(=순차 순서) row 리스트(평탄화). 결정성 보장."""
    n = len(tasks)
    if workers <= 1 or n <= 1:
        out: List[dict] = []
        for t in tasks:
            out.extend(seq_fn(t))
        return out
    import multiprocessing as mp
    procs = min(workers, n)
    LOG.info(f"parallel eval: {n} entry combos across {procs} workers")
    indexed: List[Tuple[int, List[dict]]] = []
    with mp.Pool(processes=procs, initializer=init_fn, initargs=init_args) as pool:
        chunk = max(1, n // (procs * 4))
        for idx, rows in pool.imap_unordered(worker_fn, tasks, chunksize=chunk):
            indexed.append((idx, rows))
    indexed.sort(key=lambda x: x[0])
    flat: List[dict] = []
    for _, rows in indexed:
        flat.extend(rows)
    return flat


# ===========================================================================
# 포맷 헬퍼
# ===========================================================================

def _combo_label(entry_over: Dict[str, Any], sl, tp, mh, K) -> str:
    parts = [f"{k}={v}" for k, v in sorted(entry_over.items())]
    parts += [f"sl={sl}", f"tp={tp}", f"mh={mh}", f"K={K}"]
    return " ".join(parts)


# ===========================================================================
# main
# ===========================================================================

def main():
    p = argparse.ArgumentParser(description="한정자본 포트폴리오 멀티버스 (진입×K×청산 스윕)")
    p.add_argument("--book", required=True)
    p.add_argument("--rules-module", default="rules", dest="rules_module")
    p.add_argument("--rule", required=True, help="단일 룰 .name (또는 rule_<name>)")
    p.add_argument("--universe", default="top_volume:50")
    p.add_argument("--granularity", default="auto", choices=["minute", "daily", "auto"])
    p.add_argument("--periods", default="2025-10,2026-04,2026-05",
                   help="분봉 전용 쉼표구분 구간 (daily 는 무시)")
    p.add_argument("--start", default=None, help="daily 기간 시작 (기본 daily_prices 최소)")
    p.add_argument("--end", default=None, help="daily 기간 끝 (기본 daily_prices 최대)")
    p.add_argument("--entry-grid", required=True, dest="entry_grid",
                   help='JSON: {"<rule_field>":[...], ...} (매수후보/매수타이밍)')
    p.add_argument("--exit-grid", required=True, dest="exit_grid",
                   help='JSON: {"sl":[...],"tp":[...],"mh":[...]} (매도타이밍)')
    p.add_argument("--K-list", type=int, nargs="+", required=True, dest="k_list",
                   help="보유종목수 max_positions 후보 (공백구분)")
    p.add_argument("--max-per-stock", type=float, default=3_000_000.0, dest="max_per_stock")
    p.add_argument("--initial-capital", type=float, default=10_000_000.0, dest="initial_capital")
    p.add_argument("--minute-resample-freq", type=int, default=15, dest="resample_freq")
    p.add_argument("--out", default=None)
    p.add_argument("--limit", type=int, default=None, help="유니버스 N개 제한 (속도)")
    p.add_argument("--top-k", type=int, default=15)
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 1) - 1),
                   help="entry 조합 병렬 워커 수 (기본 cpu-1). 1이면 순차(회귀 안전).")
    p.add_argument("--surge-require-mc", action="store_true", dest="surge_require_mc",
                   help="surge 유니버스에서 시총 미상 종목 배제(엄격 중소형). "
                        "기본 off=mc 미상 통과(대형주 누수 가능, 책 1차 사양).")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.universe.startswith("top_volume:"):
        universe_kind = "top_volume"
    elif args.universe.startswith("surge:"):
        universe_kind = "surge"
    else:
        p.error("--universe 는 top_volume:N 또는 surge:N 형식만 지원")
    top_n = int(args.universe.split(":", 1)[1])

    strat_mod, rules_mod = _load_book(args.book, args.rules_module)
    rule_cls = _resolve_rule_cls(rules_mod, args.rule)
    rule_name = rule_cls().name

    granularity = args.granularity
    if granularity == "auto":
        g = getattr(strat_mod, "BOOK_META", {}).get("data_granularity", "minute")
        granularity = "minute" if g.startswith("minute") else "daily"
    LOG.info(f"book={args.book} rule={rule_name} granularity={granularity} "
             f"universe={universe_kind}:{top_n} K={args.k_list}")

    entry_grid = _validate_entry_grid(json.loads(args.entry_grid), rule_cls)
    exit_grid = _normalize_exit_grid(json.loads(args.exit_grid))
    entry_combos = _cartesian(entry_grid)
    exit_combos = _cartesian(exit_grid)
    total = len(entry_combos) * len(exit_combos) * len(args.k_list)
    LOG.info(f"grid: entry={len(entry_combos)} exit={len(exit_combos)} K={len(args.k_list)} "
             f"total={total} (캐시는 entry당 1회 = {len(entry_combos)}회만 생성)")

    out_dir = Path(args.out) if args.out else Path(r"D:\tmp\multiverse") / f"{args.book}_{rule_name}_portfolio"
    out_dir.mkdir(parents=True, exist_ok=True)

    # warmup: 룰 평가에 필요한 최소 봉 (분봉은 min_bars/ma 게이트, 일봉은 lookback 충당)
    warmup = 70 if granularity == "minute" else 42

    rows: List[dict] = []

    if granularity == "minute":
        periods = [x.strip() for x in args.periods.split(",") if x.strip()]
        for pr in periods:
            if pr not in MINUTE_PERIODS:
                p.error(f"분봉 기간 {pr!r} 미정의. 사용가능: {list(MINUTE_PERIODS)}")
        period_data: Dict[str, Dict[str, pd.DataFrame]] = {}
        period_turnover: Dict[str, Dict[str, float]] = {}
        for pr in periods:
            start, end = MINUTE_PERIODS[pr]
            if universe_kind == "surge":
                uni, sdiag = _load_surge_minute(start, end, top_n,
                                                require_mc=args.surge_require_mc)
                LOG.info(f"period={pr} surge-universe(require_mc={args.surge_require_mc}): "
                         f"lookback={sdiag.get('surge_lookback')} "
                         f"surged={sdiag['n_surged']} mc_known={sdiag['n_mc_known']} "
                         f"excl_bigcap={sdiag['n_excluded_bigcap']} pool={sdiag['n_pool']} "
                         f"selected={sdiag.get('n_selected', 0)} "
                         f"(mc=daily_prices.market_cap 부분·일부 stale, 미상은 통과)")
            else:
                uni = _load_top_volume_minute(start, end, top_n)
            if args.limit:
                uni = uni[: args.limit]
            data1m = _load_minute_data(uni, start, end)
            data = _resample_15(data1m, args.resample_freq)
            period_data[pr] = data
            # turnover = 구간 종목별 close*volume 합 (진입 우선순위)
            period_turnover[pr] = {
                code: float((df["close"] * df["volume"]).sum()) for code, df in data.items()
            }
            LOG.info(f"period={pr} universe={len(uni)} resampled_data={len(data)} "
                     f"(freq={args.resample_freq}m)")

        tasks = [(i, ro) for i, ro in enumerate(entry_combos)]
        rows = _run_entry_combos(
            tasks, args.workers, _worker_minute,
            _winit_minute, (rule_cls, rule_name, warmup, periods, period_data,
                            period_turnover, exit_combos, args.k_list,
                            args.max_per_stock, args.initial_capital),
            lambda t: _eval_entry_minute_seq(t[1], rule_cls, rule_name, warmup, periods,
                                             period_data, period_turnover, exit_combos,
                                             args.k_list, args.max_per_stock, args.initial_capital),
        )
        rows.sort(key=lambda r: (-r["pos_periods"], -r["sharpe"], -r["pnl"]))
        sort_desc = "pos_periods desc, mean_sharpe desc, mean_pnl desc"
        regimes = False
    else:  # daily
        if args.start is None or args.end is None:
            mn, mx = _daily_minmax_dates()
            start = args.start or mn
            end = args.end or mx
        else:
            start, end = args.start, args.end
        LOG.info(f"daily period: {start} ~ {end}")
        if universe_kind == "surge":
            uni, sdiag = _load_surge_daily(start, end, top_n,
                                           require_mc=args.surge_require_mc)
            LOG.info(f"surge-universe(require_mc={args.surge_require_mc}): "
                     f"surged={sdiag['n_surged']} mc_known={sdiag['n_mc_known']} "
                     f"excl_bigcap={sdiag['n_excluded_bigcap']} pool={sdiag['n_pool']} "
                     f"selected={sdiag.get('n_selected', 0)} "
                     f"(filter: >=+{SURGE_THRESHOLD:.0%} day in window + mc<{SURGE_MARKET_CAP_MAX/1e8:.0f}억; "
                     f"mc=daily_prices.market_cap 부분·일부 stale, 미상은 통과)")
        else:
            uni = _load_top_volume_daily(start, end, top_n)
        if args.limit:
            uni = uni[: args.limit]
        data = _load_daily_adj(uni, start, end)
        turnover = {code: float((df["close"] * df["volume"]).sum()) for code, df in data.items()}
        LOG.info(f"universe={len(uni)} loaded_data={len(data)}")
        regimes = (args.start is not None and args.end is not None)

        tasks = [(i, ro) for i, ro in enumerate(entry_combos)]
        rows = _run_entry_combos(
            tasks, args.workers, _worker_daily,
            _winit_daily, (rule_cls, rule_name, warmup, data, turnover, exit_combos,
                           args.k_list, args.max_per_stock, args.initial_capital),
            lambda t: _eval_entry_daily_seq(t[1], rule_cls, rule_name, warmup, data, turnover,
                                            exit_combos, args.k_list, args.max_per_stock,
                                            args.initial_capital),
        )
        rows.sort(key=lambda r: (-r["sharpe"], -r["pnl"]))
        sort_desc = "sharpe desc, pnl desc"

    # --- TSV 저장 ---
    tsv_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    tsv_path = out_dir / f"book_portfolio_{args.book}_{rule_name}.tsv"
    pd.DataFrame(tsv_rows).to_csv(tsv_path, sep="\t", index=False)

    # --- top-K 콘솔 ---
    print(f"\n=== PORTFOLIO MULTIVERSE {args.book} / {rule_name} ({granularity}) "
          f"- sorted by {sort_desc} ===")
    print(f"total combos: {len(rows)}  |  initial={args.initial_capital:,.0f} "
          f"max_per_stock={args.max_per_stock:,.0f}  |  tsv: {tsv_path}")
    topk = rows[: args.top_k]
    if granularity == "minute":
        print(f"{'rank':>4} {'combo':<52} {'ntr':>5} {'pos/N':>6} {'mSharpe':>8} "
              f"{'mPnl':>8} {'mxc':>4} {'skip':>6}  flag")
        for i, r in enumerate(topk, 1):
            label = _combo_label(r["_entry_over"], r["sl"], r["tp"], r["mh"], r["K"])
            flag = "[OVERFIT]" if r["overfit"] else ""
            print(f"{i:>4} {label:<52} {r['n_trades']:>5} "
                  f"{r['pos_periods']}/{r['n_periods']:>3} {r['sharpe']:>8.3f} "
                  f"{r['pnl']:>8.4f} {r['max_concurrent']:>4} {r['n_skipped']:>6}  {flag}")
    else:
        print(f"{'rank':>4} {'combo':<52} {'ntr':>5} {'sharpe':>8} {'pnl':>9} "
              f"{'calmar':>7} {'hit':>6} {'maxdd':>7} {'mxc':>4} {'skip':>6}")
        for i, r in enumerate(topk, 1):
            label = _combo_label(r["_entry_over"], r["sl"], r["tp"], r["mh"], r["K"])
            print(f"{i:>4} {label:<52} {r['n_trades']:>5} {r['sharpe']:>8.3f} "
                  f"{r['pnl']:>9.4f} {r['calmar']:>7.2f} {r['hit']:>6.2%} "
                  f"{r['max_dd']:>7.2%} {r['max_concurrent']:>4} {r['n_skipped']:>6}")

    # --- best vs baseline ---
    defaults = _rule_defaults(rule_cls)
    baseline_entry_over = {k: defaults[k] for k in entry_grid.keys()}
    bl_sl = exit_grid["sl"][0]; bl_tp = exit_grid["tp"][0]; bl_mh = exit_grid["mh"][0]
    bl_K = args.k_list[0]

    def _match(r):
        return (r["_entry_over"] == baseline_entry_over and r["sl"] == bl_sl
                and r["tp"] == bl_tp and r["mh"] == bl_mh and r["K"] == bl_K)

    baseline = next((r for r in rows if _match(r)), None)
    best = rows[0] if rows else None
    print("\n--- BEST vs BASELINE ---")
    if best is not None:
        print(f"BEST    : {_combo_label(best['_entry_over'], best['sl'], best['tp'], best['mh'], best['K'])}")
        if granularity == "minute":
            print(f"          pos={best['pos_periods']}/{best['n_periods']} "
                  f"mSharpe={best['sharpe']:.3f} mPnl={best['pnl']:.4f} "
                  f"mxc={best['max_concurrent']} skip={best['n_skipped']} "
                  f"{'[OVERFIT]' if best['overfit'] else ''}")
        else:
            print(f"          sharpe={best['sharpe']:.3f} pnl={best['pnl']:.4f} "
                  f"calmar={best['calmar']:.2f} hit={best['hit']:.2%} "
                  f"mxc={best['max_concurrent']} skip={best['n_skipped']}")
    if baseline is not None:
        bl_label = _combo_label(baseline["_entry_over"], baseline["sl"], baseline["tp"],
                                baseline["mh"], baseline["K"])
        print(f"BASELINE: {bl_label}")
        if granularity == "minute":
            print(f"          pos={baseline['pos_periods']}/{baseline['n_periods']} "
                  f"mSharpe={baseline['sharpe']:.3f} mPnl={baseline['pnl']:.4f}")
        else:
            print(f"          sharpe={baseline['sharpe']:.3f} pnl={baseline['pnl']:.4f} "
                  f"calmar={baseline['calmar']:.2f} hit={baseline['hit']:.2%}")
    else:
        print("BASELINE: (rule defaults + first exit + first K) 가 grid 에 없어 비교 생략")

    if granularity == "daily" and regimes:
        print(f"\n(regime window: {start} ~ {end} - results above limited to this window)")


# 순차 경로용 wrapper (병렬 init 인자를 클로저로 받아 전역 의존 없이 평가) ---------

def _eval_entry_minute_seq(ro, rule_cls, rule_name, warmup, periods, period_data,
                           period_turnover, exit_combos, k_list, max_per_stock, initial):
    global _W_RULE_CLS, _W_RULE_NAME, _W_WARMUP, _W_PERIODS, _W_PERIOD_DATA
    global _W_PERIOD_TURNOVER, _W_EXIT_COMBOS, _W_K_LIST, _W_MAX_PER_STOCK, _W_INITIAL
    _W_RULE_CLS = rule_cls; _W_RULE_NAME = rule_name; _W_WARMUP = warmup
    _W_PERIODS = periods; _W_PERIOD_DATA = period_data; _W_PERIOD_TURNOVER = period_turnover
    _W_EXIT_COMBOS = exit_combos; _W_K_LIST = k_list
    _W_MAX_PER_STOCK = max_per_stock; _W_INITIAL = initial
    return _eval_entry_minute(ro)


def _eval_entry_daily_seq(ro, rule_cls, rule_name, warmup, data, turnover, exit_combos,
                          k_list, max_per_stock, initial):
    global _W_RULE_CLS, _W_RULE_NAME, _W_WARMUP, _W_DATA, _W_TURNOVER
    global _W_EXIT_COMBOS, _W_K_LIST, _W_MAX_PER_STOCK, _W_INITIAL
    _W_RULE_CLS = rule_cls; _W_RULE_NAME = rule_name; _W_WARMUP = warmup
    _W_DATA = data; _W_TURNOVER = turnover
    _W_EXIT_COMBOS = exit_combos; _W_K_LIST = k_list
    _W_MAX_PER_STOCK = max_per_stock; _W_INITIAL = initial
    return _eval_entry_daily(ro)


if __name__ == "__main__":
    main()
