"""arm A 단계 분류 — 순수(DB·로그 파일 없음). (날짜, 전략, 종목)이 라이브에서 «어디서 멈췄나».

단계(스펙 「결정」 절 스키마 — 후보/신호/캡/현금/체결 + 기타 게이트):
  fill         실제 체결(virtual_trading_records BUY)
  cash         `[매수거절] 수량부족` · VTM `전략 가상 잔고 부족` — 또는 계기 줄이 없고 재구성 수량 0(recon)
  gate         매수신호 뒤 실행 경로에서 막힘 — other_holder · market_gate · daily_loss · band · throttle · other
  unexplained  매수신호는 있는데 막힌 계기 줄이 없다(DEBUG 게이트 — 25분 매수 쿨다운·종목정보 없음·VI · 로그 버퍼)
  cap          `[캡]` max_positions/daily_trades(3전략 · 09-16~) 또는 체결 원장 시간선상 빈자리 없음(앞 순위 매수로 소진 포함 · classify.classify_candidate)
  held         09:00 에 이 전략이 이미 보유(classify.classify_candidate) → generate_signal 이 매도 분기로 간다
  signal       룰 미충족(로그 N) 또는 판단 근거 없음(재현값 표기)
증거 `basis`: log(계기 줄) · timeline(체결 원장 재구성) · vtr · recon(수량 재구성) · replay(재현).
하루 동안 여러 게이트를 만나면 «라이브 실행 경로에서 가장 깊이 간 곳»을 대표로 두고 전부 `detail` 에 남긴다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

from backtest.concept_axes.minervini.cap_skip_ledger.classify import Trade

from . import logscan8 as L8

STAGE_CANDIDATE = "candidate"
STAGE_SIGNAL = "signal"
STAGE_HELD = "held"
STAGE_CAP = "cap"
STAGE_GATE = "gate"
STAGE_CASH = "cash"
STAGE_UNEXPLAINED = "unexplained"
STAGE_FILL = "fill"

GATE_KIND: Dict[str, str] = {
    L8.G_QTY: STAGE_CASH, L8.G_BALANCE: STAGE_CASH,
    L8.G_HELD_ANY: "other_holder", L8.G_OWNED: "other_holder",
    L8.G_CRASH: "market_gate", L8.G_REGIME: "market_gate",
    L8.G_BUYSTOP: "band", L8.G_BAND_ABOVE: "band", L8.G_BAND_BELOW: "band", L8.G_LIMITUP: "band",
    L8.G_THROTTLE: "throttle",
    L8.G_DAILY_LOSS: "daily_loss",
    L8.G_REJECT_OTHER: "other", L8.G_NO_PRICE: "other", L8.G_UNFILLED: "other",
}
# 라이브 실행 경로 순서: core/trading_context.py:351(급락) · :366(국면) · :381-396(소유) · :428-436(일일손실) · :438-453(매수스톱) ·
# :466-482(상한가) · :484-515(진입억제) → bot/trading_analyzer.py:127-130(보유 중 무시 · 127 조회 · 128-130 판정) → 엔진 :356-430
# (데이터부족·현재가·밴드 하회·밴드 이탈·수량부족) → VTM 잔고(execute_virtual_buy) → 미체결
GATE_DEPTH: Tuple[str, ...] = (
    L8.G_CRASH, L8.G_REGIME, L8.G_OWNED, L8.G_DAILY_LOSS, L8.G_BUYSTOP, L8.G_LIMITUP, L8.G_THROTTLE, L8.G_HELD_ANY,
    L8.G_REJECT_OTHER, L8.G_NO_PRICE, L8.G_BAND_BELOW, L8.G_BAND_ABOVE, L8.G_QTY, L8.G_BALANCE, L8.G_UNFILLED)

FUNNEL_COLS = ["date", "strategy", "code", "stage", "result", "n", "first_ts", "last_ts", "basis"]


@dataclass
class AFacts:
    d: date
    folder: str
    code: str
    held_live: bool
    no_slot_live: bool
    slot_note: str
    cap_log: Dict[str, L8.Fold]          # StratDay.cap_blocking(code) — timeframe 제외
    buysig: Optional[L8.Fold]
    gates: Dict[str, L8.Fold]            # StratDay.gates_for(code)
    filled: Optional[Trade]
    signal_log: str                      # Y | N | NA
    signal_replay: str                   # Y | N
    a_qty_upper: Optional[int] = None    # sizing.arm_a_qty(기준가, per_stock, cap).qty — 잔고 항 제외 상한


@dataclass
class AStop:
    stage: str
    result: str
    basis: str
    detail: str


def deepest_gate(gates: Dict[str, L8.Fold]) -> Optional[str]:
    seen = [g for g in GATE_DEPTH if g in gates]
    return seen[-1] if seen else None


def _fold_txt(name: str, f: L8.Fold) -> str:
    return f"{name}×{f.n}({f.first}~{f.last})"


def classify_a(f: AFacts) -> AStop:
    if f.filled is not None:
        return AStop(STAGE_FILL, "Y", "vtr", f"{f.filled.buy_ts:%H:%M:%S} @{f.filled.buy_price:g}")
    if f.buysig is not None:
        g = deepest_gate(f.gates)
        detail = " ".join(_fold_txt(k, v) for k, v in sorted(f.gates.items()))
        if g is not None:
            kind = GATE_KIND[g]
            return AStop(STAGE_CASH, g, "log", detail) if kind == STAGE_CASH else AStop(STAGE_GATE, kind, "log", detail)
        if f.a_qty_upper == 0:
            return AStop(STAGE_CASH, "qty_zero_recon", "recon",
                         "계기 줄 없음 · 재구성 수량 0(복리 per_stock·종목당 상한 기준 — 잔고 미반영 상한)")
        return AStop(STAGE_UNEXPLAINED, "signal_Y_no_trace", "log",
                     "DEBUG 게이트(25분 매수 쿨다운·종목정보 없음·VI) 또는 로그 버퍼 — 계기 줄 없음")
    if f.held_live:
        return AStop(STAGE_HELD, "Y", "timeline", "09:00 이 전략 보유 → generate_signal 매도 분기")
    if f.cap_log:
        return AStop(STAGE_CAP, "+".join(sorted(f.cap_log)), "log",
                     " ".join(_fold_txt(k, v) for k, v in sorted(f.cap_log.items())))
    if f.no_slot_live:
        return AStop(STAGE_CAP, "no_slot", "timeline", f.slot_note)
    if f.signal_log == "N":
        return AStop(STAGE_SIGNAL, "N", "log", "on_tick 평가 · [on_tick] 매수신호 없음")
    return AStop(STAGE_SIGNAL, f.signal_replay, "replay", "라이브 평가 여부 불명 — 재현 신호")


def _row(f: AFacts, stage: str, result: str, n: str, first: str, last: str, basis: str) -> Dict[str, str]:
    return dict(date=f.d.isoformat(), strategy=f.folder, code=f.code, stage=stage, result=result,
                n=n, first_ts=first, last_ts=last, basis=basis)


def funnel_rows(f: AFacts) -> List[Dict[str, str]]:
    """(날짜, 전략, 종목, 단계, 결과) + n_evals/first_ts/last_ts 로 접힌 행(스펙 결정 절 스키마)."""
    rows = [_row(f, STAGE_CANDIDATE, "Y", "1", "", "", "e6")]
    if f.buysig is not None:
        rows.append(_row(f, STAGE_SIGNAL, "Y", str(f.buysig.n), f.buysig.first, f.buysig.last, "log"))
    elif f.signal_log == "N":
        rows.append(_row(f, STAGE_SIGNAL, "N", "", "", "", "log"))
    else:
        rows.append(_row(f, STAGE_SIGNAL, f"replay:{f.signal_replay}", "", "", "", "replay"))
    if f.held_live:
        rows.append(_row(f, STAGE_HELD, "Y", "", "", "", "timeline"))
    for r, fold in sorted(f.cap_log.items()):
        rows.append(_row(f, STAGE_CAP, r, str(fold.n), fold.first, fold.last, "log"))
    if f.no_slot_live and not f.cap_log:
        rows.append(_row(f, STAGE_CAP, "no_slot", "", "", "", "timeline"))
    for g in (x for x in GATE_DEPTH if x in f.gates):
        fold = f.gates[g]
        stage = STAGE_CASH if GATE_KIND[g] == STAGE_CASH else STAGE_GATE
        rows.append(_row(f, stage, g, str(fold.n), fold.first, fold.last, "log"))
    if f.filled is not None:
        ts = f"{f.filled.buy_ts:%H:%M:%S}"
        rows.append(_row(f, STAGE_FILL, "Y", "1", ts, ts, "vtr"))
    return rows
