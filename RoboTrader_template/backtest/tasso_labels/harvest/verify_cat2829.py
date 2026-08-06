# -*- coding: utf-8 -*-
"""[28]·[29] 파이프라인 검증 — V1(수집) · V2(원장) · V5(revision 재판정).

각 검사가 **서로 다른 실패 방식**을 잡는다. 하나가 다른 하나를 대체하지 않는다.
"""
from __future__ import annotations

import datetime
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


# ============================ V1 배선 (진입점) ============================

def listed_counts(catalog):
    """카탈로그가 실제로 담은 글 수를 카테고리별로 센다.

    🔑 키를 str 로 맞춘다 — `post_cnt` 는 JSON 객체라 키가 항상 str 이고,
       v1_coverage 는 `listed_cnt.get(cat, 0)` 로 **같은 키**를 찾는다.
       한쪽만 int 면 전 카테고리가 조용히 0 으로 세어져 delta 가 거짓이 된다.
    """
    out = {}
    for entry in catalog.get("posts", {}).values():
        key = str(entry.get("category"))
        out[key] = out.get(key, 0) + 1
    return out


def main():
    """CATLIST_JSON · POSTMETA_JSON 을 읽어 V1 을 돌리고 VERIFY_LOG 에 남긴다.

    🔑 이 배선이 없어서 C1(logNo 타입) 파급이 테스트에 안 잡혔다. 부품만 테스트하면
       「어느 파일을 읽어 어느 집합끼리 비교하는가」가 통째로 사각지대가 된다.
    반환: PASS 0 / FAIL 1.
    """
    catalog = json.loads(C.CATLIST_JSON.read_text(encoding="utf-8"))
    metas = json.loads(C.POSTMETA_JSON.read_text(encoding="utf-8"))

    catalog_lognos = {str(k) for k in catalog.get("posts", {})}
    saved_lognos = {str(m["log_no"]) for m in metas}
    post_cnt = {str(k): v for k, v in (catalog.get("post_cnt") or {}).items()}
    result = v1_coverage(catalog_lognos, saved_lognos, post_cnt, listed_counts(catalog))

    record = dict(result, check="V1",
                  checked_at=datetime.datetime.now().isoformat(timespec="seconds"),
                  catalog_posts=len(catalog_lognos), saved_posts=len(saved_lognos))
    with open(str(C.VERIFY_LOG), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print("V1", result["status"], "· 목록", len(catalog_lognos),
          "건 · 저장", len(saved_lognos), "건")
    print("post_cnt_delta", result["post_cnt_delta"])
    if result["missing"]:
        print("🔴 목록에 있는데 저장 안 됨", len(result["missing"]), "건:",
              result["missing"][:20])
    if result["extra"]:
        print("🔴 목록에 없는데 저장됨", len(result["extra"]), "건:", result["extra"][:20])
    # ⚠️ 중단하지 않는다 — 이건 우리 결함이 아니라 근거의 부재이고, 판단은 사람이 한다.
    if post_cnt and all(v is None for v in post_cnt.values()):
        print("⚠️ post_cnt 가 전부 None — 카테고리 API 가 글 수를 안 줬다. "
              "「전수」를 뒷받침할 **독립 증거가 없다**(목록 API 혼자 자기를 증명 중).")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
