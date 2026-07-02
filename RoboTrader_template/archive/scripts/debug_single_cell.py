"""G2 stall 진단 + fix 검증용 단일 셀 직접 실행.

fix 내용: pit_reader.backtest_session() — 전체 루프를 단일 DB 연결로 감쌈.
root cause: psycopg2.connect() ~220ms/call × 17,654회 = 53분/셀.
"""
import logging
import sys
import time
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from RoboTrader_template.multiverse.composable.personas._grid import expand_grid_quant
from RoboTrader_template.multiverse.composable import build_quant_strategy
from RoboTrader_template.multiverse.engine.portfolio_engine import run_portfolio_backtest
from RoboTrader_template.multiverse.data.kospi200_pit import get_kospi200_pit

# 1단계: ParamSet 1개
grid = expand_grid_quant()
print(f"quant grid size: {len(grid)}")
ps = grid[0]
print(f"first ParamSet: {ps.config_hash()}")

# 2단계: KOSPI200 200종목 (2024년 기준)
t0 = time.monotonic()
universe = get_kospi200_pit(date(2024, 1, 2))
print(f"universe: {len(universe)} 종목 ({time.monotonic()-t0:.1f}s)")

# 3단계: 단일 셀 백테스트 — 1년 (fix 후 ~1분 이내 예상)
strategy = build_quant_strategy(ps, candidate_symbols=universe)
start = time.monotonic()
print("=== run_portfolio_backtest 시작 (2024년 1년) ===")
result = run_portfolio_backtest(
    strategy=strategy,
    candidate_symbols=universe,
    start_date=date(2024, 1, 2),
    end_date=date(2024, 12, 31),
    initial_capital=10_000_000,
    universe_filter="kospi200_pit",
)
elapsed = time.monotonic() - start
print(f"=== 완료: {elapsed:.1f}초 / 거래 {len(result.trades)}건 / 최종 {result.final_equity:,.0f}원 ===")
print(f"거래일 수: {len(result.daily_equity)}")
print(f"리밸런싱 수: {len(result.rebalance_dates)}")

# 5년 추정
est_5y = elapsed * 5
est_144 = est_5y * 144 / 3600 / 8
print()
print(f"1년 소요: {elapsed:.1f}초")
print(f"5년 추정: {est_5y:.0f}초 = {est_5y/60:.1f}분/셀")
print(f"144셀 × 8 jobs 추정: {est_144:.1f}시간")
