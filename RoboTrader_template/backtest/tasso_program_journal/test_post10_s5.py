# -*- coding: utf-8 -*-
"""`run_s5_post10.py` 가드 시험 — post9 판(`test_post9_s5.py`) 구조 승계 · 🆕 `P10-S5기호` · 재진입 갈래 «갈림» 가드.

🔑 단독 단언은 판별력이 없다 → 대칭 단언 · 가드를 시험하지 않으면 그것도 장식이다.
🔴 재실행 byte 시험은 **같은 DB 지문**일 때만 돈다(지문이 움직이면 skip — 산출물을 덮어쓰지 않는다).
🔴 옛 회차 시험·러너는 실행하지 않는다.

실행: `python -m pytest test_post10_s5.py -q -p no:cacheprovider`
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
import run_s5_post10 as S10

BASE = Path(__file__).resolve().parent
NUMBERS = BASE / S10.OUT_NAME
STAMP = BASE / S10.STAMP_DIR / "read_stamp.json"
BASE_REF = "8e014ca"   # 원장·post10 레인 산출 «이전» 커밋


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
    assert S10.POST_LOG == "224429747319" and S10.POST_DATE == S10.DB_UPTO == S10.PIT_CUTOFF == "2026-10-02"
    assert S10.MIN_JUDGEABLE == 3 and S10.BAND_PP == 10 and S10.APPROX == [] and len(S10.EXACT9) == 9
    assert S10.REENTRY == {"범한퓨얼셀", "서산", "한켐", "우리로"} and S10.SANDS == "샌즈랩"
    assert [n for n, _c, _d in S10.EXACT9 if n in S10.REENTRY].__len__() == 4
    intake = (BASE / "INTAKE_2026-10-04_post10.md").read_text(encoding="utf-8")
    for nm, code, _d in S10.EXACT9:
        assert re.search(rf"\| {nm} \| \**{code}\**", intake), nm
    for nm, code in S10.FOLLOWUP3:
        assert re.search(rf"\| {nm} \| {code} \|", intake), nm
    assert S10.EXACT9 != S9.EXACT5                                    # 대칭 — 표본이 post9 에서 바뀌었다


def test_p1_live_ban_is_prereg_post10_line56_verbatim():
    line56 = (BASE / "PREREG_POST10.md").read_text(encoding="utf-8").splitlines()[55]
    assert line56 == "> " + S10.LIVE_BAN


def test_p1_ledger_guard_passes_and_bites():
    rows = S10.ledger_rows()
    assert len(rows) == 12 and S10.assert_ledger_matches(rows)
    bad = [dict(r) for r in rows]
    bad[2]["reg_date"] = "2026-09-05"
    with pytest.raises(AssertionError):
        S10.assert_ledger_matches(bad)
    bad2 = [dict(r) for r in rows]
    bad2[0]["prog_ver"] = "1.0.42"
    with pytest.raises(AssertionError):
        S10.assert_ledger_matches(bad2)


# ── P2 판정 로직 = post8 객체 그대로(새로 쓰기 0) ────────────────────────────
def test_p2_verdict_logic_is_imported_not_redefined():
    src = (BASE / "run_s5_post10.py").read_text(encoding="utf-8")
    for fn in ("s5_label", "final_label", "ctrl_rate", "pit_row", "control_top1", "loss_rate"):
        assert f"def {fn}(" not in src, fn
    assert S10.LABELS is S8.LABELS and S10.AMBIG == S8.AMBIG
    assert re.findall(r"^def (\w+)", src, re.M)[-3:] == ["assert_symbol", "assert_no_grade_names10", "main"]


def test_p2_prior_scripts_untouched():
    for f in ("run_s5_post7.py", "run_s5_post8.py", "run_s5_post9.py", "RESULTS_S5_POST9.md", "RESULTS_S5_POST9_NUMBERS.md",
              "test_post9_s5.py", "FREEZE_S5_2026-09-16.md", "PREREG_S5_FUND_NEWS_OOS.md"):
        assert git("diff", "--quiet", BASE_REF, "--", f).returncode == 0, f
    assert git("cat-file", "-e", f"{BASE_REF}:./{S10.OUT_NAME}").returncode != 0, "대칭 — 기준 ref 에 post10 산출물 없음"


def test_p2_script_writes_only_its_numbers_and_stamp():
    src = (BASE / "run_s5_post10.py").read_text(encoding="utf-8")
    assert re.findall(r'BASE / (\w+)\)\.write_bytes', src) == ["OUT_NAME"]
    assert src.count(".write_text(") == 1 and 'p = d / "read_stamp.json"' in src
    assert not re.search(r'"git",\s*"(add|commit|stash|checkout|reset)', src) and 'git("diff", "--quiet"' in src


# ── P3 가드가 문다 ─────────────────────────────────────────────────────────────
def test_p3_duties_guard_bites_on_wrong_reading_word():
    ok = list(S10.REQUIRED_MARKERS)
    assert S10.assert_duties(ok)
    bad = [m.replace("답 = 판정", "답 = 표본") for m in ok]
    with pytest.raises(AssertionError):
        S10.assert_duties(bad)
    with pytest.raises(AssertionError):
        S10.assert_duties([m for m in ok if m != "`P10-S5기호`"])
    with pytest.raises(AssertionError):
        S10.assert_duties([m for m in ok if m != "`P10-기업행위봉`: 기업행위 건 "])


def test_p3_evidence_real_repo_ok_and_bites_without_archive(tmp_path, monkeypatch):
    ev = S10.collect_evidence()
    assert ev["ok"] and ev["pd"][0] == "723779e" and ev["fz"][0] == "96beddc"
    assert ev["fetch"] == "2026-10-04 09:13:03" and ev["pub"] == "2026-10-02 20:49:47"
    assert any("**빈 결과**" in r[2] for r in ev["rows"]), "원문 추가 커밋 명령은 빈 결과(위반 아님)로 인쇄"
    monkeypatch.setattr(S10, "ARCHIVE", tmp_path)          # 대칭 — 보관본이 없으면 ②·③ 이 문다
    ev2 = S10.collect_evidence()
    assert not ev2["ok"] and "② md5 3줄 부재/불일치" in ev2["reasons"]


def test_p3_symbol_guard_bites():
    """`P10-S5기호` 기계 검사 — 판정 칸 선두 기호가 라벨과 맞아야 한다 · 미개방 = 기호 없음."""
    good = ["- ⇒ **최종: ✅ (S5-성립)**", "x"]
    assert S10.assert_symbol(good)
    assert S10.assert_symbol(["- ⇒ **최종: ❌ (S5-이탈)**"])
    assert S10.assert_symbol(["- ⇒ **최종: ⛔ 판정 불가(갈림)** — 주 갈래 답 (S5-성립)"])
    assert S10.assert_symbol(["- ⇒ **최종: 판정 미개방 — 순서 증거 미비 · 기록: exact (S5-성립)**"])
    for bad in (["- ⇒ **최종: (S5-성립)**"],                          # 기호 없음
                ["- ⇒ **최종: ❌ (S5-성립)**"],                         # 라벨 ↔ 기호 어긋남
                ["- ⇒ **최종: ✅ (S5-이탈)**"],
                ["- ⇒ **최종: ⛔ 판정 미개방**"],                       # 미개방에 기호
                ["x"],                                                # 판정 칸 없음
                good + good):                                          # 판정 칸 둘
        with pytest.raises(AssertionError):
            S10.assert_symbol(bad)


def test_p3_grade_name_guard_allows_only_the_verbatim_footnote():
    assert S10.assert_no_grade_names10(["- 2′번 — *「" + S10.FOOT_OUT + "」*"])      # 축자 단서 1곳만 허용
    with pytest.raises(AssertionError):
        S10.assert_no_grade_names10(["- ⇒ 등급 GT-E 로 읽는다"])                      # 대칭 — 그 밖의 GT 코드는 문다
    with pytest.raises(AssertionError):
        S10.assert_no_grade_names10(["- 2′번 — *「" + S10.FOOT_OUT + "」*", "조건 미달"])
    assert "(S5-성립)의 성립은 «±10%p 안에서 같다»" in S10.FOOT_OK and "GT-E" in S10.FOOT_OUT and "GT-" not in S10.FOOT_OK


def test_p3_split_rule_uses_min_n_and_label_difference():
    """재진입 제외 갈래의 「갈림」 — 판정 가능 ≥ 3 ∧ 답 상이 일 때만(최소 n 미달은 인쇄만)."""
    import inspect
    src = inspect.getsource(S10.main)
    assert "re_counts = re_r[\"s_ok\"] >= MIN_JUDGEABLE" in src and "re_split = re_counts and re_r[\"fin\"] != fin" in src
    assert S10.SYMBOL[S10.LABEL_OK] == "✅" and S10.SYMBOL[S10.LABEL_OUT] == "❌" and S10.SYMBOL[S10.LABEL_HOLD] == "⛔"
    assert S10.SYMBOL[S10.AMBIG] == "⛔" and S10.SPLIT_WORD == "판정 불가(갈림)"


# ── P4 산출물 구조 · 판정값 스냅샷 ─────────────────────────────────────────────
@pytest.mark.skipif(not NUMBERS.exists(), reason="산출물 아직 없음")
def test_p4_numbers_snapshot_and_duties():
    L = NUMBERS.read_text(encoding="utf-8").splitlines()
    body = "\n".join(L)
    assert L[0] == "# RESULTS_S5_POST10_NUMBERS — 기계 생성 (수정 금지)"
    assert S10.assert_duties(L) and S8.assert_labels_only_in_verdict(L) and S10.assert_no_grade_names10(L) and S10.assert_symbol(L)
    assert "**선정 건 영업적자 비율 = 5/9 = 55.6%**" in body and "114/236 = 48.3%" in body
    rows = [ln for ln in L if re.match(r"^\| \((가|나|다|라)\) ", ln)]
    assert len(rows) == 4 and all(ln.endswith("| 예 | **(S5-성립)** |") for ln in rows)
    assert "| 주 갈래 — 신규 ∧ `exact` | 9 · 9 | **(S5-성립)** |" in body
    assert "| §1-5 재진입 포함 ↔ 제외(🔴 항등 아님) | 9 ↔ 5 · 판정 가능 9 ↔ 5 | **(S5-성립)** ↔ **(S5-이탈)** — 🔴 **갈렸다**" in body
    assert "- ⇒ **최종: ⛔ 판정 불가(갈림)**" in body and "순서 증거 미비** —" not in body
    assert "🟢 **기계 검사(§5 (나)3) 통과**" in body
    assert "- 2번 — *「" + S10.FOOT_OK in body and "- 2′번 — *「" + S10.FOOT_OUT in body      # 단서 각주 축자
    assert "- 🔴 `P10-기업행위봉`: 기업행위 건 0/9" in body and "답(참고) · 세지 않는다" in body
    assert "| post8(재계산) | 4 · 3 | 2/3 = 66.7% | 49/97 = 50.5% | +16.2%p |" in body, "post8 인쇄값 재현(회귀)"
    assert "| post9(재계산) | 5 · 5 | 2/5 = 40.0% | 57/126 = 45.2% | -5.2%p |" in body, "post9 인쇄값 재현(회귀)"
    assert "- ⇒ **최종: ✅" not in body                                  # 대칭 — 갈림이라 성립 기호가 선두에 오지 않는다
    st = json.loads(STAMP.read_text(encoding="utf-8"))
    m = re.search(r"^\| 🔴 D-9 ① 쿼리 실행 시각\(KST\) \| \*\*(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\*\*", body, re.M)
    assert m and m.group(1) == st["first_read_kst"] and st["timezone"] == "Asia/Seoul"
    assert set(st) == {"fingerprint", "first_read_kst", "timezone"}


@pytest.mark.skipif(not (db_ok() and NUMBERS.exists() and STAMP.exists()), reason="DB 없음 또는 산출물 없음")
def test_p4_rerun_byte_identical_when_same_fingerprint(tmp_path):
    import psycopg2
    from run_tests import DSN
    conn = psycopg2.connect(**DSN)
    try:
        _f, _n, _r, fp = S10.read_stamp(conn.cursor(), [d for *_x, d in S10.EXACT9] + [d for *_x, d in S9.EXACT5]
                                        + [d for *_x, d in S8.EXACT4], base=tmp_path)
    finally:
        conn.close()
    if fp != json.loads(STAMP.read_text(encoding="utf-8"))["fingerprint"]:
        pytest.skip("DB 지문 이동(다음 sweep) — byte 재현은 같은 스냅샷 안에서만 성립")
    before = hashlib.md5(NUMBERS.read_bytes()).hexdigest(), hashlib.md5(STAMP.read_bytes()).hexdigest()
    r = subprocess.run([sys.executable, "-X", "utf8", "run_s5_post10.py"], cwd=str(BASE),
                       capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    after = hashlib.md5(NUMBERS.read_bytes()).hexdigest(), hashlib.md5(STAMP.read_bytes()).hexdigest()
    assert before == after
