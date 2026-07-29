"""다중소유 종목 부분매도 — 라이브 실사례 replay 회귀 테스트
=============================================================

배경:
    0eb4a5e 이전 FundManager 는 보유 레지스트리를 ``Set[str]`` (stock_code
    단독 키) 로 들고 있었다. 두 전략이 같은 종목을 동시 보유한 상태에서 한
    전략이 매도하면 ``discard(stock_code)`` 가 **코드를 통째로** 제거해,
    남은 전략의 보유가 레지스트리·position_count·can_add_position 에서
    소실됐다(언더카운트).

    0eb4a5e 가 레지스트리를 ``(stock_code, owner)`` 엔트리 집합으로 바꿨고,
    10269ec 가 등록·해제 양쪽에 owner 를 전달하게 했으며, 8493851 이 스냅샷을
    frozenset 으로 굳혔다.

이 파일이 하는 일:
    라이브 페이퍼 매매에서 이 시나리오는 드물다 — 전체 매도 486건 중 6건
    (1.2%). 발생을 기다리는 대신, **실제로 발생했던 6건을 DB 에서 그대로
    뽑아 결정론적으로 replay** 한다. 픽스처 값(종목코드·소유 전략·수량·단가)은
    전부 ``kis_template.virtual_trading_records`` 실측치이며 합성값이 아니다.

추출 쿼리 (kis_template, SELECT only):
    매도 시점에 열려 있던 BUY(= 그 시점 이전 매수 중 아직 대응 SELL 이 없는
    행) 가 2건 이상인 SELL 을 고른 뒤, 각 건의 열린 BUY 전부를 함께 뽑았다.

owner 표기에 대한 근거:
    6건 **전부 오버나이트 보유**(매수일 < 매도일)라, 매도 당일 아침
    StateRestorer 를 거쳐 슬롯이 재생성된다. state_restorer.py:577 은
    ``trading_stock.owner_strategy_name = db_strategy`` 로 **DB strategy 컬럼
    값을 그대로** 넣는다. 매도 경로(trading_decision_engine.py:882)와 등록
    경로(trading_analyzer.py:197)는 둘 다 같은 슬롯 필드를 읽으므로,
    이 6건에서 레지스트리에 들어간 owner 문자열 = DB strategy 값이다.
    따라서 아래 폴더키 표기는 라이브 실제값과 일치한다.
"""
import pytest

from core.fund_manager import FundManager


# ============================================================================
# 실측 픽스처 — kis_template.virtual_trading_records 에서 추출 (수정 금지)
# ============================================================================
class OpenBuy:
    """매도 시점에 열려 있던 매수 1건 (virtual_trading_records BUY 행)"""

    def __init__(self, buy_id: int, owner: str, quantity: int, price: float):
        self.buy_id = buy_id
        self.owner = owner
        self.quantity = quantity
        self.price = price

    @property
    def cost(self) -> float:
        return float(self.price) * int(self.quantity)


class ReplayCase:
    """다중소유 상태에서 한 전략만 매도한 실사례 1건"""

    def __init__(self, sell_id, sell_date, stock_code, sell_owner,
                 sell_buy_id, sell_quantity, sell_price, open_buys):
        self.sell_id = sell_id
        self.sell_date = sell_date
        self.stock_code = stock_code
        self.sell_owner = sell_owner
        self.sell_buy_id = sell_buy_id
        self.sell_quantity = sell_quantity
        self.sell_price = sell_price
        self.open_buys = open_buys

    @property
    def owners(self):
        return [b.owner for b in self.open_buys]

    @property
    def surviving_owners(self):
        """매도하지 않은 = 보유가 유지되어야 하는 전략들"""
        return [b.owner for b in self.open_buys if b.owner != self.sell_owner]

    @property
    def sold_buy(self) -> OpenBuy:
        """매도로 청산된 매수 행"""
        return next(b for b in self.open_buys if b.buy_id == self.sell_buy_id)

    @property
    def total_invested(self) -> float:
        return sum(b.cost for b in self.open_buys)

    @property
    def case_id(self) -> str:
        return (f"{self.sell_date.replace('-', '')}-{self.stock_code}"
                f"-sell_{self.sell_owner}-vs-{'+'.join(self.surviving_owners)}")


REPLAY_CASES = [
    # sell_id=1366
    ReplayCase(
        sell_id=1366, sell_date="2026-06-30", stock_code="420770",
        sell_owner="book_envelope_200d", sell_buy_id=1316,
        sell_quantity=11, sell_price=188700.00,
        open_buys=[
            OpenBuy(1316, "book_envelope_200d", 11, 171500.00),
            OpenBuy(1338, "rs_leader", 5, 169500.00),
        ],
    ),
    # sell_id=1390
    ReplayCase(
        sell_id=1390, sell_date="2026-07-01", stock_code="483650",
        sell_owner="book_pullback_ma5", sell_buy_id=1253,
        sell_quantity=4, sell_price=219000.00,
        open_buys=[
            OpenBuy(1241, "elder_ema_pullback", 2, 234000.00),
            OpenBuy(1253, "book_pullback_ma5", 4, 226000.00),
        ],
    ),
    # sell_id=1595
    ReplayCase(
        sell_id=1595, sell_date="2026-07-14", stock_code="010170",
        sell_owner="book_pullback_ma5", sell_buy_id=1577,
        sell_quantity=153, sell_price=10670.00,
        open_buys=[
            OpenBuy(1568, "minervini_volume_dryup", 263, 12650.00),
            OpenBuy(1577, "book_pullback_ma5", 153, 12500.00),
        ],
    ),
    # sell_id=1659
    ReplayCase(
        sell_id=1659, sell_date="2026-07-16", stock_code="005860",
        sell_owner="book_pullback_ma5", sell_buy_id=1638,
        sell_quantity=180, sell_price=2490.00,
        open_buys=[
            OpenBuy(1626, "daytrading_3methods_breakout", 2, 2570.00),
            OpenBuy(1638, "book_pullback_ma5", 180, 2570.00),
        ],
    ),
    # sell_id=1697
    ReplayCase(
        sell_id=1697, sell_date="2026-07-21", stock_code="008350",
        sell_owner="book_pullback_ma5", sell_buy_id=1682,
        sell_quantity=1, sell_price=1056.00,
        open_buys=[
            OpenBuy(1669, "book_pullback_ma20", 1, 1095.00),
            OpenBuy(1682, "book_pullback_ma5", 1, 1100.00),
        ],
    ),
    # sell_id=1798 — 2026-07-28 EOD 에서 결함이 처음 발견된 그 건
    ReplayCase(
        sell_id=1798, sell_date="2026-07-28", stock_code="037230",
        sell_owner="book_pullback_ma5", sell_buy_id=1780,
        sell_quantity=1433, sell_price=1347.00,
        open_buys=[
            OpenBuy(1780, "book_pullback_ma5", 1433, 1395.00),
            OpenBuy(1791, "book_pullback_ma20", 141, 1390.00),
        ],
    ),
]

CASE_IDS = [c.case_id for c in REPLAY_CASES]


# ============================================================================
# 헬퍼
# ============================================================================
def _seed(case: ReplayCase, max_position_count: int = 20) -> FundManager:
    """매도 직전 상태 재현 — 열려 있던 모든 매수를 owner 와 함께 등록"""
    fm = FundManager(initial_funds=100_000_000,
                     max_position_count=max_position_count)
    for buy in case.open_buys:
        fm.add_position(case.stock_code, buy.owner)
    fm.invested_funds = case.total_invested
    fm.available_funds = fm.total_funds - fm.invested_funds
    return fm


def _sell(fm: FundManager, case: ReplayCase) -> None:
    """실제 매도 경로 재현 (trading_decision_engine.py:883-889)

    release_investment(owner=...) 후 remove_position(owner=...) 이 연달아
    호출된다. 회수 금액은 매수 원가(avg_price * qty)다.
    """
    sold = case.sold_buy
    fm.release_investment(sold.cost, stock_code=case.stock_code,
                          owner=case.sell_owner)
    fm.remove_position(case.stock_code, case.sell_owner)


def _entries(fm: FundManager):
    return set(fm._position_entries)


# ============================================================================
# 1. 핵심 회귀 — 잔여 전략의 보유가 소실되지 않는다
# ============================================================================
@pytest.mark.parametrize("case", REPLAY_CASES, ids=CASE_IDS)
class TestSurvivingOwnerKeepsPosition:

    def test_매도후에도_종목이_보유목록에_남는다(self, case):
        """구코드는 여기서 실패한다 — discard 가 코드를 통째로 지웠다"""
        fm = _seed(case)
        _sell(fm, case)

        assert case.stock_code in fm.current_position_codes, (
            f"{case.sell_date} {case.stock_code}: {case.sell_owner} 매도 후 "
            f"잔여 전략 {case.surviving_owners} 의 보유가 사라졌다"
        )

    def test_매도전략_엔트리만_사라지고_잔여전략_엔트리는_남는다(self, case):
        fm = _seed(case)
        _sell(fm, case)

        entries = _entries(fm)
        assert (case.stock_code, case.sell_owner) not in entries
        for owner in case.surviving_owners:
            assert (case.stock_code, owner) in entries

    def test_잔여_엔트리_수가_매도한_전략_수만큼만_줄어든다(self, case):
        fm = _seed(case)
        before = len(_entries(fm))
        _sell(fm, case)

        assert len(_entries(fm)) == before - 1

    def test_보유종목수는_distinct_1종목으로_유지된다(self, case):
        """position_count 의 의미는 distinct stock_code 수 (변경 없음)"""
        fm = _seed(case)
        _sell(fm, case)

        assert fm.get_status()['position_count'] == 1

    def test_잔여전략까지_매도해야_종목이_사라진다(self, case):
        fm = _seed(case)
        _sell(fm, case)

        for owner in case.surviving_owners:
            fm.remove_position(case.stock_code, owner)

        assert case.stock_code not in fm.current_position_codes
        assert fm.get_status()['position_count'] == 0


# ============================================================================
# 2. 파생 동작 일관성 — can_add_position
# ============================================================================
@pytest.mark.parametrize("case", REPLAY_CASES, ids=CASE_IDS)
class TestDerivedBehaviourConsistency:

    def test_한도가_찬_상태에서도_잔여보유_종목은_분할매수가_허용된다(self, case):
        """구코드는 매도 후 보유가 소실돼 이 종목을 '신규'로 오인했다"""
        fm = _seed(case, max_position_count=1)
        _sell(fm, case)

        assert fm.can_add_position(case.stock_code) is True

    def test_한도가_찬_상태에서_다른_종목_신규진입은_계속_막힌다(self, case):
        """소실이 일어나면 한도 슬롯이 잘못 비어 신규 진입이 뚫린다"""
        fm = _seed(case, max_position_count=1)
        _sell(fm, case)

        other = "999999"
        assert other != case.stock_code
        assert fm.can_add_position(other) is False


# ============================================================================
# 3. 돈 원장 — 레지스트리 수정이 자금 정합성을 건드리지 않는다
# ============================================================================
@pytest.mark.parametrize("case", REPLAY_CASES, ids=CASE_IDS)
class TestFundLedgerUnaffected:

    def test_매도전략_원가만_회수되고_잔여전략_투자금은_남는다(self, case):
        fm = _seed(case)
        _sell(fm, case)

        remaining = sum(b.cost for b in case.open_buys
                        if b.buy_id != case.sell_buy_id)
        assert fm.invested_funds == pytest.approx(remaining)

    def test_매도후_자금정합성_등식이_유지된다(self, case):
        fm = _seed(case)
        _sell(fm, case)

        assert fm.verify_fund_integrity()['is_valid'] is True


# ============================================================================
# 4. 이중호출 멱등성 — 실제 매도 경로는 release + remove 를 연달아 부른다
# ============================================================================
@pytest.mark.parametrize("case", REPLAY_CASES, ids=CASE_IDS)
class TestDoubleRemovalIdempotent:

    def test_remove_를_추가로_더_불러도_잔여전략은_무사하다(self, case):
        fm = _seed(case)
        _sell(fm, case)
        fm.remove_position(case.stock_code, case.sell_owner)  # 삼중 호출

        assert case.stock_code in fm.current_position_codes
        for owner in case.surviving_owners:
            assert (case.stock_code, owner) in _entries(fm)

    def test_owner_미지정_제거는_다중소유_상태에서_보류된다(self, case):
        """매도 전 상태에서 owner 없이 지우려 하면 모호 → 아무것도 안 지운다"""
        fm = _seed(case)
        fm.remove_position(case.stock_code)  # owner 미지정

        assert _entries(fm) == {(case.stock_code, b.owner)
                                for b in case.open_buys}


# ============================================================================
# 5. 픽스처 무결성 — 실측 데이터 전제가 깨지면 위 검증이 무의미해진다
# ============================================================================
class TestFixtureIntegrity:

    def test_추출된_사례는_6건이다(self):
        assert len(REPLAY_CASES) == 6

    @pytest.mark.parametrize("case", REPLAY_CASES, ids=CASE_IDS)
    def test_각_사례는_서로_다른_전략_2개가_동시보유한_상태다(self, case):
        assert len(case.open_buys) == 2
        assert len(set(case.owners)) == 2

    @pytest.mark.parametrize("case", REPLAY_CASES, ids=CASE_IDS)
    def test_매도전략은_열린_매수_중_하나의_소유자다(self, case):
        assert case.sell_owner in case.owners
        assert case.sold_buy.owner == case.sell_owner

    @pytest.mark.parametrize("case", REPLAY_CASES, ids=CASE_IDS)
    def test_매도수량은_해당_전략의_보유수량과_같다(self, case):
        """부분청산이 아닌 그 전략의 전량 매도 = 엔트리 제거가 맞는 상황"""
        assert case.sell_quantity == case.sold_buy.quantity

    @pytest.mark.parametrize("case", REPLAY_CASES, ids=CASE_IDS)
    def test_owner_표기는_전략_폴더키다(self, case):
        """복원 경로가 DB strategy 값을 그대로 owner 로 쓰므로 폴더키여야 한다"""
        from pathlib import Path
        strategies_dir = Path(__file__).resolve().parents[1] / "strategies"
        for owner in case.owners:
            assert (strategies_dir / owner).is_dir(), (
                f"{owner} 는 strategies/ 폴더키가 아니다 — DB 표기와 코드 표기가 "
                f"분열했을 수 있다"
            )


# ============================================================================
# 6. owner 표기 분열 — 등록·해제가 같은 표기를 써야만 매칭된다
# ============================================================================
class TestOwnerNotationInvariance:
    """표기 분열 자체는 존재한다(신규매수=클래스명 / 복원=폴더키).

    레지스트리가 안전한 이유는 표기가 통일돼서가 아니라, 등록(trading_analyzer:197)과
    해제(trading_decision_engine:882·liquidation_handler:341)가 **같은 슬롯 객체의
    owner_strategy_name 을 읽기 때문**이다. 아래 두 테스트가 그 전제를 고정한다.
    """

    FOLDER_KEY = "book_pullback_ma5"
    CLASS_NAME = "BookPullbackMa5Strategy"

    def test_같은_표기로_등록·해제하면_정확히_그_엔트리만_지워진다(self):
        for owner in (self.FOLDER_KEY, self.CLASS_NAME):
            fm = FundManager(initial_funds=100_000_000)
            fm.add_position("037230", owner)
            fm.add_position("037230", "book_pullback_ma20")

            fm.remove_position("037230", owner)

            assert _entries(fm) == {("037230", "book_pullback_ma20")}

    def test_등록과_해제의_표기가_다르면_엔트리가_잔류한다(self):
        """표기 불일치는 조용한 no-op 이 된다 — add/remove 대칭이 깨지면 안 되는 이유"""
        fm = FundManager(initial_funds=100_000_000)
        fm.add_position("037230", self.CLASS_NAME)

        fm.remove_position("037230", self.FOLDER_KEY)

        assert ("037230", self.CLASS_NAME) in _entries(fm)
        assert "037230" in fm.current_position_codes
