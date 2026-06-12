"""전략 발굴 게이트 러너 — 후보를 G2~G5 생존 필터로 일괄 판정.

spec: docs/superpowers/specs/2026-06-11-strategy-discovery-pipeline.md
원칙: 목표수익률 역산 금지·in-sample best-pick 금지. 게이트는 채택이 아니라 기각 장치.

게이트 (하나라도 FAIL → 기각, 사유는 reports/discovery/ 에 기록):
  G2 1차 백테스트  : 풀기간 PnL>0 · Sharpe>0.4 · 청산거래>=100 (라이브 사이징 100만/종목)
  G3 상관          : 기존 활성 합성(live_sum)과 corr<0.5 AND 꼬리 lift<2.5 AND ΔSharpe>0
  G4 강건성 3축    : 워크포워드 반기 양수>=7/11 & 최악>-15% · 부트스트랩 Sharpe p05>0 ·
                     슬리피지 30bp PnL>0
  G5 과적합 방어   : 핵심 파라미터 ±20% 5점 PnL 전부 양수 · OOS(train/test) Sharpe 둘다>0

usage:
  python scripts/strategy_gate.py --out reports/discovery \
      --live-returns reports/books_research/_mv4_returns
  python scripts/strategy_gate.py --candidates oversold_rsi2 --smoke
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from scripts.book_param_multiverse import (  # noqa: E402
    _daily_minmax_dates,
    _load_daily_adj,
    _load_top_volume_daily,
)
from scripts.book_portfolio_multiverse import _SLTPMHAdapter, _precompute_signals  # noqa: E402
from scripts.discovery.exit_adapters import (  # noqa: E402
    BBReversionExitAdapter,
    CloseAboveMAExitAdapter,
    MAReversionExitAdapter,
)
from scripts.discovery.rules import (  # noqa: E402
    BBReversionRule,
    MeanReversionMA20Rule,
    NDownVolSurgeRule,
    OversoldRSI2Rule,
    RSI2PureRule,
    StrengthClose1DRule,
    ThreeDownBounceRule,
    TurnOfMonthRule,
)
from scripts.exit_multiverse.portfolio_sim import run_portfolio  # noqa: E402
from scripts.multiverse4_portfolio_analysis import (  # noqa: E402
    block_bootstrap_metrics,
    combine_sum_of_equities,
    load_returns,
    maxdd_from_returns,
    semiannual_windows,
    sharpe,
    tail_coloss_lift,
)
from scripts.multiverse4_returns_export import (  # noqa: E402
    INITIAL,
    MAX_PER_STOCK,
    _patch_costs,
)

GATE_THRESHOLDS = dict(
    g2_pnl_min=0.0, g2_sharpe_min=0.4, g2_trades_min=100,
    g2_monthly_trades_min=10.0,   # 배치3+ (사장님 지시): 월평균 거래 ≥10회
    g3_corr_max=0.5, g3_lift_max=2.5, g3_dsharpe_min=0.0,
    g4_wf_pos_min_ratio=7 / 11, g4_wf_worst_min=-0.15,
    g4_boot_p05_min=0.0, g4_cost_slippage=0.003,
    g5_oos_split="2024-06-30",
    # 거래당 그로스 엣지 생존선 (현물 왕복 ≈0.41% + 여유 / ETF·선물 거래세 면제 가정)
    edge_gross_adopt=0.005, edge_gross_etf=0.002,
)

ROUNDTRIP_COST = 0.00015 * 2 + 0.0018 + 0.001 * 2  # 수수료×2+거래세+슬리피지×2 ≈ 0.41%


# ---------------------------------------------------------------------------
# 후보 레지스트리 (배치1) — 사양 출처는 scripts/discovery/rules.py docstring
# ---------------------------------------------------------------------------

@dataclass
class CandidateSpec:
    name: str
    warmup: int
    K: int
    params: dict
    adapter: object
    build_signals: Callable[[Dict[str, pd.DataFrame]], Dict[str, List[int]]] = field(repr=False, default=None)
    # 섭동 5점: (라벨, build_signals 변형) — ±20% 강건성 확인용 (best-pick 금지)
    perturb: List[Tuple[str, Callable]] = field(repr=False, default_factory=list)
    note: str = ""
    top_n: int = 50          # 유니버스 (배치3: 희소조건 빈도 확보용 300)
    # G3 구속 모드: "full"=corr+lift+ΔSharpe / "dsharpe_only"=ΔSharpe만 구속(corr·lift 참고치)
    #   — 1~2일 보유는 in-market일 베타로 corr 0.8+가 구조적(배치2)이라 spec 부록A에서 수정.
    g3_mode: str = "full"


def _sig(rule_factory, warmup):
    def _f(data):
        return _precompute_signals(data, rule_factory(), warmup, "daily")
    return _f


def _perturb5(label_fmt, values, rule_fn, warmup):
    return [(label_fmt.format(v), _sig(lambda v=v: rule_fn(v), warmup)) for v in values]


CANDIDATES: Dict[str, CandidateSpec] = {
    "oversold_rsi2": CandidateSpec(
        name="oversold_rsi2", warmup=205, K=5,
        params=dict(stop_loss_pct=99.0, take_profit_pct=99.0, max_hold_bars=20),
        adapter=CloseAboveMAExitAdapter(ma=5),
        build_signals=_sig(OversoldRSI2Rule, 205),
        perturb=_perturb5("rsi_buy={}", [8.0, 9.0, 10.0, 11.0, 12.0],
                          lambda v: OversoldRSI2Rule(rsi_buy=v), 205),
        note="Connors RSI-2 verbatim. 청산=SMA5 회복(+mh20 가드), 손익절 없음(사양)."),
    "strength_close_1d": CandidateSpec(
        name="strength_close_1d", warmup=25, K=5,
        params=dict(stop_loss_pct=99.0, take_profit_pct=99.0, max_hold_bars=0),
        adapter=_SLTPMHAdapter(),
        build_signals=_sig(StrengthClose1DRule, 25),
        perturb=_perturb5("range_pos={}", [0.60, 0.675, 0.75, 0.825, 0.90],
                          lambda v: StrengthClose1DRule(range_pos=v), 25),
        note="강세마감 익일보유. mh=0 → 시가→익일시가 1거래일(최소 실현가능 보유)."),
    "bb_reversion": CandidateSpec(
        name="bb_reversion", warmup=45, K=5,
        params=dict(stop_loss_pct=0.03, take_profit_pct=0.05, max_hold_bars=15),
        adapter=BBReversionExitAdapter(),
        build_signals=_sig(BBReversionRule, 45),
        perturb=_perturb5("bb_std={}", [1.6, 1.8, 2.0, 2.2, 2.4],
                          lambda v: BBReversionRule(bb_std=v), 45),
        note="레포 템플릿 verbatim (미검증 자산 재활용). 라이브는 저변동 섹터 대상이나 게이트는 top50 공통 풀."),
    "mean_reversion_ma20": CandidateSpec(
        name="mean_reversion_ma20", warmup=25, K=5,
        params=dict(stop_loss_pct=0.07, take_profit_pct=0.12, max_hold_bars=7),
        adapter=MAReversionExitAdapter(ma=20, recovery_ratio=0.9),
        build_signals=_sig(MeanReversionMA20Rule, 25),
        perturb=_perturb5("entry_dev={}", [-8.0, -9.0, -10.0, -11.0, -12.0],
                          lambda v: MeanReversionMA20Rule(entry_deviation_pct=v), 25),
        note="레포 템플릿 verbatim (미검증 자산 재활용)."),
}


# --- 배치2 (2026-06-11): 1일/2일 보유 컨셉 — 진입 3종 × 보유 {h1=mh0, h2=mh1} ---
# 순수 시간청산(sl/tp=99): 보유기간 자체가 컨셉이라 손익절 없는 사양이 a priori.

def _timed_hold_params(mh: int) -> dict:
    return dict(stop_loss_pct=99.0, take_profit_pct=99.0, max_hold_bars=mh)


_BATCH2_ENTRIES = {
    "three_down_bounce": dict(
        warmup=25, rule=ThreeDownBounceRule,
        perturb=_perturb5("n_down={}", [1, 2, 3, 4, 5],
                          lambda v: ThreeDownBounceRule(n_down=int(v)), 25),
        note="Connors 연속하락 반등 verbatim (n=3). 섭동=연속일수 1~5."),
    "rsi2_pure": dict(
        warmup=25, rule=RSI2PureRule,
        perturb=_perturb5("rsi_buy={}", [8.0, 9.0, 10.0, 11.0, 12.0],
                          lambda v: RSI2PureRule(rsi_buy=v), 25),
        note="RSI(2)<10 무필터 — 배치1 corr 0.89=SMA200 필터 가설 직접 검정."),
    "turn_of_month": dict(
        warmup=25, rule=TurnOfMonthRule,
        perturb=_perturb5("offset={}", [-1, 0, 1, 2, 3],
                          lambda v: TurnOfMonthRule(entry_offset=int(v)), 25),
        note="월말월초 효과 (published TOM). 섭동=윈도우 내 진입 오프셋(전부 양수 기대). "
             "캘린더는 주말+공휴일 라이브러리 근사(임시휴장 미반영 가능)."),
}

for _ename, _e in _BATCH2_ENTRIES.items():
    for _h, _mh in (("h1", 0), ("h2", 1)):
        _name = f"{_ename}_{_h}"
        CANDIDATES[_name] = CandidateSpec(
            name=_name, warmup=_e["warmup"], K=5,
            params=_timed_hold_params(_mh),
            adapter=_SLTPMHAdapter(),
            build_signals=_sig(_e["rule"], _e["warmup"]),
            perturb=_e["perturb"],
            note=f"{_e['note']} 보유={'1거래일(시가→익일시가)' if _mh == 0 else '2거래일'}.")


# --- 배치3 (2026-06-11 승인, spec 부록A): 희소 과락 반등 선별강도×엣지 곡선 ---
#   제약: 월 거래 ≥10회 (g2_monthly_trades_min). 유니버스 top300 (빈도 보전).
#   G3는 dsharpe_only (단기보유 corr 0.8+ 구조적 — 부록A 명시 수정).
#   ★측정 매트릭스 사전 고정 — 결과 본 후 변형 추가 금지.

def _b3(name, rule_fn, perturb, mh, note, warmup=25, adapter=None, params=None):
    CANDIDATES[name] = CandidateSpec(
        name=name, warmup=warmup, K=5,
        params=params if params is not None else _timed_hold_params(mh),
        adapter=adapter if adapter is not None else _SLTPMHAdapter(),
        build_signals=_sig(rule_fn, warmup), perturb=perturb,
        note=note, top_n=300, g3_mode="dsharpe_only")


# A. 깊은 연속하락: N∈{4,5,6,7} × {h1,h2} — 섭동은 자기 N 중심 ±2 (5점)
for _n in (4, 5, 6, 7):
    for _h, _mh in (("h1", 0), ("h2", 1)):
        _b3(f"deep_down_n{_n}_{_h}",
            lambda n=_n: ThreeDownBounceRule(n_down=n),
            _perturb5("n_down={}", [_n - 2, _n - 1, _n, _n + 1, _n + 2],
                      lambda v: ThreeDownBounceRule(n_down=max(1, int(v))), 25),
            _mh,
            f"배치3-A: {_n}일 연속하락 반등, 보유={'1' if _mh == 0 else '2'}거래일, top300.")

# B. 깊은 MA20 이탈: {-12,-15,-20%} — 청산=템플릿 verbatim(MA회복), 섭동 ±20%
for _dev in (-12.0, -15.0, -20.0):
    _b3(f"deep_mr_dev{int(abs(_dev))}",
        lambda d=_dev: MeanReversionMA20Rule(entry_deviation_pct=d),
        _perturb5("entry_dev={}", [round(_dev * f, 1) for f in (0.8, 0.9, 1.0, 1.1, 1.2)],
                  lambda v: MeanReversionMA20Rule(entry_deviation_pct=float(v)), 25),
        0,
        f"배치3-B: MA20 {_dev:.0f}% 깊은 이탈, 청산=MA회복(sl7/tp12/mh7), top300.",
        adapter=MAReversionExitAdapter(ma=20, recovery_ratio=0.9),
        params=dict(stop_loss_pct=0.07, take_profit_pct=0.12, max_hold_bars=7))

# C. 조건 중첩: 4일 연속하락 AND 거래량 ≥2× (h2) — 섭동=vol_mult ±20%
_b3("confluence_n4vol2_h2",
    lambda: NDownVolSurgeRule(n_down=4, vol_mult=2.0),
    _perturb5("vol_mult={}", [1.6, 1.8, 2.0, 2.2, 2.4],
              lambda v: NDownVolSurgeRule(n_down=4, vol_mult=float(v)), 25),
    1,
    "배치3-C: 4일 연속하락 AND 거래량 ≥2×20일평균 (조건 중첩), 보유=2거래일, top300.")


# ---------------------------------------------------------------------------
# 게이트 판정 (순수함수 — 테스트 대상)
# ---------------------------------------------------------------------------

def evaluate_gates(m: dict) -> Dict[str, Tuple[bool, str]]:
    """메트릭 dict → {게이트: (PASS여부, 상세)}. 게이트별 독립 판정."""
    t = GATE_THRESHOLDS
    out: Dict[str, Tuple[bool, str]] = {}

    monthly = m.get("monthly_trades")
    g2 = (m["pnl"] > t["g2_pnl_min"] and m["sharpe"] > t["g2_sharpe_min"]
          and m["n_trades"] >= t["g2_trades_min"]
          and (monthly is None or monthly >= t["g2_monthly_trades_min"]))
    out["G2"] = (g2, f"pnl={m['pnl']:+.1%} sharpe={m['sharpe']:.2f} trades={m['n_trades']}"
                     + (f" 월{monthly:.1f}회" if monthly is not None else ""))

    dsharpe_ok = m["delta_sharpe"] > t["g3_dsharpe_min"]
    if m.get("g3_mode", "full") == "dsharpe_only":
        g3 = dsharpe_ok
        g3_note = " (corr·lift 참고치 — 단기보유 ΔSharpe 구속)"
    else:
        g3 = (m["corr_combo"] < t["g3_corr_max"] and m["tail_lift_combo"] < t["g3_lift_max"]
              and dsharpe_ok)
        g3_note = ""
    out["G3"] = (g3, f"corr={m['corr_combo']:.2f} lift={m['tail_lift_combo']:.2f} "
                     f"ΔSharpe={m['delta_sharpe']:+.3f}{g3_note}")

    wf_ok = (m["wf_total"] > 0
             and m["wf_pos"] / m["wf_total"] >= t["g4_wf_pos_min_ratio"] - 1e-9
             and m["wf_worst"] > t["g4_wf_worst_min"])
    out["G4_walkforward"] = (wf_ok, f"pos={m['wf_pos']}/{m['wf_total']} worst={m['wf_worst']:+.1%}")

    out["G4_bootstrap"] = (m["boot_sharpe_p05"] > t["g4_boot_p05_min"],
                           f"sharpe_p05={m['boot_sharpe_p05']:+.3f}")
    out["G4_cost"] = (m["cost30_pnl"] > 0.0, f"slip30bp pnl={m['cost30_pnl']:+.1%}")

    perturb_ok = len(m["perturb_pnls"]) > 0 and all(p > 0 for p in m["perturb_pnls"])
    out["G5_perturb"] = (perturb_ok,
                         "pnls=" + ",".join(f"{p:+.1%}" for p in m["perturb_pnls"]))
    out["G5_oos"] = (m["oos_train_sharpe"] > 0 and m["oos_test_sharpe"] > 0,
                     f"train={m['oos_train_sharpe']:.2f} test={m['oos_test_sharpe']:.2f}")
    return out


# ---------------------------------------------------------------------------
# 실행 파이프라인
# ---------------------------------------------------------------------------

def _run_sim(spec: CandidateSpec, data, turnover, cache) -> dict:
    res = run_portfolio(data=data, signal_cache=cache, adapter=spec.adapter,
                        params=spec.params, turnover=turnover,
                        initial_capital=INITIAL, max_positions=spec.K,
                        max_per_stock=MAX_PER_STOCK)
    dr: pd.Series = res["daily_returns"]
    dr.index = pd.to_datetime(dr.index)
    dr = dr.sort_index()
    eq = (1.0 + dr).cumprod()
    sells = [tr for tr in res["trades"] if tr["side"] == "sell"]
    mean_trade = (sum(float(tr["pnl_pct"]) for tr in sells) / len(sells)) if sells else 0.0
    return dict(dr=dr, pnl=float(eq.iloc[-1] - 1.0) if len(eq) else 0.0,
                sharpe=sharpe(dr.to_numpy()), maxdd=maxdd_from_returns(dr),
                n_trades=len(sells), mean_trade_pnl=mean_trade)


def run_candidate(spec: CandidateSpec, data, turnover,
                  live_returns: Dict[str, pd.Series], boot_iters: int = 1000) -> dict:
    """후보 1개 G2~G5 메트릭 수집. 신호 캐시는 base 1회 + 섭동 5회(비용런은 base 캐시 재사용)."""
    print(f"  [G2] base run ...")
    cache = spec.build_signals(data)
    base = _run_sim(spec, data, turnover, cache)
    dr = base["dr"]

    print(f"  [G3] corr vs live combo ...")
    combo = combine_sum_of_equities(live_returns)
    pair = pd.concat([dr.rename("cand"), combo.rename("combo")], axis=1).dropna()
    corr_combo = float(pair["cand"].corr(pair["combo"])) if len(pair) >= 60 else float("nan")
    lift = tail_coloss_lift(dr, combo)
    with_cand = dict(live_returns)
    with_cand[spec.name] = dr
    delta_sharpe = (sharpe(combine_sum_of_equities(with_cand).to_numpy())
                    - sharpe(combo.to_numpy()))

    print(f"  [G4] walkforward / bootstrap / cost30bp ...")
    wins = semiannual_windows(dr.index.min(), dr.index.max())
    wf_pnls = []
    for _, w0, w1 in wins:
        rw = dr[(dr.index >= w0) & (dr.index <= w1)].dropna()
        if len(rw) >= 20:
            wf_pnls.append(float((1.0 + rw).prod() - 1.0))
    boot = block_bootstrap_metrics(dr.fillna(0.0), n_iter=boot_iters)
    with _patch_costs(slippage=GATE_THRESHOLDS["g4_cost_slippage"]):
        cost30 = _run_sim(spec, data, turnover, cache)
    # 무비용 쌍둥이 런 (캐시 재사용) — 거래당 그로스 엣지 곡선용 (spec 부록A)
    with _patch_costs(commission=0.0, tax=0.0, slippage=0.0):
        zc = _run_sim(spec, data, turnover, cache)
    months = max(1.0, (dr.index.max() - dr.index.min()).days / 30.44)

    print(f"  [G5] perturbation x{len(spec.perturb)} / OOS ...")
    perturb_pnls = []
    for label, build in spec.perturb:
        pcache = build(data)
        pres = _run_sim(spec, data, turnover, pcache)
        perturb_pnls.append(pres["pnl"])
        print(f"    perturb {label}: pnl={pres['pnl']:+.1%} trades={pres['n_trades']}")
    split = pd.Timestamp(GATE_THRESHOLDS["g5_oos_split"])
    tr_s = sharpe(dr[dr.index <= split].to_numpy())
    te_s = sharpe(dr[dr.index > split].to_numpy())

    return dict(
        pnl=base["pnl"], sharpe=base["sharpe"], maxdd=base["maxdd"],
        n_trades=base["n_trades"], n_signals=sum(len(v) for v in cache.values()),
        monthly_trades=base["n_trades"] / months,
        edge_gross=zc["mean_trade_pnl"],          # 무비용 거래당 평균 (그로스 엣지)
        edge_net=base["mean_trade_pnl"] - (0.00015 * 2 + 0.0018),  # 슬리피지in − 수수료·세금
        zc_pnl=zc["pnl"],
        corr_combo=corr_combo, tail_lift_combo=lift, delta_sharpe=delta_sharpe,
        g3_mode=spec.g3_mode,
        wf_pos=sum(1 for p in wf_pnls if p > 0), wf_total=len(wf_pnls),
        wf_worst=min(wf_pnls) if wf_pnls else 0.0,
        boot_sharpe_p05=boot["sharpe_p05"], boot_maxdd_p50=boot["maxdd_p50"],
        cost30_pnl=cost30["pnl"],
        perturb_pnls=perturb_pnls,
        oos_train_sharpe=tr_s, oos_test_sharpe=te_s,
        dr=dr,
    )


def _report_md(name: str, spec: CandidateSpec, m: dict,
               gates: Dict[str, Tuple[bool, str]]) -> str:
    t = GATE_THRESHOLDS
    if all(ok for ok, _ in gates.values()):
        verdict = "PASS → G6 페이퍼 졸업 후보"
    elif m.get("edge_gross") is not None and t["edge_gross_etf"] <= m["edge_gross"] < t["edge_gross_adopt"]:
        verdict = ("REJECT(현물) but ★ETF 조건부 후보 — 그로스 엣지 "
                   f"{m['edge_gross']:+.2%}/거래 ∈ [0.2%, 0.5%) (거래세 면제 상품 재검 대상). FAIL: "
                   + ", ".join(g for g, (ok, _) in gates.items() if not ok))
    else:
        verdict = "REJECT (" + ", ".join(g for g, (ok, _) in gates.items() if not ok) + ")"
    edge_line = ""
    if m.get("edge_gross") is not None:
        edge_line = (f"- 거래당 엣지: 그로스 {m['edge_gross']:+.2%} · 넷(수수료·세금 차감) "
                     f"{m['edge_net']:+.2%} · 생존선(현물) {ROUNDTRIP_COST:.2%} · "
                     f"월평균 {m['monthly_trades']:.1f}회 · 무비용 PnL {m['zc_pnl']:+.1%}")
    lines = [
        f"# 게이트 리포트 — {name}",
        "",
        f"- 사양: {spec.note}",
        f"- 측정: top_volume:{spec.top_n} · K={spec.K} · 종목당 {MAX_PER_STOCK:,.0f}원(라이브 사이징) · "
        f"풀기간 연속 백테스트",
        f"- base: PnL {m['pnl']:+.1%} · Sharpe {m['sharpe']:.2f} · MaxDD {m['maxdd']:.1%} · "
        f"거래 {m['n_trades']} · 신호 {m['n_signals']}",
    ] + ([edge_line] if edge_line else []) + [
        "",
        "| 게이트 | 판정 | 상세 |",
        "|---|---|---|",
    ]
    for g, (ok, detail) in gates.items():
        lines.append(f"| {g} | {'✅ PASS' if ok else '❌ FAIL'} | {detail} |")
    lines += ["", f"**판정: {verdict}**", ""]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", nargs="*", default=list(CANDIDATES.keys()))
    ap.add_argument("--live-returns", default=str(ROOT / "reports" / "books_research" / "_mv4_returns"))
    ap.add_argument("--out", default=str(ROOT / "reports" / "discovery"))
    ap.add_argument("--top-n", type=int, default=50)
    ap.add_argument("--smoke", action="store_true", help="top20·부트스트랩 100회 축소")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    top_n = 20 if args.smoke else args.top_n
    boot_iters = 100 if args.smoke else 1000

    live_returns = load_returns(Path(args.live_returns))
    print(f"[live] 기존 활성 {len(live_returns)}전략 returns 로드")

    mn, mx = _daily_minmax_dates()
    # 유니버스/일봉 top_n 별 1회 로드 (배치3=300, 기본=50; --smoke/--top-n 은 강제 덮어씀)
    _cache: Dict[int, tuple] = {}

    def _get(tn: int):
        if tn not in _cache:
            uni = _load_top_volume_daily(mn, mx, tn)
            d = _load_daily_adj(uni, mn, mx)
            to = {c: float((df["close"] * df["volume"]).sum()) for c, df in d.items()}
            _cache[tn] = (d, to)
            print(f"[load] {mn}~{mx} top_n={tn} loaded={len(d)}")
        return _cache[tn]

    forced = args.smoke or args.top_n != 50
    summary = []
    for name in args.candidates:
        spec = CANDIDATES[name]
        tn = top_n if forced else spec.top_n
        data, turnover = _get(tn)
        print(f"\n===== {name} (top_n={tn}) =====")
        m = run_candidate(spec, data, turnover, live_returns, boot_iters=boot_iters)
        gates = evaluate_gates(m)
        md = _report_md(name, spec, m, gates)
        (out / f"gate_{name}.md").write_text(md, encoding="utf-8")
        dr_out = pd.DataFrame({"date": m["dr"].index.strftime("%Y-%m-%d"),
                               "daily_return": m["dr"].to_numpy()})
        dr_out.to_csv(out / f"returns_{name}.csv", index=False)
        all_pass = all(ok for ok, _ in gates.values())
        fails = [g for g, (ok, _) in gates.items() if not ok]
        t = GATE_THRESHOLDS
        verdict = "PASS" if all_pass else (
            "REJECT_ETF_COND" if t["edge_gross_etf"] <= m["edge_gross"] < t["edge_gross_adopt"]
            else "REJECT")
        summary.append(dict(candidate=name, verdict=verdict,
                            fails=";".join(fails),
                            pnl=round(m["pnl"], 4), sharpe=round(m["sharpe"], 3),
                            maxdd=round(m["maxdd"], 4), trades=m["n_trades"],
                            monthly=round(m["monthly_trades"], 1),
                            edge_gross=round(m["edge_gross"], 4),
                            corr=round(m["corr_combo"], 3),
                            lift=round(m["tail_lift_combo"], 2)))
        print(md)

    sdf = pd.DataFrame(summary)
    # 기존 요약과 병합 (배치 간 덮어쓰기 방지) — 같은 후보 재실행 시 최신으로 교체
    sum_path = out / "gate_summary.tsv"
    if sum_path.exists():
        prev = pd.read_csv(sum_path, sep="\t")
        prev = prev[~prev["candidate"].isin(sdf["candidate"])]
        sdf = pd.concat([prev, sdf], ignore_index=True)
    sdf.to_csv(sum_path, sep="\t", index=False)
    print("\n=== 배치 요약 ===")
    print(sdf.to_string(index=False))


if __name__ == "__main__":
    main()
