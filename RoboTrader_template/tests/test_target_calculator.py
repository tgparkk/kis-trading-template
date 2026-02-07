"""
TargetProfitLossCalculator 유닛 테스트
- 가중치 정규화 검증
- 5구간 경계값 검증
- 입력 검증 및 예외 안전성
"""
import pytest
from core.quant.target_profit_loss_calculator import TargetProfitLossCalculator


class TestWeightNormalization:
    """가중치 정규화 테스트"""

    def test_weight_normalization(self):
        calc = TargetProfitLossCalculator(
            rank_weight=0.6, score_weight=0.45, momentum_weight=0.45
        )
        total = calc.rank_weight + calc.score_weight + calc.momentum_weight
        assert abs(total - 1.0) < 1e-9

    def test_default_weights(self):
        calc = TargetProfitLossCalculator()
        total = calc.rank_weight + calc.score_weight + calc.momentum_weight
        assert abs(total - 1.0) < 1e-9
        assert abs(calc.rank_weight - 0.4) < 1e-9
        assert abs(calc.score_weight - 0.3) < 1e-9
        assert abs(calc.momentum_weight - 0.3) < 1e-9


class TestTierCalculation:
    """구간별 익절/손절률 테스트"""

    def test_tier_s_top_rank(self):
        calc = TargetProfitLossCalculator()
        # rank=1 → rank_score=100, score=95, mom=90
        # composite = 100*0.4 + 95*0.3 + 90*0.3 = 40+28.5+27 = 95.5 >= 80
        profit, loss = calc.calculate(rank=1, total_score=95, momentum_score=90)
        assert profit == 0.20
        assert loss == 0.08

    def test_tier_a(self):
        calc = TargetProfitLossCalculator()
        # rank=10 → rank_score=(51-10)/50*100=82, score=75, mom=70
        # composite = 82*0.4 + 75*0.3 + 70*0.3 = 32.8+22.5+21 = 76.3
        # 65 <= 76.3 < 80 → Tier A
        profit, loss = calc.calculate(rank=10, total_score=75, momentum_score=70)
        assert profit == 0.17
        assert loss == 0.09

    def test_tier_b(self):
        calc = TargetProfitLossCalculator()
        # rank=25 → rank_score=(51-25)/50*100=52, score=60, mom=55
        # composite = 52*0.4 + 60*0.3 + 55*0.3 = 20.8+18+16.5 = 55.3
        # 50 <= 55.3 < 65 → Tier B
        profit, loss = calc.calculate(rank=25, total_score=60, momentum_score=55)
        assert profit == 0.15
        assert loss == 0.10

    def test_tier_c(self):
        calc = TargetProfitLossCalculator()
        # rank=35 → rank_score=(51-35)/50*100=32, score=45, mom=40
        # composite = 32*0.4 + 45*0.3 + 40*0.3 = 12.8+13.5+12 = 38.3
        # 35 <= 38.3 < 50 → Tier C
        profit, loss = calc.calculate(rank=35, total_score=45, momentum_score=40)
        assert profit == 0.13
        assert loss == 0.10

    def test_tier_d_low(self):
        calc = TargetProfitLossCalculator()
        # rank=50 → rank_score=(51-50)/50*100=2, score=20, mom=10
        # composite = 2*0.4 + 20*0.3 + 10*0.3 = 0.8+6+3 = 9.8
        # < 35 → Tier D
        profit, loss = calc.calculate(rank=50, total_score=20, momentum_score=10)
        assert profit == 0.12
        assert loss == 0.10


class TestBoundaryValues:
    """경계값 테스트"""

    def test_boundary_80(self):
        calc = TargetProfitLossCalculator()
        # composite 정확히 80 → >= 80 → Tier S
        # rank=1→100, score=s, mom=m → 100*0.4 + s*0.3 + m*0.3 = 80
        # 40 + s*0.3 + m*0.3 = 80 → s*0.3 + m*0.3 = 40 → s+m = 133.3
        # s=66.67, m=66.67
        profit, loss = calc.calculate(rank=1, total_score=66.67, momentum_score=66.67)
        # composite ≈ 40 + 20.0 + 20.0 = 80.0
        assert profit == 0.20
        assert loss == 0.08

    def test_boundary_65(self):
        calc = TargetProfitLossCalculator()
        # rank=1→100, 100*0.4 + s*0.3 + m*0.3 = 65
        # 40 + 0.3*(s+m) = 65 → s+m = 83.33
        profit, loss = calc.calculate(rank=1, total_score=41.67, momentum_score=41.67)
        # composite ≈ 40 + 12.5 + 12.5 = 65.0
        assert profit == 0.17
        assert loss == 0.09


class TestInputValidation:
    """입력 검증 테스트"""

    def test_rank_over_50(self):
        calc = TargetProfitLossCalculator()
        # rank>50 → rank_score=0
        profit, loss = calc.calculate(rank=51, total_score=50, momentum_score=50)
        # composite = 0*0.4 + 50*0.3 + 50*0.3 = 30 < 35 → Tier D
        assert profit == 0.12
        assert loss == 0.10

    def test_invalid_rank_negative(self):
        calc = TargetProfitLossCalculator()
        # rank=-5 → 기본값 50 적용
        profit, loss = calc.calculate(rank=-5, total_score=50, momentum_score=50)
        # rank=50 → rank_score=2, composite = 2*0.4 + 50*0.3 + 50*0.3 = 0.8+15+15 = 30.8
        assert profit == 0.12
        assert loss == 0.10

    def test_score_over_100(self):
        calc = TargetProfitLossCalculator()
        # total_score=150 → 클램프 100
        profit, loss = calc.calculate(rank=1, total_score=150, momentum_score=100)
        # composite = 100*0.4 + 100*0.3 + 100*0.3 = 100 >= 80 → Tier S
        assert profit == 0.20
        assert loss == 0.08

    def test_exception_returns_default(self):
        calc = TargetProfitLossCalculator()
        # None 입력 → except → 기본값 (0.15, 0.10)
        profit, loss = calc.calculate(rank=None, total_score=None, momentum_score=None)
        assert profit == 0.15
        assert loss == 0.10


class TestFromPortfolioItem:
    """포트폴리오 아이템 기반 계산 테스트"""

    def test_from_portfolio_complete(self):
        calc = TargetProfitLossCalculator()
        item = {'rank': 1, 'total_score': 95}
        factors = {'momentum_score': 90}
        profit, loss = calc.calculate_from_portfolio_item(item, factors)
        assert profit == 0.20
        assert loss == 0.08

    def test_from_portfolio_no_factors(self):
        calc = TargetProfitLossCalculator()
        item = {'rank': 1, 'total_score': 95}
        profit, loss = calc.calculate_from_portfolio_item(item, factors_data=None)
        # momentum=50 (기본값)
        # composite = 100*0.4 + 95*0.3 + 50*0.3 = 40+28.5+15 = 83.5 >= 80
        assert profit == 0.20
        assert loss == 0.08

    def test_from_portfolio_empty_dict(self):
        calc = TargetProfitLossCalculator()
        item = {}  # rank=50(기본), total_score=0(기본)
        profit, loss = calc.calculate_from_portfolio_item(item)
        # rank=50 → rank_score=2, score=0, mom=50
        # composite = 2*0.4 + 0*0.3 + 50*0.3 = 0.8+0+15 = 15.8 < 35
        assert profit == 0.12
        assert loss == 0.10
