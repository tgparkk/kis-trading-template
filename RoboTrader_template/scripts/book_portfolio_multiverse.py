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
  --regime-gate(PIT 국면 게이트 차원) --entry-filter(PIT 진입필터 차원, scripts.entry_filters)
  --filter-threshold(rs_rank 백분위/adx 컷) --filter-n(rs_rank/mkt_rs 룩백봉수)
  ★게이트·필터=none 이면 기존 동작 바이트동일(회귀 안전). 라이브 전략 무수정.

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
    _DAILY_CODE_RE,
    _build_strategy,
    _cartesian,
    _load_book,
    _load_daily_adj,
    _load_minute_data,
    _load_top_volume_daily,
    _load_top_volume_minute,
    _daily_minmax_dates,
    _quant_daily_connection,
    _rule_defaults,
    _resolve_rule_cls,
)
from scripts.exit_multiverse.portfolio_sim import run_portfolio  # noqa: E402
from scripts.entry_filters import FILTER_CHOICES, apply_entry_filter  # noqa: E402
from scripts.discovery.dynamic_risk import eff_sl, eff_tp  # noqa: E402

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
        if ret <= -eff_sl(position, params):
            return "stop_loss"
        if ret >= eff_tp(position, params):
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
    # 일봉 SSOT=robotrader_quant. 6자리 숫자 보통주만(지수·변형코드 제외).
    # quant 는 market_cap 이 사실상 전 종목 완비(robotrader 는 sparse ~98/256 였음).
    with _quant_daily_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            WITH px AS (
                SELECT stock_code, date, close,
                       LAG(close) OVER (PARTITION BY stock_code ORDER BY date) AS pc
                FROM daily_prices
                WHERE date >= %s AND date <= %s AND close > 0 AND stock_code ~ %s
            )
            SELECT DISTINCT stock_code FROM px
            WHERE pc > 0 AND (close - pc) / pc >= %s
            """,
            (start, end, _DAILY_CODE_RE, surge_threshold),
        )
        surged = {r[0] for r in cur.fetchall()}
        # 종목별 최신 market_cap (양수)
        cur.execute(
            """
            SELECT DISTINCT ON (stock_code) stock_code, market_cap
            FROM daily_prices
            WHERE market_cap > 0 AND date <= %s AND stock_code ~ %s
            ORDER BY stock_code, date DESC
            """,
            (end, _DAILY_CODE_RE),
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
    # 일봉 SSOT=robotrader_quant.
    with _quant_daily_connection() as conn:
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
# 국면 진입 게이트 (PIT) — core.regime.regime_classifier 그대로 호출(재구현 금지).
#
#   regime 시계열은 전 종목 공통(시장 레벨)이므로 1회 사전계산 후 진입봉에 매핑한다.
#   classify_daily/classify_intraday 는 각 봉 라벨이 그 봉(≤T/≤t)까지의 데이터로만
#   산출됨이 tests/regime/test_regime_no_lookahead.py 의 절단·미래 불변성으로 증명되어
#   있으므로, 전체 시계열을 1회 분류한 뒤 진입일 라벨을 조회해도 PIT-safe 다(절단값과 동일).
#
#   게이트 종류:
#     none         : 필터 없음(baseline)
#     exclude_bear : regime != bear 인 진입봉만 허용 (약세장 무방비 구제 검증 핵심)
#     bull_only    : regime == bull 인 진입봉만 허용 (가장 보수적)
#     trend_only   : (분봉) trendiness == trend 인 진입봉만 (추세전략용)
#     dir_match    : (분봉) trendiness==trend & direction==up (롱 방향 일치)
#
#   진입봉 i 의 라벨은 그 봉의 datetime 으로 조회. 라벨이 없으면(워밍업 등) 안전하게
#   '허용'(=신호 유지) 처리 — 게이트는 약세장 배제만 목적, 미지 구간 과잉배제 방지.
# ===========================================================================

GATE_CHOICES = ("none", "exclude_bear", "bull_only", "trend_only", "dir_match")
DAILY_GATES = ("none", "exclude_bear", "bull_only")
MINUTE_GATES = ("none", "trend_only", "dir_match")


def _build_daily_regime_map(start: str, end: str) -> Dict[pd.Timestamp, str]:
    """KOSPI 일봉(SSOT) + 전종목 %above MA120 breadth 로 일자→regime 라벨 1회 산출.

    classify_daily 그대로 호출. breadth panel 은 [start,end] 전 종목 close wide 패널.
    워밍업(MA120) 확보 위해 start 이전 룩백을 포함해 로드(라벨은 PIT 라 안전).
    """
    from core.regime.regime_classifier import classify_daily, DailyRegimeParams
    from db.connection import DatabaseConnection
    import datetime as _dt

    # MA120 + breadth120 워밍업을 위해 시작 이전 달력 ~400일(≈260 거래일) 룩백 로드.
    look_start = (_dt.date.fromisoformat(str(start)) - _dt.timedelta(days=400)).isoformat()
    # KOSPI 지수 라인은 robotrader 유지(전구간 보유, quant 엔 'KOSPI' 코드 없음).
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT date, close FROM daily_prices "
            "WHERE stock_code = 'KOSPI' AND date >= %s AND date <= %s ORDER BY date ASC",
            (look_start, end),
        )
        krows = cur.fetchall()
    if not krows:
        raise RuntimeError("daily_prices(robotrader) 에 KOSPI 지수 행이 없음 (국면 게이트 불가)")
    kospi = pd.Series({pd.Timestamp(r[0]): float(r[1]) for r in krows}, name="close").sort_index()
    # 전종목 breadth 패널은 정본 유니버스(robotrader_quant).
    panel = _load_breadth_panel(look_start, end)
    res = classify_daily(kospi, panel, DailyRegimeParams())
    return {pd.Timestamp(d): str(v) for d, v in res["regime"].items()}


def _load_breadth_panel(look_start: str, end: str) -> pd.DataFrame:
    """전종목 close wide 패널(index=date, columns=stock_code) — 정본 유니버스(quant).

    %above-MA120 breadth 산출용. 6자리 숫자 보통주만(지수·변형코드 제외),
    quant date(text) 불량 문자열은 coerce→dropna.
    """
    with _quant_daily_connection() as conn:
        panel_df = pd.read_sql(
            """
            SELECT date, stock_code, close FROM daily_prices
            WHERE date >= %s AND date <= %s AND close > 0 AND stock_code ~ %s
            """,
            conn, params=(look_start, end, _DAILY_CODE_RE),
        )
    panel_df = panel_df.assign(date=pd.to_datetime(panel_df["date"], format="mixed", errors="coerce"))
    panel_df = panel_df.dropna(subset=["date"])
    return (panel_df.pivot_table(index="date", columns="stock_code", values="close", aggfunc="last")
            .sort_index())


def _load_kospi_close(start: str, end: str, lookback_days: int = 400) -> pd.Series:
    """KOSPI 일봉 종가(SSOT, daily_prices) Series(index=Timestamp). mkt_rs 필터용.

    N일 수익률 워밍업 위해 start 이전 lookback_days 룩백 포함(라이브 PIT 와 동일 — 진입봉
    날짜 ≤t 슬라이스로만 사용). 행 없으면 빈 Series 반환(필터 호출자에서 drop 처리).
    """
    from db.connection import DatabaseConnection
    import datetime as _dt
    look_start = (_dt.date.fromisoformat(str(start)) - _dt.timedelta(days=lookback_days)).isoformat()
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT date, close FROM daily_prices "
            "WHERE stock_code = 'KOSPI' AND date >= %s AND date <= %s ORDER BY date ASC",
            (look_start, end),
        )
        rows = cur.fetchall()
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series({pd.Timestamp(r[0]): float(r[1]) for r in rows}, name="close").sort_index()


def _build_minute_regime_maps(
    period_data: Dict[str, Dict[str, pd.DataFrame]],
    period_minute_prev_close: Dict[str, Dict[str, float]],
) -> Dict[str, Dict[pd.Timestamp, dict]]:
    """구간별 datetime→{direction,trendiness,...} 라벨 맵. classify_intraday 그대로 호출.

    리샘플된 period_data(15분봉)를 일자별로 모아 long 패널을 만들고 당일 단위로 분류.
    각 분봉 라벨은 그 봉(≤t)까지 누적으로 산출됨(PIT, 장중 절단 불변성 증명).
    """
    from core.regime.regime_classifier import classify_intraday, IntradayRegimeParams
    out: Dict[str, Dict[pd.Timestamp, dict]] = {}
    params = IntradayRegimeParams()
    for pr, data in period_data.items():
        prev_close = period_minute_prev_close.get(pr, {})
        # long 패널 구성 (code 컬럼 포함)
        frames = []
        for code, df in data.items():
            g = df[["datetime", "open", "high", "low", "close", "volume"]].copy()
            g["stock_code"] = code
            frames.append(g)
        label_map: Dict[pd.Timestamp, dict] = {}
        if frames:
            longp = pd.concat(frames, ignore_index=True)
            longp["datetime"] = pd.to_datetime(longp["datetime"])
            longp["d"] = longp["datetime"].dt.date
            for _day, day_df in longp.groupby("d"):
                res = classify_intraday(day_df.drop(columns=["d"]), prev_close, params)
                for t, row in res.iterrows():
                    label_map[pd.Timestamp(t)] = {
                        "direction": str(row["direction"]),
                        "trendiness": str(row["trendiness"]),
                        "vol_class": str(row["vol_class"]),
                    }
        out[pr] = label_map
    return out


def _gate_allows_daily(label: Optional[str], gate: str) -> bool:
    if gate == "none" or label is None:
        return True
    if gate == "exclude_bear":
        return label != "bear"
    if gate == "bull_only":
        return label == "bull"
    return True  # 분봉 게이트는 일봉에 미적용 → 통과


def _gate_allows_minute(lab: Optional[dict], gate: str) -> bool:
    if gate == "none" or lab is None:
        return True
    if gate == "trend_only":
        return lab["trendiness"] == "trend"
    if gate == "dir_match":
        return lab["trendiness"] == "trend" and lab["direction"] == "up"
    return True  # 일봉 게이트는 분봉에 미적용 → 통과


def _filter_cache_daily(cache: Dict[str, List[int]], data: Dict[str, pd.DataFrame],
                        regime_map: Dict[pd.Timestamp, str], gate: str) -> Dict[str, List[int]]:
    if gate == "none":
        return cache
    out: Dict[str, List[int]] = {}
    for code, bars in cache.items():
        df = data[code]
        dts = df["datetime"]
        out[code] = [i for i in bars
                     if _gate_allows_daily(regime_map.get(pd.Timestamp(dts.iloc[i])), gate)]
    return out


def _filter_cache_minute(cache: Dict[str, List[int]], data: Dict[str, pd.DataFrame],
                         label_map: Dict[pd.Timestamp, dict], gate: str) -> Dict[str, List[int]]:
    if gate == "none":
        return cache
    out: Dict[str, List[int]] = {}
    for code, bars in cache.items():
        df = data[code]
        dts = df["datetime"]
        out[code] = [i for i in bars
                     if _gate_allows_minute(label_map.get(pd.Timestamp(dts.iloc[i])), gate)]
    return out


# ===========================================================================
# 1층 후보 스크린 게이트 (분봉 전용). 책의 2층 시스템: 일봉 후보 스크린 통과 종목·날짜에서만
#   분봉 진입 시그널을 인정. PIT: 일봉 D 신호 → D+1..D+window 거래일만 장중매매 유효.
# ===========================================================================

def _eligible_dates_from_signals(signal_idx: List[int], dates: list, window: int) -> set:
    """후보 신호 bar 인덱스 → 장중 매매 유효일 set. PIT: 신호일 D(인덱스 i) → D+1..D+window 거래일.
    dates = 해당 종목 일봉의 거래일(date) 리스트(인덱스 정렬). window>=1."""
    eligible: set = set()
    n = len(dates)
    for i in signal_idx:
        for w in range(1, window + 1):
            j = i + w
            if j < n:
                eligible.add(dates[j])
    return eligible


def _build_candidate_eligibility(uni, period_start, period_end, screen, window, rules_mod):
    """후보 스크린(일봉 룰) 통과 종목의 장중 매매 유효일 맵 {code: set(date)}.
    screen='none'이면 {}. 일봉을 룩백 포함 로드 → 룰 PIT 평가 → D+1..D+window 유효일."""
    if screen == "none":
        return {}
    import datetime as _dt
    cand_rule = _resolve_rule_cls(rules_mod, screen)()
    ps = _dt.date.fromisoformat(period_start)
    lb_start = (ps - _dt.timedelta(days=420)).isoformat()  # ≳200 거래일 룩백(A~I high_window=200)
    daily = _load_daily_adj(uni, lb_start, period_end)
    elig: Dict[str, set] = {}
    for code, df in daily.items():
        if df is None or len(df) == 0:
            continue
        dcol = "datetime" if "datetime" in df.columns else "date"
        dates = pd.to_datetime(df[dcol]).dt.date.tolist()
        sig_idx = [i for i in range(len(df)) if cand_rule.evaluate(df.iloc[:i + 1], {}).triggered]
        e = _eligible_dates_from_signals(sig_idx, dates, window)
        if e:
            elig[code] = e
    return elig


def _filter_cache_candidate(cache, data, elig_map):
    """분봉 신호 캐시를 후보 유효일(eligible date) 종목·날짜로만 게이팅. PIT(진입봉 날짜 기준)."""
    out: Dict[str, List[int]] = {}
    for code, bars in cache.items():
        elig = elig_map.get(code)
        if not elig:
            out[code] = []
            continue
        dts = pd.to_datetime(data[code]["datetime"])
        out[code] = [i for i in bars if dts.iloc[i].date() in elig]
    return out


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
# 국면 게이트 (게이트 차원). 라벨 맵은 1회 사전계산 후 워커에 전파.
_W_GATES: List[str] = ["none"]
_W_REGIME_MAP: Optional[Dict[pd.Timestamp, str]] = None              # daily: date→regime
_W_MINUTE_LABELS: Optional[Dict[str, Dict[pd.Timestamp, dict]]] = None  # minute: pr→{dt→label}
# 1층 후보 스크린 게이트 (분봉 전용). screen='none' 이면 기존 동작 바이트동일.
_W_CANDIDATE_MAPS: Optional[Dict[str, Dict[str, set]]] = None  # pr → {code: eligible date set}
_W_CANDIDATE_SCREEN: str = "none"
# 진입 필터 (필터 차원, scripts.entry_filters). 필터=none 일 때 기존 동작 바이트동일.
_W_FILTERS: List[str] = ["none"]
_W_FILTER_THRESHOLD: float = 0.5
_W_FILTER_N: int = 60
_W_KOSPI_CLOSE: Optional[pd.Series] = None  # mkt_rs 용 KOSPI 종가(date index)


def _eval_entry_minute(ro: Dict[str, Any]) -> List[dict]:
    """한 entry 조합 (minute): 캐시 1회/구간 → 게이트×exit×K 조합 row 리스트."""
    strat = _build_strategy(_W_RULE_CLS, _W_RULE_NAME, ro)
    # entry 조합당 구간별 캐시 1회 생성 (게이트·exit×K 재사용)
    caches: Dict[str, Dict[str, List[int]]] = {}
    for pr in _W_PERIODS:
        caches[pr] = _precompute_signals(_W_PERIOD_DATA[pr], strat, _W_WARMUP, "minute")
        if _W_CANDIDATE_SCREEN != "none":
            caches[pr] = _filter_cache_candidate(
                caches[pr], _W_PERIOD_DATA[pr], (_W_CANDIDATE_MAPS or {}).get(pr, {}))

    rows: List[dict] = []
    for gate in _W_GATES:
        # 게이트별 캐시 필터 (entry 신호는 동일, 진입봉 국면만 추가 게이팅)
        gcaches = {pr: _filter_cache_minute(caches[pr], _W_PERIOD_DATA[pr],
                                            (_W_MINUTE_LABELS or {}).get(pr, {}), gate)
                   for pr in _W_PERIODS}
        for filt in _W_FILTERS:
            # 진입 필터(no-lookahead). filt='none' 이면 gcaches 그대로.
            fcaches = {pr: apply_entry_filter(_W_PERIOD_DATA[pr], gcaches[pr], filt=filt,
                                              threshold=_W_FILTER_THRESHOLD, n=_W_FILTER_N,
                                              kospi_close=_W_KOSPI_CLOSE)
                       for pr in _W_PERIODS}
            for eo in _W_EXIT_COMBOS:
                params = dict(stop_loss_pct=eo["sl"], take_profit_pct=eo["tp"], max_hold_bars=eo["mh"])
                for K in _W_K_LIST:
                    per_period = {}
                    for pr in _W_PERIODS:
                        res = run_portfolio(
                            data=_W_PERIOD_DATA[pr], signal_cache=fcaches[pr], adapter=_ADAPTER,
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
                    row = {**{f"e_{k}": v for k, v in ro.items()}, "gate": gate, "filter": filt,
                           "sl": eo["sl"], "tp": eo["tp"], "mh": eo["mh"], "K": K,
                           "n_trades": ntr, "pos_periods": pos_periods, "n_periods": len(_W_PERIODS),
                           "sharpe": mean_sharpe, "pnl": mean_pnl, "overfit": overfit,
                           "max_concurrent": mxc, "n_skipped": nskip, "_entry_over": ro}
                    for pr in _W_PERIODS:
                        row[f"pnl_{pr}"] = per_period[pr]["pnl"]
                    rows.append(row)
    return rows


def _eval_entry_daily(ro: Dict[str, Any]) -> List[dict]:
    """한 entry 조합 (daily): 캐시 1회 → 게이트×exit×K 조합 row 리스트."""
    strat = _build_strategy(_W_RULE_CLS, _W_RULE_NAME, ro)
    cache = _precompute_signals(_W_DATA, strat, _W_WARMUP, "daily")

    rows: List[dict] = []
    for gate in _W_GATES:
        gcache = _filter_cache_daily(cache, _W_DATA, _W_REGIME_MAP or {}, gate)
        for filt in _W_FILTERS:
            # 진입 필터 적용(no-lookahead). filt='none' 이면 gcache 그대로(동일 객체).
            fcache = apply_entry_filter(_W_DATA, gcache, filt=filt,
                                        threshold=_W_FILTER_THRESHOLD, n=_W_FILTER_N,
                                        kospi_close=_W_KOSPI_CLOSE)
            for eo in _W_EXIT_COMBOS:
                params = dict(stop_loss_pct=eo["sl"], take_profit_pct=eo["tp"], max_hold_bars=eo["mh"])
                for K in _W_K_LIST:
                    res = run_portfolio(
                        data=_W_DATA, signal_cache=fcache, adapter=_ADAPTER, params=params,
                        turnover=_W_TURNOVER, initial_capital=_W_INITIAL, max_positions=K,
                        max_per_stock=_W_MAX_PER_STOCK,
                    )
                    m = _portfolio_metrics(res, _W_INITIAL)
                    row = {**{f"e_{k}": v for k, v in ro.items()}, "gate": gate, "filter": filt,
                           "sl": eo["sl"], "tp": eo["tp"], "mh": eo["mh"], "K": K,
                           "n_trades": m["n_trades"], "sharpe": m["sharpe"], "pnl": m["pnl"],
                           "calmar": m["calmar"], "hit": m["hit"], "max_dd": m["max_dd"],
                           "max_concurrent": m["max_concurrent"], "n_skipped": m["n_skipped"],
                           "_entry_over": ro}
                    rows.append(row)
    return rows


# --- 병렬 워커 initializer / wrapper ---

def _winit_minute(rule_cls, rule_name, warmup, periods, period_data, period_turnover,
                  exit_combos, k_list, max_per_stock, initial, gates, minute_labels,
                  filters, filter_threshold, filter_n, kospi_close,
                  candidate_maps, candidate_screen):
    global _W_RULE_CLS, _W_RULE_NAME, _W_WARMUP, _W_PERIODS, _W_PERIOD_DATA
    global _W_PERIOD_TURNOVER, _W_EXIT_COMBOS, _W_K_LIST, _W_MAX_PER_STOCK, _W_INITIAL
    global _W_GATES, _W_MINUTE_LABELS
    global _W_FILTERS, _W_FILTER_THRESHOLD, _W_FILTER_N, _W_KOSPI_CLOSE
    global _W_CANDIDATE_MAPS, _W_CANDIDATE_SCREEN
    _W_RULE_CLS = rule_cls; _W_RULE_NAME = rule_name; _W_WARMUP = warmup
    _W_PERIODS = periods; _W_PERIOD_DATA = period_data; _W_PERIOD_TURNOVER = period_turnover
    _W_EXIT_COMBOS = exit_combos; _W_K_LIST = k_list
    _W_MAX_PER_STOCK = max_per_stock; _W_INITIAL = initial
    _W_GATES = gates; _W_MINUTE_LABELS = minute_labels
    _W_FILTERS = filters; _W_FILTER_THRESHOLD = filter_threshold
    _W_FILTER_N = filter_n; _W_KOSPI_CLOSE = kospi_close
    _W_CANDIDATE_MAPS = candidate_maps; _W_CANDIDATE_SCREEN = candidate_screen


def _winit_daily(rule_cls, rule_name, warmup, data, turnover, exit_combos, k_list,
                 max_per_stock, initial, gates, regime_map,
                 filters, filter_threshold, filter_n, kospi_close):
    global _W_RULE_CLS, _W_RULE_NAME, _W_WARMUP, _W_DATA, _W_TURNOVER
    global _W_EXIT_COMBOS, _W_K_LIST, _W_MAX_PER_STOCK, _W_INITIAL
    global _W_GATES, _W_REGIME_MAP
    global _W_FILTERS, _W_FILTER_THRESHOLD, _W_FILTER_N, _W_KOSPI_CLOSE
    _W_RULE_CLS = rule_cls; _W_RULE_NAME = rule_name; _W_WARMUP = warmup
    _W_DATA = data; _W_TURNOVER = turnover
    _W_EXIT_COMBOS = exit_combos; _W_K_LIST = k_list
    _W_MAX_PER_STOCK = max_per_stock; _W_INITIAL = initial
    _W_GATES = gates; _W_REGIME_MAP = regime_map
    _W_FILTERS = filters; _W_FILTER_THRESHOLD = filter_threshold
    _W_FILTER_N = filter_n; _W_KOSPI_CLOSE = kospi_close


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

def _combo_label(entry_over: Dict[str, Any], sl, tp, mh, K, gate: str = "none",
                 filt: str = "none") -> str:
    parts = [f"{k}={v}" for k, v in sorted(entry_over.items())]
    parts += [f"sl={sl}", f"tp={tp}", f"mh={mh}", f"K={K}", f"gate={gate}", f"filter={filt}"]
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
    p.add_argument("--regime-gate", nargs="+", default=["none"], dest="regime_gate",
                   choices=list(GATE_CHOICES),
                   help="PIT 국면 진입게이트(차원). 일봉: none/exclude_bear/bull_only, "
                        "분봉: none/trend_only/dir_match. 여러 값=게이트 차원 스윕.")
    p.add_argument("--entry-filter", nargs="+", default=["none"], dest="entry_filter",
                   choices=list(FILTER_CHOICES),
                   help="PIT 진입 필터(차원, scripts.entry_filters). none=baseline(바이트동일). "
                        "rs_rank=N봉수익률 횡단면 백분위>=임계, mkt_rs=KOSPI 대비 아웃퍼폼, "
                        "adx=ADX(14)>=임계, ma_slope=종가>MA50 & MA50기울기>0. 여러 값=필터 차원 스윕.")
    p.add_argument("--filter-threshold", type=float, default=0.5, dest="filter_threshold",
                   help="rs_rank 백분위 컷(0~1) 또는 adx 컷(예 20/25). mkt_rs/ma_slope 는 무시.")
    p.add_argument("--filter-n", type=int, default=60, dest="filter_n",
                   help="rs_rank/mkt_rs 의 수익률 룩백 봉수 N (기본 60).")
    p.add_argument("--candidate-screen", default="none",
                   help="분봉 진입을 1층 일봉 후보 스크린 통과 종목·날짜로만 게이팅 "
                        "(none 또는 일봉 룰 .name 예: envelope_200d_high). 분봉 전용.")
    p.add_argument("--candidate-window", type=int, default=3,
                   help="후보 신호일 D 이후 장중 매매 유효 거래일수(D+1..D+window). 기본 3.")
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

    # 게이트 차원: 입력 보존 순서, 중복 제거, granularity 적합성 검증.
    gates: List[str] = list(dict.fromkeys(args.regime_gate))
    allowed_gates = MINUTE_GATES if granularity == "minute" else DAILY_GATES
    bad = [g for g in gates if g not in allowed_gates]
    if bad:
        p.error(f"--regime-gate {bad} 는 {granularity} 트랙에 부적합. 가능: {list(allowed_gates)}")
    LOG.info(f"regime gates (dim): {gates}")

    # 필터 차원: 입력 보존 순서, 중복 제거.
    filters: List[str] = list(dict.fromkeys(args.entry_filter))
    LOG.info(f"entry filters (dim): {filters} (threshold={args.filter_threshold} n={args.filter_n})")

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

        # 1층 후보 스크린(일봉 룰) 유효일 맵 1회 사전계산(screen≠none 일 때만). PIT.
        candidate_screen = args.candidate_screen
        candidate_maps: Dict[str, Dict[str, set]] = {}
        if candidate_screen != "none":
            for pr in periods:
                cstart, cend = MINUTE_PERIODS[pr]
                uni_pr = list(period_data[pr].keys())
                cmap = _build_candidate_eligibility(uni_pr, cstart, cend, candidate_screen,
                                                    args.candidate_window, rules_mod)
                candidate_maps[pr] = cmap
                n_days = sum(len(v) for v in cmap.values())
                LOG.info(f"period={pr} candidate-screen={candidate_screen} "
                         f"window={args.candidate_window}: eligible_stocks={len(cmap)} "
                         f"stock_days={n_days}")

        # 분봉 국면 라벨 1회 사전계산(게이트≠none 일 때만). bias(갭)는 게이트에 불필요 →
        # prev_close 미전달(flat). trend_only/dir_match 는 trendiness/direction 만 사용.
        minute_labels: Dict[str, Dict[pd.Timestamp, dict]] = {}
        if any(g != "none" for g in gates):
            minute_labels = _build_minute_regime_maps(period_data, {pr: {} for pr in periods})
            for pr in periods:
                n_trend = sum(1 for v in minute_labels.get(pr, {}).values()
                              if v["trendiness"] == "trend")
                LOG.info(f"period={pr} intraday-regime bars={len(minute_labels.get(pr, {}))} "
                         f"trend_bars={n_trend}")

        # mkt_rs 필터용 KOSPI 종가(분봉 트랙은 진입봉 날짜로 일봉수익률 매핑).
        kospi_close_m: Optional[pd.Series] = None
        if "mkt_rs" in filters:
            mn_dates = [MINUTE_PERIODS[pr][0] for pr in periods]
            mx_dates = [MINUTE_PERIODS[pr][1] for pr in periods]
            kospi_close_m = _load_kospi_close(min(mn_dates), max(mx_dates))
            LOG.info(f"mkt_rs filter (minute): loaded KOSPI close rows={len(kospi_close_m)}")

        tasks = [(i, ro) for i, ro in enumerate(entry_combos)]
        rows = _run_entry_combos(
            tasks, args.workers, _worker_minute,
            _winit_minute, (rule_cls, rule_name, warmup, periods, period_data,
                            period_turnover, exit_combos, args.k_list,
                            args.max_per_stock, args.initial_capital, gates, minute_labels,
                            filters, args.filter_threshold, args.filter_n, kospi_close_m,
                            candidate_maps, candidate_screen),
            lambda t: _eval_entry_minute_seq(t[1], rule_cls, rule_name, warmup, periods,
                                             period_data, period_turnover, exit_combos,
                                             args.k_list, args.max_per_stock, args.initial_capital,
                                             gates, minute_labels, filters, args.filter_threshold,
                                             args.filter_n, kospi_close_m,
                                             candidate_maps, candidate_screen),
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

        # 일봉 국면 라벨 1회 사전계산(게이트≠none 일 때만). KOSPI SSOT + 전종목 breadth.
        regime_map: Dict[pd.Timestamp, str] = {}
        if any(g != "none" for g in gates):
            regime_map = _build_daily_regime_map(start, end)
            from collections import Counter
            cnt = Counter(v for k, v in regime_map.items()
                          if pd.Timestamp(start) <= k <= pd.Timestamp(end))
            LOG.info(f"daily-regime label dist in window: {dict(cnt)}")

        # mkt_rs 필터용 KOSPI 종가 1회 로드(요청 시에만).
        kospi_close: Optional[pd.Series] = None
        if "mkt_rs" in filters:
            kospi_close = _load_kospi_close(start, end)
            LOG.info(f"mkt_rs filter: loaded KOSPI close rows={len(kospi_close)}")

        tasks = [(i, ro) for i, ro in enumerate(entry_combos)]
        rows = _run_entry_combos(
            tasks, args.workers, _worker_daily,
            _winit_daily, (rule_cls, rule_name, warmup, data, turnover, exit_combos,
                           args.k_list, args.max_per_stock, args.initial_capital,
                           gates, regime_map, filters, args.filter_threshold,
                           args.filter_n, kospi_close),
            lambda t: _eval_entry_daily_seq(t[1], rule_cls, rule_name, warmup, data, turnover,
                                            exit_combos, args.k_list, args.max_per_stock,
                                            args.initial_capital, gates, regime_map,
                                            filters, args.filter_threshold, args.filter_n,
                                            kospi_close),
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
        print(f"{'rank':>4} {'combo':<64} {'ntr':>5} {'pos/N':>6} {'mSharpe':>8} "
              f"{'mPnl':>8} {'mxc':>4} {'skip':>6}  flag")
        for i, r in enumerate(topk, 1):
            label = _combo_label(r["_entry_over"], r["sl"], r["tp"], r["mh"], r["K"], r["gate"], r["filter"])
            flag = "[OVERFIT]" if r["overfit"] else ""
            print(f"{i:>4} {label:<64} {r['n_trades']:>5} "
                  f"{r['pos_periods']}/{r['n_periods']:>3} {r['sharpe']:>8.3f} "
                  f"{r['pnl']:>8.4f} {r['max_concurrent']:>4} {r['n_skipped']:>6}  {flag}")
    else:
        print(f"{'rank':>4} {'combo':<64} {'ntr':>5} {'sharpe':>8} {'pnl':>9} "
              f"{'calmar':>7} {'hit':>6} {'maxdd':>7} {'mxc':>4} {'skip':>6}")
        for i, r in enumerate(topk, 1):
            label = _combo_label(r["_entry_over"], r["sl"], r["tp"], r["mh"], r["K"], r["gate"], r["filter"])
            print(f"{i:>4} {label:<64} {r['n_trades']:>5} {r['sharpe']:>8.3f} "
                  f"{r['pnl']:>9.4f} {r['calmar']:>7.2f} {r['hit']:>6.2%} "
                  f"{r['max_dd']:>7.2%} {r['max_concurrent']:>4} {r['n_skipped']:>6}")

    # --- best vs baseline ---
    defaults = _rule_defaults(rule_cls)
    baseline_entry_over = {k: defaults[k] for k in entry_grid.keys()}
    bl_sl = exit_grid["sl"][0]; bl_tp = exit_grid["tp"][0]; bl_mh = exit_grid["mh"][0]
    bl_K = args.k_list[0]
    bl_gate = gates[0]
    bl_filter = filters[0]

    def _match(r):
        return (r["_entry_over"] == baseline_entry_over and r["sl"] == bl_sl
                and r["tp"] == bl_tp and r["mh"] == bl_mh and r["K"] == bl_K
                and r["gate"] == bl_gate and r["filter"] == bl_filter)

    baseline = next((r for r in rows if _match(r)), None)
    best = rows[0] if rows else None
    print("\n--- BEST vs BASELINE ---")
    if best is not None:
        print(f"BEST    : {_combo_label(best['_entry_over'], best['sl'], best['tp'], best['mh'], best['K'], best['gate'], best['filter'])}")
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
                                baseline["mh"], baseline["K"], baseline["gate"], baseline["filter"])
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
                           period_turnover, exit_combos, k_list, max_per_stock, initial,
                           gates, minute_labels, filters, filter_threshold, filter_n,
                           kospi_close, candidate_maps, candidate_screen):
    global _W_RULE_CLS, _W_RULE_NAME, _W_WARMUP, _W_PERIODS, _W_PERIOD_DATA
    global _W_PERIOD_TURNOVER, _W_EXIT_COMBOS, _W_K_LIST, _W_MAX_PER_STOCK, _W_INITIAL
    global _W_GATES, _W_MINUTE_LABELS
    global _W_FILTERS, _W_FILTER_THRESHOLD, _W_FILTER_N, _W_KOSPI_CLOSE
    global _W_CANDIDATE_MAPS, _W_CANDIDATE_SCREEN
    _W_RULE_CLS = rule_cls; _W_RULE_NAME = rule_name; _W_WARMUP = warmup
    _W_PERIODS = periods; _W_PERIOD_DATA = period_data; _W_PERIOD_TURNOVER = period_turnover
    _W_EXIT_COMBOS = exit_combos; _W_K_LIST = k_list
    _W_MAX_PER_STOCK = max_per_stock; _W_INITIAL = initial
    _W_GATES = gates; _W_MINUTE_LABELS = minute_labels
    _W_FILTERS = filters; _W_FILTER_THRESHOLD = filter_threshold
    _W_FILTER_N = filter_n; _W_KOSPI_CLOSE = kospi_close
    _W_CANDIDATE_MAPS = candidate_maps; _W_CANDIDATE_SCREEN = candidate_screen
    return _eval_entry_minute(ro)


def _eval_entry_daily_seq(ro, rule_cls, rule_name, warmup, data, turnover, exit_combos,
                          k_list, max_per_stock, initial, gates, regime_map,
                          filters, filter_threshold, filter_n, kospi_close):
    global _W_RULE_CLS, _W_RULE_NAME, _W_WARMUP, _W_DATA, _W_TURNOVER
    global _W_EXIT_COMBOS, _W_K_LIST, _W_MAX_PER_STOCK, _W_INITIAL
    global _W_GATES, _W_REGIME_MAP
    global _W_FILTERS, _W_FILTER_THRESHOLD, _W_FILTER_N, _W_KOSPI_CLOSE
    _W_RULE_CLS = rule_cls; _W_RULE_NAME = rule_name; _W_WARMUP = warmup
    _W_DATA = data; _W_TURNOVER = turnover
    _W_EXIT_COMBOS = exit_combos; _W_K_LIST = k_list
    _W_MAX_PER_STOCK = max_per_stock; _W_INITIAL = initial
    _W_GATES = gates; _W_REGIME_MAP = regime_map
    _W_FILTERS = filters; _W_FILTER_THRESHOLD = filter_threshold
    _W_FILTER_N = filter_n; _W_KOSPI_CLOSE = kospi_close
    return _eval_entry_daily(ro)


if __name__ == "__main__":
    main()
