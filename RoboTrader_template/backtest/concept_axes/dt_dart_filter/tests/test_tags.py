from datetime import date

from backtest.concept_axes.dt_dart_filter import tags as T

CAL = [date(2023, 3, 6), date(2023, 3, 7), date(2023, 3, 8), date(2023, 3, 9), date(2023, 3, 10),
       date(2023, 3, 13), date(2023, 3, 14)]


def test_is_lag0_tag_accepts_three_tags():
    assert T.is_lag0_tag("주요사항보고서(유상증자결정)")
    assert T.is_lag0_tag("최대주주변경을수반하는주식양수도계약체결")
    assert T.is_lag0_tag("소송등의제기ㆍ신청(일반사항)")
    assert T.is_lag0_tag("횡령ㆍ배임혐의발생")


def test_is_lag0_tag_rejects_correction_subsidiary_other_and_mgmt_dispute():
    assert not T.is_lag0_tag("[기재정정]주요사항보고서(유상증자결정)")
    assert not T.is_lag0_tag("주요사항보고서(유상증자결정)(자회사의주요경영사항)")
    assert not T.is_lag0_tag("주요사항보고서(자기주식취득결정)")
    assert not T.is_lag0_tag("단일판매ㆍ공급계약체결")
    assert not T.is_lag0_tag("소송등의제기ㆍ신청(경영권분쟁소송)")
    assert not T.is_lag0_tag("")


def test_window_marks_lag0_same_trading_day_only():
    f = [("000001", date(2023, 3, 8), "주요사항보고서(유상증자결정)")]
    assert T.window_marks(f, CAL, 0) == {("000001", date(2023, 3, 8))}


def test_window_marks_weekend_filing_not_lag0_but_in_w5():
    f = [("000002", date(2023, 3, 11), "최대주주변경")]          # 토요일
    assert T.window_marks(f, CAL, 0) == set()
    w5 = T.window_marks(f, CAL, 4)
    assert ("000002", date(2023, 3, 13)) in w5 and ("000002", date(2023, 3, 14)) in w5
    assert ("000002", date(2023, 3, 10)) not in w5


def test_window_marks_ignores_non_tags_and_blank_codes():
    f = [("000003", date(2023, 3, 8), "주요사항보고서(자기주식취득결정)"),
         ("", date(2023, 3, 8), "주요사항보고서(유상증자결정)")]
    assert T.window_marks(f, CAL, 4) == set()


# ── critic B1 · 태그별 표식(only=) ───────────────────────────────────────────────
import pytest                                                    # noqa: E402

from backtest.concept_axes.dt_dart_filter import settings as S  # noqa: E402

RIGHTS, MAJOR, EMBEZ = "주요사항보고서(유상증자결정)", "최대주주변경을수반하는주식양수도계약체결", "횡령ㆍ배임혐의발생"


def test_is_lag0_tag_only_restricts_to_one_tag():
    t_rights, t_major, t_legal = S.TAGS_LAG0
    assert T.is_lag0_tag(RIGHTS, only=t_rights) and not T.is_lag0_tag(RIGHTS, only=t_major)
    assert T.is_lag0_tag(MAJOR, only=t_major) and not T.is_lag0_tag(MAJOR, only=t_legal)
    assert T.is_lag0_tag(EMBEZ, only=t_legal) and not T.is_lag0_tag(EMBEZ, only=t_rights)
    assert not T.is_lag0_tag("소송등의제기ㆍ신청(경영권분쟁소송)", only=t_legal)     # 경영권분쟁 제외 유지
    assert not T.is_lag0_tag("[기재정정]주요사항보고서(유상증자결정)", only=t_rights)  # 정정 제외 유지
    with pytest.raises(ValueError):
        T.is_lag0_tag(RIGHTS, only="경영권분쟁")


def test_window_marks_only_per_tag_sets_union_to_all_tags():
    f = [("000001", date(2023, 3, 8), RIGHTS), ("000002", date(2023, 3, 8), MAJOR),
         ("000003", date(2023, 3, 9), EMBEZ), ("000001", date(2023, 3, 8), EMBEZ),      # 같은 날 두 태그
         ("000004", date(2023, 3, 11), RIGHTS)]                                           # 토요일 = lag0 없음
    per = [T.window_marks(f, CAL, 0, only=t) for t in S.TAGS_LAG0]
    assert per[0] == {("000001", date(2023, 3, 8))}
    assert per[1] == {("000002", date(2023, 3, 8))}
    assert per[2] == {("000003", date(2023, 3, 9)), ("000001", date(2023, 3, 8))}
    assert set().union(*per) == T.window_marks(f, CAL, 0)
