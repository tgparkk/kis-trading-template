"""
Phase E6 단위 테스트 — CandidateSelector 전략별 후보 풀 분리

테스트 범위:
- test_candidates_per_strategy_separate_pools: 2 전략에 다른 후보 dict 반환
- test_candidates_overlap_first_strategy_wins: 같은 종목 등장 시 첫 strategy만 등록
- test_load_screener_candidates_multi_strategy: main.py 통합 흐름 (다중 전략)
- test_backward_compat_single_strategy: self.strategies가 1개면 기존 동작
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from core.candidate_selector import CandidateSelector, CandidateStock
from core.trading.stock_state_manager import StockStateManager
from core.models import TradingStock, StockState
from utils.korean_time import now_kst


# ============================================================================
# 픽스처 헬퍼
# ============================================================================

def _make_selector():
    """DB 없는 CandidateSelector 인스턴스."""
    config = MagicMock()
    config.candidate_filters = None  # 블랙리스트 필터 비활성
    broker = MagicMock()
    return CandidateSelector(config=config, broker=broker, db_manager=None)


def _make_candidate(code: str, name: str = None, reason: str = "test") -> CandidateStock:
    return CandidateStock(
        code=code,
        name=name or code,
        market="KRX",
        score=50.0,
        reason=reason,
        prev_close=10000.0,
    )


# ============================================================================
# 1. select_candidates_per_strategy — 전략별 분리 풀 반환
# ============================================================================

class TestCandidatesPerStrategySeparatePools:
    """2 전략에 대해 서로 다른 후보 dict를 반환하는지 검증."""

    def test_candidates_per_strategy_separate_pools(self):
        selector = _make_selector()

        strategy_a_candidates = [_make_candidate("000001"), _make_candidate("000002")]
        strategy_b_candidates = [_make_candidate("000003"), _make_candidate("000004")]

        strategies = {"StrategyA": MagicMock(), "StrategyB": MagicMock()}

        def fake_fetch(strategy_name, max_candidates):
            if strategy_name == "StrategyA":
                return strategy_a_candidates
            return strategy_b_candidates

        selector._fetch_candidates_for_strategy = fake_fetch

        result = selector.select_candidates_per_strategy(strategies, max_per_strategy=10)

        assert set(result.keys()) == {"StrategyA", "StrategyB"}
        assert [c.code for c in result["StrategyA"]] == ["000001", "000002"]
        assert [c.code for c in result["StrategyB"]] == ["000003", "000004"]

    def test_empty_strategy_returns_empty_list(self):
        selector = _make_selector()
        strategies = {"OnlyA": MagicMock()}

        selector._fetch_candidates_for_strategy = lambda name, max_c: []

        result = selector.select_candidates_per_strategy(strategies, max_per_strategy=5)

        assert result == {"OnlyA": []}


# ============================================================================
# 2. 종목 중복 — 첫 번째 전략 우선
# ============================================================================

class TestCandidatesOverlapFirstStrategyWins:
    """전략별 자본이 독립이므로 같은 종목이 여러 전략 후보에 중복 허용된다."""

    def test_overlap_allowed_for_independent_capital(self):
        selector = _make_selector()

        shared_code = "999999"
        strategies = {"First": MagicMock(), "Second": MagicMock()}

        def fake_fetch(strategy_name, max_candidates):
            # 두 전략 모두 같은 종목 포함
            return [_make_candidate(shared_code), _make_candidate(f"unique_{strategy_name}")]

        selector._fetch_candidates_for_strategy = fake_fetch

        result = selector.select_candidates_per_strategy(strategies, max_per_strategy=10)

        first_codes = [c.code for c in result["First"]]
        second_codes = [c.code for c in result["Second"]]

        # 첫 전략은 공유 종목 포함
        assert shared_code in first_codes
        # 두 번째 전략도 공유 종목 포함 (독립 자본이므로 제거하지 않음)
        assert shared_code in second_codes
        # 두 번째 전략의 고유 종목도 유지
        assert "unique_Second" in second_codes

    def test_no_overlap_both_strategies_full(self):
        selector = _make_selector()
        strategies = {"A": MagicMock(), "B": MagicMock()}

        def fake_fetch(strategy_name, max_candidates):
            prefix = "1" if strategy_name == "A" else "2"
            return [_make_candidate(f"{prefix}0000{i}") for i in range(3)]

        selector._fetch_candidates_for_strategy = fake_fetch

        result = selector.select_candidates_per_strategy(strategies, max_per_strategy=10)

        assert len(result["A"]) == 3
        assert len(result["B"]) == 3
        # 코드 집합 겹침 없어야 함
        codes_a = {c.code for c in result["A"]}
        codes_b = {c.code for c in result["B"]}
        assert codes_a.isdisjoint(codes_b)


# ============================================================================
# 3. StockStateManager 중복 등록 거부
# ============================================================================

class TestStockStateManagerDuplicateRejection:
    """register_stock이 중복 코드를 거부하는지 검증."""

    def _make_ts(self, code: str) -> TradingStock:
        return TradingStock(
            stock_code=code,
            stock_name=code,
            state=StockState.SELECTED,
            selected_time=now_kst(),
            selection_reason="test",
        )

    def test_first_registration_succeeds(self):
        mgr = StockStateManager()
        ts = self._make_ts("000001")
        result = mgr.register_stock(ts)
        assert result is True
        assert mgr.get_trading_stock("000001") is ts

    def test_duplicate_registration_rejected(self):
        """POSITIONED 상태 종목의 두 번째 등록은 거부되고 원본 유지 (E8 정책)."""
        mgr = StockStateManager()
        ts1 = self._make_ts("000001")
        mgr.register_stock(ts1)
        # POSITIONED로 전이 후 두 번째 등록 시도
        mgr.change_stock_state("000001", StockState.BUY_PENDING)
        mgr.change_stock_state("000001", StockState.POSITIONED)

        ts2 = self._make_ts("000001")
        result = mgr.register_stock(ts2)

        assert result is False
        # 원본 객체 유지 (복합키: 동일 전략 기준 거부)
        assert mgr.get_trading_stock("000001") is ts1

    def test_different_codes_both_registered(self):
        mgr = StockStateManager()
        ts_a = self._make_ts("000001")
        ts_b = self._make_ts("000002")

        assert mgr.register_stock(ts_a) is True
        assert mgr.register_stock(ts_b) is True
        assert len(mgr.trading_stocks) == 2


# ============================================================================
# 4. main.py 통합 흐름 — 다중 전략
# ============================================================================

class TestLoadScreenerCandidatesMultiStrategy:
    """_load_screener_candidates가 다중 전략 경로를 타는지 검증."""

    def _make_bot(self, num_strategies: int):
        """DayTradingBot 필수 속성을 mock으로 구성."""
        bot = MagicMock()
        bot._candidates_loaded = False
        bot._candidate_load_retries = 0

        # strategies dict
        strategy_names = [f"Strategy{i}" for i in range(num_strategies)]
        bot.strategies = {name: MagicMock(name=name) for name in strategy_names}
        bot.strategy = next(iter(bot.strategies.values())) if bot.strategies else None

        # config
        bot.config = MagicMock()
        bot.config.strategy = None

        # trading_manager
        bot.trading_manager = MagicMock()
        bot.trading_manager.trading_stocks = {}
        bot.trading_manager.add_selected_stock = AsyncMock(return_value=True)
        bot.trading_manager.get_trading_stock = MagicMock(return_value=MagicMock())

        # candidate_selector
        bot.candidate_selector = MagicMock()

        # telegram
        bot.telegram = MagicMock()
        bot.telegram.notify_system_status = AsyncMock()

        # db_manager
        bot.db_manager = None

        return bot

    def test_single_strategy_uses_legacy_path(self):
        """단일 전략이면 다중 전략 경로를 타지 않아야 함."""
        from main import DayTradingBot

        bot = self._make_bot(num_strategies=1)

        # 스크리너 JSON 로드 → 1건 반환
        single_candidate = _make_candidate("000001")
        bot.candidate_selector.load_from_screener = MagicMock(
            return_value=[single_candidate]
        )

        # _load_candidates_multi_strategy를 직접 테스트하지 않아도 됨 —
        # _load_screener_candidates 내부에서 len(self.strategies) > 1 분기를 확인
        async def run():
            # 언바운드 메서드 직접 호출 (self=bot)
            await DayTradingBot._load_screener_candidates(bot)

        asyncio.get_event_loop().run_until_complete(run())

        # 단일 경로: load_from_screener 호출됨
        bot.candidate_selector.load_from_screener.assert_called_once()
        # 다중 전략 메서드는 호출되지 않음
        assert not hasattr(bot.candidate_selector, 'select_candidates_per_strategy') or \
               not bot.candidate_selector.select_candidates_per_strategy.called

    def test_multi_strategy_calls_select_per_strategy(self):
        """2개 이상 전략이면 select_candidates_per_strategy를 호출해야 함."""
        from main import DayTradingBot

        bot = self._make_bot(num_strategies=2)

        cand_a = _make_candidate("000001")
        cand_b = _make_candidate("000002")
        bot.candidate_selector.select_candidates_per_strategy = MagicMock(
            return_value={
                "Strategy0": [cand_a],
                "Strategy1": [cand_b],
            }
        )

        async def run():
            await DayTradingBot._load_candidates_multi_strategy(bot, max_per_strategy=10)

        asyncio.get_event_loop().run_until_complete(run())

        bot.candidate_selector.select_candidates_per_strategy.assert_called_once()
        assert bot._candidates_loaded is True

        # 두 종목 모두 add_selected_stock 호출
        assert bot.trading_manager.add_selected_stock.call_count == 2

    def test_multi_strategy_same_stock_registered_per_owner(self):
        """같은 코드가 두 전략에 배정되면 각 전략 owner로 각각 등록된다.

        전략별 자본 독립 → 동일 종목을 여러 전략이 각자 보유 가능. 과거의
        '두 번째 등록 거부' 가드는 제거되었고, 동일 전략 중복만 add_selected_stock
        내부에서 막힌다.
        """
        from main import DayTradingBot

        bot = self._make_bot(num_strategies=2)

        shared = _make_candidate("999999")
        bot.candidate_selector.select_candidates_per_strategy = MagicMock(
            return_value={
                "Strategy0": [shared],
                "Strategy1": [shared],  # 의도적 중복 — 이제 둘 다 등록되어야 함
            }
        )

        calls = []

        async def fake_add(stock_code, stock_name, selection_reason, prev_close, owner_strategy=""):
            calls.append((stock_code, owner_strategy))
            return True

        bot.trading_manager.add_selected_stock = fake_add

        async def run():
            await DayTradingBot._load_candidates_multi_strategy(bot, max_per_strategy=10)

        asyncio.get_event_loop().run_until_complete(run())

        # 두 전략 모두 동일 종목을 각자 owner로 등록
        assert len(calls) == 2
        assert all(code == "999999" for code, _ in calls)
        assert {owner for _, owner in calls} == {"Strategy0", "Strategy1"}


# ============================================================================
# 5. backward compat — 단일 전략 기존 동작
# ============================================================================

class TestBackwardCompatSingleStrategy:
    """self.strategies가 1개면 기존 단일 풀 동작 유지."""

    def test_single_strategy_registered_with_strategy_name(self):
        """단일 전략 경로: 후보 등록 시 strategy_name이 전략명으로 설정됨."""
        from main import DayTradingBot

        bot = MagicMock()
        bot._candidates_loaded = False
        bot._candidate_load_retries = 0
        bot.config = MagicMock()
        bot.config.strategy = None

        strategy_mock = MagicMock()
        strategy_mock.name = "SampleStrategy"
        bot.strategies = {"SampleStrategy": strategy_mock}
        bot.strategy = strategy_mock

        cand = _make_candidate("000001", name="테스트종목")
        bot.candidate_selector = MagicMock()
        bot.candidate_selector.load_from_screener = MagicMock(return_value=[cand])

        ts_mock = MagicMock()
        bot.trading_manager = MagicMock()
        bot.trading_manager.trading_stocks = {}
        bot.trading_manager.add_selected_stock = AsyncMock(return_value=True)
        bot.trading_manager.get_trading_stock = MagicMock(return_value=ts_mock)
        bot.db_manager = None
        bot.telegram = MagicMock()
        bot.telegram.notify_system_status = AsyncMock()

        async def run():
            await DayTradingBot._load_screener_candidates(bot)

        asyncio.get_event_loop().run_until_complete(run())

        assert bot._candidates_loaded is True
        # strategy_name 설정 확인
        assert ts_mock.strategy_name == "SampleStrategy"


# ============================================================================
# 6. 거래량 폴백 풀에 전략 base_filter 적용 (유니버스 누수 차단)
# ============================================================================

class TestVolumeFallbackRespectsBaseFilter:
    """거래량 순위 폴백 풀이 수용 전략의 screener base_filter를 통과한 종목만
    포함해야 한다. base_filter는 거래대금≥10억·시총<5천억 컷이며, 폴백 풀은
    원래 이 컷을 거치지 않아 daytrading 유니버스를 위반했다(2026-06-25 감사 E).
    """

    def test_volume_fallback_respects_strategy_base_filter(self):
        from main import apply_volume_fallback_with_filter

        fallback = [
            _make_candidate("000001"),  # 위반: 거래대금<10억·시총>5천억
            _make_candidate("000002"),  # 통과
        ]
        # CandidateStock은 market_cap/trading_value를 들지 않으므로 quant 유니버스
        # 스냅샷(SSOT)에서 조회한다. 단위테스트는 이 조회를 주입한다.
        universe_lookup = {
            "000001": {"market_cap": 600_000_000_000, "trading_value": 500_000_000},
            "000002": {"market_cap": 300_000_000_000, "trading_value": 2_000_000_000},
        }

        pool = apply_volume_fallback_with_filter(
            "daytrading_3methods_breakout", fallback, universe_lookup=universe_lookup
        )
        codes = {c.code for c in pool}

        assert "000002" in codes
        assert "000001" not in codes  # base_filter가 폴백에도 적용

    def test_unknown_strategy_returns_fallback_unchanged(self):
        """어댑터가 없는 전략은 보수적으로 기존 동작(필터 미적용) 유지."""
        from main import apply_volume_fallback_with_filter

        fallback = [_make_candidate("000001"), _make_candidate("000002")]
        universe_lookup = {
            "000001": {"market_cap": 600_000_000_000, "trading_value": 500_000_000},
        }

        pool = apply_volume_fallback_with_filter(
            "no_such_strategy_xyz", fallback, universe_lookup=universe_lookup
        )

        # 어댑터 없음 → 폴백 풀 그대로
        assert {c.code for c in pool} == {"000001", "000002"}

    def test_missing_universe_data_treated_as_filtered_out(self):
        """유니버스 스냅샷에 없는 종목은 거래대금 검증 불가 → base_filter 컷에서 제외.

        base_filter는 trading_value 미상(0)을 min_trading_value 미만으로 취급하므로
        스냅샷에 없는 종목은 자연히 빠진다(스크리너와 동일 의미).
        """
        from main import apply_volume_fallback_with_filter

        fallback = [_make_candidate("000003")]  # 스냅샷에 없음
        pool = apply_volume_fallback_with_filter(
            "daytrading_3methods_breakout", fallback, universe_lookup={}
        )

        assert pool == []
