import pandas as pd
from collectors.index_writer import (
    fdr_df_to_index_rows,
    kis_df_to_index_rows,
    upsert_index_reconciliation,
)


def test_fdr_df_to_index_rows_maps_and_formats_date():
    df = pd.DataFrame(
        {"Open": [2500.0], "High": [2520.0], "Low": [2490.0], "Close": [2510.0], "Volume": [1.0e9]},
        index=pd.to_datetime(["2026-06-23"]),
    )
    rows = fdr_df_to_index_rows("KOSPI", df)
    assert rows == [{
        "index_code": "KOSPI", "date": "2026-06-23",
        "open": 2500.0, "high": 2520.0, "low": 2490.0, "close": 2510.0, "volume": 1.0e9,
    }]


def test_fdr_df_to_index_rows_empty():
    assert fdr_df_to_index_rows("KOSPI", pd.DataFrame()) == []


# ─────────────── KIS 업종 일봉 → index_daily 행 (2026-09-10 전환) ───────────────
# 필드 이름은 2026-09-10 프로브 «실측» 이다 — scratchpad/index_kis_probe/RESULT.md §2.
def _kis_df(rows):
    return pd.DataFrame(rows)


def _kis_row(d="20260907", o="6900.00", h="6995.40", low="6867.91", c="6995.39", vol="240446"):
    return {"stck_bsop_date": d, "bstp_nmix_oprc": o, "bstp_nmix_hgpr": h,
            "bstp_nmix_lwpr": low, "bstp_nmix_prpr": c, "acml_vol": vol}


def test_kis_df_to_index_rows_maps_and_formats_date():
    rows = kis_df_to_index_rows("KOSPI", _kis_df([_kis_row()]))
    assert rows == [{
        "index_code": "KOSPI", "date": "2026-09-07",
        "open": 6900.0, "high": 6995.40, "low": 6867.91, "close": 6995.39,
        "volume": 240446000.0,
    }]


def test_kis_volume_unit_is_thousand_shares():
    """🔑 KIS `acml_vol` 은 «천 주» 단위다 — ×1000 해야 기존 단위(FDR)와 이어진다.

    실측(09-07 KOSPI): KIS 240,446 vs FDR/DB 240,446,154 ⇒ 반올림 오차 154주 (≤ 999).
    """
    rows = kis_df_to_index_rows("KOSPI", _kis_df([_kis_row(vol="240446")]))
    assert rows[0]["volume"] == 240446 * 1000
    assert abs(rows[0]["volume"] - 240446154) <= 999


def test_kis_df_to_index_rows_empty():
    assert kis_df_to_index_rows("KOSPI", pd.DataFrame()) == []
    assert kis_df_to_index_rows("KOSPI", None) == []


def test_kis_df_to_index_rows_is_order_agnostic():
    """KIS 응답은 최신순이다 — 정렬이 뒤집혀도 행 «집합»은 같아야 한다."""
    a = _kis_row(d="20260907", c="6995.39")
    b = _kis_row(d="20260904", c="6687.21")
    asc = kis_df_to_index_rows("KOSPI", _kis_df([b, a]))
    desc = kis_df_to_index_rows("KOSPI", _kis_df([a, b]))
    assert sorted(asc, key=lambda r: r["date"]) == sorted(desc, key=lambda r: r["date"])


def test_kis_and_fdr_rows_share_the_same_schema():
    """두 소스가 «같은 계약»을 낸다 — 키 집합이 어긋나면 UPSERT 파라미터가 깨진다."""
    kis = kis_df_to_index_rows("KOSPI", _kis_df([_kis_row()]))[0]
    fdr = fdr_df_to_index_rows("KOSPI", pd.DataFrame(
        {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1.0]},
        index=pd.to_datetime(["2026-09-07"]),
    ))[0]
    assert set(kis) == set(fdr)


# ─────────────── collection_reconciliation(dataset='index') ───────────────
class _FakeCursor:
    def __init__(self, sink):
        self.sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.sink.append((sql, params))


class _FakeConn:
    def __init__(self):
        self.executed = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _FakeCursor(self.executed)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_upsert_index_reconciliation_shape():
    """dataset='index' · ISO 날짜 · value_match_rate 는 «NULL»(대조할 2차 소스가 없다)."""
    conn = _FakeConn()
    upsert_index_reconciliation(conn, "2026-09-10", 6, 0, 6, 1.0, "PASS")
    sql, params = conn.executed[0]
    assert "collection_reconciliation" in sql and "'index'" in sql
    assert params == ("2026-09-10", 6, 0, 6, None, 1.0, "PASS")
    assert conn.commits == 1 and conn.rollbacks == 0


def test_upsert_index_reconciliation_rolls_back_and_raises():
    class _Boom(_FakeConn):
        def cursor(self):
            raise RuntimeError("db down")

    conn = _Boom()
    try:
        upsert_index_reconciliation(conn, "2026-09-10", 6, 0, 6, 1.0, "PASS")
    except RuntimeError:
        pass
    else:  # pragma: no cover - 계약 위반
        raise AssertionError("예외가 삼켜졌다")
    assert conn.rollbacks == 1


def test_kis_df_to_index_rows_drops_zero_close_bars():
    """🔴 종가 0/빈 칸 봉은 버린다 (리뷰 rev1 🟡-5).

    KIS 는 장 시작 «전»에도 T 라벨 봉을 준다(07:40:2x 에 T 로 찍힌 daily_prices 행이
    매 거래일 31~36건 — 2026-09-10 리뷰 실측). 미확정 칸은 빈 문자열이라 `_num` 이 0.0 으로
    접는데, 그대로 두면 표의 max 가 T 가 되어 신선도 두 축이 «무조건 PASS» 가 된다.
    지수 종가 0 은 유효값이 아니다.
    """
    rows = kis_df_to_index_rows("KOSPI", _kis_df([
        _kis_row(d="20260910", c=""),        # 07:40 미확정 봉
        _kis_row(d="20260909", c="0"),       # 명시적 0
        _kis_row(d="20260908", c="6954.52"),
    ]))
    assert [r["date"] for r in rows] == ["2026-09-08"]
    assert rows[0]["close"] == 6954.52
