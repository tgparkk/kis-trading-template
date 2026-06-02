"""태쏘 『데이트레이딩 바이블 2』 기법 B — 종가배팅(close_betting) 일봉 규칙.

카탈로그(reports/books_research/taesso_daytrading_bible2/strategy_catalog.md)
"기법 B — 종가배팅" 절을 구현.

셋업(일봉):
  D0 장대양봉 → D1 단봉조정(=신호일) → D1 종가 매수 → 익일 오전 +2~3% 익절.

run 스크립트는 종목별 daily_prices 의 df.iloc[:i+1] 윈도우를 전달한다.
evaluate 는 df 마지막 행(t=D1)까지만 사용하고, D0=직전봉(df.iloc[-2])으로 본다 (no-lookahead).

datetime 컬럼: pandas Timestamp(일 단위). 컬럼: datetime, open, high, low, close, volume.

진입/청산 모델링 판단(근사):
- **D1 종가 진입 ≈ 다음봉 시가**: BookBacktester 는 신호 발생 봉(t=D1)의 다음봉 시가에
  체결한다. 책의 "D1 종가 매수"는 익일 시가(다음 일봉 open)와 근사적으로 같다고 본다
  (장 막판 종가 vs 익일 시가 갭은 슬리피지로 흡수). 따라서 룰은 D1에서 triggered=True 만 낸다.
- **익절/손절은 백테스터 파라미터로 표현**: take_profit≈0.02~0.03, max_hold_bars=1,
  stop_loss 는 단봉(D1) 저점 기반. BookBacktester 는 stop_loss 를 고정 %로만 받으므로
  룰은 metadata["d1_low"]/["sl_pct_from_d1_low"] 에 단봉저점·권장 손절%를 기록해 둔다
  (정밀 단봉저점 손절은 백테스터 확장 시 사용; 현 프레임에선 고정 stop_loss_pct 근사).
- **시총 < 5,000억 게이트**: 일봉 df 에는 시총 데이터가 없다. ctx["market_cap"](원) 가
  주입되면 검사하고, 없으면 게이트를 건너뛰며 metadata["market_cap_checked"]=False 로 표시.
- **관리종목/우선주 제외**: 별도 플래그 데이터 없음 → universe(거래대금 상위)로 간접 회피.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


@dataclass
class rule_close_betting_setup(Rule):
    """종가배팅 셋업 — D0 장대양봉 + D1 단봉조정 → D1 종가(≈익일 시가) 진입.

    진입(모두 충족):
      [D0 = df.iloc[-2] 장대양봉]
        1. 종가 상승률 (close-open)/open ∈ [body_min, body_max] (예: +7%~+25%)
        2. 거래대금 close*volume >= turnover_min (예: 300억)
        3. 시세 초입(전고점 돌파): D0 종가 > 직전 breakout_lookback 봉(D0 제외)의 고가 최대값
        4. (선택) 시총 < market_cap_max — ctx["market_cap"] 주입 시만 검사

      [D1 = df.iloc[-1] 단봉(신호일)]
        5. 일중 변동폭 (high-low)/D0종가 <= range_max (예: 7%)
        6. 거래량 < D0 거래량 * vol_dryup (예: 30%) — 거래 급감
        7. 위치: D1 저가 >= D0 중간값((D0 open + D0 close)/2) AND D1 종가 <= D0 종가
                 (D0 장대양봉 몸통 상단 절반 안쪽에 머무름)

    청산은 BookBacktester 파라미터(take_profit≈0.02~0.03 / max_hold_bars=1 / stop_loss)로 표현.
    metadata 에 d1_low(단봉저점)·권장 손절%를 기록.
    """

    name: str = "close_betting_setup"
    body_min: float = 0.07            # D0 최소 상승률 +7%
    body_max: float = 0.25            # D0 최대 상승률 +25% (그 이상 추격 위험)
    turnover_min: float = 300e8       # D0 거래대금 ≥ 300억
    breakout_lookback: int = 20       # 시세 초입(전고점 돌파) 판정 룩백
    vol_dryup: float = 0.30           # D1 거래량 < D0 * 0.30
    range_max: float = 0.07           # D1 일중 변동폭 <= 7%
    market_cap_max: float = 5_000e8   # 시총 < 5,000억 (ctx 주입 시만)
    sl_floor_buffer: float = 0.005    # 단봉저점 아래 권장 손절 버퍼(0.5%)

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        # 인덱스 가드: D0(직전봉) + 전고점 룩백 + D1 필요
        if df is None or len(df) < self.breakout_lookback + 2:
            return RuleResult(triggered=False)

        d0 = df.iloc[-2]
        d1 = df.iloc[-1]

        d0_open = float(d0["open"])
        d0_close = float(d0["close"])
        d0_vol = float(d0["volume"])
        if d0_open <= 0 or d0_close <= 0:
            return RuleResult(triggered=False)

        # 1. D0 장대양봉 상승률
        d0_body = (d0_close - d0_open) / d0_open
        if not (self.body_min <= d0_body <= self.body_max):
            return RuleResult(triggered=False)

        # 2. D0 거래대금
        d0_turnover = d0_close * d0_vol
        if d0_turnover < self.turnover_min:
            return RuleResult(triggered=False)

        # 3. 시세 초입 = 전고점 돌파 (D0 제외한 직전 breakout_lookback 봉 고가 최대 < D0 종가)
        prior = df.iloc[-(self.breakout_lookback + 2):-2]
        if len(prior) == 0:
            return RuleResult(triggered=False)
        prior_high = float(prior["high"].max())
        if d0_close <= prior_high:
            return RuleResult(triggered=False)

        # 4. 시총 게이트 (ctx 주입 시만)
        market_cap = ctx.get("market_cap")
        market_cap_checked = False
        if market_cap is not None:
            market_cap_checked = True
            if float(market_cap) >= self.market_cap_max:
                return RuleResult(triggered=False)

        # 5. D1 단봉 변동폭
        d1_high = float(d1["high"])
        d1_low = float(d1["low"])
        d1_close = float(d1["close"])
        d1_vol = float(d1["volume"])
        d1_range = (d1_high - d1_low) / d0_close
        if d1_range > self.range_max:
            return RuleResult(triggered=False)

        # 6. D1 거래량 급감
        if not (d0_vol > 0 and d1_vol < d0_vol * self.vol_dryup):
            return RuleResult(triggered=False)

        # 7. D1 위치: [D0 중간값 ~ D0 종가] 안쪽
        d0_mid = (d0_open + d0_close) / 2.0
        if d1_low < d0_mid:
            return RuleResult(triggered=False)
        if d1_close > d0_close:
            return RuleResult(triggered=False)

        # 단봉저점 기반 권장 손절% (진입가≈D1종가 대비)
        sl_pct_from_d1_low: Optional[float] = None
        if d1_close > 0:
            sl_pct_from_d1_low = max(
                0.0, (d1_close - d1_low) / d1_close + self.sl_floor_buffer
            )

        return RuleResult(
            triggered=True,
            side="buy",
            confidence=68.0,
            reasons=[
                f"close_betting d0_body={d0_body:.2%} turnover={d0_turnover/1e8:.0f}억 "
                f"breakout(>{prior_high:.1f}) d1_range={d1_range:.2%} "
                f"vol_dryup={d1_vol/d0_vol:.2%} pos[{d0_mid:.1f}~{d0_close:.1f}]"
            ],
            metadata={
                "d0_body": d0_body,
                "d0_turnover": d0_turnover,
                "d0_mid": d0_mid,
                "d1_low": d1_low,
                "d1_close": d1_close,
                "sl_pct_from_d1_low": sl_pct_from_d1_low,
                "market_cap_checked": market_cap_checked,
            },
        )


# 책 전체 일봉 규칙
ALL_RULES = [
    rule_close_betting_setup,
]
