# -*- coding: utf-8 -*-
"""T11 판독·판정 JSONL → 이미지 원장 CSV 2벌.

    img_claims_28_29.csv        판독·판정 원문 제거 = 커밋본
    img_claims_28_29_quoted.csv 원문 포함 = 로컬 전용 (gitignore 재차단)

입력은 전부 `img_readings/` 아래에 보존돼 있다(그 자체도 gitignore 대상).
`topic` 은 기계가 못 만든다 — 사람이 항목마다 읽고 쓴 `img_topics.json` 이 출처다.

계약·검사는 verify_img_claims.py 가 SSOT 다. 여기서는 그걸 **불러서** 쓴다
(빌더가 자기 규칙을 따로 갖고 있으면 두 벌이 조용히 갈라진다).
"""
from __future__ import annotations

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_img_claims as V       # noqa: E402


def build_rows(targets, readings, judges_a, judges_b, topics):
    """판정된 id 전건에 대해 원장 행을 만든다. 정렬은 (날짜, log_no, img_no)."""
    by_stem = {t["stem"]: t for t in targets}
    rows = []
    for key in judges_a:
        if key not in judges_b:
            raise ValueError("JUDGE_B_MISSING:" + key)
        stem, img_no = key.split("#")
        img_no = int(img_no)
        t = by_stem[stem]
        rd = readings[key]
        topic = topics.get(key)
        if not topic or not str(topic).strip():
            raise ValueError("TOPIC_MISSING:" + key)
        leaks = V.scan_topic(topic)
        if leaks:
            # 🔴 원장을 만들면서 막는다. 검증 단계까지 미루면 값이 든 CSV 가
            #    한 번은 디스크에 쓰이고, 그 파일은 공개본이라 추적 대상이 된다.
            raise ValueError("TOPIC_LEAK:%s %s" % (key, leaks))
        vs_text, agree = V.consensus(judges_a[key]["verdict"], judges_b[key]["verdict"])
        rows.append({
            "log_no": t["log_no"],
            "post_date": t["post_date"],
            "category": t["category"],
            "img_no": img_no,
            "content_type": str(rd.get("content_type") or ""),
            "topic": str(topic),
            "vs_text": vs_text,
            "judge_agree": str(bool(agree)),
            "readable": str(bool(rd.get("readable"))),
            "verbatim": str(rd.get("verbatim") or ""),
            "methodology": str(rd.get("methodology") or ""),
            "numbers": str(rd.get("numbers") or ""),
            "note": str(rd.get("note") or ""),
            "verdict_A": str(judges_a[key]["verdict"]),
            "evidence_A": str(judges_a[key].get("evidence") or ""),
            "verdict_B": str(judges_b[key]["verdict"]),
            "evidence_B": str(judges_b[key].get("evidence") or ""),
        })
    rows.sort(key=lambda r: (r["post_date"], r["log_no"], r["img_no"]))
    return rows


def write_ledgers(rows, public_path, quoted_path):
    for path, cols in ((quoted_path, V.COLUMNS), (public_path, V.PUBLIC_COLUMNS)):
        with open(str(path), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(cols), extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)


def main():
    targets = json.loads(V.IMG_TARGETS_JSON.read_text(encoding="utf-8"))
    readings = V.load_readings()
    ja, jb = V.load_judges()
    topics = {k: v for k, v in
              json.loads(V.TOPICS_JSON.read_text(encoding="utf-8")).items()
              if not k.startswith("_")}
    rows = build_rows(targets, readings, ja, jb, topics)
    extra = sorted(set(topics) - {"%s#%d" % (
        {t["log_no"]: t["stem"] for t in targets}[r["log_no"]], r["img_no"]) for r in rows})
    if extra:
        raise ValueError("TOPIC_ORPHAN:" + repr(extra))
    write_ledgers(rows, V.IMG_PUBLIC_CSV, V.IMG_QUOTED_CSV)
    print("이미지 원장", len(rows), "행 · 글",
          len({r["log_no"] for r in rows}), "건 ·",
          "판정 갈림", sum(1 for r in rows if r["judge_agree"] == "False"), "건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
