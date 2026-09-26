"""연구 ② LLM shadow — 사전등록 §10 테스트(DB·CLI 없음 · 합성 데이터).

실행: (워크트리 루트) python -m pytest RoboTrader_template/tests/test_llm_shadow.py -q
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.concept_axes.candidate_ledger.llm_shadow import cli as C  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import dart_load as DL  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import freeze as FZ  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import inputs as I  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import ledger as LG  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import lock as LK  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import prompt_v1 as P  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import schedule as SC  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import search_arm as SA  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import settings as S  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import state as ST  # noqa: E402

D = date(2026, 9, 23)
D_PREV = date(2026, 9, 22)
T = date(2026, 9, 28)
EXAMPLE_EXE_SHA = "9dbe16dafed59da5cdabbfe11ad0335738c753fad794989b47f9446accd6de3a"   # 예시 값(동결 파일 몫)


def _fences():
    md = S.PREREG_MD.read_text(encoding="utf-8")
    out = {}
    for lab in ("A.1", "A.2", "A.3", "A.5", "A.6"):
        i = md.index("**" + lab + " ")
        a = md.index("```\n", i) + 4
        out[lab] = md[a:md.index("\n```", a)]
    return out


# ── 해시 = 부록 · 명령 ───────────────────────────────────────────────────────────
def test_prompt_hashes_equal_prereg_appendix():
    f = _fences()
    assert P.verify_against_prereg()["prompt_sha256"] == P.PROMPT_SHA256
    want = hashlib.sha256((f["A.1"] + "\n" + f["A.2"] + "\n" + f["A.3"]).encode("utf-8")).hexdigest()
    assert P.PROMPT_SHA256 == want
    want_s = hashlib.sha256("\n".join(f[k] for k in ("A.1", "A.2", "A.3", "A.5", "A.6")).encode("utf-8")).hexdigest()
    assert P.PROMPT_SHA256_SEARCH == want_s
    assert P.compact(P.A3_SCHEMA) == f["A.3"] and len(P.CATALYST_ENUM) == 12


def test_appendix_mismatch_refused(tmp_path):
    md = S.PREREG_MD.read_text(encoding="utf-8").replace("0~10 정수.", "0~9 정수.")
    p = tmp_path / "x.md"
    p.write_text(md, encoding="utf-8")
    with pytest.raises(P.AppendixMismatch):
        P.verify_against_prereg(p)


def test_argv_builders_match_a4_a7():
    assert P.argv_main("EXE", "claude-opus-5-5") == [
        "EXE", "-p", "--model", "claude-opus-5-5", "--effort", "medium", "--safe-mode", "--tools", "",
        "--no-session-persistence", "--output-format", "json", "--json-schema", _fences()["A.3"],
        "--system-prompt", _fences()["A.1"]]
    s = P.argv_search("EXE", "claude-opus-5-5")
    assert s[:9] == ["EXE", "-p", "--model", "claude-opus-5-5", "--effort", "medium", "--safe-mode", "--tools",
                     "WebSearch,WebFetch"]
    # 개정 1(2026-09-26 amendment) — `--allowedTools` 없이는 WebFetch 가 permission_denials 로 막힌다(dry-run 실측).
    assert s[9:11] == ["--allowedTools", "WebSearch,WebFetch"]
    assert s[11:15] == ["--no-session-persistence", "--output-format", "json", "--json-schema"]
    sch = json.loads(s[15])
    assert sch["required"] == ["code", "catalyst_tags", "risk_flags", "score", "rationale", "sources",
                               "excluded_after_D"]
    assert "sources" in sch["properties"] and "items" not in sch["properties"]
    assert s[16] == "--system-prompt" and _fences()["A.5"] in s[17] and P.A1_RULE2_MAIN not in s[17]
    assert P.argv_sha256(P.argv_main("A", "m")) == P.argv_sha256(P.argv_main("B", "m"))   # exe 경로 제외


def test_render_block_follows_a2():
    fields = dict(name="가", code="000010", market="KOSPI", mcap_eok="1", r20="-", stac_yymm="-", sales_growth="-",
                  oi_growth="-", ni_growth="-", roe="-", liab="-", reserve="-", eps="-", d10="2026-09-10",
                  D="2026-09-23", n_dart_all=0, dart_lines="(없음)", d5="2026-09-17", n_press_all=0,
                  press_lines="(없음)")
    b = P.render_block(2, 5, fields)
    assert b.startswith("=== 2/5 가 (000010) · KOSPI") and len(b.split("\n")) == 6
    assert P.block_body(b) == P.block_body(P.renumber(b, 1, 1))
    assert P.render_header("2026-09-23", "2026-09-28", 5, search=True).count("\n") == 0
    assert P.render_user("2026-09-23", "2026-09-28", [b]).split("\n")[1].startswith("아래 1개 종목")


# ── 컷오프 · (A) 새 항목 ─────────────────────────────────────────────────────────
def test_cutoff_boundaries():
    ok_cre = datetime(2026, 9, 28, 8, 29, 59)
    assert I.news_visible(datetime(2026, 9, 23, 23, 59, 59), ok_cre, D, T)
    assert not I.news_visible(datetime(2026, 9, 24, 0, 0, 0), ok_cre, D, T)
    assert not I.news_visible(datetime(2026, 9, 23, 12, 0), datetime(2026, 9, 28, 8, 30, 0), D, T)
    assert I.cutoffs(D, T) == (datetime(2026, 9, 24), datetime(2026, 9, 28, 8, 30))


def test_new_item_trigger():
    U = {"000010", "000020", "000030", "000040", "000050"}
    disc = [("000010", "주요사항보고서(유상증자결정)", D, "B"),           # 포함
            ("000020", "[기재정정]단일판매·공급계약체결", D, "I"),        # 정정 → 제외
            ("000030", "자기주식취득결정", D_PREV, "B"),                   # D′ → 제외
            ("999990", "자기주식취득결정", D, "B")]                        # U 밖
    press = [("000040", datetime(2026, 9, 23, 0, 0), datetime(2026, 9, 23, 1, 0)),     # D′+1 00:00 포함
             ("000050", datetime(2026, 9, 22, 23, 59), datetime(2026, 9, 22, 23, 59)),  # D′ → 제외
             ("000030", datetime(2026, 9, 23, 10, 0), datetime(2026, 9, 28, 8, 30))]    # created 컷 → 제외
    a, d, p = I.new_item_codes(disc, press, D_PREV, D, T, U)
    assert d == {"000010"} and p == {"000040"} and a == {"000010", "000040"}


# ── 조각 · 첫 20일 · 이월 · 성수기 ───────────────────────────────────────────────
def test_slice_and_first_20_days():
    code = "005930"
    k = int(hashlib.sha256(f"20261004:F1:{code}".encode()).hexdigest(), 16) % 20
    assert SC.slice_of("F1", code) == k
    assert any(SC.slice_of("F1", f"{i:06d}") != SC.slice_of("F2", f"{i:06d}") for i in range(10, 30))
    codes = [f"{i:06d}" for i in range(10, 110)]
    for n in (0, 5, 19):
        sch = SC.build_schedule("F1", D, n, codes, set(), set(), {}, {c: 0 for c in codes}, "all")
        got = {c.code for c in sch.cells}
        assert got == {c for c in codes if SC.slice_of("F1", c) <= n}
        assert all(c.trigger == "B" for c in sch.cells)
    late = "999910"
    sch = SC.build_schedule("F1", D, 3, codes + [late], set(), set(), {}, {c: 0 for c in codes}, "all")
    assert late in {c.code for c in sch.cells}                                  # 늦은 편입 = 첫날 (B)
    sch = SC.build_schedule("F3", D, 19, codes, set(), set(), {}, {c: 0 for c in codes}, "A_only")
    assert sch.cells == []


def test_rotation_20_days_and_a_overrides_b():
    codes = ["000010", "000020"]
    sch = SC.build_schedule("F1", D, 30, codes, {"000020"}, set(), {"000010": 11, "000020": 0}, {}, "all")
    assert {c.code: c.trigger for c in sch.cells} == {"000020": "A"}           # 000010 은 19거래일 → 아직
    sch = SC.build_schedule("F1", D, 31, codes, set(), set(), {"000010": 11, "000020": 0}, {}, "all")
    got = {c.code: c.gap_td for c in sch.cells}
    assert got == {"000010": 20, "000020": 31}
    assert [c.code for c in sch.cells] == ["000020", "000010"]                 # 오래 밀린 순


def test_one_day_carry_and_drop():
    codes = [f"{i:06d}" for i in range(10, 20)]
    a1 = set(codes[:5])
    s1 = SC.build_schedule("F1", D, 25, codes, a1, set(), {}, {}, "all", cap=3)
    skipped = {c.code for c in s1.cells if c.planned == S.ST_SKIP}
    assert len([c for c in s1.called]) == 3 and len(skipped) == 2 and s1.peak_day
    s2 = SC.build_schedule("F1", D + timedelta(days=1), 26, codes, {codes[9]}, skipped, {}, {}, "all", cap=1)
    by = {c.code: c for c in s2.cells}
    assert sum(c.planned == "call" for c in s2.cells) == 1
    assert all(by[c].carried for c in skipped)
    assert sorted(c.planned for c in s2.cells if c.code in skipped) == ["call", S.ST_DROP]
    assert by[codes[9]].planned == S.ST_SKIP and not by[codes[9]].carried
    s1b = SC.build_schedule("F1", D, 25, codes, a1, set(), {}, {}, "all", cap=3)
    assert [c.code for c in s1b.called] == [c.code for c in s1.called]           # [87] 재현


def test_peak_day_pauses_b():
    codes = [f"{i:06d}" for i in range(10, 30)]
    sch = SC.build_schedule("F1", D, 40, codes, set(codes[:4]), set(), {}, {}, "all", cap=4)
    assert sch.peak_day and all(c.trigger == "A" for c in sch.cells) and sch.counts["n_sel_b"] == 0
    sch2 = SC.build_schedule("F1", D, 41, codes, set(codes[:2]), set(), {}, {}, "all", cap=4)
    assert not sch2.peak_day and sum(c.trigger == "B" for c in sch2.cells) == 2  # (B) 는 다음 날 다시 due


# ── 상태 기계 ────────────────────────────────────────────────────────────────────
class Recorder:
    """가짜 CLI — 호출마다 stdin 의 코드 목록을 기록. bad = parse_error 로 만들 코드."""

    def __init__(self, bad=(), crash_after=None, overload_first=False, limit=False):
        self.calls, self.bad, self.crash_after = [], set(bad), crash_after
        self.overload_first, self.limit = overload_first, limit

    def __call__(self, argv, stdin, timeout, model, most_output):
        import re
        codes = re.findall(r"^=== \d+/\d+ .*\((\w{6})\) · ", stdin, re.M)
        if self.crash_after is not None and len(self.calls) >= self.crash_after:
            raise RuntimeError("crash")
        self.calls.append(codes)
        if self.overload_first and len(self.calls) == 1:
            return C.interpret(json.dumps({"is_error": True, "api_error_status": 529, "result": "Overloaded"}),
                               "", model, most_output, 1)
        if self.limit:
            return C.interpret(json.dumps({"is_error": True, "result": "Claude usage limit reached"}), "", model,
                               most_output, 1)
        items = [dict(code=c, catalyst_tags=(["없음", "수주"] if c in self.bad else ["없음"]), risk_flags=[],
                      score=5, rationale="t") for c in codes]
        raw = {"is_error": False, "structured_output": {"items": items}, "total_cost_usd": 0.02,
               "duration_ms": 10, "modelUsage": {model: {"outputTokens": 5}}}
        return C.interpret(json.dumps(raw, ensure_ascii=False), "", model, most_output, 10)


def _ctx(store, caller, n_codes=45):
    inp = I.SyntheticInputs(n_codes=n_codes)
    return ST.Ctx(store=store, inputs=inp, family="F1", caller=caller, exe="EXE", code_sha="c", exe_sha256="e",
                  cli_version="v", log=lambda m: None), inp.calendar(D)


def test_resume_idempotent_no_recall():
    store = ST.MemoryStore()
    ctx, cal = _ctx(store, Recorder(), n_codes=60)
    ST.plan_day(ctx, D, cal)
    plan = [r for r in store.select("plan", {"family": "F1", "scan_date": D}) if r["planned"] == "call"]
    assert len({r["batch_id"] for r in plan}) >= 2
    crash = Recorder(crash_after=1)
    ctx.caller = crash
    ST.score_day(ctx, D)
    assert ctx.stop_reason and len(crash.calls) == 1
    rec = Recorder()
    ctx2, _ = _ctx(store, rec, n_codes=60)
    ST.plan_day(ctx2, D, cal)                                           # 멱등(이미 있음)
    ST.score_day(ctx2, D)
    primary = [c for call in crash.calls + rec.calls[:-1] for c in call]
    assert sorted(primary) == sorted(r["stock_code"] for r in plan)     # 칸마다 1차 1회
    assert len(rec.calls[-1]) == min(20, -(-len(plan) * 5 // 100))     # 마지막 = 반복
    rec3 = Recorder()
    ctx3, _ = _ctx(store, rec3, n_codes=60)
    ST.score_day(ctx3, D)
    assert rec3.calls == []                                             # 더 부를 칸 없음
    assert len(store.select("rep", {"family": "F1"})) == len(rec.calls[-1])


def test_non_ok_does_not_reset_rotation():
    store = ST.MemoryStore()
    probe, cal = _ctx(store, Recorder())
    ST.plan_day(probe, D, cal)
    called = [r["stock_code"] for r in store.select("plan", {"family": "F1"}) if r["planned"] == "call"]
    bad = called[0]
    rec = Recorder(bad=[bad])
    probe.caller = rec
    ST.score_day(probe, D)
    st = {r["stock_code"]: r["status"] for r in store.select("shadow", {"family": "F1", "scan_date": D})}
    assert st[bad] == S.ST_PARSE and all(v == S.ST_OK for c, v in st.items() if c != bad)
    assert any(bad in call and len(call) == 1 for call in rec.calls)    # 재시도 묶음 1회
    _, _, last = ST.family_history(probe, cal)
    assert bad not in last and all(c in last for c in called if c != bad)


def test_overload_retry_and_limit_stop():
    store = ST.MemoryStore()
    ctx, cal = _ctx(store, Recorder(overload_first=True))
    slept = []
    ctx.sleep = slept.append
    ST.plan_day(ctx, D, cal)
    ST.score_day(ctx, D)
    kinds = sorted(b["kind"] for b in store.select("batch", {"family": "F1"}))
    assert slept[0] == 180 and "overload_retry" in kinds and kinds.count("primary") >= 1
    store2 = ST.MemoryStore()
    ctx2, cal2 = _ctx(store2, Recorder(limit=True), n_codes=60)
    ST.plan_day(ctx2, D, cal2)
    ST.score_day(ctx2, D)
    sts = {r["status"] for r in store2.select("shadow", {"family": "F1"})}
    assert ctx2.stop_reason == "limit_error" and S.ST_LIMIT in sts


def test_batching_and_seeds_reproducible():
    codes = [f"{i:06d}" for i in range(1000, 1360)]
    b1, b2 = ST.make_batches(codes, D, "F1"), ST.make_batches(codes, D, "F1")
    assert b1 == b2 and len(b1) == 18 and all(len(cs) == 20 for _, cs in b1)
    assert ST.make_batches(codes, D + timedelta(days=1), "F1") != b1
    assert b1[0][0] == "F1:2026-09-23:p01"
    assert len(ST.repeat_pick(codes[:100], D)) == 5 and len(ST.repeat_pick(codes, D)) == 18
    assert len(ST.repeat_pick(codes * 3 + [f"{i:06d}" for i in range(2000, 2100)], D)) == 20
    assert ST.repeat_pick([], D) == [] and ST.retry_order(codes, D) == ST.retry_order(codes, D)
    assert len(ST.retry_order(codes, D)) == 20


# ── 사후 검사 · 한도 · 429/529 ───────────────────────────────────────────────────
def _it(code, tags=("없음",), risk=(), score=5):
    return dict(code=code, catalyst_tags=list(tags), risk_flags=list(risk), score=score, rationale="r")


def test_post_checks():
    ok, err = C.validate_batch({"items": [_it("000010"), _it("000020", ("수주", "신사업"), ("소송",), 7)]},
                               ["000010", "000020"])
    assert err is None and all(v[0] == S.ST_OK for v in ok.values())
    per, err = C.validate_batch({"items": [_it("000010")]}, ["000010", "000020"])
    assert err == "code 집합 불일치" and all(v[0] == S.ST_PARSE for v in per.values())
    per, err = C.validate_batch({"items": [_it("000010"), _it("000010")]}, ["000010"])
    assert err == "code 중복"
    per, err = C.validate_batch({"items": [_it("000010", ("없음", "수주")), _it("000020")]}, ["000010", "000020"])
    assert per["000010"][0] == S.ST_PARSE and per["000020"][0] == S.ST_OK
    for bad in (_it("000010", score=11), _it("000010", ("모름",)), _it("000010", risk=("소송", "소송")),
                dict(_it("000010"), extra=1), _it("000010", score=True)):
        assert C.validate_batch({"items": [bad]}, ["000010"])[0]["000010"][0] == S.ST_PARSE
    assert C.validate_batch(None, ["000010"])[1]


def test_limit_regex_and_overload_path():
    for s in ("Claude usage limit reached", "Rate limited", "quota exceeded", "Too Many Requests", "limit reached"):
        assert C.LIMIT_RE.search(s)
    assert not C.LIMIT_RE.search("unlimited reached") and not C.LIMIT_RE.search("ratelimit")
    r = C.interpret(json.dumps({"is_error": True, "result": "5-hour usage limit reached"}), "", "m", False, 1)
    assert r.status == S.ST_LIMIT
    r = C.interpret(json.dumps({"is_error": True, "api_error_status": 429, "result": "x"}), "", "m", False, 1)
    assert r.status == C.ST_OVERLOAD
    r = C.interpret(json.dumps({"is_error": False, "modelUsage": {"claude-sonnet-5": {}}}), "", "claude-opus-5-5",
                    False, 1)
    assert r.status == S.ST_MODEL
    seq = iter([C.CallResult(C.ST_OVERLOAD), C.CallResult(S.ST_OK)])
    slept = []
    first, second = C.call_with_overload_retry(lambda: next(seq), slept.append)
    assert slept == [180] and first.status == C.ST_OVERLOAD and second.status == S.ST_OK
    mu = {"claude-haiku-5": {"outputTokens": 3}, "claude-opus-5-5": {"outputTokens": 90}}
    assert C.pick_model(mu, False)[0] is None                            # 본체 = 유일 키 규칙(둘 이상 → None)


def test_search_model_check_rule_and_web_search_sum():
    """개정 2·3(2026-09-26 amendment) — 가족 키 존재 + 보조 키 전부 webSearchRequests≥1 · 증거는 modelUsage 합."""
    fam = "claude-opus-5-5"
    mu_ok = {fam: {"inputTokens": 6, "outputTokens": 628, "webSearchRequests": 0},
             "claude-haiku-4-5-20251001": {"inputTokens": 26758, "outputTokens": 931, "webSearchRequests": 2}}
    assert C.pick_model(mu_ok, True, fam) == (fam, sorted(mu_ok))
    r = C.interpret(json.dumps({"is_error": False, "structured_output": {}, "modelUsage": mu_ok}), "", fam, True, 1)
    assert r.status == S.ST_OK and r.model == fam and r.web_search_requests == 2
    assert r.helper_models == "claude-haiku-4-5-20251001"

    mu_zero = {fam: {"outputTokens": 628}, "claude-haiku-4-5-20251001": {"outputTokens": 931, "webSearchRequests": 0}}
    assert C.pick_model(mu_zero, True, fam)[0] is None
    r2 = C.interpret(json.dumps({"is_error": False, "structured_output": {}, "modelUsage": mu_zero}), "", fam, True, 1)
    assert r2.status == S.ST_MODEL

    mu_no_fam = {"claude-haiku-4-5-20251001": {"outputTokens": 931, "webSearchRequests": 2}}
    assert C.pick_model(mu_no_fam, True, fam)[0] is None
    r3 = C.interpret(json.dumps({"is_error": False, "structured_output": {}, "modelUsage": mu_no_fam}), "", fam,
                     True, 1)
    assert r3.status == S.ST_MODEL

    # modelUsage 없으면 top-level usage.server_tool_use.web_search_requests 로 폴백.
    r4 = C.interpret(json.dumps({"is_error": False, "structured_output": {},
                                "usage": {"server_tool_use": {"web_search_requests": 5}}}), "", fam, True, 1)
    assert r4.web_search_requests == 5


# ── 잠금 · 가드 ──────────────────────────────────────────────────────────────────
def test_stale_lock_auto_release(tmp_path):
    p = tmp_path / "runner.lock"
    p.write_text("pid=999999 owner=dead created_at=2026-01-01T00:00:00\n", encoding="utf-8")
    lk = LK.RunnerLock(p, owner="t").acquire()
    assert lk.stale_from.startswith("pid=999999") and f"pid={os.getpid()}" in p.read_text(encoding="utf-8")
    with pytest.raises(LK.LockBusy):
        LK.RunnerLock(p, owner="second").acquire()
    lk.release()
    LK.RunnerLock(p, owner="again").acquire().release()


def test_api_key_guard_and_oauth_exception():
    base = {"PATH": "x", "CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli", "CLAUDE_CODE_OAUTH_TOKEN": "tok"}
    env = C.build_env(base)
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "tok" and env["DISABLE_AUTOUPDATER"] == "1"
    assert "CLAUDECODE" not in env and "CLAUDE_CODE_ENTRYPOINT" not in env and env["PATH"] == "x"
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        with pytest.raises(C.ApiKeyPresent):
            C.build_env(dict(base, **{k: "sk"}))


def _frozen(**kw):
    d = dict(code_sha="0" * 40, exe_sha256=EXAMPLE_EXE_SHA, cli_version="2.1.283", prompt_sha256=P.PROMPT_SHA256,
             prompt_sha256_search=P.PROMPT_SHA256_SEARCH, batch_timeout_s=180, frozen_at="t")
    d.update(kw)
    return FZ.Frozen(**d)


def test_exe_hash_refusal(tmp_path):
    exe = tmp_path / "claude.exe"
    exe.write_bytes(b"fake-binary")
    with pytest.raises(FZ.GuardError):
        FZ.check_exe(_frozen(), exe)
    assert FZ.check_exe(_frozen(exe_sha256=FZ.file_sha256(exe)), exe) == FZ.file_sha256(exe)


def test_live_tree_refused():
    with pytest.raises(FZ.GuardError):
        FZ.refuse_live_tree(Path("D:/GIT/kis-trading-template/RoboTrader_template/scripts/x.py"))
    FZ.refuse_live_tree(Path("D:/tmp/kis-wt-llm/RoboTrader_template"))


@pytest.mark.skipif(shutil.which("git") is None, reason="git 없음")
def test_dirty_worktree_and_head_refusal(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    g = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(g + ["init", "-q"], cwd=repo, check=True)
    (repo / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run(g + ["add", "a.txt"], cwd=repo, check=True)
    subprocess.run(g + ["commit", "-qm", "c"], cwd=repo, check=True)
    exe, pkg = tmp_path / "claude.exe", tmp_path / "package.json"
    exe.write_bytes(b"x")
    pkg.write_text(json.dumps({"version": "2.1.283"}), encoding="utf-8")
    fr = _frozen(code_sha=FZ.git_head(repo), exe_sha256=FZ.file_sha256(exe))
    assert FZ.check_runtime(repo, fr, exe, pkg)["cli_version"] == "2.1.283"
    with pytest.raises(FZ.GuardError):
        FZ.check_runtime(repo, _frozen(code_sha="f" * 40, exe_sha256=fr.exe_sha256), exe, pkg)
    (repo / "dirty.txt").write_text("d", encoding="utf-8")
    with pytest.raises(FZ.GuardError, match="깨끗"):
        FZ.check_runtime(repo, fr, exe, pkg)
    with pytest.raises(FZ.GuardError):
        FZ.write_frozen(repo, 180, exe, pkg, tmp_path / "frozen.json")
    os.remove(repo / "dirty.txt")
    pkg.write_text(json.dumps({"version": "2.1.284"}), encoding="utf-8")
    with pytest.raises(FZ.GuardError, match="CLI"):
        FZ.check_runtime(repo, fr, exe, pkg)


# ── 입력 서식 · 재무 PIT · 달력 ─────────────────────────────────────────────────
def test_titles_dedupe_limit_and_format():
    t0 = datetime(2026, 9, 23, 10, 0)
    rows = [(t0 - timedelta(hours=i), i, f"[회사]  제목{i % 14}   끝", "dart") for i in range(20)]
    lines, n = I.select_lines(rows, "dart", 12)
    assert n == 14 and len(lines) == 12 and lines[0] == "- 09-23 제목0 끝"
    pl, n2 = I.select_lines([(t0, 1, "가" * 130, "hankyung")], "press", 8)
    assert pl == ["- 09-23 [hankyung] " + "가" * 120] and n2 == 1
    assert I.select_lines([], "press", 8) == ([], 0)


def test_financial_pit_and_formats():
    assert I.fin_available_on("202606") == date(2026, 8, 29)
    assert I.fin_available_on("202512") == date(2026, 4, 10)
    rows = [{"stac_yymm": "202606"}, {"stac_yymm": "202603"}, {"stac_yymm": "202512"}]
    assert I.pick_financial(rows, date(2026, 8, 28))["stac_yymm"] == "202603"
    assert I.pick_financial(rows, date(2026, 8, 29))["stac_yymm"] == "202606"
    assert I.pick_financial(rows, date(2026, 4, 9)) is None
    assert I.fmt_num(None) == "-" and I.fmt_num(12.5) == "12.5" and I.fmt_num(1234.0) == "1,234"
    win = [date(2026, 8, 1) + timedelta(days=i) for i in range(21)]
    px = {d: (100.0, None) for d in win}
    px[win[-1]] = (110.0, 1.0)
    assert I.r20_text(px, win) == "+10.0%"
    px[win[5]] = (100.0, 0.5)
    assert I.r20_text(px, win) == "N/A"


def test_trading_days_12_31_closed():
    assert not I.is_trading_day(date(2026, 12, 31))
    assert I.next_trading_day(date(2026, 12, 30)) == date(2027, 1, 4)
    assert I.next_trading_day(D) == T                                  # 추석 9/24·25 휴장


# ── 검색 팔 ─────────────────────────────────────────────────────────────────────
def test_search_sample_k_rule():
    assert [SA.sample_k(n) for n in (0, 3, 50, 99, 250, 265, 400)] == [0, 3, 5, 5, 12, 13, 15]
    codes = [f"{i:06d}" for i in range(10, 275)]
    s1 = SA.sample_codes(codes, D)
    assert s1 == SA.sample_codes(list(reversed(codes)), D) and len(s1) == 13 and len(set(s1)) == 13


P1 = "가나다라마바사아자차카타파하 신제품 출시"
P2 = "다른 종목 기사 제목입니다 열다섯자 이상"


def test_search_normalization_and_matching():
    assert SA.normalize_title(" [속보][단독] 삼성전자ㆍ“HBM” 공급, 계약! ") == "삼성전자·hbm공급계약"
    assert SA.normalize_title("ＡＢＣ (주)") == "abc주"
    lk = SA.Lookup(rcp_stocks={"20260923000123": {"000010"}},
                   disc_by_stock={"000010": [(date(2026, 9, 22), SA.normalize_title("자기주식취득결정"))]},
                   press=[(date(2026, 9, 22), SA.normalize_title(P1), {"000010"}),
                          (date(2026, 9, 23), SA.normalize_title(P2), {"000099"})])
    url = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260923000123"
    assert SA.match_disclosure({"url": url, "title": "x", "date": "2026-09-23"}, "000010", lk) == "found"
    assert SA.match_disclosure({"url": url, "title": "x", "date": "2026-09-23"}, "000020", lk) == "unlinked"
    assert SA.match_disclosure({"title": "[회사] 자기주식 취득 결정", "date": "2026-09-23"}, "000010", lk) == "found"
    assert SA.match_disclosure({"title": "자기주식취득결정", "date": "2026-09-25"}, "000010", lk) == "missing"
    assert SA.match_press({"title": P1[:-3], "date": "2026-09-23"}, "000010", lk) == "found"
    assert SA.match_press({"title": "가나다라", "date": "2026-09-23"}, "000010", lk) == "missing"   # 15자 미만
    assert SA.match_press({"title": P2, "date": "2026-09-22"}, "000010",
                          lk) == "unlinked"
    out = {"code": "000010", "excluded_after_D": [{"title": "t", "date": "2026-09-24"}],
           "sources": [{"title": "t", "source": "DART", "date": "2026-09-23", "url": url},
                       {"title": "없는 기사 제목", "source": "hankyung", "date": "2026-09-23"},
                       {"title": "미래", "source": "mk", "date": "2026-09-24"}]}
    a = SA.aggregate([{"stock_code": "000010", "status": "ok", "output_json": out}], D, lk)
    assert (a["n_sources_le_d"], a["n_disc_sources"], a["n_missing_disc"], a["n_missing_press"],
            a["n_rule_violation"], a["n_excluded_after_d"]) == (2, 1, 0, 1, 1, 1)


def test_search_run_writes_rows_and_deadline(tmp_path):
    store = ST.MemoryStore()

    def caller(argv, stdin, timeout, model, most_output):
        import re
        code = re.findall(r"\((\w{6})\) · ", stdin)[0]
        so = dict(code=code, catalyst_tags=["없음"], risk_flags=[], score=5, rationale="t", sources=[],
                  excluded_after_D=[])
        raw = {"is_error": False, "structured_output": so, "usage": {"server_tool_use": {"web_search_requests": 2}},
               "modelUsage": {"claude-haiku-5": {"outputTokens": 1, "webSearchRequests": 2},
                              model: {"outputTokens": 9}}}
        return C.interpret(json.dumps(raw, ensure_ascii=False), "", model, most_output, 1)
    now = datetime(2026, 9, 28, 8, 31)
    sc = SA.SearchCtx(store=store, caller=caller, exe="EXE", code_sha="c", exe_sha256="e", cli_version="v",
                      timeout_s=180, deadline=datetime(2026, 9, 28, 8, 58), now=lambda: now, log=lambda m: None)
    blk = {c: f"=== 1/1 가 ({c}) · KOSPI · 끝" for c in ("000010", "000020")}
    s = SA.run_search(sc, D, T, ["000020", "000010"], blk, "F1")
    rows = store.select("search", {"family": "S1"})
    assert s["ok"] == 2 and [r["sample_order"] for r in rows] == [2, 1] and rows[0]["prompt_sha256"] == \
        P.PROMPT_SHA256_SEARCH
    late = SA.SearchCtx(store=ST.MemoryStore(), caller=caller, exe="EXE", code_sha="c", exe_sha256="e",
                        cli_version="v", timeout_s=180, deadline=now, now=lambda: now, log=lambda m: None)
    assert SA.run_search(late, D, T, ["000010"], blk, "F1")[SA.ST_NOT_CALLED] == 1


# ── DART 적재 완결 · 원장 ────────────────────────────────────────────────────────
def test_dart_completeness_rules(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    day = date(2026, 9, 28)
    ds = day.strftime("%Y%m%d")
    items = [{"rcept_no": f"r{i}"} for i in range(3)]
    (raw / f"{ds}_B_p1.json").write_text(json.dumps({"status": "000", "total_count": 3, "total_page": 1,
                                                     "list": items}), encoding="utf-8")
    counts = {"rcept_dt": 2, "rcept_no": 1}
    q = lambda sql, params: counts["rcept_dt" if "rcept_dt =" in sql else "rcept_no"]  # noqa: E731
    assert DL.day_complete(q, tmp_path, "B", day)
    counts["rcept_no"] = 0
    assert not DL.day_complete(q, tmp_path, "B", day)
    assert not DL.day_complete(q, tmp_path, "I", day)                   # 증거 없음
    with open(tmp_path / "call_log.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({"url": f"x?bgn_de={ds}&end_de={ds}&pblntf_ty=I", "status": "013",
                            "ts": "2026-09-28T16:10:00"}) + "\n")
    assert DL.day_complete(q, tmp_path, "I", day)
    assert DL.calls_today(tmp_path / "call_log.jsonl", day) == 1
    assert DL.day_complete(q, tmp_path, "B", date(2026, 9, 23))         # ① 완결 판정 구간
    prog = {f"{t}:{d}": {"done": True} for t in ("B", "I") for d in ("20260924", "20260925")}
    prog["B:20260926"] = {"done": True}
    (tmp_path / "progress.json").write_text(json.dumps(prog), encoding="utf-8")
    assert DL.last_loaded_day(tmp_path) == date(2026, 9, 25)


def test_dart_load_budget(tmp_path):
    seen = []
    conn = type("Conn", (), {"cursor": lambda self: None, "commit": lambda self: None})()
    with open(tmp_path / "call_log.jsonl", "w", encoding="utf-8") as f:
        for _ in range(58):
            f.write(json.dumps({"url": "u", "status": "000", "ts": "2026-09-28T08:30:00"}) + "\n")
    DL.CHECK_BACK_DAYS = -1                                              # 완결 판정 건너뜀(DB 없음)
    try:
        r = DL.load_forward(conn, date(2026, 9, 25), date(2026, 9, 28), tmp_path,
                            runner=lambda s, e, b, o: seen.append((s, e, b)))
    finally:
        DL.CHECK_BACK_DAYS = 14
    assert seen == [(date(2026, 9, 24), date(2026, 9, 25), 2)] and r.calls_before == 58


def test_ledger_append_only(tmp_path):
    store = ST.MemoryStore()
    store.insert_many([("batch", [dict(family="F1", scan_date=D, batch_id="b", kind="primary", status="ok")])])
    LG.export_day(store, D, root=tmp_path)
    LG.export_day(store, D, root=tmp_path)
    lines = (tmp_path / "ledger_sha256.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 * len(ST.TABLES)
    b = [ln.split("\t") for ln in lines if "\tbatch\t" in ln]
    assert b[0][2] == "1" and b[0][3] == b[1][3]


def test_runner_dry_run_no_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("KIS_LLM_SHADOW_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location("llm_candidate_shadow", ROOT / "scripts" / "llm_candidate_shadow.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--dry-run", "--no-cli", "--date", "2026-09-28"]) == 0
    assert list((tmp_path / "dryrun").glob("*/2026-09-23/shadow.*.csv"))
    with pytest.raises(SystemExit):
        mod.parse_args(["--no-cli"])


def _ddl_columns():
    import re
    sql = (ROOT / "backtest/concept_axes/candidate_ledger/llm_shadow/ddl.sql").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS llm_shadow\.(\w+) \((.*?)\n\);", sql, re.S):
        cols = set()
        for line in m.group(2).split("\n"):
            line = line.split("--")[0].strip()
            if not line or line.startswith("PRIMARY KEY"):
                continue
            for part in line.split(","):
                w = part.strip().split()
                if w:
                    cols.add(w[0])
        out[m.group(1)] = cols
    return out


def test_row_keys_match_ddl(tmp_path, monkeypatch):
    cols = _ddl_columns()
    assert set(cols) == set(ST.PK)
    store = ST.MemoryStore()
    ctx, cal = _ctx(store, Recorder(bad=[]), n_codes=45)
    ST.plan_day(ctx, D, cal)
    ST.score_day(ctx, D)
    s2, cal2 = _ctx(ST.MemoryStore(), Recorder(limit=True), n_codes=45)
    ST.plan_day(s2, D, cal2)
    ST.score_day(s2, D)
    ST._finalize(ctx, D, [])
    sc = SA.SearchCtx(store=store, caller=Recorder(), exe="EXE", code_sha="c", exe_sha256="e", cli_version="v",
                      timeout_s=180, deadline=datetime.now() + timedelta(minutes=5), log=lambda m: None)
    SA.run_search(sc, D, T, ["000010"], {"000010": "=== 1/1 가 (000010) · 끝"}, "F1")
    SA.write_agg(store, None, D, T, "c")
    for st in (store, s2.store):
        for table, rows in st.t.items():
            for r in rows.values():
                extra = set(r) - cols[table]
                assert not extra, (table, extra)
    for pk_table, pk in ST.PK.items():
        assert set(pk) <= cols[pk_table]
