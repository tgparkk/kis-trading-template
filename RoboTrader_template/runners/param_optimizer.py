"""
전략 파라미터 최적화 러너 (MultiverseEngine CLI 래퍼)
======================================================
전략의 파라미터 그리드를 탐색하여 순수익(PnL) 최대 조합을 찾는다.

Usage:
    python -m RoboTrader_template.runners.param_optimizer \
        --strategies sample,bb_reversion \
        --stock-codes 005930,000660,035420 \
        --days 90 \
        --n-jobs 4 \
        --min-trades 10 \
        --top-n 20

구성:
    - 각 전략 폴더의 multiverse_grid.yaml 을 읽어 파라미터 조합 생성
    - DB(PriceRepository.get_daily_prices)에서 종목별 일봉 로드
    - backtest.MultiverseEngine 으로 그리드 탐색 (n_jobs 병렬)
    - BacktestResult.total_return 기준 정렬 (initial_capital 고정이므로 PnL 순위 동치)
    - output/param_optimizer_{strategy}_{date}.md 로 상세 리포트 저장
    - stdout 에 전략별 베스트 파라미터 비교 요약 출력
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

_PROJ_ROOT = Path(__file__).parent.parent
if str(_PROJ_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT.parent))
if str(_PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT))

from backtest.multiverse import MultiverseEngine, MultiverseResult  # noqa: E402
from db.repositories.price import PriceRepository  # noqa: E402
from strategies.config import StrategyLoader  # noqa: E402


_LOGGER = logging.getLogger("runners.param_optimizer")
_OUTPUT_DIR = _PROJ_ROOT / "output"
_STRATEGIES_DIR = _PROJ_ROOT / "strategies"
_INITIAL_CAPITAL = 10_000_000.0
_SORT_KEY = "total_return"  # PnL 최대화 = initial_capital 고정 시 total_return 최대와 동치


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="전략 파라미터 최적화 (그리드 탐색, PnL 최대화)")
    p.add_argument("--strategies", required=True,
                   help="쉼표 구분 전략 폴더명. 예: sample,bb_reversion")
    p.add_argument("--stock-codes", required=True,
                   help="쉼표 구분 종목코드. 예: 005930,000660,035420")
    p.add_argument("--days", type=int, default=90,
                   help="DB 일봉 조회 기간 (일, 기본 90)")
    p.add_argument("--n-jobs", type=int, default=4,
                   help="MultiverseEngine 병렬 스레드 수 (기본 4)")
    p.add_argument("--min-trades", type=int, default=10,
                   help="최소 거래 수 필터 (기본 10)")
    p.add_argument("--top-n", type=int, default=20,
                   help="리포트 상위 N개 (기본 20)")
    p.add_argument("--initial-capital", type=float, default=_INITIAL_CAPITAL,
                   help=f"백테스트 초기 자본 (기본 {_INITIAL_CAPITAL:,.0f})")
    p.add_argument("--max-positions", type=int, default=5,
                   help="동시 최대 보유 종목 수 (기본 5)")
    p.add_argument("--position-size-pct", type=float, default=0.2,
                   help="종목당 투자 비율 (기본 0.2)")
    return p.parse_args()


def _load_grid(strategy_name: str) -> Dict[str, List[Any]]:
    """strategies/{name}/multiverse_grid.yaml 로드."""
    grid_path = _STRATEGIES_DIR / strategy_name / "multiverse_grid.yaml"
    if not grid_path.exists():
        raise FileNotFoundError(
            f"파라미터 그리드 파일 없음: {grid_path} - "
            f"해당 전략에 multiverse_grid.yaml 을 생성하세요."
        )
    with open(grid_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not data:
        raise ValueError(f"파라미터 그리드가 비어있습니다: {grid_path}")
    return data


def _load_daily_data(stock_codes: List[str], days: int) -> Dict[str, pd.DataFrame]:
    """DB에서 종목별 일봉 데이터 로드. BacktestEngine 형식에 맞춤."""
    repo = PriceRepository()
    out: Dict[str, pd.DataFrame] = {}
    for code in stock_codes:
        df = repo.get_daily_prices(code, days=days)
        if df is None or df.empty:
            print(f"[WARN] {code}: 일봉 데이터 없음 - 스킵", file=sys.stderr)
            continue
        # BacktestEngine 은 컬럼 [date, open, high, low, close, volume] 요구
        df = df.sort_values("date").reset_index(drop=True)
        out[code] = df
    return out


def _total_pnl(initial_capital: float, total_return: float) -> float:
    """total_return(비율) → 절대 PnL 금액."""
    return initial_capital * float(total_return)


def _build_top_dataframe(result: MultiverseResult, top_n: int,
                        initial_capital: float) -> pd.DataFrame:
    """MultiverseResult 에서 total_return 기준 top_n DataFrame + 절대 PnL 컬럼 추가."""
    df = result.top(n=top_n, sort_by=_SORT_KEY)
    if df.empty:
        return df
    df = df.copy()
    df.insert(0, "pnl_krw", (df["total_return"] * initial_capital).round(0).astype(int))
    return df


def _df_to_markdown(df: pd.DataFrame) -> str:
    """tabulate 의존성 없이 DataFrame 을 Markdown 테이블로 변환."""
    if df.empty:
        return "_(비어있음)_"
    headers = ["#"] + [str(c) for c in df.columns]
    sep = ["---"] * len(headers)
    rows = [headers, sep]
    for idx, row in df.iterrows():
        values = [str(idx)]
        for c in df.columns:
            v = row[c]
            if isinstance(v, float):
                values.append(f"{v:.4f}")
            else:
                values.append(str(v))
        rows.append(values)
    return "\n".join("| " + " | ".join(r) + " |" for r in rows)


def _write_markdown(strategy_name: str, result: MultiverseResult,
                   top_n: int, initial_capital: float,
                   stock_codes: List[str], days: int, out_path: Path) -> None:
    """전략별 상세 리포트 Markdown 저장 (PnL 기준 정렬)."""
    df = _build_top_dataframe(result, top_n, initial_capital)

    lines: List[str] = []
    lines.append(f"# 파라미터 최적화 결과 — {strategy_name}")
    lines.append("")
    lines.append(f"- **정렬 기준**: PnL 최대 (`total_return` × initial_capital)")
    lines.append(f"- **초기 자본**: {initial_capital:,.0f}원")
    lines.append(f"- **대상 종목**: {', '.join(stock_codes)} ({len(stock_codes)}개)")
    lines.append(f"- **조회 기간**: 최근 {days}일")
    lines.append(f"- **전체 조합**: {result.total_combinations:,}개")
    lines.append(f"- **min_trades 통과**: {result.filtered_count:,}개")
    lines.append(f"- **소요 시간**: {result.elapsed_seconds:.1f}초")
    lines.append("")

    lines.append(f"## Top {top_n} (PnL 기준)")
    lines.append("")
    if df.empty:
        lines.append("_(결과 없음 — min_trades 필터를 낮추거나 그리드/데이터를 확인하세요.)_")
    else:
        lines.append(_df_to_markdown(df))
    lines.append("")

    top_stability = min(5, top_n)
    lines.append("## 안정성 리포트 — PnL 기준 (이웃 파라미터 비교)")
    lines.append("")
    lines.append("```")
    lines.append(result.stability_report(top_n=top_stability, metric="pnl"))
    lines.append("```")
    lines.append("")
    lines.append("## 안정성 리포트 — Sharpe 기준 (참고)")
    lines.append("")
    lines.append("```")
    lines.append(result.stability_report(top_n=top_stability, metric="sharpe"))
    lines.append("```")
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _run_one_strategy(strategy_name: str, daily_data: Dict[str, pd.DataFrame],
                     stock_codes: List[str], args: argparse.Namespace) -> Optional[Dict]:
    """단일 전략에 대해 MultiverseEngine 실행. 베스트 요약 dict 반환."""
    print(f"\n[OPT] 전략={strategy_name} 시작")

    try:
        strategy_class = StrategyLoader._load_strategy_class(strategy_name)
    except Exception as e:
        print(f"[OPT] 전략 클래스 로드 실패: {strategy_name} - {e}", file=sys.stderr)
        return None

    try:
        grid = _load_grid(strategy_name)
    except Exception as e:
        print(f"[OPT] 그리드 로드 실패: {strategy_name} - {e}", file=sys.stderr)
        return None

    mv = MultiverseEngine(
        strategy_class=strategy_class,
        daily_data=daily_data,
        stock_codes=stock_codes,
        initial_capital=args.initial_capital,
        max_positions=args.max_positions,
        position_size_pct=args.position_size_pct,
    )
    for key, values in grid.items():
        if not isinstance(values, list) or not values:
            print(f"[OPT] 그리드 항목 무시: {key}={values!r} (리스트 아님 또는 비어있음)", file=sys.stderr)
            continue
        mv.add_param(key, values)

    t0 = datetime.now()
    result = mv.run(min_trades=args.min_trades, n_jobs=args.n_jobs)
    elapsed = (datetime.now() - t0).total_seconds()
    print(f"[OPT] 전략={strategy_name} 완료 "
          f"(조합 {result.total_combinations:,} → 필터 통과 {result.filtered_count:,}, "
          f"소요 {elapsed:.1f}초)")

    date_tag = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_path = _OUTPUT_DIR / f"param_optimizer_{strategy_name}_{date_tag}.md"
    _write_markdown(strategy_name, result, args.top_n, args.initial_capital,
                    stock_codes, args.days, out_path)
    print(f"[OPT] 리포트 저장: {out_path}")

    df = _build_top_dataframe(result, 1, args.initial_capital)
    if df.empty:
        return {
            "strategy": strategy_name,
            "best_pnl": None,
            "best_params": None,
            "filtered_count": result.filtered_count,
            "total_combinations": result.total_combinations,
            "report_path": str(out_path),
        }
    row = df.iloc[0].to_dict()
    metric_cols = {
        "pnl_krw", "total_return", "win_rate", "sharpe_ratio",
        "max_drawdown", "total_trades",
        "stability_score", "stability_grade",
        "sharpe_stability_score", "sharpe_stability_grade",
        "pnl_stability_score", "pnl_stability_grade",
    }
    param_cols = [c for c in df.columns if c not in metric_cols]
    best_params = {c: row[c] for c in param_cols}
    return {
        "strategy": strategy_name,
        "best_pnl": int(row["pnl_krw"]),
        "best_return": float(row["total_return"]),
        "best_trades": int(row["total_trades"]),
        "best_win_rate": float(row["win_rate"]),
        "best_mdd": float(row["max_drawdown"]),
        "pnl_stability_grade": str(row.get("pnl_stability_grade", "")),
        "sharpe_stability_grade": str(row.get("sharpe_stability_grade", "")),
        "best_params": best_params,
        "filtered_count": result.filtered_count,
        "total_combinations": result.total_combinations,
        "report_path": str(out_path),
    }


def _print_summary(summaries: List[Dict]) -> None:
    """전략별 베스트 비교 요약을 stdout 에 출력."""
    print("\n" + "=" * 70)
    print("전략별 베스트 파라미터 비교 (PnL 기준)")
    print("=" * 70)
    if not summaries:
        print("(결과 없음)")
        return

    summaries_sorted = sorted(
        summaries,
        key=lambda s: (s.get("best_pnl") if s.get("best_pnl") is not None else -10**18),
        reverse=True,
    )
    for s in summaries_sorted:
        print(f"\n[{s['strategy']}]")
        if s.get("best_pnl") is None:
            print(f"  베스트 없음 (min_trades 미달)")
        else:
            print(f"  베스트 PnL: {s['best_pnl']:+,}원 "
                  f"({s['best_return']*100:+.2f}%)")
            print(f"  거래수 {s['best_trades']}건, 승률 {s['best_win_rate']*100:.1f}%, "
                  f"MDD {s['best_mdd']*100:.2f}%, "
                  f"PnL안정성 [{s['pnl_stability_grade']}] / Sharpe안정성 [{s['sharpe_stability_grade']}]")
            print(f"  파라미터: {s['best_params']}")
        print(f"  조합 {s['total_combinations']:,} → 통과 {s['filtered_count']:,}")
        print(f"  리포트: {s['report_path']}")
    print("\n" + "=" * 70)


def main() -> int:
    args = _parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")

    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    stock_codes = [c.strip() for c in args.stock_codes.split(",") if c.strip()]
    if not strategies or not stock_codes:
        print("[OPT] 오류: --strategies 와 --stock-codes 는 최소 1개 필요", file=sys.stderr)
        return 2

    print(f"[OPT] 전략={strategies}, 종목={stock_codes}, 기간={args.days}일, "
          f"n_jobs={args.n_jobs}, min_trades={args.min_trades}")

    daily_data = _load_daily_data(stock_codes, args.days)
    if not daily_data:
        print("[OPT] 오류: 일봉 데이터가 하나도 로드되지 않았습니다.", file=sys.stderr)
        return 3
    loaded_codes = list(daily_data.keys())
    print(f"[OPT] 일봉 로드 완료: {len(loaded_codes)}종목 "
          f"(평균 {sum(len(v) for v in daily_data.values())/len(daily_data):.0f}일)")

    summaries: List[Dict] = []
    for name in strategies:
        summary = _run_one_strategy(name, daily_data, loaded_codes, args)
        if summary is not None:
            summaries.append(summary)

    _print_summary(summaries)
    return 0 if summaries else 4


if __name__ == "__main__":
    sys.exit(main())
