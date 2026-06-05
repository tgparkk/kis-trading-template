"""홍용찬 실전 퀀트투자 일봉 백테스트 (4선 저밸류 PER+PBR+PCR+PSR + 소형주 하위20% + 성장/마진/부채 게이트).

usage:
  python scripts/run_hongyongchan.py --variant Q --all-modes
  python scripts/run_hongyongchan.py --variant Q --all-modes --quarterly
  python scripts/run_hongyongchan.py --variant K --all-modes              # 문병로 대조(연 1회 보유)
  python scripts/run_hongyongchan.py --variant Q --all-modes --april-only
  python scripts/run_hongyongchan.py --variant B --mode single --rule value4_low

데이터: daily_prices (OHLC adj_factor 적용 수정주가; market_cap 은 레벨값 → adj 미적용)
universe: financial_statements DISTINCT stock_code (131종목, 전부 일봉 보유 — 문병로와 동일, 책간 비교성 유지)
재무: point-in-time fund 조인 (effective_date=report_date+105d ≤ 거래일)

4선 저밸류 (모두 cheap=low, POR 제거 — 문병로 vc_score에서 POR 빼고 PCR 유지):
      PBR = pbr                                     (pbr>0)
      PER = per                                     (per>0)
      PSR = (market_cap/1e8) / revenue              (revenue>0, mc>0)
      PCR = (market_cap/1e8) / operating_cash_flow  (ocf>0, mc>0; pcr<=PCR_CAP)
게이트(보조, hong_rank 전용):
      흑자      = operating_profit>0 AND net_income>0
      성장YoY   = revenue_t/revenue_{t-1}-1 > 0  OR  net_income_t/net_income_{t-1}-1 > 0 (연간 차분)
      마진      = operating_margin >= OPM_MIN (있을 때만; skip-missing)
      ROE       = roe >= ROE_MIN (있을 때만; skip-missing)
      부채      = debt_ratio <= DEBT_MAX (있을 때만; skip-missing)

순위: 거래일별 적격(4선 교집합)에서
      각 팩터 백분위(cheap=high) 평균 → v4_score → dense ordinal v4_rank(1=최저평가)
      market_cap 하위 20% 게이트 → 그 부분집합 v4_score 내림차순 → dense ordinal smallv4_rank
      소형주20% ∩ 흑자 ∩ 성장YoY>0 ∩ 마진/ROE/부채 게이트 부분집합 → v4_score 내림차순 → hong_rank
청산: Variant Q (sl 20% / tp 99%(off) / mh 63, trail 없음, 분기 보유 근사) ·
      K (sl 17.5% / tp 99%(off) / mh 250 — 문병로 연 1회 대조) · B (sl 8% / tp 12% / mh 20)
리밸런싱 게이트(옵션):
      --quarterly : 진입 신호를 분기 첫 영업일 근사(month ∈ {1,4,7,10} & 종목별 그 달 첫 거래일)에만 허용.
      --april-only: 진입 신호를 4월 영업일에만 허용.
      (report_date 91%가 연간(12월)이라 분기 리밸런싱은 캘린더 근사 — 한계 명시.)

⚠️ 배당 전략 제외(사장님 방침). dividend_yield 백필/룰 미구현.
⚠️ market_cap 5년 백필(2021~2026) → 다년·다국면 검증 가능.
⚠️ universe 131 = 문병로와 동일 → 책간 비교성 유지(리포트 명시).
⚠️ 게이트 지표(roe/opm/debt) 부분 커버리지 → "데이터 있는 종목만 적용, 없으면 통과"(skip-missing).
⚠️ 반드시 RoboTrader_template/ cwd 에서 실행 (상대경로 reports/...).
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.books.hongyongchan.rules import ALL_RULES
from strategies.books.hongyongchan.strategy import BOOK_META, build_strategy

LOG = logging.getLogger("hongyongchan")

VARIANT_PARAMS = {
    "Q": dict(stop_loss_pct=0.20, take_profit_pct=0.99, max_hold_bars=63, trail_ma=None),
    "K": dict(stop_loss_pct=0.175, take_profit_pct=0.99, max_hold_bars=250, trail_ma=None),
    "B": dict(stop_loss_pct=0.08, take_profit_pct=0.12, max_hold_bars=20, trail_ma=None),
}

# 재무 컬럼 (financial_statements) — 4선 + 게이트에 필요한 것만 (POR 미사용, dividend_yield 제외)
_FS_NUM_COLS = [
    "operating_cash_flow",
    "per", "pbr", "revenue",
    "operating_profit", "net_income",
    "roe", "operating_margin", "debt_ratio",
]

LAG_DAYS = 105       # 한국 사업보고서 공시 지연 → effective_date = report_date + 105d
PCR_CAP = 100.0      # PCR 분모(ocf) 작을 때 폭주 캡
SMALLCAP_PCTL = 20.0  # 소형주 게이트: market_cap 하위 20% (홍용찬 명시값; 문병로 40%보다 타이트)
MIN_ELIGIBLE = 10    # 룰 min_eligible 와 정합 (로깅/sanity 용)

# hong_combo 게이트 임계 (skip-missing: 지표 없으면 통과)
ROE_MIN = 0.0        # ROE 양호(흑자성 자본수익) — 0 이상
OPM_MIN = 0.0        # 영업이익률 양호 — 0 이상
DEBT_MAX = 200.0     # 부채비율 상한(%) — 200% 이하

# daily_prices.market_cap 은 원(won) 단위, financial_statements 컬럼은 억원 단위.
MARKET_CAP_UNIT_DIVISOR = 1e8


def _load_fundamentals_universe() -> List[str]:
    """financial_statements의 DISTINCT stock_code (전부 일봉 보유)."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT stock_code FROM financial_statements ORDER BY stock_code")
        rows = cur.fetchall()
    return [r[0] for r in rows]


def _load_daily_adj(stock_codes: List[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
    """종목별 daily_prices 로드.

    OHLC 는 adj_factor 적용 수정주가, market_cap 은 레벨값이므로 adj 미적용(그대로).
    반환 df 컬럼: datetime, open, high, low, close, volume, market_cap.
    """
    # 일봉 SSOT=robotrader_quant (market_cap 완비 → robotrader 6개월 제약 해소).
    # 펀더멘털/유니버스(financial_statements)는 robotrader 유지.
    from scripts.book_param_multiverse import _quant_daily_connection
    out: Dict[str, pd.DataFrame] = {}
    with _quant_daily_connection() as conn:
        cur = conn.cursor()
        for code in stock_codes:
            cur.execute("""
                SELECT date, open, high, low, close, volume, adj_factor, market_cap
                FROM daily_prices
                WHERE stock_code = %s
                  AND date >= %s AND date <= %s
                ORDER BY date ASC
            """, (code, start, end))
            rows = cur.fetchall()
            if not rows or len(rows) < 30:
                continue
            df = pd.DataFrame(
                rows,
                columns=["date", "open", "high", "low", "close", "volume", "adj_factor", "market_cap"],
            )
            df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
            df = df.dropna(subset=["date"])
            if len(df) < 30:
                continue
            for col in ["open", "high", "low", "close", "volume", "market_cap"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            # quant close 는 이미 분할조정된 연속 시세 → adj_factor 곱하지 않음(곱하면 분할일 가짜 절벽).
            df = df.dropna(subset=["open", "high", "low", "close"])
            df["datetime"] = df["date"]
            out[code] = df[["datetime", "open", "high", "low", "close", "volume", "market_cap"]].reset_index(drop=True)
    return out


def _load_fundamentals_timeseries(stock_codes: List[str]) -> Dict[str, List[dict]]:
    """종목별 재무 시계열 로드.

    Returns:
        dict[code] -> report_date ASC 정렬된 row dict 리스트.
        report_date 는 date 로 파싱(malformed VARCHAR 는 스킵), 숫자 컬럼은 float(NULL→None).
    """
    from db.connection import DatabaseConnection
    out: Dict[str, List[dict]] = {}
    cols = ", ".join(["report_date"] + _FS_NUM_COLS)
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        for code in stock_codes:
            cur.execute(f"""
                SELECT {cols}
                FROM financial_statements
                WHERE stock_code = %s
                ORDER BY report_date ASC
            """, (code,))
            rows = cur.fetchall()
            if not rows:
                continue
            parsed: List[dict] = []
            for r in rows:
                rd_raw = r[0]
                rd = pd.to_datetime(rd_raw, errors="coerce")
                if pd.isna(rd):
                    continue
                rec: dict = {"report_date": rd.date()}
                for j, col in enumerate(_FS_NUM_COLS, start=1):
                    val = r[j]
                    if val is None:
                        rec[col] = None
                    else:
                        try:
                            fv = float(val)
                            rec[col] = None if math.isnan(fv) else fv
                        except (TypeError, ValueError):
                            rec[col] = None
                parsed.append(rec)
            parsed.sort(key=lambda x: x["report_date"])
            if parsed:
                out[code] = parsed
    return out


def _build_fund_by_idx(df: pd.DataFrame, fs_rows: List[dict]) -> List[Optional[dict]]:
    """df 각 행에 대응하는 point-in-time 4선 + 게이트 fund dict 리스트 (no-lookahead).

    각 거래일 D 에 대해:
      effective_date(row) = report_date + 105d
      fs_curr = effective_date ≤ D 인 행 中 report_date 최대
      market_cap = df.iloc[i]["market_cap"]  (그날 레벨값), market_cap_eok = mc/1e8
      pbr = pbr                                   (pbr>0)
      per = per                                   (per>0)
      psr = market_cap_eok / revenue             (revenue>0, mc>0)
      pcr = market_cap_eok / operating_cash_flow (ocf>0, mc>0; pcr<=PCR_CAP)
      흑자 = operating_profit>0 AND net_income>0
      성장YoY = revenue/net_income 전년 대비 증가(직전 연간 report_date 차분)
      게이트 지표 = roe / operating_margin / debt_ratio (present 면 값, 없으면 None → skip-missing)

    eligible_value = pbr/per/psr/pcr 4개 모두 유효(present & valid).
    하나라도 None/가드 위반이면 해당 팩터 None, eligible_value=False.
    fs_curr 없으면 그 봉 fund=None.
    """
    n = len(df)
    if not fs_rows:
        return [None] * n

    # 성장 YoY 사전계산: 같은 종목 직전 연간 report_date 대비 차분.
    # report_date ASC 정렬된 fs_rows 에서 직전 행의 revenue/net_income 과 비교.
    prev_rev: Dict[date, Optional[float]] = {}
    prev_ni: Dict[date, Optional[float]] = {}
    last_rev: Optional[float] = None
    last_ni: Optional[float] = None
    for row in fs_rows:  # ASC
        rd = row["report_date"]
        prev_rev[rd] = last_rev
        prev_ni[rd] = last_ni
        if row.get("revenue") is not None:
            last_rev = row.get("revenue")
        if row.get("net_income") is not None:
            last_ni = row.get("net_income")

    eff = [(row["report_date"] + timedelta(days=LAG_DAYS), row) for row in fs_rows]
    eff.sort(key=lambda x: x[0])

    fund_by_idx: List[Optional[dict]] = []
    ptr = 0
    curr: Optional[dict] = None

    for i in range(n):
        d = df.iloc[i]["datetime"]
        d = d.date() if hasattr(d, "date") else pd.to_datetime(d).date()

        # effective_date ≤ D 인 행들을 소비하며 가장 최신(report_date 최대) 선택
        while ptr < len(eff) and eff[ptr][0] <= d:
            cand = eff[ptr][1]
            if curr is None or cand["report_date"] >= curr["report_date"]:
                curr = cand
            ptr += 1

        if curr is None:
            fund_by_idx.append(None)
            continue

        op = curr.get("operating_profit")
        ni = curr.get("net_income")
        ocf = curr.get("operating_cash_flow")
        per_v = curr.get("per")
        pbr_v = curr.get("pbr")
        revenue = curr.get("revenue")
        roe_v = curr.get("roe")
        opm_v = curr.get("operating_margin")
        debt_v = curr.get("debt_ratio")

        mc_raw = df.iloc[i]["market_cap"]
        try:
            mc = float(mc_raw)
        except (TypeError, ValueError):
            mc = float("nan")

        pbr: Optional[float] = None
        per: Optional[float] = None
        psr: Optional[float] = None
        pcr: Optional[float] = None

        mc_ok = not (mc is None or math.isnan(mc) or mc <= 0)
        mc_eok = mc / MARKET_CAP_UNIT_DIVISOR if mc_ok else None

        # PBR
        if pbr_v is not None and pbr_v > 0:
            pbr = pbr_v
        # PER
        if per_v is not None and per_v > 0:
            per = per_v
        # PSR
        if mc_ok and revenue is not None and revenue > 0:
            psr = mc_eok / revenue
        # PCR (분모 ocf>0, 작을 때 폭주 캡)
        if mc_ok and ocf is not None and ocf > 0:
            pcr_calc = mc_eok / ocf
            if pcr_calc <= PCR_CAP:
                pcr = pcr_calc

        eligible_value = (
            pbr is not None and per is not None
            and psr is not None and pcr is not None
        )

        # 게이트 평가 (hong_rank 용)
        profitable = (op is not None and op > 0 and ni is not None and ni > 0)

        # 성장 YoY: revenue 또는 net_income 증가
        cur_rd = curr["report_date"]
        pr = prev_rev.get(cur_rd)
        pn = prev_ni.get(cur_rd)
        growth_pos = False
        if revenue is not None and pr is not None and pr > 0 and revenue > pr:
            growth_pos = True
        if ni is not None and pn is not None and pn > 0 and ni > pn:
            growth_pos = True

        # 마진/ROE/부채 게이트 (skip-missing: 없으면 통과)
        roe_ok = (roe_v is None) or (roe_v >= ROE_MIN)
        opm_ok = (opm_v is None) or (opm_v >= OPM_MIN)
        debt_ok = (debt_v is None) or (debt_v <= DEBT_MAX)

        gate_pass = profitable and growth_pos and roe_ok and opm_ok and debt_ok

        fund_by_idx.append({
            "market_cap": None if (mc is None or math.isnan(mc)) else mc,
            "pbr": pbr,
            "per": per,
            "psr": psr,
            "pcr": pcr,
            "eligible_value": eligible_value,
            "gate_pass": gate_pass,
            "profitable": profitable,
            "growth_pos": growth_pos,
        })

    return fund_by_idx


def _build_cross_sectional_ranks(
    data: Dict[str, pd.DataFrame],
    fund_by_idx_map: Dict[str, List[Optional[dict]]],
):
    """횡단면 순위 precompute (no-lookahead: 거래일 D 데이터만 사용).

    거래일 D 별로:
    - 4선 적격(eligible_value==True) 교집합에서:
        각 팩터 백분위(cheap=high): pct = 1 - (rank_asc-1)/(N-1)  (N==1 → 1.0)
        v4_score = mean(pct_pbr, pct_per, pct_psr, pct_pcr)
        v4_rank  = v4_score 내림차순 dense ordinal (1=best/cheapest)
        smallv4_rank = market_cap 하위 20% 게이트 부분집합 v4_score 내림차순 dense ordinal
        hong_rank    = 소형주20% ∩ gate_pass 부분집합 v4_score 내림차순 dense ordinal
    - n_eligible = 4선 적격 교집합 수.

    Returns:
        v4_by_idx_map / sv_by_idx_map / hong_by_idx_map: dict[code] -> list aligned to df rows
        nelig_by_idx_map: dict[code] -> list aligned to df rows (int n_eligible or 0)
        nelig_by_date: dict[date] -> int (로깅용)
        nhong_by_date: dict[date] -> int (hong 게이트 통과 수, 로깅용)
        psr_all / pcr_all: list[float] (분포 sanity 로깅용)
        n_eligible_with_pcr: int (4선 적격 표본수 = PCR 실제 반영 종목·시점 수)
    """
    elig_by_date: Dict[date, List[dict]] = defaultdict(list)   # 4선 교집합
    psr_all: List[float] = []
    pcr_all: List[float] = []

    for code, df in data.items():
        fbi = fund_by_idx_map.get(code, [])
        for i in range(len(df)):
            fund = fbi[i] if i < len(fbi) else None
            if fund is None:
                continue
            d = df.iloc[i]["datetime"]
            d = d.date() if hasattr(d, "date") else pd.to_datetime(d).date()

            if not fund.get("eligible_value"):
                continue
            pbr = fund.get("pbr")
            per = fund.get("per")
            psr = fund.get("psr")
            pcr = fund.get("pcr")
            mc = fund.get("market_cap")
            if (pbr is None or per is None or psr is None
                    or pcr is None or mc is None):
                continue
            elig_by_date[d].append({
                "code": code, "pbr": pbr, "per": per, "psr": psr,
                "pcr": pcr, "market_cap": mc,
                "gate_pass": bool(fund.get("gate_pass")),
            })
            psr_all.append(psr)
            pcr_all.append(pcr)

    n_eligible_with_pcr = sum(len(v) for v in elig_by_date.values())

    v4_by_date: Dict[date, Dict[str, int]] = {}
    sv_by_date: Dict[date, Dict[str, int]] = {}
    hong_by_date: Dict[date, Dict[str, int]] = {}
    nelig_by_date: Dict[date, int] = {}
    nhong_by_date: Dict[date, int] = {}

    def _pct_cheap(values: List[float]) -> List[float]:
        """오름차순 rank 기반 백분위(cheap=low → high pct). pct = 1 - (rank_asc-1)/(N-1)."""
        ne = len(values)
        if ne == 1:
            return [1.0]
        order = sorted(range(ne), key=lambda k: values[k])  # 오름차순 (작을수록 cheap)
        rank_asc = [0] * ne
        for pos, k in enumerate(order, start=1):
            rank_asc[k] = pos
        return [1.0 - (rank_asc[k] - 1) / (ne - 1) for k in range(ne)]

    for d, items in elig_by_date.items():
        ne = len(items)
        nelig_by_date[d] = ne
        if ne == 0:
            continue

        pct_pbr = _pct_cheap([it["pbr"] for it in items])
        pct_per = _pct_cheap([it["per"] for it in items])
        pct_psr = _pct_cheap([it["psr"] for it in items])
        pct_pcr = _pct_cheap([it["pcr"] for it in items])

        v4_score = [
            (pct_pbr[k] + pct_per[k] + pct_psr[k] + pct_pcr[k]) / 4.0
            for k in range(ne)
        ]

        # v4_rank: v4_score 내림차순 dense ordinal (1=best/cheapest)
        v4_order = sorted(range(ne), key=lambda k: v4_score[k], reverse=True)
        v4_map: Dict[str, int] = {}
        for ordinal, k in enumerate(v4_order, start=1):
            v4_map[items[k]["code"]] = ordinal
        v4_by_date[d] = v4_map

        # smallv4_rank: market_cap 하위 20% 게이트 → 부분집합 v4_score 내림차순
        mcaps = [it["market_cap"] for it in items]
        if ne == 1:
            mc_thresh = mcaps[0]
        else:
            mc_thresh = float(np.percentile(np.array(mcaps, dtype=float), SMALLCAP_PCTL))
        gated = [k for k in range(ne) if mcaps[k] <= mc_thresh]
        sv_map: Dict[str, int] = {}
        if gated:
            gated_sorted = sorted(gated, key=lambda k: v4_score[k], reverse=True)
            for ordinal, k in enumerate(gated_sorted, start=1):
                sv_map[items[k]["code"]] = ordinal
        sv_by_date[d] = sv_map

        # hong_rank: 소형주20% ∩ gate_pass 부분집합 v4_score 내림차순
        hong_idx = [k for k in gated if items[k]["gate_pass"]]
        nhong_by_date[d] = len(hong_idx)
        hong_map: Dict[str, int] = {}
        if hong_idx:
            hong_sorted = sorted(hong_idx, key=lambda k: v4_score[k], reverse=True)
            for ordinal, k in enumerate(hong_sorted, start=1):
                hong_map[items[k]["code"]] = ordinal
        hong_by_date[d] = hong_map

    # 종목별 bar 에 매핑
    v4_by_idx_map: Dict[str, List[Optional[int]]] = {}
    sv_by_idx_map: Dict[str, List[Optional[int]]] = {}
    hong_by_idx_map: Dict[str, List[Optional[int]]] = {}
    nelig_by_idx_map: Dict[str, List[int]] = {}
    for code, df in data.items():
        v4s: List[Optional[int]] = []
        svs: List[Optional[int]] = []
        hongs: List[Optional[int]] = []
        neligs: List[int] = []
        for i in range(len(df)):
            d = df.iloc[i]["datetime"]
            d = d.date() if hasattr(d, "date") else pd.to_datetime(d).date()
            vmap = v4_by_date.get(d)
            smap = sv_by_date.get(d)
            hmap = hong_by_date.get(d)
            v4s.append(vmap.get(code) if vmap else None)
            svs.append(smap.get(code) if smap else None)
            hongs.append(hmap.get(code) if hmap else None)
            neligs.append(nelig_by_date.get(d, 0))
        v4_by_idx_map[code] = v4s
        sv_by_idx_map[code] = svs
        hong_by_idx_map[code] = hongs
        nelig_by_idx_map[code] = neligs

    return (
        v4_by_idx_map, sv_by_idx_map, hong_by_idx_map,
        nelig_by_idx_map, nelig_by_date, nhong_by_date,
        psr_all, pcr_all, n_eligible_with_pcr,
    )


def simulate_one_stock(
    code: str,
    df: pd.DataFrame,
    fund_by_idx: List[Optional[dict]],
    v4_by_idx: List[Optional[int]],
    sv_by_idx: List[Optional[int]],
    hong_by_idx: List[Optional[int]],
    nelig_by_idx: List[int],
    strategy,
    stop_loss_pct: float,
    take_profit_pct: float,
    max_hold_bars: int,
    trail_ma: Optional[int],
    april_only: bool = False,
    quarterly: bool = False,
    warmup_bars: int = 20,
    commission_rate: float = 0.00015,  # 수수료 매매 각각 (양방향)
    tax_rate: float = 0.0018,           # 거래세 매도 시
    slippage_rate: float = 0.001,       # 슬리피지 단방향
    # → 왕복 ≈ commission×2 + tax + slippage×2 = 0.41%
    initial_capital: float = 10_000_000,
) -> dict:
    """단일 종목 일봉 시뮬레이션. 신호 → 다음 봉 시가 매수 → sl/tp/mh/trail 청산.

    april_only=True 면 진입 신호를 4월 영업일(거래일 D의 month==4)에만 허용.
    quarterly=True 면 진입 신호를 분기 첫 영업일 근사(month ∈ {1,4,7,10} & 종목별 그 달 첫 거래일)에만 허용.
    (둘 다 켜지면 april_only 가 우선 — 동시 사용 시 main 에서 막음.)
    """
    from strategies.base import SignalType
    n = len(df)
    if n < warmup_bars + 2:
        return {"n_trades": 0, "trades": [], "equity_curve": [initial_capital]}

    df = df.reset_index(drop=True).copy()

    # 분기 첫 영업일 근사: 종목별 (year, month) 첫 거래일 인덱스 집합 (month ∈ {1,4,7,10})
    quarter_entry_idx: set = set()
    if quarterly:
        seen_ym: set = set()
        for i in range(n):
            dt = df.iloc[i]["datetime"]
            dt = dt if hasattr(dt, "month") else pd.to_datetime(dt)
            ym = (dt.year, dt.month)
            if dt.month in (1, 4, 7, 10) and ym not in seen_ym:
                quarter_entry_idx.add(i)
            seen_ym.add(ym)

    cash = initial_capital
    position: Optional[dict] = None
    trades: List[dict] = []
    equity: List[float] = []

    for i in range(warmup_bars, n - 1):
        bar_now = df.iloc[i]
        bar_next = df.iloc[i + 1]

        # 청산 체크
        if position is not None:
            entry_price = position["entry_price"]
            cur_close = float(bar_now["close"])
            ret = (cur_close - entry_price) / entry_price
            hold_bars = i - position["entry_idx"]
            exit_reason = None
            if ret <= -stop_loss_pct:
                exit_reason = "stop_loss"
            elif ret >= take_profit_pct:
                exit_reason = "take_profit"
            elif hold_bars >= max_hold_bars:
                exit_reason = "max_hold"
            elif trail_ma is not None and i >= trail_ma:
                ma = df["close"].iloc[i - trail_ma + 1:i + 1].mean()
                if cur_close < ma:
                    exit_reason = "trail_ma"
            if exit_reason is not None:
                raw_next_open = float(bar_next["open"])
                if raw_next_open <= 0:  # 다음 봉 시가 무효(거래정지/데이터공백) → 이번 봉 청산 보류
                    exit_reason = None
            if exit_reason is not None:
                fill = float(bar_next["open"]) * (1 - slippage_rate)
                proceeds = position["qty"] * fill
                fee = proceeds * (commission_rate + tax_rate)
                cash += proceeds - fee
                pnl = (fill - entry_price) / entry_price
                trades.append({
                    "stock_code": code, "side": "sell", "idx": i + 1,
                    "datetime": str(bar_next["datetime"]), "price": fill,
                    "qty": position["qty"], "reason": exit_reason,
                    "entry_price": entry_price, "pnl_pct": pnl,
                })
                position = None

        # 신호 평가
        if position is None:
            cur_dt = bar_now["datetime"]
            cur_month = cur_dt.month if hasattr(cur_dt, "month") else pd.to_datetime(cur_dt).month
            if april_only:
                allow_entry = (cur_month == 4)
            elif quarterly:
                allow_entry = (i in quarter_entry_idx)
            else:
                allow_entry = True
            if allow_entry:
                window = df.iloc[: i + 1]
                fund = fund_by_idx[i] if i < len(fund_by_idx) else None
                v4 = v4_by_idx[i] if i < len(v4_by_idx) else None
                sv = sv_by_idx[i] if i < len(sv_by_idx) else None
                hong = hong_by_idx[i] if i < len(hong_by_idx) else None
                ne = nelig_by_idx[i] if i < len(nelig_by_idx) else 0
                ctx_extra = {
                    "fund": fund, "v4_rank": v4, "smallv4_rank": sv,
                    "hong_rank": hong, "n_eligible": ne,
                }
                signal = strategy.generate_signal_with_extra_ctx(code, window, "daily", ctx_extra)
                if signal is not None and signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                    raw_next_open = float(bar_next["open"])
                    fill = raw_next_open * (1 + slippage_rate)
                    qty = int((cash * 0.99) // fill) if fill > 0 else 0  # 다음 봉 시가 무효 → 매수 스킵
                    if qty > 0:
                        cost = qty * fill
                        fee = cost * commission_rate
                        cash -= cost + fee
                        position = {"entry_idx": i + 1, "entry_price": fill, "qty": qty}
                        trades.append({
                            "stock_code": code, "side": "buy", "idx": i + 1,
                            "datetime": str(bar_next["datetime"]), "price": fill,
                            "qty": qty, "reason": ",".join(signal.reasons or ["signal"]),
                            "entry_price": fill, "pnl_pct": 0.0,
                        })

        mtm = cash
        if position is not None:
            mtm += position["qty"] * float(bar_now["close"])
        equity.append(mtm)

    # 강제 청산
    if position is not None and float(df.iloc[-1]["close"]) > 0:  # 마지막 종가 무효면 청산 미기록
        last = df.iloc[-1]
        fill = float(last["close"]) * (1 - slippage_rate)
        proceeds = position["qty"] * fill
        fee = proceeds * (commission_rate + tax_rate)
        cash += proceeds - fee
        entry_price = position["entry_price"]
        trades.append({
            "stock_code": code, "side": "sell", "idx": n - 1,
            "datetime": str(last["datetime"]), "price": fill,
            "qty": position["qty"], "reason": "forced_close",
            "entry_price": entry_price,
            "pnl_pct": (fill - entry_price) / entry_price,
        })
        equity.append(cash)

    return {"n_trades": sum(1 for t in trades if t["side"] == "sell"), "trades": trades, "equity_curve": equity}


def _compute_metrics(initial: float, equity: List[float], trades: List[dict]) -> dict:
    if not equity:
        return dict(n_trades=0, pnl_pct=0.0, sharpe=0.0, calmar=0.0, max_dd=0.0,
                    hit_rate=0.0, avg_hold_days=0.0)
    eq = np.array(equity, dtype=float)
    pnl_pct = (eq[-1] - initial) / initial
    rets = np.diff(eq) / eq[:-1]
    rets = rets[np.isfinite(rets)]
    sharpe = float(rets.mean() / rets.std() * math.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = float(-dd.min()) if len(dd) else 0.0
    calmar = float(pnl_pct / max_dd) if max_dd > 1e-9 else 0.0
    sells = [t for t in trades if t["side"] == "sell"]
    wins = sum(1 for t in sells if t["pnl_pct"] > 0)
    hit = wins / len(sells) if sells else 0.0
    holds: List[int] = []
    buy_idx: Optional[int] = None
    for t in trades:
        if t["side"] == "buy":
            buy_idx = t["idx"]
        elif t["side"] == "sell" and buy_idx is not None:
            holds.append(t["idx"] - buy_idx)
            buy_idx = None
    avg_hold = float(np.mean(holds)) if holds else 0.0
    return dict(n_trades=len(sells), pnl_pct=pnl_pct, sharpe=sharpe, calmar=calmar,
                max_dd=max_dd, hit_rate=hit, avg_hold_days=avg_hold)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--variant", required=True, choices=["Q", "K", "B"])
    p.add_argument("--mode", default=None, choices=["single", "all_AND"])
    p.add_argument("--rule", default=None)
    p.add_argument("--all-modes", action="store_true")
    p.add_argument("--april-only", action="store_true",
                   help="진입 신호를 4월 영업일에만 허용 (연 1회 리밸런싱 근사)")
    p.add_argument("--quarterly", action="store_true",
                   help="진입 신호를 분기 첫 영업일 근사(month∈{1,4,7,10})에만 허용")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--start", default=None, help="YYYY-MM-DD (기본: daily_prices 최소 날짜)")
    p.add_argument("--end", default=None, help="YYYY-MM-DD (기본: daily_prices 최대 날짜)")
    p.add_argument("--reports-dir", default="reports/books_research/hongyongchan")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.all_modes and args.mode is not None:
        p.error("--all-modes 와 --mode 는 동시 사용 불가")
    if not args.all_modes and args.mode is None:
        p.error("--mode 또는 --all-modes 둘 중 하나 필수")
    if args.april_only and args.quarterly:
        p.error("--april-only 와 --quarterly 는 동시 사용 불가")

    # 기간 자동
    if args.start is None or args.end is None:
        from db.connection import DatabaseConnection
        with DatabaseConnection.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MIN(date), MAX(date) FROM daily_prices")
            mn, mx = cur.fetchone()
        args.start = args.start or str(mn)
        args.end = args.end or str(mx)
    LOG.info(f"period: {args.start} ~ {args.end}  april_only={args.april_only} quarterly={args.quarterly}")

    universe = _load_fundamentals_universe()
    if args.limit:
        universe = universe[: args.limit]
    LOG.info(f"universe size: {len(universe)}")

    data = _load_daily_adj(universe, args.start, args.end)
    LOG.info(f"loaded data for {len(data)} stocks")
    if not data:
        LOG.error("no data — aborting")
        return

    # market_cap 보유 종목 수 (universe 라벨용)
    n_with_mc = sum(1 for df in data.values() if df["market_cap"].notna().any())
    LOG.info(f"stocks with >=1 non-null market_cap: {n_with_mc}")

    fs_ts = _load_fundamentals_timeseries(list(data.keys()))
    LOG.info(f"loaded fundamentals for {len(fs_ts)} stocks")

    # 종목별 point-in-time fund 사전계산 (한 번만)
    fund_by_idx_map: Dict[str, List[Optional[dict]]] = {}
    for code, df in data.items():
        fund_by_idx_map[code] = _build_fund_by_idx(df, fs_ts.get(code, []))

    # 횡단면 순위 precompute (no-lookahead)
    (v4_by_idx_map, sv_by_idx_map, hong_by_idx_map,
     nelig_by_idx_map, nelig_by_date, nhong_by_date,
     psr_all, pcr_all, n_eligible_with_pcr) = _build_cross_sectional_ranks(
        data, fund_by_idx_map
    )
    if nelig_by_date:
        ne_vals = np.array(list(nelig_by_date.values()), dtype=float)
        LOG.info(
            f"n_eligible (4선 교집합) per date: dates={len(ne_vals)} "
            f"min={int(ne_vals.min())} median={int(np.median(ne_vals))} "
            f"mean={ne_vals.mean():.1f} max={int(ne_vals.max())}"
        )
    else:
        LOG.warning("no eligible (code,date) found — v4/smallv4/hong rank signals will be empty")

    if nhong_by_date:
        nh_vals = np.array(list(nhong_by_date.values()), dtype=float)
        LOG.info(
            f"hong_gate 통과 (소형주20%∩흑자∩성장∩마진/부채) per date: dates={len(nh_vals)} "
            f"min={int(nh_vals.min())} median={int(np.median(nh_vals))} "
            f"mean={nh_vals.mean():.1f} max={int(nh_vals.max())}"
        )
    else:
        LOG.warning("no hong_gate 통과 (code,date) — hong_combo signals will be empty")

    LOG.info(f"PCR 반영 표본(4선 적격 (code,date) 수): {n_eligible_with_pcr}")

    # 팩터 분포 sanity (Korean large-caps median 기대 범위; 1e8-scale 단위버그 검출용)
    for label, arr_list in (("PSR", psr_all), ("PCR", pcr_all)):
        if arr_list:
            arr = np.array(arr_list, dtype=float)
            LOG.info(
                f"{label} distribution: n={len(arr)} "
                f"min={arr.min():.4f} median={np.median(arr):.4f} "
                f"mean={arr.mean():.4f} max={arr.max():.4f}"
            )
        else:
            LOG.warning(f"no {label} values computed — check eligibility/unit math")

    params = VARIANT_PARAMS[args.variant]
    rule_names = [cls().name for cls in ALL_RULES]
    combos = [("single", n) for n in rule_names] + [("all_AND", None)] if args.all_modes else [(args.mode, args.rule)]

    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    leaderboard_path = Path("reports/books_research/leaderboard.parquet")

    from backtest.book_backtester import append_leaderboard

    if args.april_only:
        rebal_tag = "_apr"
        rebal_label = "_april"
    elif args.quarterly:
        rebal_tag = "_q"
        rebal_label = "_quarterly"
    else:
        rebal_tag = ""
        rebal_label = ""
    period_label = "daily_full" + rebal_label

    for mode, rule_name in combos:
        strategy = build_strategy(mode=mode, target_rule=rule_name)
        per_stock_pnl = []
        all_trades = []
        per_stock_metrics = []
        for code, df in data.items():
            res = simulate_one_stock(
                code=code, df=df, fund_by_idx=fund_by_idx_map[code],
                v4_by_idx=v4_by_idx_map[code], sv_by_idx=sv_by_idx_map[code],
                hong_by_idx=hong_by_idx_map[code], nelig_by_idx=nelig_by_idx_map[code],
                strategy=strategy,
                stop_loss_pct=params["stop_loss_pct"],
                take_profit_pct=params["take_profit_pct"],
                max_hold_bars=params["max_hold_bars"],
                trail_ma=params["trail_ma"],
                april_only=args.april_only,
                quarterly=args.quarterly,
                warmup_bars=20,
            )
            metrics = _compute_metrics(10_000_000, res["equity_curve"], res["trades"])
            per_stock_metrics.append(metrics)
            per_stock_pnl.append(metrics["pnl_pct"])
            for t in res["trades"]:
                all_trades.append(t)

        n_stocks = len(per_stock_metrics)
        agg = {
            "n_stocks": n_stocks,
            "n_trades": int(sum(m["n_trades"] for m in per_stock_metrics)),
            "pnl_pct": float(np.mean(per_stock_pnl)) if per_stock_pnl else 0.0,
            "sharpe": float(np.mean([m["sharpe"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
            "calmar": float(np.mean([m["calmar"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
            "max_dd": float(np.mean([m["max_dd"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
            "hit_rate": float(np.mean([m["hit_rate"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
            "avg_hold_days": float(np.mean([m["avg_hold_days"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
        }
        label = rule_name if mode == "single" else mode
        LOG.info(f"[variant={args.variant}{rebal_tag} {mode}/{label}] n_stocks={n_stocks} n_trades={agg['n_trades']} "
                 f"pnl={agg['pnl_pct']:.4%} sharpe={agg['sharpe']:.2f}")

        out_file = reports_dir / f"results_variant{args.variant}{rebal_tag}_{mode}_{label}.parquet"
        if all_trades:
            pd.DataFrame(all_trades).to_parquet(out_file, index=False)

        append_leaderboard(
            path=leaderboard_path,
            row={
                "book_id": "hongyongchan",
                "book_name": BOOK_META["name"],
                "period": period_label,
                "rule_combo": label,
                "mode": mode,
                "variant": args.variant + rebal_tag,
                "universe": f"factor_kr:{n_with_mc}",
                "stop_loss_pct": params["stop_loss_pct"],
                "take_profit_pct": params["take_profit_pct"],
                "max_hold_bars": params["max_hold_bars"],
                "n_stocks": agg["n_stocks"],
                "n_trades": agg["n_trades"],
                "pnl_pct": agg["pnl_pct"],
                "sharpe": agg["sharpe"],
                "calmar": agg["calmar"],
                "max_dd_pct": agg["max_dd"],
                "hit_rate": agg["hit_rate"],
                "avg_hold_bars": agg["avg_hold_days"],
            },
        )


if __name__ == "__main__":
    main()
