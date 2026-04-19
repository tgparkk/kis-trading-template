"""
스크리너 스냅샷 수집 러너
==========================
전략별 스크리너를 실행하여 후보 종목을 screener_snapshots 테이블에 저장한다.

Usage:
    python -m RoboTrader_template.runners.screener_snapshot_collector \
        --strategies lynch,sawkami,bb_reversion \
        --date today \
        --max-candidates 10 \
        --dry-run

옵션:
    --strategies : 쉼표 구분 전략명 (기본: lynch,sawkami,bb_reversion)
    --date       : today | YYYY-MM-DD (기본: today)
    --max-candidates : 전략당 최대 후보 종목 수 (기본 10)
    --dry-run    : DB 저장 없이 stdout 출력만

run_once() 를 직접 import 하면 EOD 훅 등 외부에서 재사용 가능.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJ_ROOT = Path(__file__).parent.parent
if str(_PROJ_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT.parent))
if str(_PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT))

from strategies.screener_base import ScreenerBase  # noqa: E402
from utils.korean_time import now_kst  # noqa: E402

_LOGGER = logging.getLogger("runners.screener_snapshot_collector")

# 지원 전략 목록
ALL_STRATEGIES = ["lynch", "sawkami", "bb_reversion"]


# ---------------------------------------------------------------------------
# 어댑터 팩토리
# ---------------------------------------------------------------------------

def _build_adapter(
    strategy_name: str,
    broker=None,
    db_manager=None,
    config=None,
) -> Optional[ScreenerBase]:
    """전략명 → 어댑터 인스턴스. 실패 시 None 반환."""
    try:
        if strategy_name == "lynch":
            from strategies.lynch.screener import LynchScreenerAdapter
            return LynchScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "sawkami":
            from strategies.sawkami.screener import SawkamiScreenerAdapter
            return SawkamiScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "bb_reversion":
            from strategies.bb_reversion.screener import BBReversionScreenerAdapter
            return BBReversionScreenerAdapter()
        else:
            _LOGGER.warning("알 수 없는 전략: %s", strategy_name)
            return None
    except Exception as e:
        _LOGGER.error("어댑터 생성 실패 (%s): %s", strategy_name, e)
        return None


# ---------------------------------------------------------------------------
# 핵심 로직 — EOD 훅·CLI 공용
# ---------------------------------------------------------------------------

def run_once(
    strategies: List[str],
    scan_date: date,
    max_candidates: int,
    dry_run: bool,
    broker=None,
    db_manager=None,
    config=None,
) -> List[Dict[str, Any]]:
    """
    전략 목록을 순회하여 스크리너를 실행하고 결과를 DB 에 저장한다.

    Returns:
        전략별 요약 dict 목록:
        [{"strategy": str, "count": int, "elapsed": float, "params_hash": str, "ok": bool}]
    """
    summaries: List[Dict[str, Any]] = []

    for name in strategies:
        t0 = time.monotonic()
        _LOGGER.info("[스냅샷] %s 시작", name)
        print(f"[스냅샷] {name} 스크리닝 시작...")

        adapter = _build_adapter(name, broker=broker, db_manager=db_manager, config=config)
        if adapter is None:
            summaries.append({"strategy": name, "count": 0, "elapsed": 0.0,
                               "params_hash": "", "ok": False})
            continue

        try:
            params: Dict[str, Any] = adapter.default_params()
            # max_candidates 파라미터 오버라이드 (어댑터가 지원하는 경우)
            if "max_candidates" in params:
                params = {**params, "max_candidates": max_candidates}

            params_hash = ScreenerBase.compute_params_hash(params)
            candidates = adapter.scan(scan_date, params)

            # max_candidates 상한 적용 (어댑터가 내부에서 자르지 않은 경우 대비)
            candidates = candidates[:max_candidates]

            elapsed = time.monotonic() - t0
            count = len(candidates)

            if dry_run:
                print(f"[스냅샷] {name} - {count}건 (dry-run, DB 저장 안 함, {elapsed:.1f}초)")
                for c in candidates:
                    print(f"  {c.code}  {c.name}  score={c.score}  {c.reason}")
            else:
                ok = False
                if db_manager is not None and count > 0:
                    ok = db_manager.candidate_repo.save_screener_snapshot(
                        strategy=name,
                        scan_date=scan_date,
                        params_hash=params_hash,
                        params_json=params,
                        candidates=candidates,
                    )
                elif count == 0:
                    ok = True  # 0건도 정상 (DB 저장 스킵)
                status = "저장완료" if ok else "저장실패"
                print(f"[스냅샷] {name} - {count}건 {status} ({elapsed:.1f}초)")

            summaries.append({
                "strategy": name,
                "count": count,
                "elapsed": elapsed,
                "params_hash": params_hash,
                "ok": True,
            })

        except Exception as e:
            elapsed = time.monotonic() - t0
            _LOGGER.error("[스냅샷] %s 실패: %s", name, e, exc_info=True)
            print(f"[스냅샷] {name} - 실패: {e} ({elapsed:.1f}초)", file=sys.stderr)
            summaries.append({
                "strategy": name,
                "count": 0,
                "elapsed": elapsed,
                "params_hash": "",
                "ok": False,
            })

    return summaries


def _print_summary_table(summaries: List[Dict[str, Any]], dry_run: bool) -> None:
    """전략별 결과 요약 테이블 출력."""
    label = " [dry-run]" if dry_run else ""
    print(f"\n{'=' * 60}")
    print(f"스크리너 스냅샷 수집 요약{label}")
    print(f"{'=' * 60}")
    header = f"{'전략':<15} {'건수':>5} {'소요(초)':>8} {'params_hash':<12} {'결과':<8}"
    print(header)
    print("-" * 60)
    for s in summaries:
        ph = s["params_hash"][:8] + "…" if s["params_hash"] else "-"
        result_label = "OK" if s["ok"] else "FAIL"
        print(f"{s['strategy']:<15} {s['count']:>5} {s['elapsed']:>8.1f} {ph:<12} {result_label:<8}")
    total = sum(s["count"] for s in summaries)
    print("-" * 60)
    print(f"{'합계':<15} {total:>5}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="스크리너 스냅샷 수집 (전략별 후보 종목 → screener_snapshots 저장)"
    )
    p.add_argument(
        "--strategies",
        default=",".join(ALL_STRATEGIES),
        help=f"쉼표 구분 전략명 (기본: {','.join(ALL_STRATEGIES)})",
    )
    p.add_argument(
        "--date",
        default="today",
        help="수집 기준일 today | YYYY-MM-DD (기본: today)",
    )
    p.add_argument(
        "--max-candidates",
        type=int,
        default=10,
        help="전략당 최대 후보 종목 수 (기본 10)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="DB 저장 없이 결과만 stdout 에 출력",
    )
    return p.parse_args()


def _resolve_date(date_str: str) -> date:
    if date_str.lower() == "today":
        return now_kst().date()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"날짜 형식 오류 (YYYY-MM-DD 또는 today): {date_str!r}")


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )

    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    if not strategies:
        print("[오류] --strategies 에 전략명을 하나 이상 지정하세요.", file=sys.stderr)
        return 2

    try:
        scan_date = _resolve_date(args.date)
    except ValueError as e:
        print(f"[오류] {e}", file=sys.stderr)
        return 2

    dry_run: bool = args.dry_run
    max_candidates: int = args.max_candidates

    print(f"[스냅샷] 전략={strategies}, 날짜={scan_date}, 최대={max_candidates}, dry-run={dry_run}")

    # broker / db_manager 초기화 (bb_reversion 은 불필요하나, lynch/sawkami 는 필요)
    broker = None
    db_manager = None
    config = None

    # lynch, sawkami 가 포함된 경우에만 초기화 시도
    needs_broker = any(s in strategies for s in ("lynch", "sawkami"))
    if needs_broker and not dry_run:
        try:
            from utils.price_utils import load_config
            from framework.broker import KISBroker
            from db.database_manager import DatabaseManager

            config = load_config()
            broker = KISBroker(config)
            db_manager = DatabaseManager()
            print("[스냅샷] broker/DB 초기화 완료")
        except Exception as e:
            print(f"[경고] broker/DB 초기화 실패 — lynch/sawkami 는 스킵될 수 있음: {e}",
                  file=sys.stderr)
    elif not dry_run:
        # bb_reversion 전용 — DB 만 필요
        try:
            from db.database_manager import DatabaseManager
            db_manager = DatabaseManager()
            print("[스냅샷] DB 초기화 완료")
        except Exception as e:
            print(f"[경고] DB 초기화 실패 — 저장 스킵: {e}", file=sys.stderr)

    summaries = run_once(
        strategies=strategies,
        scan_date=scan_date,
        max_candidates=max_candidates,
        dry_run=dry_run,
        broker=broker,
        db_manager=db_manager,
        config=config,
    )

    _print_summary_table(summaries, dry_run)

    failed = [s for s in summaries if not s["ok"]]
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
