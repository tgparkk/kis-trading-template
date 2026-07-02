"""systrader79 평균모멘텀스코어 동적 자산배분 — KOSPI 단일자산 MVP 백테스트.

usage:
  python scripts/run_systrader79.py
  python scripts/run_systrader79.py --bps 30 --safe-annual 0.03

데이터: KOSPI 지수 일봉 (daily_prices stock_code='KOSPI', 2021-01~2026-05).
전략: 위험자산=KOSPI 비중 = 평균모멘텀스코어(1~12개월), 안전자산=현금. 월간 리밸런싱.
벤치마크: KOSPI 100% 단순보유.

산출: CAGR / Sharpe(√12) / MaxDD / Calmar / 최종수익률, KOSPI b&h 대조,
월별 위험자산 비중 추이 → reports/books_research/systrader79/report.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Windows 콘솔 cp949 에서 em-dash/이모지 출력 시 UnicodeEncodeError 방지.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.allocation_backtester import (  # noqa: E402
    AllocationBacktester,
    resample_month_end,
)
from strategies.allocation.systrader79_avgmom import AvgMomentumScoreStrategy  # noqa: E402

LOG = logging.getLogger("run_systrader79")
logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")

START = "2021-01-04"
END = "2026-05-29"

OUT_DIR = ROOT / "reports" / "books_research" / "systrader79"
OUT_REPORT = OUT_DIR / "report.md"

# 기존 측정치 (대조표용 — MEMORY.md / Elder 포트폴리오 결론).
KOSPI_BH_REF = dict(cagr=0.2039, sharpe=0.95, max_dd=0.348)
ELDER_REF = dict(cagr=0.13, sharpe=1.08, max_dd=0.23, note="Elder A 통합 K=20")


def load_kospi_close() -> pd.Series:
    """daily_prices의 KOSPI 지수 종가 일봉 (SELECT only)."""
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
    s = pd.Series(
        {pd.Timestamp(r[0]): float(r[1]) for r in rows}, name="kospi"
    ).sort_index()
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bps", type=float, default=15.0, help="왕복 리밸런싱 비용(bp)")
    ap.add_argument("--safe-annual", type=float, default=0.0, help="안전자산 연 수익률(현금 기본 0)")
    ap.add_argument("--lookback", type=int, default=12, help="모멘텀 룩백 개월")
    args = ap.parse_args()

    kospi_daily = load_kospi_close()
    LOG.info(
        f"KOSPI {len(kospi_daily)} bars "
        f"{kospi_daily.index.min().date()}~{kospi_daily.index.max().date()}"
    )

    monthly = resample_month_end(kospi_daily)
    LOG.info(f"월말 리샘플: {len(monthly)} 개월 "
             f"{monthly.index.min().date()}~{monthly.index.max().date()}")

    strat = AvgMomentumScoreStrategy(lookback_months=args.lookback)
    weights = strat.risk_weights(monthly)
    LOG.info(f"비중 산출(워밍업 {args.lookback}개월 제외): {len(weights)} 개월, "
             f"{weights.index.min().date()}~{weights.index.max().date()}")

    bt = AllocationBacktester(round_trip_bps=args.bps, safe_rate_annual=args.safe_annual)
    res = bt.run(monthly, weights)

    # 벤치마크: 동일 백테스트 구간(워밍업 이후)으로 b&h 정렬.
    bh_close = monthly.loc[monthly.index >= weights.index.min()]
    bh = bt.run_buy_and_hold(bh_close)

    # ---- 콘솔 + 리포트 ----
    report_lines: list[str] = []

    def emit(line: str = "") -> None:
        print(line)
        report_lines.append(line)

    emit("# systrader79 평균모멘텀스코어 동적 자산배분 — KOSPI 단일자산 MVP")
    emit()
    emit("## 알고리즘 요약")
    emit()
    emit(f"- 위험자산 = KOSPI 지수, 안전자산 = 현금(연 {args.safe_annual*100:.1f}%).")
    emit(f"- 매월 말: KOSPI 현재가가 1~{args.lookback}개월 전 월말 종가보다 높으면 각 1점 "
         f"→ 합÷{args.lookback} = 평균모멘텀스코어(0~1).")
    emit("- 위험자산 목표비중 = 평균모멘텀스코어, 나머지 = 현금. 월간 리밸런싱.")
    emit(f"- no-lookahead: t월 말 비중은 t월 말까지 종가만 사용 → t+1월 보유. "
         f"왕복 리밸런싱 비용 {args.bps:.0f}bp.")
    emit(f"- 워밍업 {args.lookback}개월 → 백테스트 구간 "
         f"{weights.index.min().date()}~{weights.index.max().date()} ({res.n_months}개월).")
    emit()

    emit("## 성과 (월간, √12 연율화)")
    emit()
    emit("| 지표 | 평균모멘텀스코어 | KOSPI b&h (동구간) |")
    emit("|---|---:|---:|")
    emit(f"| 최종 누적수익률 | {res.final_return_pct*100:+.2f}% | {bh.final_return_pct*100:+.2f}% |")
    emit(f"| CAGR | {res.cagr*100:+.2f}% | {bh.cagr*100:+.2f}% |")
    emit(f"| Sharpe | {res.sharpe:.3f} | {bh.sharpe:.3f} |")
    emit(f"| Sortino | {res.sortino:.3f} | {bh.sortino:.3f} |")
    emit(f"| MaxDD | {res.max_dd_pct*100:.2f}% | {bh.max_dd_pct*100:.2f}% |")
    emit(f"| Calmar | {res.calmar:.3f} | {bh.calmar:.3f} |")
    emit(f"| 위험자산 평균노출 | {res.avg_risk_weight*100:.1f}% | 100.0% |")
    emit(f"| 누적 회전율 | {res.turnover_total:.2f} | 0.00 |")
    emit()

    emit("## 외부 벤치마크 대조 (기존 측정치)")
    emit()
    emit("| 전략 | CAGR | Sharpe | MaxDD |")
    emit("|---|---:|---:|---:|")
    emit(f"| **평균모멘텀스코어(본 백테스트)** | {res.cagr*100:+.2f}% | {res.sharpe:.2f} | {res.max_dd_pct*100:.1f}% |")
    emit(f"| KOSPI b&h (동구간 실측) | {bh.cagr*100:+.2f}% | {bh.sharpe:.2f} | {bh.max_dd_pct*100:.1f}% |")
    emit(f"| KOSPI b&h (기존 측정치, 풀구간) | {KOSPI_BH_REF['cagr']*100:+.2f}% | "
         f"{KOSPI_BH_REF['sharpe']:.2f} | {KOSPI_BH_REF['max_dd']*100:.1f}% |")
    emit(f"| {ELDER_REF['note']} | {ELDER_REF['cagr']*100:+.2f}% | "
         f"{ELDER_REF['sharpe']:.2f} | {ELDER_REF['max_dd']*100:.1f}% |")
    emit()

    # 월별 위험자산 비중 추이 (연도별 요약 + 전체 min/max/mean).
    wser = pd.Series(res.weights, index=pd.to_datetime(res.dates[:-1]))
    emit("## 월별 위험자산 비중 추이 (연도별 평균)")
    emit()
    emit("| 연도 | 평균비중 | 최소 | 최대 | 관측월수 |")
    emit("|---|---:|---:|---:|---:|")
    for yr, grp in wser.groupby(wser.index.year):
        emit(f"| {yr} | {grp.mean()*100:.1f}% | {grp.min()*100:.1f}% | "
             f"{grp.max()*100:.1f}% | {len(grp)} |")
    emit(f"| **전체** | {wser.mean()*100:.1f}% | {wser.min()*100:.1f}% | "
         f"{wser.max()*100:.1f}% | {len(wser)} |")
    emit()

    # ---- 결론: MDD 방어 + 위험조정 ----
    mdd_defended = res.max_dd_pct < bh.max_dd_pct
    sharpe_better = res.sharpe > bh.sharpe
    upward = res.final_return_pct > 0

    emit("## 결론 — MDD 방어 성공 여부")
    emit()
    emit(f"- **MDD 방어**: 평균모멘텀스코어 {res.max_dd_pct*100:.1f}% vs KOSPI b&h "
         f"{bh.max_dd_pct*100:.1f}% → "
         f"{'성공 (MDD 더 낮음)' if mdd_defended else '실패 (MDD 더 높거나 같음)'}.")
    emit(f"- **위험조정수익(Sharpe)**: {res.sharpe:.2f} vs {bh.sharpe:.2f} → "
         f"{'개선' if sharpe_better else '미개선'}.")
    emit(f"- **우상향 여부**: 최종수익 {res.final_return_pct*100:+.2f}% → "
         f"{'우상향' if upward else '하락'}.")
    emit(f"- **systrader79 테제 판정**: "
         f"{'MDD를 낮추면서 우상향 — 테제 성립' if (mdd_defended and upward) else ''}"
         f"{'' if (mdd_defended and upward) else 'MDD 방어 또는 우상향 일부 미달 — 아래 종합 참고'}.")
    emit()
    emit("> 종합: 위험자산 평균노출 "
         f"{res.avg_risk_weight*100:.0f}%로 KOSPI 폭등장(2025~26)에서 절대수익은 "
         "b&h에 뒤질 수 있으나(노출 축소 대가), 핵심은 하락구간 비중 자동 축소를 통한 "
         "MaxDD 절대 방어 여부다.")
    emit()

    emit("## 한계")
    emit()
    emit(f"- **단일 위험자산(KOSPI+현금)** MVP — 채권/금/해외 ETF 다자산 미구현(ETF 백필 선행 필요).")
    emit(f"- **짧은 히스토리**: 워밍업 후 {res.n_months}개월(≈{res.n_months/12:.1f}년). "
         "단일 국면(2021~2026, 2025~26 대폭등 편향) 표본 한계.")
    emit("- **월간 해상도**: 월말 종가만 사용 — 월중 급락/급등 미포착. 안전자산=현금 0%(보수적).")
    emit("- **외부 대조의 한계**: 개별주 책(Elder 등)과는 대상·계좌모델이 달라 직접 A/B 불가, 정성 대조만.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    LOG.info(f"saved report: {OUT_REPORT}")


if __name__ == "__main__":
    main()
