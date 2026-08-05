# -*- coding: utf-8 -*-
"""[28]·[29] 파이프라인 검증 — V1(수집) · V2(원장) · V5(revision 재판정).

각 검사가 **서로 다른 실패 방식**을 잡는다. 하나가 다른 하나를 대체하지 않는다.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cat2829_common as C          # noqa: E402
import claims_schema as S           # noqa: E402


def v1_coverage(catalog_lognos, saved_lognos, post_cnt, listed_cnt):
    """목록 ↔ 저장 파일 차집합 0 강제 + postCnt 차이 기록.

    catalog_lognos / saved_lognos : set[str]
    post_cnt   : {categoryNo: int|None}   카테고리 API 가 주장하는 글 수
    listed_cnt : {categoryNo: int}        목록 API 가 실제로 준 글 수
    """
    missing = sorted(set(catalog_lognos) - set(saved_lognos))
    extra = sorted(set(saved_lognos) - set(catalog_lognos))
    delta = {}
    for cat, claimed in post_cnt.items():
        delta[cat] = None if claimed is None else listed_cnt.get(cat, 0) - claimed
    return {
        "status": "FAIL" if (missing or extra) else "PASS",
        "missing": missing,
        "extra": extra,
        "post_cnt_delta": delta,
    }


def v2_ledger_coverage(rows, expected_lognos):
    """원장이 **모든 글**을 덮는가.

    「글당 최소 1행」 규칙 덕에, 원장에 없는 log_no = 정독이 안 된 글이다.
    (주장이 없는 글도 topic=⑧기타 · vs_v1=none 행을 남기게 돼 있다.)
    """
    seen = {r["log_no"] for r in rows}
    missing = sorted(set(expected_lognos) - seen)
    return {
        "status": "FAIL" if missing else "PASS",
        "missing_lognos": missing,
        "rows": len(rows),
        "posts": len(seen),
    }


def v5_revision_candidates(rows):
    """`conflict` 로 분류된 행 중, **같은 (topic, v1_anchor)** 안에서 시간에 따라
    numbers 가 바뀐 묶음을 revision 후보로 올린다.

    ⚠️ 판정이 아니라 **후보 제시**다. 최종 분류는 사람이 한다.
    """
    groups = {}
    for r in rows:
        if r.get("vs_v1") != "conflict":
            continue
        key = (r["topic"], str(r.get("v1_anchor") or ""))
        groups.setdefault(key, []).append(r)

    out = []
    for (topic, anchor), grp in sorted(groups.items()):
        grp = sorted(grp, key=lambda r: (r["post_date"], r["log_no"]))
        numbers = [str(r.get("numbers") or "") for r in grp]
        if len(grp) < 2 or len(set(numbers)) < 2:
            continue
        out.append({
            "topic": topic,
            "v1_anchor": anchor,
            "timeline": [{"post_date": r["post_date"], "log_no": r["log_no"],
                          "numbers": str(r.get("numbers") or ""),
                          "claim_id": r["claim_id"]} for r in grp],
        })
    return out
