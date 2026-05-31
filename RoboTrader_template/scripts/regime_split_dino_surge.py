"""디노(백새봄) 『급등주 투자법』 — 거래 국면(BULL/BEAR/SIDEWAYS)·연도 분해.

목적: dino_surge 의 핵심 룰(variant B pullback_rebound = 베스트, variant A
dino_test_pullback = 책충실/재무게이트, variant A no-fin)의 per-trade 성과를
Elder/Minervini/문병로와 동일 잣대(KOSPI 20일 ±2% 국면 라벨)로 분해해
 — 특히 약세장(2022 BEAR)에서 회전형 +10% 익절이 방어가 되는지 — 를 판정한다.

디노 룰 특수성:
- 회전 철학(짧은 hold, +10% 익절)이라 entry≈exit 국면이 대체로 일치(문병로의
  176~210일 보유와 대비). 그래도 entry/exit 두 기준 모두 보고.
- per-trade pnl 은 side=='sell' 행의 pnl_pct(소수=비율). headline Sharpe(per-stock
  평균)는 pooled 로그로 재현 불가 → 국면별은 pooled per-trade mean/std proxy 로 보고.
- daily_prices·입력 parquet 은 읽기만(SELECT/read-only).

출력:
- reports/books_research/dino_surge/regime_split.parquet (분해표)
- reports/books_research/dino_surge/regime_split.md (보고 텍스트)
- reports/books_research/regime_label_5y.parquet 재사용(Elder 와 동일 라벨)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.regime_analysis import classify_regime_rolling  # noqa: E402

LOG = logging.getLogger("regime_split_dino_surge")
logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")

DINO_DIR = ROOT / "reports" / "books_research" / "dino_surge"
OUT_TABLE = DINO_DIR / "regime_split.parquet"
OUT_REPORT = DINO_DIR / "regime_split.md"
OUT_LABEL = ROOT / "reports" / "books_research" / "regime_label_5y.parquet"

START = "2021-01-04"
END = "2026-05-29"
WINDOW = 20
THRESHOLD = 0.02  # ±2% — regime_split_* 스크립트 통일 convention

# (라벨, parquet 경로) — 핵심 4셋: 베스트(B) + 살베이지(C 디노진입+추세청산)
# + 책충실(A 재무게이트) + A no-fin. C 는 B 와 진입 동일(pullback_rebound), 청산만 Elder식.
RULES = [
    ("B pullback_rebound", DINO_DIR / "results_variantB_single_pullback_rebound.parquet"),
    ("C pullback+trend_exit", DINO_DIR / "results_variantC_single_pullback_rebound.parquet"),
    ("A dino_test (fin)", DINO_DIR / "results_variantA_single_dino_test_pullback.parquet"),
    ("A dino_test (no-fin)", DINO_DIR / "results_variantA_nofin_single_dino_test_pullback.parquet"),
]

REGIMES = ["BULL", "BEAR", "SIDEWAYS"]


def load_kospi_close() -> pd.Series:
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
    return pd.Series({pd.Timestamp(r[0]): float(r[1]) for r in rows}, name="kospi").sort_index()


def build_label_series() -> pd.Series:
    if OUT_LABEL.exists():
        df = pd.read_parquet(OUT_LABEL)
        s = pd.Series(df["regime"].values, index=pd.to_datetime(df["date"].values), name="regime")
        LOG.info(f"reuse label: {OUT_LABEL} ({len(s)} days)")
        return s.sort_index()
    kospi = load_kospi_close()
    regime = classify_regime_rolling(kospi, window=WINDOW, threshold=THRESHOLD)
    label = regime.map(lambda r: r.value.upper())
    pd.DataFrame({"date": label.index, "regime": label.values}).to_parquet(OUT_LABEL, index=False)
    return label


def pair_trades(df: pd.DataFrame) -> pd.DataFrame:
    buys = df[df["side"] == "buy"].reset_index(drop=True)
    sells = df[df["side"] == "sell"].reset_index(drop=True)
    n = min(len(buys), len(sells))
    buys, sells = buys.iloc[:n], sells.iloc[:n]
    entry = pd.to_datetime(buys["datetime"].values)
    exit_ = pd.to_datetime(sells["datetime"].values)
    return pd.DataFrame({
        "stock_code": buys["stock_code"].values,
        "entry_date": entry,
        "exit_date": exit_,
        "hold_days": (exit_ - entry) / np.timedelta64(1, "D"),
        "pnl_pct": sells["pnl_pct"].values.astype(float),
        "reason": sells["reason"].values,
    })


def regime_at(label: pd.Series, dt: pd.Timestamp) -> str:
    if dt in label.index:
        return label.loc[dt]
    pos = label.index.searchsorted(dt, side="right") - 1
    if pos < 0:
        return "SIDEWAYS"
    return label.iloc[pos]


def _per_trade_sharpe(pnl: np.ndarray) -> float:
    if len(pnl) < 2 or pnl.std() == 0:
        return 0.0
    return float(pnl.mean() / pnl.std())


def summarize_bucket(pnl: np.ndarray) -> dict:
    n = len(pnl)
    if n == 0:
        return dict(n_trades=0, mean_pct=0.0, median_pct=0.0, sum_pct=0.0,
                    hit=0.0, sharpe_proxy=0.0)
    return dict(
        n_trades=n, mean_pct=float(pnl.mean()), median_pct=float(np.median(pnl)),
        sum_pct=float(pnl.sum()), hit=float((pnl > 0).mean()),
        sharpe_proxy=_per_trade_sharpe(pnl),
    )


def main() -> None:
    label = build_label_series()
    valid = label.iloc[WINDOW:]
    counts = valid.value_counts()
    total_days = int(counts.sum())

    rows = []
    report_lines: list[str] = []

    def emit(line: str = "") -> None:
        print(line)
        report_lines.append(line)

    emit("# 디노 급등주 투자법 — 국면(BULL/BEAR/SIDEWAYS)·연도 분해")
    emit()
    emit(f"국면 분류: KOSPI 20일 rolling 누적수익률, ±{THRESHOLD*100:.0f}% 임계 "
         f"(Elder/Minervini/문병로 와 동일 라벨 `regime_label_5y.parquet`).")
    emit()
    emit("## 국면 분포 (window 이후 실제 분류 거래일)")
    emit()
    emit("| 국면 | 일수 | 비율 |")
    emit("|---|---:|---:|")
    for r in REGIMES:
        c = int(counts.get(r, 0))
        emit(f"| {r} | {c} | {c/total_days*100:.1f}% |")
    emit(f"| **합계** | **{total_days}** | 100% |")
    emit()
    emit("> per-trade pnl = sell행 pnl_pct(소수=비율). per-trade Sharpe proxy = pooled "
         "mean/std(연율화 안 함). 표본<20 은 ⚠표본부족 표기. 회전 철학상 hold 가 짧아 "
         "entry≈exit 국면 대체로 일치.")

    # ── 국면 분해 (entry / exit 기준) ─────────────────────────────
    for basis in ("entry", "exit"):
        date_col = "entry_date" if basis == "entry" else "exit_date"
        emit()
        emit(f"## {basis.upper()} 기준 국면 분해표")
        emit()
        emit("| rule | 국면 | n | mean% | median% | 승률 | shp_px | hold(d) |")
        emit("|---|---|---:|---:|---:|---:|---:|---:|")
        for rule_label, path in RULES:
            if not path.exists():
                LOG.warning(f"missing: {path}")
                continue
            trades = pair_trades(pd.read_parquet(path))
            trades["regime"] = trades[date_col].map(lambda d: regime_at(label, d))
            s = summarize_bucket(trades["pnl_pct"].values)
            hold_all = float(trades["hold_days"].mean()) if len(trades) else 0.0
            emit(f"| {rule_label} | ALL | {s['n_trades']} | {s['mean_pct']*100:.3f} | "
                 f"{s['median_pct']*100:.3f} | {s['hit']*100:.1f}% | {s['sharpe_proxy']:.3f} | {hold_all:.1f} |")
            for r in REGIMES:
                sub = trades[trades["regime"] == r]
                s = summarize_bucket(sub["pnl_pct"].values)
                hold = float(sub["hold_days"].mean()) if len(sub) else 0.0
                note = "" if s["n_trades"] >= 20 else " ⚠표본부족"
                emit(f"| {rule_label} | {r} | {s['n_trades']} | {s['mean_pct']*100:.3f} | "
                     f"{s['median_pct']*100:.3f} | {s['hit']*100:.1f}% | {s['sharpe_proxy']:.3f} | {hold:.1f}{note} |")
                rows.append(dict(basis=basis, rule=rule_label, regime=r, n_trades=s["n_trades"],
                                 mean_pct=s["mean_pct"], median_pct=s["median_pct"], sum_pct=s["sum_pct"],
                                 hit_rate=s["hit"], sharpe_proxy=s["sharpe_proxy"], avg_hold_days=hold))

    # ── 연도 분해 (exit 기준) ─────────────────────────────────────
    emit()
    emit("## 연도별 분해 (exit 기준, per-trade)")
    emit()
    emit("| rule | 연도 | n | mean% | 승률 | shp_px |")
    emit("|---|---|---:|---:|---:|---:|")
    for rule_label, path in RULES:
        if not path.exists():
            continue
        trades = pair_trades(pd.read_parquet(path))
        trades["year"] = pd.to_datetime(trades["exit_date"]).dt.year
        for yr in sorted(trades["year"].unique()):
            sub = trades[trades["year"] == yr]
            s = summarize_bucket(sub["pnl_pct"].values)
            note = "" if s["n_trades"] >= 20 else " ⚠"
            emit(f"| {rule_label} | {yr} | {s['n_trades']} | {s['mean_pct']*100:.3f} | "
                 f"{s['hit']*100:.1f}% | {s['sharpe_proxy']:.3f}{note} |")

    out_df = pd.DataFrame(rows)
    out_df.to_parquet(OUT_TABLE, index=False)
    LOG.info(f"saved table: {OUT_TABLE}")

    # ── 핵심 질문: 약세장 방어 ────────────────────────────────────
    emit()
    emit("## 핵심 질문 — 회전형 +10% 익절이 약세장(BEAR)에서 방어가 되는가?")
    emit()
    bear_entry = out_df[(out_df["basis"] == "entry") & (out_df["regime"] == "BEAR")]
    bear_exit = out_df[(out_df["basis"] == "exit") & (out_df["regime"] == "BEAR")]
    emit("| rule | entry-BEAR mean% | n | exit-BEAR mean% | n |")
    emit("|---|---:|---:|---:|---:|")
    for rule_label, _ in RULES:
        be = bear_entry[bear_entry["rule"] == rule_label]
        bx = bear_exit[bear_exit["rule"] == rule_label]
        be_m = be["mean_pct"].iloc[0] * 100 if len(be) else float("nan")
        be_n = int(be["n_trades"].iloc[0]) if len(be) else 0
        bx_m = bx["mean_pct"].iloc[0] * 100 if len(bx) else float("nan")
        bx_n = int(bx["n_trades"].iloc[0]) if len(bx) else 0
        emit(f"| {rule_label} | {be_m:.3f} | {be_n} | {bx_m:.3f} | {bx_n} |")
    emit()
    emit("- 비교 기준 — Elder ema_pullback A: BEAR per-trade **+3.01%** (CANDIDATE 등록 근거).")

    OUT_REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    LOG.info(f"saved report: {OUT_REPORT}")


if __name__ == "__main__":
    main()
