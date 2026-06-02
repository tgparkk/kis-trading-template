"""정기 리밸런싱 N종목 포트폴리오 멀티버스 (가치/퀀트 책 공정 재검증).

배경 (reports/books_research/_FIDELITY_AUDIT_SUMMARY.md):
  가치/퀀트 책(greenblatt/oshaughnessy/lynch/hong/moon)은 원문이 **N종목 균등분산 +
  정기 리밸런싱 + 장기보유** 포트폴리오인데, 기존 백테스트(run_*.py / book_backtester)는
  종목별 독립계좌 sl/tp/mh 단타로 검증되어 per-stock 평균이 보고됐다(포트폴리오 미모델).
  이 드라이버는 그 갭을 메운다 — 진짜 한정자본·max-K·정기 리밸런싱·균등비중 포트폴리오.

모델 (5책 공통, 신규 최소 리밸런싱 시뮬):
  각 책의 run 스크립트 함수(데이터/재무/PIT fund/횡단면 rank)를 **그대로 import 재사용**
  → 책별 어댑터가 거래일 D 마다 종목별 "primary rank"(낮을수록 우선)를 제공.
  매 리밸런싱일(주기: 분기/연1회 근사) 적격 종목을 rank 오름차순 정렬 → 상위 K 균등비중 보유
  → 다음 리밸런싱까지 홀딩(중간 옵션 sl: 종가가 진입가 대비 -sl 이하면 다음봉 시가 청산).
  한정자본 1천만, no-lookahead(PIT 105d lag, df.iloc[:i+1] rank 산정), 결정적(rank tie→code asc).

  Lynch 는 횡단면 rank 가 아니라 절대 스크린 → "스크린 통과=적격", tie-break PER asc(cheap first).

흐름:
  책 로드 → universe/daily/fundamentals 로드(run 스크립트 함수) → PIT fund + 횡단면 rank precompute
  → 거래일별 rank 룩업(date→{code:rank}) 구성 → freq×K 조합마다 포트폴리오 시뮬 → equity 메트릭
  → 전구간 Sharpe/CAGR/MaxDD/Calmar + 국면(BULL/SIDE/BEAR) 분해(regime_label_5y.parquet 재사용).

usage:
  python scripts/book_rebalance_multiverse.py --book moonbyungro_metric --rule value_composite_kr \
    --freqs quarterly,annual --K-list 10 20 30 --start 2021-01-01 --end 2026-05-29 \
    --out reports/books_research/_rebalance_tmp/moon_vc

CLI:
  --book {greenblatt_magic,oshaughnessy_value,lynch_one_up,hongyongchan,moonbyungro_metric}
  --rule <primary rank rule name> (책별 기본 주력 룰 자동 선택 가능 — --rule 생략 시)
  --freqs quarterly,annual  --K-list 10 20 30  --start --end  --sl(옵션, 0=off)  --out
"""
from __future__ import annotations

import argparse
import importlib
import logging
import math
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

LOG = logging.getLogger("book_rebalance_multiverse")

REGIME_LABEL_PATH = ROOT / "reports" / "books_research" / "regime_label_5y.parquet"

# 책별 run 스크립트 모듈명 + 주력(primary) rank 키 + 기본 룰명
#   primary_rank_key: 거래일별 rank map 산출에 쓸 책의 대표 횡단면 순위.
BOOK_SPEC = {
    "greenblatt_magic":   dict(run="run_greenblatt_magic",   primary="magic", default_rule="magic_formula_top"),
    "oshaughnessy_value": dict(run="run_oshaughnessy_value", primary="vc",    default_rule="value_composite_kr"),
    "hongyongchan":       dict(run="run_hongyongchan",       primary="hong",  default_rule="hong_combo"),
    "moonbyungro_metric": dict(run="run_moonbyungro_metric", primary="vc",    default_rule="value_composite_kr"),
    "lynch_one_up":       dict(run="run_lynch_one_up",        primary="screen", default_rule="garp_combo"),
}


# ===========================================================================
# 책별 rank 맵 빌더 — run 스크립트 함수 재사용, date→{code:rank}(낮을수록 우선) 반환.
# ===========================================================================

def _build_rank_lookup(
    book: str, data: Dict[str, pd.DataFrame], run_mod, primary: str,
) -> Tuple[Dict[date, Dict[str, int]], Dict[date, int]]:
    """거래일 D → {code: primary_rank} (1=best, 낮을수록 우선). + date→n_eligible.

    run 스크립트의 _build_fund_by_idx + _build_cross_sectional_ranks 를 그대로 호출
    (PIT 105d lag·no-lookahead 동일). primary 키에 따라 어떤 rank 시리즈를 쓸지 결정.
    Lynch(primary='screen')는 횡단면 rank 가 없으므로 별도 처리(_build_lynch_screen).
    """
    fs_ts = run_mod._load_fundamentals_timeseries(list(data.keys()))
    fund_by_idx_map: Dict[str, List[Optional[dict]]] = {}
    for code, df in data.items():
        fund_by_idx_map[code] = run_mod._build_fund_by_idx(df, fs_ts.get(code, []))

    if primary == "screen":
        return _build_lynch_screen(book, data, fund_by_idx_map, run_mod)

    # oshaughnessy 의 _build_cross_sectional_ranks 는 3번째 인자(mom63)를 요구.
    if book == "oshaughnessy_value":
        mom63_map = {code: run_mod._build_mom63_by_idx(df) for code, df in data.items()}
        ranks = run_mod._build_cross_sectional_ranks(data, fund_by_idx_map, mom63_map)
    else:
        ranks = run_mod._build_cross_sectional_ranks(data, fund_by_idx_map)
    # 각 run 스크립트의 반환 튜플에서 primary rank map 과 nelig map 위치는 책마다 다르므로
    # 키 매핑으로 안전 추출 (튜플 길이/순서 의존 제거).
    rank_idx_map, nelig_idx_map = _extract_primary_rank_maps(book, primary, ranks)

    # bar-index 정렬 rank → date 기반 lookup 으로 변환
    rank_by_date: Dict[date, Dict[str, int]] = {}
    nelig_by_date: Dict[date, int] = {}
    for code, df in data.items():
        rlist = rank_idx_map.get(code, [])
        nlist = nelig_idx_map.get(code, [])
        for i in range(len(df)):
            d = _bar_date(df, i)
            r = rlist[i] if i < len(rlist) else None
            if r is not None:
                rank_by_date.setdefault(d, {})[code] = int(r)
            ne = nlist[i] if i < len(nlist) else 0
            if ne:
                nelig_by_date[d] = int(ne)
    return rank_by_date, nelig_by_date


def _extract_primary_rank_maps(book: str, primary: str, ranks_tuple):
    """run._build_cross_sectional_ranks 반환을 책별로 해석해 (rank_idx_map, nelig_idx_map) 반환.

    각 run 스크립트의 반환 순서(독스트링·코드 기준):
      greenblatt: (rank_by_idx_map, nelig_by_idx_map, nelig_by_date)
      oshaughnessy: (vc_by_idx_map, tv_by_idx_map, psr_by_idx_map, nelig_by_idx_map, nelig_by_date, ...)
      hong: (v4_by_idx_map, smallv4_by_idx_map, hong_by_idx_map, nelig_by_idx_map, nelig_by_date, ...)
      moon: (vc_by_idx_map, pbr_by_idx_map, sv_by_idx_map, nelig_by_idx_map, nelig_by_date, ...)
    """
    if book == "greenblatt_magic":
        return ranks_tuple[0], ranks_tuple[1]
    if book == "oshaughnessy_value":
        # primary vc → idx0 ; nelig → idx3
        key = {"vc": 0, "tv": 1, "psr": 2}.get(primary, 0)
        return ranks_tuple[key], ranks_tuple[3]
    if book == "hongyongchan":
        key = {"v4": 0, "smallv4": 1, "hong": 2}.get(primary, 2)
        return ranks_tuple[key], ranks_tuple[3]
    if book == "moonbyungro_metric":
        key = {"vc": 0, "pbr": 1, "sv": 2, "smallvalue": 2}.get(primary, 0)
        return ranks_tuple[key], ranks_tuple[3]
    raise ValueError(f"unknown book {book} for primary rank extraction")


def _build_lynch_screen(book, data, fund_by_idx_map, run_mod):
    """Lynch 절대 스크린 → date→{code:rank}. rank = PER asc(cheap first) tie-break.

    스크린 통과 = run 스크립트 strategy.generate_signal_with_extra_ctx(...) BUY.
    주력 룰(garp_combo)로 적격 판정 후 PER 오름차순(없으면 큰 수)으로 결정적 순위 부여.
    """
    from collections import defaultdict
    from strategies.base import SignalType
    spec = BOOK_SPEC[book]
    strat = run_mod.build_strategy(mode="single", target_rule=spec["default_rule"])

    pass_by_date: Dict[date, List[Tuple[str, float]]] = defaultdict(list)
    warmup = 20
    for code, df in data.items():
        fbi = fund_by_idx_map.get(code, [])
        n = len(df)
        for i in range(warmup, n - 1):
            fund = fbi[i] if i < len(fbi) else None
            window = df.iloc[: i + 1]
            sig = strat.generate_signal_with_extra_ctx(code, window, "daily", {"fund": fund})
            if sig is not None and sig.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                per = None
                if fund is not None:
                    pv = fund.get("per")
                    try:
                        per = float(pv) if pv is not None and not math.isnan(float(pv)) else None
                    except (TypeError, ValueError):
                        per = None
                pass_by_date[_bar_date(df, i)].append((code, per if per is not None else 1e18))

    rank_by_date: Dict[date, Dict[str, int]] = {}
    nelig_by_date: Dict[date, int] = {}
    for d, items in pass_by_date.items():
        items.sort(key=lambda x: (x[1], x[0]))  # PER asc, code asc (결정적)
        rank_by_date[d] = {code: idx + 1 for idx, (code, _) in enumerate(items)}
        nelig_by_date[d] = len(items)
    return rank_by_date, nelig_by_date


def _bar_date(df: pd.DataFrame, i: int) -> date:
    d = df.iloc[i]["datetime"]
    return d.date() if hasattr(d, "date") else pd.to_datetime(d).date()


# ===========================================================================
# 리밸런싱 주기 판단 (분기/연1회). 거래일 시퀀스 기준 첫 영업일.
# ===========================================================================

def _rebalance_dates(all_dates: List[date], freq: str) -> List[date]:
    """freq 별 리밸런싱일(해당 기간의 첫 거래일) 목록 반환.

    quarterly: 분기(1,4,7,10월) 변경 시 첫 거래일.
    annual   : 연도 변경 시 첫 거래일 (사실상 1월 첫 거래일).
    """
    out: List[date] = []
    prev_key = None
    for d in all_dates:
        if freq == "quarterly":
            q = (d.month - 1) // 3
            key = (d.year, q)
        elif freq == "annual":
            key = (d.year,)
        else:
            raise ValueError(f"unknown freq {freq}")
        if key != prev_key:
            out.append(d)
            prev_key = key
    return out


# ===========================================================================
# 포트폴리오 시뮬 — 한정자본·max-K·균등비중·정기 리밸런싱·홀딩(옵션 sl).
# ===========================================================================

def _simulate_portfolio(
    data: Dict[str, pd.DataFrame],
    rank_by_date: Dict[date, Dict[str, int]],
    rebalance_set: set,
    K: int,
    initial_capital: float = 10_000_000.0,
    sl: float = 0.0,
    commission_rate: float = 0.00015,
    tax_rate: float = 0.0018,
    slippage_rate: float = 0.001,
) -> dict:
    """일자 합집합 루프로 단일 NAV 포트폴리오를 굴린다.

    매 리밸런싱일 D: rank_by_date[D] 상위 K(낮은 rank) 균등 목표. 사라진 종목은 다음봉 시가 매도,
    신규 종목은 다음봉 시가 매수(가용현금 / 빈슬롯 균등). 비리밸일엔 옵션 sl만(종가 -sl 이하→다음봉 시가 청산).
    체결가는 다음 거래일 시가(매수 +slip, 매도 -slip). equity = cash + Σ qty*close(당일).
    """
    # 전체 거래일 합집합 (정렬). 종목별 date→row 인덱스 룩업.
    date_set: set = set()
    px: Dict[str, Dict[date, dict]] = {}
    for code, df in data.items():
        m: Dict[date, dict] = {}
        for i in range(len(df)):
            d = _bar_date(df, i)
            m[d] = {"open": float(df.iloc[i]["open"]), "close": float(df.iloc[i]["close"])}
            date_set.add(d)
        px[code] = m
    all_dates = sorted(date_set)
    if len(all_dates) < 3:
        return dict(equity_curve=[initial_capital], dates=all_dates, daily_returns=[],
                    n_trades=0, n_rebalances=0)

    cash = initial_capital
    positions: Dict[str, dict] = {}   # code -> {qty, entry_price}
    pending: List[dict] = []          # 다음 거래일 시가 체결 큐: {code, side, target_value?}
    equity_curve: List[float] = []
    eq_dates: List[date] = []
    n_trades = 0
    n_rebalances = 0

    for di, d in enumerate(all_dates):
        # 1) 대기 주문 체결 (오늘 시가)
        for order in pending:
            code = order["code"]; side = order["side"]
            row = px.get(code, {}).get(d)
            if row is None or row["open"] <= 0:
                continue
            o = row["open"]
            if side == "SELL":
                pos = positions.get(code)
                if not pos:
                    continue
                fill = o * (1 - slippage_rate)
                proceeds = pos["qty"] * fill
                fee = proceeds * (commission_rate + tax_rate)
                cash += proceeds - fee
                n_trades += 1
                del positions[code]
            elif side == "BUY":
                if code in positions:
                    continue
                fill = o * (1 + slippage_rate)
                tv = order.get("target_value", 0.0)
                qty = int(tv // fill) if fill > 0 else 0
                if qty <= 0:
                    continue
                cost = qty * fill
                fee = cost * commission_rate
                if cash < cost + fee:
                    qty = int((cash * 0.999) // (fill * (1 + commission_rate)))
                    if qty <= 0:
                        continue
                    cost = qty * fill; fee = cost * commission_rate
                cash -= cost + fee
                positions[code] = {"qty": qty, "entry_price": fill}
                n_trades += 1
        pending = []

        is_last = (di >= len(all_dates) - 1)

        # 2) 옵션 sl (비리밸일 포함 매일): 종가가 진입가 -sl 이하 → 다음봉 시가 청산 예약
        if sl and sl > 0 and not is_last:
            for code, pos in list(positions.items()):
                row = px.get(code, {}).get(d)
                if row is None:
                    continue
                if (row["close"] - pos["entry_price"]) / pos["entry_price"] <= -sl:
                    pending.append({"code": code, "side": "SELL"})

        # 3) 리밸런싱 (오늘이 리밸런싱일이고 마지막이 아니면 → 다음봉 시가 체결 예약)
        if d in rebalance_set and not is_last:
            ranks = rank_by_date.get(d, {})
            if ranks:
                ranked = sorted(ranks.items(), key=lambda kv: (kv[1], kv[0]))  # rank asc, code asc
                target = [c for c, _ in ranked[:K]]
                target_set = set(target)
                cur = set(positions.keys())
                # 청산: 목표 이탈 종목
                for code in cur - target_set:
                    if not any(o["code"] == code and o["side"] == "SELL" for o in pending):
                        pending.append({"code": code, "side": "SELL"})
                # 매수: 신규 종목 (균등비중 = 현재 equity / K)
                eq_now = cash + sum(p["qty"] * px.get(c, {}).get(d, {"close": p["entry_price"]})["close"]
                                    for c, p in positions.items())
                slot_value = eq_now / K if K > 0 else 0.0
                for code in target_set - cur:
                    pending.append({"code": code, "side": "BUY", "target_value": slot_value})
                n_rebalances += 1

        # 4) 일별 평가금 (당일 종가 mark-to-market; 종가 없으면 entry 폴백)
        holdings = 0.0
        for code, pos in positions.items():
            row = px.get(code, {}).get(d)
            holdings += pos["qty"] * (row["close"] if row else pos["entry_price"])
        equity_curve.append(cash + holdings)
        eq_dates.append(d)

    return dict(equity_curve=equity_curve, dates=eq_dates, n_trades=n_trades,
                n_rebalances=n_rebalances)


# ===========================================================================
# 메트릭 (equity 기반) + 국면 분해.
# ===========================================================================

def _load_regime_label() -> Optional[pd.Series]:
    if not REGIME_LABEL_PATH.exists():
        LOG.warning(f"regime label 미존재: {REGIME_LABEL_PATH} — 국면 분해 생략")
        return None
    df = pd.read_parquet(REGIME_LABEL_PATH)
    s = pd.Series(df["regime"].values, index=pd.to_datetime(df["date"].values))
    return s.sort_index()


def _regime_at(label: pd.Series, d: date) -> str:
    ts = pd.Timestamp(d)
    if ts in label.index:
        return str(label.loc[ts]).upper()
    pos = label.index.searchsorted(ts, side="right") - 1
    if pos < 0:
        return "SIDEWAYS"
    return str(label.iloc[pos]).upper()


def _metrics(res: dict, initial: float, label: Optional[pd.Series]) -> dict:
    eq = np.asarray(res["equity_curve"], dtype=float)
    dates = res["dates"]
    if eq.size < 2:
        return dict(n_trades=res.get("n_trades", 0), n_rebalances=res.get("n_rebalances", 0),
                    pnl=0.0, cagr=0.0, sharpe=0.0, max_dd=0.0, calmar=0.0,
                    bull_sharpe=0.0, side_sharpe=0.0, bear_sharpe=0.0,
                    bull_ret=0.0, side_ret=0.0, bear_ret=0.0)
    pnl = (eq[-1] - initial) / initial
    rets = np.diff(eq) / eq[:-1]
    rets = np.where(np.isfinite(rets), rets, 0.0)
    sharpe = float(rets.mean() / rets.std() * math.sqrt(252)) if rets.std() > 0 else 0.0
    # CAGR (거래일 → 연수)
    n_years = max(len(eq) / 252.0, 1e-9)
    cagr = float((eq[-1] / initial) ** (1.0 / n_years) - 1.0) if eq[-1] > 0 else -1.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = float(-dd.min()) if dd.size else 0.0
    calmar = float(cagr / max_dd) if max_dd > 1e-9 else 0.0

    out = dict(n_trades=res.get("n_trades", 0), n_rebalances=res.get("n_rebalances", 0),
               pnl=pnl, cagr=cagr, sharpe=sharpe, max_dd=max_dd, calmar=calmar)

    # 국면 분해 (일별 수익률을 regime 라벨로 그룹화 → 국면별 Sharpe·누적수익)
    reg = {"BULL": [], "SIDEWAYS": [], "BEAR": []}
    if label is not None:
        for k in range(1, len(eq)):
            r = (eq[k] - eq[k - 1]) / eq[k - 1] if eq[k - 1] > 0 else 0.0
            rg = _regime_at(label, dates[k])
            if rg not in reg:
                rg = "SIDEWAYS"
            reg[rg].append(r)
    for name, key in (("BULL", "bull"), ("SIDEWAYS", "side"), ("BEAR", "bear")):
        arr = np.asarray(reg[name], dtype=float)
        if arr.size > 1 and arr.std() > 0:
            out[f"{key}_sharpe"] = float(arr.mean() / arr.std() * math.sqrt(252))
        else:
            out[f"{key}_sharpe"] = 0.0
        out[f"{key}_ret"] = float(np.prod(1 + arr) - 1) if arr.size else 0.0
    return out


# ===========================================================================
# main
# ===========================================================================

def main():
    p = argparse.ArgumentParser(description="정기 리밸런싱 N종목 포트폴리오 멀티버스 (가치/퀀트 재검증)")
    p.add_argument("--book", required=True, choices=list(BOOK_SPEC))
    p.add_argument("--rule", default=None, help="primary rank 룰(생략 시 책 기본 주력)")
    p.add_argument("--primary", default=None,
                   help="rank 키 override (vc/pbr/sv/magic/psr/tv/v4/smallv4/hong/screen)")
    p.add_argument("--freqs", default="quarterly,annual")
    p.add_argument("--K-list", type=int, nargs="+", default=[10, 20, 30], dest="k_list")
    p.add_argument("--sl", type=float, default=0.0, help="옵션 stop-loss(0=off, 예 0.20)")
    p.add_argument("--start", default="2021-01-01")
    p.add_argument("--end", default="2026-05-29")
    p.add_argument("--initial-capital", type=float, default=10_000_000.0, dest="initial_capital")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    spec = BOOK_SPEC[args.book]
    primary = args.primary or spec["primary"]
    run_mod = importlib.import_module(f"scripts.{spec['run']}")
    LOG.info(f"book={args.book} run={spec['run']} primary={primary} "
             f"freqs={args.freqs} K={args.k_list} sl={args.sl} period={args.start}~{args.end}")

    universe = run_mod._load_fundamentals_universe()
    if args.limit:
        universe = universe[: args.limit]
    data = run_mod._load_daily_adj(universe, args.start, args.end)
    LOG.info(f"universe={len(universe)} loaded_data={len(data)}")
    if not data:
        LOG.error("no data — aborting")
        return

    rank_by_date, nelig_by_date = _build_rank_lookup(args.book, data, run_mod, primary)
    if nelig_by_date:
        ne = np.array(list(nelig_by_date.values()), dtype=float)
        LOG.info(f"rank dates={len(rank_by_date)} n_eligible: min={int(ne.min())} "
                 f"median={int(np.median(ne))} max={int(ne.max())}")
    else:
        LOG.warning("rank lookup 비어있음 — 결과 0거래 예상")

    # 전체 거래일 합집합 (리밸런싱일 산정용)
    date_set: set = set()
    for code, df in data.items():
        for i in range(len(df)):
            date_set.add(_bar_date(df, i))
    all_dates = sorted(date_set)

    label = _load_regime_label()
    freqs = [f.strip() for f in args.freqs.split(",") if f.strip()]

    rows: List[dict] = []
    for freq in freqs:
        rebs = _rebalance_dates(all_dates, freq)
        reb_set = set(rebs)
        for K in args.k_list:
            res = _simulate_portfolio(
                data=data, rank_by_date=rank_by_date, rebalance_set=reb_set, K=K,
                initial_capital=args.initial_capital, sl=args.sl,
            )
            m = _metrics(res, args.initial_capital, label)
            row = dict(book=args.book, rule=(args.rule or spec["default_rule"]), primary=primary,
                       freq=freq, K=K, sl=args.sl, n_rebal=len(rebs), **m)
            rows.append(row)
            LOG.info(f"[{freq} K={K}] reb={len(rebs)} trades={m['n_trades']} "
                     f"CAGR={m['cagr']:.2%} Sharpe={m['sharpe']:.3f} MaxDD={m['max_dd']:.2%} "
                     f"Calmar={m['calmar']:.2f} | BULL={m['bull_sharpe']:.2f} "
                     f"SIDE={m['side_sharpe']:.2f} BEAR={m['bear_sharpe']:.2f}")

    df_rows = pd.DataFrame(rows).sort_values(["sharpe"], ascending=False).reset_index(drop=True)

    out_dir = Path(args.out) if args.out else (ROOT / "reports" / "books_research" / "_rebalance_tmp" / args.book)
    out_dir.mkdir(parents=True, exist_ok=True)
    tsv = out_dir / f"rebalance_{args.book}_{primary}.tsv"
    df_rows.to_csv(tsv, sep="\t", index=False)

    print(f"\n=== REBALANCE MULTIVERSE {args.book} / primary={primary} "
          f"(period {args.start}~{args.end}, initial={args.initial_capital:,.0f}) ===")
    print(f"tsv: {tsv}")
    print(f"{'freq':>10} {'K':>3} {'reb':>4} {'trades':>6} {'CAGR':>8} {'Sharpe':>7} "
          f"{'MaxDD':>7} {'Calmar':>7} | {'BULL':>6} {'SIDE':>6} {'BEAR':>6}")
    for _, r in df_rows.iterrows():
        print(f"{r['freq']:>10} {int(r['K']):>3} {int(r['n_rebal']):>4} {int(r['n_trades']):>6} "
              f"{r['cagr']:>8.2%} {r['sharpe']:>7.3f} {r['max_dd']:>7.2%} {r['calmar']:>7.2f} | "
              f"{r['bull_sharpe']:>6.2f} {r['side_sharpe']:>6.2f} {r['bear_sharpe']:>6.2f}")

    if not df_rows.empty:
        b = df_rows.iloc[0]
        print(f"\nBEST: {b['freq']} K={int(b['K'])} → Sharpe={b['sharpe']:.3f} CAGR={b['cagr']:.2%} "
              f"MaxDD={b['max_dd']:.2%} | BULL={b['bull_sharpe']:.2f} SIDE={b['side_sharpe']:.2f} "
              f"BEAR={b['bear_sharpe']:.2f}")


if __name__ == "__main__":
    main()
