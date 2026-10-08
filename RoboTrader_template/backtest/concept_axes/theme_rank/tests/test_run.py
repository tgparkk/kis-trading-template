from __future__ import annotations

import pytest

from backtest.concept_axes.theme_rank import run as RN

TXT = ("…\n- arena.csv md5: " + "a" * 32 + "\n- signals.csv md5: " + "b" * 32 +
       "\n- calib.json md5: " + "c" * 32 + "\n")


def test_read_frozen_md5():
    assert RN.read_frozen_md5(TXT) == {"arena.csv": "a" * 32, "signals.csv": "b" * 32, "calib.json": "c" * 32}


def test_guard_refuses_when_not_frozen_or_mismatch(monkeypatch):
    monkeypatch.setattr(RN, "PREREG_FROZEN_BLOB", "")
    monkeypatch.setattr(RN, "N_CUT", 547)
    with pytest.raises(SystemExit):
        RN.guard(lambda: "x" * 40, TXT, lambda name: "a" * 32)
    monkeypatch.setattr(RN, "PREREG_FROZEN_BLOB", "f" * 40)
    with pytest.raises(SystemExit):
        RN.guard(lambda: "e" * 40, TXT, lambda name: "a" * 32)                 # blob 불일치
    md5s = {"arena.csv": "a" * 32, "signals.csv": "b" * 32, "calib.json": "0" * 32}
    with pytest.raises(SystemExit):
        RN.guard(lambda: "f" * 40, TXT, md5s.get)                             # calib md5 불일치
    md5s["calib.json"] = "c" * 32
    RN.guard(lambda: "f" * 40, TXT, md5s.get)                                 # 통과


def test_guard_refuses_without_n_cut(monkeypatch):
    monkeypatch.setattr(RN, "PREREG_FROZEN_BLOB", "f" * 40)
    monkeypatch.setattr(RN, "N_CUT", None)
    with pytest.raises(SystemExit):
        RN.guard(lambda: "f" * 40, TXT, {"arena.csv": "a" * 32, "signals.csv": "b" * 32, "calib.json": "c" * 32}.get)


@pytest.mark.parametrize("args,expected", [
    ((0.01, 0.03, 0.02, 0.04, 0.6, 0.02), "PASS"),
    ((0.01, 0.03, 0.02, 0.04, 0.4, 0.02), "FAIL"),     # 돈 게이트 미달
    ((0.01, 0.03, 0.02, 0.04, 0.6, -0.01), "FAIL"),    # 편향 빼면 부호 뒤집힘
    ((0.01, 0.03, -0.01, 0.04, 0.6, 0.02), "FAIL"),    # 두 창 부호 불일치
    ((0.20, 0.03, 0.02, 0.04, 0.6, 0.02), "FAIL"),     # 유의 아님
    ((0.01, -0.03, -0.02, -0.04, -0.6, -0.02), "NEG"),
    ((0.01, -0.03, 0.02, -0.04, -0.6, -0.02), "FAIL"),
    ((float("nan"), 0.03, 0.02, 0.04, 0.6, 0.02), "FAIL"),
    ((0.01, float("nan"), 0.02, 0.04, 0.6, 0.02), "FAIL"),
    ((0.01, 0.03, float("nan"), 0.04, 0.6, 0.02), "FAIL"),
    ((0.01, 0.03, float("nan"), float("nan"), 0.6, 0.02), "FAIL"),
    ((0.01, -0.03, float("nan"), -0.02, -0.6, -0.02), "FAIL"),
    ((0.01, 0.03, 0.02, 0.04, float("nan"), 0.02), "FAIL"),
    ((0.01, 0.03, 0.02, 0.04, 0.6, float("nan")), "FAIL"),
])
def test_verdict_table(args, expected):
    assert RN.verdict(*args) == expected
