import pandas as pd
import pytest
from collectors.stock_market_collector import collect_stock_market


class FakeCursor:
    """params 가 없는 execute 는 규모 조회(SELECT)다 — 쓰기 sink 에 넣지 않는다."""
    def __init__(self, conn): self.conn = conn
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=None):
        if params is None:
            self.conn.selected = True
        else:
            self.conn.rows.append(params)
    def fetchall(self): return list(self.conn.existing.items())


class FakeConn:
    """existing=기존 적재 행수. 기본값 {} = 빈 테이블 = 규모 하한 미적용."""
    def __init__(self, existing=None):
        self.existing = dict(existing or {})
        self.rows = []; self.commits = 0; self.selected = False
    def cursor(self): return FakeCursor(self)
    def commit(self): self.commits += 1


def _listing(mapping):
    def fn(market):
        return pd.DataFrame({"Code": mapping[market]})
    return fn


def test_collect_writes_both_markets():
    conn = FakeConn()
    res = collect_stock_market(
        listing_fn=_listing({"KOSPI": ["005930"], "KOSDAQ": ["035720", "247540"]}),
        conn=conn,
    )
    assert res["KOSPI"] == 1
    assert res["KOSDAQ"] == 2
    assert res["overlap"] == 0
    assert {"stock_code": "005930", "market": "KOSPI"} in conn.rows
    assert {"stock_code": "247540", "market": "KOSDAQ"} in conn.rows


def test_collect_raises_when_a_market_is_empty():
    # 한쪽이 비면 조용한 수집 실패다 — 기존 매핑을 덮어쓰지 않고 즉시 실패시킨다
    conn = FakeConn()
    with pytest.raises(RuntimeError, match="KOSDAQ"):
        collect_stock_market(
            listing_fn=_listing({"KOSPI": ["005930"], "KOSDAQ": []}), conn=conn
        )
    assert conn.rows == []


def test_collect_raises_on_overlap():
    # 같은 코드가 양쪽에 있으면 라벨이 모순이다 — 쓰지 않는다
    conn = FakeConn()
    with pytest.raises(RuntimeError, match="교집합"):
        collect_stock_market(
            listing_fn=_listing({"KOSPI": ["005930"], "KOSDAQ": ["005930"]}), conn=conn
        )
    assert conn.rows == []
