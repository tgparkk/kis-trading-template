"""summary.md — 사람용 요약(순수 · CSV 모양 dict 행만 받는다 · DB 없음).

답할 것(스펙 「결정」 절):
  ① A vs B1 — 자원 제약(캡·현금)이 잘라낸 표본 규모 + 그 종목 성과(시뮬 대 시뮬: A_sim vs B1 · A_actual 병기)
  ② B1 vs B2 — 합산 여부만으로 결과 차이 ⇒ 차이 큰 전략 = 중복 처리를 따로 정할 전략
  ③ 평단 이동으로 손절/익절이 뒤집힌 건수(+ D4 반대편: 보유기한 시계 리셋)
  ④ 전략별 중복 신호 통계(rs_leader 로트 분포)
  ⑤ 충실도(신호 Y·N 방향 · 규칙 민감도 · 재현 비중·빈티지 · 청산 · 진입가 · 익절손절) — envelope·rs_leader 필수
🔴 총자산·누적수익률·자본 분모 % 를 쓰지 않는다 · 금액 = 원 단위 정수 · % = 소수 2자리 · 실현/평가 분리.
🔑 실행 시각·git SHA 는 넣지 않는다(run_meta.json) — 같은 입력이면 같은 바이트. 문장은 표에서 만든다(고정 문구 금지).
🔑 본 집계(§2~§5)는 main 실행만 쓴다 — `lots_b1.csv` arm=B1(tier main) · `accounts_b2.csv`. A3 상한(arm=B1_ub 는 main 로트를
   «다시» 담는다 · `accounts_b2_ub.csv`) · D3 반대편(B1_nogate) · D1 11~20위(B1_ext)는 §6-1 에 따로 적고 합치지 않는다.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import arms as A
from . import exitsim8 as X
from . import fidelity8 as F
from . import registry as R

BANNER = ("> **관측 원장이다 — 판정 근거로 쓰지 말 것.** 일봉 근사 · gross(수수료·세금 없음) · "
          "B 는 자본 분모가 없는 세계라 합계는 «원»과 «명목 가중 %»(Σ손익÷Σ명목)로만 적는다.")
A_GROUPS = (("fill", "A 체결"), ("held", "A 이미 보유"), ("cap", "A 캡(K·일일 체결)"),
            ("cash", "A 현금(수량부족·잔고)"), ("gate:other_holder", "A 타전략 보유"),
            ("gate:market_gate", "A 시장급락"), ("gate:daily_loss", "A 일일손실한도"),
            ("gate:band", "A 밴드·매수스톱"), ("gate:throttle", "A 진입억제"), ("gate:other", "A 기타 게이트"),
            ("unexplained", "A 계기 없음"), ("signal", "A 신호 없음·불명"))
RESOURCE_GROUPS = ("cap", "cash")
PERF_HDR = ["건수", "청산/보유", "청산 승", "청산 평균%", "실현 손익(원)", "평가 손익(원)", "명목가중%"]
# D5 표시 값 — run.py 의 D5_* 와 같다(test_report 가 대조한다 · run 이 report 를 import 하므로 여기선 run 을 import 하지 않는다).
D5_THROTTLE = "throttle"                       # 진입억제 줄이 있고 라이브가 못 샀다 → 멈춘 단계로 다시 가른다(throttle_split)
D5_THROTTLE_DELAY = "throttle_delay"           # 진입억제 줄이 있으나 라이브가 결국 샀다(A 체결) — 지연
D5_COOLDOWN_UNKNOWN = "buy_cooldown(관측 불가)"
D5_DAILY_LOSS = "daily_loss"
D5_LABELS = ((D5_COOLDOWN_UNKNOWN, "25분 매수 쿨다운 — 관측 불가"), (D5_DAILY_LOSS, "일일손실한도 — 로그"))  # 진입억제 제외
ARM_B1, ARM_UB, ARM_NOGATE, ARM_EXT = "B1", "B1_ub", "B1_nogate", "B1_ext"   # run.build_arms 의 lots_b1.csv arm 값
SCN_MAIN = "본 집계(main)"
SCN_UB = "A3 상한(main + 분봉 없음 상한)"
SCN_ALLDAY = "D3′ 민감도 — 하루 종일 막았으면"
SCN_NOGATE = "D3 반대편 — 게이트가 없었다면(차단 행만 09:02)"
SCN_EXT = "D1 11~20위(ext)"
LIFTED_BASES = (X.BASIS_LIFT, X.BASIS_LIVE_FILL)   # 09:02 에 급락 게이트로 막혔다가 해제 뒤 산 본 집계 로트
LS8_DAY = "daytrading_3methods_breakout"   # livesignal8.DAY 와 같은 값 — report 는 라이브 모듈을 import 하지 않는다
LS8_MIN = "minervini_volume_dryup"         # livesignal8.MIN
RULES = (("outcome_v1", "v1 09:02 한 시점"), ("outcome_v2", "v2 classify_candidate"),
         ("outcome", "v3 v2+빈자리 구간 on_tick(채택)"))
RULE_SHORT = {"outcome_v1": "v1(옛 09:02)", "outcome_v2": "v2(classify_candidate)"}
LIMITS = [
    "B 진입 = D 09:02 한 번(D 시가 · 시가가 밴드 밖이고 장중 복귀면 경계값 · 장중 내내 밖이면 불가). 라이브는 첫 틱 이후 "
    "실시간가다. 사장님 규칙 «후보 통과 종목은 전부 산다»에 따라 진입억제(60초·사이클 3건)·25분 매수 쿨다운·VI·"
    "일일손실한도는 B 에 적용하지 않고, 라이브였다면 걸렸을 건만 §6-3 D5 표로 따로 센다 — 진입억제는 멈춘 단계로 세 갈래, "
    "25분 쿨다운은 «관측 불가» 표시만(슬롯 객체 단위라 막힘을 확정할 수 없다), VI 는 DEBUG 로그라 관측 불가.",
    "D3′ 급락 게이트 = «풀린 뒤 산다»: 09:02 에 막혀 있으면 로그 `[시장방향성필터]` 시간선에서 게이트가 «열린» 구간"
    "(재차단 구간 제외) 안의 첫 밴드 안 분봉 가격(`minute_candles`)에 산다. A_sim(실제 매수)도 같은 경로를 탄다. "
    "열린 구간 안 분봉이 없는 행(`no_minute_data` · 분봉 0개 포함)은 "
    "«안 산 것»이 아니라 «모른다»다 — 본 집계에서 빼고(하한 = 안 삼) D 일봉 상한(tier `lift_ub`)을 §6-2 에 나란히 싣는다. "
    "상한은 체결 시각을 몰라 재차단 구간 체결을 배제하지 못한다. 단 분봉이 없어도 라이브가 해제 뒤 실제로 산 행은 «아는 "
    "것»이다 — 그 체결 시각·가격으로 진입한다(basis `live_fill` · 본 집계 안 · 진입 뒤 고저를 몰라 진입일 터치는 안 본다). "
    "daytrading `auto`(09-14~)의 종목 시장은 «지금» "
    "stock_market 매핑(PIT 아님).",
    "09:02 에 게이트가 열려 있던 행의 밴드 복귀(band_touch) 진입은 시각을 몰라, 그날 뒤에 게이트가 다시 막힌 구간에서 "
    "샀을 수도 있다(보정하지 않는다).",
    "청산 = 일봉 근사: 보유기간·갭 익절·데이터 청산은 시가, 갭 손절은 시가(라이브는 09:05 이후 가격 — "
    "sl_gap_open 플래그), 장중 고저 동시 터치는 손절 우선. 폴링이 놓친 짧은 꼬리 때문에 시뮬 손절이 실제보다 많을 수 있다.",
    "신호 = 라이브 로그 우선(그 시점 DB) · 로그로 판정 못 하는 행(보유·캡)은 재현(지금 DB). 재현 행은 D-1 거래량이 라이브 "
    "스캔 뒤 재기록된 빈티지를 탄다 — 재기록은 09-14 거래시간 연장 «전»에도 있었고(예 09-10 115440 · 09-11 006880) "
    "연장 뒤 폭이 커졌다(최대 폭 = §1-3 관측 빈티지 범위 · 051160 09-18). 거래량 룰 전략(day·min)의 재현 행은 룰 여유와 "
    "«빈티지 취약» 표시를 §1-3 에 싣는다(보정은 하지 않는다).",
    "«평가 가능»(로그로 N 을 말할 수 있다) 규칙은 v1→v2→v3 로 바뀌었다(계획서 「계획 검증 실행」). 세 규칙의 결과를 §1-2 에 모두 싣는다.",
    "envelope 자체 프레임(QuantDailyReader 230봉)은 «지금 DB» 라 빈티지 위험. 창 안 스냅샷은 09-09~09-15 스캔 1~2행 뒤 0행.",
    "rs_leader corp_action 모드는 날짜별(09-17~ live). 09-10 은 가드 코드 자체가 없었다(9811d42 · 09-10 23:49 머지) — shadow 와 동치.",
    "arm A 는 라이브 자금 게이트 시간선(잔고·복리·쿨다운)을 재현하지 않는다. 멈춘 단계는 로그 계기 줄 → 체결 원장 시간선 → "
    "재구성(a_qty_upper = 잔고 미반영 상한) 순으로 분류하고 근거를 a_stop_basis 에 적었다.",
    "관측 기간이 짧다(마지막 봉 = 머리말 last_bar) — 대부분 로트가 미청산(평가)이다. 진입 집합은 fills_b.csv 로 동결해 두고 "
    "`--reuse-fills` 로 청산만 재추적할 것(fills_b.csv 의 tier=lift_ub 행은 상한 전용).",
    "gross — 수수료·세금 없음. 라이브 실현손익 보고 기준(net · fund_manager)과 다르다.",
    "생존편향·adj_factor 계열 결함(병합·감자 미조정·정지 패딩)은 그대로다.",
]


def _i(s: Optional[str]) -> int:
    return int(s) if s not in (None, "") else 0


def _f(s: Optional[str]) -> Optional[float]:
    return float(s) if s not in (None, "") else None


def won(x: int) -> str:
    return f"{int(x):,d}"


def pct(x: Optional[float]) -> str:
    return "-" if x is None else f"{x:+.2f}%"


def ratio(x: Optional[float]) -> str:
    return "-" if x is None else f"{x * 100:.2f}%"


def md_table(header: Sequence[Any], rows: Sequence[Sequence[Any]]) -> str:
    out = ["| " + " | ".join(str(h) for h in header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x).replace("|", "/") for x in r) + " |")
    return "\n".join(out)


def perf(rows: Sequence[Dict[str, str]]) -> Dict[str, Any]:
    closed = [r for r in rows if r["exit_status"] == "closed"]
    rets = [x for x in (_f(r["ret_pct"]) for r in closed) if x is not None]
    notional = sum(_i(r["notional_won"]) for r in rows)
    pnl_c = sum(_i(r["pnl_won"]) for r in closed)
    pnl_o = sum(_i(r["pnl_won"]) for r in rows if r["exit_status"] != "closed")
    return dict(n=len(rows), n_closed=len(closed), n_open=len(rows) - len(closed), win=sum(1 for x in rets if x > 0),
                mean_closed=(sum(rets) / len(rets) if rets else None), pnl_closed=pnl_c, pnl_open=pnl_o,
                nw=((pnl_c + pnl_o) / notional * 100.0 if notional else None))


def perf_cells(p: Dict[str, Any]) -> List[str]:
    return [str(p["n"]), f"{p['n_closed']}/{p['n_open']}", f"{p['win']}/{p['n_closed']}", pct(p["mean_closed"]),
            won(p["pnl_closed"]), won(p["pnl_open"]), pct(p["nw"])]


def _total(p: Dict[str, Any]) -> int:
    return p["pnl_closed"] + p["pnl_open"]


def replay_share(rows: Sequence[Dict[str, str]]) -> str:
    n = len(rows)
    k = sum(1 for r in rows if r.get("signal_basis") == "replay")
    return f"{k}/{n} ({ratio(k / n)})" if n else "-"


def a_group(row: Dict[str, str]) -> str:
    st = row.get("a_stop_stage", "")
    return f"gate:{row.get('a_stop_result', '')}" if st == "gate" else st


def lot_groups(ledger: Sequence[Dict[str, str]]) -> Dict[str, str]:
    """B1 로트 id → 그 원장 행의 A 멈춘 단계 묶음(`a_group`)."""
    return {r["b1_lot_id"]: a_group(r) for r in ledger if r.get("b1_lot_id")}


def dir_cell(agree: int, n: int, rate: Optional[float]) -> str:
    """방향별 일치 칸 — 표본이 FID_MIN_N 미만이면 비율 대신 «판정 불가»(0/3 이 «0.00%»로 읽히지 않게 · A5)."""
    return f"{agree}/{n} {ratio(rate)}" if n >= F.FID_MIN_N else f"{agree}/{n} 판정 불가"


def verdict_cell(g: Dict[str, Any]) -> str:
    """판정 옆에 verdict_note 를 붙인다 — `ok` 가 판정 못 한 방향을 숨기지 않게(과제 3 검수 6)."""
    return f"{g['verdict']} — {g['verdict_note']}" if g.get("verdict_note") else str(g["verdict"])


def _d5(row: Dict[str, str]) -> List[str]:
    return (row.get("d5_flags") or "").split(",")


def _has_flag(row: Dict[str, str], flag: str) -> bool:
    return any(p.startswith(flag) for p in (row.get("flags") or "").split(" · "))


def _tiers(acct: Dict[str, str]) -> List[str]:
    return (acct.get("fill_tiers") or R.TIER_MAIN).split(",")


def main_lots(lots: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    return [r for r in lots if r["arm"] == ARM_B1 and r.get("tier", R.TIER_MAIN) == R.TIER_MAIN]


def main_accounts(accounts: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    return [a for a in accounts if set(_tiers(a)) <= {R.TIER_MAIN}]


def scenarios(lots: Sequence[Dict[str, str]], accounts: Sequence[Dict[str, str]],
              accounts_ub: Sequence[Dict[str, str]]) -> List[Tuple[str, str, Dict[str, Any], Optional[Dict[str, Any]]]]:
    """시나리오별 (이름, 출처, B1 성과, B2 성과|None) — 각 행은 한 실행(또는 그 부분집합)이다. 행끼리 더하지 않는다.
    상한 = arm B1_ub «전체»(main 로트를 다시 담는다 · B1 + B1_ub 금지) + accounts_b2_ub."""
    b1 = main_lots(lots)

    def arm(name: str) -> List[Dict[str, str]]:
        return [r for r in lots if r["arm"] == name]

    return [(SCN_MAIN, "lots_b1 arm=B1 · accounts_b2", perf(b1), perf(main_accounts(accounts))),
            (SCN_UB, "lots_b1 arm=B1_ub 전체(main 반복 + tier=lift_ub) · accounts_b2_ub", perf(arm(ARM_UB)),
             perf(accounts_ub)),
            (SCN_ALLDAY, "arm=B1 에서 entry_basis=after_lift·live_fill 제외",
             perf([r for r in b1 if r["entry_basis"] not in LIFTED_BASES]), None),
            (SCN_NOGATE, "arm=B1_nogate(급락 차단 main 행만 · 나머지 로트는 본 집계와 같다)", perf(arm(ARM_NOGATE)), None),
            (SCN_EXT, "arm=B1_ext(라이브 후보 밖)", perf(arm(ARM_EXT)), None)]


def throttle_split(b1: Sequence[Dict[str, str]], grp: Dict[str, str]
                   ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]], Counter]:
    """진입억제 표시 B1 로트 → (최종 차단 = A 가 진입억제에서 멈춤 · 지연 뒤 라이브 체결 · 진입억제를 지나 다른 단계에서 멈춤,
    그 다른 단계 묶음별 건수). 과제 9 판정: throttle_delay 는 A=체결만 — 나머지는 원장 a_stop_stage 로 여기서 가른다."""
    final: List[Dict[str, str]] = []
    delay: List[Dict[str, str]] = []
    later: List[Dict[str, str]] = []
    why: Counter = Counter()
    for r in b1:
        fl = _d5(r)
        if D5_THROTTLE_DELAY in fl:
            delay.append(r)
        elif D5_THROTTLE in fl:
            g = grp.get(r["lot_id"], "")
            if g == "gate:throttle":
                final.append(r)
            else:
                later.append(r)
                why[g] += 1
    return final, delay, later, why


def crash_summary(ledger: Sequence[Dict[str, str]]) -> Dict[str, Any]:
    """D3′ 급락 차단 행 — 해제 뒤 상태 · 분봉 없는데 라이브가 산 행(live_fill · 과제 10 fix 1) · A3 분봉 없음(모른다) ·
    상한 상태 · 재차단(첫 해제만 봤다면 재차단 구간에서 샀을 행)."""
    crash = [r for r in ledger if r.get("crash_blocked") == "Y"]
    main = [r for r in crash if r["tier"] == R.TIER_MAIN]
    ext = [r for r in crash if r["tier"] == R.TIER_EXT]
    unk = [r for r in main if r.get("lift_unknown") == "Y"]
    rb = [r for r in main if r.get("lift_reblocked") == "Y"]
    return dict(n_main=len(main), status=Counter(r.get("lift_status") or "(밴드 없음)" for r in main),
                n_live=sum(1 for r in main if r.get("b_entry_basis") == X.BASIS_LIVE_FILL),
                n_unknown=len(unk), ub=Counter(r.get("ub_status") or "(없음)" for r in unk),
                rb_main=len(rb), rb_main_filled=sum(1 for r in rb if r.get("lift_status") == X.LIFT_FILLED),
                rb_ext=sum(1 for r in ext if r.get("lift_reblocked") == "Y"),
                unknown_ext=sum(1 for r in ext if r.get("lift_unknown") == "Y"))


def lift_add_split(b1: Sequence[Dict[str, str]], accounts: Sequence[Dict[str, str]]) -> Dict[str, Dict[str, int]]:
    """A4 — B1 vs B2 차 중 «해제 뒤 추가매수»(FLAG_LIFT_ADD) 계좌 몫. 그 계좌 손익 − 같은 체결(전략·종목·날짜)의 B1 로트
    손익 합. B2 는 그날 기존 평단으로 하루 전체 일봉을 먼저 보고 추가 뒤 터치를 안 보는데 B1 은 진입 뒤 분봉을 본다 —
    이 비대칭이 섞이는 몫이다. 나머지 = 전체 차 − 그 몫."""
    pnl = {(r["strategy"], r["code"], r.get("entry_date", "")): _i(r["pnl_won"]) for r in b1}
    out: Dict[str, Dict[str, int]] = {}
    for f in sorted({r["strategy"] for r in b1} | {a["strategy"] for a in accounts}):
        m2 = [a for a in accounts if a["strategy"] == f]
        flagged = [a for a in m2 if _has_flag(a, X.FLAG_LIFT_ADD)]
        diff_flag = sum(_i(a["pnl_won"]) - sum(pnl.get((f, a["code"], d), 0)
                                               for d in (a.get("fill_dates") or "").split(",")) for a in flagged)
        diff_all = sum(_i(a["pnl_won"]) for a in m2) - sum(_i(r["pnl_won"]) for r in b1 if r["strategy"] == f)
        out[f] = dict(n_flag=len(flagged), diff_flag=diff_flag, diff_all=diff_all, diff_rest=diff_all - diff_flag)
    return out


def _low_flags(sig_table: Sequence[Dict[str, Any]], exit_table: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    low: Dict[str, str] = {}
    for g in sig_table:
        if g["verdict"] == "LOW":
            key = str(g["group"]).split("[")[0]
            if "[신호 충실도 낮음]" not in low.get(key, ""):
                low[key] = low.get(key, "") + "[신호 충실도 낮음]"
    for g in exit_table:
        if g["verdict"] == "LOW":
            low[g["strategy"]] = low.get(g["strategy"], "") + "[청산 충실도 낮음]"
    return low


def render(meta: Dict[str, Any], sig_rows: Sequence[Dict[str, str]], exit_rows: Sequence[Dict[str, str]],
           entry_rows: Sequence[Dict[str, str]], ledger: Sequence[Dict[str, str]], lots: Sequence[Dict[str, str]],
           accounts: Sequence[Dict[str, str]], a_sim: Sequence[Dict[str, str]], a_actual: Sequence[Dict[str, str]],
           offlist: Sequence[Dict[str, str]], accounts_ub: Sequence[Dict[str, str]] = ()) -> str:
    sig_table = F.signal_table(sig_rows)
    exit_table = F.exit_table(exit_rows)
    tabs = {k: {g["group"]: g for g in F.signal_table(sig_rows, outcome_key=k)} for k, _ in RULES}
    low = _low_flags(sig_table, exit_table)

    def name(f: str) -> str:
        return f"{f} {low[f]}" if f in low else f

    b1 = main_lots(lots)
    main_accts = main_accounts(accounts)
    stray = (sum(1 for r in lots if r["arm"] == ARM_B1) - len(b1)) + (len(accounts) - len(main_accts))
    grp = lot_groups(ledger)
    L: List[str] = ["# ledger8 — 8전략 세 arm 관측 원장 요약", "", BANNER]
    if meta.get("reuse_fills"):                  # 최종 검수 M1 — 재추적 실행임을 머리에서 밝힌다
        L.append(f"> 🔒 **재추적 모드 — B 진입 집합은 이전 실행에서 동결했다**: `{meta['reuse_fills']}`(그 실행 git SHA "
                 f"{meta.get('reuse_fills_sha') or '불명 — 원본 run_meta.json 없음'}). 신호를 다시 평가해도 B 진입은 바뀌지 "
                 "않고 청산만 DB 최신 봉까지 다시 추적했다. 이 모드는 D3 반대편(B1_nogate)을 다시 만들지 않고 원장의 급락 행 "
                 "세부(lift_status 등)가 비어 있다 — §6-1 D3 반대편·§6-2 급락 행 수치는 동결 원본 실행의 summary 를 볼 것.")
    L += [f"> 창 {meta['window']}({meta['n_days']}거래일) · 청산 추적 = DB 최신 봉 {meta.get('last_bar', '')} · "
          f"DB {meta['db']} · 로그 {meta['log_dir']} · 실행 시각·git SHA 는 run_meta.json", ""]

    L += ["## 0. 원장 신뢰도", ""]
    L.append(f"- 충실도 LOW: {', '.join(f'{k} {v}' for k, v in low.items()) or '없음'} — "
             "LOW 전략의 수치는 그 표기와 함께만 인용할 것(기준값은 결과를 보고 바꾸지 않았다).")
    exit_na = [f"{g['strategy']} {g['verdict']}" for g in exit_table if g["verdict"].startswith("판정 불가")]
    if exit_na:
        L.append(f"- 청산 충실도 판정 불가(실제 청산 표본 < {F.FID_MIN_N}): {', '.join(exit_na)} — LOW 는 아니지만 청산 "
                 "재현이 확인되지 않았다. 이 전략의 청산 결과(§2~§5)는 이 표기와 함께 인용할 것(§1-4).")
    v3_low = {g["group"] for g in sig_table if g["verdict"] == "LOW"}
    for k, _ in RULES[:2]:
        was = [grp_ for grp_, g in tabs[k].items() if g["verdict"] == "LOW" and grp_ not in v3_low]
        if was:
            L.append(f"- {RULE_SHORT[k]} 규칙에서는 {', '.join(was)} 이 LOW 였다(§1-2 참조) — 채택 v3 에선 LOW 가 아니다.")
    for g in sig_table:
        if g["evaluable"] and g["bought"] == g["evaluable"]:
            L.append(f"- `{g['group']}` 판정 가능 {g['evaluable']}행이 전부 실제 체결(bought)이다 — 자명한 Y/Y 라 "
                     "신호 재현력의 증거로는 약하다.")
    thin_n = [g["group"] for g in sig_table if g["n_n"] < F.FID_MIN_N]
    if thin_n:
        L.append(f"- N 방향(라이브 N 인데 재현 Y 오류율) 표본 부족 {len(thin_n)}그룹: {', '.join(thin_n)} — "
                 "이 그룹의 재현 신호는 Y 쪽 오류를 잴 수 없다(§1-3 재현 비중과 함께 읽을 것).")
    L.append(f"- 본 집계(§2~§5)는 main 체결만이다: B1 {len(b1)} 로트 · B2 {len(main_accts)} 계좌. A3 상한·D3 반대편·"
             "D1 11~20위는 §6-1 에 따로 적었고 본 집계와 더하지 않는다.")
    if stray:
        L.append(f"- [경고] 본 집계 입력에 main 밖 체결이 섞인 행 {stray} — 본 집계에서 뺐다(lots_b1 arm=B1 은 tier=main, "
                 "accounts_b2 는 fill_tiers 가 전부 main 이어야 한다).")
    for w in meta.get("warnings", []):
        L.append(f"- [경고] {w}")
    L.append("")

    L += ["## 1. 충실도 (⑤)", "", "### 1-1. 신호 — 채택 규칙 v3 · 방향별(Y = 로그 Y 중 재현 Y · N = 로그 N 중 재현 N)", ""]
    L.append(md_table(["전략[모드]", "행", "판정가능", "Y 방향 일치", "N 방향 일치", "그중 bought", "이유 문자열 일치",
                       "기준가 일치", "판정"],
                      [[g["group"], g["n"], g["evaluable"], dir_cell(g["agree_Y"], g["y_n"], g["y_rate"]),
                        dir_cell(g["agree_N"], g["n_n"], g["n_rate"]), g["bought"],
                        f"{g['reasons_eq']}/{g['agree_Y']}", f"{g['ref_eq']}/{g['agree_Y']}", verdict_cell(g)]
                       for g in sig_table]))
    L += ["", f"- 방향별 표본이 {F.FID_MIN_N} 미만이면 비율 대신 «판정 불가»로 적는다.", "",
          "### 1-2. «평가 가능» 규칙 민감도 · 재구성 모순", ""]
    rows_ = []
    for g in sig_table:
        cells = []
        for k, _ in RULES:
            x = tabs[k].get(g["group"])
            cells.append("-" if x is None else f"{x['evaluable']}행 · Y {dir_cell(x['agree_Y'], x['y_n'], x['y_rate'])}"
                                                f" · N {dir_cell(x['agree_N'], x['n_n'], x['n_rate'])} · {verdict_cell(x)}")
        rows_.append([g["group"]] + cells)
    L.append(md_table(["전략[모드]"] + [lbl for _, lbl in RULES], rows_))
    cv2 = Counter(r["strategy"] for r in sig_rows if r.get("no_slot_but_log_y_v2") == "Y")
    cv3 = Counter(r["strategy"] for r in sig_rows if r.get("no_slot_but_log_y") == "Y")
    L += ["", "- 재구성 모순 = 체결 원장 시간선은 no_slot 인데 라이브 로그엔 `[on_tick] 매수신호` 가 있다(재구성 규칙의 충실도): "
          f"v2 {sum(cv2.values())}건({' · '.join(f'{k} {v}' for k, v in sorted(cv2.items())) or '-'}) → "
          f"v3 {sum(cv3.values())}건({' · '.join(f'{k} {v}' for k, v in sorted(cv3.items())) or '-'}).", ""]
    L += ["### 1-3. 재현 신호 비중 · 거래량 룰 빈티지", ""]
    rows_ = []
    for f in R.ALL_FOLDERS:
        sr = [r for r in sig_rows if r["strategy"] == f]
        mine = [r for r in b1 if r["strategy"] == f]
        if not sr and not mine:
            continue
        used_y = [r for r in ledger if r["strategy"] == f and r["tier"] == R.TIER_MAIN and r.get("signal_used") == "Y"]
        frag = sum(1 for r in sr if r.get("vintage_fragile") == "Y")
        withm = sum(1 for r in sr if r.get("signal_basis") == "replay" and r.get("rule_margin_pct"))
        rows_.append([name(f), len(sr), replay_share(used_y), replay_share(mine),
                      f"{withm}/{frag}" if f in (LS8_DAY, LS8_MIN) else "-"])
    L.append(md_table(["전략", "main 후보 행", "사용 신호 Y 중 재현", "B1 로트 중 재현", "재현 행 룰 여유 계산/빈티지 취약"],
                      rows_))
    v = meta.get("vintage") or {}
    L += ["", f"- 관측 빈티지(daytrading D-1 거래량 · 라이브 사유 vs 재현 사유 {v.get('n', 0)}쌍): "
          f"{ratio(v.get('vmin'))} ~ {ratio(v.get('vmax'))}. 재기록은 거래량을 «늘린다» ⇒ daytrading(비율 ≥ 문턱이 Y) 재현은 "
          "Y 쪽으로, minervini(비율 ≤ 문턱이 Y) 재현은 N 쪽으로 기운다. «빈티지 취약» = 관측 최대 폭 안에서 뒤집힐 수 있는 재현 행.",
          ""]
    L += ["### 1-4. 청산 — 실제 매수를 실제 진입가로 시뮬 (분모 = 실제 청산된 건)", ""]
    L.append(md_table(["전략", "실제 매수", "실제 청산", "사유·날짜 일치", "사유만", "불일치", "실제만 청산", "당일 청산",
                       "사유 일치율", "판정"],
                      [[g["strategy"], g["n"], g["closed"], g["Y"], g["reason_only"], g["N"], g["actual_only_closed"],
                        g["same_day"], ratio(g["reason_rate"]), g["verdict"]] for g in exit_table]) if exit_table else "(없음)")
    tpsl = F.tp_sl_table(exit_rows)
    L += ["", "### 1-5. 익절·손절 비율 — 엔진 경로 vs 체결 원장 BUY", ""]
    L.append(md_table(["전략", "일치/건수"], [[g["strategy"], f"{g['match']}/{g['n']}"] for g in tpsl]) if tpsl else "(없음)")
    es = F.entry_diff_stats(entry_rows)
    L += ["", "### 1-6. 진입가 — (A_sim 진입가 ÷ 실제 체결가 − 1)×100 · + 면 시뮬이 비싸다", ""]
    L.append(md_table(["전략", "건수", "부호 포함 평균", "|차| 평균", "양수", "첫 틱(≤09:05) 건수", "첫 틱 부호 평균"],
                      [[g["strategy"], g["n"], pct(g["signed_mean"]), pct(g["abs_mean"]).replace("+", ""),
                        f"{g['positive']}/{g['n']}", g["n_first"], pct(g["signed_mean_first"])] for g in es])
             if es else "(없음)")
    n_live = sum(1 for r in entry_rows if r.get("sim_entry_basis") == X.BASIS_LIVE_FILL)
    if n_live:
        L += ["", f"- 급락일 실제 매수 중 `live_fill` {n_live}건은 해제 뒤 열린 구간 분봉이 없어 A_sim 진입 = 실제 체결 "
              "그대로다(B1 과 같은 D3′ 경로) — 시뮬 진입가가 아니라 이 표에서 뺐다. 급락일 나머지는 해제 뒤 첫 밴드 안 분봉 "
              "진입가(after_lift)로 비교한다."]
    off: Counter = Counter()
    for r in offlist:
        off[r["strategy"]] += _i(r["n_offlist"])
    L += ["", "- E6 목록 밖 `[on_tick] 매수신호`(소유자 미지정 SELECTED — B 에서 제외, 스펙 3-4): "
          + (" · ".join(f"{k} {v}" for k, v in sorted(off.items())) or "없음"), ""]

    L += ["## 2. A vs B1 — 자원 제약이 잘라낸 표본과 그 성과 (①)", ""]
    size_rows, perf_rows = [], []
    for f in R.ALL_FOLDERS:
        led = [r for r in ledger if r["strategy"] == f and r["tier"] == R.TIER_MAIN]
        mine = [r for r in b1 if r["strategy"] == f]
        if not led and not mine:
            continue
        res_lots = [r for r in mine if grp.get(r["lot_id"]) in RESOURCE_GROUPS]
        size_rows.append([name(f), len(led), sum(1 for r in led if r.get("signal_used") == "Y"), len(mine),
                          sum(1 for r in a_sim if r["strategy"] == f), len(res_lots)])
        perf_rows.append([name(f), "A_actual(실제 · 진실값)"]
                         + perf_cells(perf([r for r in a_actual if r["strategy"] == f])) + ["-"])
        asf = [r for r in a_sim if r["strategy"] == f]
        perf_rows.append([name(f), "A_sim(실제 매수 · 같은 시뮬)"] + perf_cells(perf(asf)) + [replay_share(asf)])
        perf_rows.append([name(f), "B1 전체"] + perf_cells(perf(mine)) + [replay_share(mine)])
        for key, label in A_GROUPS:
            g = [r for r in mine if grp.get(r["lot_id"]) == key]
            if g:
                perf_rows.append([name(f), f"B1 중 {label}"] + perf_cells(perf(g)) + [replay_share(g)])
    L.append(md_table(["전략", "후보 행(main)", "사용 신호 Y", "B1 로트", "A_sim 로트", "B1 중 A 가 자원 제약(캡·현금)으로 못 산 것"],
                      size_rows))
    fill_rows = [r for r in ledger if r["tier"] == R.TIER_MAIN and r.get("a_stop_stage") == "fill"]
    matched = [r for r in fill_rows if r.get("b1_lot_id")]
    missing = Counter(r["strategy"] for r in fill_rows if not r.get("b1_lot_id"))
    L += ["", md_table(["전략", "묶음"] + PERF_HDR + ["재현 신호 비중"], perf_rows),
          "", f"- 라이브 실제 매수 {len(a_actual)}건(A_actual) · main 후보 행 {len(fill_rows)} · 그중 B1 본 집계 로트가 있는 것 "
          f"{len(matched)}(live_fill {sum(1 for r in matched if r.get('b_entry_basis') == X.BASIS_LIVE_FILL)}) · 빠진 것 "
          + (" · ".join(f"{k} {n}" for k, n in sorted(missing.items())) or "없음")
          + " — live_fill = 분봉 없는 급락 해제 뒤 라이브 실제 체결 시각·가격(§6-2).",
          "- A 와 B 는 «A_sim 대 B1»(같은 진입·청산 시뮬)으로만 비교한다. A_actual 은 참고(진실값 · 체결가·시각이 다르다).",
          "- «재현 신호 비중»이 높은 묶음(특히 «A 캡»·«A 이미 보유»)은 라이브가 그 종목을 평가하지 않아 신호가 전부 재현이다 — "
          "§1-1 N 방향 표본과 §1-3 빈티지를 함께 볼 것.", ""]

    L += ["## 3. B1 vs B2 — 합산 여부만으로 달라진 것 (②)", ""]
    split = lift_add_split(b1, main_accts)
    rows_ = []
    for f in R.ALL_FOLDERS:
        m1 = [r for r in b1 if r["strategy"] == f]
        m2 = [r for r in main_accts if r["strategy"] == f]
        if not m1:
            continue
        p1, p2 = perf(m1), perf(m2)
        t1, t2 = _total(p1), _total(p2)
        s = split[f]
        rows_.append((abs(t2 - t1), [name(f), p1["n"], p2["n"], sum(_i(r["n_adds"]) for r in m2), won(t1), won(t2),
                                     won(t2 - t1), s["n_flag"], won(s["diff_flag"]), won(s["diff_rest"]),
                                     pct(p1["nw"]), pct(p2["nw"])]))
    rows_.sort(key=lambda x: -x[0])
    L.append(md_table(["전략", "B1 로트", "B2 계좌", "B2 추가매수", "B1 손익(원·실현+평가)", "B2 손익(원·실현+평가)",
                       "차(B2−B1)", "해제 뒤 추가매수 계좌(A4)", "그 계좌 몫 차", "나머지 차", "B1 명목가중%",
                       "B2 명목가중%"], [r for _, r in rows_]) if rows_ else "(없음)")
    n_flag = sum(s["n_flag"] for s in split.values())
    L += ["", "- 차이가 큰 전략부터 — 중복 매수 처리를 따로 정해야 할 후보. 부호보다 크기를 본다. 미청산 로트끼리는 같은 "
          "마지막 종가로 평가돼 합이 같아지므로(Σ(종가−매입가)×수량 = (종가−평단)×총수량) 차이는 청산이 갈린 계좌에서만 생긴다.",
          f"- «해제 뒤 추가매수 계좌»(FLAG_LIFT_ADD · {n_flag}계좌) = B2 가 D3′ 해제 뒤 체결을 평단에 더한 날이 있는 계좌. 그날 "
          "B2 는 기존 평단으로 하루 전체 일봉을 먼저 보고 추가 뒤 터치는 보지 않는데, B1 은 진입 뒤 분봉 터치를 본다 — 이 "
          "비대칭이 차에 섞인다. «그 계좌 몫 차» = 그 계좌 손익 − 같은 체결의 B1 로트 손익 합 · «나머지 차» = 차 − 그 몫"
          "(합산 효과만 보려면 이 칸을 볼 것).", ""]

    L += ["## 4. 평단 이동으로 뒤집힌 청산 (③)", ""]
    rows_ = []
    for f in R.ALL_FOLDERS:
        m2 = [r for r in main_accts if r["strategy"] == f and _i(r["n_adds"]) > 0]
        if not m2:
            continue
        c = Counter("reason" if r["avg_flip"].startswith("reason:") else r["avg_flip"] for r in m2)
        slp = sum(1 for r in m2 if r["avg_flip"].startswith("reason:")
                  and ({"sl", "tp"} & set(r["avg_flip"][len("reason:"):].split("→"))))
        clk = sum(1 for r in m2 if r["hold_clock_reset_diff"].startswith("diff:"))
        rows_.append([name(f), len(m2), c.get("same", 0), c.get("date_only", 0), c.get("reason", 0), slp, clk])
    L.append(md_table(["전략", "추가매수 있는 계좌", "B1 첫 로트와 같음", "날짜만 다름", "사유 다름", "그중 손절·익절이 뒤집힘",
                       "시계 리셋 시 청산 달라짐(D4-b)"], rows_) if rows_ else "(추가매수 계좌 없음)")
    L.append("")

    L += ["## 5. 전략별 중복 신호 (④)", ""]
    rows_ = []
    for f in R.ALL_FOLDERS:
        m1 = [r for r in b1 if r["strategy"] == f]
        if not m1:
            continue
        per_code = Counter(r["code"] for r in m1)
        dist = Counter(min(v, 4) for v in per_code.values())
        rows_.append([name(f), len(m1), len(per_code), sum(1 for r in m1 if r["is_repeat_while_open"] == "Y"),
                      sum(_i(r["n_adds"]) for r in main_accts if r["strategy"] == f),
                      max(_i(r["open_lot_seq"]) for r in m1), dist.get(1, 0), dist.get(2, 0), dist.get(3, 0),
                      dist.get(4, 0)])
    L.append(md_table(["전략", "B1 로트", "종목 수", "열린 로트 위 재신호", "B2 추가매수(대조)", "최대 동시 로트",
                       "종목당 1로트", "2", "3", "4+"], rows_) if rows_ else "(없음)")
    L += ["", "- «열린 로트 위 재신호»와 «B2 추가매수»는 같은 시간선(09:00 시가 단계 청산은 진입 전)이라 대부분 같다. 남는 차이는 "
          "로트별 청산과 평단 청산이 갈린 계좌다. rs_leader 는 신호가 매일 반복될 수 있어 로트가 불어난다(스펙 §4 위험).", ""]

    L += ["## 6. 부록 — 시나리오 · D3′ 급락(A3) · D2 타전략 보유 · D5 속도 조절 · 수량 근거", "",
          "### 6-1. 시나리오별 합계 — 각 행은 한 실행(또는 그 부분집합)이다 · 행끼리 더하지 말 것", ""]
    rows_ = []
    for label, src, p1, p2 in scenarios(lots, accounts, accounts_ub):
        rows_.append([label, src] + perf_cells(p1)
                     + ([str(p2["n"]), won(_total(p2)), pct(p2["nw"])] if p2 is not None else ["-", "-", "-"]))
    L.append(md_table(["시나리오", "출처"] + [f"B1 {h}" for h in PERF_HDR]
                      + ["B2 계좌", "B2 손익(원·실현+평가)", "B2 명목가중%"], rows_))
    L += ["", "- §2~§5 는 첫 행(본 집계)만 쓴다. arm=B1_ub 는 main 로트를 다시 담고 있어 «상한 = B1_ub 전체»다(B1 + B1_ub 는 "
          "이중 계산). B2 는 본 집계와 상한만 따로 돌렸다(D3 반대편·ext 는 B1 만).", ""]
    cs = crash_summary(ledger)
    ub_lots = [r for r in lots if r["arm"] == ARM_UB and r.get("tier") == R.TIER_LIFT_UB]
    p_ub = perf(ub_lots)
    n_addunk = sum(1 for a in accounts_ub if _has_flag(a, A.FLAG_ADD_UNKNOWN))
    lo1, up1 = perf(b1), perf([r for r in lots if r["arm"] == ARM_UB])
    lo2, up2 = perf(main_accts), perf(accounts_ub)
    L += ["### 6-2. D3′ 급락 게이트 · A3 분봉 없음(모른다)", ""]
    L.append(f"- D3′ 급락 차단 main 행 {cs['n_main']}: "
             + (" · ".join(f"{k} {n}" for k, n in sorted(cs["status"].items())) or "없음")
             + " (filled = 게이트 열린 구간 안 해제 뒤 체결 · no_minute_data = 분봉 없음 · unfillable = 열린 구간 "
               "내내 밴드 밖)")
    if cs["status"].get(X.LIFT_NO_MINUTE):
        L.append(f"- 분봉 없음 main {cs['status'][X.LIFT_NO_MINUTE]}행 중 {cs['n_live']}행은 라이브가 게이트 해제 뒤 실제로 "
                 "샀다 — «아는 것은 안다»: 그 체결 시각·가격으로 진입(basis live_fill · 본 집계 안 · 진입 뒤 분봉이 없어 "
                 "진입일 고저는 안 봄). 나머지만 «모른다»다.")
    L.append(f"- 분봉 없음(모른다 · 본 집계 밖) main {cs['n_unknown']}행 → 상한(D 일봉 [저가, 고가]가 밴드와 겹치면 체결 · "
             "가격 = 종가가 밴드 안이면 종가, 아니면 가까운 밴드 경계): "
             + (" · ".join(f"{k} {n}" for k, n in sorted(cs["ub"].items())) or "없음")
             + f". ext 의 분봉 없음 {cs['unknown_ext']}행은 상한을 만들지 않는다(ext 는 그 자체가 별도 칸).")
    L += ["", md_table(["항목", "하한 = 본 집계(모른다 → 안 삼)", "상한(모른다 → 일봉 겹치면 체결)"],
                       [["B1 로트", lo1["n"], up1["n"]], ["B1 손익(원·실현+평가)", won(_total(lo1)), won(_total(up1))],
                        ["B1 명목가중%", pct(lo1["nw"]), pct(up1["nw"])], ["B2 계좌", lo2["n"], up2["n"]],
                        ["B2 손익(원·실현+평가)", won(_total(lo2)), won(_total(up2))],
                        ["B2 명목가중%", pct(lo2["nw"]), pct(up2["nw"])]]), ""]
    L.append(f"- B1 상한 − 하한 = 상한 체결 로트 {p_ub['n']}건(tier=lift_ub)의 손익 {won(_total(p_ub))}원 — B1 은 로트 "
             "독립이라 이 차가 곧 «모른다» 행 몫이다. B2 는 같은 종목 계좌에 섞이므로 차를 행 단위로 나누지 않는다.")
    L.append(f"- 추가매수 불명(FLAG_ADD_UNKNOWN) B2 상한 계좌 {n_addunk} — 상한 체결 날 같은 (전략, 종목) 계좌가 열려 있어 "
             "추가매수 여부·순서를 모른다(B2 상한 손익은 이 계좌들만큼 불확실하다).")
    L.append("- D3′ 는 게이트가 «열린» 구간 안에서만 산다(라이브와 같게 재차단 구간 체결을 뺐다 · 과제 9 보정): "
             f"첫 해제 시각만 봤다면 재차단 구간에서 샀을 main 행 {cs['rb_main']} → 다음 열린 구간 체결 "
             f"{cs['rb_main_filled']} · 미체결 {cs['rb_main'] - cs['rb_main_filled']} · ext {cs['rb_ext']}.")
    L.append("")

    final, delay, later, why = throttle_split(b1, grp)
    a_label = dict(A_GROUPS)
    why_txt = " · ".join(f"{a_label.get(k, k or 'A 단계 없음')} {n}"
                         for k, n in sorted(why.items(), key=lambda kv: (-kv[1], kv[0])))
    lifted = [r for r in b1 if r["entry_basis"] == X.BASIS_LIFT]
    oh = [r for r in b1 if r.get("other_holder_live")]
    L += ["### 6-3. D2 · D5 — 본 집계(B1) 안에서 표시만 한 로트", ""]
    rows_ = [["D3′ 해제 뒤 체결(본 집계 안)"] + perf_cells(perf(lifted)),
             ["D3′ 분봉 없음 — 라이브 실제 체결로 진입(live_fill · 본 집계 안)"]
             + perf_cells(perf([r for r in b1 if r["entry_basis"] == X.BASIS_LIVE_FILL])),
             ["D2 라이브였다면 타전략 보유로 막혔을 B1 로트(other_holder_live)"] + perf_cells(perf(oh)),
             ["D5 라이브였다면 진입억제에서 최종 차단(A 멈춘 단계 = 진입억제)"] + perf_cells(perf(final)),
             ["D5 라이브였다면 진입억제로 지연 뒤 체결(A 체결)"] + perf_cells(perf(delay)),
             [f"D5 라이브였다면 진입억제를 지나 다른 단계에서 멈춤({why_txt or '-'})"] + perf_cells(perf(later))]
    for k, label in D5_LABELS:
        rows_.append([f"D5 {label}"] + perf_cells(perf([r for r in b1 if k in _d5(r)])))
    L.append(md_table(["묶음"] + PERF_HDR, rows_))
    qb = Counter(r["qty_basis"] for r in b1)
    L += ["", "- 진입억제 세 갈래는 원장(ledger8.csv)의 A 멈춘 단계로 나눴다. 진입억제 표시는 «그날 그 종목에 `[진입억제]` 줄이 "
          "있었다»는 뜻이지 B 진입 시각과 맞춘 것이 아니고, 라이브가 그 종목에 매수신호를 낸 날만 관측된다.",
          "- 25분 매수 쿨다운: 라이브 쿨다운은 (종목, 전략) 슬롯 객체 단위라 «확실히 막힘» 건수는 근거가 없다 — 다른 전략 매수가 "
          "이 전략 객체에 닿았는지 모르는 경우만 «관측 불가»로 센다.",
          "- VI 매수 보류는 DEBUG 로그라 관측 불가 — 표에 없다.",
          "- B1 수량 근거: " + (" · ".join(f"{k} {v}" for k, v in sorted(qb.items())) or "없음")
          + " (one_share = 주가 > 1,000,000원 → 1주)", ""]

    L += ["## 7. arm A — 후보가 라이브에서 멈춘 단계", ""]
    rows_ = []
    for f in R.ALL_FOLDERS:
        led = [r for r in ledger if r["strategy"] == f and r["tier"] == R.TIER_MAIN]
        if not led:
            continue
        c = Counter(a_group(r) for r in led)
        rows_.append([name(f), len(led)] + [c.get(k, 0) for k, _ in A_GROUPS])
    L.append(md_table(["전략", "후보 행"] + [lbl for _, lbl in A_GROUPS], rows_) if rows_ else "(없음)")
    L += ["", "- 근거(`a_stop_basis`)는 ledger8.csv — log(계기 줄) · timeline(체결 원장 재구성) · vtr · recon · replay.", ""]

    L += ["## 8. 가정·한계", ""]
    L += [f"- {x}" for x in LIMITS]
    L.append("")
    return "\n".join(L)
