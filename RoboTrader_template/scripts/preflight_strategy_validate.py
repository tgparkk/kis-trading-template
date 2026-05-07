"""
사전 헬스체크 - 전략 설정 + 의존성 + DB 연결 검증
=====================================================

봇 시작 전 30초 이내에 완료되도록 설계.
외부 API(KIS 등) 호출은 절대 없음.

실행:
    cd RoboTrader_template
    python -X utf8 scripts/preflight_strategy_validate.py
    python -X utf8 scripts/preflight_strategy_validate.py --verbose
    python -X utf8 scripts/preflight_strategy_validate.py --quiet

종료 코드:
    0 - 모두 PASS 또는 WARN만 있음
    1 - 하나 이상 FAIL
"""

import sys
import os
import json
import importlib
import argparse
import time
from pathlib import Path
from typing import List, Tuple, Optional

# 프로젝트 루트를 sys.path에 추가
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# ============================================================================
# 결과 타입
# ============================================================================

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

CheckResult = Tuple[str, str, str]  # (status, name, detail)


# ============================================================================
# 개별 검사 함수
# ============================================================================

def check_core_imports() -> List[CheckResult]:
    """psycopg2·pandas·yaml 등 핵심 패키지 import 가능 여부."""
    results: List[CheckResult] = []
    packages = [
        ("psycopg2", FAIL),      # DB 필수
        ("pandas", FAIL),        # 전략 필수
        ("numpy", FAIL),         # 전략 필수
        ("yaml", FAIL),          # config.yaml 로딩 필수
        ("telegram", WARN),      # 텔레그램 알림 (없어도 봇 동작)
        ("aiohttp", WARN),       # KIS HTTP 클라이언트
    ]
    for pkg, severity_on_fail in packages:
        try:
            importlib.import_module(pkg)
            results.append((PASS, f"import:{pkg}", "OK"))
        except ImportError as e:
            results.append((severity_on_fail, f"import:{pkg}", str(e)))
    return results


def check_db_connection() -> CheckResult:
    """PostgreSQL/TimescaleDB 연결 가능 여부 (SELECT 1)."""
    try:
        from db.connection import DatabaseConnection
        DatabaseConnection.initialize(min_conn=1, max_conn=2)
        with DatabaseConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
                if row and row[0] == 1:
                    return (PASS, "db:connection", "SELECT 1 OK")
        return (FAIL, "db:connection", "SELECT 1 결과 없음")
    except Exception as e:
        return (FAIL, "db:connection", str(e))


def check_trading_config() -> Tuple[CheckResult, List[dict]]:
    """trading_config.json 로딩 및 strategies 배열 존재 여부."""
    config_path = _PROJECT_ROOT / "config" / "trading_config.json"
    if not config_path.exists():
        return (FAIL, "config:trading_config.json", "파일 없음"), []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        strategies = cfg.get("strategies", [])
        if not isinstance(strategies, list) or len(strategies) == 0:
            return (WARN, "config:trading_config.json", "strategies 배열이 비어있음"), []
        enabled = [s for s in strategies if s.get("enabled", True)]
        return (
            PASS,
            "config:trading_config.json",
            f"strategies {len(enabled)}개 활성 (전체 {len(strategies)}개)",
        ), enabled
    except json.JSONDecodeError as e:
        return (FAIL, "config:trading_config.json", f"JSON 파싱 오류: {e}"), []
    except Exception as e:
        return (FAIL, "config:trading_config.json", str(e)), []


def check_strategy(name: str) -> List[CheckResult]:
    """
    단일 전략에 대해 4가지 검사 수행:
      1. config.yaml 로딩 + 범위 검증 (validate())
      2. strategy.py import 가능 여부
      3. BaseStrategy 상속 여부
      4. 필수 메서드 구현 여부 (generate_signal, on_init, on_tick)
    """
    results: List[CheckResult] = []
    prefix = f"strategy:{name}"

    # 1. config.yaml 로딩 + 유효성 검증
    try:
        # StrategyLoader.load_strategy는 validate()까지 호출함
        # 하지만 여기서는 단계별로 분리해 세밀한 PASS/FAIL을 보여준다
        from strategies.config import StrategyConfig, StrategyConfigError
        cfg = StrategyConfig(name)
        # load()는 cwd 기준 'strategies/{name}/config.yaml'을 봄.
        # 스크립트는 프로젝트 루트 기준으로 실행되므로 chdir 불필요.
        os.chdir(_PROJECT_ROOT)
        cfg.load()
        results.append((PASS, f"{prefix}:config_load", "config.yaml 로딩 OK"))
    except FileNotFoundError as e:
        results.append((FAIL, f"{prefix}:config_load", str(e)))
        return results  # config 없으면 이후 검사 의미없음
    except Exception as e:
        results.append((FAIL, f"{prefix}:config_load", str(e)))
        return results

    try:
        from strategies.config import StrategyConfig, StrategyConfigError
        cfg2 = StrategyConfig(name)
        cfg2.load()
        cfg2.validate()
        results.append((PASS, f"{prefix}:config_validate", "범위 검증 OK"))
    except Exception as e:
        results.append((FAIL, f"{prefix}:config_validate", str(e)))

    # 2. strategy.py import
    try:
        from strategies.config import StrategyLoader, StrategyConfigError
        strategy_class = StrategyLoader._load_strategy_class(name)
        results.append((PASS, f"{prefix}:import", f"{strategy_class.__name__} import OK"))
    except Exception as e:
        results.append((FAIL, f"{prefix}:import", str(e)))
        return results  # import 실패 시 이후 검사 불가

    # 3. BaseStrategy 상속
    try:
        from strategies.base import BaseStrategy
        if issubclass(strategy_class, BaseStrategy):
            results.append((PASS, f"{prefix}:inherits_base", "BaseStrategy 상속 OK"))
        else:
            results.append((FAIL, f"{prefix}:inherits_base", "BaseStrategy를 상속하지 않음"))
    except Exception as e:
        results.append((FAIL, f"{prefix}:inherits_base", str(e)))

    # 4. 필수 메서드 구현 확인
    required_methods = ["generate_signal", "on_init", "on_tick"]
    for method in required_methods:
        if hasattr(strategy_class, method):
            results.append((PASS, f"{prefix}:method:{method}", "구현됨"))
        else:
            results.append((FAIL, f"{prefix}:method:{method}", "메서드 없음"))

    return results


# ============================================================================
# 메인 실행 엔진
# ============================================================================

class PreflightRunner:
    """사전 헬스체크 실행기."""

    def __init__(self, verbose: bool = False, quiet: bool = False):
        self.verbose = verbose
        self.quiet = quiet
        self._results: List[CheckResult] = []

    def _record(self, result: CheckResult) -> None:
        self._results.append(result)

    def _print(self, result: CheckResult) -> None:
        status, name, detail = result
        if self.quiet and status == PASS:
            return
        tag = f"[{status}]"
        print(f"  {tag:<7} {name:<45} {detail}")

    def _add_and_print(self, result: CheckResult) -> None:
        self._record(result)
        if self.verbose or result[0] != PASS:
            self._print(result)
        elif not self.quiet:
            self._print(result)

    def run(self) -> int:
        """전체 체크 실행. 반환값: 0=성공, 1=FAIL 있음."""
        start = time.time()

        print("=" * 65)
        print("  RoboTrader 사전 헬스체크 (preflight_strategy_validate)")
        print("=" * 65)

        # --- 1. 핵심 패키지 import ---
        if self.verbose:
            print("\n[1/4] 핵심 패키지 의존성")
        for r in check_core_imports():
            self._add_and_print(r)

        # --- 2. DB 연결 ---
        if self.verbose:
            print("\n[2/4] DB 연결")
        self._add_and_print(check_db_connection())

        # --- 3. trading_config.json + 전략 목록 ---
        if self.verbose:
            print("\n[3/4] trading_config.json")
        cfg_result, enabled_strategies = check_trading_config()
        self._add_and_print(cfg_result)

        # --- 4. 각 활성 전략 검증 ---
        if self.verbose:
            print(f"\n[4/4] 전략 검증 ({len(enabled_strategies)}개 활성)")
        for spec in enabled_strategies:
            name = spec.get("name", "")
            if not name:
                self._add_and_print((WARN, "strategy:?", "name 필드 없음"))
                continue
            for r in check_strategy(name):
                self._add_and_print(r)

        # --- 요약 ---
        elapsed = time.time() - start
        passes = sum(1 for r in self._results if r[0] == PASS)
        warns = sum(1 for r in self._results if r[0] == WARN)
        fails = sum(1 for r in self._results if r[0] == FAIL)
        total = len(self._results)

        print()
        print("-" * 65)
        print(f"  결과: {passes} PASS / {warns} WARN / {fails} FAIL  ({elapsed:.1f}초)")
        if fails == 0:
            if warns > 0:
                print("  [WARN] 경고 있음 - 봇 시작은 가능하나 확인 권장")
            else:
                print("  [OK] 모든 검사 통과 - 봇 시작 가능")
        else:
            print("  [FAIL] 검사 실패 - 봇 시작을 중단하세요")
        print()

        return 0 if fails == 0 else 1


# ============================================================================
# CLI 진입점
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="봇 시작 전 사전 헬스체크 (전략 설정 + DB + 의존성)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
종료 코드:
  0  모두 PASS 또는 WARN만 있음 (봇 시작 가능)
  1  하나 이상 FAIL (봇 시작 중단 권장)

예시:
  python -X utf8 scripts/preflight_strategy_validate.py
  python -X utf8 scripts/preflight_strategy_validate.py --verbose
  python -X utf8 scripts/preflight_strategy_validate.py --quiet
        """,
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="모든 검증 단계를 섹션별로 출력",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="실패(FAIL/WARN)만 출력",
    )
    args = parser.parse_args()

    runner = PreflightRunner(verbose=args.verbose, quiet=args.quiet)
    sys.exit(runner.run())


if __name__ == "__main__":
    main()
