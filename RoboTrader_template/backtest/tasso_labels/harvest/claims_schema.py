# -*- coding: utf-8 -*-
"""주장 원장의 행 계약 — 병합기·검증기·테스트의 단일 출처.

🔑 열거식 가드는 반드시 빠뜨린다. 열·enum·상한을 **여기 한 곳**에만 두고
   소비자는 전부 이 모듈을 읽는다.
"""
from __future__ import annotations

TOPICS = (
    "①후보선정", "②앵커", "③분할매수", "④분할매도",
    "⑤데이터기반", "⑥국면대응", "⑦프로그램·상품", "⑧기타",
)

VS_V1 = ("new", "agree", "conflict", "revision", "none")

# 원장 전체 열 (quote 포함 = 로컬 전용 판본)
COLUMNS = (
    "log_no", "post_date", "category", "claim_id", "topic",
    "claim", "numbers", "quote", "para_idx", "image_ref",
    "vs_v1", "v1_anchor",
)

# 공개 판본 = quote 제거. 커밋되는 쪽에는 타인의 원문을 싣지 않는다.
PUBLIC_COLUMNS = tuple(c for c in COLUMNS if c != "quote")

QUOTE_MAX = 40

# 이 값들이면 1판의 어느 절과 관계 맺는지 반드시 밝혀야 한다.
ANCHOR_REQUIRED = ("agree", "conflict", "revision")
# 이 값들이면 1판과 무관하므로 anchor 가 있으면 안 된다(반대 방향 결속).
ANCHOR_FORBIDDEN = ("new", "none")


def validate_row(row):
    """위반 사유 리스트를 반환한다. 빈 리스트 = 통과."""
    bad = []
    for col in COLUMNS:
        if col not in row:
            bad.append("MISSING_COLUMN:" + col)
    if bad:
        return bad

    if row["category"] not in (28, 29):
        bad.append("BAD_CATEGORY:" + repr(row["category"]))
    if row["topic"] not in TOPICS:
        bad.append("BAD_TOPIC:" + repr(row["topic"]))
    if row["vs_v1"] not in VS_V1:
        bad.append("BAD_VS_V1:" + repr(row["vs_v1"]))

    quote = "" if row["quote"] is None else str(row["quote"])
    if len(quote) > QUOTE_MAX:
        bad.append("QUOTE_TOO_LONG:" + str(len(quote)) + ">" + str(QUOTE_MAX))

    anchor = ("" if row["v1_anchor"] is None else str(row["v1_anchor"])).strip()
    if row["vs_v1"] in ANCHOR_REQUIRED and not anchor:
        bad.append("ANCHOR_REQUIRED_FOR:" + str(row["vs_v1"]))
    if row["vs_v1"] in ANCHOR_FORBIDDEN and anchor:
        bad.append("ANCHOR_FORBIDDEN_FOR:" + str(row["vs_v1"]))

    if not str(row["claim"] or "").strip():
        bad.append("EMPTY_CLAIM")
    return bad
