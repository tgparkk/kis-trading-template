"""문병로 메트릭 스튜디오 5팩터 거래 국면(BULL/BEAR/SIDEWAYS) 분해.

목적: value_composite_kr(베스트)·low_pbr(문병로 시그니처)·small_value 등
핵심 가치/저PBR/소형주 룰의 per-trade를, Elder/Minervini 때와 같은 잣대
(KOSPI 20일 ±2% 국면 라벨)로 분해해 — 특히 약세장(2022 BEAR)에서도
per-trade 평균이 양(+)인지, 저PBR/소형주가 방어가 되는지 — 를 판정한다.

국면 라벨: KOSPI 지수(daily_prices stock_code='KOSPI') 종가의 20일 rolling
누적수익률, ±2% 임계 (regime_split_elder_minervini.py 와 통일).

주의 — 문병로 룰의 특수성:
- 이 책은 펀더멘털 가치투자라 hold가 매우 길다(median 176~210일, max ≈ 1년).
  한 거래가 BULL 진입→BEAR 보유→회복 식으로 여러 국면을 가로지른다.
- 따라서 두 가지 기준 모두 보고한다:
    (1) entry 기준 — "그 국면에서 진입한 거래가 결국 양수였나"
        (Elder/Minervini 비교용. 기본 convention).
    (2) exit  기준 — "그 국면에서 청산된 거래의 성과"
        (약세장에 청산된(=주로 stop_loss) 거래의 손실 규모 파악용).
- 입력 parquet은 종목 풀 전체의 per-trade 로그(buy/sell 행 쌍).
  per-trade pnl 은 side=='sell' 행의 pnl_pct (소수=비율, 0.168=+16.8%).
  headline Sharpe 는 per-stock metric 평균이라 pooled 로그로 재현 불가 →
  국면별은 pooled per-trade mean/std proxy 로 보고하고 한계를 명시.
- daily_prices 는 SELECT 만. 수정/삭제 금지. 입력 parquet 은 읽기만.

출력:
- reports/books_research/moonbyungro_metric/regime_split.parquet (분해표)
- reports/books_research/regime_label_5y.parquet 재사용(있으면 로드, 없으면 생성)
- stdout 에 판정 보고 텍스트
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Windows 콘솔 cp949 에서 em-dash/이모지 출력 시 UnicodeEncodeError 방지.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.regime_analysis import classify_regime_rolling  # noqa: E402

LOG = logging.getLogger("regime_split_moonbyungro")
logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")

MBR_DIR = ROOT / "reports" / "books_research" / "moonbyungro_metric"
OUT_TABLE = MBR_DIR / "regime_split.parquet"
OUT_REPORT = MBR_DIR / "regime_split.md"
OUT_LABEL = ROOT / "reports" / "books_research" / "regime_label_5y.parquet"

START = "2021-01-04"
END = "2026-05-29"
WINDOW = 20
THRESHOLD = 0.02  # ±2% — regime_split_* 스크립트 통일 convention

# (라벨, parquet 경로) — 핵심 3룰 × variant K, A = 6셋.
# value_composite_kr(베스트)와 low_pbr(시그니처)를 반드시 포함.
RULES = [
    ("value_composite_kr K", MBR_DIR / "results_variantK_single_value_composite_kr.parquet"),
    ("value_composite_kr A", MBR_DIR / "results_variantA_single_value_composite_kr.parquet"),
    ("low_pbr K", MBR_DIR / "results_variantK_single_low_pbr.parquet"),
    ("low_pbr A", MBR_DIR / "results_variantA_single_low_pbr.parquet"),
    ("small_value K", MBR_DIR / "results_variantK_single_small_value.parquet"),
    ("small_value A", MBR_DIR / "results_variantA_single_small_value.parquet"),
]

REGIMES = ["BULL", "BEAR", "SIDEWAYS"]


def load_kospi_close() -> pd.Series:
    """daily_prices의 KOSPI 지수 종가 시계열 (SELECT only)."""
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


def build_label_series() -> pd.Series:
    """일별 BULL/BEAR/SIDEWAYS 라벨 (str). index=Timestamp.

    기존 regime_label_5y.parquet 이 있으면 재사용(Elder 와 동일 라벨 보장).
    없으면 KOSPI 로 생성.
    """
    if OUT_LABEL.exists():
        df = pd.read_parquet(OUT_LABEL)
        s = pd.Series(df["regime"].values, index=pd.to_datetime(df["date"].values), name="regime")
        LOG.info(f"reuse label: {OUT_LABEL} ({len(s)} days)")
        return s.sort_index()
    kospi = load_kospi_close()
    LOG.info(f"KOSPI {len(kospi)} bars {kospi.index.min().date()}~{kospi.index.max().date()}")
    regime = classify_regime_rolling(kospi, window=WINDOW, threshold=THRESHOLD)
    label = regime.map(lambda r: r.value.upper())
    pd.DataFrame({"date": label.index, "regime": label.values}).to_parquet(OUT_LABEL, index=False)
    LOG.info(f"saved label: {OUT_LABEL}")
    return label


def pair_trades(df: pd.DataFrame) -> pd.DataFrame:
    """buy/sell 행 쌍을 round-trip 거래 1행으로 결합.

    반환 컬럼: stock_code, entry_date, exit_date, hold_days, pnl_pct
    """
    buys = df[df["side"] == "buy"].reset_index(drop=True)
    sells = df[df["side"] == "sell"].reset_index(drop=True)
    n = min(len(buys), len(sells))
    buys, sells = buys.iloc[:n], sells.iloc[:n]
    entry = pd.to_datetime(buys["datetime"].values)
    exit_ = pd.to_datetime(sells["datetime"].values)
    out = pd.DataFrame({
        "stock_code": buys["stock_code"].values,
        "entry_date": entry,
        "exit_date": exit_,
        "hold_days": (exit_ - entry) / np.timedelta64(1, "D"),
        "pnl_pct": sells["pnl_pct"].values.astype(float),
    })
    return out


def regime_at(label: pd.Series, dt: pd.Timestamp) -> str:
    """날짜 dt의 국면 라벨. 정확 일치 없으면 직전 거래일(asof) 라벨."""
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
    label = build_label_series()

    # window 미만 초기 구간(SIDEWAYS 채움) 제외하고 '실제 분류된' 거래일 통계
    valid = label.iloc[WINDOW:]
    counts = valid.value_counts()
    total_days = int(counts.sum())
    LOG.info("=== 국면별 거래일 (window 이후) ===")
    for r in REGIMES:
        c = int(counts.get(r, 0))
        LOG.info(f"  {r}: {c}일 ({c/total_days*100:.1f}%)")
    y22 = valid[(valid.index >= "2022-01-01") & (valid.index <= "2022-12-31")]
    y22c = y22.value_counts()
    LOG.info(f"2022년 국면: BULL={int(y22c.get('BULL',0))} BEAR={int(y22c.get('BEAR',0))} "
             f"SIDEWAYS={int(y22c.get('SIDEWAYS',0))} (총 {len(y22)}일)")

    rows = []
    report_lines: list[str] = []

    def emit(line: str = "") -> None:
        print(line)
        report_lines.append(line)

    emit("# 문병로 메트릭 스튜디오 — 국면(BULL/BEAR/SIDEWAYS) 분해")
    emit()
    emit(f"국면 분류: KOSPI 20일 rolling 누적수익률, ±{THRESHOLD*100:.0f}% 임계 "
         f"(Elder/Minervini 와 동일 라벨 `regime_label_5y.parquet`).")
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
    emit(f"2022년(약세장 검증연도) 국면: BULL {int(y22c.get('BULL',0))} / "
         f"BEAR {int(y22c.get('BEAR',0))} / SIDEWAYS {int(y22c.get('SIDEWAYS',0))} "
         f"(총 {len(y22)}일) — 2022가 BEAR 비중 높음을 확인.")
    emit()
    emit("> **주의(문병로 룰 특수성)**: 가치투자라 보유기간이 길다(median 176~210일). "
         "한 거래가 여러 국면을 가로질러, 아래는 **entry 기준**(그 국면에서 *진입*한 거래의 "
         "최종 결과)과 **exit 기준**(그 국면에서 *청산*된 거래의 성과)을 모두 보고한다. "
         "per-trade Sharpe proxy = pooled mean/std(연율화 안 함). 표본<20 은 (표본부족) 표기.")

    for basis in ("entry", "exit"):
        date_col = "entry_date" if basis == "entry" else "exit_date"
        emit()
        emit(f"## {basis.upper()} 기준 분해표")
        emit()
        emit("| rule | 국면 | n | mean% | median% | 승률 | shp_px | hold(d) |")
        emit("|---|---|---:|---:|---:|---:|---:|---:|")
        for rule_label, path in RULES:
            if not path.exists():
                LOG.warning(f"missing: {path}")
                continue
            df = pd.read_parquet(path)
            trades = pair_trades(df)
            trades["regime"] = trades[date_col].map(lambda d: regime_at(label, d))

            all_pnl = trades["pnl_pct"].values
            s = summarize_bucket(all_pnl)
            hold_all = float(trades["hold_days"].mean()) if len(trades) else 0.0
            emit(f"| {rule_label} | ALL | {s['n_trades']} | {s['mean_pct']*100:.3f} | "
                 f"{s['median_pct']*100:.3f} | {s['hit']*100:.1f}% | {s['sharpe_proxy']:.3f} | "
                 f"{hold_all:.0f} |")
            for r in REGIMES:
                sub = trades[trades["regime"] == r]
                pnl = sub["pnl_pct"].values
                s = summarize_bucket(pnl)
                hold = float(sub["hold_days"].mean()) if len(sub) else 0.0
                note = "" if s["n_trades"] >= 20 else " ⚠표본부족"
                emit(f"| {rule_label} | {r} | {s['n_trades']} | {s['mean_pct']*100:.3f} | "
                     f"{s['median_pct']*100:.3f} | {s['hit']*100:.1f}% | {s['sharpe_proxy']:.3f} | "
                     f"{hold:.0f}{note} |")
                rows.append({
                    "basis": basis,
                    "rule": rule_label,
                    "regime": r,
                    "n_trades": s["n_trades"],
                    "mean_pct": s["mean_pct"],
                    "median_pct": s["median_pct"],
                    "sum_pct": s["sum_pct"],
                    "hit_rate": s["hit"],
                    "sharpe_proxy": s["sharpe_proxy"],
                    "avg_hold_days": hold,
                })

    # 핵심 질문 답변 (entry 기준 BEAR 셀 자동 요약)
    out_df = pd.DataFrame(rows)
    out_df.to_parquet(OUT_TABLE, index=False)
    LOG.info(f"saved table: {OUT_TABLE}")

    emit()
    emit("## 핵심 질문 — 저PBR/소형주가 약세장(BEAR)에서 방어가 되는가?")
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
    emit("- **entry-BEAR mean% > 0** → 약세장에서 *진입*한 가치/저PBR 거래가 결국 양수로 회복 = 약세장 진입 방어 성립.")
    emit("- **exit-BEAR mean% < 0** → 약세장에 *청산*된 거래(주로 stop_loss)는 손실 = 약세장 한복판 청산의 비용.")
    emit("- 비교 기준 — Elder ema_pullback A: BEAR per-trade **+3.01%** (CANDIDATE 등록 근거).")

    OUT_REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    LOG.info(f"saved report: {OUT_REPORT}")


if __name__ == "__main__":
    main()
