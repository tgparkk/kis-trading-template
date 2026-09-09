# tests/collectors/test_index_freshness.py
"""지수 신선도 판정 — 순수 함수 (설계 §4).

배경 (2026-09-08~09): `collect_index` 가 FDR 이 돌려준 «옛 6봉»을 그대로 성공으로
세어 `index_daily`·`daily_prices` 가 09-07 에서 2거래일 멈췄는데도 로그·EOD 요약이
전부 정상이었다. 「N행 갱신」은 「오늘 것이 들어왔다」의 증거가 아니다.

여기서 고정하는 계약:
  1. cutoff — 장전 W1 훅이 07:40 에 넣는 «오늘 행» 때문에 정상인 지수가 매일 아침
     STALE 로 오탐하면 안 된다(설계 §4-1 실측: 09-08 78건 · 09-09 73건, 07:40:12).
  2. 축 A(상대)·축 B(절대)를 «따로» 판정한다 — 한 규칙의 두 축은 한 줄로 뭉치지 않는다.
  3. ref 를 못 구하면 「모른다」다 — 「안전」으로도 「고장」으로도 접지 않는다.
"""
from datetime import date, datetime

from collectors.index_writer import (
    check_index_freshness,
    evaluate_freshness,
    format_freshness_warning,
    freshness_cutoff,
    reference_trade_date,
)


# ────────────────────────── cutoff ──────────────────────────
def test_cutoff_before_confirm_time_is_yesterday():
    """07:40·15:35 = 오늘 봉 미확정 ⇒ cutoff 는 어제."""
    assert freshness_cutoff(datetime(2026, 9, 9, 7, 40)) == date(2026, 9, 8)
    assert freshness_cutoff(datetime(2026, 9, 9, 15, 35)) == date(2026, 9, 8)


def test_cutoff_at_and_after_confirm_time_is_today():
    """15:40 «정각»부터 오늘 봉을 확정으로 본다(경계 포함)."""
    assert freshness_cutoff(datetime(2026, 9, 9, 15, 40)) == date(2026, 9, 9)
    assert freshness_cutoff(datetime(2026, 9, 9, 15, 49)) == date(2026, 9, 9)


# ────────────────────────── D_ref ──────────────────────────
def test_reference_trade_date_ignores_rows_newer_than_cutoff():
    """🔴 07:40 오탐 회귀 — 오라클에 «오늘 행»이 섞여 있어도 D_ref 는 어제다.

    장전 W1 훅이 T 당일 07:40:1x 에 T 행을 73~78종목 넣는다. cutoff 가 없으면
    D_ref=T 가 되어 정상인 지수(T−1)가 매일 아침 STALE 로 오탐한다.
    """
    oracle = ["2026-09-09", "2026-09-08", "2026-09-09"]   # 오늘(09-09) 행이 섞여 있다
    assert reference_trade_date(oracle, datetime(2026, 9, 9, 7, 40)) == date(2026, 9, 8)


def test_reference_trade_date_after_cutoff_uses_today():
    oracle = ["2026-09-09", "2026-09-08"]
    assert reference_trade_date(oracle, datetime(2026, 9, 9, 15, 49)) == date(2026, 9, 9)


def test_reference_trade_date_none_when_no_oracle_rows():
    """오라클이 비면 「모른다」 — None 이지 「신선」이 아니다."""
    assert reference_trade_date([], datetime(2026, 9, 9, 15, 49)) is None
    assert reference_trade_date([None], datetime(2026, 9, 9, 15, 49)) is None


# ────────────────────────── 축 A (상대) ──────────────────────────
def _axes(recs):
    return sorted(r["axis"] for r in recs)


def test_axis_a_stale_when_index_lags_reference():
    recs = evaluate_freshness("KOSPI", "index_daily", date(2026, 9, 7), date(2026, 9, 9),
                              date(2026, 9, 9), "kis")
    assert _axes(recs) == ["A"]
    assert recs[0]["lag_days"] == 2 and recs[0]["src"] == "kis"
    assert recs[0]["table"] == "index_daily" and recs[0]["index"] == "KOSPI"


def test_axis_a_fresh_when_equal_or_ahead():
    """max == ref 는 정상. max > ref 도 정상 — 15:35 에 T 봉을 받으면 T > T−1 이다."""
    assert evaluate_freshness("KOSPI", "index_daily", date(2026, 9, 9), date(2026, 9, 9),
                              date(2026, 9, 9), "kis") == []
    assert evaluate_freshness("KOSPI", "index_daily", date(2026, 9, 9), date(2026, 9, 8),
                              date(2026, 9, 9), "kis") == []


def test_axis_a_skipped_when_reference_unknown():
    """ref 가 None(모른다)이면 축 A 는 판정하지 않는다 — 오탐도 오음도 만들지 않는다."""
    assert evaluate_freshness("KOSPI", "index_daily", date(2026, 9, 9), None,
                              date(2026, 9, 9), "kis") == []


# ────────────────────────── 축 B (절대) ──────────────────────────
def test_axis_b_boundary_five_days_is_fresh():
    """달력 5일 = 한계치 «이하» ⇒ 신선(주말·연휴 흡수)."""
    assert evaluate_freshness("KOSDAQ", "index_daily", date(2026, 9, 4), date(2026, 9, 4),
                              date(2026, 9, 9), "kis") == []


def test_axis_b_six_days_is_stale():
    recs = evaluate_freshness("KOSDAQ", "index_daily", date(2026, 9, 3), date(2026, 9, 3),
                              date(2026, 9, 9), "kis")
    assert _axes(recs) == ["B"]
    assert recs[0]["lag_days"] == 6


def test_both_axes_reported_separately():
    """🔑 두 축이 동시에 참이면 «2개»가 나온다 — 한 줄로 뭉치지 않는다."""
    recs = evaluate_freshness("KOSPI", "index_daily", date(2026, 9, 1), date(2026, 9, 9),
                              date(2026, 9, 9), "kis")
    assert _axes(recs) == ["A", "B"]


def test_missing_index_rows_fire_both_axes():
    """표에 그 지수 행이 하나도 없으면(=None) 두 축 모두 발화한다."""
    recs = evaluate_freshness("KOSPI", "index_daily", None, date(2026, 9, 9),
                              date(2026, 9, 9), "kis")
    assert _axes(recs) == ["A", "B"]
    assert all(r["lag_days"] is None for r in recs)


# ────────────────────────── 로그 표면 ──────────────────────────
def test_format_freshness_warning_shape():
    rec = evaluate_freshness("KOSPI", "index_daily", date(2026, 9, 7), date(2026, 9, 9),
                             date(2026, 9, 9), "kis")[0]
    assert format_freshness_warning(rec) == (
        "[index-freshness] STALE axis=A table=index_daily index=KOSPI "
        "max=2026-09-07 ref=2026-09-09 lag=2 src=kis"
    )


class _RecLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, msg, *args):
        self.warnings.append(msg % args if args else msg)


def test_check_index_freshness_warns_per_stale_axis():
    log = _RecLogger()
    stale = check_index_freshness(
        {"KOSPI": "2026-09-07", "KOSDAQ": "2026-09-09"},
        ["2026-09-09", "2026-09-09", "2026-09-08"],
        datetime(2026, 9, 9, 15, 49), "index_daily", "kis", log,
    )
    assert [r["index"] for r in stale] == ["KOSPI"]
    assert len(log.warnings) == 1 and log.warnings[0].startswith("[index-freshness] STALE axis=A")


def test_check_index_freshness_silent_when_all_fresh():
    log = _RecLogger()
    stale = check_index_freshness(
        {"KOSPI": "2026-09-09", "KOSDAQ": "2026-09-09"},
        ["2026-09-09"], datetime(2026, 9, 9, 15, 49), "index_daily", "kis", log,
    )
    assert stale == [] and log.warnings == []


def test_check_index_freshness_logs_unknown_when_no_oracle():
    """오라클을 못 읽으면 unknown 을 1줄 남긴다 — STALE 로 접지 않는다."""
    log = _RecLogger()
    stale = check_index_freshness(
        {"KOSPI": "2026-09-09", "KOSDAQ": "2026-09-09"},
        [], datetime(2026, 9, 9, 15, 49), "index_daily", "fdr", log,
    )
    assert stale == []
    assert len(log.warnings) == 1 and "unknown" in log.warnings[0]
