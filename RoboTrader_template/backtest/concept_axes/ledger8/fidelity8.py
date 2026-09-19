"""충실도 — 순수 판정·집계(DB 없음). 라이브 계기와 재현을 대조해 «원장을 얼마나 믿을지»를 수치로 낸다.

🔒 기준값은 결과를 보고 바꾸지 않는다. 미달은 숨기지 않고 표에 LOW 로 적는다.
   신호 충실도는 B 계산 «전에» 본다(스펙 §4-2) — run `--stage signal`.
🔑 신호 일치는 방향을 나눠 본다. 판정 가능 행은 대부분 «로그 Y» 라 Y 방향만 검증되기 쉽다 — 「라이브 N 인데
   재현 Y」 오류율(N 방향)은 로그 N 표본이 있어야 잰다. 표본이 모자라면 «판정 불가»로 남긴다(critic 2026-09-19).
🔑 «평가 가능»(= 로그로 N 을 말할 수 있다) 규칙은 `slot_verdict` 한 곳에 순수 함수로 둔다. 변경 이력(v1→v2→v3)은
   계획서 「계획 검증 실행」 절에 있고, 세 규칙의 결과를 모두 보고서에 싣는다(채택 = v3).
"""
from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backtest.concept_axes.minervini.cap_skip_ledger import classify as C

SIG_AGREE_MIN = 0.90      # 전략별 신호 일치율(방향별 · 평가 가능 행) 기준
EXIT_REASON_MIN = 0.70    # 전략별 청산 사유 일치율(실제 청산된 건) 기준
FID_MIN_N = 5             # 분모가 이보다 작으면 «판정 불가»

LOG_Y, LOG_N, LOG_NA = "Y", "N", "NA"
OUT_AGREE_Y = "agree_Y"
OUT_AGREE_N = "agree_N"
OUT_REPLAY_ONLY = "replay_only"
OUT_LOG_ONLY = "log_only"
OUT_NA = "na"
EVALUABLE_STATES = (C.STATE_SLOT, C.STATE_BOUGHT)


def signal_log_state(buysig_seen: bool, ontick_ran: bool, evaluable: bool) -> str:
    """라이브 로그가 말하는 그날 신호.

    Y  = 그날 `[on_tick] 매수신호: CODE(` 가 한 줄이라도 있다(무스로틀 — strategies/base.py:720-726).
    N  = 그 전략 on_tick 이 그날 돌았고 평가 가능(`slot_verdict`)했는데 줄이 없다.
    NA = 그 밖 — 보유·캡이라 `_check_buy` 까지 안 갔을 수 있거나 로그가 없다.
    """
    if buysig_seen:
        return LOG_Y
    if ontick_ran and evaluable:
        return LOG_N
    return LOG_NA


def decide_signal(replay: str, log: str) -> Tuple[str, str]:
    """(사용 신호, 근거). 라이브 로그가 판정 가능하면 로그(그 시점 DB), 아니면 재현(지금 DB)."""
    if log in (LOG_Y, LOG_N):
        return log, "log"
    return replay, "replay"


def signal_outcome(replay: str, log: str) -> str:
    if log == LOG_NA:
        return OUT_NA
    if replay == "Y" and log == LOG_Y:
        return OUT_AGREE_Y
    if replay == "N" and log == LOG_N:
        return OUT_AGREE_N
    return OUT_REPLAY_ONLY if replay == "Y" else OUT_LOG_ONLY


# ── «평가 가능» 규칙 (v1 · v2 · v3 — 채택 v3) ──────────────────────────────────
@dataclass
class SlotVerdict:
    state: str        # v3(채택) — classify.STATE_BOUGHT/HELD/NO_SLOT/SLOT
    state_v2: str     # v2 = cap_skip_ledger classify_candidate 그대로(민감도)
    eval_v1: bool     # v1 = 09:02 한 시점: 그 시각 미보유 ∧ 빈자리 구간 안(민감도)
    note: str


def slot_verdict(trades: Sequence[C.Trade], d: date, k: int, mdt: int, code: str, list_order: Sequence[str],
                 ontick_times: Sequence[str], first_tick: time = time(9, 2, 0)) -> SlotVerdict:
    """그날 라이브가 이 종목을 `_check_buy` 까지 평가할 수 있었나(체결 원장 시간선 · 순수).

    v2 = `classify.classify_candidate`(cap_skip_ledger/classify.py:176-205): bought > held(09:00 보유) >
         no_slot(장 전체 빈자리 없음 «또는 모든 빈자리가 목록상 앞 순위 매수로 닫힘») > slot_available.
    v3 = v2 의 no_slot 중 «빈자리 구간 안에서 그 전략 on_tick 이 한 번 «통째로» 돌았다»면 slot_available —
         on_tick 은 한 번 돌 때 목록 전부를 평가하고, 그 한 번이 빈자리 동안 돌았으면 이 종목도 자리 있는 상태로
         평가됐다. (반례: ma5 09-11 006910 — 빈자리 09:00:00~09:28:07 · 첫 신호 09:03:37)
         `[on_tick] 매수검토` 요약 줄은 on_tick «끝»(매도 루프 뒤 · strategies/base.py:763-766)에 찍히므로
         요약 시각 t 하나로는 매수 루프 시각을 모른다 — 그 on_tick 의 매도 루프(또는 그 사이 position_monitor)가
         빈자리를 연 경우 매수 루프는 구간 «전»에 돌았다(critic 2차 A2). 그래서 on_tick 의 시작 하한 = 같은
         전략의 «직전» 요약 시각 p 를 쓰고 «구간 시작 ≤ p ≤ t < 구간 끝»일 때만 인정한다. 그날 첫 요약 줄은
         p = 장 시작 09:00:00 — main.py:433 루프가 `is_market_open()` 거짓이면 on_tick 을 부르지 않는다(하한으로 안전).
         소진 매수를 낸 on_tick 의 요약 줄은 소진 시각 «뒤»라 스스로 제외된다.
    v1 = 09:02 한 시점 규칙(최초안) — 첫 틱 안에서 앞 순위 매수가 자리를 채우는 경우를 못 본다.
    """
    n0, windows = C.slot_windows_detail(trades, d, k, mdt)
    state_v2, note = C.classify_candidate(code, d, trades, windows, list_order=list_order)
    t1 = datetime.combine(d, first_tick)
    held_t1 = any(x.code == code for x in C.open_at(trades, t1))
    eval_v1 = (not held_t1) and any(w[0] <= first_tick < w[1] for w in windows)
    state = state_v2
    if state_v2 == C.STATE_NO_SLOT:
        hits: List[Tuple[str, str]] = []
        prev = C.SESSION_OPEN.strftime("%H:%M:%S")      # 그날 첫 on_tick 의 시작 하한 = 장 시작
        for t in sorted(ontick_times):
            if any(w[0].strftime("%H:%M:%S") <= prev <= t < w[1].strftime("%H:%M:%S") for w in windows):
                hits.append((prev, t))
            prev = t
        if hits:
            state = C.STATE_SLOT
            note += f" · 빈자리 구간 안 on_tick 1회 전체 {hits[0][0]}~{hits[0][1]}(직전 요약~요약 · v3: 평가 가능)"
    return SlotVerdict(state, state_v2, eval_v1,
                       f"{note} · K={k} 09:00보유={n0} 빈자리={C.fmt_windows(windows) or '(없음)'}")


# ── 빈티지(거래량 재기록) ─────────────────────────────────────────────────────
_VOL_RE = re.compile(r"vol=(\d+)/(\d+)")


def day_volume_vintage(live_reasons: Optional[str], replay_reasons: Optional[str]) -> Optional[float]:
    """daytrading 사유 `vol=a/b` 의 a(D-1 거래량) — (재현 a ÷ 라이브 a − 1). 라이브 스캔 뒤 재기록된 폭."""
    a = _VOL_RE.search(live_reasons or "")
    b = _VOL_RE.search(replay_reasons or "")
    if not a or not b or float(a.group(1)) <= 0:
        return None
    return float(b.group(1)) / float(a.group(1)) - 1.0


def vintage_fragile(bias: Optional[str], signal: str, ratio: Optional[float], threshold: Optional[float],
                    vmax: Optional[float]) -> str:
    """재현 신호가 «관측 빈티지 폭» 안에서 뒤집힐 수 있었나. 반환 'Y' 취약 · 'N' 안전 · '' 재료 없음.

    재기록은 거래량을 «늘린다»(관측). 그래서 방향이 정해져 있다.
      bias='Y'(daytrading: 비율 ≥ 문턱이 Y) — 재현 Y 이고 비율/(1+vmax) < 문턱 ⇒ 라이브는 N 이었을 수 있다.
      bias='N'(minervini: 비율 ≤ 문턱이 Y) — 재현 N 이고 비율/(1+vmax) ≤ 문턱 ⇒ 라이브는 Y 였을 수 있다.
    반대쪽(day 재현 N · min 재현 Y)은 재기록이 일어나도 뒤집히지 않는다 → 'N'.
    ⚠️ vmax 를 비율 전체에 거는 것은 상한(보수적)이다 — minervini 는 D-1 봉 하나가 recent 10봉 평균에 1/10 로만 든다.
    """
    if not bias or ratio is None or threshold is None or vmax is None:
        return ""
    live_min = ratio / (1.0 + max(vmax, 0.0))
    if bias == "Y" and signal == "Y":
        return "Y" if live_min < threshold else "N"
    if bias == "N" and signal == "N":
        return "Y" if live_min <= threshold else "N"
    return "N"


def _group(row: Dict[str, Any]) -> str:
    mode = row.get("mode") or ""
    return f"{row['strategy']}[{mode}]" if mode else str(row["strategy"])


def signal_table(rows: Sequence[Dict[str, Any]], outcome_key: str = "outcome") -> List[Dict[str, Any]]:
    """전략별(rs_leader 는 모드별) 신호 일치 — 방향을 나눈다.

    Y 방향 = 로그 Y 행 중 재현도 Y = agree_Y / (agree_Y + log_only)
    N 방향 = 로그 N 행 중 재현도 N = agree_N / (agree_N + replay_only) — 「라이브 N 인데 재현 Y」 오류율의 거울
    판정: 분모 ≥ FID_MIN_N 인 방향만 기준과 비교 · 하나라도 미달 LOW · 둘 다 표본 부족이면 «판정 불가».
    `bought` = 판정 가능 행 중 실제 체결(자명한 Y/Y) 수. `outcome_key` 로 민감도 규칙(v1·v2)의 결과도 같은 표로 낸다.
    """
    groups: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for r in rows:
        key = _group(r)
        g = groups.setdefault(key, dict(group=key, n=0, evaluable=0, agree_Y=0, agree_N=0, replay_only=0,
                                        log_only=0, bought=0, reasons_eq=0, ref_eq=0))
        g["n"] += 1
        o = r[outcome_key]
        if o == OUT_NA:
            continue
        g["evaluable"] += 1
        g[o] += 1
        g["bought"] += int(r.get("slot_state") == C.STATE_BOUGHT)
        if o == OUT_AGREE_Y:
            g["reasons_eq"] += int(r.get("reasons_equal") == "Y")
            g["ref_eq"] += int(r.get("ref_equal") == "Y")
    out: List[Dict[str, Any]] = []
    for g in groups.values():
        g["y_n"] = g["agree_Y"] + g["log_only"]
        g["n_n"] = g["agree_N"] + g["replay_only"]
        g["y_rate"] = g["agree_Y"] / g["y_n"] if g["y_n"] else None
        g["n_rate"] = g["agree_N"] / g["n_n"] if g["n_n"] else None
        g["rate"] = (g["agree_Y"] + g["agree_N"]) / g["evaluable"] if g["evaluable"] else None
        dirs = (("Y", g["y_n"], g["y_rate"]), ("N", g["n_n"], g["n_rate"]))
        judged = [(nm, r_) for nm, n_, r_ in dirs if n_ >= FID_MIN_N]
        g["verdict_note"] = " · ".join(f"{nm} 방향 판정 불가(n={n_}<{FID_MIN_N})" for nm, n_, _ in dirs
                                       if n_ < FID_MIN_N)
        if not judged:
            g["verdict"] = "판정 불가"
        elif any(r_ < SIG_AGREE_MIN for _, r_ in judged):
            g["verdict"] = "LOW"
        else:
            g["verdict"] = "ok"
        out.append(g)
    return out


# ── ③ 청산 · 익절손절 · 진입가 ─────────────────────────────────────────────
# 실제 매도 사유(vtr.reason) → 시뮬 사유 코드. position_monitor 문자열(:282·:317-320·:330-333·:229-244)과
# 전략 매도 신호 사유(', '.join(signal.reasons) — 각 전략 evaluate_sell_conditions)를 앞머리로 가른다.
_ACTUAL_RULES = (
    (re.compile(r"^목표 익절 도달"), "tp"),
    (re.compile(r"^손절 실행"), "sl"),
    (re.compile(r"^보유기간 \d+일 초과"), "max_hold"),
    (re.compile(r"^최대 보유일 초과"), "max_hold"),
    (re.compile(r"^EMA\d+ trailing 이탈"), "trail_ema"),
    (re.compile(r"^EMA\d+ 추세반전"), "trend_flip"),
    (re.compile(r"^MA\d+ trailing 이탈"), "trail_ma"),
    (re.compile(r"^MA\d+×[\d.]+ 회복"), "ma_recovery"),
    (re.compile(r"^MA\d+ 이탈"), "ma_break"),
    (re.compile(r"^장기보유 종목"), "stale"),
)


def actual_reason(text: Optional[str]) -> str:
    t = (text or "").strip()
    for rx, code in _ACTUAL_RULES:
        if rx.match(t):
            return code
    return f"other:{t[:20]}"


def exit_outcome(actual: str, actual_date: Optional[date], sim: str, sim_date: Optional[date]) -> str:
    if actual == "open" and sim == "open":
        return "both_open"
    if actual == "open":
        return "sim_only_closed"
    if sim == "open":
        return "actual_only_closed"
    if actual == sim:
        return "Y" if actual_date == sim_date else "reason_only"
    return "N"


def exit_table(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """전략별 청산 일치. 분모 = «실제 청산된» 건(actual_reason != open) — 시뮬만 열려 있으면 불일치로 센다."""
    groups: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for r in rows:
        g = groups.setdefault(r["strategy"], dict(strategy=r["strategy"], n=0, closed=0, Y=0, reason_only=0, N=0,
                                                  actual_only_closed=0, sim_only_closed=0, both_open=0, same_day=0))
        g["n"] += 1
        g[r["outcome"]] += 1
        if r["actual_reason"] != "open":
            g["closed"] += 1
            g["same_day"] += int(r.get("same_day_actual") == "Y")
    out: List[Dict[str, Any]] = []
    for g in groups.values():
        c = g["closed"]
        g["reason_rate"] = (g["Y"] + g["reason_only"]) / c if c else None
        g["full_rate"] = g["Y"] / c if c else None
        if c < FID_MIN_N:
            g["verdict"] = f"판정 불가(n={c}<{FID_MIN_N})"
        else:
            g["verdict"] = "ok" if g["reason_rate"] >= EXIT_REASON_MIN else "LOW"
        out.append(g)
    return out


def rates_equal(a: Optional[float], b: Optional[float]) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) < 1e-9


def tp_sl_table(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """전략별 — 체결 원장 BUY 의 target_profit_rate/stop_loss_rate 와 엔진 경로 값 일치 건수."""
    groups: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for r in rows:
        if r.get("tp_sl_match") not in ("Y", "N"):
            continue
        g = groups.setdefault(r["strategy"], dict(strategy=r["strategy"], n=0, match=0))
        g["n"] += 1
        g["match"] += int(r["tp_sl_match"] == "Y")
    return list(groups.values())


def entry_diff_stats(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """진입차% = (가상 진입가 ÷ 실제 체결가 − 1)×100 · + 면 가상이 비싸다. 전략별 + (전체)."""
    groups: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for r in rows:
        if not r.get("entry_diff_pct"):
            continue
        x = float(r["entry_diff_pct"])
        for key in (r["strategy"], "(전체)"):
            g = groups.setdefault(key, dict(strategy=key, n=0, s=0.0, a=0.0, positive=0, n_first=0, s_first=0.0))
            g["n"] += 1
            g["s"] += x
            g["a"] += abs(x)
            g["positive"] += int(x > 0)
            if r.get("first_tick") == "Y":
                g["n_first"] += 1
                g["s_first"] += x
    return [dict(strategy=g["strategy"], n=g["n"], signed_mean=g["s"] / g["n"], abs_mean=g["a"] / g["n"],
                 positive=g["positive"], n_first=g["n_first"],
                 signed_mean_first=(g["s_first"] / g["n_first"] if g["n_first"] else None))
            for g in groups.values()]
