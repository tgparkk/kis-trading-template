"""critic M6 — build → 커밋 → seal → 커밋 → open 을 tmp git 레포에서 끝까지 돌린다.

합성 가격·후보·공시 · DB 접근 함수는 전부 합성으로 바꾼다(conn=None — 남은 DB 호출이 있으면 바로 깨진다).
진짜로 도는 것: require_frozen(동결 커밋 뒤 변경 · pins · 패키지 깨끗함 · 어댑터 룰) · build 의 원장·표식·ca_path·build_meta
쓰기 · seal 의 봉인 파일 · open 의 무결성 확인 → open.started → 주 검정 · 보조 · 태그별 · ca_path 판 · RESULTS · open.json.
가짜 게이트(400 복제)와 생존자 누락률은 결정적 합성 값으로 바꾼다(각자 테스트가 따로 있다).
"""
import json
import subprocess
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.dt_dart_filter import frozen_consts as FC
from backtest.concept_axes.dt_dart_filter import run as RUN
from backtest.concept_axes.dt_dart_filter import settings as S
from backtest.concept_axes.dt_dart_filter import surv as SV
from backtest.concept_axes.dt_dart_filter import tags as T

RIGHTS, MAJOR, EMBEZ = "주요사항보고서(유상증자결정)", "최대주주변경을수반하는주식양수도계약체결", "횡령ㆍ배임혐의발생"
N_STOCK = 60
LATE = 59                    # 이 종목은 달력 30번째 날부터 가격이 있다(초기 p_L NaN → 대형 포함 표본의 NaN 분위 경로)
JUMPERS = (10, 11)           # 달력 JUMP_AT 번째 날 +40% → 진입 순번 JUMP_AT−10..JUMP_AT−1 로트 ca_path
JUMP_AT = 110                # 표식 로트(스캔 순번 86·87 = 종목 10·11)도 걸리게 고른 날


def _code(j):
    return f"{j + 1:06d}"


def _cal():
    out, d = [], date(2021, 1, 4)
    while len(out) < 200:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _px(cal):
    rows = []
    for j in range(N_STOCK):
        base = 50_000.0 if j < 3 else 10_000.0                 # 0~2 = 대형(p_L ≥ 0.5)
        for i, d in enumerate(cal):
            if j == LATE and i < 30:
                continue
            c = base * (1 + 0.01 * np.sin(i + j)) * (1.4 if (j in JUMPERS and i >= JUMP_AT) else 1.0)
            rows.append(dict(stock_code=_code(j), date=pd.Timestamp(d), open=c * 0.995, high=c * 1.01, low=c * 0.99,
                             close=c, volume=1e6, adj_factor=np.nan, market_cap=np.nan, volatility_20d=np.nan))
    px = pd.DataFrame(rows).sort_values(["stock_code", "date"]).reset_index(drop=True)
    px.attrs["normalize_counts"] = {"n_rows_raw": len(px), "n_dropped_bad_date": 0, "n_dropped_close": 3,
                                    "n_patched_ohl": 1}
    return px


def _filings(cal, scan_days):
    fil = []
    for i, d in enumerate(scan_days):
        j = 4 + (i % 2) + 2 * ((i // 2) % 20)                   # 그날 후보(같은 짝홀) 중 소형 1종목
        fil.append((_code(j), d, (RIGHTS, MAJOR, EMBEZ)[i % 3]))
        if i % 10 == 0:
            fil.append((_code(j), d, EMBEZ if i % 3 != 2 else MAJOR))   # 같은 종목·같은 날 두 번째 태그
    fil.append((_code(20), date(2021, 3, 6), RIGHTS))            # 토요일 → lag0 아님 · W5 는 있음
    fil.append((_code(21), date(2021, 3, 9), "주요사항보고서(자기주식취득결정)"))   # 태그 아님
    return fil


def _scan_rows(cal_idx, days):
    rows = []
    for i, ts in enumerate(days):
        d = pd.Timestamp(ts).date()
        js = [j for j in range(N_STOCK) if (i + j) % 2 == 0 and not (j == LATE and cal_idx[d] < 30)]
        for r, j in enumerate(js):
            rows.append(dict(scan_date=d, stock_code=_code(j), score=2.5, rank=r + 1, n_passed=len(js),
                             market_cap=float("nan"), trading_value=1e10 + 1e7 * j))
    return rows, {"n_errors": 0, "n_days": len(days), "n_rows": len(rows)}


def _sim_factory(cal, marks, effect):
    idx = {d: i for i, d in enumerate(cal)}

    def sim(env, code, scan_d, halts):
        i = idx[scan_d]
        base = dict(stock_code=code, scan_date=scan_d)
        if i + 3 >= len(cal):
            return dict(base, status="no_next_day")
        d1 = cal[i + 1]
        if int(code) == 31 and i % 4 == 0:
            return dict(base, status="no_fill", entry_date=d1)
        if int(code) == 33 and i % 6 == 0:
            return dict(base, status="halt_entry", entry_date=d1)
        rng = np.random.default_rng([int(code), i])
        ret = (effect if (code, scan_d) in marks else 0.0) + float(rng.normal(0, 4))
        return dict(base, status="filled", fill="open", entry_date=d1, entry_price=10_000.0, exit_date=cal[i + 3],
                    exit_reason="sl", hold_days=2, ret_sl=ret, ret_tp=ret, both=False, unresolved=(i % 13 == 0),
                    halted_in_path=False, flags="")
    return sim


def _g(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)


def _commit(repo, msg):
    _g(repo, "add", "-A")
    _g(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", msg)


GATE = dict(rej_cr1=0.10, rej_2w=0.09, tool="cr1", reason="ok", n_valid=400, n_valid_2w=400, n_valid_min=380,
            sd_null=0.5, mean_se_cr1=0.5, rej_lo_cr1=0.05, mean_fake_n1=150.0, n_fake=400, n_skipped=0)
SURV = {"surv_i": 0.02, "n_i": 300, "surv_ii": 0.01, "n_ii": 2000,
        "breakdown_i": {c: 1 for c in SV.CLASSES}, "breakdown_ii": {c: 2 for c in SV.CLASSES}}


@pytest.mark.parametrize("effect, want", [(-4.0, "있음(−)"), (4.0, "역방향")])
def test_build_seal_open_end_to_end(monkeypatch, tmp_path, effect, want):
    repo = tmp_path / "repo"
    pkg = repo / "pkg"
    res = pkg / "results"
    res.mkdir(parents=True)
    _g(repo, "init", "-q")
    (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")
    (pkg / "frozen_consts.py").write_text("PREREG_FROZEN_BLOB = 'set'\n", encoding="utf-8")
    (res / "proxy_coef.json").write_text(json.dumps({"beta": [-20.0, 0.0, 2.0]}), encoding="utf-8")
    (res / "backfill_check.json").write_text(json.dumps(dict(
        complete=True, window=[S.FILING_START.isoformat(), S.SCAN_END.isoformat()], types=list(S.BACKFILL_TYPES))),
        encoding="utf-8")
    monkeypatch.setattr(S, "PKG", pkg)
    monkeypatch.setattr(S, "RESULTS", res)
    monkeypatch.setattr(S, "PREREG", pkg / "PREREG.md")
    (pkg / "PREREG.md").write_text("# 사전등록\n\n```pins\npkg/a.py " + RUN.blob(pkg / "a.py") + "\n```\n",
                                   encoding="utf-8")
    _commit(repo, "freeze")
    monkeypatch.setattr(FC, "PREREG_FROZEN_BLOB", RUN.blob(pkg / "PREREG.md"))
    monkeypatch.setattr(FC, "PROXY_COEF_MD5", RUN.md5(res / "proxy_coef.json"))
    monkeypatch.setattr(RUN, "required_pins", lambda root: ["pkg/a.py"])

    cal = _cal()
    cal_idx = {d: i for i, d in enumerate(cal)}
    px = _px(cal)
    scan_days = [d for d in cal if S.SCAN_START <= d <= S.SCAN_END]
    fil = _filings(cal, scan_days)
    marks = T.window_marks(fil, cal, 0)
    fp = {"sha256": "f" * 64, "per_stock": {_code(j): "0" * 32 for j in range(N_STOCK)}}
    monkeypatch.setattr(RUN, "_load_env", lambda conn: (cal, px, None))
    monkeypatch.setattr(RUN.T, "count_backfill_rows", lambda conn, a, b, t: S.BACKFILL_ROWS_EXPECTED)
    monkeypatch.setattr(RUN.T, "load_filings", lambda conn, a, b: list(fil))
    monkeypatch.setattr(RUN.U, "scan_window", lambda p, days: _scan_rows(cal_idx, days))
    monkeypatch.setattr(RUN.L, "simulate_candidate", _sim_factory(cal, marks, effect))
    monkeypatch.setattr(RUN.LD, "db_fingerprint", lambda conn, a, b: fp)
    monkeypatch.setattr(RUN.G, "fake_gate", lambda df: dict(GATE, n_real_marks=int((df["x"] == 1).sum())))
    monkeypatch.setattr(RUN, "_survivorship", lambda conn, p: SURV)

    # ── build ──
    RUN.stage_build(None)
    meta = json.loads((res / "build_meta.json").read_text(encoding="utf-8"))
    assert meta["normalize_counts"] == px.attrs["normalize_counts"]
    assert meta["per_stock"] == fp["per_stock"] and meta["n_backfill_rows"] == S.BACKFILL_ROWS_EXPECTED
    assert {"ledger_A.csv", "marks_lag0.csv", "marks_w5.csv", "marks_w20.csv", "marks_lag0_t1.csv",
            "marks_lag0_t2.csv", "marks_lag0_t3.csv"} <= set(meta["md5"])
    per = [RUN._read_marks(n) for n in RUN.TAG_MARKS]
    assert set().union(*per) == RUN._read_marks("lag0") == marks
    led = RUN._read_ledger()
    assert list(pd.read_csv(res / "ledger_A.csv", nrows=0).columns) == RUN.LEDGER_COLS
    ca = led[led["ca_path"]]
    assert len(ca) > 0 and set(ca["stock_code"]) <= {_code(j) for j in JUMPERS}
    assert not led.loc[led["status"] != "filled", "ca_path"].any()
    _commit(repo, "build")

    # ── seal ──
    RUN.stage_seal(None)
    seal = json.loads((res / "seal.json").read_text(encoding="utf-8"))
    assert seal["lib_versions"] == RUN.lib_versions() and seal["n1"] >= S.N1_MIN
    _commit(repo, "seal")

    # ── open ──
    RUN.stage_open(None)
    assert (res / "open.started").exists()
    out = json.loads((res / "open.json").read_text(encoding="utf-8"))
    assert {"label", "fe_sl", "fe_tp", "secondary", "per_tag", "ca_path", "aux", "opened", "git_sha"} <= set(out)
    assert out["label"] == want
    assert [t["tag"] for t in out["per_tag"]["tags"]] == list(S.TAGS_LAG0)
    assert all(0.0 <= t["p_holm"] <= 1.0 for t in out["per_tag"]["tags"]) and out["per_tag"]["tool_used"] == "cr1"
    assert out["per_tag"]["interpreted"] is (want == "있음(−)")
    cnt = out["ca_path"]["counts"]
    assert cnt["표식"]["ca_path"] > 0 and cnt["대조"]["ca_path"] > 0
    # 합성 설계상 표식은 하루 1행 → 표식 ca_path 로트를 빼면 그날이 통째로 빠져 n₁ 이 정확히 그만큼 준다(양 팔 대칭 제외)
    assert out["ca_path"]["fe_sl_excl"]["n1"] == out["fe_sl"]["n1"] - cnt["표식"]["ca_path"]
    assert set(out["aux"]) == {"no_fill", "unresolved"}
    assert out["aux"]["no_fill"]["대조"]["no_fill"] > 0 and out["aux"]["unresolved"]["대조"]["unresolved"] > 0
    assert {"w5", "w20", "all_sizes", "halt_entry"} <= set(out["secondary"])
    txts = list(res.glob("RESULTS_*.md"))
    assert len(txts) == 1
    txt = txts[0].read_text(encoding="utf-8")
    assert f"주 라벨: **{want}**" in txt and "태그별" in txt and "ca_path" in txt and "no_fill" in txt
    assert ("기여" in txt) is (want == "있음(−)") and ("해석 안 함" in txt) is (want != "있음(−)")
    with pytest.raises(SystemExit):                                           # 두 번째 개봉 거부
        RUN.stage_open(None)
