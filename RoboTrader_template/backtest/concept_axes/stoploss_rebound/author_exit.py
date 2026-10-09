"""ⓐ 저자식 청산 — 사전등록 §6-2·§6-5·§6-7 그대로(🔒 동결 e4d9ee2). 순수 함수 · DB 없음 · `ExitOut` 반환.

공통(두 arm 동일 · §6-3): 진입 = 실제 BUY 체결 · 익절 tp · 보유기간 상한 · 데이터 청산(`SellProbe`) · 일봉 근사 하루 순서
  — `exitsim8` 부품(`entry_day`·`open_phase`·`after_open` → `cap_skip_ledger/sim.py::simulate_exit` 봉 1개)을 그대로 부른다.
고정 손절 비활성: `ExitRules.sl = SL_OFF(1.0)` — 수익률 ≤ −100% 는 닿을 수 없어 갭·장중 손절이 작동하지 않는다(§6 머리).
진입 당일(k=0): `exitsim8.entry_day` 를 같은 규칙(sl 비활성)으로 — 익절 터치만(진입 기준 ②③ 은 `Pos.entry_basis`·`touch_bar`
  로 호출자가 넣는다) · 데이터 청산은 공통. 저자 트리거는 k ≥ 1 부터(§6-5).
저자 손절 트리거(일봉 «종가» · 유효 봉에서만 · 패딩(None) 행 발동 금지 §6-7):
  (a) 종가 수익률 ≤ −20%
  (b) 60일선 «하향 이탈 사건» — 직전 유효 봉 종가 ≥ 그 봉의 SMA60 ∧ 당일 종가 < 당일 SMA60.
      SMA60 = 그날까지 유효 봉 60개 종가 단순평균(원시 close · 진입일 이전 봉 포함). 가용 봉 < 60 이면 (b) 미평가(플래그).
      진입일 종가 < SMA60 인 로트는 종가 ≥ SMA60 인 날(회복) «뒤»부터 (b) 를 켠다.
  (c) 무반응 — k ≥ 10 인 첫 유효 봉에서, 그때까지(k=1..그날) 유효 봉 종가 수익률이 한 번도 +3% 이상이 아니었으면.
  같은 날 복수 트리거 = 1회(트리거 판정일 s 하나 · 사유는 모두 기록).
트리거 뒤: s 다음 KOSPI 거래일부터 5거래일 동안 매일 «시가»에 지분 1/5 — 그날 봉이 None(거래량 0·결측)이면 그 몫을 다음
  유효 봉으로 이월(쌓아서 함께 매도). 익절·데이터 청산·보유기간 상한은 정지. 트리거 전 공통 청산이 같은 날 먼저면 공통 우선
  (장중 청산은 종가 판정보다 앞이다).
관측 기간 H(`horizon`) 밖 날짜는 보지 않는다 — 남은 지분은 호출자가 H 종료 평가(`lots.terminal`)로 값을 매긴다.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Sequence, Tuple

from backtest.concept_axes.ledger8 import exitsim8 as X

SL_OFF = 1.0              # §6 머리 — 닿을 수 없는 손절(고정 손절 비활성)
LOSS_LIMIT = 0.20         # (a) 손실 한도
SMA_N = 60                # (b) 60일선
NO_REACT_K = 10           # (c) 주(主) 판정일 — 5 는 인쇄만(§6-5)
REACT_RATE = 0.03         # (c) «반응» 감각값
SPLIT_N = 5               # 분할 매도 일수 = 지분 1/5

TRIG_LOSS = "loss20"
TRIG_SMA = "sma60_break"
TRIG_NOREACT = "no_react"
EXIT_SPLIT = "author_split"
KIND_SPLIT = "split"

FLAG_SMA_NA = "sma60_na(가용 봉<60)"
FLAG_SPLIT_CARRY = "split_carry"


@dataclass
class Tranche:
    k: int
    day: date
    weight: float
    price: float
    kind: str                     # 공통 청산 사유(tp·max_hold·데이터 청산) 또는 KIND_SPLIT


@dataclass
class AuthorOut(X.ExitOut):
    """`ExitOut` + 분할 내역. status = closed(전량 매도) | open(H 끝 남은 지분 있음) · price/ret_pct = 실현분 가중평균."""
    tranches: List[Tranche] = field(default_factory=list)
    remaining: float = 1.0
    trigger_k: Optional[int] = None
    trigger_date: Optional[date] = None
    triggers: Tuple[str, ...] = ()
    below_sma_at_entry: Optional[bool] = None
    sma_na: bool = False


def _rate(entry: float, px: float) -> float:
    return (float(px) - float(entry)) / float(entry)


def _sma(closes: Sequence[float]) -> Optional[float]:
    if len(closes) < SMA_N:
        return None
    return sum(closes[-SMA_N:]) / SMA_N


def entry_below_sma(pre_closes: Sequence[float], entry_close: Optional[float]) -> Optional[bool]:
    """진입일 종가 < 진입일 SMA60 인가(봉인 단계 인쇄 «진입 시 SMA60 아래» · ⓐ 의 (b) 켜기 규칙). 모르면 None."""
    if entry_close is None:
        return None
    s = _sma([float(c) for c in pre_closes] + [float(entry_close)])
    return None if s is None else float(entry_close) < s


def _finish(pos: X.Pos, tranches: List[Tranche], sold: int, flags: List[str], reason_closed: str,
            trig_k: Optional[int], trig_d: Optional[date], trig: Tuple[str, ...], below: Optional[bool],
            sma_na: bool) -> AuthorOut:
    remaining = (SPLIT_N - sold) / SPLIT_N
    w = sum(t.weight for t in tranches)
    px = sum(t.weight * t.price for t in tranches) / w if w > 0 else None
    last = tranches[-1] if tranches else None
    closed = sold >= SPLIT_N
    return AuthorOut(status="closed" if closed else "open",
                     reason=reason_closed if closed else X.EXIT_OPEN,
                     exit_date=last.day if last else None, price=px,
                     ret_pct=_rate(pos.entry_price, px) * 100.0 if px is not None else None,
                     hold_days=last.k if last else None, flags=list(flags), phase="",
                     tranches=tranches, remaining=remaining, trigger_k=trig_k, trigger_date=trig_d, triggers=trig,
                     below_sma_at_entry=below, sma_na=sma_na)


def author_exit(pos: X.Pos, rules: X.ExitRules, path: X.PathT, probe: X.Probe, pre_closes: Sequence[float],
                horizon: int, no_react_k: int = NO_REACT_K) -> AuthorOut:
    """로트 1개 ⓐ — path[0] = 진입일(k=0) · None 봉 = 거래 불가(거래량 0·결측) · `pre_closes` = 진입일 «전» 유효 봉 종가(오름차순).

    `rules` 는 ⓑ 와 같은 `resolve_live_tp_sl` 값을 그대로 받는다(sl 은 여기서 SL_OFF 로 바꾼다).
    """
    ra = dataclasses.replace(rules, sl=SL_OFF)
    if not path:
        return _finish(pos, [], 0, ["no_path"], X.EXIT_OPEN, None, None, (), None, False)
    closes: List[float] = [float(c) for c in pre_closes]
    _, d0, bar0 = path[0]
    touch_ok = pos.entry_basis == X.BASIS_D_OPEN or pos.touch_bar is not None
    flags: List[str] = [] if touch_ok else [X.FLAG_NO_D_TOUCH]
    sma_na = False
    ex0 = X.entry_day(pos, ra, bar0, probe)
    if ex0 is not None:
        flags.extend(ex0.flags)
        return _finish(pos, [Tranche(0, ex0.exit_date or d0, 1.0, float(ex0.price), ex0.reason)], SPLIT_N, flags,
                       ex0.reason, None, None, (), None, False)
    below: Optional[bool] = None
    prev_close: Optional[float] = None
    prev_sma: Optional[float] = None
    if bar0 is not None:
        below = entry_below_sma(closes, bar0.close)
        closes.append(float(bar0.close))
        prev_close, prev_sma = float(bar0.close), _sma(closes)
        sma_na = prev_sma is None
    armed = below is False                      # 진입 시 아래(또는 모름)면 회복(종가 ≥ SMA60) 뒤부터
    reacted = False
    noreact_done = False
    pending_mh = False
    trig_k: Optional[int] = None
    trig_d: Optional[date] = None
    trig: Tuple[str, ...] = ()
    sale_ks: Tuple[int, ...] = ()
    due = 0
    sold = 0
    tranches: List[Tranche] = []
    for k, day, bar in list(path)[1:]:
        if k > horizon:
            break
        if trig_k is None:
            if bar is None:
                flags.append(f"{X.FLAG_BAR_MISSING}:{day}")
                if k >= ra.max_hold_days:
                    pending_mh = True
                continue
            ex = X.open_phase(pos, ra, k, bar, pending_mh) or X.after_open(pos, ra, k, day, bar, probe)
            if ex is not None:                  # 공통 청산(트리거 전) — 전량 · ⓑ 와 같은 규칙
                flags.extend(ex.flags)
                return _finish(pos, [Tranche(k, ex.exit_date or day, 1.0, float(ex.price), ex.reason)], SPLIT_N,
                               flags, ex.reason, None, None, (), below, sma_na)
            c = float(bar.close)
            closes.append(c)
            s = _sma(closes)
            if s is None:
                sma_na = True
            hits: List[str] = []
            if _rate(pos.entry_price, c) <= -LOSS_LIMIT:
                hits.append(TRIG_LOSS)
            if (armed and s is not None and prev_close is not None and prev_sma is not None
                    and prev_close >= prev_sma and c < s):
                hits.append(TRIG_SMA)
            if s is not None and c >= s:
                armed = True
            if _rate(pos.entry_price, c) >= REACT_RATE:
                reacted = True
            if not noreact_done and k >= no_react_k:
                noreact_done = True
                if not reacted:
                    hits.append(TRIG_NOREACT)
            prev_close, prev_sma = c, s
            if hits:
                trig_k, trig_d, trig = k, day, tuple(hits)
                sale_ks = tuple(range(k + 1, k + 1 + SPLIT_N))
            continue
        if k in sale_ks:
            due += 1
        if due == 0:
            continue
        if bar is None:
            flags.append(f"{FLAG_SPLIT_CARRY}:{day}")
            continue
        tranches.append(Tranche(k, day, due / SPLIT_N, float(bar.open), KIND_SPLIT))
        sold += due
        due = 0
        if sold >= SPLIT_N:
            break
    if sma_na:
        flags.append(FLAG_SMA_NA)
    return _finish(pos, tranches, sold, flags, EXIT_SPLIT, trig_k, trig_d, trig, below, sma_na)
