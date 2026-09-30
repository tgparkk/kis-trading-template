# -*- coding: utf-8 -*-
"""`run_s5_post9.py` 가드 시험 — post8 판(`test_post8_s5.py`) 구조 승계 · 짧게.

🔑 단독 단언은 판별력이 없다 → 대칭 단언 · 가드를 시험하지 않으면 그것도 장식이다.
🔴 재실행 byte 시험은 **같은 DB 지문**일 때만 돈다(지문이 움직이면 skip — 산출물을 덮어쓰지 않는다).

실행: `python -m pytest test_post9_s5.py -q -p no:cacheprovider`
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import run_s5_post8 as S8
import run_s5_post9 as S9

BASE = Path(__file__).resolve().parent
NUMBERS = BASE / S9.OUT_NAME
STAMP = BASE / S9.STAMP_DIR / "read_stamp.json"
BASE_REF = "30aed89"   # post9 원장 커밋 = post9 레인 산출 «이전»


def git(*a):
    return subprocess.run(["git", *a], cwd=str(BASE), capture_output=True, text=True, encoding="utf-8")


def db_ok():
    try:
        import psycopg2
        from run_tests import DSN
        psycopg2.connect(connect_timeout=5, **DSN).close()
        return True
    except Exception:  # noqa: BLE001
        return False


# ── P1 상수 · 표본 ──────────────────────────────────────────────────────────
def test_p1_constants_and_sample_equal_intake():
    assert S9.POST_LOG == "224421214462" and S9.POST_DATE == S9.DB_UPTO == S9.PIT_CUTOFF == "2026-09-23"
    assert S9.MIN_JUDGEABLE == 3 and S9.BAND_PP == 10 and S9.APPROX == []
    assert S9.EXACT5 == [("삼미금속", "012210", "2026-09-04"), ("에스투더블유", "488280", "2026-09-10"),
                         ("빛샘전자", "072950", "2026-09-14"), ("한국첨단소재", "062970", "2026-09-15"),
                         ("한컴위드", "054920", "2026-09-15")]
    intake = (BASE / "INTAKE_2026-09-24_post9.md").read_text(encoding="utf-8")
    for nm, code, _d in S9.EXACT5:
        assert re.search(rf"\| {nm} \| {code} \|", intake), nm


def test_p1_live_ban_is_prereg_post9_line39_verbatim():
    line39 = (BASE / "PREREG_POST9.md").read_text(encoding="utf-8").splitlines()[38]
    assert line39 == "> " + S9.LIVE_BAN


def test_p1_ledger_guard_passes_and_bites(tmp_path):
    rows = S9.ledger_rows()
    assert S9.assert_ledger_matches(rows)
    bad = [dict(r) for r in rows]
    bad[1]["reg_date"] = "2026-09-05"
    with pytest.raises(AssertionError):
        S9.assert_ledger_matches(bad)
    bad2 = [dict(r) for r in rows]
    bad2[0]["prog_ver"] = "1.0.42"
    with pytest.raises(AssertionError):
        S9.assert_ledger_matches(bad2)


# ── P2 판정 로직 = post8 객체 그대로(새로 쓰기 0) ────────────────────────────
def test_p2_verdict_logic_is_imported_not_redefined():
    src = (BASE / "run_s5_post9.py").read_text(encoding="utf-8")
    for fn in ("s5_label", "final_label", "ctrl_rate", "pit_row", "control_top1", "loss_rate"):
        assert f"def {fn}(" not in src, fn
    assert S9.LABELS is S8.LABELS and S9.AMBIG == S8.AMBIG


def test_p2_post8_and_post7_scripts_untouched():
    for f in ("run_s5_post8.py", "run_s5_post7.py", "RESULTS_S5_POST8.md", "RESULTS_S5_POST8_NUMBERS.md",
              "test_post8_s5.py", "FREEZE_S5_2026-09-16.md", "PREREG_S5_FUND_NEWS_OOS.md"):
        assert git("diff", "--quiet", BASE_REF, "--", f).returncode == 0, f
    assert git("cat-file", "-e", f"{BASE_REF}:./{S9.OUT_NAME}").returncode != 0, "대칭 — 기준 ref 에 post9 산출물 없음"


def test_p2_script_writes_only_its_numbers_and_stamp():
    src = (BASE / "run_s5_post9.py").read_text(encoding="utf-8")
    assert re.findall(r'BASE / (\w+)\)\.write_bytes', src) == ["OUT_NAME"]
    assert src.count(".write_text(") == 1 and 'p = d / "read_stamp.json"' in src


# ── P3 가드가 문다 ─────────────────────────────────────────────────────────────
def test_p3_duties_guard_bites_on_wrong_reading_word():
    ok = list(S9.REQUIRED_MARKERS)
    assert S9.assert_duties(ok)
    bad = [m.replace("답 = 판정", "답 = 표본") for m in ok]
    with pytest.raises(AssertionError):
        S9.assert_duties(bad)
    with pytest.raises(AssertionError):
        S9.assert_duties([m for m in ok if m != "`P9-수집증거`"])


def test_p3_evidence_real_repo_ok_and_bites_without_archive(tmp_path, monkeypatch):
    ev = S9.collect_evidence()
    assert ev["ok"] and ev["pd"][0] == "58833f0" and ev["fz"][0] == "96beddc"
    assert ev["fetch"] == "2026-09-23 23:57:58" and ev["pub"] == "2026-09-23 19:54:26"
    assert any("**빈 결과**" in r[2] for r in ev["rows"]), "원문 추가 커밋 명령은 빈 결과(위반 아님)로 인쇄"
    monkeypatch.setattr(S9, "ARCHIVE", tmp_path)          # 대칭 — 보관본이 없으면 ②·③ 이 문다
    ev2 = S9.collect_evidence()
    assert not ev2["ok"] and "② md5 3줄 부재/불일치" in ev2["reasons"]


# ── P4 산출물 구조 · 판정값 스냅샷 ─────────────────────────────────────────────
@pytest.mark.skipif(not NUMBERS.exists(), reason="산출물 아직 없음")
def test_p4_numbers_snapshot_and_duties():
    L = NUMBERS.read_text(encoding="utf-8").splitlines()
    body = "\n".join(L)
    assert L[0] == "# RESULTS_S5_POST9_NUMBERS — 기계 생성 (수정 금지)"
    assert S9.assert_duties(L) and S8.assert_labels_only_in_verdict(L) and S8.assert_no_grade_names(L)
    assert "- ⇒ **최종: (S5-성립)**" in body
    rows = [ln for ln in L if re.match(r"^\| \((가|나|다|라)\) ", ln)]
    assert len(rows) == 4 and all(ln.endswith("| 예 | **(S5-성립)** |") for ln in rows)
    assert "**선정 건 영업적자 비율 = 2/5 = 40.0%**" in body and "57/126 = 45.2%" in body
    assert "- `P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(" in body
    assert "🟢 **기계 검사(§5 (나)3) 통과**" in body and "순서 증거 미비** —" not in body
    assert "| post8(재계산) | 4 · 3 | 2/3 = 66.7% | 49/97 = 50.5% | +16.2%p |" in body, "post8 인쇄값 재현(회귀)"
    st = json.loads(STAMP.read_text(encoding="utf-8"))
    m = re.search(r"^\| 🔴 D-9 ① 쿼리 실행 시각\(KST\) \| \*\*(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\*\*", body, re.M)
    assert m and m.group(1) == st["first_read_kst"] and st["timezone"] == "Asia/Seoul"


@pytest.mark.skipif(not (db_ok() and NUMBERS.exists() and STAMP.exists()), reason="DB 없음 또는 산출물 없음")
def test_p4_rerun_byte_identical_when_same_fingerprint(tmp_path):
    import psycopg2
    from run_tests import DSN
    conn = psycopg2.connect(**DSN)
    try:
        _f, _n, _r, fp = S9.read_stamp(conn.cursor(), [d for *_x, d in S9.EXACT5] + [d for *_x, d in S8.EXACT4],
                                       base=tmp_path)
    finally:
        conn.close()
    if fp != json.loads(STAMP.read_text(encoding="utf-8"))["fingerprint"]:
        pytest.skip("DB 지문 이동(다음 sweep) — byte 재현은 같은 스냅샷 안에서만 성립")
    before = hashlib.md5(NUMBERS.read_bytes()).hexdigest(), hashlib.md5(STAMP.read_bytes()).hexdigest()
    r = subprocess.run([sys.executable, "-X", "utf8", "run_s5_post9.py"], cwd=str(BASE),
                       capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    after = hashlib.md5(NUMBERS.read_bytes()).hexdigest(), hashlib.md5(STAMP.read_bytes()).hexdigest()
    assert before == after
