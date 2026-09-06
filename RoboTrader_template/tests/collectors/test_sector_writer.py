"""섹터 명부 SCD2 순수 함수 테스트 (T1 · T2 · T3). DB 를 쓰지 않는다."""
import os
import sys
from datetime import date, datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from collectors import sector_writer as w  # noqa: E402

D = date(2026, 9, 7)


def test_parent_code_identifies_preferred_shares():
    """끝자리 ≠ '0' 이면 우선주 — 부모는 앞 5자리 + '0'."""
    assert w.parent_code("00104K") == "001040"
    assert w.parent_code("000087") == "000080"
    assert w.parent_code("0220WL") == "0220W0"
    assert w.parent_code("005930") is None
    assert w.parent_code("0001A0") is None, "끝자리가 '0' 이면 보통주다(신형 상장코드)"


def test_parent_rule_copies_from_parent():
    """부모가 KSIC 를 가지면 코드·회사코드·이름을 함께 받고 출처를 못박는다."""
    cands = {
        "001040": {"ksic_code": "264", "ksic3_name": "통신 및 방송 장비 제조업",
                   "corp_code": "00126380"},
        "00104K": {"ksic_code": None, "ksic3_name": None, "corp_code": None},
    }
    out = w.apply_parent_rule(cands, {"001040", "00104K"})
    assert out["00104K"]["ksic_code"] == "264"
    assert out["00104K"]["ksic_source"] == "parent:001040"
    assert out["00104K"]["corp_code"] == "00126380"
    assert out["00104K"]["ksic3_name"] == "통신 및 방송 장비 제조업"
    assert out["001040"]["ksic_code"] == "264", "보통주는 건드리지 않는다"


def test_parent_absent_leaves_all_null():
    """부모가 유니버스에 아예 없으면(가상의 0220XL) 전부 NULL 이다."""
    cands = {"0220XL": {"ksic_code": None, "ksic3_name": None, "corp_code": None}}
    out = w.apply_parent_rule(cands, {"0220XL"})
    assert out["0220XL"]["ksic_code"] is None
    assert out["0220XL"].get("ksic_source") is None
    assert out["0220XL"]["ksic3_name"] is None


def test_parent_without_ksic_copies_name_only():
    """🔴 실제 사례 0220WL → 0220W0: 부모에 KSIC 가 없으면 «코드만» NULL 이고
    이름은 KSIC 와 독립으로 복사된다(캐시엔 부모 이름이 114/114 있다)."""
    cands = {
        "0220W0": {"ksic_code": None, "ksic3_name": "부동산 임대 및 공급업",
                   "corp_code": None},
        "0220WL": {"ksic_code": None, "ksic3_name": None, "corp_code": None},
    }
    out = w.apply_parent_rule(cands, {"0220W0", "0220WL"})
    assert out["0220WL"]["ksic_code"] is None
    assert out["0220WL"].get("ksic_source") is None
    assert out["0220WL"]["ksic3_name"] == "부동산 임대 및 공급업"


def test_self_value_wins_over_parent():
    """캐시 행에 자기 값이 있으면 그것이 부모보다 우선한다."""
    cands = {
        "001040": {"ksic_code": "264", "ksic3_name": "부모이름", "corp_code": "00126380"},
        "00104K": {"ksic_code": None, "ksic3_name": "자기이름", "corp_code": None},
    }
    out = w.apply_parent_rule(cands, {"001040", "00104K"})
    assert out["00104K"]["ksic3_name"] == "자기이름"


def _open(vf=date(2026, 1, 2), **kw):
    row = {"valid_from": vf, "ksic_code": None, "ksic3_name": None,
           "ksic_source": None, "ksic_checked_at": None, "corp_code": None}
    row.update(kw)
    return row


def test_same_value_opens_no_new_row():
    """값이 같으면 새 줄 0 — 제자리 갱신(last_seen_at·부수 열)만 한다."""
    plan = w.plan_map_changes(
        {"005930": _open(ksic_code="264", ksic3_name="가")},
        {"005930": {"ksic_code": "264", "ksic3_name": "가", "source_asof": date(2026, 9, 4)}},
        D)
    assert plan["open_new"] == [] and plan["close"] == []
    assert plan["counts"]["changed"] == 0
    assert len(plan["inplace"]) == 1
    assert plan["inplace"][0]["set"]["source_asof"] == date(2026, 9, 4)
    assert "collected_at" not in plan["inplace"][0]["set"], "collected_at 은 불변이다"


def test_null_to_value_fills_in_place():
    """🔴 NULL→값은 «이력»이 아니라 «알게 된 것» — 새 줄을 열지 않는다."""
    plan = w.plan_map_changes(
        {"005930": _open()},
        {"005930": {"ksic_code": "264", "ksic_source": "dart", "ksic3_name": "가"}},
        D)
    assert plan["open_new"] == [] and plan["close"] == []
    assert plan["counts"]["filled"] == 1 and plan["counts"]["changed"] == 0
    s = plan["inplace"][0]["set"]
    assert s["ksic_code"] == "264" and s["ksic_source"] == "dart" and s["ksic3_name"] == "가"


def test_value_to_value_closes_and_opens():
    """값→다른 값만 줄을 닫는다. valid_to = trade_date − 1일 · 새 줄 valid_from = trade_date.

    ⚠️ guard=False — 표본이 1종목이라 5% 가드(분모 = 비-NULL 열린 줄)가 무조건 걸린다.
       가드 자체는 T3 이 «분모가 충분한» 100종목 표본으로 따로 검증한다."""
    plan = w.plan_map_changes(
        {"005930": _open(vf=date(2026, 1, 2), ksic_code="264",
                         ksic_source="dart", ksic_checked_at=datetime(2026, 8, 1, 9, 0))},
        {"005930": {"ksic_code": "265", "ksic_source": "dart"}},
        D, guard=False)
    assert plan["close"] == [{"stock_code": "005930", "valid_from": date(2026, 1, 2),
                              "valid_to": date(2026, 9, 6)}]
    assert len(plan["open_new"]) == 1
    row = plan["open_new"][0]
    assert row["valid_from"] == D and row["ksic_code"] == "265"
    assert plan["counts"]["changed"] == 1
    assert plan["changed_codes"] == ["005930"]


def test_same_day_change_updates_in_place():
    """열린 줄이 «오늘» 시작이면 값→값도 제자리 갱신이다(PK 충돌·역전 방지).
    ⚠️ guard=False — 표본 1종목(위와 같은 이유)."""
    plan = w.plan_map_changes(
        {"005930": _open(vf=D, ksic_code="264")},
        {"005930": {"ksic_code": "265"}},
        D, guard=False)
    assert plan["close"] == [] and plan["open_new"] == []
    assert plan["inplace"][0]["set"]["ksic_code"] == "265"
    assert plan["counts"]["changed"] == 1
    assert plan["changed_codes"] == ["005930"]


def test_future_open_row_is_skipped_and_counted():
    """valid_from > trade_date(과거 날짜 재실행)면 그 종목은 건너뛰고 «센다»."""
    plan = w.plan_map_changes(
        {"005930": _open(vf=date(2026, 9, 10), ksic_code="264")},
        {"005930": {"ksic_code": "265"}},
        date(2026, 9, 7))
    assert plan["skipped_past"] == ["005930"]
    assert plan["counts"]["skipped_past"] == 1
    assert plan["inplace"] == [] and plan["open_new"] == [] and plan["close"] == []


def test_blank_new_value_is_not_a_change():
    """🔴 새 값이 NULL/공백이면 그 필드는 «유지» — 소스가 비어도 이력이 갈라지면 안 된다."""
    plan = w.plan_map_changes(
        {"005930": _open(ksic_code="264", ksic3_name="가")},
        {"005930": {"ksic_code": None, "ksic3_name": "   "}},
        D)
    assert plan["open_new"] == [] and plan["close"] == []
    assert plan["counts"]["changed"] == 0
    assert "ksic_code" not in plan["inplace"][0]["set"]
    assert "ksic3_name" not in plan["inplace"][0]["set"]


def test_new_row_inherits_ksic_checked_at():
    """새 줄의 ksic_checked_at 은 닫힌 줄 값을 «승계» — NULL 로 떨어지면
    재확인 큐(ASC NULLS FIRST) 맨 앞으로 튀어 예산을 먹는다.
    ⚠️ guard=False — 표본 1종목."""
    prev = datetime(2026, 8, 1, 9, 0)
    plan = w.plan_map_changes(
        {"005930": _open(ksic_code="264", ksic_checked_at=prev)},
        {"005930": {"ksic_code": "265"}},
        D, guard=False)
    assert plan["open_new"][0]["ksic_checked_at"] == prev


def test_new_stock_opens_row_at_trade_date():
    """처음 보는 종목은 valid_from = trade_date 로 연다."""
    plan = w.plan_map_changes({}, {"999999": {"ksic_code": "264"}}, D)
    assert plan["counts"]["new"] == 1
    assert plan["open_new"][0]["valid_from"] == D


def test_parent_change_opens_new_row_for_child():
    """T1 마지막 항목 — 부모가 값→값으로 바뀌면 «자식도» 새 줄을 연다.
    (우선주 후보엔 열린 줄 값을 승계하지 않으므로 부모 값이 그대로 후보가 된다)
    ⚠️ guard=False — 표본 2종목."""
    cands = w.apply_parent_rule(
        {"001040": {"ksic_code": "265"}, "00104K": {"ksic_code": None}},
        {"001040", "00104K"})
    plan = w.plan_map_changes(
        {"001040": _open(ksic_code="264"), "00104K": _open(ksic_code="264")},
        cands, D, guard=False)
    # 정렬은 ASCII 순 — '0'(0x30) < 'K'(0x4B) 이므로 "001040" 이 먼저다
    assert sorted(r["stock_code"] for r in plan["open_new"]) == ["001040", "00104K"]
    assert all(r["valid_from"] == D for r in plan["open_new"])
    assert sorted(plan["changed_codes"]) == ["001040", "00104K"]


def _many(n, ksic="264"):
    return dict(("%06d" % i, _open(ksic_code=ksic, ksic3_name="가")) for i in range(n))


def test_guard_raises_over_five_percent():
    """🔴 값→값이 5% 를 넘으면 한 행도 쓰지 않는다 — 소스가 통째로 바뀐 날이다."""
    opens = _many(100)
    cands = {}
    for i in range(100):
        code = "%06d" % i
        cands[code] = {"ksic_code": "265" if i < 6 else "264", "ksic3_name": "가"}
    with pytest.raises(RuntimeError) as e:
        w.plan_map_changes(opens, cands, D)
    assert "ksic_code" in str(e.value) and "6/100" in str(e.value)


def test_guard_allows_exactly_five_percent():
    """경계 — «초과»만 막는다(5.0% 는 통과)."""
    opens = _many(100)
    cands = dict(("%06d" % i,
                  {"ksic_code": "265" if i < 5 else "264", "ksic3_name": "가"})
                 for i in range(100))
    plan = w.plan_map_changes(opens, cands, D)
    assert plan["counts"]["changed"] == 5
    assert abs(plan["guard"]["ksic_code"]["ratio"] - 0.05) < 1e-9


def test_guard_ignores_null_fills():
    """NULL→값 300건은 «변경»이 아니므로 가드에 안 걸린다(분자에 안 들어간다)."""
    opens = dict(("%06d" % i, _open()) for i in range(300))
    cands = dict(("%06d" % i, {"ksic_code": "264", "ksic_source": "dart"})
                 for i in range(300))
    plan = w.plan_map_changes(opens, cands, D)
    assert plan["counts"]["filled"] == 300
    assert plan["guard"] == {}, "분모(비-NULL 열린 줄)가 0 이면 가드는 생략된다"


def test_guard_skips_when_denominator_zero():
    """분모 0 = 최초 수집. 가드를 걸면 첫 수집이 영원히 불가능해진다."""
    plan = w.plan_map_changes({}, {"005930": {"ksic_code": "264"}}, D)
    assert plan["guard"] == {}


class _FakeCur:
    def __init__(self, log):
        self.log = log
        self.description = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.log.append((sql, params))


class _FakeConn:
    def __init__(self):
        self.log = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _FakeCur(self.log)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_guard_trip_means_zero_writes():
    """🔴 가드가 걸리면 «한 행도» 안 쓴다 — 계획 단계에서 터지므로 SQL 이 0건이다."""
    conn = _FakeConn()
    opens = _many(100)
    cands = dict(("%06d" % i,
                  {"ksic_code": "265" if i < 10 else "264", "ksic3_name": "가"})
                 for i in range(100))
    with pytest.raises(RuntimeError):
        plan = w.plan_map_changes(opens, cands, D)
        w.write_map(conn, plan, "eod")
    assert conn.log == [] and conn.commits == 0


def test_write_map_always_touches_last_seen_and_never_collected_at():
    """제자리 갱신은 last_seen_at 을 «항상» 올리고 collected_at 은 절대 안 만진다."""
    conn = _FakeConn()
    plan = w.plan_map_changes(
        {"005930": _open(ksic_code="264", ksic3_name="가")},
        {"005930": {"ksic_code": "264", "ksic3_name": "가"}},
        D)
    out = w.write_map(conn, plan, "eod")
    assert out == {"closed": 0, "inserted": 0, "updated": 1}
    sql = conn.log[0][0]
    assert "last_seen_at=now()" in sql
    assert "collected_at" not in sql
