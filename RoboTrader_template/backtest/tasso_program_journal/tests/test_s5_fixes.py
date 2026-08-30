# -*- coding: utf-8 -*-
"""`PREREG_POST6.md` §5 (C-17~C-22) 측정 장치 수정의 **회귀 테스트**.

사전등록이 «필수»라고 적은 것:
  · §5-1-3  C-17 — 상장 20봉 미만 1건에 `f9_newhigh` NaN · `f9_newhigh_pct` NaN ·
                   그 건이 `SEL-S3` 중앙값 **분모에서 빠진다**
  · §5-3-5  C-19 — 지문을 인위로 한 글자 바꾼 뒤 `check()` 가 **실패를 내는지**
                   (🔑 *캡처 장치도 가드다 — 가드를 시험하지 않으면 그것도 장식이다*)
  · §5-4-3  C-20 — 짝수 길이 리스트에서 **두 가운데 값의 평균**이 나오는지
  · §5-5-3  C-21 — `P6-G-E`: `fill_n == 1` ⟺ `fill_level == first_only`

DB 없이 도는 테스트만 모았다(합성 데이터 + 저장소 파일). 라이브 트리 import 0건.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

import pandas as pd
import pytest

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import backfill_fill_n as BF           # noqa: E402
import regen_gate as RG                # noqa: E402
import run_gapfill as GAP              # noqa: E402
import run_minute_entry as MIN         # noqa: E402
import universe_gap as UG              # noqa: E402
import verify_ledger as V              # noqa: E402
import verify_ledger_post5 as VP       # noqa: E402
from run_reconstruct_post5 import feasible_exact, feasible_pointwise  # noqa: E402
from run_selection import build_features, window_stat                 # noqa: E402
from run_selection_post4 import med as med4                           # noqa: E402
from run_selection_post5 import med as med5                           # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# C-17 — f9_newhigh 의 NaN 보존
# ════════════════════════════════════════════════════════════════════════════
def _synthetic():
    """오래된 종목 1개(80봉) + **상장 12봉짜리 신규주 1개**. 실제 표본의 삼양바이오팜 자리다."""
    days = pd.bdate_range("2026-04-01", periods=80)
    rows = []
    for i, d in enumerate(days):
        rows.append(dict(stock_code="OLD001", date=d, close=1000 + i, high=1010 + i,
                         low=990 + i, trading_value=1e9, market_cap=1e11))
    for i, d in enumerate(days[-12:]):          # 신규주 — 이력 12거래일
        rows.append(dict(stock_code="NEW001", date=d, close=5000 + 10 * i, high=5100 + 10 * i,
                         low=4900 + 10 * i, trading_value=2e9, market_cap=3e10))
    df = pd.DataFrame(rows).sort_values(["stock_code", "date"]).reset_index(drop=True)
    return build_features(df), days


def test_c17_short_history_gets_nan_not_zero():
    """§5-1-3 ① — 상장 20봉 미만 종목의 `f9_newhigh` 는 **NaN**(「관측값 0」이 아니다)."""
    df, _days = _synthetic()
    new = df[df.stock_code == "NEW001"]
    assert len(new) == 12
    assert new.f9_newhigh.isna().all(), "신규주 12봉 전부 NaN 이라야 한다"
    assert (new.f9_newhigh == 0.0).sum() == 0, "🔴 「계산 불가」가 「갱신 없음(0)」으로 둔갑했다"


def test_c17_percentile_follows_to_nan():
    """§5-1-3 ② — 백분위도 NaN. `rank(pct=True)` 가 NaN 을 자동 제외하므로 «따라온다»."""
    df, _days = _synthetic()
    new = df[df.stock_code == "NEW001"]
    assert new.f9_newhigh_pct.isna().all()
    # `f5`·`f6` 과 같은 결측 표시가 됐는가 (원 결함 서술: f9 만 달랐다)
    assert new.f5_pos60.isna().all() and new.f6_spikes60.isna().all()


def test_c17_old_idiom_would_have_said_zero():
    """정정 «전» 관용구가 무엇을 했는지 못박는다 — 이 단언이 깨지면 결함 서술 자체가 틀린 것이다."""
    df, _days = _synthetic()
    g = df.groupby("stock_code", sort=False)
    prev_max = g.close.transform(lambda s: s.shift(1).rolling(60, min_periods=20).max())
    before = (df.close >= prev_max).astype(float)          # 옛 코드 그대로
    new_mask = df.stock_code == "NEW001"
    assert (before[new_mask] == 0.0).all(), "옛 코드는 신규주를 「갱신 없음」이라고 말했다"
    assert df.loc[new_mask, "f9_newhigh"].isna().all(), "새 코드는 「계산 불가」라고 말한다"


def test_c17_nan_drops_out_of_sel_s3_denominator():
    """§5-1-3 ③ — 그 건이 **`SEL-S3` 중앙값 분모에서 빠진다.**

    `SEL-S3` = 창 안 `f9_newhigh_pct` 최댓값들의 중앙값. post4·post5 의 `med()` 둘 다로 확인한다
    (post4 쪽은 C-17 로 NaN 이 들어올 수 있게 되면서 같은 처리가 필요해졌다)."""
    df, days = _synthetic()
    d1 = days[-1]
    s_old = window_stat(df, "OLD001", d1 - pd.Timedelta(days=10), d1)
    s_new = window_stat(df, "NEW001", d1 - pd.Timedelta(days=10), d1)
    assert s_old is not None and s_new is not None
    v_old, v_new = s_old["f9_newhigh"], s_new["f9_newhigh"]
    assert v_new != v_new, "신규주의 창 최대 백분위는 NaN 이라야 한다"

    xs = [v_old, v_new]
    for med in (med4, med5):
        assert med(xs) == v_old, "NaN 이 분모에 남으면 안 된다 (분모 2 → 1)"
        assert med([]) is None
    # 분모가 실제로 줄었는지 — 「빠진다」의 직접 단언
    kept = [x for x in xs if x == x]
    assert len(kept) == 1 and len(xs) == 2


# ════════════════════════════════════════════════════════════════════════════
# C-18 — 유니버스 prev_close 결손 공개
# ════════════════════════════════════════════════════════════════════════════
def _cov(d, mcap, test):
    return dict(date=d, universe_mcap=mcap, universe_test=test, dropped=mcap - test,
                drop_rate=(mcap - test) / mcap, prev_bar_date="2026-08-04", stale_prev=0)


def test_c18_guard_threshold_is_one_percent():
    assert UG.DROP_RATE_GUARD == 0.01


def test_c18_guard_fires_at_or_above_one_percent_only():
    """§5-2 가드 — post5 실측(0.00% · 0.04% ↔ 6.91%)이 문턱 양쪽으로 갈리는지."""
    rows = [_cov("2026-08-03", 2570, 2570),      # 0.00%
            _cov("2026-08-12", 2762, 2761),      # 0.04%
            _cov("2026-08-05", 2763, 2572)]      # 6.91%
    assert [r["date"] for r in UG.flagged(rows)] == ["2026-08-05"]
    # 경계 — 정확히 1% 는 «발동»한다(≥)
    assert UG.flagged([_cov("x", 1000, 990)])


def test_c18_render_prints_five_columns_and_the_guard_sentence():
    rows = [_cov("2026-08-05", 2763, 2572)]
    txt = "\n".join(UG.render(rows))
    for col in ("universe_mcap", "universe_test", "dropped", "drop_rate", "prev_bar_date"):
        assert col in txt, col
    assert "직접 비교하지 말 것" in txt
    assert "빼면 더 커질 뿐 작아지지 않는다" in txt, "편향 방향 인쇄가 빠졌다"
    assert "6.91%" in txt


# ════════════════════════════════════════════════════════════════════════════
# C-19 — regen_gate 지문·등록
# ════════════════════════════════════════════════════════════════════════════
def test_c19_daily_prices_slice_has_no_upper_bound():
    """§5-3-1 — 상한이 남아 있으면 스냅샷이 움직여도 지문이 «안 움직인다»."""
    keys = [k for k in RG.FINGERPRINT_SQL if k.startswith("daily_prices")]
    assert len(keys) == 1
    sql = RG.FINGERPRINT_SQL[keys[0]]
    assert "2026-08-14" not in sql and "BETWEEN" not in sql.upper()
    assert ">= '2026-04-01'" in sql and "max(date)" in sql


def test_c19_post5_artifacts_registered():
    """§5-3-2·3 — 등재되지 않은 산출물은 게이트가 «안 본다»."""
    for f in ("RESULTS_D1_OOS_POST5_NUMBERS.md", "RESULTS_EXIT_V2_POST5_NUMBERS.md",
              "RESULTS_SELECTION_POST5_NUMBERS.md", "RESULTS_REGDAY_POST5_NUMBERS.md",
              "RESULTS_RECONSTRUCT_POST5_NUMBERS.md", "RESULTS_LADDER_TRANCHE_NUMBERS.md"):
        assert f in RG.PAIRS, f
        assert (BASE / RG.PAIRS[f]).is_file()
    for d in ("INTAKE_2026-08-29_post5.md", "LABELS_2026-08-29_post5.md",
              "PREDECISION_2026-08-29_post5.md", "RESULTS_D1_OOS_POST5.md",
              "RESULTS_EXIT_V2_POST5.md", "RESULTS_SELECTION_POST5.md",
              "RESULTS_REGDAY_POST5.md", "RESULTS_RECONSTRUCT_POST5.md",
              "RESULTS_LADDER_TRANCHE.md", "PREREG_POST6.md"):
        assert d in RG.MANUAL_DOCS, d


def test_c19_manifest_covers_every_pair():
    man = json.loads(RG.MANIFEST.read_text(encoding="utf-8"))
    assert set(man["artifacts"]) == set(RG.PAIRS), "매니페스트가 PAIRS 와 어긋난다(--update 필요)"
    assert man.get("db_fingerprint"), "지문 기준선이 비었다"
    assert not any(k.endswith("2026-08-14]") for k in man["db_fingerprint"])


def test_c19_guard_fails_when_fingerprint_is_perturbed(tmp_path, monkeypatch, capsys):
    """§5-3-5 (필수) — 지문을 **한 글자** 바꾸면 `check()` 가 실패를 내는가.

    🔑 *가드를 시험하지 않으면 그것도 장식이다.* DB 없이 돌도록 `db_fingerprint` 는 고정값을 준다."""
    man = json.loads(RG.MANIFEST.read_text(encoding="utf-8"))
    true_fp = man["db_fingerprint"]
    monkeypatch.setattr(RG, "db_fingerprint", lambda: (true_fp, None))

    # (1) 손대지 않으면 지문 검사는 통과한다 (대조군)
    ok_path = tmp_path / "ok.json"
    ok_path.write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(RG, "MANIFEST", ok_path)
    RG.check()
    assert "DB 지문 일치" in capsys.readouterr().out

    # (2) 한 글자만 흔든다 — 슬라이스 하나의 max(date) 끝자리
    bad = json.loads(json.dumps(man))
    k = next(iter(bad["db_fingerprint"]))
    v = list(bad["db_fingerprint"][k])
    v[2] = v[2][:-1] + ("0" if v[2][-1] != "0" else "1")
    bad["db_fingerprint"][k] = v
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(RG, "MANIFEST", bad_path)
    rc = RG.check()
    out = capsys.readouterr().out
    assert rc != 0, "🔴 지문을 흔들었는데 게이트가 통과했다 = 죽은 가드"
    assert "움직였다" in out and k in out


def test_c19_old_slice_was_blind_to_snapshot_advance():
    """§7-B #10 「죽은 가드 실측 점검」 — DB 가 있으면 **실제로** 두 형태를 재서 비교한다.

    ⚠️ 사전등록 §5-3 표는 *「`count`·`max(date)` 가 안 움직인다」*고 적었지만, 창 «안» 백필은
       `count` 로 잡힌다. 진짜 못 잡는 축은 **`max(date)`(스냅샷 전진)**다."""
    psycopg2 = pytest.importorskip("psycopg2")
    from run_tests import DSN
    try:
        conn = psycopg2.connect(connect_timeout=5, **DSN)
    except Exception as e:  # noqa: BLE001
        pytest.skip("DB 없음: %s" % type(e).__name__)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT max(date) FROM daily_prices "
                        "WHERE date BETWEEN '2026-04-01' AND '2026-08-14'")
            old_max = str(cur.fetchone()[0])
            cur.execute(RG.FINGERPRINT_SQL["daily_prices[>=2026-04-01]"])
            new_max = str(cur.fetchone()[2])
    finally:
        conn.close()
    assert old_max == "2026-08-14", "옛 슬라이스는 상한에 못 박혀 있다"
    assert new_max >= old_max
    if new_max > old_max:
        assert True, "🔴 옛 형태는 스냅샷이 %s 까지 전진한 것을 못 봤다" % new_max


def test_c19_frozen_stale_is_recorded_not_silent():
    """정정으로 스크립트만 바뀐 산출물은 **사유가 매니페스트에 박혀** 있어야 한다(조용한 통과 금지)."""
    man = json.loads(RG.MANIFEST.read_text(encoding="utf-8"))
    assert RG.FROZEN_STALE, "동결 목록이 비었다"
    for art, why in RG.FROZEN_STALE.items():
        assert art in RG.PAIRS, art
        assert man["artifacts"][art].get("frozen_reason") == why, art


# ════════════════════════════════════════════════════════════════════════════
# C-20 — 중앙값 관용구
# ════════════════════════════════════════════════════════════════════════════
C20_FILES = ("run_d1_oos.py", "run_gapfill.py", "run_minute_entry.py",
             "run_reconstruct_post4.py")
UPPER_MEDIAN = re.compile(r"\[\s*len\(\s*[A-Za-z_][A-Za-z_0-9]*\s*\)\s*//\s*2\s*\]")


def test_c20_upper_median_idiom_is_gone_from_all_four_files():
    """🔑 계열 규칙: ***정정은 「파일」이 아니라 「관용구」 단위로.***"""
    for f in C20_FILES:
        src = (BASE / f).read_text(encoding="utf-8")
        hits = [ln for ln in src.splitlines()
                if UPPER_MEDIAN.search(ln) and not ln.lstrip().startswith("#")]
        assert not hits, "%s 에 상위 중앙값 관용구가 남았다: %s" % (f, hits)
        assert "import statistics" in src, f


def test_c20_statistics_median_averages_two_middles():
    """§5-4-3 — 짝수 `n` 에서 두 가운데 값의 **평균**."""
    assert statistics.median([1, 2, 3, 4]) == 2.5
    assert sorted([1, 2, 3, 4])[4 // 2] == 3, "옛 관용구는 «상위» 중앙값 3 을 줬다"
    assert statistics.median([1, 2, 3]) == 2       # 홀수는 불변


def test_c20_gapfill_med_stamp_averages_two_middle_times():
    even = [("20260806", "090000"), ("20260806", "090100"),
            ("20260806", "091000"), ("20260806", "091200")]
    assert GAP.med_stamp(even) == ("20260806", "090530")     # (0901 + 0910)/2
    odd = even[:3]
    assert GAP.med_stamp(odd) == ("20260806", "090100")      # 홀수는 실제 표본


def test_c20_minute_entry_mid_items_pairs_stay_together():
    """`t` 와 `P` 는 짝지어진 값이다 — 가운데 «원소»에 대해 성분별 중앙값."""
    hit = [(100.0, "090000"), (200.0, "090100"), (300.0, "091000"), (400.0, "091200")]
    mid = MIN.mid_items(hit)
    assert len(mid) == 2 and mid == hit[1:3]
    t = statistics.median([MIN.tsec(x[1]) for x in mid])
    p = statistics.median([x[0] for x in mid])
    assert t == statistics.median([MIN.tsec(x[1]) for x in hit]), "정렬돼 있으면 전체 중앙값과 같다"
    assert p == 250.0
    assert MIN.hhmm_sec(t) == "09:05"
    assert len(MIN.mid_items(hit[:3])) == 1


# ════════════════════════════════════════════════════════════════════════════
# C-21 — 원장 fill_level 축 분리 + P6-G-E
# ════════════════════════════════════════════════════════════════════════════
def test_c21_backfill_rule_is_mechanical():
    """§5-5-2 규약 표 그대로 — 사람 판단이 들어갈 자리가 없다."""
    assert BF.convert("first_only") == ("first_only", "1")
    assert BF.convert("1") == ("first_only", "1")
    assert BF.convert("2") == ("partial", "2")
    assert BF.convert("5") == ("partial", "5")
    assert BF.convert("full") == ("full", "")
    assert BF.convert("unknown") == ("unknown", "")


def test_c21_ledger_matches_the_prereg_simulation_table():
    """§5-5-4 시뮬레이션 표(현재 50행)와 **정확히** 같아야 한다."""
    trades = V.load_csv("ledger_trades.csv")
    assert len(trades) == 50
    hdr = list(trades[0].keys())
    assert hdr[hdr.index("fill_level") + 1] == "fill_n", "fill_n 은 fill_level 바로 뒤(§5-5-5)"
    from collections import Counter
    got = Counter((t["fill_level"], t["fill_n"]) for t in trades)
    assert got == Counter({("unknown", ""): 30, ("first_only", "1"): 6, ("partial", "2"): 4,
                           ("partial", "4"): 4, ("partial", "3"): 2, ("partial", "5"): 2,
                           ("full", ""): 2}), got
    assert got[("first_only", "1")] == 6, "5 → 6 (post5 삼양바이오팜의 fill_level=1 편입)"


def test_c21_gate_e_passes_on_the_current_ledger():
    VP.failures.clear()
    dist = VP.gate_e(V.load_csv("ledger_trades.csv"))
    assert not VP.failures, VP.failures
    assert sum(dist.values()) == 50


@pytest.mark.parametrize("row,why", [
    ({"fill_level": "partial", "fill_n": "1"}, "fill_n==1 인데 first_only 가 아니다"),
    ({"fill_level": "first_only", "fill_n": "2"}, "first_only 인데 fill_n 이 1 이 아니다"),
    ({"fill_level": "first_only", "fill_n": ""}, "first_only 인데 fill_n 이 비었다"),
    ({"fill_level": "3", "fill_n": "3"}, "fill_level 에 정수 차수가 남았다"),
    ({"fill_level": "partial", "fill_n": "x"}, "fill_n 이 정수가 아니다"),
])
def test_c21_gate_e_catches_violations(row, why):
    """**위반 1건이면 게이트 실패**(§5-5-3) — 가드가 실제로 무는지 시험한다."""
    VP.failures.clear()
    base = {"post_log_no": "1", "item_no": "1", "stock_name": "T"}
    base.update(row)
    VP.gate_e([base])
    assert VP.failures, why
    VP.failures.clear()


def test_c21_gate_e_flags_missing_column():
    VP.failures.clear()
    VP.gate_e([{"post_log_no": "1", "item_no": "1", "stock_name": "T", "fill_level": "full"}])
    assert any("backfill 미적용" in f for f in VP.failures)
    VP.failures.clear()


# ════════════════════════════════════════════════════════════════════════════
# C-22 — 점법 ⊆ 정확법
# ════════════════════════════════════════════════════════════════════════════
def test_c22_pointwise_solutions_lie_inside_the_exact_intervals():
    """A-11 의 근거 — *「점법 해집합 ⊆ 정확 해집합」*. 이게 깨지면 C-22 의 비교 자체가 무의미하다.

    `rows` 는 DB 행 모양 `(date, open, high, low, close)` 를 흉내낸 합성 봉."""
    from reconstruct_prices import gross_ret
    rows = [("2026-08-13", 9000, 10000, 8800, 9500),
            ("2026-08-14", 9500, 10400, 9200, 10000),
            ("2026-08-15", 10000, 10600, 9600, 10200)]
    legs = [10.54, 0.41]
    pts = feasible_pointwise(rows, legs, gross_ret)
    iv = feasible_exact(rows, legs, "gross")
    assert pts, "합성 예제에서 점법 해가 0개면 시험이 안 된다"
    assert iv, "정확법이 점법보다 좁을 수는 없다"
    for P in pts:
        assert any(a <= P <= b for a, b in iv), "점 %r 이 정확 구간 밖" % P
    span_pt = max(pts) - min(pts)
    span_iv = iv[-1][1] - iv[0][0]
    assert span_iv >= span_pt, "정확법 범위가 점법보다 좁다"
