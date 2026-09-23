# -*- coding: utf-8 -*-
"""`run_anchor_redesign.py --mode post8` 가드 시험 + **post7 경로 불변** 시험.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* · *가드를 시험하지 않으면 그것도 장식이다*.
🔴 원본·동결 산출물은 고치지 않는다. post7 byte 불변 시험은 **임시 디렉터리 사본**에서만 돈다
   (`RESULTS_ANCHOR_POST7*.md` 재생성 금지 — 작업트리의 그 두 파일은 건드리지 않는다).

실행: `python -m pytest test_post8_anchor.py -q -p no:cacheprovider`
"""
from __future__ import annotations

import ast
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import run_anchor_redesign as ANC
import run_ladder_tranche as LAD

BASE = Path(__file__).resolve().parent
REL = "RoboTrader_template/backtest/tasso_program_journal/run_anchor_redesign.py"
NUM8 = BASE / "RESULTS_ANCHOR_POST8_NUMBERS.md"
DOC8 = BASE / "RESULTS_ANCHOR_POST8.md"


def git(*a):
    return subprocess.run(["git", *a], cwd=str(BASE), capture_output=True, text=True, encoding="utf-8")


def head_src():
    r = git("show", "HEAD:" + REL)
    assert r.returncode == 0, r.stderr
    return r.stdout


def fn_md5(src):
    t = ast.parse(src)
    return {n.name: hashlib.md5(ast.get_source_segment(src, n).encode("utf-8")).hexdigest()
            for n in t.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def db_ok():
    try:
        import psycopg2
        from run_tests import DSN
        psycopg2.connect(connect_timeout=5, **DSN).close()
        return True
    except Exception:  # noqa: BLE001
        return False


# ── P1 상수 · 표본 ──────────────────────────────────────────────────────────
def test_p1_post8_constants():
    assert ANC.PUB8 == "2026-09-18" == ANC.POST8_END
    assert ANC.POST8_LOG_NO == "224416253270"
    assert ANC.END == "2026-09-11" and ANC.PUB7 == "2026-09-12", "post7 상수는 불변"
    assert ANC.PAIR_GATE == 40 == LAD.PAIR_THRESHOLD and ANC.MIN_N == 3
    assert ANC.NULL_SEED == 20260815 and ANC.S_ANCHOR == 100
    assert ANC.RETRO8_LAST_POST_DATE == ANC.PUB7


def test_p1_post8_sample_equals_intake():
    got = [(n, c, d, k) for n, c, d, k, *_ in ANC.POST8_EXACT]
    assert got == [("우리로", "046970", "2026-09-11", 1), ("JW신약", "067290", "2026-09-01", 1),
                   ("액스비스", "0011A0", "2026-09-11", 1), ("우리기술", "032820", "2026-09-09", 1)]
    assert [n for n, _c, _d, _k, _f, rein, _p in ANC.POST8_EXACT if rein] == ["우리로"], "🔒 #1-(i′)"
    assert sum(p for *_x, p in ANC.POST8_EXACT) == 0
    assert all(k == 1 for _n, _c, _d, k, *_ in ANC.POST8_EXACT), "exact 4 전부 N=1 ⇒ 그 글 열 0쌍(구성)"
    assert [n for n, _c, n2, _d in ANC.POST8_APPROX] == ["헥토파이낸셜", "코데즈컴바인"]
    items = ANC.post8_items()
    assert len(items) == 4 and all(it["post"] == 8 and it["post_date"] == "2026-09-18" for it in items)
    assert all(it["post_date"] == "2026-09-17" for it in ANC.post8_items(pub="2026-09-17"))


def test_p1_retro8_is_post1_to_7():
    r = ANC.retro8_items()
    from collections import Counter
    dist = Counter(i["post"] for i in r)
    assert [dist.get(k, 0) for k in range(1, 8)] == [0, 2, 3, 6, 7, 10, 6]
    assert 8 not in dist, "post8 건이 소급 열로 새 들어오지 않는다"


# ── P2 🔴 post7 경로 불변 ────────────────────────────────────────────────────
def test_p2_post7_function_bodies_byte_identical_to_head():
    a, b = fn_md5(head_src()), fn_md5((BASE / "run_anchor_redesign.py").read_text(encoding="utf-8"))
    changed = [k for k in a if b.get(k) != a[k]]
    assert not changed, f"post7 경로 함수 본문이 바뀌었다: {changed}"
    assert len(a) == 30


def test_p2_only_the_entry_line_was_replaced():
    r = git("diff", "--numstat", "HEAD", "--", "run_anchor_redesign.py")
    added, deleted, _ = r.stdout.split("\t")
    assert deleted == "1", "지운 줄은 진입점 `sys.exit(main())` 하나뿐이어야 한다"
    minus = [ln for ln in git("diff", "HEAD", "--", "run_anchor_redesign.py").stdout.splitlines()
             if ln.startswith("-") and not ln.startswith("---")]
    assert minus == ["-    sys.exit(main())"]


def test_p2_post7_argparse_unchanged_and_cli_opens_post8():
    import contextlib
    import io
    for fn, argv in ((ANC.main, []), (ANC.cli, []), (ANC.cli, ["--mode", "post9"]),
                     (ANC.main, ["--mode", "post8"])):
        with contextlib.redirect_stderr(io.StringIO()):
            with pytest.raises(SystemExit) as e:
                fn(argv)
        assert e.value.code == 2, (fn.__name__, argv)
    src = (BASE / "run_anchor_redesign.py").read_text(encoding="utf-8")
    assert 'choices=("post7",)' in src and 'choices=("post7", "post8")' in src
    assert "sys.exit(cli())" in src


def test_p2_post7_test_file_still_passes():
    r = subprocess.run([sys.executable, "-X", "utf8", "test_post7_anchor.py"], cwd=str(BASE),
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout[-2000:]
    assert "전건 PASS" in r.stdout


def test_p2_post7_frozen_outputs_untouched_in_worktree():
    for f in ("RESULTS_ANCHOR_POST7.md", "RESULTS_ANCHOR_POST7_NUMBERS.md", "test_post7_anchor.py"):
        assert git("diff", "--quiet", "HEAD", "--", f).returncode == 0, f


@pytest.mark.skipif(not db_ok(), reason="DB 없음")
def test_p2_post7_mode_output_byte_identical_head_vs_new(tmp_path):
    """HEAD 판과 새 판을 «같은 스냅샷»에서 `--mode post7` 로 돌려 두 산출물이 byte 같은가.

    🔴 작업트리의 동결 산출물은 쓰지 않는다 — 사본 디렉터리 두 개에서만 돈다.
    (동결 파일 자체와의 비교는 DB 스냅샷 전진으로 구조적으로 불가 — `max(date)` 줄이 움직인다.)"""
    outs = {}
    for tag, src in (("head", head_src()), ("new", (BASE / "run_anchor_redesign.py").read_text(encoding="utf-8"))):
        d = tmp_path / tag
        d.mkdir()
        for p in BASE.glob("*.py"):
            if p.name.startswith("test_"):
                continue
            shutil.copy2(p, d / p.name)
        for p in BASE.glob("*.csv"):
            shutil.copy2(p, d / p.name)
        (d / "run_anchor_redesign.py").write_bytes(src.encode("utf-8"))
        r = subprocess.run([sys.executable, "-X", "utf8", "run_anchor_redesign.py", "--mode", "post7"],
                           cwd=str(d), capture_output=True, text=True, encoding="utf-8", timeout=900)
        assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
        outs[tag] = {f: (d / f).read_bytes() for f in
                     ("RESULTS_ANCHOR_POST7_NUMBERS.md", "RESULTS_ANCHOR_POST7.md")}
    for f in outs["head"]:
        assert outs["head"][f] == outs["new"][f], f"post7 모드 산출물 {f} 가 byte 달라졌다"


# ── P3 `D-1` · `ANC-P3` 합성 규칙 ────────────────────────────────────────────
def _row(name, post, n, h0, l5, highs):
    v = dict(H0=h0, H1=max(highs), H2=h0, H3=h0, L5=l5)
    return dict(name=name, post=post, N=n, v=v, highs=highs)


def test_p3_same_n_everywhere_means_zero_pairs_and_no_statistic():
    rows = [_row(f"x{i}", 8, 1, 100 + 7 * i, 80, [100 + 7 * i, 90, 95]) for i in range(4)]
    out = ANC.p3_eval8(rows, gate_open=True)
    for c in ANC.CANDIDATES:
        assert out[c]["comp"] == 0 and out[c]["ans"] is None and out[c]["V"] is None
        assert "정의 안 됨" in out[c]["why"]


def test_p3_gate_closed_vs_open_is_symmetric():
    rows = [_row("a", 8, 1, 100, 60, [100, 90, 95, 70]), _row("b", 8, 3, 200, 180, [200, 150, 160]),
            _row("c", 8, 2, 150, 100, [150, 120, 130, 110])]
    closed = ANC.p3_eval8(rows, gate_open=False)
    opened = ANC.p3_eval8(rows, gate_open=True)
    assert any(closed[c]["comp"] for c in ANC.CANDIDATES), "N 이 다르면 쌍이 생긴다(판별력)"
    for c in ANC.CANDIDATES:
        if closed[c]["comp"]:
            assert closed[c]["ans"] is None and "게이트 미달" in closed[c]["why"]
            assert isinstance(opened[c]["ans"], bool) and opened[c]["beat"] is not None


def test_p3_lad_cumulative_parser(tmp_path):
    assert ANC.lad_cumulative_pairs(tmp_path)[0] is None, "파일이 없으면 None(자체 재산출 경로)"
    (tmp_path / ANC.LAD_POST8_NUMBERS).write_text("x\n**누적 비교가능 쌍 = 327**\ny\n", encoding="utf-8")
    v, src = ANC.lad_cumulative_pairs(tmp_path)
    assert v == 327 and "327" in src
    (tmp_path / ANC.LAD_POST8_NUMBERS).write_text("누적 비교가능 쌍 = 327\n", encoding="utf-8")
    assert ANC.lad_cumulative_pairs(tmp_path)[0] is None, "줄 형식이 다르면 잡지 않는다(대칭)"


# ── P4 `ANC-N4` 전수 대조 (post7 교훈) ───────────────────────────────────────
def _ev(p1=None, p2=None, p3=None):
    def blk(x):
        return {c: dict(ans=(x or {}).get(c), raw=None, n=4, ident=False, comp=0, why="")
                for c in ANC.CANDIDATES}
    return {"ANC-P1": blk(p1), "ANC-P2": blk(p2), "ANC-P3": blk(p3)}


def test_p4_branch_diff_checks_all_three_tests_and_all_candidates():
    base = _ev(p1={"A2": False}, p2={"A0": False, "A3": False}, p3={"A3": True})
    assert ANC.branch_diff8(base, base) == ([], [])
    alt = _ev(p1={"A2": True}, p2={"A0": True, "A3": False}, p3={"A3": False})
    flips, mutes = ANC.branch_diff8(base, alt)
    assert "A2×`ANC-P1`(△)" in flips and "A0×`ANC-P2`(△)" in flips and "A3×`ANC-P3`(▽)" in flips, \
        "P1 만 보면 P2·P3 뒤집힘을 놓친다(post7 초판 결함)"
    alt2 = _ev(p1={"A2": None}, p2={"A0": False, "A3": False}, p3={"A3": True})
    flips2, mutes2 = ANC.branch_diff8(base, alt2)
    assert flips2 == [] and mutes2 == ["A2×`ANC-P1`"], "판정↔미판정은 갈림이 아니라 따로 센다"


def test_p4_axis1_is_alive_on_a_trading_day_publication():
    cal = ["2026-09-16", "2026-09-17", "2026-09-18"]
    ident, incl, prev = ANC.publish_bar_identity(cal, pub=ANC.PUB8, end=ANC.POST8_END)
    assert ident is False and incl == "2026-09-18" and prev == "2026-09-17"
    ident7, *_ = ANC.publish_bar_identity(["2026-09-10", "2026-09-11"], pub=ANC.PUB7, end=ANC.END)
    assert ident7 is True, "대칭 — 휴장 발행(post7)이면 항등"


# ── P5 가드가 문다 ─────────────────────────────────────────────────────────────
def test_p5_grade_and_duty_guards_bite():
    ok = list(ANC._DUTY8)
    assert ANC._assert_duties8(ok) and ANC._assert_no_grade8(ok)
    for bad in ("GT-D", "조건 미달", "충족·참고용"):
        with pytest.raises(AssertionError):
            ANC._assert_no_grade8(ok + [bad])
    with pytest.raises(AssertionError):
        ANC._assert_duties8([m for m in ok if m != "D-1 ②"])


# ── P6 산출물 구조 ─────────────────────────────────────────────────────────────
@pytest.mark.skipif(not NUM8.exists(), reason="산출물 아직 없음")
def test_p6_numbers_structure():
    L = NUM8.read_text(encoding="utf-8").splitlines()
    body = "\n".join(L)
    assert L[0] == "# RESULTS_ANCHOR_POST8_NUMBERS — 기계 생성 (수정 금지)"
    assert ANC._assert_duties8(L) and ANC._assert_no_grade8(L)
    # D-1 세 수 — ③ = ②
    import re
    two = re.search(r"\*\*D-1 ②\*\* 누적 비교가능 쌍 \| \*\*(\d+)\*\*", body)
    three = re.search(r"\*\*D-1 ③\*\* 게이트 판정에 쓴 수\(= ②\) \| \*\*(\d+)\*\*", body)
    one = re.search(r"\*\*D-1 ①\*\* 그 글 «단독» 비교가능 쌍 \| \*\*(\d+)\*\*", body)
    assert one and two and three and two.group(1) == three.group(1) and one.group(1) == "0"
    # ANC-N4 전수 표 = 3 판정 × 4 후보 = 12 행
    n4 = [ln for ln in L if re.match(r"^\| `ANC-P[123]` \| A[0-3] \|", ln)]
    assert len(n4) == 12
    for ax in ("- 축 ①:", "- 축 ②:", "- 축 ③:"):
        assert any(ln.startswith(ax) for ln in L), ax
    assert "항등(명시 인쇄)" in body
    # D-9 ⑤ — post8 신규 전건 [D, END] 걸침 줄
    for nm in ("우리로", "JW신약", "액스비스", "우리기술"):
        assert any(ln.startswith(f"- {nm} `[D, END]`: 창 `[") and "혼합 빈티지" in ln for ln in L), nm
    assert sum(1 for ln in L if "`ANC-N4` ① 갈래" in ln and "혼합 빈티지" in ln) == 4
    # 소급 각주가 소급 표마다
    assert body.count("소급 = 탐색 · 채택은 그 글 열로만") >= 8
    # 분 단위 시각이 본문에 없다
    assert not re.search(r"실행일 \*\*2026-\d\d-\d\d \d\d:\d\d", body)


@pytest.mark.skipif(not (NUM8.exists() and DOC8.exists()), reason="산출물 아직 없음")
def test_p6_doc_equals_numbers_except_title():
    a = NUM8.read_text(encoding="utf-8").splitlines()
    b = DOC8.read_text(encoding="utf-8").splitlines()
    assert a[1:] == b[1:] and a[0] != b[0]


def test_p6_script_writes_only_post8_files_in_post8_block():
    src = (BASE / "run_anchor_redesign.py").read_text(encoding="utf-8")
    blk = src.split("# 🆕 `--mode post8` — **순수 덧붙임**", 1)[1]
    import re
    targets = re.findall(r'BASE / "([^"]+)"\)\.write_text', blk)
    assert sorted(targets) == ["RESULTS_ANCHOR_POST8.md", "RESULTS_ANCHOR_POST8_NUMBERS.md"]
    assert not re.search(r'^END = "', blk, re.M), "post7 상수 이름 `END` 를 다시 묶지 않는다"
