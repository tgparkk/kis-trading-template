"""
보유종목 레지스트리 다중소유(multi-owner) 회귀 테스트
=====================================================

배경 (2026-07-28 라이브 실증):
    FundManager.current_position_codes 가 stock_code 단독 키 Set 이라,
    두 전략이 같은 종목을 보유(037230 = book_pullback_ma5 1433주 +
    book_pullback_ma20 141주)하다가 한 전략이 매도하면 discard 가 코드를
    통째로 제거했다. 고친 증상은 이것이다 —
    **다owner 보유 중 한 전략이 매도하면 잔여 전략의 보유가 레지스트리와
    보유한도 체크(position_count·can_add_position)에서 소실(언더카운트)된다.**

    ⚠️ "EOD 보유종목=30 vs 실보유 31" 격차는 이 수정의 대상이 아니다.
    position_count 의 의미는 기존과 같은 distinct 종목 수로 유지하므로,
    두 전략이 같은 종목을 동시 보유하는 동안에는 수정 후에도 30 vs 31 이
    그대로 나타난다(정상). 다음 EOD 에서 그 격차를 보고 수정 실패로
    오진하지 말 것.

    돈 원장(invested_funds)은 이 결함과 무관하며 정확했다.

수정 방향:
    내부 자료구조를 (stock_code, owner) 엔트리 집합으로 바꾸고,
    current_position_codes 는 distinct stock_code 를 돌려주는 property 로
    하위호환을 유지한다.
"""
import pytest
from unittest.mock import MagicMock, patch

from core.fund_manager import FundManager


MA5 = "book_pullback_ma5"
MA20 = "book_pullback_ma20"


def _fm(total=100_000_000, max_position_count=20) -> FundManager:
    fm = FundManager(initial_funds=total, max_position_count=max_position_count)
    return fm


# ============================================================================
# 1. 오늘 시나리오 재현 — 다owner 보유 중 한 전략 매도
# ============================================================================
class TestMultiOwnerSell:
    """두 전략이 같은 종목 보유 → 한 전략만 매도"""

    def test_한전략_매도해도_남은전략_보유가_유지된다(self):
        fm = _fm()
        code = "037230"

        fm.add_position(code, MA5)
        fm.add_position(code, MA20)

        # 두 전략의 매수 자금 (돈 원장은 결함과 무관하나 실제 흐름을 재현)
        fm.invested_funds = 3_000_000.0
        fm.available_funds = fm.total_funds - fm.invested_funds

        # ma5 매도 흐름: release_investment → remove_position (둘 다 owner 지정)
        fm.release_investment(2_000_000.0, stock_code=code, owner=MA5)
        fm.remove_position(code, MA5)

        # 남은 owner(ma20)의 보유가 사라지면 안 된다
        assert code in fm.current_position_codes
        assert fm.get_status()['position_count'] == 1
        assert fm.verify_fund_integrity()['position_count'] == 1

    def test_모든_owner_매도_후에는_종목이_사라진다(self):
        fm = _fm()
        code = "037230"

        fm.add_position(code, MA5)
        fm.add_position(code, MA20)

        fm.remove_position(code, MA5)
        assert code in fm.current_position_codes

        fm.remove_position(code, MA20)
        assert code not in fm.current_position_codes
        assert fm.get_status()['position_count'] == 0

    def test_같은_owner_중복추가는_멱등(self):
        fm = _fm()
        fm.add_position("037230", MA5)
        fm.add_position("037230", MA5)

        fm.remove_position("037230", MA5)
        assert "037230" not in fm.current_position_codes

    def test_다owner_보유는_보유한도에_1종목으로만_계산된다(self):
        """position_count 의미 = distinct stock_code 수 (변경 없음)"""
        fm = _fm(max_position_count=2)
        fm.add_position("037230", MA5)
        fm.add_position("037230", MA20)
        fm.add_position("005930", MA5)

        assert len(fm.current_position_codes) == 2
        # 2종목 = 한도 도달 → 신규 종목 불가, 기존 종목 분할매수는 허용
        assert fm.can_add_position("000660") is False
        assert fm.can_add_position("037230") is True


# ============================================================================
# 2. 이중제거 멱등성 (release_investment + remove_position 연속 호출)
# ============================================================================
class TestDoubleRemovalIdempotent:
    """한 번의 매도에 release_investment 와 remove_position 이 연달아 호출된다"""

    def test_release_후_remove_는_1회만_제거된다(self):
        fm = _fm()
        code = "005930"
        fm.add_position(code, MA5)
        fm.invested_funds = 1_000_000.0
        fm.available_funds = fm.total_funds - fm.invested_funds

        fm.release_investment(1_000_000.0, stock_code=code, owner=MA5)
        assert code not in fm.current_position_codes

        # 두 번째 제거는 no-op 이어야 한다 (예외/음수 없음)
        fm.remove_position(code, MA5)
        assert code not in fm.current_position_codes
        assert fm.get_status()['position_count'] == 0
        assert fm.invested_funds == 0.0

    def test_다owner에서_이중제거해도_남은_owner는_무사하다(self):
        fm = _fm()
        code = "037230"
        fm.add_position(code, MA5)
        fm.add_position(code, MA20)
        fm.invested_funds = 3_000_000.0
        fm.available_funds = fm.total_funds - fm.invested_funds

        fm.release_investment(2_000_000.0, stock_code=code, owner=MA5)
        fm.remove_position(code, MA5)   # 이중 호출
        fm.remove_position(code, MA5)   # 삼중 호출도 무해

        assert code in fm.current_position_codes
        assert fm.get_status()['position_count'] == 1


# ============================================================================
# 3. owner=None 레거시 경로
# ============================================================================
class TestLegacyOwnerNone:
    """owner 미지정 호출 (기존 코드/실주문 경로) 하위호환"""

    def test_단일엔트리는_owner없이_제거된다(self):
        fm = _fm()
        fm.add_position("005930")
        fm.remove_position("005930")
        assert "005930" not in fm.current_position_codes

    def test_owner로_추가한_단일엔트리도_owner없이_제거된다(self):
        fm = _fm()
        fm.add_position("005930", MA5)
        fm.remove_position("005930")
        assert "005930" not in fm.current_position_codes

    def test_다중엔트리는_owner없이_제거되지_않고_경고한다(self):
        fm = _fm()
        code = "037230"
        fm.add_position(code, MA5)
        fm.add_position(code, MA20)

        with patch.object(fm.logger, 'warning') as mock_warn:
            fm.remove_position(code)  # owner 미지정 = 모호
            assert mock_warn.called

        # 모호한 제거는 보류 — 둘 다 남아 있어야 한다
        assert code in fm.current_position_codes
        fm.remove_position(code, MA5)
        fm.remove_position(code, MA20)
        assert code not in fm.current_position_codes

    def test_release_investment_owner없이도_자금은_회수된다(self):
        """모호해서 엔트리는 남더라도 자금 회수는 정상 수행"""
        fm = _fm()
        code = "037230"
        fm.add_position(code, MA5)
        fm.add_position(code, MA20)
        fm.invested_funds = 3_000_000.0
        fm.available_funds = fm.total_funds - fm.invested_funds

        fm.release_investment(2_000_000.0, stock_code=code)

        assert fm.invested_funds == 1_000_000.0
        assert code in fm.current_position_codes


# ============================================================================
# 4. property 하위호환 (getter/setter)
# ============================================================================
class TestPropertyBackCompat:
    """current_position_codes 대입/조회 하위호환"""

    def test_setter_로_전체교체가_가능하다(self):
        fm = _fm(max_position_count=3)
        fm.add_position("037230", MA5)

        fm.current_position_codes = {"A", "B"}

        assert fm.current_position_codes == {"A", "B"}
        assert len(fm.current_position_codes) == 2
        assert fm.can_add_position("C") is True

        fm.current_position_codes = {"A", "B", "C"}
        assert fm.can_add_position("D") is False
        assert fm.can_add_position("A") is True

    def test_setter_로_넣은_코드는_owner없이_제거된다(self):
        fm = _fm()
        fm.current_position_codes = {"A", "B"}
        fm.remove_position("A")
        assert fm.current_position_codes == {"B"}

    def test_getter_는_distinct_코드집합이다(self):
        fm = _fm()
        fm.add_position("037230", MA5)
        fm.add_position("037230", MA20)
        codes = fm.current_position_codes
        assert codes == {"037230"}
        assert len(codes) == 1

    def test_getter_반환값_변이는_내부상태를_바꾸지_않는다(self):
        """getter 는 스냅샷 — 외부 변이가 레지스트리를 오염시키면 안 된다"""
        fm = _fm()
        fm.add_position("005930", MA5)
        snapshot = fm.current_position_codes
        try:
            snapshot.add("999999")
        except AttributeError:
            pass  # frozenset 반환도 허용
        assert fm.current_position_codes == {"005930"}


# ============================================================================
# 5. 복원 경로 (state_restorer) — owner 전달
# ============================================================================
class TestRestorePath:
    """StateRestorer._sync_fund_manager_for_position 이 owner 를 전달하는지"""

    def _restorer(self, fm):
        from bot.state_restorer import StateRestorer
        return StateRestorer(
            trading_manager=MagicMock(),
            db_manager=MagicMock(),
            telegram_integration=MagicMock(),
            config=MagicMock(),
            get_previous_close_callback=MagicMock(return_value=0.0),
            broker=MagicMock(),
            fund_manager=fm,
        )

    def test_이중보유_복원시_엔트리2개_종목1개(self):
        fm = _fm()
        restorer = self._restorer(fm)

        restorer._sync_fund_manager_for_position("037230", 1433, 10_000.0, owner=MA5)
        restorer._sync_fund_manager_for_position("037230", 141, 10_000.0, owner=MA20)

        assert fm.current_position_codes == {"037230"}
        assert fm.get_status()['position_count'] == 1

        # 한 전략 매도 후에도 종목은 남는다 (오늘 결함의 복원 경로 버전)
        fm.remove_position("037230", MA5)
        assert "037230" in fm.current_position_codes
        fm.remove_position("037230", MA20)
        assert "037230" not in fm.current_position_codes

    def test_owner_미지정_복원은_레거시처럼_동작한다(self):
        fm = _fm()
        restorer = self._restorer(fm)

        restorer._sync_fund_manager_for_position("005930", 10, 70_000.0)

        assert fm.current_position_codes == {"005930"}
        fm.remove_position("005930")
        assert fm.current_position_codes == set()
