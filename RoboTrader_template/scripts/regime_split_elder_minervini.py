"""Elder · Minervini 5년 거래 국면(BULL/BEAR/SIDEWAYS) 분해.

목적: triple_screen_ema_pullback 등 핵심 룰의 거래를 진입일 기준으로
국면 라벨에 매핑해, 전체기간 성과가 어느 국면 기여인지 — 특히
하락장(BEAR)에서도 per-trade 평균이 양(+)인지 — 를 판정한다.

국면 라벨: KOSPI 지수(daily_prices stock_code='KOSPI') 종가의
20일 rolling 누적수익률, ±2% 임계 (기존 regime_split_minervini.py /
regime_split_weinstein.py 와 통일된 convention).

주의:
- 입력 parquet은 종목 풀 전체의 per-trade 로그(buy/sell 행 쌍).
  headline Sharpe(0.68 등)는 per-stock 백테스트 metric의 종목간 평균이라
  pooled per-trade 로그로 재현 불가. 따라서 국면별 Sharpe는
  pooled per-trade ratio(mean/std)로 보고하고 그 한계를 명시한다.
- daily_prices는 SELECT만. 수정/삭제 금지.

출력:
- reports/books_research/regime_split_elder_minervini.parquet (분해표)
- reports/books_research/regime_label_5y.parquet (5년 일별 국면 라벨)
- stdout 에 판정 보고 텍스트
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.regime_analysis import classify_regime_rolling, MarketRegime  # noqa: E402

LOG = logging.getLogger("regime_split_elder_minervini")
logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ELDER_DIR = ROOT / "reports" / "books_research" / "elder_triple_screen"
MIN_DIR = ROOT / "reports" / "books_research" / "minervini_vcp"
OUT_DIR = ROOT / "reports" / "books_research"
OUT_TABLE = OUT_DIR / "regime_split_elder_minervini.parquet"
OUT_LABEL = OUT_DIR / "regime_label_5y.parquet"

START = "2021-01-04"
END = "2026-05-29"
WINDOW = 20
THRESHOLD = 0.02  # ±2% — 기존 regime_split_* 스크립트 convention

# (라벨, parquet 경로)
RULES = [
    ("elder ema_pullback A", ELDER_DIR / "results_variantA_single_triple_screen_ema_pullback.parquet"),
    ("elder ema_pullback B", ELDER_DIR / "results_variantB_single_triple_screen_ema_pullback.parquet"),
    ("elder force_index A", ELDER_DIR / "results_variantA_single_triple_screen_force_index.parquet"),
    ("elder stochastic A", ELDER_DIR / "results_variantA_single_triple_screen_stochastic.parquet"),
    ("minervini volume_dryup B", MIN_DIR / "results_variantB_single_volume_dryup.parquet"),
    ("minervini trend_template B", MIN_DIR / "results_variantB_single_trend_template.parquet"),
]

REGIMES = ["BULL", "BEAR", "SIDEWAYS"]


def load_kospi_close() -> pd.Series:
    """daily_prices의 KOSPI 지수 종가 시계열."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT date, close FROM daily_prices "
            "WHERE stock_code = 'KOSPI' AND date >= %s AND date <= %s "
            "ORDER BY date ASC",
            (START, END),
        )
        rows = cur.fetchall()
    if not rows:
        raise RuntimeError("daily_prices에 KOSPI 지수 행이 없음")
    s = pd.Series({pd.Timestamp(r[0]): float(r[1]) for r in rows}, name="kospi").sort_index()
    return s


def build_label_series(kospi: pd.Series) -> pd.Series:
    """일별 BULL/BEAR/SIDEWAYS 라벨 (str). index=Timestamp."""
    regime = classify_regime_rolling(kospi, window=WINDOW, threshold=THRESHOLD)
    return regime.map(lambda r: r.value.upper())


def pair_trades(df: pd.DataFrame) -> pd.DataFrame:
    """buy/sell 행 쌍을 round-trip 거래 1행으로 결합.

    반환 컬럼: entry_date, exit_date, hold_bars, pnl_pct, stock_code
    """
    buys = df[df["side"] == "buy"].reset_index(drop=True)
    sells = df[df["side"] == "sell"].reset_index(drop=True)
    n = min(len(buys), len(sells))
    buys, sells = buys.iloc[:n], sells.iloc[:n]
    out = pd.DataFrame({
        "stock_code": buys["stock_code"].values,
        "entry_date": pd.to_datetime(buys["datetime"].values),
        "exit_date": pd.to_datetime(sells["datetime"].values),
        "hold_bars": sells["idx"].values - buys["idx"].values,
        "pnl_pct": sells["pnl_pct"].values,
    })
    return out


def regime_at(label: pd.Series, dt: pd.Timestamp) -> str:
    """진입일 dt의 국면 라벨. 정확 일치 없으면 직전 거래일(asof) 라벨."""
    if dt in label.index:
        return label.loc[dt]
    pos = label.index.searchsorted(dt, side="right") - 1
    if pos < 0:
        return "SIDEWAYS"
    return label.iloc[pos]


def _per_trade_sharpe(pnl: np.ndarray) -> float:
    """pooled per-trade Sharpe proxy = mean/std (연율화 안 함)."""
    if len(pnl) < 2 or pnl.std() == 0:
        return 0.0
    return float(pnl.mean() / pnl.std())


def summarize_bucket(pnl: np.ndarray) -> dict:
    n = len(pnl)
    if n == 0:
        return dict(n_trades=0, mean_pct=0.0, median_pct=0.0, sum_pct=0.0,
                    hit=0.0, sharpe_proxy=0.0)
    return dict(
        n_trades=n,
        mean_pct=float(pnl.mean()),
        median_pct=float(np.median(pnl)),
        sum_pct=float(pnl.sum()),
        hit=float((pnl > 0).mean()),
        sharpe_proxy=_per_trade_sharpe(pnl),
    )


def main() -> None:
    kospi = load_kospi_close()
    LOG.info(f"KOSPI {len(kospi)} bars {kospi.index.min().date()}~{kospi.index.max().date()}")

    label = build_label_series(kospi)
    # window 미만 초기 구간(SIDEWAYS 채움) 제외하고 '실제 분류된' 거래일 통계
    valid = label.iloc[WINDOW:]
    counts = valid.value_counts()
    total_days = int(counts.sum())
    LOG.info("=== 국면별 거래일 (window 이후) ===")
    for r in REGIMES:
        c = int(counts.get(r, 0))
        LOG.info(f"  {r}: {c}일 ({c/total_days*100:.1f}%)")

    # 2022 약세장 확인
    y22 = valid[(valid.index >= "2022-01-01") & (valid.index <= "2022-12-31")]
    y22c = y22.value_counts()
    LOG.info(f"2022년 국면: BULL={int(y22c.get('BULL',0))} BEAR={int(y22c.get('BEAR',0))} "
             f"SIDEWAYS={int(y22c.get('SIDEWAYS',0))} (총 {len(y22)}일)")

    # 국면 라벨 저장
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    label_df = pd.DataFrame({"date": label.index, "regime": label.values})
    label_df.to_parquet(OUT_LABEL, index=False)
    LOG.info(f"saved label: {OUT_LABEL}")

    # 거래 국면 분해
    rows = []
    print("\n" + "=" * 100)
    print("국면별 분해표: 룰 × {BULL, BEAR, SIDEWAYS}")
    print("(per-trade 진입일 기준 매핑. sharpe_proxy = pooled per-trade mean/std, 연율화 안 함)")
    print("=" * 100)
    header = f"{'rule':<28} {'regime':<9} {'n':>5} {'mean%':>8} {'med%':>8} {'hit':>6} {'shp_px':>7} {'hold':>6}"
    for rule_label, path in RULES:
        if not path.exists():
            LOG.warning(f"missing: {path}")
            continue
        df = pd.read_parquet(path)
        trades = pair_trades(df)
        trades["regime"] = trades["entry_date"].map(lambda d: regime_at(label, d))

        print("\n" + header)
        print("-" * len(header))
        # 전체
        all_pnl = trades["pnl_pct"].values
        s = summarize_bucket(all_pnl)
        hold_all = float(trades["hold_bars"].mean()) if len(trades) else 0.0
        print(f"{rule_label:<28} {'ALL':<9} {s['n_trades']:>5} {s['mean_pct']*100:>8.3f} "
              f"{s['median_pct']*100:>8.3f} {s['hit']*100:>5.1f}% {s['sharpe_proxy']:>7.3f} {hold_all:>6.1f}")
        for r in REGIMES:
            sub = trades[trades["regime"] == r]
            pnl = sub["pnl_pct"].values
            s = summarize_bucket(pnl)
            hold = float(sub["hold_bars"].mean()) if len(sub) else 0.0
            note = "" if s["n_trades"] >= 20 else " (표본부족)"
            print(f"{rule_label:<28} {r:<9} {s['n_trades']:>5} {s['mean_pct']*100:>8.3f} "
                  f"{s['median_pct']*100:>8.3f} {s['hit']*100:>5.1f}% {s['sharpe_proxy']:>7.3f} {hold:>6.1f}{note}")
            rows.append({
                "rule": rule_label,
                "regime": r,
                "n_trades": s["n_trades"],
                "mean_pct": s["mean_pct"],
                "median_pct": s["median_pct"],
                "sum_pct": s["sum_pct"],
                "hit_rate": s["hit"],
                "sharpe_proxy": s["sharpe_proxy"],
                "avg_hold_bars": hold,
            })

    out_df = pd.DataFrame(rows)
    out_df.to_parquet(OUT_TABLE, index=False)
    LOG.info(f"saved table: {OUT_TABLE}")
    print("\n" + "=" * 100)
    print(f"국면 분류: KOSPI 20일 rolling 누적수익률, ±{THRESHOLD*100:.0f}% 임계")
    print(f"전체 거래일: BULL {int(counts.get('BULL',0))} / "
          f"BEAR {int(counts.get('BEAR',0))} / SIDEWAYS {int(counts.get('SIDEWAYS',0))} (총 {total_days})")
    print("=" * 100)


if __name__ == "__main__":
    main()
