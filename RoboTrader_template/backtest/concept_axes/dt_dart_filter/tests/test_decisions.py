"""사장님 동결 전 결정 A-1~A-6(2026-10-10 「권고안 전부 적용」) + M5 범위 판정 — 합성 데이터 · DB 없음 · git 은 tmp 레포만.

A-1 「있음(−)」 δ̂ ≤ −0.4 를 두 동시 터치 판 모두에 · A-2 ca_path 대칭 제외 손절 우선 판도 단측 p<α ∧ δ̂ ≤ −0.4 ·
A-3 도구 fail 또는 n₁<100 → 봉인이 최종 판정 기록 · open 거부 · A-4 재봉인 1회(지문 변경 때만 · v1 보존 · 차이표) ·
A-5 정지일 = 거래량≤0 행 ∪ 내부 결측 거래일 · 생존자 gap_interior 분리 · A-6 게이트 하측 거부율 ≤ 0.075 ·
M5 동결 뒤 «.py» 변경만 거부(.md 통과).
"""
import json
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.dt_dart_filter import gate as G
from backtest.concept_axes.dt_dart_filter import lots as L
from backtest.concept_axes.dt_dart_filter import run as RUN
from backtest.concept_axes.dt_dart_filter import settings as S
from backtest.concept_axes.dt_dart_filter import surv as SV
from backtest.concept_axes.dt_dart_filter.stats import FE
from backtest.concept_axes.dt_dart_filter.tests.test_open_e2e import GATE, _commit, _setup
from backtest.concept_axes.dt_dart_filter.tests.test_prefreeze import _repo
from backtest.concept_axes.dt_dart_filter.tests.test_run import _fake_build, _frozen_env, _seal_files
from backtest.concept_axes.ledger8 import exitsim8 as X

NAN = float("nan")


# ── A-1 · A-2 · label ─────────────────────────────────────────────────────────────
def _fe(beta, p1c, p1w=None):
    p1w = p1c if p1w is None else p1w
    return FE(beta, 1.0, 1.0, p1c, 2 * p1c, p1w, 2 * p1w, 500, 120, 300, 200, 40)


SL, TP, EX = _fe(-1.0, 0.01), _fe(-0.9, 0.03), _fe(-0.8, 0.02)


def _lab(sl=SL, tp=TP, ex=EX, tool="cr1", n1=120, si=0.3, sii=0.1):
    return RUN.label(sl, tp, tool, n1, si, sii, ex)


def test_label_a1_delta_threshold_on_both_touch_rules():
    assert _lab() == "있음(−)"
    assert _lab(tp=_fe(-0.3, 0.01)) == "판별 보류"                 # 익절 우선 판 δ̂ > −0.4
    assert _lab(tp=_fe(-0.4, 0.01)) == "있음(−)"                   # 경계 포함
    assert _lab(sl=_fe(-0.39, 0.01)) == "판별 보류"
    assert _lab(tp=_fe(NAN, 0.01)) == "판별 보류"                  # NaN = 닫힌 쪽


def test_label_a2_ca_path_excluded_fit_must_also_pass():
    assert _lab(ex=_fe(-0.8, 0.06)) == "판별 보류"                 # 제외 판 p ≥ α
    assert _lab(ex=_fe(-0.39, 0.01)) == "판별 보류"                # 제외 판 δ̂ > −0.4
    assert _lab(ex=_fe(NAN, NAN)) == "판별 보류"
    two = dict(sl=_fe(-1.0, 0.5, 0.01), tp=_fe(-0.9, 0.5, 0.02), tool="2way")
    assert _lab(ex=_fe(-0.8, 0.01, 0.01), **two) == "있음(−)"
    assert _lab(ex=_fe(-0.8, 0.01, 0.20), **two) == "판별 보류"     # 봉인 도구(2원)의 p 를 쓴다
    rev = FE(1.2, 1.0, 1.0, 0.995, 0.01, 0.995, 0.01, 500, 120, 300, 200, 40)           # δ̂ > 0 · 양측 p 0.01
    assert _lab(sl=rev, tp=rev, ex=_fe(NAN, NAN)) == "역방향"                       # 역방향은 제외 판과 무관
    with pytest.raises(TypeError):
        RUN.label(SL, TP, "cr1", 120, 0.3, 0.1)                     # 제외 판 없이 부르면 안 된다


# ── A-3 · 봉인 최종 판정 ─────────────────────────────────────────────────────────────
def test_sealed_verdict_rules():
    assert RUN.sealed_verdict("fail", 500) == "판정 불가(도구)"
    assert RUN.sealed_verdict("fail", 5) == "판정 불가(도구)"
    assert RUN.sealed_verdict("cr1", S.N1_MIN - 1) == "판별 보류(n₁<100)"
    assert RUN.sealed_verdict("2way", S.N1_MIN) is None and RUN.sealed_verdict("cr1", 400) is None
    assert _lab(tool="fail") == RUN.sealed_verdict("fail", 120)
    assert _lab(n1=99) == RUN.sealed_verdict("cr1", 99)


@pytest.mark.parametrize("tool, n1_min, want", [("fail", None, "판정 불가(도구)"), ("cr1", 10 ** 6, "판별 보류(n₁<100)")])
def test_seal_records_final_verdict_and_open_refuses_without_writing(monkeypatch, tmp_path, tool, n1_min, want):
    gate = dict(GATE, tool=tool, reason="out_of_band" if tool == "fail" else "ok")
    e = _setup(monkeypatch, tmp_path, -4.0, gate=gate)
    if n1_min:
        monkeypatch.setattr(S, "N1_MIN", n1_min)
    RUN.stage_build(None)
    _commit(e.repo, "build")
    RUN.stage_seal(None)
    seal = json.loads((e.res / "seal.json").read_text(encoding="utf-8"))
    assert seal["final_verdict"] == want
    rep = (e.res / "sealed_report.md").read_text(encoding="utf-8")
    assert "최종 판정" in rep and want in rep and "개봉 안 함" in rep
    _commit(e.repo, "seal")
    before = {p.name: p.read_bytes() for p in e.res.iterdir()}
    with pytest.raises(SystemExit, match="최종 판정"):
        RUN.stage_open(None)
    assert {p.name: p.read_bytes() for p in e.res.iterdir()} == before          # 아무것도 안 씀 · open.started 없음
    e.fp = {"sha256": "e" * 64, "per_stock": dict(e.fp["per_stock"])}
    with pytest.raises(SystemExit, match="최종 판정"):
        RUN.stage_reseal(None)                                                 # 최종 판정 뒤 재봉인(도구 쇼핑) 금지
    assert {p.name: p.read_bytes() for p in e.res.iterdir()} == before


def test_open_refuses_seal_with_fail_tool_or_small_n1(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    monkeypatch.setattr(RUN, "committed_unchanged", lambda p: True)
    for gate, n1 in (({"tool": "fail"}, 300), ({"tool": "cr1"}, 99)):
        _seal_files(tmp_path, {"build_md5": _fake_build(tmp_path), "gate": gate, "n1": n1})
        with pytest.raises(SystemExit, match="최종 판정"):
            RUN.stage_open(None)
        assert not (tmp_path / "open.started").exists()


# ── A-4 · 재봉인 1회 ─────────────────────────────────────────────────────────────────
def test_reseal_once_after_db_fingerprint_change_then_open(monkeypatch, tmp_path):
    e = _setup(monkeypatch, tmp_path, -4.0)
    with pytest.raises(SystemExit, match="seal.json"):
        RUN.stage_reseal(None)                                                  # 봉인 전 재봉인 없음
    RUN.stage_build(None)
    _commit(e.repo, "build")
    RUN.stage_seal(None)
    _commit(e.repo, "seal")
    v1_seal, v1_rep = (e.res / "seal.json").read_bytes(), (e.res / "sealed_report.md").read_bytes()
    old_meta = json.loads((e.res / "build_meta.json").read_text(encoding="utf-8"))

    with pytest.raises(SystemExit, match="고칠 것 없음"):
        RUN.stage_reseal(None)                                                  # 지문 같음 → 거부 · 아무것도 안 옮김
    assert (e.res / "seal.json").read_bytes() == v1_seal and not (e.res / "seal_v1.json").exists()

    # 매일 EOD 수집이 한 종목 adj_factor 를 다시 씀(M4) → open 은 open.started 전에 거부
    e.fp = {"sha256": "e" * 64, "per_stock": {**e.fp["per_stock"], "000005": "1" * 32}}
    with pytest.raises(SystemExit, match="지문"):
        RUN.stage_open(None)
    assert not (e.res / "open.started").exists()

    RUN.stage_reseal(None)
    assert (e.res / "seal_v1.json").read_bytes() == v1_seal
    assert (e.res / "sealed_report_v1.md").read_bytes() == v1_rep
    s1, s2 = json.loads(v1_seal), json.loads((e.res / "seal.json").read_text(encoding="utf-8"))
    assert s2["reseal"]["n"] == 1 and s2["reseal"]["v1_seal_md5"] == RUN.md5(e.res / "seal_v1.json")
    assert s2["reseal"]["db_fingerprint_v1"] == old_meta["db_fingerprint"]
    assert s2["reseal"]["db_fingerprint_v2"] == "e" * 64
    assert json.loads((e.res / "build_meta.json").read_text(encoding="utf-8"))["db_fingerprint"] == "e" * 64
    RUN.check_sealed_report(e.res / "sealed_report.md", e.res / "seal.json")
    diff = (e.res / "reseal_diff.md").read_text(encoding="utf-8")
    assert "값이 바뀐 종목 1: 000005" in diff and "새로 생긴 종목 0" in diff and "사라진 종목 0" in diff
    f1, f2 = RUN.flatten_seal(s1), RUN.flatten_seal(s2)
    for k in set(f1) | set(f2):
        assert f"| `{k}` |" in diff, k                                          # 모든 봉인 필드 v1 vs v2
    assert "gate.tool" in f1 and "build_md5.ledger_A.csv" in f1 and "reseal.n" in f2

    with pytest.raises(SystemExit):
        RUN.stage_reseal(None)                                                  # 커밋 전 두 번째 재봉인 거부(더러운 패키지)
    _commit(e.repo, "reseal")
    with pytest.raises(SystemExit, match="1회"):
        RUN.stage_reseal(None)                                                  # 커밋 뒤에도 거부
    RUN.stage_open(None)
    assert json.loads((e.res / "open.json").read_text(encoding="utf-8"))["label"] == "있음(−)"


def test_build_and_seal_refuse_after_reseal(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    (tmp_path / "seal_v1.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="seal_v1.json"):
        RUN.stage_build(None)
    with pytest.raises(SystemExit, match="seal_v1.json"):
        RUN.stage_seal(None)


def _resealed_files(tmp_path, record=True, v1_md5=None):
    (tmp_path / "seal_v1.json").write_text('{"v": 1}', encoding="utf-8")
    (tmp_path / "sealed_report_v1.md").write_text("# v1\n", encoding="utf-8")
    (tmp_path / "reseal_diff.md").write_text("# diff\n", encoding="utf-8")
    rec = {"n": 1, "v1_seal_md5": v1_md5 or RUN.md5(tmp_path / "seal_v1.json")} if record else None
    _seal_files(tmp_path, {"build_md5": _fake_build(tmp_path), "gate": {"tool": "cr1"}, "n1": 150, "reseal": rec})


def test_open_checks_reseal_record_consistency(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    monkeypatch.setattr(RUN, "committed_unchanged", lambda p: True)
    monkeypatch.setattr(RUN, "_check_build", lambda conn: {})

    def stop(conn):
        raise RuntimeError("reached")
    monkeypatch.setattr(RUN, "_load_env", stop)

    _resealed_files(tmp_path, record=False)                 # 재봉인 파일은 있는데 seal.json 에 기록 없음
    with pytest.raises(SystemExit, match="재봉인"):
        RUN.stage_open(None)
    _resealed_files(tmp_path, v1_md5="0" * 32)             # v1 md5 불일치
    with pytest.raises(SystemExit, match="재봉인"):
        RUN.stage_open(None)
    _resealed_files(tmp_path)
    (tmp_path / "reseal_diff.md").unlink()                   # 차이표 없음
    with pytest.raises(SystemExit, match="재봉인"):
        RUN.stage_open(None)
    _resealed_files(tmp_path)
    monkeypatch.setattr(RUN, "committed_unchanged", lambda p: p.name != "seal_v1.json")   # v1 미커밋
    with pytest.raises(SystemExit, match="재봉인"):
        RUN.stage_open(None)
    assert not (tmp_path / "open.started").exists()
    monkeypatch.setattr(RUN, "committed_unchanged", lambda p: True)
    with pytest.raises(RuntimeError, match="reached"):      # 모두 맞으면 open.started 뒤 계산으로 간다
        RUN.stage_open(None)
    assert (tmp_path / "open.started").exists()


def test_flatten_seal_and_diff_table():
    s1 = {"n1": 120, "gate": {"tool": "cr1", "rej_cr1": 0.1}, "lib_versions": {"numpy": "2.0.2"}, "reseal": None,
          "n1_raw_by_year": {"2021": 40}}
    s2 = {"n1": 118, "gate": {"tool": "2way", "rej_cr1": 0.1}, "lib_versions": {"numpy": "2.0.2"},
          "reseal": {"n": 1}, "n1_raw_by_year": {"2021": 39}}
    f1 = RUN.flatten_seal(s1)
    assert f1 == {"n1": 120, "gate.tool": "cr1", "gate.rej_cr1": 0.1, "lib_versions.numpy": "2.0.2", "reseal": None,
                  "n1_raw_by_year.2021": 40}
    lines = RUN.seal_diff_table(s1, s2)
    txt = "\n".join(lines)
    assert "| `n1` | 120 | 118 | 다름 |" in txt and "| `gate.rej_cr1` | 0.1 | 0.1 | 같음 |" in txt
    assert "| `reseal` | null | — | 다름 |" in txt and "| `reseal.n` | — | 1 | 다름 |" in txt


# ── A-5 · 정지일 = 거래량≤0 행 ∪ 내부 결측 거래일 ───────────────────────────────────────
CAL = [d for d in (date(2022, 1, 3) + timedelta(days=i) for i in range(20)) if d.weekday() < 5][:12]   # 평일 달력


def _px(spec):
    rows = []
    for code, days in spec.items():
        for i, vol in days:
            d = CAL[i] if isinstance(i, int) else i
            rows.append(dict(stock_code=code, date=pd.Timestamp(d), open=100.0, high=101.0, low=99.0, close=100.0,
                             volume=vol, adj_factor=np.nan))
    return pd.DataFrame(rows).sort_values(["stock_code", "date"]).reset_index(drop=True)


def test_halt_dates_volume_zero_rows_and_interior_missing_days():
    px = _px({"A": [(1, 5.0), (2, 5.0), (5, 0.0), (7, 5.0)],            # 3·4·6 내부 결측 · 5 거래량 0 · 0·8~ 바깥
              "B": [(i, (np.nan if i == 2 else 5.0)) for i in range(12)],   # 결측 거래량 = 정지
              "C": [(0, 5.0), (date(2022, 1, 8), 5.0), (11, 5.0)]})        # 달력 밖 행(토요일)은 무시
    out = L.halt_dates(px, CAL)
    assert out["A"] == {CAL[3], CAL[4], CAL[5], CAL[6]}
    assert out["B"] == {CAL[2]}
    assert out["C"] == set(CAL[1:11])
    assert L.interior_missing(px, CAL) == {"A": {CAL[3], CAL[4], CAL[6]}, "C": set(CAL[1:11])}


def _env(bars):
    idx = {d: i for i, d in enumerate(CAL)}
    return SimpleNamespace(cal=CAL, cal_idx=idx, bad_open=set(), bars=lambda code: bars,
                           next_day=lambda d: CAL[idx[d] + 1] if idx.get(d, -9) + 1 < len(CAL) else None)


def test_interior_missing_day_in_holding_forces_exit_at_resume_open():
    days = [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11]                         # CAL[3] 행 없음(내부 결측)
    px = _px({"Z": [(i, 5.0) for i in days]})
    bars = {CAL[i]: X.Bar(CAL[i], 100.0, 101.0, 99.5, 100.0) for i in days}
    bars[CAL[4]] = X.Bar(CAL[4], 95.0, 96.0, 94.0, 95.0)              # 재개 첫 봉
    halts = L.halt_dates(px, CAL)["Z"]
    assert halts == {CAL[3]}
    r = L.simulate_candidate(_env(bars), "Z", CAL[0], halts)
    assert r["exit_reason"] == L.EXIT_HALT_RESUME and r["exit_date"] == CAL[4] and abs(r["ret_sl"] + 5.0) < 1e-9
    assert r["halted_in_path"]
    assert L.simulate_candidate(_env(bars), "Z", CAL[2], halts)["status"] == "halt_entry"   # 진입일 내부 결측


def test_surv_interior_gap_is_its_own_excluded_bucket():
    cal = CAL[:6]
    keys = {("G", cal[0]), ("G", cal[4]), ("D", cal[0]), ("P", cal[1])}
    first = {"G": cal[0], "D": cal[0], "P": cal[1]}
    last = {"G": cal[4], "D": cal[0], "P": cal[1]}
    assert SV.classify("G", cal[2], "Y", cal, keys, first, last) == "gap_interior"   # 앞뒤로 행 있음 → 정지(제외)
    assert SV.classify("D", cal[2], "Y", cal, keys, first, last) == "gone_after"     # 그 뒤로 행 없음 → 누락
    assert SV.classify("N", cal[2], "Y", cal, keys, first, last) == "never_present"
    assert SV.classify("P", cal[0], "Y", cal, keys, first, last) == "later_listed"
    rows = [("G", cal[2], "유상증자결정", "B", "Y"), ("D", cal[2], "유상증자결정", "B", "Y"),
            ("P", cal[1], "유상증자결정", "B", "Y"), ("G", cal[0], "사업보고서 (2021.12)", "A", "Y"),
            ("G", cal[3], "분기보고서 (2022.03)", "A", "Y")]
    out = SV.survivorship(rows, cal, keys, first, last)
    assert out["breakdown_i"]["gap_interior"] == 1 and out["n_i"] == 2 and out["surv_i"] == 0.5
    assert out["breakdown_ii"]["present"] == 1 and out["n_ii"] == 1 and out["surv_ii"] == 0.0   # 내부 결측 공시는 회사 판정 밖
    assert "내부 결측" in SV.breakdown_text(out)
    assert set(SV.CLASSES) == {"present", "gone_after", "never_present", "gap_interior", "later_listed", "konex",
                               "out_of_cal"}


# ── A-6 · 가짜 게이트 하측 거부율 ≤ 0.075 ─────────────────────────────────────────────────
def _fes_lo(n_rej, n_lo_c, n_lo_w, n=400):
    out = []
    for i in range(n):
        p2 = 0.01 if i < n_rej else 0.5
        out.append(FE(-0.1 * (i % 7), 1.0, 1.0, 0.01 if i < n_lo_c else 0.5, p2, 0.01 if i < n_lo_w else 0.5, p2,
                      100, 10, 50, 40, 10))
    return out


def test_gate_a6_lower_tail_limit_per_tool():
    assert S.FAKE_LO_TAIL_MAX == 0.075
    ok = G.summarize(_fes_lo(40, 30, 0), 400)                          # 30/400 = 0.075 → 경계 포함
    assert ok["tool"] == "cr1" and ok["rej_lo_cr1"] == pytest.approx(0.075) and ok["why_cr1"] == "ok"
    to2 = G.summarize(_fes_lo(40, 31, 0), 400)                         # CR1 하측 0.0775 → 2원
    assert to2["tool"] == "2way" and to2["reason"] == "ok" and to2["why_cr1"] == "lower_tail"
    assert to2["rej_lo_2w"] == 0.0 and to2["why_2w"] == "ok"
    bad = G.summarize(_fes_lo(40, 31, 31), 400)
    assert bad["tool"] == "fail" and bad["reason"] == "out_of_band" and bad["why_2w"] == "lower_tail"
    assert bad["rej_lo_2w"] == pytest.approx(31 / 400)
    band = G.summarize(_fes_lo(20, 0, 0), 400)                         # 양측 0.05 → 밴드 밖
    assert band["why_cr1"] == "band" and band["tool"] == "fail"
    deg = G.summarize(_fes_lo(40, 0, 0)[:379] + [FE(NAN, NAN, NAN, NAN, NAN, NAN, NAN, 0, 0, 0, 0, 0)] * 21, 400)
    assert deg["tool"] == "fail" and deg["reason"] == "degenerate" and deg["why_cr1"] == "degenerate"


def test_seal_report_prints_lower_tail_for_both_tools_and_limit():
    gate = dict(GATE, rej_lo_2w=0.04, why_cr1="ok", why_2w="ok")
    seal = dict(n1=110, n1_raw=130, n1_raw_by_year={2021: 50}, n0_raw=5000, n0=4100, sd_ctrl_sl=8.0, sd_ctrl_tp=8.1,
                gate=gate, mde_null=2.9, mde_se=2.7, pl_small_share_by_year={2021: {"n": 1, "n_nan": 0,
                                                                                   "share_small": 0.7}},
                surv={"surv_i": 0.01, "n_i": 3, "surv_ii": 0.0, "n_ii": 2, "breakdown_i": {c: 1 for c in SV.CLASSES},
                      "breakdown_ii": {c: 1 for c in SV.CLASSES}}, final_verdict=None, reseal=None)
    txt = "\n".join(RUN.seal_report_lines(seal))
    assert "하측(p1<0.05) CR1 0.050 · 2원 0.040" in txt and "≤ 0.075" in txt


# ── M5 범위(Ruling) · 동결 뒤 .py 변경만 거부 ────────────────────────────────────────────
def test_code_changes_since_freeze_ignores_md_and_non_py(monkeypatch, tmp_path):
    repo, pkg = _repo(tmp_path)
    monkeypatch.setattr(S, "PKG", pkg)
    monkeypatch.setattr(S, "RESULTS", pkg / "results")
    (repo / "REGISTRY.md").write_text("| DF1 |\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "note.md").write_text("x\n", encoding="utf-8")
    (pkg / "PREREG.md").write_text("# 사전등록\n", encoding="utf-8")
    (repo / "cfg.json").write_text("{}", encoding="utf-8")
    (pkg / "results" / "z.py").write_text("z = 1\n", encoding="utf-8")
    _commit(repo, "docs after freeze")
    assert RUN.code_changes_since_freeze() == []


def test_code_changes_since_freeze_catches_py_anywhere_incl_deletion(monkeypatch, tmp_path):
    repo, pkg = _repo(tmp_path)
    monkeypatch.setattr(S, "PKG", pkg)
    monkeypatch.setattr(S, "RESULTS", pkg / "results")
    (repo / "utils").mkdir()
    (repo / "utils" / "helper.py").write_text("h = 1\n", encoding="utf-8")
    (repo / "REGISTRY.md").write_text("| DF1 |\n", encoding="utf-8")
    (pkg / "a.py").unlink()
    _commit(repo, "py after freeze")
    assert RUN.code_changes_since_freeze() == ["pkg/a.py", "utils/helper.py"]
