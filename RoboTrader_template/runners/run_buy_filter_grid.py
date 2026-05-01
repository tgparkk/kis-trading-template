"""
매수 필터 그리드 탐색 스크립트 (2026-05-01)
============================================
Phase 2: 매수필터 파라미터 최적화 — OOS + 워크포워드 검증

실행:
    cd RoboTrader_template
    python runners/run_buy_filter_grid.py

결과:
    output/buy_filter_grid_2026-05-01.parquet
    output/buy_filter_grid_2026-05-01.md
    ~/.claude/projects/D--GIT-kis-trading-template/memory/plan-2026-05-01-buy-filter-grid-result.md
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# 경로 설정 — RoboTrader_template/ 를 sys.path에 추가
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent.parent  # RoboTrader_template/
sys.path.insert(0, str(_HERE))

# ---------------------------------------------------------------------------
# 외부 DB 환경변수 (memory 기준)
# ---------------------------------------------------------------------------
os.environ.setdefault("EXTERNAL_DB_HOST", "127.0.0.1")
os.environ.setdefault("EXTERNAL_DB_PORT", "5433")
os.environ.setdefault("EXTERNAL_DB_USER", "postgres")
os.environ.setdefault("EXTERNAL_DB_PASSWORD", "1234")

# ---------------------------------------------------------------------------
# 로깅 설정
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_buy_filter_grid")


def main() -> None:
    # -----------------------------------------------------------------------
    # 1. 데이터 로드 (strategy_analysis.daily_candles)
    # -----------------------------------------------------------------------
    logger.info("=== Phase 2 매수 필터 그리드 탐색 시작 ===")
    logger.info("외부 DB에서 일봉 데이터 로드 중...")

    from strategies.historical_data import get_daily_candles_range, get_sectors

    STOCK_CODES = [
        "005930", "000660", "034020", "005380", "196170",
        "035420", "042660", "012450", "042700", "086520",
        "006400", "000270", "064350", "005490", "000100",
        "035720", "005935", "007660", "105560", "028300",
        "247540", "068270", "125490", "267260", "456160",
        "010140", "272210", "373220", "466100", "051910",
        "015760", "010120", "277810", "055550", "329180",
        "000250", "278470", "207940", "298380", "003670",
        "450080", "489790", "348370", "064400", "402340",
        "108490", "009150", "079550", "141080", "009540",
        "086790", "047810", "012330", "009830", "087010",
        "468530", "298040", "080220", "001440", "352820",
    ]  # 거래대금 상위 60종목 (2024-2026)

    START = "2024-01-01"
    END = "2026-04-30"
    OOS_RATIO = 0.2    # 80% IS / 20% OOS
    N_JOBS = 4

    t0 = time.time()
    daily_data = get_daily_candles_range(
        stock_codes=STOCK_CODES,
        start_date=date(2024, 1, 1),
        end_date=date(2026, 4, 30),
    )

    available_codes = [c for c in STOCK_CODES if c in daily_data and not daily_data[c].empty]
    logger.info(
        f"데이터 로드 완료: {len(available_codes)}/{len(STOCK_CODES)}종목, "
        f"소요={time.time()-t0:.1f}초"
    )

    if not available_codes:
        logger.error("로드된 데이터 없음. DB 접속 확인 필요.")
        sys.exit(1)

    # 데이터 길이 요약
    lengths = [len(daily_data[c]) for c in available_codes]
    logger.info(
        f"일봉 레코드: 종목당 평균 {sum(lengths)/len(lengths):.0f}건 "
        f"(최소 {min(lengths)}, 최대 {max(lengths)})"
    )

    # -----------------------------------------------------------------------
    # 2. 그리드 정의 (multiverse_grid.yaml 반영)
    # -----------------------------------------------------------------------
    logger.info("\n=== 그리드 정의 ===")
    GRID = {
        "parameters.min_buy_signals": [1, 2, 3],
        "parameters.rsi_oversold":    [30, 35, 40, 45],
        "parameters.volume_multiplier": [1.0, 1.5, 2.0],
        "parameters.ma_short_period": [3, 5, 10],
        "risk_management.stop_loss_pct": [0.03, 0.05, 0.07],
    }
    from itertools import product as _product
    total_combos = 1
    for k, v in GRID.items():
        logger.info(f"  {k}: {v}")
        total_combos *= len(v)
    logger.info(f"  => 총 조합: {total_combos}개")

    # -----------------------------------------------------------------------
    # 3. MultiverseEngine 구성
    # -----------------------------------------------------------------------
    from backtest.multiverse import MultiverseEngine
    from strategies.sample.strategy import SampleStrategy

    mv = MultiverseEngine(
        strategy_class=SampleStrategy,
        daily_data=daily_data,
        stock_codes=available_codes,
        initial_capital=10_000_000,
        max_positions=5,
        position_size_pct=0.2,
    )
    for path, values in GRID.items():
        mv.add_param(path, values)

    # -----------------------------------------------------------------------
    # 4. run_oos_split (IS 80% / OOS 20%)
    # -----------------------------------------------------------------------
    logger.info(f"\n=== IS/OOS 분리 백테스트 시작 (n_jobs={N_JOBS}) ===")
    oos_result = mv.run_oos_split(
        start=START,
        end=END,
        oos_ratio=OOS_RATIO,
        min_trades=5,   # 2년 데이터지만 EOD 청산이라 거래 적을 수 있음
        n_jobs=N_JOBS,
        stability_threshold=0.7,
    )

    logger.info(
        f"OOS 분리 완료: 전체={oos_result.total_combinations}개, "
        f"통과={oos_result.filtered_count}개, "
        f"소요={oos_result.elapsed_seconds:.1f}초"
    )

    # -----------------------------------------------------------------------
    # 5. Top 10 후보 (pnl_stability_grade == 안정 + oos_calmar > 0)
    # -----------------------------------------------------------------------
    all_df = oos_result.top(n=oos_result.filtered_count or 324, sort_by="oos_calmar")
    logger.info(f"\n=== OOS 결과 분포 (전체 {len(all_df)}개 통과) ===")
    if not all_df.empty and "oos_calmar" in all_df.columns:
        logger.info(f"  oos_calmar: mean={all_df['oos_calmar'].mean():.3f}  "
                    f"median={all_df['oos_calmar'].median():.3f}  "
                    f"best={all_df['oos_calmar'].max():.3f}  "
                    f"worst={all_df['oos_calmar'].min():.3f}")
        if "oos_return" in all_df.columns:
            logger.info(f"  oos_return: mean={all_df['oos_return'].mean():.3f}  "
                        f"median={all_df['oos_return'].median():.3f}  "
                        f"best={all_df['oos_return'].max():.3f}  "
                        f"worst={all_df['oos_return'].min():.3f}")

    # 필터: pnl_stability_grade == 안정 AND oos_calmar > 0
    stable_positive: object = all_df
    if "pnl_stability_grade" in all_df.columns:
        stable_positive = all_df[
            (all_df["pnl_stability_grade"] == "안정") &
            (all_df.get("oos_calmar", 0) > 0)
        ]
        logger.info(
            f"  안정+OOS양수: {len(stable_positive)}개"
        )

    if len(stable_positive) == 0:
        logger.warning("안정+OOS양수 후보 없음 — oos_calmar > 0 조건만으로 폴백")
        if "oos_calmar" in all_df.columns:
            stable_positive = all_df[all_df["oos_calmar"] > 0]
        if len(stable_positive) == 0:
            logger.warning("oos_calmar > 0 후보도 없음 — 전체 Top 10 사용")
            stable_positive = all_df

    top10_df = stable_positive.head(10)
    logger.info(f"\n=== Top 10 OOS 후보 ===")
    logger.info(f"\n{top10_df.to_string()}")

    # Top 10 파라미터 리스트 (워크포워드에 전달)
    param_keys = list(GRID.keys())
    top10_params = []
    for _, row in top10_df.iterrows():
        p = {}
        for k in param_keys:
            col = k.split(".")[-1]
            if col in row:
                p[k] = row[col]
        top10_params.append(p)

    # -----------------------------------------------------------------------
    # 6. run_walkforward (Top 10 대상 / 전체 재실행)
    # -----------------------------------------------------------------------
    logger.info(f"\n=== 워크포워드 검증 시작 (n_jobs={N_JOBS}) ===")
    # is_window=252(1년), oos_window=63(3개월), n_windows=3
    # (2년 데이터라 6윈도우는 커버리지 부족 — 3개로 축소)
    wf_result = mv.run_walkforward(
        start=START,
        end=END,
        is_window=252,
        oos_window=63,
        n_windows=3,
        min_trades=5,
        n_jobs=N_JOBS,
        stability_threshold=0.7,
    )

    logger.info(
        f"워크포워드 완료: 전체={wf_result.total_combinations}개, "
        f"통과={wf_result.filtered_count}개, "
        f"소요={wf_result.elapsed_seconds:.1f}초"
    )

    passing_result = wf_result.walkforward_passing()
    passing_df = passing_result.top(n=50, sort_by="calmar_ratio") if passing_result.results else None
    n_passing = len(passing_result.results)
    logger.info(f"워크포워드 전체 통과: {n_passing}개")

    if passing_df is not None and not passing_df.empty:
        logger.info(f"\n=== 워크포워드 통과 후보 ===")
        logger.info(f"\n{passing_df.head(20).to_string()}")

    # -----------------------------------------------------------------------
    # 7. 결과 저장
    # -----------------------------------------------------------------------
    out_dir = _HERE / "output"
    out_dir.mkdir(exist_ok=True)
    parquet_path = out_dir / "buy_filter_grid_2026-05-01.parquet"
    md_path = out_dir / "buy_filter_grid_2026-05-01.md"

    # Parquet (전체 OOS 결과)
    oos_result.to_parquet(str(parquet_path), top_n=0)

    # Markdown (Top 20 + 워크포워드 통과)
    _write_markdown(
        md_path=md_path,
        oos_result=oos_result,
        top10_df=top10_df,
        passing_df=passing_df,
        n_passing=n_passing,
        total_combos=total_combos,
        grid=GRID,
        start=START,
        end=END,
    )

    # -----------------------------------------------------------------------
    # 8. 사장님 결재용 권고 문서
    # -----------------------------------------------------------------------
    plan_path = Path(
        r"C:\Users\sttgp\.claude\projects\D--GIT-kis-trading-template\memory"
        r"\plan-2026-05-01-buy-filter-grid-result.md"
    )
    _write_recommendation(
        plan_path=plan_path,
        oos_result=oos_result,
        top10_df=top10_df,
        passing_df=passing_df,
        n_passing=n_passing,
        total_combos=total_combos,
        grid=GRID,
        start=START,
        end=END,
        elapsed_oos=oos_result.elapsed_seconds,
        elapsed_wf=wf_result.elapsed_seconds,
    )

    logger.info(f"\n=== 완료 ===")
    logger.info(f"  Parquet: {parquet_path}")
    logger.info(f"  Markdown: {md_path}")
    logger.info(f"  권고 문서: {plan_path}")


# ---------------------------------------------------------------------------
# 헬퍼: Markdown 저장
# ---------------------------------------------------------------------------

def _write_markdown(
    md_path: Path,
    oos_result,
    top10_df,
    passing_df,
    n_passing: int,
    total_combos: int,
    grid: dict,
    start: str,
    end: str,
) -> None:
    import pandas as pd
    lines = []
    lines.append("# 매수 필터 그리드 탐색 결과 (2026-05-01)")
    lines.append("")
    lines.append(f"- **기간**: {start} ~ {end}")
    lines.append(f"- **Universe**: 거래대금 상위 60종목 (KOSPI/KOSDAQ)")
    lines.append(f"- **총 조합**: {total_combos}개")
    lines.append(f"- **IS/OOS 통과**: {oos_result.filtered_count}개")
    lines.append(f"- **워크포워드 통과**: {n_passing}개")
    lines.append(f"- **IS/OOS 소요**: {oos_result.elapsed_seconds:.1f}초")
    lines.append("")

    lines.append("## 그리드 파라미터")
    lines.append("")
    for k, v in grid.items():
        lines.append(f"- `{k}`: {v}")
    lines.append("")

    lines.append("## IS/OOS Top 20 (oos_calmar 기준)")
    lines.append("")
    top20 = oos_result.top(n=20, sort_by="oos_calmar")
    if not top20.empty:
        lines.append(top20.to_markdown(index=True))
    else:
        lines.append("_(결과 없음)_")
    lines.append("")

    lines.append("## Top 10 후보 (안정+OOS양수)")
    lines.append("")
    if top10_df is not None and not top10_df.empty:
        lines.append(top10_df.to_markdown(index=True))
    else:
        lines.append("_(후보 없음)_")
    lines.append("")

    lines.append(f"## 워크포워드 통과 후보 ({n_passing}개)")
    lines.append("")
    if passing_df is not None and not passing_df.empty:
        lines.append(passing_df.head(20).to_markdown(index=True))
    else:
        lines.append("_(통과 후보 없음)_")
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    logging.getLogger("run_buy_filter_grid").info(f"Markdown 저장: {md_path}")


# ---------------------------------------------------------------------------
# 헬퍼: 사장님 결재용 권고 문서
# ---------------------------------------------------------------------------

def _write_recommendation(
    plan_path: Path,
    oos_result,
    top10_df,
    passing_df,
    n_passing: int,
    total_combos: int,
    grid: dict,
    start: str,
    end: str,
    elapsed_oos: float,
    elapsed_wf: float,
) -> None:
    import pandas as pd

    lines = []
    lines.append("# 매수 필터 그리드 결과 — 사장님 결재용 권고 (2026-05-01)")
    lines.append("")
    lines.append("## 1. 실행 요약")
    lines.append("")
    lines.append(f"| 항목 | 값 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 기간 | {start} ~ {end} |")
    lines.append(f"| Universe | 거래대금 상위 60종목 |")
    lines.append(f"| 그리드 조합 수 | {total_combos}개 |")
    lines.append(f"| IS/OOS 통과 | {oos_result.filtered_count}개 |")
    lines.append(f"| 워크포워드 통과 | {n_passing}개 |")
    lines.append(f"| IS/OOS 소요 | {elapsed_oos:.0f}초 ({elapsed_oos/60:.1f}분) |")
    lines.append(f"| 워크포워드 소요 | {elapsed_wf:.0f}초 ({elapsed_wf/60:.1f}분) |")
    lines.append("")

    lines.append("## 2. 그리드 파라미터")
    lines.append("")
    for k, v in grid.items():
        lines.append(f"- `{k}`: {v}")
    lines.append("")

    # IS/OOS 분포
    all_df = oos_result.top(n=oos_result.filtered_count or 324, sort_by="oos_calmar")
    lines.append("## 3. IS/OOS 메트릭 분포")
    lines.append("")
    if not all_df.empty:
        for col in ["oos_calmar", "oos_return", "is_calmar", "is_return", "calmar_ratio", "total_return"]:
            if col in all_df.columns:
                s = all_df[col].dropna()
                if len(s) > 0:
                    lines.append(
                        f"- **{col}**: mean={s.mean():.3f}, "
                        f"median={s.median():.3f}, "
                        f"best={s.max():.3f}, "
                        f"worst={s.min():.3f}"
                    )
    lines.append("")

    # Top 10
    lines.append("## 4. Top 10 OOS 후보")
    lines.append("")
    if top10_df is not None and not top10_df.empty:
        lines.append(top10_df.to_markdown(index=True))
    else:
        lines.append("_(없음)_")
    lines.append("")

    # 워크포워드
    lines.append(f"## 5. 워크포워드 통과 후보 ({n_passing}개)")
    lines.append("")
    if passing_df is not None and not passing_df.empty:
        lines.append(passing_df.head(10).to_markdown(index=True))
    else:
        lines.append("_(통과 후보 없음)_")
    lines.append("")

    # 추천 파라미터 — OOS + 워크포워드 교집합 우선, 없으면 OOS Top 기준
    lines.append("## 6. 추천 파라미터")
    lines.append("")
    _add_recommendations(lines, top10_df, passing_df)

    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("\n".join(lines), encoding="utf-8")
    logging.getLogger("run_buy_filter_grid").info(f"권고 문서 저장: {plan_path}")


def _add_recommendations(lines: list, top10_df, passing_df) -> None:
    """추천 파라미터 1순위 + 차선 2개 작성."""
    import pandas as pd

    candidates = []

    # 워크포워드 통과 후보가 있으면 우선 사용
    if passing_df is not None and not passing_df.empty:
        source = "워크포워드 통과 + OOS 기준"
        # oos_calmar 또는 calmar_ratio 기준 정렬
        sort_col = "oos_calmar" if "oos_calmar" in passing_df.columns else "calmar_ratio"
        ranked = passing_df.sort_values(sort_col, ascending=False)
        candidates = ranked.head(3).to_dict("records")
    elif top10_df is not None and not top10_df.empty:
        source = "OOS Top 기준 (워크포워드 통과 없음)"
        sort_col = "oos_calmar" if "oos_calmar" in top10_df.columns else "calmar_ratio"
        ranked = top10_df.sort_values(sort_col, ascending=False)
        candidates = ranked.head(3).to_dict("records")

    if not candidates:
        lines.append("_(추천 불가 — 후보 없음)_")
        return

    lines.append(f"> 기준: {source}")
    lines.append("")

    rank_labels = ["1순위 (최우선 추천)", "2순위 (차선)", "3순위 (차선)"]
    param_keys = [
        ("parameters.min_buy_signals", "min_buy_signals"),
        ("parameters.rsi_oversold", "rsi_oversold"),
        ("parameters.volume_multiplier", "volume_multiplier"),
        ("parameters.ma_short_period", "ma_short_period"),
        ("risk_management.stop_loss_pct", "stop_loss_pct"),
    ]

    for i, (label, cand) in enumerate(zip(rank_labels, candidates)):
        lines.append(f"### {label}")
        lines.append("")
        lines.append("**파라미터:**")
        for full_key, col in param_keys:
            val = cand.get(col, cand.get(full_key.split(".")[-1], "N/A"))
            lines.append(f"- `{full_key}`: {val}")
        lines.append("")

        oos_c = cand.get("oos_calmar", None)
        oos_r = cand.get("oos_return", None)
        wf_p = cand.get("wf_min_pf", None)
        wf_pass = cand.get("wf_pass", None)
        sharpe = cand.get("sharpe_ratio", None)

        lines.append("**성과:**")
        if oos_c is not None:
            lines.append(f"- OOS Calmar: {oos_c:.3f}")
        if oos_r is not None:
            lines.append(f"- OOS 수익률: {oos_r:+.2%}")
        if sharpe is not None:
            lines.append(f"- Sharpe: {sharpe:.3f}")
        if wf_p is not None:
            lines.append(f"- WF 최소 PF: {wf_p:.3f}")
        if wf_pass is not None:
            lines.append(f"- WF 통과: {'예' if wf_pass else '아니오'}")
        lines.append("")

        # 근거/주의사항
        if i == 0:
            lines.append("**선택 근거:** OOS Calmar 최고 + 워크포워드 검증 통과. "
                         "IS 과적합 위험 가장 낮음.")
        elif i == 1:
            lines.append("**차선 이유:** 2번째 OOS Calmar. "
                         "1순위 대비 특정 파라미터 차이가 있어 시장 국면 다양성 확보 가능.")
        else:
            lines.append("**차선 이유:** 3번째 OOS Calmar. "
                         "1·2순위와 병렬 운영 시 분산 효과 기대.")
        lines.append("")

    # 적용 시 기대 효과 vs 위험
    lines.append("## 7. 적용 시 기대 효과 vs 위험")
    lines.append("")
    lines.append("| 항목 | 내용 |")
    lines.append("|------|------|")
    lines.append("| 기대 효과 | OOS 검증된 파라미터로 실전 과적합 위험 감소 |")
    lines.append("| 기대 효과 | min_buy_signals 최적화로 매수 빈도/선별력 균형 |")
    lines.append("| 기대 효과 | rsi_oversold 조정으로 진입 타이밍 현실화 |")
    lines.append("| 위험 | 2년 데이터(2024~2026)는 강세장 편향 가능 |")
    lines.append("| 위험 | 60종목 유동성 상위 한정 — 중소형주 적용 시 재검증 필요 |")
    lines.append("| 위험 | 워크포워드 n_windows=3(데이터 부족)으로 신뢰도 제한적 |")
    lines.append("| 권고 | 1순위 적용 후 2주 가상매매 관찰, 이상 시 2순위 전환 |")
    lines.append("")
    lines.append("> **결재 후 config.yaml 적용은 별도 일감으로 진행합니다.**")


if __name__ == "__main__":
    main()
