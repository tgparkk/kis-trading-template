"""시장 매핑 수집기 규모 하한 — 급락게이트 `auto` 활성화 선행조건 ③.

기존 가드는 **완전 0건만** 차단했다(`collect_stock_market:41-42`). FDR 이
943건 대신 20건을 주면 성공으로 기록되고, 그중 오라벨이 정상 라벨을
덮어쓴다. 교집합 검사는 **같은 실행 안의 중복**만 잡으므로 이걸 못 본다.

🔴 이 프로젝트에서 급락보호가 실제로 약해질 수 있는 유일한 물리 경로다.
   (①② 는 전부 "both" 폴백 = 보호 과잉 쪽 실패라 무방비를 만들지 않는다.)

⚠️ DB·네트워크 미접촉: 상장목록은 `listing_fn` 스텁, DB 는 `FakeConn` 이다.
   `_default_listing`(FDR)·`KisDbConnection` 는 이 파일에서 한 번도 불리지
   않으며, `test_no_write_happens_before_floor_check` 가 그것을 단언한다.
"""
import pandas as pd
import pytest

from collectors.stock_market_collector import MIN_SCALE_RATIO, collect_stock_market

# 2026-08-03 실측(kis_template.stock_market)
LIVE_COUNTS = {"KOSPI": 943, "KOSDAQ": 1820}


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        if params is None:  # 규모 조회(SELECT) — 쓰기가 아니다
            self.conn.selects += 1
            self._result = [(m, n) for m, n in self.conn.existing.items()]
        else:
            self.conn.rows.append(params)

    def fetchall(self):
        return list(getattr(self, "_result", []))


class FakeConn:
    """기존 행수(existing)를 갖는 DB 스텁. 쓰기는 rows 에만 쌓인다."""

    def __init__(self, existing=None):
        self.existing = dict(existing or {})
        self.rows = []
        self.commits = 0
        self.selects = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def _listing(mapping):
    def fn(market):
        return pd.DataFrame({"Code": mapping[market]})
    return fn


def _codes(prefix, n):
    return [f"{prefix}{i:04d}" for i in range(n)]


def _full_listing(kospi_n, kosdaq_n):
    return _listing({
        "KOSPI": _codes("10", kospi_n),
        "KOSDAQ": _codes("20", kosdaq_n),
    })


# =========================================================================
# 하한 미달은 한 행도 쓰지 않는다
# =========================================================================

def test_partial_kospi_listing_is_rejected_without_writing():
    """FDR 이 943건 대신 20건을 줘도 성공으로 기록되면 안 된다."""
    conn = FakeConn(existing=LIVE_COUNTS)
    with pytest.raises(RuntimeError, match="규모"):
        collect_stock_market(listing_fn=_full_listing(20, 1820), conn=conn)
    assert conn.rows == [], "거부 시 기존 매핑을 한 행도 건드리면 안 된다"
    assert conn.commits == 0


def test_partial_kosdaq_listing_is_rejected():
    conn = FakeConn(existing=LIVE_COUNTS)
    with pytest.raises(RuntimeError, match="규모"):
        collect_stock_market(listing_fn=_full_listing(943, 300), conn=conn)
    assert conn.rows == []


def test_floor_is_per_market_not_aggregate():
    """합계로 걸면 한쪽이 통째로 붕괴해도 다른 쪽이 가려준다.

    KOSPI 100건(하한 754 미달) + KOSDAQ 2600건 ⇒ 합계 2700 은 기존 2763 의
    97.7% 라 합계 기준으로는 통과해버린다. 시장별로 걸어야 잡힌다.
    """
    conn = FakeConn(existing=LIVE_COUNTS)
    with pytest.raises(RuntimeError, match="KOSPI"):
        collect_stock_market(listing_fn=_full_listing(100, 2600), conn=conn)
    assert conn.rows == []


def test_no_write_happens_before_floor_check():
    """검증이 첫 UPSERT 보다 먼저다 — 부분 오염 자체가 불가능해야 한다.

    KOSPI 는 하한을 통과하고 KOSDAQ 만 미달인 경우, 순서가 잘못돼 있으면
    KOSPI 943행이 이미 쓰인 뒤에 예외가 난다.
    """
    conn = FakeConn(existing=LIVE_COUNTS)
    with pytest.raises(RuntimeError, match="KOSDAQ"):
        collect_stock_market(listing_fn=_full_listing(943, 100), conn=conn)
    assert conn.rows == []
    assert conn.selects >= 1, "기존 규모를 읽지 않았다면 하한을 걸 수 없다"


def test_rejection_message_names_market_and_counts():
    """거부는 보여야 한다 — 사유에 시장·수집분·기존 규모가 드러날 것."""
    conn = FakeConn(existing=LIVE_COUNTS)
    with pytest.raises(RuntimeError) as ei:
        collect_stock_market(listing_fn=_full_listing(20, 1820), conn=conn)
    msg = str(ei.value)
    assert "KOSPI" in msg and "20" in msg and "943" in msg


# =========================================================================
# 통과해야 하는 경우
# =========================================================================

def test_normal_collection_passes_floor():
    """정상 규모(실측값 그대로)는 통과한다."""
    conn = FakeConn(existing=LIVE_COUNTS)
    res = collect_stock_market(listing_fn=_full_listing(943, 1820), conn=conn)
    assert res["KOSPI"] == 943 and res["KOSDAQ"] == 1820
    assert len(conn.rows) == 2763


def test_natural_attrition_passes_floor():
    """자연 감소(상폐)로는 하한을 칠 수 없어야 한다.

    2026-07-01~08-03 실측 이탈률 0.272%/월(2,578종목 중 7종목). 연 환산
    약 3.2% 로, 20% 문턱까지는 6년 이상이 걸린다. 여기서는 1년치보다도
    보수적으로 5% 감소를 넣어 통과를 확인한다.
    """
    conn = FakeConn(existing=LIVE_COUNTS)
    res = collect_stock_market(listing_fn=_full_listing(896, 1729), conn=conn)  # -5%
    assert res["KOSPI"] == 896 and res["KOSDAQ"] == 1729


def test_just_above_floor_passes():
    """하한 바로 위(floor+1)는 통과한다.

    ⚠️ 이건 **경계 자체가 아니다** — floor+1 은 `<` 든 `<=` 든 똑같이 통과한다.
       진짜 경계는 아래 `test_exact_floor_boundary_passes` 가 밟는다.
    """
    conn = FakeConn(existing=LIVE_COUNTS)
    floor_kospi = int(943 * MIN_SCALE_RATIO)      # 754
    floor_kosdaq = int(1820 * MIN_SCALE_RATIO)    # 1456
    res = collect_stock_market(
        listing_fn=_full_listing(floor_kospi + 1, floor_kosdaq + 1), conn=conn)
    assert res["KOSPI"] == floor_kospi + 1


def test_exact_floor_boundary_passes():
    """정확히 하한값이면 통과 — 하한 '미만'만 거부한다(`<`, `<=` 아님).

    경계를 밟을 수 있는 쪽은 KOSDAQ 뿐이다:
      · KOSPI  943 × 0.8 = 754.4  → 정수로 안 떨어져 어떤 입력도 경계를 못 밟는다
      · KOSDAQ 1820 × 0.8 = 1456.0 → 부동소수점으로도 정확(실측)
    `1456 < 1456.0` 은 False(통과) / `1456 <= 1456.0` 은 True(거부)이므로,
    비교 연산자 변이는 **이 값에서만** 드러난다.
    """
    assert 1820 * MIN_SCALE_RATIO == 1456.0, "전제: 경계가 정수로 떨어져야 밟을 수 있다"
    conn = FakeConn(existing=LIVE_COUNTS)
    res = collect_stock_market(listing_fn=_full_listing(943, 1456), conn=conn)
    assert res["KOSDAQ"] == 1456, "하한과 같은 값은 거부 대상이 아니다"
    assert len(conn.rows) == 943 + 1456


def test_growth_is_never_blocked():
    """신규 상장으로 늘어나는 것은 언제나 정상이다."""
    conn = FakeConn(existing=LIVE_COUNTS)
    res = collect_stock_market(listing_fn=_full_listing(1200, 2400), conn=conn)
    assert res["KOSPI"] == 1200


# =========================================================================
# 최초 수집(빈 테이블)에는 하한을 적용하지 않는다
# =========================================================================

def test_first_collection_on_empty_table_is_allowed():
    """하한을 무조건 걸면 첫 수집이 영원히 불가능해진다."""
    conn = FakeConn(existing={})
    res = collect_stock_market(listing_fn=_full_listing(943, 1820), conn=conn)
    assert res["KOSPI"] == 943 and res["KOSDAQ"] == 1820


def test_floor_applies_per_market_when_one_side_is_new():
    """한쪽만 최초면 그쪽만 면제하고 다른 쪽 하한은 그대로 건다."""
    conn = FakeConn(existing={"KOSDAQ": 1820})  # KOSPI 는 아직 0행
    # KOSPI 는 최초라 면제 / KOSDAQ 은 미달 → 거부
    with pytest.raises(RuntimeError, match="KOSDAQ"):
        collect_stock_market(listing_fn=_full_listing(5, 100), conn=conn)
    assert conn.rows == []

    conn2 = FakeConn(existing={"KOSDAQ": 1820})
    res = collect_stock_market(listing_fn=_full_listing(5, 1820), conn=conn2)
    assert res["KOSPI"] == 5, "최초 수집인 시장에는 하한을 적용하지 않는다"


# =========================================================================
# 기존 가드는 그대로 살아 있어야 한다
# =========================================================================

def test_zero_rows_still_rejected():
    conn = FakeConn(existing=LIVE_COUNTS)
    with pytest.raises(RuntimeError, match="0건"):
        collect_stock_market(
            listing_fn=_listing({"KOSPI": _codes("10", 943), "KOSDAQ": []}), conn=conn)
    assert conn.rows == []


def test_overlap_still_rejected_before_any_write():
    conn = FakeConn(existing=LIVE_COUNTS)
    with pytest.raises(RuntimeError, match="교집합"):
        collect_stock_market(
            listing_fn=_listing({
                "KOSPI": _codes("10", 943),
                "KOSDAQ": _codes("10", 1820),  # 앞 943개가 KOSPI 와 겹친다
            }), conn=conn)
    assert conn.rows == []
