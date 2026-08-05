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
