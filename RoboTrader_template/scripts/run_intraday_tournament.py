"""분봉 데이트레이딩 10전략 토너먼트 1라운드.

조합: strategies × universes × max_positions × sl × tp = 10 × 2 × 3 × 1 × 1 = 60 시나리오 (SL/TP 그리드 미지정 시)
      SL/TP 그리드 지정 시: 10 × 2 × 3 × |sl_grid| × |tp_grid|
각 시나리오: 약 168거래일 분봉 시뮬, 평가 지표 8종 계산

실제 실행은 4~24시간 소요 - 매니저가 수동으로 시작합니다.

사용 예:
    python scripts/run_intraday_tournament.py \\
        --start 20250901 --end 20260515 \\
        --skip 202603 \\
        --capital 10000000 \\
        --max-positions 3 4 5 \\
        --universe screener,dynamic \\
        --strategies all \\
        --eod 15:20 \\
        --slip-bps 5 \\
        --out reports/tournament_round1

    # SL/TP 그리드 지정 예시 (384 시나리오):
    python scripts/run_intraday_tournament.py \\
        --start 20250901 --end 20260515 \\
        --strategies vwap_trade,orb,reversal_vwap,red_to_green \\
        --universe screener,dynamic \\
        --max-positions 3 4 5 \\
        --sl-grid 0.005,0.01,0.02,0.03 \\
        --tp-grid 0.01,0.02,0.04,0.06 \\
        --eod 15:20 --slip-bps 5 \\
        --out reports/tournament_sl_tp_grid
"""
from __future__ import annotations

import argparse
import importlib
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

import pandas as pd

# 프로젝트 루트를 sys.path에 추가 (scripts/ 에서 직접 실행 시 필요)
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backtest.engine import BacktestEngine
from backtest.tournament_metrics import compute_metrics, _rank_by_composite
from utils.logger import setup_logger

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# 전략 레지스트리
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: dict[str, object] = {
    "abcd_pattern":        "strategies.intraday.abcd_pattern.strategy.AbcdPatternStrategy",
    "bull_flag":           "strategies.intraday.bull_flag.strategy.BullFlagStrategy",
    "reversal_rsi":        "strategies.intraday.reversal_rsi.strategy.ReversalRsiStrategy",
    "reversal_vwap":       "strategies.intraday.reversal_vwap.strategy.ReversalVwapStrategy",
    "ma_trend":            "strategies.intraday.ma_trend.strategy.MaTrendStrategy",
    "vwap_trade":          "strategies.intraday.vwap_trade.strategy.VwapTradeStrategy",
    "support_resistance":  "strategies.intraday.support_resistance.strategy.SupportResistanceStrategy",
    "red_to_green":        "strategies.intraday.red_to_green.strategy.RedToGreenStrategy",
    "orb":                 "strategies.intraday.orb.strategy.OrbStrategy",
    "pullback":            "strategies.intraday.pullback.strategy.PullbackStrategy",
    # ORB v2 — 거래량 임계값(0.5/1.0/1.5/2.0) × 시장환경 필터(off/on) = 8 entries
    "orb_v2_vr05_nomkt": {"class": "strategies.intraday.orb_v2.strategy.OrbV2Strategy",
                           "params": {"parameters": {"volume_ratio_threshold": 0.5, "use_market_filter": False}}},
    "orb_v2_vr05_mkt":   {"class": "strategies.intraday.orb_v2.strategy.OrbV2Strategy",
                           "params": {"parameters": {"volume_ratio_threshold": 0.5, "use_market_filter": True}}},
    "orb_v2_vr10_nomkt": {"class": "strategies.intraday.orb_v2.strategy.OrbV2Strategy",
                           "params": {"parameters": {"volume_ratio_threshold": 1.0, "use_market_filter": False}}},
    "orb_v2_vr10_mkt":   {"class": "strategies.intraday.orb_v2.strategy.OrbV2Strategy",
                           "params": {"parameters": {"volume_ratio_threshold": 1.0, "use_market_filter": True}}},
    "orb_v2_vr15_nomkt": {"class": "strategies.intraday.orb_v2.strategy.OrbV2Strategy",
                           "params": {"parameters": {"volume_ratio_threshold": 1.5, "use_market_filter": False}}},
    "orb_v2_vr15_mkt":   {"class": "strategies.intraday.orb_v2.strategy.OrbV2Strategy",
                           "params": {"parameters": {"volume_ratio_threshold": 1.5, "use_market_filter": True}}},
    "orb_v2_vr20_nomkt": {"class": "strategies.intraday.orb_v2.strategy.OrbV2Strategy",
                           "params": {"parameters": {"volume_ratio_threshold": 2.0, "use_market_filter": False}}},
    "orb_v2_vr20_mkt":   {"class": "strategies.intraday.orb_v2.strategy.OrbV2Strategy",
                           "params": {"parameters": {"volume_ratio_threshold": 2.0, "use_market_filter": True}}},
}


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _load_strategy(key: str):
    """레지스트리 키 → BaseStrategy 인스턴스 (string 또는 dict 형식 둘 다 지원)."""
    entry = STRATEGY_REGISTRY[key]
    if isinstance(entry, str):
        dotpath = entry
        params = {}
    elif isinstance(entry, dict):
        dotpath = entry["class"]
        params = entry.get("params", {})
    else:
        raise TypeError(f"Unsupported STRATEGY_REGISTRY entry type for {key}: {type(entry)}")

    module_path, cls_name = dotpath.rsplit(".", 1)
    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, cls_name)
        return cls(params)
    except Exception as exc:
        logger.error(f"전략 로드 실패 [{key}]: {exc}")
        raise


def _make_screener_provider() -> Callable[[str], List[str]]:
    """screener_snapshots DB에서 날짜별 후보 코드를 반환하는 콜백.

    run_minute()의 candidate_provider 시그니처: (trade_date: str) -> List[str]

    성능 최적화:
    - psycopg2.connect() 직접 호출 대신 DatabaseConnection 풀 재사용
    - pd.read_sql (SQLAlchemy import ~0.25초) 대신 cursor 직접 사용
    """
    from db.connection import DatabaseConnection

    _cache: dict[str, List[str]] = {}

    def _provider(trade_date: str) -> List[str]:
        if trade_date in _cache:
            return _cache[trade_date]

        # trade_date: YYYYMMDD → YYYY-MM-DD (screener_snapshots.scan_date 형식)
        if len(trade_date) == 8:
            date_key = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        else:
            date_key = trade_date

        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT DISTINCT stock_code FROM screener_snapshots WHERE scan_date = %s",
                    (date_key,),
                )
                rows = cursor.fetchall()
                cursor.close()
            codes = [row[0] for row in rows]
        except Exception as exc:
            logger.warning(f"screener_snapshots 조회 실패 [{trade_date}]: {exc}")
            codes = []

        _cache[trade_date] = codes
        return codes

    return _provider


def _make_dynamic_provider(
    cache_dir: Optional[str] = None,
    top_n: int = 50,
    rank_by: str = "volatility_pct",
) -> Callable[[str], List[str]]:
    """intraday_universe.build_universe_for_date 기반 동적 provider.

    직원 A의 산출물 - import 실패 시 빈 리스트 반환하는 stub으로 대체.

    Args:
        cache_dir: Parquet 캐시 디렉토리. None이면 캐시 미사용.
        top_n: dynamic universe 상위 N개로 cap. 0이면 무제한.
        rank_by: top_n 적용 기준 컬럼명 ("volatility_pct" 또는 "amount_sum").
    """
    cache_path: Optional[Path] = Path(cache_dir) if cache_dir else None
    effective_top_n: Optional[int] = top_n if top_n > 0 else None

    try:
        from utils.intraday_universe import build_universe_for_date as _build

        def _provider(trade_date: str) -> List[str]:
            try:
                return _build(
                    trade_date,
                    cache_dir=cache_path,
                    top_n=effective_top_n,
                    rank_by=rank_by,
                )
            except Exception as exc:
                logger.warning(f"dynamic universe 조회 실패 [{trade_date}]: {exc}")
                return []

    except ImportError:
        logger.warning(
            "utils.intraday_universe 로드 불가 - dynamic provider를 stub으로 대체합니다."
        )

        def _provider(trade_date: str) -> List[str]:  # type: ignore[misc]
            return []

    return _provider


def _parse_skip_dates(raw_list: Optional[List[str]]) -> Set[str]:
    """CLI --skip 값 리스트 → set (완전 일치 + prefix 모두 지원)."""
    if not raw_list:
        return set()
    return set(raw_list)


def _write_report_md(df: pd.DataFrame, out_dir: Path) -> None:
    """tournament_round1_summary.md 작성.

    tabulate가 없으면 to_markdown() 대신 단순 텍스트 표 사용.
    """
    def _to_table(sub: pd.DataFrame, cols: List[str]) -> str:
        try:
            return sub[cols].to_markdown(index=False)
        except ImportError:
            # tabulate 없는 환경: 헤더 + 데이터 직접 포맷
            lines = ["| " + " | ".join(str(c) for c in cols) + " |"]
            lines.append("|" + "|".join(["---"] * len(cols)) + "|")
            for _, row in sub[cols].iterrows():
                lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
            return "\n".join(lines)

    desired_cols = [
        "rank", "strategy", "universe", "max_positions", "sl_pct", "tp_pct",
        "avg_daily_return_pct", "win_rate_pct", "calmar", "mdd_pct",
        "pass", "composite_score",
    ]
    # DataFrame에 실제 존재하는 컬럼만 사용 (기존 결과 파일 호환성 유지)
    report_cols = [c for c in desired_cols if c in df.columns]

    lines = [
        "# 분봉 데이트레이딩 10전략 토너먼트 1라운드",
        "",
        f"- 생성 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 시나리오 수: {len(df)}",
        "- 합격선: 일수익률 >= 0.3% AND 일승률 >= 50% AND MDD >= -15%",
        "- 종합점수 = 0.4×z(일수익률) + 0.3×z(일승률) + 0.3×z(Calmar)",
        "",
        "## 상위 10 시나리오",
        "",
        _to_table(df.head(10), report_cols),
        "",
    ]

    pass_count = int(df["pass"].sum())
    lines.append(f"## 합격 시나리오 수: {pass_count}")
    if pass_count > 0:
        lines.append("")
        lines.append(_to_table(df[df["pass"]], report_cols))

    lines.append("")
    lines.append("## 전략별 평균 지표")
    lines.append("")
    grp_strategy = (
        df.groupby("strategy")[["avg_daily_return_pct", "win_rate_pct", "calmar", "mdd_pct"]]
        .mean()
        .reset_index()
    )
    try:
        lines.append(grp_strategy.to_markdown(index=False))
    except ImportError:
        lines.append(grp_strategy.to_string(index=False))

    lines.append("")
    lines.append("## universe별 평균 지표")
    lines.append("")
    grp_uni = (
        df.groupby("universe")[["avg_daily_return_pct", "win_rate_pct", "calmar", "mdd_pct"]]
        .mean()
        .reset_index()
    )
    try:
        lines.append(grp_uni.to_markdown(index=False))
    except ImportError:
        lines.append(grp_uni.to_string(index=False))

    summary_path = out_dir / "tournament_round1_summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"리포트 저장: {summary_path}")


# ---------------------------------------------------------------------------
# 메인 로직
# ---------------------------------------------------------------------------

def _run_scenario(
    scenario_idx: int,
    total_scenarios: int,
    strat_key: str,
    uni: str,
    n_pos: int,
    providers: Dict[str, Callable[[str], List[str]]],
    args: argparse.Namespace,
    skip_dates: Set[str],
    sl_pct: Optional[float] = None,
    tp_pct: Optional[float] = None,
) -> Tuple[int, dict]:
    """단일 시나리오 실행 (ThreadPoolExecutor worker 함수).

    Args:
        sl_pct: 손절 비율 (예: 0.01 = 1%). None이면 전략 디폴트 사용.
        tp_pct: 익절 비율 (예: 0.02 = 2%). None이면 전략 디폴트 사용.

    Returns:
        (scenario_idx, metrics_dict)
    """
    sl_label = f"{sl_pct:.3f}" if sl_pct is not None else "default"
    tp_label = f"{tp_pct:.3f}" if tp_pct is not None else "default"
    label = f"[{scenario_idx}/{total_scenarios}] {strat_key} / {uni} / pos={n_pos} / SL={sl_label} / TP={tp_label}"
    logger.info(f"시나리오 시작: {label}")

    try:
        strategy = _load_strategy(strat_key)

        # SL/TP 그리드 값이 지정된 경우 전략 인스턴스에 주입
        # (IntradayBaseStrategy.stop_loss_pct / take_profit_pct 속성 덮어쓰기)
        if sl_pct is not None:
            strategy.stop_loss_pct = sl_pct
        if tp_pct is not None:
            strategy.take_profit_pct = tp_pct

        provider = providers[uni]

        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=args.capital,
            max_positions=n_pos,
        )

        # engine.run_minute의 stop_loss_pct / take_profit_pct 파라미터에도 전달
        run_kwargs: dict = dict(
            stock_codes=[],          # candidate_provider로 일자별 동적 결정
            start_date=args.start,
            end_date=args.end,
            candidate_provider=provider,
            initial_capital=args.capital,
            max_positions=n_pos,
            slip_bps=float(args.slip_bps),
            eod_time=args.eod,
            skip_dates=skip_dates,
        )
        if sl_pct is not None:
            run_kwargs["stop_loss_pct"] = sl_pct
        if tp_pct is not None:
            run_kwargs["take_profit_pct"] = tp_pct

        result = engine.run_minute(**run_kwargs)

        metrics = compute_metrics(result, args.capital)
        # sl_pct / tp_pct가 None이면 전략 인스턴스의 실제 값으로 기록
        effective_sl = sl_pct if sl_pct is not None else getattr(strategy, "stop_loss_pct", 0.01)
        effective_tp = tp_pct if tp_pct is not None else getattr(strategy, "take_profit_pct", 0.02)
        metrics.update({
            "strategy": strat_key,
            "universe": uni,
            "max_positions": n_pos,
            "sl_pct": effective_sl,
            "tp_pct": effective_tp,
        })

        logger.info(
            f"시나리오 완료: {label} - "
            f"total_pnl={metrics['total_pnl_pct']:+.2f}% "
            f"win={metrics['win_rate_pct']:.1f}% "
            f"MDD={metrics['mdd_pct']:.2f}% "
            f"trades={metrics['trade_count']}"
        )
        return scenario_idx, metrics

    except Exception as exc:
        logger.error(f"시나리오 실패: {label} - {exc}", exc_info=True)
        zero = compute_metrics(None, args.capital)
        effective_sl = sl_pct if sl_pct is not None else 0.01
        effective_tp = tp_pct if tp_pct is not None else 0.02
        zero.update({
            "strategy": strat_key,
            "universe": uni,
            "max_positions": n_pos,
            "sl_pct": effective_sl,
            "tp_pct": effective_tp,
        })
        return scenario_idx, zero


def run_tournament(args: argparse.Namespace) -> None:
    """토너먼트 시뮬레이션 실행."""
    # 출력 디렉토리 (타임스탬프 포함)
    out_dir = Path(args.out) / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"출력 디렉토리: {out_dir}")

    # 전략 목록
    if args.strategies == "all":
        strategy_keys = list(STRATEGY_REGISTRY.keys())
    else:
        strategy_keys = [k.strip() for k in args.strategies.split(",")]
        invalid = [k for k in strategy_keys if k not in STRATEGY_REGISTRY]
        if invalid:
            raise ValueError(f"알 수 없는 전략 키: {invalid}. 유효 키: {list(STRATEGY_REGISTRY.keys())}")

    # universe 타입 목록
    universe_types: List[str] = [u.strip() for u in args.universe.split(",")]
    valid_universes = {"screener", "dynamic"}
    invalid_uni = set(universe_types) - valid_universes
    if invalid_uni:
        raise ValueError(f"유효하지 않은 universe 타입: {invalid_uni}. 선택: {valid_universes}")

    # max_positions 목록
    max_positions_list: List[int] = [int(x) for x in args.max_positions]

    # skip_dates 처리
    skip_dates: Set[str] = _parse_skip_dates(args.skip)

    # universe provider 생성 (재사용 — providers는 읽기 전용으로 worker 간 공유 안전)
    providers: Dict[str, Callable[[str], List[str]]] = {}
    if "screener" in universe_types:
        providers["screener"] = _make_screener_provider()
    if "dynamic" in universe_types:
        providers["dynamic"] = _make_dynamic_provider(
            cache_dir=getattr(args, "dynamic_cache", None) or "cache/intraday_universe",
            top_n=getattr(args, "dynamic_top_n", 50),
            rank_by=getattr(args, "dynamic_rank_by", "volatility_pct"),
        )

    # SL/TP 그리드 파싱
    sl_list: List[Optional[float]] = (
        [float(x) for x in args.sl_grid.split(",")]
        if args.sl_grid else [None]
    )
    tp_list: List[Optional[float]] = (
        [float(x) for x in args.tp_grid.split(",")]
        if args.tp_grid else [None]
    )

    # 시나리오 목록 구성 (strategy × universe × pos × sl × tp)
    scenarios: List[Tuple[int, str, str, int, Optional[float], Optional[float]]] = []
    scenario_idx = 0
    for strat_key in strategy_keys:
        for uni in universe_types:
            for n_pos in max_positions_list:
                for sl_pct in sl_list:
                    for tp_pct in tp_list:
                        scenario_idx += 1
                        scenarios.append((scenario_idx, strat_key, uni, n_pos, sl_pct, tp_pct))

    total_scenarios = len(scenarios)
    n_workers = getattr(args, "workers", 8)

    logger.info(
        f"토너먼트 시작: 전략 {len(strategy_keys)}개 x universe {len(universe_types)}개 "
        f"x max_positions {max_positions_list} x SL {len(sl_list)}개 x TP {len(tp_list)}개 "
        f"= {total_scenarios}개 시나리오 (workers={n_workers})"
    )

    all_results = []

    if n_workers == 1:
        # 직렬 실행 (디버깅용)
        for idx, strat_key, uni, n_pos, sl_pct, tp_pct in scenarios:
            _, metrics = _run_scenario(
                idx, total_scenarios, strat_key, uni, n_pos,
                providers, args, skip_dates,
                sl_pct=sl_pct, tp_pct=tp_pct,
            )
            all_results.append(metrics)
    else:
        # 병렬 실행 (ThreadPoolExecutor)
        futures_map = {}
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            for idx, strat_key, uni, n_pos, sl_pct, tp_pct in scenarios:
                future = executor.submit(
                    _run_scenario,
                    idx, total_scenarios, strat_key, uni, n_pos,
                    providers, args, skip_dates,
                    sl_pct, tp_pct,
                )
                futures_map[future] = (idx, strat_key, uni, n_pos, sl_pct, tp_pct)

            # 완료된 순서대로 수집 (결과는 이후 composite_score로 정렬)
            for future in as_completed(futures_map):
                _, metrics = future.result()
                all_results.append(metrics)

        # 시나리오 순서대로 재정렬 (재현성 보장)
        all_results.sort(key=lambda m: (m["strategy"], m["universe"], m["max_positions"], m["sl_pct"], m["tp_pct"]))

    if not all_results:
        logger.error("실행된 시나리오가 없습니다.")
        return

    # 종합 점수 정렬
    df = pd.DataFrame(all_results)
    df = _rank_by_composite(df)

    # 결과 저장
    parquet_path = out_dir / "tournament_results.parquet"
    csv_path = out_dir / "tournament_results.csv"
    df.to_parquet(parquet_path, index=False)
    df.to_csv(csv_path, index=False)
    logger.info(f"결과 저장: {parquet_path}, {csv_path}")

    # 리포트 작성
    _write_report_md(df, out_dir)

    pass_count = int(df["pass"].sum())
    logger.info(
        f"\n{'='*60}\n"
        f"토너먼트 완료\n"
        f"  시나리오: {len(df)}개\n"
        f"  합격:     {pass_count}개\n"
        f"  결과 위치: {out_dir}\n"
        f"{'='*60}"
    )
    print(f"\nTournament done. Results: {out_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_intraday_tournament",
        description="분봉 데이트레이딩 10전략 토너먼트 1라운드 시뮬레이터",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python scripts/run_intraday_tournament.py \\
      --start 20250901 --end 20260515 \\
      --skip 202603 \\
      --capital 10000000 \\
      --max-positions 3 4 5 \\
      --universe screener,dynamic \\
      --strategies all \\
      --eod 15:20 \\
      --slip-bps 5 \\
      --out reports/tournament_round1

전략 키 목록:
  abcd_pattern, bull_flag, reversal_rsi, reversal_vwap,
  ma_trend, vwap_trade, support_resistance, red_to_green,
  orb, pullback
""",
    )

    p.add_argument(
        "--start", required=True, metavar="YYYYMMDD",
        help="백테스트 시작일 (예: 20250901)",
    )
    p.add_argument(
        "--end", required=True, metavar="YYYYMMDD",
        help="백테스트 종료일 (예: 20260515)",
    )
    p.add_argument(
        "--skip", nargs="*", default=[], metavar="PREFIX_OR_DATE",
        help="건너뛸 기간 또는 날짜 (예: 202603  또는 20260301). 여러 개 가능.",
    )
    p.add_argument(
        "--capital", type=float, default=10_000_000,
        metavar="KRW",
        help="초기 자본금 (원, 기본 10,000,000)",
    )
    p.add_argument(
        "--max-positions", nargs="+", default=[3, 4, 5],
        metavar="N",
        help="동시 최대 보유 종목 수 그리드 (기본: 3 4 5)",
    )
    p.add_argument(
        "--universe", default="screener,dynamic",
        metavar="TYPE[,TYPE]",
        help="universe 타입: screener / dynamic / screener,dynamic (기본: screener,dynamic)",
    )
    p.add_argument(
        "--strategies", default="all",
        metavar="all|KEY[,KEY]",
        help="실행할 전략 키 리스트 또는 'all' (기본: all)",
    )
    p.add_argument(
        "--eod", default="15:20",
        metavar="HH:MM",
        help="EOD 강제청산 시각 (기본: 15:20)",
    )
    p.add_argument(
        "--slip-bps", type=float, default=5.0,
        metavar="BPS",
        help="슬리피지 (bp, 기본: 5)",
    )
    p.add_argument(
        "--out", default="reports/tournament_round1",
        metavar="DIR",
        help="결과 저장 디렉토리 (타임스탬프 서브디렉토리 자동 생성)",
    )
    p.add_argument(
        "--dynamic-cache", default="cache/intraday_universe",
        metavar="DIR",
        help="dynamic universe Parquet 캐시 디렉토리 (기본: cache/intraday_universe)",
    )
    p.add_argument(
        "--workers", type=int, default=8,
        metavar="N",
        help="ThreadPool 병렬 worker 수 (기본: 8). 1이면 직렬 실행 (디버깅용).",
    )
    p.add_argument(
        "--dynamic-top-n", type=int, default=50,
        metavar="N",
        help="dynamic universe 상위 N개 종목으로 제한 (기본: 50, 0=무제한)",
    )
    p.add_argument(
        "--dynamic-rank-by", choices=["volatility_pct", "amount_sum"], default="volatility_pct",
        help="dynamic universe top_n 적용 기준 (기본: volatility_pct)",
    )
    p.add_argument(
        "--sl-grid", default=None,
        metavar="PCT[,PCT]",
        help=(
            "손절 비율 그리드 (쉼표 구분, 소수 형식). "
            "예: 0.005,0.01,0.02,0.03 → SL 0.5%%/1%%/2%%/3%%. "
            "미지정 시 각 전략 config 디폴트 사용."
        ),
    )
    p.add_argument(
        "--tp-grid", default=None,
        metavar="PCT[,PCT]",
        help=(
            "익절 비율 그리드 (쉼표 구분, 소수 형식). "
            "예: 0.01,0.02,0.04,0.06 → TP 1%%/2%%/4%%/6%%. "
            "미지정 시 각 전략 config 디폴트 사용."
        ),
    )
    p.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="로그 레벨 (기본: INFO)",
    )
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    run_tournament(args)


if __name__ == "__main__":
    main()
