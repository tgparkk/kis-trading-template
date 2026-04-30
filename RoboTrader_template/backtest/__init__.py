"""
Backtest Package
================

일봉 데이터를 사용해 전략의 generate_signal()을 재사용하는 백테스트 엔진.

Usage:
    from backtest import BacktestEngine, MultiverseEngine
    from strategies.sample.strategy import SampleStrategy

    # 단일 백테스트
    engine = BacktestEngine(SampleStrategy(), initial_capital=10_000_000)
    result = engine.run(stock_codes=["005930", "000660"], daily_data=data)
    print(f"수익률: {result.total_return:.2%}, 승률: {result.win_rate:.2%}")

    # 파라미터 스윕
    mv = MultiverseEngine(
        strategy_class=SampleStrategy,
        daily_data=data,
        stock_codes=["005930", "000660"],
    )
    mv.add_param("parameters.ma_short_period", [3, 5, 10])
    mv.add_param("parameters.rsi_oversold", [25, 30, 35])
    results = mv.run(min_trades=20, n_jobs=4)
    print(results.top(10))
"""

from backtest.engine import BacktestEngine, BacktestResult, make_screener_snapshot_provider
from backtest.multiverse import MultiverseEngine, MultiverseResult

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "make_screener_snapshot_provider",
    "MultiverseEngine",
    "MultiverseResult",
]
