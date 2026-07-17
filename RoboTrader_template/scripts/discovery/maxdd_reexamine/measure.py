"""maxdd 재검정 — 일수익 포트폴리오 하니스 (PREREG.md 동결 스펙 구현).

adj_factor 곱셈 버그로 MaxDD가 거짓(≈99%) 부풀림돼 탈락한 전략들의 **참 성능**을,
사전등록(PREREG.md)에 고정된 바로 판정하기 위한 하니스. 재측정 결과를 **일 포트폴리오
수익 시리즈**(date-indexed pandas Series) 하나로 환원한 뒤, 그 위에서 OOS 분할·베타헤지
잔차·알파를 모두 계산한다.

두 측정 경로
------------
1) **Gen-1 러너**(예: minervini_vcp) — `run_minervini_vcp.py`의 `_load_daily_adj`(수정본,
   adj_factor 미곱)·`simulate_one_stock`·`_compute_metrics`를 **import 재사용**(로직 복붙 금지).
   러너의 `main()`은 포트폴리오 백테스트가 아니라 종목마다 독립 1천만 자본으로
   `simulate_one_stock`을 돌리고 per-stock 지표를 np.mean 낸다 — 그 per-stock-avg MaxDD가
   99%로 거짓 부풀려졌던 바로 그 숫자다. PREREG 바는 OOS-by-date·베타헤지를 위해 **일
   포트폴리오 수익 시리즈**를 요구하므로, 아래 방식으로 시리즈를 조립한다:

   - 각 종목의 equity_curve(bar별 mtm)를 **일수익 시리즈**로 환원(equity.pct_change()).
     현금 보유일은 mtm 불변 → 수익 0(자동). equity[k]의 날짜는 결정적으로
     df["datetime"].iloc[warmup : warmup+len(equity)] 로 복원된다(simulate_one_stock의
     루프 range(warmup, n-1) + 강제청산 1행 구조에서 유도, 두 경우 모두 정합).
   - 포트폴리오 = 각 날짜에서 **모든 종목 일수익의 동일가중 평균**(union 날짜 정렬, 데이터
     시작 전 종목은 0 기여). 각 슬리브 1천만 동일자본의 동일가중 = equal-weight-of-sleeves.
   - 비용은 왕복 0.21%(commission_rate=0.00015 각 방향, tax_rate=0.0018 매도, slippage=0.0)로
     **강제**, native VARIANT_PARAMS variant A(충실청산), native 유니버스(top_volume:50),
     native warmup(60).

2) **deep_mr_dev20** — `multiverse4_returns_export.py`(clean book_param 가격경로, 이미
   adj 정합)를 서브프로세스로 실행해 daily_returns CSV + KOSPI.csv를 얻어 **그대로** 일
   포트폴리오 수익 시리즈로 로드. 이건 애초에 포트폴리오 sim이라 조립 불필요.

메트릭(일 포트폴리오 수익 r_t 위)
--------------------------------
- 분할: train = r_t[date ≤ 2024-06-30], test = r_t[date > 2024-06-30] (PREREG §3).
- 구간별(train/test/full): 연율 Sharpe = mean/std × √252; MaxDD(누적곱 equity); CAGR/total.
- alpha vs KOSPI = 전략 연율수익(CAGR) − KOSPI 연율수익(CAGR), 구간별(PREREG §6-3).
- 베타헤지 잔차(PREREG §5, hedge_bt.rolling_oos_beta 재사용): 팩터 = **동일가중 native
  유니버스 일수익**(전 대상종목 raw close pct-change, 항상 투자). 주간(5거래일 비겹침)
  리샘플 → window=26 롤링 OOS 베타 → resid = book_w − β·factor_w → Sharpe ×√52.

KOSPI 소스: `book_portfolio_multiverse._load_kospi_close`(일봉 SSOT daily_prices의
'KOSPI' 코드, resolver 기본 kis_template). multiverse4가 KOSPI.csv에 쓰는 것과 동일 함수.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]  # RoboTrader_template/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 베타 하니스(사전등록 §5 지정) — 롤링 OOS 베타 재사용.
# ⚠️ pattern-lab 에는 `db.py`(모듈)가 있어 RoboTrader_template 의 `db/`(패키지)를 가린다.
# hedge_bt(+corr_scout/signals/db)를 pattern-lab 우선으로 잠깐 import 해 rolling_oos_beta 만
# 확보한 뒤, sys.path/sys.modules 를 원복해 이후 `import db.connection` 이 RT 패키지를 찾게 한다.
_PATTERN_LAB = Path("D:/tmp/pattern-lab")


def _import_rolling_oos_beta():
    saved_path = list(sys.path)
    sys.path.insert(0, str(_PATTERN_LAB))
    try:
        from hedge_bt import rolling_oos_beta as _fn
        return _fn
    finally:
        sys.path[:] = saved_path
        for _m in ("hedge_bt", "db", "corr_scout", "signals"):
            sys.modules.pop(_m, None)


rolling_oos_beta = _import_rolling_oos_beta()

# ---- 동결 상수 (PREREG.md) ----
START = "2021-01-01"
END = "2026-06-30"
SPLIT = pd.Timestamp("2024-06-30")     # train ≤ SPLIT, test > SPLIT
COMMISSION = 0.00015                    # 각 방향
TAX = 0.0018                           # 매도
SLIPPAGE = 0.0                         # 왕복 0.21% net
GEN1_WARMUP = 60                       # simulate_one_stock native 기본
BETA_WINDOW = 26
WEEK = 5                               # 5거래일 비겹침


# =====================================================================
# STEP 1a — Gen-1 일 포트폴리오 수익
# =====================================================================

def gen1_portfolio(runner, strategy, variant: str = "A", top_n: int = 50,
                   warmup: int = GEN1_WARMUP, start: str = START, end: str = END):
    """Gen-1 러너의 로더/시뮬레이터를 재사용해 일 포트폴리오 수익 + 팩터를 조립.

    반환 dict:
      port          : 일 포트폴리오 수익 Series(동일가중-of-sleeves)
      factor         : 동일가중 native 유니버스 일수익 Series(베타 팩터)
      per_stock_maxdd: 종목별 max_dd 리스트(러너 _compute_metrics, native 지표)
      n_trades       : 전 종목 매도(청산) 건수 합
      n_stocks       : 데이터 로드된 종목 수
    """
    universe = runner._load_top_volume_universe(start, end, top_n)
    data: Dict[str, pd.DataFrame] = runner._load_daily_adj(universe, start, end)
    if not data:
        raise RuntimeError("gen1: no data loaded")
    wide_close = runner._build_universe_close(data)
    rs_wide = runner.compute_rs_percentile_12w(wide_close)
    params = runner.VARIANT_PARAMS[variant]

    per_stock_ret: Dict[str, pd.Series] = {}
    per_stock_maxdd = []
    n_trades = 0
    for code, df in data.items():
        rs_series = rs_wide[code] if code in rs_wide.columns else None
        res = runner.simulate_one_stock(
            code=code, df=df, rs_series=rs_series, strategy=strategy,
            stop_loss_pct=params["stop_loss_pct"],
            take_profit_pct=params["take_profit_pct"],
            max_hold_bars=params["max_hold_bars"],
            trail_ma=params["trail_ma"],
            warmup_bars=warmup,
            commission_rate=COMMISSION, tax_rate=TAX, slippage_rate=SLIPPAGE,
        )
        eq = res["equity_curve"]
        n_trades += res["n_trades"]
        m = runner._compute_metrics(10_000_000, eq, res["trades"])
        per_stock_maxdd.append(m["max_dd"])
        if len(eq) < 2:
            continue
        # equity[k] 의 날짜 = df.iloc[warmup+k]["datetime"] (루프 + 강제청산 구조에서 유도).
        dates = pd.to_datetime(df["datetime"].iloc[warmup:warmup + len(eq)].values)
        if len(dates) != len(eq):
            # 방어: 길이 불일치 시 겹치는 만큼만
            m2 = min(len(dates), len(eq))
            dates, eq = dates[:m2], eq[:m2]
        s = pd.Series(np.asarray(eq, dtype=float), index=dates)
        per_stock_ret[code] = s.pct_change()

    ret_df = pd.DataFrame(per_stock_ret).sort_index()
    # 동일가중-of-sleeves: 모든 종목 열, 데이터 전/현금일은 0 → 항상 전체 종목수로 평균.
    port = ret_df.fillna(0.0).mean(axis=1)
    port.name = "port"

    # 베타 팩터 = 동일가중 native 유니버스 일수익(raw close pct-change, 항상 투자).
    close_df = pd.DataFrame({c: df.set_index("datetime")["close"] for c, df in data.items()})
    close_df.index = pd.to_datetime(close_df.index)
    close_df = close_df.sort_index()
    factor = close_df.pct_change().mean(axis=1)  # skipna=True → 가용 종목 동일가중
    factor.name = "factor"

    return dict(port=port, factor=factor, per_stock_maxdd=per_stock_maxdd,
                n_trades=n_trades, n_stocks=len(data))


# =====================================================================
# STEP 1b — deep_mr_dev20 (multiverse4 서브프로세스)
# =====================================================================

def deep_mr_portfolio(start: str = START, end: str = END, out_dir: Optional[str] = None):
    """multiverse4_returns_export.py 를 서브프로세스로 실행해 deep_mr_dev20 일수익 로드.

    반환 dict: port(일수익 Series), kospi_ret(Series), factor(동일가중 native 유니버스),
               n_trades, out_dir.
    """
    if out_dir is None:
        out_dir = "D:/tmp/maxdd_reexamine_mv4/deep_mr"
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    cmd = [sys.executable, "scripts/multiverse4_returns_export.py",
           "--strategies", "deep_mr_dev20",
           "--start", start, "--end", end,
           "--commission", str(COMMISSION), "--tax", str(TAX), "--slippage", str(SLIPPAGE),
           "--out", str(out)]
    print(f"[deep_mr] running: {' '.join(cmd)}", flush=True)
    # multiverse4 는 stdout 을 utf-8 로 재설정 → 부모도 utf-8 로 디코드(기본 cp949 크래시 회피).
    r = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print(r.stdout[-2000:] if r.stdout else "")
    if r.returncode != 0:
        print(r.stderr[-4000:])
        raise RuntimeError(f"multiverse4 export failed (rc={r.returncode})")

    df = pd.read_csv(out / "deep_mr_dev20.csv")
    port = pd.Series(df["daily_return"].to_numpy(),
                     index=pd.to_datetime(df["date"])).sort_index()
    port.name = "port"
    kdf = pd.read_csv(out / "KOSPI.csv")
    kospi_ret = pd.Series(kdf["daily_return"].to_numpy(),
                          index=pd.to_datetime(kdf["date"])).sort_index()

    tr = pd.read_csv(out / "deep_mr_dev20_trades.csv")
    n_trades = int((tr["side"] == "sell").sum()) if "side" in tr.columns else len(tr)

    factor = deep_mr_universe_factor(start, end)
    return dict(port=port, kospi_ret=kospi_ret, factor=factor,
                n_trades=n_trades, out_dir=str(out))


def deep_mr_universe_factor(start: str = START, end: str = END) -> pd.Series:
    """deep_mr native 유니버스(PIT 스크리너 합집합) 동일가중 일수익 = 베타 팩터.

    multiverse4_returns_export 의 유니버스 로더/스펙을 재사용(로직 복붙 금지).
    """
    from scripts.multiverse4_returns_export import (
        SPECS, _load_strategy_universe_data, _monthly_scan_dates,
    )
    from db.quant_daily_reader import QuantDailyReader
    spec = SPECS["deep_mr_dev20"]
    scan_dates = _monthly_scan_dates(start, end)
    reader = QuantDailyReader()
    data, _turnover = _load_strategy_universe_data(spec, start, end, scan_dates, reader)
    close_df = pd.DataFrame({c: df.set_index("datetime")["close"] for c, df in data.items()})
    close_df.index = pd.to_datetime(close_df.index)
    close_df = close_df.sort_index()
    factor = close_df.pct_change().mean(axis=1)
    factor.name = "factor"
    return factor


# =====================================================================
# STEP 2 — 구간 메트릭
# =====================================================================

def _seg(r: pd.Series, ppy: int = 252) -> dict:
    r = r.dropna()
    if len(r) < 2:
        return dict(n=len(r), sharpe=float("nan"), maxdd=float("nan"),
                    cagr=float("nan"), total=float("nan"), ann_ret=float("nan"))
    eq = (1.0 + r).cumprod()
    peak = eq.cummax()
    maxdd = float((1.0 - eq / peak).max())
    sd = r.std(ddof=1)
    sharpe = float(r.mean() / sd * np.sqrt(ppy)) if sd > 0 else float("nan")
    total = float(eq.iloc[-1] - 1.0)
    years = len(r) / ppy
    cagr = float(eq.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 and eq.iloc[-1] > 0 else float("nan")
    return dict(n=len(r), sharpe=sharpe, maxdd=maxdd, cagr=cagr, total=total,
                ann_ret=cagr)


def segment_metrics(r: pd.Series) -> Dict[str, dict]:
    r = r.dropna().sort_index()
    train = r[r.index <= SPLIT]
    test = r[r.index > SPLIT]
    return {"full": _seg(r), "train": _seg(train), "test": _seg(test)}


def alpha_vs_kospi(port: pd.Series, kospi_ret: pd.Series) -> Dict[str, float]:
    """alpha = 전략 CAGR − KOSPI CAGR, 구간별(full/train/test)."""
    sm = segment_metrics(port)
    km = segment_metrics(kospi_ret.dropna())
    return {seg: sm[seg]["cagr"] - km[seg]["cagr"] for seg in ("full", "train", "test")}


# =====================================================================
# STEP 3 — 베타헤지 잔차 Sharpe
# =====================================================================

def _weekly_compound(s: pd.Series, week: int = WEEK) -> pd.Series:
    """일수익 s를 비겹침 5거래일 블록으로 복리 합성. 블록 라벨 = 블록 마지막 날짜."""
    s = s.dropna().sort_index()
    vals = s.to_numpy()
    idx = s.index
    out_r, out_d = [], []
    k = 0
    n = len(vals)
    while k + week <= n:
        block = vals[k:k + week]
        out_r.append(float(np.prod(1.0 + block) - 1.0))
        out_d.append(idx[k + week - 1])
        k += week
    return pd.Series(out_r, index=pd.DatetimeIndex(out_d))


def beta_resid_sharpe(port: pd.Series, factor: pd.Series,
                      window: int = BETA_WINDOW) -> Dict[str, float]:
    """주간 리샘플 → 롤링 OOS 베타(단일 팩터) → 잔차 Sharpe(×√52), full·test.

    hedge_bt.rolling_oos_beta 는 2팩터 다중회귀이므로 2번째 팩터를 0열로 넘긴다
    (0열은 적합에 무영향, min-norm 해가 β2=0 → resid = book − β1·factor 로 단일팩터 동치).
    """
    df = pd.DataFrame({"book": port, "factor": factor}).dropna().sort_index()
    book_w = _weekly_compound(df["book"])
    fac_w = _weekly_compound(df["factor"])
    # 두 주간 시리즈는 동일 일 그리드에서 파생 → 인덱스 동일. 방어적 정렬.
    common = book_w.index.intersection(fac_w.index)
    book_w = book_w.loc[common]
    fac_w = fac_w.loc[common]
    zeros = np.zeros(len(fac_w))
    b1, _b2 = rolling_oos_beta(book_w.to_numpy(), fac_w.to_numpy(), zeros, window=window)
    resid = book_w.to_numpy() - b1 * fac_w.to_numpy()
    resid_s = pd.Series(resid, index=book_w.index).dropna()  # i<window = NaN 제거

    def _sh(x: pd.Series) -> float:
        x = x.dropna()
        if len(x) < 2 or x.std(ddof=1) == 0:
            return float("nan")
        return float(x.mean() / x.std(ddof=1) * np.sqrt(52))

    full = _sh(resid_s)
    test = _sh(resid_s[resid_s.index > SPLIT])
    return {"full": full, "test": test, "n_weeks": int(len(resid_s)),
            "n_weeks_test": int((resid_s.index > SPLIT).sum())}


# =====================================================================
# 오케스트레이션 / 리포트
# =====================================================================

def _fmt(x, nd=3, pct=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x*100:.1f}%" if pct else f"{x:.{nd}f}"


def measure_minervini():
    import scripts.run_minervini_vcp as runner
    strategy = runner.build_strategy(mode="single", target_rule="volume_dryup")
    g = gen1_portfolio(runner, strategy, variant="A", top_n=50)
    port, factor = g["port"], g["factor"]
    kospi = _load_kospi()
    kospi_ret = kospi.pct_change()
    seg = segment_metrics(port)
    alpha = alpha_vs_kospi(port, kospi_ret)
    resid = beta_resid_sharpe(port, factor)
    native_maxdd = float(np.mean(g["per_stock_maxdd"])) if g["per_stock_maxdd"] else float("nan")
    return dict(name="minervini_vcp", seg=seg, alpha=alpha, resid=resid,
                native_maxdd=native_maxdd, n_trades=g["n_trades"], n_stocks=g["n_stocks"])


def measure_deep_mr():
    d = deep_mr_portfolio()
    port, factor, kospi_ret = d["port"], d["factor"], d["kospi_ret"]
    seg = segment_metrics(port)
    alpha = alpha_vs_kospi(port, kospi_ret)
    resid = beta_resid_sharpe(port, factor)
    return dict(name="deep_mr_dev20", seg=seg, alpha=alpha, resid=resid,
                native_maxdd=float("nan"), n_trades=d["n_trades"], n_stocks=None)


def _load_kospi() -> pd.Series:
    from scripts.book_portfolio_multiverse import _load_kospi_close
    k = _load_kospi_close(START, END)
    k.index = pd.to_datetime(k.index)
    return k[(k.index >= pd.Timestamp(START)) & (k.index <= pd.Timestamp(END))].sort_index()


def _print_result(res: dict):
    seg = res["seg"]
    a = res["alpha"]
    print(f"\n===== {res['name']} =====")
    print(f"native per-stock-avg MaxDD : {_fmt(res['native_maxdd'], pct=True)}")
    print(f"n_trades={res['n_trades']}  n_stocks={res['n_stocks']}")
    for s in ("full", "train", "test"):
        m = seg[s]
        print(f"  [{s:5}] n={m['n']:4}  Sharpe={_fmt(m['sharpe'])}  "
              f"MaxDD={_fmt(m['maxdd'], pct=True)}  CAGR={_fmt(m['cagr'], pct=True)}  "
              f"total={_fmt(m['total'], pct=True)}  alpha={_fmt(a[s], pct=True)}")
    r = res["resid"]
    print(f"  beta-resid Sharpe: full={_fmt(r['full'])} (n_w={r['n_weeks']})  "
          f"test={_fmt(r['test'])} (n_w={r['n_weeks_test']})")


def _table(results):
    print("\n\n| strategy | native per-stock MaxDD | port MaxDD(full) | "
          "Sharpe train | Sharpe test | alpha train | alpha test | beta-resid Sharpe(full) | n_trades |")
    print("|---|---|---|---|---|---|---|---|---|")
    for res in results:
        seg, a, r = res["seg"], res["alpha"], res["resid"]
        print(f"| {res['name']} | {_fmt(res['native_maxdd'], pct=True)} | "
              f"{_fmt(seg['full']['maxdd'], pct=True)} | {_fmt(seg['train']['sharpe'])} | "
              f"{_fmt(seg['test']['sharpe'])} | {_fmt(a['train'], pct=True)} | "
              f"{_fmt(a['test'], pct=True)} | {_fmt(r['full'])} | {res['n_trades']} |")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", required=True,
                   choices=["minervini_vcp", "deep_mr_dev20", "both"])
    args = p.parse_args()
    results = []
    if args.strategy in ("minervini_vcp", "both"):
        results.append(measure_minervini())
    if args.strategy in ("deep_mr_dev20", "both"):
        results.append(measure_deep_mr())
    for res in results:
        _print_result(res)
    _table(results)


if __name__ == "__main__":
    main()
