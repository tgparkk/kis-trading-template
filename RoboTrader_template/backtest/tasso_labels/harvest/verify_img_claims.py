# -*- coding: utf-8 -*-
"""T11 이미지 원장 — 행 계약 + 검증기.

이 트랙의 원장은 **2층**이다. 산문 원장(`claims_cat2829.csv` / `..._quoted.csv`)과
같은 경계를 그림에도 그대로 적용한다:

    공개 원장  img_claims_28_29.csv         커밋된다.  `topic` = «무엇에 관한 항목인가»
    비공개 원장 img_claims_28_29_quoted.csv  gitignore. 판독·판정 원문 무손실

🔴 경계선은 **값 대 구조**다. 저자가 본문에서 *"아래 수치도 원래 공개하면 안되지만..."* 이라
   직접 밝혔듯 가려야 하는 것은 「값」이고, 그 값이 **어떤 절차로 나오는가**(구조)는
   저자 본문이 이미 산문으로 설명한다. 그래서 공개 원장은 구조만 적고 값을 적지 않는다.

⚠️ 그러므로 이 파일의 본체는 `scan_topic()` = **유출 검사**다. 나머지 검사는 원장이
   입력과 어긋나지 않았음을 보는 것이고, 유출 검사만이 **저작권 경계 자체**를 지킨다.
   판별력은 양방향으로 증명한다 — 일부러 값을 넣은 행에서 FAIL 이 나야 하고(양성),
   정상 75행에서는 한 건도 안 울려야 한다(음성). tests/test_cat2829_pipeline.py 참조.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cat2829_common as C          # noqa: E402

READINGS_DIR = C.HARVEST / "img_readings"
JUDGES_DIR = READINGS_DIR / "judges"
TOPICS_JSON = C.HARVEST / "img_topics.json"
IMG_TARGETS_JSON = C.HARVEST / "image_targets.json"
IMG_PUBLIC_CSV = C.HARVEST / "img_claims_28_29.csv"
IMG_QUOTED_CSV = C.HARVEST / "img_claims_28_29_quoted.csv"

# 판정 대상 = 판독에서 methodology 를 채운 항목(= 그림이 방법을 말하는 항목).
EXPECTED_ROWS = 75

# 비공개 원장의 전체 열. 판독 4열 + 판정 4열이 원문 그대로 실린다.
COLUMNS = (
    "log_no", "post_date", "category", "img_no", "content_type",
    "topic", "vs_text", "judge_agree", "readable",
    "verbatim", "methodology", "numbers", "note",
    "verdict_A", "evidence_A", "verdict_B", "evidence_B",
)
# 공개 판본 = 판독·판정 «원문» 전부 제거. 남는 것은 분류축과 topic 뿐이다.
PUBLIC_COLUMNS = (
    "log_no", "post_date", "category", "img_no", "content_type",
    "topic", "vs_text", "judge_agree", "readable",
)

VERDICTS = ("있음", "부분", "없음")

# 신규성 순위 — 클수록 «본문에 없다 = 새롭다». 합의는 **작은 쪽**을 택한다.
#   있음 = 본문에 이미 있다(그림이 새로 주는 것 없음)
#   부분 = 일부만 본문에 있다
#   없음 = 본문에 전혀 없다(그림만의 정보)
NOVELTY = {"있음": 0, "부분": 1, "없음": 2}


def consensus(verdict_a, verdict_b):
    """두 판정자의 **보수적 합의** → (vs_text, judge_agree).

    둘이 같으면 그대로. 갈리면 **덜 새로운 쪽**(NOVELTY 가 작은 쪽)을 택한다.
    🔑 근거: 이 원장이 뒤에 쓰일 자리는 「그림에만 있는 정보가 얼마나 되는가」이고,
       거기서 틀리면 안 되는 방향은 **신규성을 부풀리는 쪽**이다. 판정이 갈렸다는
       사실 자체는 `judge_agree=False` 로 남겨 나중에 사람이 다시 볼 수 있게 둔다.
    """
    for v in (verdict_a, verdict_b):
        if v not in NOVELTY:
            raise ValueError("BAD_VERDICT:" + repr(v))
    if verdict_a == verdict_b:
        return verdict_a, True
    return (verdict_a if NOVELTY[verdict_a] < NOVELTY[verdict_b] else verdict_b), False


# ===========================================================================
# 유출 검사 — 이 파일의 본체
# ===========================================================================
# ⚠️ 오경보를 내지 않는 것도 계약이다. 검사가 정상 행에서 울면 사람이 검사를 끄고,
#    그 순간 경계는 «있다고 믿어지는» 상태로만 남는다.
LEAK_PATTERNS = (
    # 3자리 이상 연속 숫자 = 표본 수·가격·연도 등 화면 값
    ("DIGITS3", re.compile(r"\d{3,}")),
    # 1,234 처럼 콤마로 끊긴 큰 수 (위 패턴이 자릿수 단위로는 못 잡는 형태)
    ("GROUPED_NUM", re.compile(r"\d{1,3}(?:,\d{3})+")),
    # 소수 = 비율·배수·버전 등 화면 값
    ("DECIMAL", re.compile(r"\d+\.\d+")),
    ("PERCENT", re.compile(r"[%％]")),
    # HDR 커버 «값». 'HDR 커버리지' 같은 구조 서술은 통과시킨다.
    ("HDR_VALUE", re.compile(r"HDR\s*\d")),
    ("QUARTILE", re.compile(r"Q[1-3]\b")),
    ("MONEY", re.compile(r"\d[\d,]*\s*(?:원|억|만원)")),
    ("COUNT", re.compile(r"\d[\d,]*\s*(?:개|건|주(?![가-힣])|배(?![가-힣]))")),
    # 1/4 · 1/2 같은 문턱 분수
    ("FRACTION", re.compile(r"\d\s*/\s*\d")),
)


def scan_topic(text):
    """공개 원장 `topic` 에 값이 샜는지 본다. [(패턴명, 걸린조각)] — 비면 통과."""
    hits = []
    for name, rx in LEAK_PATTERNS:
        for m in rx.finditer(str(text or "")):
            hits.append((name, m.group(0)))
    return hits


# ===========================================================================
# 입력 적재
# ===========================================================================

def _jsonl(path):
    with open(str(path), encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if line:
                yield lineno, json.loads(line)


def load_readings(readings_dir=None):
    """`img_readings/*.jsonl` → {"{stem}#{img_no}": 판독행}. judges/ 는 하위 디렉토리."""
    d = str(readings_dir or READINGS_DIR)
    out = {}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".jsonl"):
            continue
        stem = fn[:-len(".jsonl")]
        for lineno, row in _jsonl(os.path.join(d, fn)):
            if row.get("stem") != stem:
                raise ValueError("%s:%d STEM_MISMATCH:%r" % (fn, lineno, row.get("stem")))
            key = "%s#%d" % (stem, int(row["img_no"]))
            if key in out:
                raise ValueError("%s:%d DUPLICATE_READING:%s" % (fn, lineno, key))
            out[key] = row
    return out


def load_judges(judges_dir=None):
    """판정 4본 → (A, B). A = C1·C2, B = D1·D2. 둘의 id 집합이 같아야 한다."""
    d = str(judges_dir or JUDGES_DIR)
    sides = {"C": {}, "D": {}}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".jsonl"):
            continue
        side = fn.split("judge_")[-1][0]
        if side not in sides:
            raise ValueError("UNKNOWN_JUDGE_FILE:" + fn)
        for lineno, row in _jsonl(os.path.join(d, fn)):
            key = row["id"]
            if key in sides[side]:
                raise ValueError("%s:%d DUPLICATE_JUDGMENT:%s" % (fn, lineno, key))
            sides[side][key] = row
    return sides["C"], sides["D"]


def read_ledger(path):
    with open(str(path), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ===========================================================================
# 검사 — 각각 «다른 실패 방식» 을 잡는다
# ===========================================================================

def check_row_counts(public_rows, quoted_rows, expected=EXPECTED_ROWS):
    bad = []
    if len(public_rows) != expected:
        bad.append("PUBLIC_ROWS:%d≠%d" % (len(public_rows), expected))
    if len(quoted_rows) != expected:
        bad.append("QUOTED_ROWS:%d≠%d" % (len(quoted_rows), expected))
    return bad


def check_public_columns(public_rows):
    """🔴 공개본에 판독·판정 «원문» 열이 되살아나면 경계가 통째로 무너진다."""
    if not public_rows:
        return ["NO_PUBLIC_ROWS"]
    cols = tuple(public_rows[0].keys())
    if cols != PUBLIC_COLUMNS:
        return ["PUBLIC_COLUMNS:%s" % (list(cols),)]
    return []


def check_no_value_leak(public_rows):
    """★ 주 검사 — `topic` 에 화면 수치가 샜는가."""
    bad = []
    for r in public_rows:
        for name, frag in scan_topic(r.get("topic")):
            bad.append("%s#%s [%s] %r" % (r.get("log_no"), r.get("img_no"), name, frag))
    return bad


def check_topics_source_no_leak(topics):
    """🔴 `img_topics.json` **도 커밋된다**.

    빌더가 생성 시점에 막지만, 그건 «빌드를 돌렸을 때» 뿐이다. 원본 JSON 만 고치고
    재빌드를 안 하면 CSV 는 깨끗한데 JSON 에 값이 실린 채 커밋된다 — 경계가 파일
    하나만큼 뚫린다. 그래서 출처 파일도 같은 검사를 통과해야 한다.
    """
    bad = []
    for key, topic in topics.items():
        if key.startswith("_"):
            continue
        for name, frag in scan_topic(topic):
            bad.append("%s [%s] %r" % (key, name, frag))
    return bad


def check_consensus(quoted_rows):
    """`vs_text`·`judge_agree` 가 보수적 합의 규칙 그대로인가."""
    bad = []
    for r in quoted_rows:
        want_vs, want_agree = consensus(r["verdict_A"], r["verdict_B"])
        got_agree = str(r["judge_agree"]).strip().lower() == "true"
        if r["vs_text"] != want_vs or got_agree != want_agree:
            bad.append("%s#%s A=%s B=%s → vs_text=%s agree=%s (기대 %s/%s)" % (
                r["log_no"], r["img_no"], r["verdict_A"], r["verdict_B"],
                r["vs_text"], r["judge_agree"], want_vs, want_agree))
    return bad


def check_ids_exist(rows, targets, readings, judges_a, judges_b):
    """`log_no`·`img_no` 가 대상 목록과 판독·판정에 실재하는가."""
    by_logno = {t["log_no"]: t for t in targets}
    bad = []
    for r in rows:
        t = by_logno.get(str(r["log_no"]))
        if t is None:
            bad.append("UNKNOWN_LOG_NO:%s" % r["log_no"])
            continue
        if str(r["post_date"]) != t["post_date"] or str(r["category"]) != str(t["category"]):
            bad.append("META_MISMATCH:%s %s/%s" % (r["log_no"], r["post_date"], r["category"]))
        key = "%s#%s" % (t["stem"], r["img_no"])
        if key not in readings:
            bad.append("NO_READING:%s" % key)
        if key not in judges_a or key not in judges_b:
            bad.append("NO_JUDGMENT:%s" % key)
    return bad


_LOSSLESS_FROM_READING = ("verbatim", "methodology", "numbers", "note")


def check_lossless(quoted_rows, targets, readings, judges_a, judges_b):
    """🔴 비공개 원장이 입력을 **문자 단위**로 그대로 담았는가.

    ⚠️ 이 검사가 없으면 원장은 «요약» 이 될 수 있고, 그러면 뒤에 인용할 때 원문이
       아니라 우리가 쓴 문장을 저자 발언으로 귀속하게 된다 — 이 트랙이 이미 겪은 사고다.
    """
    by_logno = {t["log_no"]: t for t in targets}
    bad = []
    for r in quoted_rows:
        t = by_logno.get(str(r["log_no"]))
        if t is None:
            continue
        key = "%s#%s" % (t["stem"], r["img_no"])
        rd = readings.get(key)
        if rd is None:
            continue
        for col in _LOSSLESS_FROM_READING:
            if r[col] != str(rd.get(col) or ""):
                bad.append("READING_DRIFT:%s.%s" % (key, col))
        for col, src in (("verdict_A", judges_a), ("verdict_B", judges_b)):
            if r[col] != str(src[key]["verdict"]):
                bad.append("JUDGE_DRIFT:%s.%s" % (key, col))
        for col, src in (("evidence_A", judges_a), ("evidence_B", judges_b)):
            if r[col] != str(src[key].get("evidence") or ""):
                bad.append("JUDGE_DRIFT:%s.%s" % (key, col))
        if str(rd.get("content_type")) != r["content_type"]:
            bad.append("READING_DRIFT:%s.content_type" % key)
        if str(bool(rd.get("readable"))) != r["readable"]:
            bad.append("READING_DRIFT:%s.readable" % key)
    return bad


def run_all():
    """[(검사명, [위반...])] 을 돌려준다. 전부 빈 리스트면 통과."""
    targets = json.loads(IMG_TARGETS_JSON.read_text(encoding="utf-8"))
    readings = load_readings()
    ja, jb = load_judges()
    public_rows = read_ledger(IMG_PUBLIC_CSV)
    quoted_rows = read_ledger(IMG_QUOTED_CSV)
    topics = json.loads(TOPICS_JSON.read_text(encoding="utf-8"))
    return [
        ("행수", check_row_counts(public_rows, quoted_rows)),
        ("공개열", check_public_columns(public_rows)),
        ("★유출", check_no_value_leak(public_rows)),
        ("★출처", check_topics_source_no_leak(topics)),
        ("합의", check_consensus(quoted_rows)),
        ("id실재", check_ids_exist(public_rows, targets, readings, ja, jb)),
        ("무손실", check_lossless(quoted_rows, targets, readings, ja, jb)),
    ]


def main():
    results = run_all()
    rc = 0
    for name, bad in results:
        print("%-6s %s%s" % (name, "PASS" if not bad else "FAIL",
                             "" if not bad else " (%d건)" % len(bad)))
        for line in bad[:20]:
            print("   ", line)
        if bad:
            rc = 1
    print("판별력 증명(양방향)은 tests/test_cat2829_pipeline.py 의 T11 절이 맡는다.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
