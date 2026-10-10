"""critic(de2e361) 동결 전 수정 — 사장님 답과 무관한 것(B1 태그별 · B2 ca_path 인쇄 · M4 종목별 지문 · M5 · 사소).

합성 데이터 · DB 없음 · git 은 tmp 레포만.
"""
import json
import math
import subprocess
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.dt_dart_filter import run as RUN
from backtest.concept_axes.dt_dart_filter import settings as S
from backtest.concept_axes.dt_dart_filter import stats as ST
from backtest.concept_axes.dt_dart_filter import tags as T
from backtest.concept_axes.dt_dart_filter.stats import FE
from backtest.concept_axes.dt_dart_filter.tests.test_run import _fake_build, _frozen_env, _seal_files

D0 = date(2021, 3, 2)


# ── B1 · 태그별 3개 + Holm ────────────────────────────────────────────────────────
def test_per_tag_frame_keeps_controls_and_this_tag_rows_only():
    df = pd.DataFrame({"stock_code": list("abcde"), "scan_date": [D0] * 5, "x": [1, 1, 1, 0, 0]})
    f = RUN.per_tag_frame(df, {("a", D0), ("c", D0)})
    assert list(f["stock_code"]) == ["a", "c", "d", "e"]            # b = 다른 태그로만 표식 → 제외
    assert list(f["x"]) == [1, 1, 0, 0]


def _fe(p1c, p1w):
    return FE(-1.0, 1.0, 2.0, p1c, 2 * p1c, p1w, 2 * p1w, 100, 10, 20, 30, 5)


def test_tool_p1_follows_seal_tool_and_cr1_print_only_on_fail():
    assert RUN.tool_p1(_fe(0.01, 0.2), "cr1") == (0.01, "cr1")
    assert RUN.tool_p1(_fe(0.01, 0.2), "2way") == (0.2, "2way")
    p, used = RUN.tool_p1(_fe(0.01, 0.2), "fail")
    assert p == 0.01 and "인쇄만" in used


def _panel(seed=3, n_days=180, per_day=20):
    """날마다 후보 per_day 개 · 태그1(3일에 1번 · 효과 −4) · 태그2(3일에 1번 · 효과 0) · 태그3 표식 없음."""
    rng = np.random.default_rng(seed)
    rows, m1, m2 = [], set(), set()
    for d in range(n_days):
        day = date(2021, 2, 1) + timedelta(days=d)
        for j in range(per_day):
            code = f"{(d * per_day + j) % 300:06d}"
            eff = 0.0
            if j == 0 and d % 3 == 0:
                m1.add((code, day))
                eff = -4.0
            elif j == 0 and d % 3 == 1:
                m2.add((code, day))
            rows.append(dict(stock_code=code, scan_date=day, day=d, stock=code, block=d // 20,
                             y_sl=eff + rng.normal(0, 3), y_tp=eff + rng.normal(0, 3)))
    df = pd.DataFrame(rows)
    df["x"] = [1 if (c, s) in (m1 | m2) else 0 for c, s in zip(df["stock_code"], df["scan_date"])]
    return df, m1, m2


def test_per_tag_results_holm_nan_guard_and_interpretation_only_when_present():
    df, m1, m2 = _panel()
    res, lines = RUN.per_tag_results(df, [m1, m2, set()], "cr1", "있음(−)")
    assert [r["tag"] for r in res["tags"]] == list(S.TAGS_LAG0)
    assert [r["marks"] for r in res["tags"]] == [f"marks_{n}.csv" for n in RUN.TAG_MARKS]
    t1, t2, t3 = res["tags"]
    assert t1["beta"] < -2 and t1["n1"] == 60 and t1["p1"] == t1["fe"]["p1_cr1"] and t1["p_holm"] < 0.05
    assert math.isnan(t3["p1"]) and t3["p_holm"] == 1.0 and t3["n1"] == 0     # 표식 0 → NaN → Holm 1.0
    assert [t["p_holm"] for t in res["tags"]] == ST.holm([t["p1"] for t in res["tags"]])
    assert res["interpreted"] is True and res["tool_used"] == "cr1"
    assert any("기여 있음" in ln for ln in lines) and not any("해석 안 함" in ln for ln in lines)

    res2, lines2 = RUN.per_tag_results(df, [m1, m2, set()], "cr1", "판별 보류")
    assert [t["p_holm"] for t in res2["tags"]] == [t["p_holm"] for t in res["tags"]]   # 계산은 라벨과 무관
    assert res2["interpreted"] is False
    assert any("해석 안 함" in ln for ln in lines2) and not any("기여 있음" in ln for ln in lines2)

    res3, _ = RUN.per_tag_results(df, [m1, m2, set()], "2way", "판별 보류")
    assert res3["tags"][0]["p1"] == res3["tags"][0]["fe"]["p1_2w"] and res3["tool_used"] == "2way"
    res4, _ = RUN.per_tag_results(df, [m1, m2, set()], "fail", "판정 불가(도구)")
    assert res4["tags"][0]["p1"] == res4["tags"][0]["fe"]["p1_cr1"] and "인쇄만" in res4["tool_used"]


# ── B2 · ca_path 양 팔 대칭 제외 판(인쇄만) ──────────────────────────────────────────
def test_ca_path_results_counts_by_arm_and_symmetric_exclusion():
    df, m1, m2 = _panel()
    df["ca_path"] = [(i % 17 == 0) for i in range(len(df))]
    res, lines = RUN.ca_path_results(df, "cr1")
    x, ca = df["x"].to_numpy() == 1, df["ca_path"].to_numpy()
    assert res["counts"] == {"표식": {"ca_path": int((x & ca).sum()), "n": int(x.sum())},
                             "대조": {"ca_path": int((~x & ca).sum()), "n": int((~x).sum())}}
    keep = df[~df["ca_path"]]
    ref = ST.fe_regression(keep["y_sl"].to_numpy(), keep["x"].to_numpy(), keep["day"].to_numpy(),
                           keep["stock"].to_numpy(), keep["block"].to_numpy())
    assert res["fe_sl_excl"] == ref.__dict__ and res["p1"] == ref.p1_cr1 and res["tool_used"] == "cr1"
    assert any("ca_path" in ln for ln in lines)


# ── open 보조 · 팔별 no_fill 비율 · unresolved 수 ──────────────────────────────────
def test_fill_counts_by_arm_small_proxy_only():
    led = pd.DataFrame([("1", D0, "filled", 0.2), ("2", D0, "no_fill", 0.3), ("3", D0, "no_fill", 0.1),
                        ("4", D0, "filled", 0.7), ("5", D0, "no_fill", 0.8), ("6", D0, "halt_entry", 0.1),
                        ("7", D0, "filled", float("nan")), ("8", D0, "filled", 0.4)],
                       columns=["stock_code", "scan_date", "status", "p_L"])
    out = RUN.fill_counts(led, {("2", D0), ("1", D0), ("5", D0)})
    assert out == {"표식": {"no_fill": 1, "n": 2, "rate": 0.5}, "대조": {"no_fill": 1, "n": 2, "rate": 0.5}}


def test_unresolved_counts_by_arm():
    df = pd.DataFrame({"x": [1, 1, 0, 0, 0], "unresolved": [True, False, True, True, False]})
    assert RUN.unresolved_counts(df) == {"표식": {"unresolved": 1, "n": 2}, "대조": {"unresolved": 2, "n": 3}}


# ── M4 · 종목별 지문 ───────────────────────────────────────────────────────────────
def test_fingerprint_diff_codes():
    old = {"000001": "a", "000002": "b", "000003": "c"}
    new = {"000001": "a", "000002": "B", "000004": "d"}
    assert RUN.fingerprint_diff(old, new) == {"changed": ["000002"], "added": ["000004"], "removed": ["000003"]}


def test_check_build_prints_changed_stock_codes_only_then_refuses(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(S, "RESULTS", tmp_path)
    h = lambda ch: ch * 32                                                       # noqa: E731
    meta = {"md5": {}, "db_fingerprint": "old", "per_stock": {"000001": h("a"), "000002": h("b"), "000003": h("c")}}
    (tmp_path / "build_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    new = {"sha256": "new", "per_stock": {"000001": h("a"), "000002": h("e"), "000004": h("d")}}
    monkeypatch.setattr(RUN.LD, "db_fingerprint", lambda conn, a, b: new)
    with pytest.raises(SystemExit, match="지문"):
        RUN._check_build(None)
    out = capsys.readouterr().out
    assert "000002" in out and "000003" in out and "000004" in out and "000001" not in out
    assert h("b") not in out and h("e") not in out                               # 종목 코드만 · 해시 인쇄 안 함
    monkeypatch.setattr(RUN.LD, "db_fingerprint", lambda conn, a, b: {"sha256": "old", "per_stock": {}})
    assert RUN._check_build(None)["db_fingerprint"] == "old"


def test_check_build_without_per_stock_says_so(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(S, "RESULTS", tmp_path)
    (tmp_path / "build_meta.json").write_text(json.dumps({"md5": {}, "db_fingerprint": "old"}), encoding="utf-8")
    monkeypatch.setattr(RUN.LD, "db_fingerprint", lambda conn, a, b: {"sha256": "new", "per_stock": {"1": "x"}})
    with pytest.raises(SystemExit):
        RUN._check_build(None)
    assert "종목별 지문 없음" in capsys.readouterr().out


# ── M5 · 동결 커밋 뒤 results/ 밖 변경 금지 · 라이브러리 버전 ──────────────────────────
def _g(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)


def _commit(repo, msg):
    _g(repo, "add", "-A")
    _g(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", msg)


def _repo(tmp_path, with_frozen=True):
    repo = tmp_path / "repo"
    pkg = repo / "pkg"
    (pkg / "results").mkdir(parents=True)
    _g(repo, "init", "-q")
    (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")
    (pkg / "results" / "proxy_coef.json").write_text("{}", encoding="utf-8")
    if with_frozen:
        (pkg / "frozen_consts.py").write_text("PREREG_FROZEN_BLOB = 'x'\n", encoding="utf-8")
    _commit(repo, "freeze")
    return repo, pkg


def test_code_changes_since_freeze_allows_only_results(monkeypatch, tmp_path):
    repo, pkg = _repo(tmp_path)
    monkeypatch.setattr(S, "PKG", pkg)
    monkeypatch.setattr(S, "RESULTS", pkg / "results")
    assert RUN.code_changes_since_freeze() == []
    (pkg / "results" / "ledger_A.csv").write_text("a\n", encoding="utf-8")
    _commit(repo, "build")
    assert RUN.code_changes_since_freeze() == []
    (repo / "other").mkdir()
    (repo / "other" / "x.py").write_text("y = 2\n", encoding="utf-8")
    (pkg / "a.py").write_text("x = 2\n", encoding="utf-8")
    _commit(repo, "code after freeze")
    assert RUN.code_changes_since_freeze() == ["other/x.py", "pkg/a.py"]


def test_code_changes_since_freeze_refuses_without_frozen_commit(monkeypatch, tmp_path):
    repo, pkg = _repo(tmp_path, with_frozen=False)
    monkeypatch.setattr(S, "PKG", pkg)
    monkeypatch.setattr(S, "RESULTS", pkg / "results")
    with pytest.raises(SystemExit, match="frozen_consts"):
        RUN.code_changes_since_freeze()


def test_require_frozen_refuses_code_changed_after_freeze_commit(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    RUN.require_frozen()
    monkeypatch.setattr(RUN, "code_changes_since_freeze", lambda: ["RoboTrader_template/utils/x.py"])
    with pytest.raises(SystemExit, match=r"동결 커밋.* 뒤 results/ 밖 변경 .*utils/x\.py"):
        RUN.require_frozen()


def test_lib_versions_and_check():
    import scipy
    v = RUN.lib_versions()
    assert v == {"numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__}
    RUN.check_lib_versions({"lib_versions": dict(v)})
    for bad in ({"lib_versions": {**v, "numpy": "0.0.1"}}, {"lib_versions": {}}, {}):
        with pytest.raises(SystemExit, match="라이브러리"):
            RUN.check_lib_versions(bad)


def test_open_refuses_lib_version_mismatch_before_started_marker(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    monkeypatch.setattr(RUN, "committed_unchanged", lambda p: True)
    monkeypatch.setattr(RUN, "_check_build", lambda conn: {})
    _seal_files(tmp_path, {"build_md5": _fake_build(tmp_path), "lib_versions": {**RUN.lib_versions(), "scipy": "0"}})
    with pytest.raises(SystemExit, match="라이브러리"):
        RUN.stage_open(None)
    assert not (tmp_path / "open.started").exists()


# ── 사소 · check-backfill 유형 · build 멈춤 규칙 · 고정 의존 ────────────────────────────
def test_check_backfill_stage_uses_settings_types(monkeypatch, tmp_path):
    seen = {}

    def fake_check(conn, d, start, end, types):
        seen["args"] = (start, end, tuple(types))
        return {"n_cells": 1, "n_bad": 0, "bad": [], "complete": True}
    monkeypatch.setattr(RUN.DC, "check", fake_check)
    monkeypatch.setattr(S, "BACKFILL_TYPES", ("A", "B"))
    monkeypatch.setattr(S, "RESULTS", tmp_path)
    assert RUN.stage_check_backfill(None, tmp_path) == 0
    assert seen["args"] == (S.FILING_START, S.SCAN_END, ("A", "B"))
    assert json.loads((tmp_path / "backfill_check.json").read_text(encoding="utf-8"))["types"] == ["A", "B"]


def test_backfill_rows_expected_constant_and_check():
    assert S.BACKFILL_ROWS_EXPECTED == 226_475
    RUN.check_backfill_rows(226_475)
    for n in (226_474, 226_476, 0):
        with pytest.raises(SystemExit, match="226,475"):
            RUN.check_backfill_rows(n)


def test_check_scan_diag_refuses_errors():
    RUN.check_scan_diag({"n_errors": 0, "n_days": 3, "n_rows": 9})
    with pytest.raises(SystemExit, match="n_errors"):
        RUN.check_scan_diag({"n_errors": 1, "n_days": 3, "n_rows": 9})


class _Cur:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        self.log.append((sql, params))

    def fetchone(self):
        return (226_475,)


class _Conn:
    def __init__(self):
        self.log, self.rolled = [], False

    def cursor(self):
        return _Cur(self.log)

    def rollback(self):
        self.rolled = True


def test_count_backfill_rows_selects_window_and_types():
    c = _Conn()
    assert T.count_backfill_rows(c, S.FILING_START, S.SCAN_END, S.BACKFILL_TYPES) == 226_475
    (sql, params), = c.log
    assert sql.lstrip().upper().startswith("SELECT COUNT(*) FROM DART_DISCLOSURES")
    assert "rcept_dt BETWEEN" in sql and "pblntf_ty = ANY" in sql
    assert params == (S.FILING_START, S.SCAN_END, list(S.BACKFILL_TYPES)) and c.rolled


def _chk():
    return dict(complete=True, window=[S.FILING_START.isoformat(), S.SCAN_END.isoformat()],
                types=list(S.BACKFILL_TYPES))


def test_build_refuses_backfill_row_count_mismatch_before_loading_prices(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    monkeypatch.setattr(RUN, "committed_unchanged", lambda p: True)
    (tmp_path / "backfill_check.json").write_text(json.dumps(_chk()), encoding="utf-8")
    monkeypatch.setattr(RUN.T, "count_backfill_rows", lambda conn, a, b, t: 226_000)

    def boom(conn):
        raise AssertionError("가격을 읽기 전에 멈춰야 한다")
    monkeypatch.setattr(RUN, "_load_env", boom)
    with pytest.raises(SystemExit, match="226,475"):
        RUN.stage_build(None)


def test_build_refuses_scan_errors_before_writing_ledger(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    monkeypatch.setattr(RUN, "committed_unchanged", lambda p: True)
    (tmp_path / "backfill_check.json").write_text(json.dumps(_chk()), encoding="utf-8")
    monkeypatch.setattr(RUN.T, "count_backfill_rows", lambda conn, a, b, t: S.BACKFILL_ROWS_EXPECTED)
    monkeypatch.setattr(RUN, "_load_env", lambda conn: ([date(2021, 2, 1)], pd.DataFrame(), None))
    monkeypatch.setattr(RUN.U, "scan_window", lambda px, days: ([], {"n_errors": 2, "n_days": 1, "n_rows": 0}))
    with pytest.raises(SystemExit, match="n_errors"):
        RUN.stage_build(None)
    assert not (tmp_path / "ledger_A.csv").exists()


def test_pins_and_ledger_cover_ca_path():
    assert "RoboTrader_template/backtest/concept_axes/replayer/flags.py" in RUN.PIN_DEPS
    assert "ca_path" in RUN.LEDGER_COLS
    assert RUN.TAG_MARKS == ("lag0_t1", "lag0_t2", "lag0_t3") and len(S.TAGS_LAG0) == 3
