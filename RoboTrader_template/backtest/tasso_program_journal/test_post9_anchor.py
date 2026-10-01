# -*- coding: utf-8 -*-
"""`run_anchor_redesign.py --mode post9` 가드·판정값 스냅샷 시험 (post8 판 구조 승계 · 짧게).

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* · *가드를 시험하지 않으면 그것도 장식이다*.
🔴 동결 산출물(`RESULTS_ANCHOR_POST7*`·`POST8*`·`anchor_post8/`)은 고치지 않는다. 재실행 byte 시험은 **임시 디렉터리 사본**에서만 돈다.
🔴 post7·post8 경로 불변은 `test_post8_anchor.py`·`test_post7_anchor.py` 가 계속 검사한다(이 파일은 post9 만).

실행: `python -m pytest test_post9_anchor.py -q -p no:cacheprovider`
"""
from __future__ import annotations

import contextlib
import io
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

import run_anchor_redesign as ANC

BASE = Path(__file__).resolve().parent
NUM9 = BASE / "RESULTS_ANCHOR_POST9_NUMBERS.md"
DOC9 = BASE / "RESULTS_ANCHOR_POST9.md"


def db_ok():
    try:
        import psycopg2
        from run_tests import DSN
        psycopg2.connect(connect_timeout=5, **DSN).close()
        return True
    except Exception:  # noqa: BLE001
        return False


# ── P1 상수 · 표본 ──────────────────────────────────────────────────────────
def test_p1_post9_constants_and_post8_untouched():
    assert ANC.PUB9 == "2026-09-23" == ANC.POST9_END and ANC.POST9_LOG_NO == "224421214462"
    assert ANC.POST8_END == "2026-09-18" and ANC.END == "2026-09-11", "post7·post8 상수 불변"
    assert ANC.PAIR_GATE == 40 and ANC.MIN_N == 3 and ANC.NULL_SEED == 20260815 and ANC.S_ANCHOR == 100
    assert ANC.ANC9_STAMP_DIR == "anchor_post9" and ANC.ANC8_STAMP_DIR == "anchor_post8"


def test_p1_post9_sample_equals_intake():
    got = [(n, c, d, k) for n, c, d, k, *_ in ANC.POST9_EXACT]
    assert got == [("삼미금속", "012210", "2026-09-04", 1), ("에스투더블유", "488280", "2026-09-10", 1),
                   ("빛샘전자", "072950", "2026-09-14", 1), ("한국첨단소재", "062970", "2026-09-15", 4),
                   ("한컴위드", "054920", "2026-09-15", 2)]
    assert not any(rein for *_x, rein, _p in ANC.POST9_EXACT), "재진입 0 ⇒ ② 축 항등"
    assert ANC.POST9_APPROX == [] and ANC.POST9_FOLLOWUP == ["우리기술"], "approx 0 · 후속 계수 안 함"
    items = ANC.post9_items()
    assert len(items) == 5 and all(it["post"] == 9 and it["post_date"] == "2026-09-23" for it in items)
    ns = sorted(int(it["fill_n"]) for it in items)
    assert ns == [1, 1, 1, 2, 4]
    tot = len(ns) * (len(ns) - 1) // 2
    assert tot - sum(c * (c - 1) // 2 for c in Counter(ns).values()) == 7, "그 글 열 쌍 상한 7(구성)"


def test_p1_retro9_is_post1_to_8():
    dist = Counter(i["post"] for i in ANC.retro9_items())
    assert [dist.get(k, 0) for k in range(1, 9)] == [0, 2, 3, 6, 7, 10, 6, 4]
    assert 9 not in dist, "post9 건이 소급 열로 새 들어오지 않는다"


# ── P2 진입점 ──────────────────────────────────────────────────────────────
def test_p2_cli_entrypoints():
    for fn, argv in ((ANC.cli9, []), (ANC.cli9, ["--mode", "post10"]), (ANC.cli, ["--mode", "post9"])):
        with contextlib.redirect_stderr(io.StringIO()):
            with pytest.raises(SystemExit) as e:
                fn(argv)
        assert e.value.code == 2, (fn.__name__, argv)
    src = (BASE / "run_anchor_redesign.py").read_text(encoding="utf-8")
    assert "sys.exit(cli())" in src and "cli = cli9" in src
    assert src.index("def main_post9") < src.index("# 🆕 `--mode post8` — **순수 덧붙임**"), "post9 블록은 post8 표식 앞"


# ── P3 가드가 문다 ─────────────────────────────────────────────────────────────
def test_p3_grade_and_duty_guards_bite():
    ok = list(ANC._DUTY9)
    assert ANC._assert_duties9(ok) and ANC._assert_no_grade9(ok)
    for bad in ("GT-D", "조건 미달", "충족·참고용"):
        with pytest.raises(AssertionError):
            ANC._assert_no_grade9(ok + [bad])
    for m in ("`P9-공통독법`: 답 = 판정", "라이브 채택 금지.", "항등(명시 인쇄)"):
        with pytest.raises(AssertionError):
            ANC._assert_duties9([x for x in ok if x != m])


def test_p3_lad_cumulative_parser9(tmp_path):
    assert ANC.lad_cumulative_pairs9(tmp_path)[0] is None
    (tmp_path / ANC.LAD_POST9_NUMBERS).write_text("x\n**누적 비교가능 쌍 = 435**\ny\n", encoding="utf-8")
    assert ANC.lad_cumulative_pairs9(tmp_path)[0] == 435
    (tmp_path / ANC.LAD_POST9_NUMBERS).write_text("누적 비교가능 쌍 = 435\n", encoding="utf-8")
    assert ANC.lad_cumulative_pairs9(tmp_path)[0] is None, "줄 형식이 다르면 잡지 않는다(대칭)"


# ── P4 산출물 구조 · 판정값 스냅샷 ───────────────────────────────────────────────
@pytest.mark.skipif(not NUM9.exists(), reason="산출물 아직 없음")
def test_p4_numbers_structure_and_p9_prints():
    L = NUM9.read_text(encoding="utf-8").splitlines()
    body = "\n".join(L)
    assert L[0] == "# RESULTS_ANCHOR_POST9_NUMBERS — 기계 생성 (수정 금지)"
    assert ANC._assert_duties9(L) and ANC._assert_no_grade9(L)
    assert "**창 종료 2026-09-23 = 발행 당일(수 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1**" in body
    assert re.search(r"\*\*실행 시 `max\(date\)` = 20\d\d-\d\d-\d\d · 그 날짜 행수 [\d,]+ — 기록만\(창 아님\)\*\*", body)
    assert "`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음" in body
    # 라이브 채택 금지 문언(PREREG_POST9 §0-1)
    assert "저자가 *\"사람이 할 일은 종목 고르는 것까지\"* 라고 적었다." in body and "**기록**이지 전략 후보가 아니다" in body
    # D-1 세 수 — ① 7 · ② = ③ = LAD 파일의 수 ≥ 40
    one = re.search(r"\*\*D-1 ①\*\* 그 글 «단독» 비교가능 쌍 \| \*\*(\d+)\*\*", body)
    two = re.search(r"\*\*D-1 ②\*\* 누적 비교가능 쌍 \| \*\*(\d+)\*\*", body)
    three = re.search(r"\*\*D-1 ③\*\* 게이트 판정에 쓴 수\(= ②\) \| \*\*(\d+)\*\*", body)
    assert one and two and three and two.group(1) == three.group(1) and int(two.group(1)) >= 40 and one.group(1) == "7"
    # 그 글 열 후보별 쌍(스냅샷) · 게이트가 열려 V(R_j) 대조가 돌았다
    for c, comp in (("A0", 7), ("A1", 6), ("A2", 6), ("A3", 7)):
        assert any(ln.startswith(f"| {c} | **{comp}** |") and "`V(R_j) ≤ V(X)`" in ln for ln in L), c
    # ANC-N4 전수 표 = 3 판정 × 4 후보 = 12 행 · 세 축 줄 · ②③ 항등 명시
    assert len([ln for ln in L if re.match(r"^\| `ANC-P[123]` \| A[0-3] \|", ln)]) == 12
    for ax in ("- 축 ①:", "- 축 ②:", "- 축 ③:"):
        assert any(ln.startswith(ax) for ln in L), ax
    assert body.count("항등(명시 인쇄)") >= 2 and "살아 있다" in body
    # D-9 ⑤ — 걸침 3(빛샘 19/1 · 첨단·한컴 18/2) · 삼미 6/8 · 에스투 2/8 · 「전부 경계 후」 줄
    assert "경계 전 `19` 봉 / 후 `1` 봉 · 혼합 빈티지" in body and body.count("경계 전 `18` 봉 / 후 `2` 봉 · 혼합 빈티지") == 2
    assert "경계 전 `6` 봉 / 후 `8` 봉" in body and "경계 전 `2` 봉 / 후 `8` 봉" in body
    assert "전부 제도 경계 2026-09-14 후(전 0 / 후 8)" in body
    # 창5 END 문제 — 검정 열 0 · 소급 열 «확인 필요»
    assert "검정 열 D+4 > `END` 건 = 0건" in body and "확인 필요" in body
    # 소급 각주가 소급 표마다 · 판정 표는 선두 기호(abcbb01 규약)
    assert body.count("소급 = 탐색 · 채택은 그 글 열로만") >= 8
    rows = [ln for ln in L if re.match(r"^\| `ANC-P[12]` × A[023] \|", ln)]
    assert len(rows) == 6 and all(re.search(r"\| (✅ 성립|❌ 불성립|⛔ |미룸)", ln) for ln in rows), rows
    assert any(ln.startswith("| `ANC-P3` × 전 후보 |") and re.search(r"\| (✅ 성립|❌ 불성립|⛔ |미룸)", ln) for ln in L)
    # D-9 ① = stamp 파일과 일치
    import json
    m1 = re.search(r"^\| 🔴 D-9 ① 쿼리 실행 시각\(KST\) \| \*\*(2026-\d\d-\d\d \d\d:\d\d:\d\d)\*\*", body, re.M)
    st = json.loads((BASE / ANC.ANC9_STAMP_DIR / "read_stamp.json").read_text(encoding="utf-8"))
    assert m1 and st["first_read_kst"] == m1.group(1) and st["timezone"] == "Asia/Seoul"
    assert st["fingerprint"]["span"] == [ANC.ANC9_SPAN_START, ANC.POST9_END]


@pytest.mark.skipif(not (NUM9.exists() and DOC9.exists()), reason="산출물 아직 없음")
def test_p4_doc_equals_numbers_except_title():
    a = NUM9.read_text(encoding="utf-8").splitlines()
    b = DOC9.read_text(encoding="utf-8").splitlines()
    assert a[1:] == b[1:] and a[0] != b[0]


def test_p4_script_writes_only_post9_files_in_post9_block():
    src = (BASE / "run_anchor_redesign.py").read_text(encoding="utf-8")
    blk = src.split("def main_post9", 1)[1].split("def cli9", 1)[0]
    targets = re.findall(r'BASE / "([^"]+)"\)\.write_text', blk)
    assert sorted(targets) == ["RESULTS_ANCHOR_POST9.md", "RESULTS_ANCHOR_POST9_NUMBERS.md"]
    assert not re.search(r'^END = "', blk, re.M) and "anchor_post8" not in blk and "POST8_NUMBERS" not in blk


@pytest.mark.skipif(not (db_ok() and NUM9.exists()), reason="DB·산출물 없음")
def test_p5_rerun_byte_identical_in_tmp_copy(tmp_path):
    """같은 스냅샷·같은 stamp 로 사본 디렉터리에서 재실행 ⇒ 작업트리 산출물과 byte 동일(작업트리는 쓰지 않는다)."""
    for p in list(BASE.glob("*.py")) + list(BASE.glob("*.csv")):
        if not p.name.startswith("test_"):
            shutil.copy2(p, tmp_path / p.name)
    shutil.copy2(BASE / ANC.LAD_POST9_NUMBERS, tmp_path / ANC.LAD_POST9_NUMBERS)
    shutil.copytree(BASE / ANC.ANC9_STAMP_DIR, tmp_path / ANC.ANC9_STAMP_DIR)
    r = subprocess.run([sys.executable, "-X", "utf8", "run_anchor_redesign.py", "--mode", "post9"], cwd=str(tmp_path),
                       capture_output=True, text=True, encoding="utf-8", timeout=900)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    for f in ("RESULTS_ANCHOR_POST9_NUMBERS.md", "RESULTS_ANCHOR_POST9.md"):
        assert (tmp_path / f).read_bytes() == (BASE / f).read_bytes(), f
