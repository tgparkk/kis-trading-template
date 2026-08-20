"""adj_repair 순수 함수 — DB·KIS 에 붙지 않는다."""
from collectors.adj_repair import derive_factors, build_repair_rows, needs_repair, fetch_both


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


def test_ohlc_comes_from_adjusted_feed_volume_from_raw_feed():
    """🔴 컬럼별 출처를 섞지 않는다 — OHLC=조정, volume=원본."""
    raw = {"2026-05-29": (750, 770, 740, 760, 357326)}
    adj = {"2026-05-29": (3750, 3850, 3700, 3800, 71465)}
    rows = build_repair_rows("054940", raw, adj, {"2026-05-29": 0.2})
    r = rows[0]
    assert (r["open"], r["high"], r["low"], r["close"]) == (3750.0, 3850.0, 3700.0, 3800.0)
    assert r["volume"] == 357326          # 원본
    assert r["adj_factor"] == 0.2
    assert r["stock_code"] == "054940" and r["date"] == "2026-05-29"


def test_row_without_factor_is_dropped():
    raw = {"2026-05-29": (0, 0, 0, 760, 100), "2026-05-30": (0, 0, 0, 770, 100)}
    adj = {"2026-05-29": (0, 0, 0, 3800, 20), "2026-05-30": (0, 0, 0, 3850, 20)}
    rows = build_repair_rows("X", raw, adj, {"2026-05-29": 0.2})
    assert [r["date"] for r in rows] == ["2026-05-29"]


def test_already_correct_rows_are_skipped():
    """멱등 — 가격이 이미 조정본이면 건드리지 않는다."""
    new = [{"stock_code": "A", "date": "2026-05-29", "open": 3750.0, "high": 3850.0,
            "low": 3700.0, "close": 3800.0, "volume": 357326, "adj_factor": 0.2}]
    db_same = {"2026-05-29": (3750.0, 3850.0, 3700.0, 3800.0, 357326, 0.2)}
    assert needs_repair(db_same, new) == []


def test_wrong_factor_alone_still_triggers_repair():
    """🔴 가격이 맞아도 계수가 틀리면 고쳐야 한다 — 004710 형태(큐가 못 잡는 부류)."""
    new = [{"stock_code": "A", "date": "2026-05-29", "open": 3750.0, "high": 3850.0,
            "low": 3700.0, "close": 3800.0, "volume": 357326, "adj_factor": 0.2}]
    db_badfactor = {"2026-05-29": (3750.0, 3850.0, 3700.0, 3800.0, 357326, 5.0)}
    assert len(needs_repair(db_badfactor, new)) == 1


def test_fetch_both_requests_raw_and_adjusted_and_keys_by_iso_date():
    calls = []

    def fake(code, start, end, adj_prc):
        calls.append(adj_prc)
        px = 760 if adj_prc == "1" else 3800
        vol = 357326 if adj_prc == "1" else 71465
        return [{"stck_bsop_date": "20260529", "stck_oprc": px, "stck_hgpr": px,
                 "stck_lwpr": px, "stck_clpr": px, "acml_vol": vol}]

    raw, adj = fetch_both("054940", "20210101", "20260820", fake)
    assert sorted(calls) == ["0", "1"]
    assert raw["2026-05-29"][3] == 760.0
    assert adj["2026-05-29"][3] == 3800.0


def test_rows_with_bad_date_or_nonpositive_close_are_dropped():
    def fake(code, start, end, adj_prc):
        return [{"stck_bsop_date": "2026", "stck_clpr": 100, "acml_vol": 1},
                {"stck_bsop_date": "20260529", "stck_clpr": 0, "acml_vol": 1},
                {"stck_bsop_date": "20260530", "stck_oprc": 10, "stck_hgpr": 10,
                 "stck_lwpr": 10, "stck_clpr": 10, "acml_vol": 5}]

    raw, adj = fetch_both("X", "1", "2", fake)
    assert list(raw) == ["2026-05-30"]
