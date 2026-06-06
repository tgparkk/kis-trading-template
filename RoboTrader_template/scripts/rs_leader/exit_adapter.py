"""MA20 트레일링 청산 어댑터 (run_portfolio 규약 준수).

스펙 §4 청산 충실도 보강: sl/mh 근사 대신 추세추종 핵심인 *MA 이탈 트레일링* 모델.
청산 우선순위(bar i 종가 기준): stop_loss → ma_break(종가<MA) → max_hold.
take_profit 은 추세추종이라 미사용(고정 익절 없음).

no-lookahead: MA 는 bar i 까지의 종가(df.iloc[lo:i+1]) 만으로 산출. position dict 는
run_portfolio 가 채우는 {entry_idx, entry_price, qty, entry_date}.
RS 음전환 청산은 종목 단독 df 로 불가(횡단면 정보 필요) → 미모델(1차 한계, 리포트 명시).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


class MA20TrailExitAdapter:
    entry_mechanism = "market"

    def __init__(self, ma: int = 20):
        self.ma = ma

    def exit_reason(self, df: pd.DataFrame, i: int, position: dict, params: dict) -> Optional[str]:
        entry_price = position["entry_price"]
        cur_close = float(df.iloc[i]["close"])
        ret = (cur_close - entry_price) / entry_price
        hold_bars = i - position["entry_idx"]

        if ret <= -params["stop_loss_pct"]:
            return "stop_loss"

        # MA 트레일링: 직전 self.ma 봉(현재봉 포함) 평균 아래로 종가 마감 시 추세이탈 청산.
        if i + 1 >= self.ma:
            lo = i - self.ma + 1
            ma_val = float(df["close"].iloc[lo:i + 1].astype(float).mean())
            if cur_close < ma_val:
                return "ma_break"

        if hold_bars >= params["max_hold_bars"]:
            return "max_hold"
        return None
