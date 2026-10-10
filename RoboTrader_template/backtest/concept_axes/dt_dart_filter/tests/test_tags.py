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
