"""적격 테마(스펙 §4-2) — 검정 창 시작(2024-03-13) 전 테마(theme_no < N_cut) ∧ 사건·분류형 이름 제외.

N_cut 은 `ncut_evidence.py` 근거표로 PREREG 에서 정하고 `run.py`·러너 인자로 넘긴다(여기 기본값 없음).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, FrozenSet, Iterable, Mapping, Optional, Set, Tuple

SNAP_DATE = date(2026, 10, 8)        # 🔒 과거 검정 전 구간 고정 소속표(run_id 4 · 스펙 §4-3)

# 🔒 사건·분류형 테마 — 이름만 보고 정한다(결과 보기 전 · 스펙 §4-2 후보 목록 그대로).
EXCLUDED_NAME_PATTERNS: Tuple[str, ...] = (r"밸류업", r"지주사", r"SPAC|스팩", r"신규상장", r"여름", r"겨울", r"코로나")


def excluded_themes(theme_name: Mapping[int, str], patterns: Iterable[str] = EXCLUDED_NAME_PATTERNS) -> Set[int]:
    rx = [re.compile(p) for p in patterns]
    return {t for t, n in theme_name.items() if any(r.search(n) for r in rx)}


def eligible_themes(theme_name: Mapping[int, str], n_cut: Optional[int],
                    patterns: Iterable[str] = EXCLUDED_NAME_PATTERNS) -> Set[int]:
    """n_cut=None 이면 번호 경계 없음. 「전체 소속표」 변형은 `n_cut=None, patterns=()`."""
    ex = excluded_themes(theme_name, patterns)
    return {t for t in theme_name if (n_cut is None or t < n_cut) and t not in ex}


def restrict(members: Mapping[int, FrozenSet[str]], keep: Set[int]) -> Dict[int, FrozenSet[str]]:
    return {t: m for t, m in members.items() if t in keep}
