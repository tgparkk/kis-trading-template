"""DART 공시 제목(`report_nm`) 태그 사전 — 사전등록 `docs/prereg_2026-09-26_dart_disclosure_events.md` §3 🔒 그대로.

    from backtest.concept_axes.candidate_ledger.dart_events.dart_tags import normalize, tag_of
    tag, is_corr, flags = tag_of("[기재정정]주요사항보고서(유상증자결정)")   # ("유상증자", True, {...})

§3-1 정규화(순서 고정): ① 공백류 전부 제거 ② 가운뎃점류 6종 → `·`(U+00B7) ③ 앞머리 `[…]` 반복 제거 → prefixes · 나머지 = body.
§3-2 적용 순서(고정): is_corr 는 따로 · 태그 = ① 정정 외 접두 → 기타 ② 자회사·종속회사 주요경영사항 → 기타
③ 정규식 표(§3-3 순서 = t · body 앞머리 `^` · 첫 일치) · 불일치 → 기타.
🔴 결과를 본 뒤 정규식·순서·정정 규칙을 바꾸지 않는다(§13-1). 조회 시점 필드(rm·corp_name·corp_cls) 미사용(§13-5).
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

# ── §3-1 ────────────────────────────────────────────────────────────────────
MIDDOTS = ("ㆍ", "·", "・", "･", "∙", "‧")   # ㆍ · ・ ･ ∙ ‧
DOT = "·"
_WS_RE = re.compile(r"[\s​﻿]+")
_DOT_RE = re.compile("[" + "".join(MIDDOTS) + "]")
_PREFIX_RE = re.compile(r"^\[([^\]]*)\]")

# ── §3-2 ────────────────────────────────────────────────────────────────────
CORR_PREFIXES = frozenset({"기재정정", "첨부정정", "첨부추가", "정정"})
SUBSIDIARY_PHRASES = ("(자회사의주요경영사항)", "(종속회사의주요경영사항)")
OTHER = "기타"

# ── §3-3 🔒 표 순서 = 태그 번호 t(1..7) ─────────────────────────────────────────
TAG_TABLE: List[Tuple[int, str, str]] = [
    (1, "유상증자", r"^(주요사항보고서\()?유(무)?상증자결정"),
    (2, "CB/BW/EB", r"^(주요사항보고서\()?(전환사채권|신주인수권부사채권|교환사채권)발행결정"),
    (3, "자기주식취득", r"^(주요사항보고서\()?자기주식취득(결정|신탁계약체결결정)"),
    (4, "공급계약", r"^단일판매·공급계약체결"),
    (5, "최대주주변경", r"^(최대주주변경(\(|$)|최대주주변경을수반하는주식양수도계약체결"
                   r"|최대주주등소유주식변동신고서\(최대주주변경시\)|경영권변경등에관한계약체결)"),
    (6, "잠정실적", r"^((연결재무제표기준)?영업\(잠정\)실적\(공정공시\)"
                r"|매출액또는손익구조\d+%\(대규모법인은?\d+%\)이상(변동|변경))"),
    (7, "소송·횡령", r"^((주요사항보고서\()?소송등의제기|횡령·배임(혐의발생|사실확인))"),
]
TAGS: List[str] = [name for _, name, _ in TAG_TABLE]
TAG_NUM: Dict[str, int] = {name: t for t, name, _ in TAG_TABLE}
_COMPILED = [(t, name, re.compile(rx)) for t, name, rx in TAG_TABLE]
MGMT_DISPUTE = "경영권분쟁"                        # §3-3 t=7 부분집합(인쇄만)


def normalize(report_nm: str) -> Tuple[List[str], str]:
    """§3-1 — (prefixes, body). prefixes = 앞머리 `[…]` 안쪽 문자열(정규화 뒤 · 순서대로)."""
    s = _WS_RE.sub("", report_nm or "")
    s = _DOT_RE.sub(DOT, s)
    prefixes: List[str] = []
    while True:
        m = _PREFIX_RE.match(s)
        if not m:
            break
        prefixes.append(m.group(1))
        s = s[m.end():]
    return prefixes, s


def tag_of(report_nm: str) -> Tuple[str, bool, Dict[str, object]]:
    """§3-2 — (태그 이름, is_corr, flags). 태그 이름 ∈ TAGS ∪ {기타}."""
    prefixes, body = normalize(report_nm)
    is_corr = any(p in CORR_PREFIXES for p in prefixes)
    other_prefix = [p for p in prefixes if p not in CORR_PREFIXES]
    subsidiary = any(ph in body for ph in SUBSIDIARY_PHRASES)
    flags: Dict[str, object] = dict(prefixes=prefixes, body=body, other_prefix=bool(other_prefix),
                                    subsidiary=subsidiary, t=0, mgmt_dispute=False)
    if other_prefix:                                   # ① 정정 외 접두 → 기타
        return OTHER, is_corr, flags
    if subsidiary:                                     # ② 자회사·종속회사 주요경영사항 → 기타
        return OTHER, is_corr, flags
    for t, name, rx in _COMPILED:                      # ③ 표 순서 · 첫 일치
        if rx.match(body):
            flags["t"] = t
            flags["mgmt_dispute"] = (t == 7) and (MGMT_DISPUTE in body)
            return name, is_corr, flags
    return OTHER, is_corr, flags
