"""기동 환경 가드 — 봇이 올바른 프로젝트 venv에서 실행 중인지 fail-fast 검증.

2026-06-30 사고: template venv가 sibling(RoboTrader_quant) venv 복사본이라
activate.bat이 quant 경로를 가리켜, 봇이 매일 quant venv(finance-datareader 0.9.102,
KS11=live KRX 스크래핑)로 실행→regime 지수 LOGOUT. 몇 주간 조용히 잘못된 환경에서
돈 게 본질. 이 가드는 그 계열 사고를 기동 즉시 노출시킨다.
"""
import os
import sys
from typing import List

_OVERRIDE_ENV = "ALLOW_FOREIGN_VENV"
_MIN_FDR = (0, 9, 202)


def _norm(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def check_environment(project_root: str) -> List[str]:
    """환경 문제 목록을 반환(빈 리스트=정상). 부작용 없음(sys.exit 안 함)."""
    problems: List[str] = []

    expected_venv = _norm(os.path.join(project_root, "venv"))
    actual_prefix = _norm(sys.prefix)
    if actual_prefix != expected_venv:
        problems.append(
            f"잘못된 venv에서 실행 중: sys.prefix={actual_prefix} "
            f"(기대={expected_venv}). run_robotrader.bat로 기동했는지, "
            f"venv가 sibling venv 복사본은 아닌지 확인."
        )

    try:
        import FinanceDataReader as fdr  # noqa: N813
        parts = str(fdr.__version__).split(".")[:3]
        ver = tuple(int(x) for x in parts)
        if ver < _MIN_FDR:
            problems.append(
                f"finance-datareader {fdr.__version__} < 0.9.202 — 구버전은 "
                f"KS11/KQ11을 live KRX로 받아 LOGOUT. venv 재설치 필요."
            )
    except Exception as e:  # noqa: BLE001
        problems.append(f"finance-datareader import 실패: {e!r}")

    return problems


def assert_correct_environment(project_root: str) -> None:
    """문제 발견 시 stderr 출력 후 sys.exit(1). ALLOW_FOREIGN_VENV=1이면 경고만."""
    problems = check_environment(project_root)
    if not problems:
        return
    body = "기동 환경 가드 실패:\n  - " + "\n  - ".join(problems)
    if os.environ.get(_OVERRIDE_ENV) == "1":
        print(f"[ENV-GUARD][우회됨] {body}", file=sys.stderr)
        return
    print(f"[ENV-GUARD] {body}\n  (의도적이면 {_OVERRIDE_ENV}=1 로 우회)", file=sys.stderr)
    sys.exit(1)
