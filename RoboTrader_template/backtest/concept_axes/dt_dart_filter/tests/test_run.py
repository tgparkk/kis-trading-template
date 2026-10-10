import pytest

from backtest.concept_axes.dt_dart_filter import frozen_consts as FC
from backtest.concept_axes.dt_dart_filter import run as RUN
from backtest.concept_axes.dt_dart_filter import settings as S
from backtest.concept_axes.dt_dart_filter.stats import FE


def _fe(beta, p1, p2):
    return FE(beta, 1.0, 1.0, p1, p2, p1, p2, 500, 120, 300, 200, 40)


EX = FE(-0.8, 1.0, 1.0, 0.02, 0.04, 0.02, 0.04, 480, 110, 300, 200, 40)   # ca_path 대칭 제외 손절 우선 판(A-2)


def test_label_present_requires_both_rules_threshold_and_survivorship():
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-0.9, 0.03, 0.06), "cr1", 120, 0.3, 0.1, EX) == "있음(−)"
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-0.9, 0.20, 0.40), "cr1", 120, 0.3, 0.1, EX) == "판별 보류"
    assert RUN.label(_fe(-0.3, 0.01, 0.02), _fe(-0.3, 0.01, 0.02), "cr1", 120, 0.3, 0.1, EX) == "판별 보류"
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-0.9, 0.01, 0.02), "cr1", 120, 0.05, 0.1, EX) == "판별 보류"


def test_label_reverse_tool_fail_and_small_n():
    assert RUN.label(_fe(1.2, 0.99, 0.01), _fe(1.2, 0.99, 0.01), "cr1", 120, 0.3, 0.1, EX) == "역방향"
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-1.0, 0.01, 0.02), "fail", 120, 0.3, 0.1, EX) == "판정 불가(도구)"
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-1.0, 0.01, 0.02), "cr1", 99, 0.3, 0.1, EX) == "판별 보류(n₁<100)"


def test_require_frozen_refuses_when_blob_empty(monkeypatch):
    monkeypatch.setattr(FC, "PREREG_FROZEN_BLOB", "")
    with pytest.raises(SystemExit):
        RUN.require_frozen()


def test_open_refuses_without_frozen(monkeypatch):
    monkeypatch.setattr(FC, "PREREG_FROZEN_BLOB", "")
    with pytest.raises(SystemExit):
        RUN.main(["--stage", "open"])


# ── fix round 1 ─────────────────────────────────────────────────────────────────
import json
from pathlib import Path

import pandas as pd


_REAL_BLOB = RUN.blob


def _frozen_env(monkeypatch, tmp_path, md5_value=None):
    """동결 상태 흉내 — PREREG.md 는 tmp 파일 1개(a.py)를 고정하는 pins 블록을 담는다(실제 git hash-object)."""
    (tmp_path / "a.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "PREREG.md").write_text(
        "# 사전등록\n\n```pins\n# path blob\na.py " + _REAL_BLOB(tmp_path / "a.py") + "\n```\n", encoding="utf-8")
    (tmp_path / "proxy_coef.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(S, "RESULTS", tmp_path)
    monkeypatch.setattr(S, "PREREG", tmp_path / "PREREG.md")
    monkeypatch.setattr(FC, "PREREG_FROZEN_BLOB", "abc")
    monkeypatch.setattr(RUN, "blob", lambda p: "abc" if Path(p).name == "PREREG.md" else _REAL_BLOB(p))
    monkeypatch.setattr(RUN, "clean_package", lambda: True)
    monkeypatch.setattr(RUN, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(RUN, "required_pins", lambda root: ["a.py"])
    monkeypatch.setattr(RUN, "code_changes_since_freeze", lambda: [])   # M5 git 검사는 test_prefreeze 가 tmp 레포로 따로
    monkeypatch.setattr(FC, "PROXY_COEF_MD5", RUN.md5(tmp_path / "proxy_coef.json") if md5_value is None else md5_value)


def test_effective_n1_excludes_marked_days_without_control():
    df = pd.DataFrame({"x": [1, 0, 1, 1, 0], "day": [1, 1, 2, 3, 3], "y_sl": [0.0] * 5})
    assert RUN.effective_n1(df) == 2      # day 2 has no control -> dropped
    import dataclasses
    fe_sl = dataclasses.replace(_fe(-1.0, 0.01, 0.02), n1=99)
    assert RUN.label(fe_sl, fe_sl, "cr1", fe_sl.n1, 0.3, 0.1, EX) == "판별 보류(n₁<100)"


def test_require_frozen_needs_proxy_coef_md5(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    RUN.require_frozen()                                   # all good -> no raise
    monkeypatch.setattr(FC, "PROXY_COEF_MD5", "")
    with pytest.raises(SystemExit):
        RUN.require_frozen()
    monkeypatch.setattr(FC, "PROXY_COEF_MD5", "deadbeef")
    with pytest.raises(SystemExit):
        RUN.require_frozen()


def test_proxy_stage_refuses_after_freeze(monkeypatch):
    monkeypatch.setattr(FC, "PREREG_FROZEN_BLOB", "abc")
    with pytest.raises(SystemExit):
        RUN.stage_proxy(None)


def _seal_files(tmp_path, seal, report_md5=None):
    """seal.json + sealed_report.md(seal.json md5 줄 포함) — report_md5 를 주면 그 값을 적는다(불일치 흉내)."""
    seal = {"lib_versions": RUN.lib_versions(),                    # M5 — 봉인 때 라이브러리 버전(주면 그 값)
            "gate": {"tool": "cr1"}, "n1": S.N1_MIN, "final_verdict": None, "reseal": None,   # A-3·A-4 기본 = 개봉 대상
            **seal}
    (tmp_path / "seal.json").write_text(json.dumps(seal), encoding="utf-8")
    h = RUN.md5(tmp_path / "seal.json") if report_md5 is None else report_md5
    (tmp_path / "sealed_report.md").write_text("# 봉인\n\n" + RUN.seal_md5_line(h) + "\n", encoding="utf-8")


def _fake_build(tmp_path):
    (tmp_path / "ledger_A.csv").write_text("a\n", encoding="utf-8")
    meta = {"md5": {"ledger_A.csv": RUN.md5(tmp_path / "ledger_A.csv")}}
    (tmp_path / "build_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return RUN.build_hashes()


def test_open_refuses_tampered_build_output(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    monkeypatch.setattr(RUN, "committed_unchanged", lambda p: True)
    _seal_files(tmp_path, {"build_md5": _fake_build(tmp_path)})
    (tmp_path / "ledger_A.csv").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="build"):
        RUN.stage_open(None)
    assert not (tmp_path / "open.json").exists() and not (tmp_path / "open.started").exists()


def test_seal_linkage_detects_meta_change_and_accepts_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "RESULTS", tmp_path)
    seal = {"build_md5": _fake_build(tmp_path)}
    RUN.check_seal_linkage(seal)
    (tmp_path / "build_meta.json").write_text(json.dumps({"md5": {}}), encoding="utf-8")
    with pytest.raises(SystemExit):
        RUN.check_seal_linkage(seal)


@pytest.mark.parametrize("name", ["seal.json", "open.json", "open.started"])
def test_build_refuses_when_seal_or_open_exists(monkeypatch, tmp_path, name):
    _frozen_env(monkeypatch, tmp_path)
    (tmp_path / name).write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        RUN.stage_build(None)


# ── final review I4 · 코드 고정(pins 블록) · 동결 상수 분리 · 어댑터 파라미터 ─────────
SHA_A, SHA_0 = "a" * 40, "0" * 40


def test_frozen_constants_live_outside_settings():
    # 동결 뒤: 상수는 frozen_consts 에만 있고 동결 파일의 실제 값과 일치해야 한다(settings 에는 없음)
    assert not hasattr(S, "PREREG_FROZEN_BLOB") and not hasattr(S, "PROXY_COEF_MD5")
    assert FC.PREREG_FROZEN_BLOB == RUN.blob(S.PREREG)
    assert FC.PROXY_COEF_MD5 == RUN.md5(S.RESULTS / "proxy_coef.json")


def test_parse_pins_reads_single_block():
    txt = ("# PREREG\n\n본문 ```inline``` 무시\n\n```pins\n# 경로 blob\n\n"
           f"RoboTrader_template/x.py {SHA_A}\nb/c.json   {SHA_0}\n```\n\n끝\n")
    assert RUN.parse_pins(txt) == {"RoboTrader_template/x.py": SHA_A, "b/c.json": SHA_0}


@pytest.mark.parametrize("body", [
    None,                                            # 블록 없음
    "",                                              # 빈 블록
    f"a.py {SHA_A} extra",                           # 토큰 3개
    "a.py abc",                                      # sha 형식
    f"a.py {SHA_A.upper()}",                         # 대문자 sha
    f"/abs/a.py {SHA_A}",                            # 절대 경로
    f"C:/a.py {SHA_A}",                              # 드라이브 경로
    f"x/../a.py {SHA_A}",                            # ..
    "x\\a.py " + SHA_A,                             # 역슬래시
    f"a.py {SHA_A}\na.py {SHA_0}",                   # 중복
])
def test_parse_pins_rejects_malformed(body):
    txt = "# PREREG\n" if body is None else f"# PREREG\n```pins\n{body}\n```\n"
    with pytest.raises(SystemExit):
        RUN.parse_pins(txt)


def test_parse_pins_rejects_two_blocks_and_unclosed():
    one = f"```pins\na.py {SHA_A}\n```\n"
    with pytest.raises(SystemExit):
        RUN.parse_pins(one + one)
    with pytest.raises(SystemExit):
        RUN.parse_pins(f"```pins\na.py {SHA_A}\n")


def test_verify_pins_uses_git_blob_and_refuses_mismatch_missing_and_uncovered(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.json").write_text("{}", encoding="utf-8")
    pins = {"a.py": RUN.blob(tmp_path / "a.py"), "sub/b.json": RUN.blob(tmp_path / "sub" / "b.json")}
    RUN.verify_pins(pins, tmp_path, ["a.py", "sub/b.json"])
    with pytest.raises(SystemExit):
        RUN.verify_pins({**pins, "a.py": SHA_0}, tmp_path, ["a.py"])          # blob 불일치
    with pytest.raises(SystemExit):
        RUN.verify_pins({**pins, "zz.py": SHA_0}, tmp_path, ["a.py"])         # 고정 파일 없음
    with pytest.raises(SystemExit):
        RUN.verify_pins({"a.py": pins["a.py"]}, tmp_path, ["a.py", "sub/b.json"])   # 필수 경로 미고정


def test_required_pins_cover_package_deps_and_backfill_report():
    root = RUN.repo_root()
    req = RUN.required_pins(root)
    pkg = "RoboTrader_template/backtest/concept_axes/dt_dart_filter/"
    for name in ("run.py", "settings.py", "gate.py", "lots.py", "stats.py", "surv.py", "universe.py", "tags.py",
                 "sample.py", "proxy.py", "daycheck.py", "__init__.py"):
        assert pkg + name in req
    assert pkg + "frozen_consts.py" not in req and not any("/tests/" in r for r in req)
    assert pkg + "results/backfill_check.json" in req
    for dep in ("strategies/daytrading_3methods_breakout/screener.py", "strategies/books/daytrading_3methods/rules.py",
                "strategies/_rule_screener_base.py", "backtest/concept_axes/replayer/scan.py",
                "backtest/concept_axes/replayer/loader.py", "backtest/concept_axes/candidate_ledger/run.py",
                "backtest/concept_axes/candidate_ledger/tool_calibration/run_calib.py",
                "backtest/concept_axes/ledger8/exitsim8.py", "backtest/concept_axes/minervini/cap_skip_ledger/sim.py",
                "backtest/concept_axes/theme_rank/bandfill.py",
                "backtest/concept_axes/candidate_ledger/dart_events/dart_tags.py"):
        assert "RoboTrader_template/" + dep in req
    for r in req:
        if r.endswith("results/backfill_check.json"):
            continue                                    # Task 11 이 만든다
        assert (root / r).is_file(), r


def test_require_frozen_refuses_pin_block_mismatch(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    RUN.require_frozen()
    (tmp_path / "a.py").write_text("print(2)\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        RUN.require_frozen()


def test_require_frozen_refuses_missing_pin_block(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    (tmp_path / "PREREG.md").write_text("# 사전등록 — pins 블록 없음\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        RUN.require_frozen()


def test_require_frozen_refuses_prereg_blob_mismatch(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    monkeypatch.setattr(FC, "PREREG_FROZEN_BLOB", "def")
    with pytest.raises(SystemExit):
        RUN.require_frozen()


def test_require_frozen_refuses_dirty_package(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    monkeypatch.setattr(RUN, "clean_package", lambda: False)
    with pytest.raises(SystemExit):
        RUN.require_frozen()


def test_require_frozen_checks_adapter_params_against_settings(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    monkeypatch.setattr(S, "MIN_TV", 2_000_000_000)
    with pytest.raises(SystemExit):
        RUN.require_frozen()
