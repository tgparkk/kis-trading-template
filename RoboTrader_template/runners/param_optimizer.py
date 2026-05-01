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

    # 스크리너 그리드 이중 루프 (K 스크리너 조합 × M 전략 조합)
    python -m RoboTrader_template.runners.param_optimizer \
        --strategies bb_reversion \
        --stock-codes 015760,008350 \
        --days 120 --n-jobs 4 --min-trades 1 --top-n 5 \
        --screener-grid --max-combinations 50

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
import itertools
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
from strategies.screener_base import ScreenerBase  # noqa: E402
from runners._adapter_factory import build_adapter  # noqa: E402


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
                   help="쉼표 구분 종목코드. 예: 005930,000660,035420 "
                        "(screener-grid ON 시 fallback 실패한 조합의 기본값으로 사용)")
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
    # ------ 스크리너 그리드 옵션 ------
    p.add_argument("--screener-grid", action="store_true",
                   help="활성 시 multiverse_grid.yaml 의 screening.* 키를 스크리너 파라미터 "
                        "그리드로 분리하여 K(스크리너) × M(전략) 이중 탐색을 수행한다.")
    p.add_argument("--snapshot-date", default="today",
                   help="스냅샷 DB 조회 기준일. today | YYYY-MM-DD (기본 today)")
    p.add_argument("--max-combinations", type=int, default=100,
                   help="스크리너 × 전략 파라미터 조합 안전 상한 (기본 100). "
                        "초과 시 에러로 종료하고 그리드 축소를 권고한다.")
    # ------ IS/OOS · 워크포워드 옵션 ------
    p.add_argument("--start",
                   help="백테스트 시작일 YYYY-MM-DD. --start/--end 가 모두 있으면 --days 무시.")
    p.add_argument("--end",
                   help="백테스트 종료일 YYYY-MM-DD.")
    p.add_argument("--oos-ratio", type=float, default=0.2,
                   help="OOS 비율 (0.0~1.0, 기본 0.2). --mode oos_split 시 사용.")
    p.add_argument("--mode", choices=["plain", "oos_split", "walkforward"], default="plain",
                   help="실행 모드: plain(기본) | oos_split(IS/OOS 분리) | walkforward(워크포워드)")
    p.add_argument("--is-window", type=int, default=252,
                   help="워크포워드 IS 기간 (캘린더일, 기본 252). --mode walkforward 시 사용.")
    p.add_argument("--oos-window", type=int, default=63,
                   help="워크포워드 OOS 기간 (캘린더일, 기본 63). --mode walkforward 시 사용.")
    p.add_argument("--n-windows", type=int, default=6,
                   help="워크포워드 윈도우 수 (기본 6). --mode walkforward 시 사용.")
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


def _split_grid(grid: Dict[str, List[Any]]) -> Tuple[Dict[str, List[Any]], Dict[str, List[Any]]]:
    """그리드를 screening.* 키(스크리너용)와 나머지(전략용)로 분리."""
    screening: Dict[str, List[Any]] = {}
    strategy: Dict[str, List[Any]] = {}
    for key, values in grid.items():
        if key.startswith("screening."):
            # screening.target_sectors → target_sectors
            short_key = key[len("screening."):]
            screening[short_key] = values
        else:
            strategy[key] = values
    return screening, strategy


def _expand_screening_grid(screening_grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    """screening 그리드의 카르테시안 곱으로 파라미터 조합 목록 반환."""
    if not screening_grid:
        return [{}]
    keys = list(screening_grid.keys())
    value_lists = [screening_grid[k] for k in keys]
    combos = []
    for combo_values in itertools.product(*value_lists):
        combos.append(dict(zip(keys, combo_values)))
    return combos


def _resolve_scan_date(snapshot_date_str: str) -> date:
    """today | YYYY-MM-DD 문자열을 date 객체로 변환."""
    if snapshot_date_str.lower() == "today":
        return datetime.now().date()
    try:
        return datetime.strptime(snapshot_date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"날짜 형식 오류 (today | YYYY-MM-DD): {snapshot_date_str!r}")


def _get_stock_codes_from_snapshot(
    strategy_name: str,
    scan_date: date,
    screening_params: Dict[str, Any],
) -> Optional[List[str]]:
    """
    DB 스냅샷 조회 → 없으면 어댑터 fallback scan() 호출.
    stock_code 목록 반환. 완전 실패 시 None 반환(조합 skip 신호).
    """
    params_hash = ScreenerBase.compute_params_hash(screening_params)

    # DB 조회 시도
    try:
        from db.database_manager import DatabaseManager
        db = DatabaseManager()
        rows = db.candidate_repo.get_screener_snapshot(strategy_name, scan_date, params_hash)
        if rows:
            codes = [r["stock_code"] for r in rows if r.get("stock_code")]
            if codes:
                return codes
    except Exception as e:
        _LOGGER.warning("DB 스냅샷 조회 실패 (%s): %s — fallback 시도", strategy_name, e)

    # fallback: 어댑터 직접 scan()
    _LOGGER.warning(
        "[screener-grid] 스냅샷 없음 (%s, %s, hash=%s…) — 현재 시점 scan() fallback 사용",
        strategy_name, scan_date, params_hash[:8],
    )
    adapter = build_adapter(strategy_name)
    if adapter is None:
        _LOGGER.warning("[screener-grid] 어댑터 생성 실패 (%s) — 이 조합 skip", strategy_name)
        return None

    try:
        candidates = adapter.scan(scan_date, screening_params)
        codes = [c.code for c in candidates if c.code]
        if not codes:
            _LOGGER.warning(
                "[screener-grid] scan() 결과 0건 (%s, params=%s) — 이 조합 skip",
                strategy_name, screening_params,
            )
            return None
        return codes
    except Exception as e:
        _LOGGER.warning(
            "[screener-grid] scan() 실패 (%s, params=%s): %s — 이 조합 skip",
            strategy_name, screening_params, e,
        )
        return None


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
                   stock_codes: List[str], days: int, out_path: Path,
                   screening_params: Optional[Dict[str, Any]] = None) -> None:
    """전략별 상세 리포트 Markdown 저장 (PnL 기준 정렬)."""
    df = _build_top_dataframe(result, top_n, initial_capital)

    lines: List[str] = []
    lines.append(f"# 파라미터 최적화 결과 — {strategy_name}")
    lines.append("")
    lines.append(f"- **정렬 기준**: PnL 최대 (`total_return` × initial_capital)")
    lines.append(f"- **초기 자본**: {initial_capital:,.0f}원")
    lines.append(f"- **대상 종목**: {', '.join(stock_codes)} ({len(stock_codes)}개)")
    lines.append(f"- **조회 기간**: 최근 {days}일")
    if screening_params:
        lines.append(f"- **스크리너 파라미터**: {screening_params}")
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


def _write_screener_grid_markdown(
    strategy_name: str,
    all_rows: List[Dict[str, Any]],
    top_n: int,
    initial_capital: float,
    days: int,
    screener_combo_count: int,
    strategy_combo_count: int,
    total_backtests: int,
    out_path: Path,
) -> None:
    """스크리너 그리드 이중 루프 결과 통합 Markdown 저장."""
    lines: List[str] = []
    lines.append(f"# 스크리너 그리드 최적화 결과 — {strategy_name}")
    lines.append("")
    lines.append(f"- **초기 자본**: {initial_capital:,.0f}원")
    lines.append(f"- **조회 기간**: 최근 {days}일")
    lines.append(f"- **스크리너 조합**: {screener_combo_count}개")
    lines.append(f"- **전략 파라미터 조합**: {strategy_combo_count}개")
    lines.append(f"- **총 백테스트**: {total_backtests}개")
    lines.append("")

    if not all_rows:
        lines.append("_(결과 없음 — 모든 스크리너 조합이 skip 되었거나 min_trades 미달)_")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return

    df = pd.DataFrame(all_rows)
    df = df.sort_values("pnl_krw", ascending=False).head(top_n).reset_index(drop=True)

    lines.append(f"## Top {top_n} 전체 조합 (PnL 기준)")
    lines.append("")
    lines.append(_df_to_markdown(df))
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _resolve_date_range(args: argparse.Namespace) -> Tuple[Optional[str], Optional[str]]:
    """--start/--end 또는 --days 에서 (start_date, end_date) 결정."""
    if args.start and args.end:
        return args.start, args.end
    if args.start or args.end:
        # 한쪽만 있으면 경고 후 days 사용
        print(f"[OPT] 경고: --start 와 --end 는 함께 사용해야 합니다. --days={args.days} 로 폴백.",
              file=sys.stderr)
    return None, None


def _run_mv(
    strategy_class: Any,
    daily_data: Dict[str, pd.DataFrame],
    stock_codes: List[str],
    strategy_grid: Dict[str, List[Any]],
    args: argparse.Namespace,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> MultiverseResult:
    """MultiverseEngine 생성 + 전략 파라미터 그리드 추가 후 실행.

    Args:
        start_date: 백테스트 시작일 (None이면 데이터 전체).
        end_date: 백테스트 종료일 (None이면 데이터 전체).
    """
    mv = MultiverseEngine(
        strategy_class=strategy_class,
        daily_data=daily_data,
        stock_codes=stock_codes,
        initial_capital=args.initial_capital,
        max_positions=args.max_positions,
        position_size_pct=args.position_size_pct,
        start_date=start_date,
        end_date=end_date,
    )
    for key, values in strategy_grid.items():
        if not isinstance(values, list) or not values:
            print(f"[OPT] 그리드 항목 무시: {key}={values!r} (리스트 아님 또는 비어있음)",
                  file=sys.stderr)
            continue
        mv.add_param(key, values)

    mode = getattr(args, "mode", "plain")
    if mode == "oos_split":
        s, e = _resolve_date_range(args)
        if s is None or e is None:
            print("[OPT] --mode oos_split 은 --start 와 --end 가 필요합니다.", file=sys.stderr)
            return mv.run(min_trades=args.min_trades, n_jobs=args.n_jobs)
        return mv.run_oos_split(
            start=s, end=e,
            oos_ratio=args.oos_ratio,
            min_trades=args.min_trades,
            n_jobs=args.n_jobs,
        )
    elif mode == "walkforward":
        s, e = _resolve_date_range(args)
        if s is None or e is None:
            print("[OPT] --mode walkforward 은 --start 와 --end 가 필요합니다.", file=sys.stderr)
            return mv.run(min_trades=args.min_trades, n_jobs=args.n_jobs)
        return mv.run_walkforward(
            start=s, end=e,
            is_window=args.is_window,
            oos_window=args.oos_window,
            n_windows=args.n_windows,
            min_trades=args.min_trades,
            n_jobs=args.n_jobs,
        )
    else:
        return mv.run(min_trades=args.min_trades, n_jobs=args.n_jobs)


def _extract_summary_from_result(
    strategy_name: str,
    result: MultiverseResult,
    args: argparse.Namespace,
    report_path: str,
    screening_params: Optional[Dict[str, Any]] = None,
) -> Dict:
    """MultiverseResult 에서 베스트 요약 dict 생성."""
    df = _build_top_dataframe(result, 1, args.initial_capital)
    base = {
        "strategy": strategy_name,
        "filtered_count": result.filtered_count,
        "total_combinations": result.total_combinations,
        "report_path": report_path,
        "screening_params": screening_params,
    }
    if df.empty:
        return {**base, "best_pnl": None, "best_params": None}

    row = df.iloc[0].to_dict()
    metric_cols = {
        "pnl_krw", "total_return", "win_rate", "sharpe_ratio",
        "max_drawdown", "total_trades",
        "stability_score", "stability_grade",
        "sharpe_stability_score", "sharpe_stability_grade",
        "pnl_stability_score", "pnl_stability_grade",
    }
    param_cols = [c for c in df.columns if c not in metric_cols]
    return {
        **base,
        "best_pnl": int(row["pnl_krw"]),
        "best_return": float(row["total_return"]),
        "best_trades": int(row["total_trades"]),
        "best_win_rate": float(row["win_rate"]),
        "best_mdd": float(row["max_drawdown"]),
        "pnl_stability_grade": str(row.get("pnl_stability_grade", "")),
        "sharpe_stability_grade": str(row.get("sharpe_stability_grade", "")),
        "best_params": {c: row[c] for c in param_cols},
    }


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
        raw_grid = _load_grid(strategy_name)
    except Exception as e:
        print(f"[OPT] 그리드 로드 실패: {strategy_name} - {e}", file=sys.stderr)
        return None

    if args.screener_grid:
        return _run_one_strategy_screener_grid(
            strategy_name, strategy_class, raw_grid, daily_data, stock_codes, args,
        )

    # ---- 기존 경로 (screener-grid OFF) ----
    t0 = datetime.now()
    result = _run_mv(strategy_class, daily_data, stock_codes, raw_grid, args)
    elapsed = (datetime.now() - t0).total_seconds()
    print(f"[OPT] 전략={strategy_name} 완료 "
          f"(조합 {result.total_combinations:,} → 필터 통과 {result.filtered_count:,}, "
          f"소요 {elapsed:.1f}초)")

    date_tag = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_path = _OUTPUT_DIR / f"param_optimizer_{strategy_name}_{date_tag}.md"
    _write_markdown(strategy_name, result, args.top_n, args.initial_capital,
                    stock_codes, args.days, out_path)
    print(f"[OPT] 리포트 저장: {out_path}")

    return _extract_summary_from_result(strategy_name, result, args, str(out_path))


def _run_one_strategy_screener_grid(
    strategy_name: str,
    strategy_class: Any,
    raw_grid: Dict[str, List[Any]],
    base_daily_data: Dict[str, pd.DataFrame],
    fallback_codes: List[str],
    args: argparse.Namespace,
) -> Optional[Dict]:
    """스크리너 그리드 이중 루프: K 스크리너 조합 × M 전략 조합."""
    screening_grid, strategy_grid = _split_grid(raw_grid)

    if not screening_grid:
        print(f"[OPT] screener-grid 활성이지만 {strategy_name}/multiverse_grid.yaml 에 "
              f"screening.* 키가 없음 — 기존 단일 경로로 폴백", file=sys.stderr)
        t0 = datetime.now()
        result = _run_mv(strategy_class, base_daily_data, fallback_codes, raw_grid, args)
        elapsed = (datetime.now() - t0).total_seconds()
        date_tag = datetime.now().strftime("%Y-%m-%d_%H%M")
        out_path = _OUTPUT_DIR / f"param_optimizer_{strategy_name}_{date_tag}.md"
        _write_markdown(strategy_name, result, args.top_n, args.initial_capital,
                        fallback_codes, args.days, out_path)
        print(f"[OPT] 리포트 저장: {out_path}")
        return _extract_summary_from_result(strategy_name, result, args, str(out_path))

    screener_combos = _expand_screening_grid(screening_grid)
    # 전략 파라미터 조합 수 추산 (곱)
    strategy_combo_count = 1
    for values in strategy_grid.values():
        if isinstance(values, list) and values:
            strategy_combo_count *= len(values)

    total_combos = len(screener_combos) * strategy_combo_count
    print(f"[OPT] 스크리너 {len(screener_combos)}조합 × 전략 {strategy_combo_count}조합 "
          f"= {total_combos}개 백테스트 예정")

    if total_combos > args.max_combinations:
        print(
            f"[OPT] 오류: 조합 수 {total_combos}개가 --max-combinations {args.max_combinations}개를 초과합니다.\n"
            f"  권고: screening.* 그리드 축소 또는 --max-combinations 값 상향 후 재시도하세요.",
            file=sys.stderr,
        )
        return None

    scan_date = _resolve_scan_date(args.snapshot_date)
    price_repo = PriceRepository()
    date_tag = datetime.now().strftime("%Y-%m-%d_%H%M")

    all_rows: List[Dict[str, Any]] = []
    best_summary: Optional[Dict] = None
    skipped = 0
    executed = 0

    for s_idx, screening_params in enumerate(screener_combos, 1):
        print(f"[OPT] 스크리너 조합 {s_idx}/{len(screener_combos)}: {screening_params}")

        # 종목 코드 결정 (스냅샷 → fallback scan → fallback_codes)
        codes = _get_stock_codes_from_snapshot(strategy_name, scan_date, screening_params)
        if codes is None:
            print(f"[OPT]   → skip (종목 0건 또는 어댑터 실패)", file=sys.stderr)
            skipped += 1
            continue

        # 일봉 로드 (새 종목만 추가, 기존 캐시 재활용)
        daily_data = dict(base_daily_data)  # 얕은 복사
        new_codes = [c for c in codes if c not in daily_data]
        if new_codes:
            for code in new_codes:
                df = price_repo.get_daily_prices(code, days=args.days)
                if df is not None and not df.empty:
                    daily_data[code] = df.sort_values("date").reset_index(drop=True)

        codes_available = [c for c in codes if c in daily_data]
        if not codes_available:
            print(f"[OPT]   → skip (일봉 데이터 없음)", file=sys.stderr)
            skipped += 1
            continue

        print(f"[OPT]   → {len(codes_available)}종목으로 전략 그리드 탐색")
        t0 = datetime.now()
        result = _run_mv(strategy_class, daily_data, codes_available, strategy_grid, args)
        elapsed = (datetime.now() - t0).total_seconds()
        executed += 1

        print(f"[OPT]   조합 {result.total_combinations:,} → "
              f"통과 {result.filtered_count:,}, {elapsed:.1f}초")

        # 개별 리포트
        out_path = _OUTPUT_DIR / f"param_optimizer_{strategy_name}_sc{s_idx}_{date_tag}.md"
        _write_markdown(strategy_name, result, args.top_n, args.initial_capital,
                        codes_available, args.days, out_path, screening_params)

        # 전체 통합 테이블용 행 수집
        top_df = _build_top_dataframe(result, args.top_n, args.initial_capital)
        if not top_df.empty:
            for _, row in top_df.iterrows():
                row_dict = row.to_dict()
                # screening 정보 컬럼 앞에 추가
                for sk, sv in screening_params.items():
                    row_dict[f"screening_{sk}"] = str(sv)
                all_rows.append(row_dict)

        # 베스트 추적
        summary = _extract_summary_from_result(
            strategy_name, result, args, str(out_path), screening_params,
        )
        if summary.get("best_pnl") is not None:
            if best_summary is None or summary["best_pnl"] > (best_summary.get("best_pnl") or -10**18):
                best_summary = summary

    # 통합 리포트
    combined_path = _OUTPUT_DIR / f"param_optimizer_{strategy_name}_combined_{date_tag}.md"
    _write_screener_grid_markdown(
        strategy_name, all_rows, args.top_n, args.initial_capital, args.days,
        len(screener_combos), strategy_combo_count, total_combos, combined_path,
    )
    print(f"[OPT] 통합 리포트 저장: {combined_path}")
    print(f"[OPT] 완료: {executed}조합 실행, {skipped}조합 skip")

    if best_summary is None:
        return {
            "strategy": strategy_name,
            "best_pnl": None,
            "best_params": None,
            "screening_params": None,
            "filtered_count": 0,
            "total_combinations": total_combos,
            "report_path": str(combined_path),
        }
    best_summary["report_path"] = str(combined_path)
    return best_summary


def _print_summary(summaries: List[Dict], screener_grid: bool = False) -> None:
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
        if screener_grid:
            sc = s.get("screening_params")
            k_count = s.get("total_combinations", 0)
            print(f"  K 스크리너 조합 × M 전략 조합 = {k_count:,} 백테스트")
        if s.get("best_pnl") is None:
            print(f"  베스트 없음 (min_trades 미달 또는 전체 skip)")
        else:
            print(f"  베스트 PnL: {s['best_pnl']:+,}원 "
                  f"({s['best_return']*100:+.2f}%)")
            print(f"  거래수 {s['best_trades']}건, 승률 {s['best_win_rate']*100:.1f}%, "
                  f"MDD {s['best_mdd']*100:.2f}%, "
                  f"PnL안정성 [{s['pnl_stability_grade']}] / Sharpe안정성 [{s['sharpe_stability_grade']}]")
            if screener_grid and s.get("screening_params"):
                print(f"  베스트 screening: {s['screening_params']}")
            print(f"  베스트 parameters: {s['best_params']}")
        if not screener_grid:
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

    # --snapshot-date 유효성 검사
    if args.screener_grid:
        try:
            _resolve_scan_date(args.snapshot_date)
        except ValueError as e:
            print(f"[OPT] 오류: {e}", file=sys.stderr)
            return 2

    print(f"[OPT] 전략={strategies}, 종목={stock_codes}, 기간={args.days}일, "
          f"n_jobs={args.n_jobs}, min_trades={args.min_trades}"
          + (f", screener-grid=ON, snapshot-date={args.snapshot_date}, "
             f"max-combinations={args.max_combinations}" if args.screener_grid else ""))

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

    _print_summary(summaries, screener_grid=args.screener_grid)
    return 0 if summaries else 4


if __name__ == "__main__":
    sys.exit(main())
