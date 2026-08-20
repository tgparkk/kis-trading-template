"""adj_repair 순수 함수 — DB·KIS 에 붙지 않는다."""
from collectors.adj_repair import derive_factors


def _row(close, vol):
    return (close, close, close, close, vol)


def test_factor_is_adj_over_raw_not_the_inverse():
    """🔴 방향 고정 — 054940 실측(2026-05-29 raw vol 357,326 / adj vol 71,465).

    저장 규약은 adj_close = raw_close / adj_factor 이고 읽기 계층은 volume * adj_factor 다.
    따라서 factor = vol_adj / vol_raw = 0.2 여야 한다. 5.0 이면 25배 틀린다.
    """
    raw = {"2026-05-29": _row(760, 357326)}
    adj = {"2026-05-29": _row(3800, 71465)}
    f, diag = derive_factors(raw, adj)
    # NOTE(agent deviation): brief used tolerance 1e-9, but 71465/357326 == 0.19999944...
    # (integer-rounded real volumes can't divide to exactly 0.2). Widened to 1e-4 —
    # still 3+ orders of magnitude tighter than the 0.2-vs-5.0 direction distinction
    # this test exists to pin. See task-A-report.md.
    assert abs(f["2026-05-29"] - 0.2) < 1e-4
    assert diag["n_derived"] == 1


def test_zero_volume_day_is_filled_from_neighbour_with_same_factor():
    """거래정지 패딩(vol=0)은 계수를 못 구한다 → 같은 값을 가진 이웃에서 채운다."""
    raw = {"2026-08-10": _row(760, 1000), "2026-08-11": _row(760, 0),
           "2026-08-12": _row(3815, 2000)}
    adj = {"2026-08-10": _row(3800, 200), "2026-08-11": _row(3800, 0),
           "2026-08-12": _row(3815, 2000)}
    f, diag = derive_factors(raw, adj)
    assert abs(f["2026-08-10"] - 0.2) < 1e-9
    assert abs(f["2026-08-12"] - 1.0) < 1e-9
    assert abs(f["2026-08-11"] - 0.2) < 1e-9   # 이전 유효값(같은 구간)
    assert diag["n_zero_vol"] == 1 and diag["n_filled"] == 1


def test_no_derivable_factor_returns_empty_and_flags():
    """계수를 하나도 못 구하면 «빈 결과» 다 — 1.0 으로 때우지 않는다(fail-closed)."""
    raw = {"2026-08-11": _row(760, 0)}
    adj = {"2026-08-11": _row(3800, 0)}
    f, diag = derive_factors(raw, adj)
    assert f == {}
    assert diag["n_derived"] == 0


def test_date_present_in_only_one_feed_is_skipped():
    raw = {"2026-05-29": _row(760, 100), "2026-05-30": _row(770, 100)}
    adj = {"2026-05-29": _row(3800, 20)}
    f, diag = derive_factors(raw, adj)
    assert set(f) == {"2026-05-29"}
    assert diag["n_dates"] == 1
