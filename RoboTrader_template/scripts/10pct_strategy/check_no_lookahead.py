#!/usr/bin/env python3
"""
No Look-Ahead Lint 검사기 (Phase 0-P0-3)
==========================================

시그널/필터/출구 모듈에서 pandas forward shift (``shift(-``) 사용을 금지합니다.

검사 대상 디렉토리:
    - RoboTrader_template/strategies/
    - RoboTrader_template/multiverse/
    - RoboTrader_template/screener/   (있을 경우)
    - RoboTrader_template/scripts/10pct_strategy/

화이트리스트 (허용):
    - 파일명에 ``forward`` 가 포함된 모듈 (예: forward_return.py)
    - ``tests/`` 디렉토리 하위 파일
    - ``lib/pit_helpers.py`` (forward_return 구현체 자체)
    - 현재 파일 자체 (check_no_lookahead.py)

패턴:
    ``shift(-``  또는  ``.shift(- ``  형태의 forward leak 코드

종료 코드:
    0 — leak 없음 (CI 통과)
    1 — leak 발견 (CI 실패)

사용법:
    python scripts/10pct_strategy/check_no_lookahead.py
    python scripts/10pct_strategy/check_no_lookahead.py --root /custom/path

CI / pre-commit hook 통합 예시:
    # .pre-commit-config.yaml
    - repo: local
      hooks:
        - id: no-lookahead
          name: No Look-Ahead Lint
          entry: python RoboTrader_template/scripts/10pct_strategy/check_no_lookahead.py
          language: python
          types: [python]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

# forward shift 패턴 (양의 정수 앞 - 기호)
# shift(-1), shift( -2 ), .shift(-n) 등 모두 감지
_PATTERN = re.compile(r"\.shift\(\s*-")

# 기본 검사 대상 서브디렉토리 (root 기준 상대 경로)
_TARGET_SUBDIRS = [
    "strategies",
    "multiverse",
    "screener",
    "scripts/10pct_strategy",
]

# 화이트리스트 판정 함수


def _is_whitelisted(path: Path) -> bool:
    """True이면 검사 제외."""
    parts = path.parts

    # tests/ 하위는 제외 (테스트에서는 forward_return 호출 가능)
    if "tests" in parts:
        return True

    # lib/pit_helpers.py 제외 (forward_return 구현체)
    if "pit_helpers.py" in parts:
        return True

    # 파일명에 'forward' 포함 시 제외
    if "forward" in path.name.lower():
        return True

    # 현재 파일 자체 제외
    if path.name == "check_no_lookahead.py":
        return True

    return False


# ---------------------------------------------------------------------------
# 검사 로직
# ---------------------------------------------------------------------------

def scan_directory(root: Path) -> List[Tuple[Path, int, str]]:
    """검사 대상 디렉토리를 스캔하여 위반 목록 반환.

    Returns
    -------
    List of (file_path, line_number, line_content) tuples.
    """
    violations: List[Tuple[Path, int, str]] = []

    for subdir_name in _TARGET_SUBDIRS:
        subdir = root / subdir_name
        if not subdir.exists():
            continue

        for py_file in sorted(subdir.rglob("*.py")):
            if _is_whitelisted(py_file):
                continue

            try:
                lines = py_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError as e:
                print(f"[WARN] Cannot read {py_file}: {e}", file=sys.stderr)
                continue

            for lineno, line in enumerate(lines, start=1):
                # 주석 줄은 건너뜀
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if _PATTERN.search(line):
                    violations.append((py_file, lineno, line.rstrip()))

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="No Look-Ahead Lint: forward shift(-) 금지 검사기"
    )
    parser.add_argument(
        "--root",
        default=None,
        help="검사 루트 디렉토리 (기본: 이 스크립트의 상위 2단계)",
    )
    args = parser.parse_args()

    # root 결정: 인자 > 환경변수 > 스크립트 위치 기반 추론
    if args.root:
        root = Path(args.root).resolve()
    else:
        # scripts/10pct_strategy/check_no_lookahead.py → 상위 2단계 = RoboTrader_template/
        script_dir = Path(__file__).resolve().parent  # scripts/10pct_strategy/
        root = script_dir.parent.parent               # RoboTrader_template/

    if not root.exists():
        print(f"[ERROR] Root directory not found: {root}", file=sys.stderr)
        return 1

    print(f"[INFO] Scanning for forward shift(-) leaks under: {root}")
    print(f"[INFO] Target subdirs: {_TARGET_SUBDIRS}")
    print()

    violations = scan_directory(root)

    if not violations:
        print("[PASS] No look-ahead violations found. exit 0")
        return 0

    # 위반 보고
    print(f"[FAIL] Found {len(violations)} look-ahead violation(s):", file=sys.stderr)
    print(file=sys.stderr)
    for file_path, lineno, line_content in violations:
        # CI-friendly: file:line: message 형식
        rel = file_path.relative_to(root) if file_path.is_relative_to(root) else file_path
        print(f"  {rel}:{lineno}: {line_content.strip()}", file=sys.stderr)

    print(file=sys.stderr)
    print(
        "[HINT] forward shift(-) is only allowed in:\n"
        "  - lib/pit_helpers.py (forward_return implementation)\n"
        "  - Files with 'forward' in the filename\n"
        "  - tests/ directory\n"
        "Use safe_lag() for signals/filters. Use forward_return() for evaluation only.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
