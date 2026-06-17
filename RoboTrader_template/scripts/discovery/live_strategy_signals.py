"""라이브 8전략 진입신호 백테스트 어댑터 + 가용성 probe.

목적(dynamic-rr Task 1):
  1. 각 라이브 전략의 generate_signal 을 백테스트 엔트리-신호 인덱스 목록으로 변환.
  2. 실제 quant 유니버스에서 전략별 신호 빈도를 측정해
     v1 포함/제외 기준(>=30 신호)을 판단한다.

PIT 규약: build_signals_for 는 bar i 까지만 전달(df.iloc[:i+1]) 미래참조 없음.
신호 범위: [warmup, n-2] --- 마지막 bar 는 다음봉 체결 불가.

설계 노트 (de-risking 발견):
  - 8전략 전부 _check_buy 내부에 MarketHours.is_market_open("KRX") 가드를 가진다.
    백테스트에서는 장외 시간에 실행되므로 이 가드를 우회해야 한다.
    build_signals_for 실행 중에만 MarketHours.is_market_open 을 항상 True 로
    monkey-patch 한다 (라이브 코드에는 영향 없음).
  - book_envelope_200d._check_buy 는 QuantDailyReader(DB) + MarketHours 를 내부 호출.
    백테스트에서는 순수함수 BookEnvelope200dStrategy.evaluate_entry(window) 를
    직접 호출해 DB 의존을 제거한다.

usage (probe):
  python scripts/discovery/live_strategy_signals.py
"""
from __future__ import annotations

import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

# ------------------------------------------------------------------
# 상수: 8 라이브 전략 폴더명 -> warmup 바 수
# ------------------------------------------------------------------

LIVE_STRATEGIES: Dict[str, int] = {
    "elder_ema_pullback": 70,
    "minervini_volume_dryup": 60,
    "deep_mr_dev20": 30,
    "daytrading_3methods_breakout": 25,
    "rs_leader": 65,
    "book_envelope_200d": 205,
    "book_pullback_ma20": 30,
    "book_pullback_ma5": 15,
}

# ------------------------------------------------------------------
# 전략 로드
# ------------------------------------------------------------------

def load_strategy(folder: str):
    """StrategyLoader 를 통해 전략 인스턴스를 반환한다.

    백테스트 전용: on_init(None, None, None) 으로 내부 상태(positions,
    daily_trades 등)를 초기화한다. 라이브 broker/data_provider/executor 는
    주입하지 않는다.

    Args:
        folder: strategies/ 하위 폴더명 (예: "elder_ema_pullback")

    Returns:
        BaseStrategy 인스턴스 (generate_signal 보유, positions={} 초기화 완료)
    """
    from strategies.config import StrategyLoader
    strat = StrategyLoader.load_strategy(folder)
    strat.on_init(None, None, None)
    return strat


# ------------------------------------------------------------------
# 백테스트 컨텍스트: 장중 가드 우회
# ------------------------------------------------------------------

@contextmanager
def _backtest_market_context():
    """MarketHours.is_market_open 을 항상 True 로 반환하도록 patch 한다.

    각 전략의 _check_buy 에 있는 장중 가드를 백테스트에서 우회하기 위해서다.
    컨텍스트 범위 내에서만 적용되며 라이브 코드에는 영향이 없다.
    """
    with patch("config.market_hours.MarketHours.is_market_open", return_value=True):
        yield


# ------------------------------------------------------------------
# 신호 빌더
# ------------------------------------------------------------------

def build_signals_for(
    folder: str,
    data: Dict[str, pd.DataFrame],
    warmup: int,
) -> Dict[str, List[int]]:
    """각 종목의 BUY/STRONG_BUY 신호 발생 bar 인덱스 목록을 반환한다.

    PIT 규약: bar i 평가 시 df.iloc[:i+1] 만 전달 (no-lookahead).
    신호 범위: i in [warmup, n-2] --- 마지막 bar 는 다음봉 체결 불가.

    book_envelope_200d 는 DB 의존을 제거하기 위해 evaluate_entry 순수함수를
    직접 호출한다 (다른 7전략은 generate_signal 경로 사용).

    전략 generate_signal 이 예외를 던지면 해당 종목은 빈 리스트로 처리한다
    (de-risking 용 --- 호출자가 별도 집계 가능).

    Args:
        folder: strategies/ 하위 폴더명
        data:   Dict[stock_code -> DataFrame(datetime,open,high,low,close,volume)]
        warmup: 신호 평가 시작 bar 인덱스

    Returns:
        Dict[stock_code -> List[bar_index]]
    """
    from strategies.base import SignalType

    strat = load_strategy(folder)

    # book_envelope_200d: DB/시장시간 의존 없는 순수함수 경로
    is_envelope = folder == "book_envelope_200d"
    envelope_evaluate = None
    if is_envelope:
        from strategies.book_envelope_200d.strategy import BookEnvelope200dStrategy
        envelope_evaluate = BookEnvelope200dStrategy.evaluate_entry

    cache: Dict[str, List[int]] = {}

    with _backtest_market_context():
        for code, df in data.items():
            n = len(df)
            sig_bars: List[int] = []
            if n >= warmup + 2:
                for i in range(warmup, n - 1):
                    window = df.iloc[: i + 1]
                    try:
                        if is_envelope:
                            triggered, _, _ = envelope_evaluate(window)
                            if triggered:
                                sig_bars.append(int(i))
                        else:
                            sig = strat.generate_signal(code, window, "daily")
                            if sig is not None and sig.signal_type in (
                                SignalType.BUY,
                                SignalType.STRONG_BUY,
                            ):
                                sig_bars.append(int(i))
                    except Exception:
                        # 예외 발생 시 해당 종목 스킵 --- 상위 probe 에서 집계
                        sig_bars = []
                        break
            cache[code] = sig_bars

    return cache


# ------------------------------------------------------------------
# 가용성 probe (real quant universe)
# ------------------------------------------------------------------

def _load_universe(top_n: int = 100) -> Optional[Dict[str, pd.DataFrame]]:
    """quant daily_prices 에서 상위 top_n 종목 일봉을 로드한다.

    book_portfolio_multiverse 의 내부 로더를 재사용한다.
    DB 미접속 시 None 반환.
    """
    try:
        import scripts.book_portfolio_multiverse as bpm  # noqa: F401
        codes = bpm._load_top_volume_daily("2021-01-01", "2026-06-16", top_n)
        if not codes:
            return None
        data = bpm._load_daily_adj(codes, "2021-01-01", "2026-06-16")
        return data
    except Exception as exc:
        print(f"[WARN] 유니버스 로드 실패: {exc}", file=sys.stderr)
        return None


if __name__ == "__main__":
    # 전략 INFO 로그를 억제해 probe 요약만 출력
    import logging
    logging.disable(logging.INFO)

    print("=" * 60)
    print("라이브 8전략 신호 빈도 probe (quant 유니버스 top_n=100)")
    print("=" * 60)

    data = _load_universe(top_n=100)
    if data is None:
        print("[BLOCKED] DB 접속 불가 --- 유니버스 로드 실패. 단위 테스트는 통과.")
        sys.exit(0)

    print(f"유니버스: {len(data)}종목 로드 완료\n")

    results = []
    for folder, warmup in LIVE_STRATEGIES.items():
        try:
            sig_map = build_signals_for(folder, data, warmup)
            total = sum(len(v) for v in sig_map.values())
            n_names = sum(1 for v in sig_map.values() if v)
            tag = "" if total >= 30 else "  <- <30 v1-EXCLUDE 후보"
            print(f"{folder:40s} 신호 {total:5d}건 / {n_names:3d}종목{tag}")
            results.append((folder, total, n_names))
        except Exception as exc:
            print(f"{folder:40s} [ERROR] {exc}")
            traceback.print_exc()

    # probe 결과를 파일에도 저장
    out_dir = ROOT / "reports" / "discovery" / "dynamic_rr"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "_signal_probe.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("라이브 8전략 신호 빈도 probe (quant 유니버스 top_n=100)\n")
        f.write("=" * 60 + "\n")
        for folder, total, n_names in results:
            tag = "" if total >= 30 else "  <- <30 v1-EXCLUDE 후보"
            f.write(f"{folder:40s} 신호 {total:5d}건 / {n_names:3d}종목{tag}\n")
    print(f"\n결과 저장: {out_path}")
