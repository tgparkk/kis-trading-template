"""Step 3 — 5.5년·전 전략·PIT 게이팅 정본 재측정 (측정 전용, 라이브 무수정).

목적: Step2 파일럿(1년·2전략·정적 union)을 올바른 정본으로 끌어올린다.
  - 기간: quant 일봉 전체(≈2021~2026, 5.5년). --start/--end 오버라이드.
  - 대상: SPECS 전 전략(elder/envelope/daytrading/minervini/ma20/ma5/rs_leader).
  - 3개 유니버스 × 전략:
      U0_topvol : 정본 top-volume(spec.top_n). step2 _u0 경로 재사용.
      U1_union  : 스크리너 base_filter union (데이터=union, 진입=union 전체).
      U2_PIT    : 데이터=union(warmup 확보), 진입신호=pit_gate_signal_cache 로 게이팅
                  (진입봉 시점 스크리너 멤버십만 인정 → union 퇴화 회피).

PIT 조립(라이브 무수정): run_one 이 build_signals 결과에 PIT 훅을 노출하지 않으므로,
run_one 내부 로직(spec.build_signals → run_portfolio)을 본 스크립트에서 재구성하되 그
사이에 pit_gate_signal_cache 를 끼운다. sim/룰/청산/비용/사이징/메트릭은 정본 그대로
(multiverse4 의 run_portfolio·_patch_costs·_sharpe·_maxdd·INITIAL·MAX_PER_STOCK 재사용).

deep_mr_dev20 는 multiverse4 SPECS 에 미배선 → 측정 불가(findings 에 명시).

scan 빈도: 월별(monthly) 기본 — PIT 근사. 시총·거래대금 완만 → 분기보다 정밀,
일별보다 가벼움. --scan-freq 로 변경.

usage:
  python scripts/step3_pit_rebaseline.py --smoke                      # 빠른 검증(짧은 기간)
  python scripts/step3_pit_rebaseline.py                              # 풀런(5.5년·전 전략·월별)
  python scripts/step3_pit_rebaseline.py --strategies book_pullback_ma5 elder_ema_pullback
  python scripts/step3_pit_rebaseline.py --start 2021-01-12 --end 2026-06-25 --scan-freq monthly
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from scripts.book_param_multiverse import _daily_minmax_dates, _load_top_volume_daily  # noqa: E402
from scripts.exit_multiverse.portfolio_sim import run_portfolio  # noqa: E402
from scripts.multiverse4_returns_export import (  # noqa: E402
    INITIAL,
    MAX_PER_STOCK,
    SPECS,
    _maxdd,
    _patch_costs,
    _sharpe,
    run_one,
)
# step2 무수정 재사용 — scan_date 생성·배치 일봉 로더·union 빌더·캐시 reader.
from scripts.step2_universe_rebaseline import (  # noqa: E402
    _build_screener_unions,
    _load_data,
    _scan_dates,
    _CachedReader,
)
from backtest.screener_universe import (  # noqa: E402
    make_scan_eligible_resolver,
    pit_gate_signal_cache,
)
from db.quant_daily_reader import QuantDailyReader  # noqa: E402

# deep_mr_dev20 는 harness SPECS 에 미배선 → 측정 대상에서 제외(findings 명시).
TARGET_STRATEGIES = list(SPECS.keys())


# ---------------------------------------------------------------------------
# U2_PIT — run_one 내부 로직을 재구성(build_signals → PIT 게이팅 → run_portfolio)
# ---------------------------------------------------------------------------

def _run_pit(spec, data: Dict[str, pd.DataFrame], turnover: Dict[str, float],
             eligible_resolver, max_per_stock: float) -> dict:
    """정본 run_one 과 동일하되, 신호캐시를 진입봉 시점 PIT 멤버십으로 게이팅.

    sim/청산/비용/사이징/메트릭은 multiverse4 그대로. 유일 차이 = signal_cache 마스킹.
    """
    cache = spec.build_signals(data)
    cache = pit_gate_signal_cache(cache, data, eligible_resolver)
    n_sig = sum(len(v) for v in cache.values())
    res = run_portfolio(data=data, signal_cache=cache, adapter=spec.adapter,
                        params=spec.params, turnover=turnover,
                        initial_capital=INITIAL, max_positions=spec.K,
                        max_per_stock=max_per_stock)
    dr: pd.Series = res["daily_returns"]
    dr.index = pd.to_datetime(dr.index)
    dr = dr.sort_index()
    eq = INITIAL * (1.0 + dr).cumprod()
    sells = [t for t in res["trades"] if t["side"] == "sell"]
    return dict(n_signals=n_sig, n_trades=len(sells),
                sharpe=_sharpe(dr.to_numpy()),
                pnl=float(eq.iloc[-1] / INITIAL - 1.0) if len(eq) else 0.0,
                maxdd=_maxdd(eq.to_numpy()))


def _row(strategy: str, label: str, uni_size: int, loaded: int, r: dict) -> dict:
    return dict(
        strategy=strategy, universe=label, uni_size=uni_size, loaded=loaded,
        n_signals=r["n_signals"], n_trades=r["n_trades"],
        sharpe=round(r["sharpe"], 3), pnl=round(r["pnl"], 4),
        maxdd=round(r["maxdd"], 4),
    )


def main(argv: Optional[List[str]] = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--scan-freq", choices=["monthly", "quarterly"], default="monthly",
                    help="PIT scan_date 빈도 (기본 monthly — 라이브 일별의 월별 근사)")
    ap.add_argument("--strategies", nargs="*", default=TARGET_STRATEGIES)
    ap.add_argument("--smoke", action="store_true",
                    help="짧은 기간(최근 1년)·소수 전략으로 빠른 검증")
    ap.add_argument("--out", default=str(ROOT / "docs" / "superpowers" / "plans"
                                         / "2026-06-25-step3-pit-rebaseline-findings.md"))
    ap.add_argument("--commission", type=float, default=None)
    ap.add_argument("--tax", type=float, default=None)
    ap.add_argument("--slippage", type=float, default=None)
    ap.add_argument("--max-per-stock", type=float, default=MAX_PER_STOCK)
    args = ap.parse_args(argv)

    mn, mx = _daily_minmax_dates()
    start = args.start or mn
    end = args.end or mx
    strategies = list(args.strategies)
    if args.smoke:
        start = "2025-06-01"
        end = mx
        # 스모크: 중소형 1·대조군 1만(빠른 검증). 명시 --strategies 가 있으면 존중.
        if args.strategies == TARGET_STRATEGIES:
            strategies = ["book_pullback_ma5", "elder_ema_pullback"]

    print(f"[period] {start} ~ {end}  scan_freq={args.scan_freq}  "
          f"max_per_stock={args.max_per_stock:,.0f}")
    print(f"[strategies] {strategies}")

    reader = QuantDailyReader()
    scan_dates = _scan_dates(start, end, args.scan_freq)
    print(f"[scan] {len(scan_dates)} dates: {scan_dates[0]} .. {scan_dates[-1]}")

    # U1 union 유니버스(전략별) — 날짜당 1회 스냅샷. PIT resolver 도 같은 _CachedReader 로
    # 스냅샷 재조회를 피한다(전략 무관 동일 스냅샷이므로 날짜당 1회만 DB).
    cached_reader = _CachedReader(reader)
    unions = _build_screener_unions(strategies, scan_dates, reader)
    market_size = len(reader.get_universe_snapshot(end) or [])
    print(f"[market] snapshot({end}) size={market_size}")
    for s in strategies:
        ratio = (len(unions[s]) / market_size) if market_size else 0.0
        print(f"[union] {s}: size={len(unions[s])} (={ratio:.0%} of market)")

    # U0 top-volume 데이터는 top_n 별 1회 로드 후 공유.
    u0_cache: Dict[int, tuple] = {}

    def _u0_data(top_n: int):
        if top_n not in u0_cache:
            uni = _load_top_volume_daily(start, end, top_n)
            print(f"[U0 load] top_n={top_n} universe={len(uni)} ...")
            u0_cache[top_n] = (_load_data(uni, start, end), uni)
        (data, turnover), uni = u0_cache[top_n]
        return data, turnover, uni

    rows: List[dict] = []
    with _patch_costs(args.commission, args.tax, args.slippage):
        for name in strategies:
            spec = SPECS[name]

            # --- U0 (top-volume baseline) ---
            data0, turn0, uni0 = _u0_data(spec.top_n)
            print(f"[run] {name} U0 (top_n={spec.top_n}, loaded={len(data0)}) ...")
            r0 = run_one(spec, data0, turn0, max_per_stock=args.max_per_stock)
            rows.append(_row(name, "U0_topvol", len(uni0), len(data0), r0))
            print(f"  U0: sig={r0['n_signals']} trades={r0['n_trades']} "
                  f"sharpe={r0['sharpe']:.2f} pnl={r0['pnl']:+.1%} maxdd={r0['maxdd']:.1%}")

            # --- U1 (screener union; data=union, entry=all union) ---
            codes1 = unions[name]
            data1, turn1 = _load_data(codes1, start, end)
            print(f"[run] {name} U1 (union={len(codes1)}, loaded={len(data1)}) ...")
            r1 = run_one(spec, data1, turn1, max_per_stock=args.max_per_stock)
            rows.append(_row(name, "U1_union", len(codes1), len(data1), r1))
            print(f"  U1: sig={r1['n_signals']} trades={r1['n_trades']} "
                  f"sharpe={r1['sharpe']:.2f} pnl={r1['pnl']:+.1%} maxdd={r1['maxdd']:.1%}")

            # --- U2 (PIT: data=union, entry gated by per-bar screener membership) ---
            resolver = make_scan_eligible_resolver(name, scan_dates, reader=cached_reader)
            print(f"[run] {name} U2 PIT (data=union {len(data1)}) ...")
            r2 = _run_pit(spec, data1, turn1, resolver, args.max_per_stock)
            rows.append(_row(name, "U2_PIT", len(codes1), len(data1), r2))
            print(f"  U2: sig={r2['n_signals']} trades={r2['n_trades']} "
                  f"sharpe={r2['sharpe']:.2f} pnl={r2['pnl']:+.1%} maxdd={r2['maxdd']:.1%}")

    df = pd.DataFrame(rows)
    print("\n=== SUMMARY ===")
    print(df.to_string(index=False))

    _write_findings(Path(args.out), df, start, end, args.scan_freq, scan_dates,
                    unions, u0_cache, market_size, strategies)
    print(f"\n[out] {args.out}")
    return df


def _write_findings(out: Path, df: pd.DataFrame, start: str, end: str, scan_freq: str,
                    scan_dates: List[str], unions: Dict[str, List[str]],
                    u0_cache: Dict[int, tuple], market_size: int,
                    strategies: List[str]):
    out.parent.mkdir(parents=True, exist_ok=True)

    def _md_table(frame: pd.DataFrame) -> str:
        cols = ["strategy", "universe", "uni_size", "loaded", "n_signals",
                "n_trades", "sharpe", "pnl", "maxdd"]
        head = "| " + " | ".join(cols) + " |\n"
        sep = "| " + " | ".join("---" for _ in cols) + " |\n"
        body = ""
        for _, r in frame.iterrows():
            vals = [
                str(r["strategy"]), str(r["universe"]), str(int(r["uni_size"])),
                str(int(r["loaded"])), str(int(r["n_signals"])), str(int(r["n_trades"])),
                f"{r['sharpe']:.3f}", f"{r['pnl']:+.2%}", f"{r['maxdd']:.2%}",
            ]
            body += "| " + " | ".join(vals) + " |\n"
        return head + sep + body

    # 전략별 U0→U1→U2 델타.
    delta_lines = []
    for strat in df["strategy"].unique():
        sub = df[df["strategy"] == strat]
        try:
            u0 = sub[sub["universe"] == "U0_topvol"].iloc[0]
            u1 = sub[sub["universe"] == "U1_union"].iloc[0]
            u2 = sub[sub["universe"] == "U2_PIT"].iloc[0]
        except IndexError:
            continue
        delta_lines.append(
            f"- **{strat}**: pnl {u0['pnl']:+.2%} → {u1['pnl']:+.2%} (union) → "
            f"{u2['pnl']:+.2%} (PIT); "
            f"sharpe {u0['sharpe']:.2f} → {u1['sharpe']:.2f} → {u2['sharpe']:.2f}; "
            f"trades {int(u0['n_trades'])} → {int(u1['n_trades'])} → {int(u2['n_trades'])}; "
            f"PIT signals {int(u2['n_signals'])} (union {int(u1['n_signals'])})"
        )

    u0_sizes = {tn: len(uni) for tn, ((_d, _t), uni) in u0_cache.items()}
    union_pct = "\n".join(
        f"- **{s}**: union {len(unions[s])} 종목 "
        f"(= 전체시장 {market_size}의 {(len(unions[s]) / market_size * 100 if market_size else 0):.0f}%)"
        for s in strategies
    )

    content = f"""# Step 3 — 5.5년·전 전략·PIT 정본 재측정 결과

> 측정 전용(라이브 코드/config 무수정). 영구룰: 숫자 검증·추정 금지 — 아래 수치는
> `scripts/step3_pit_rebaseline.py` 실행 산출(워킹트리).

## 측정 설정
- 기간: **{start} ~ {end}**
- scan 빈도(PIT/union): **{scan_freq}** — scan_date {len(scan_dates)}개 ({scan_dates[0]} .. {scan_dates[-1]})
- 비용/사이징: 정본 동일 (commission 0.015% / tax 0.18% / slippage 0.10%, max_per_stock=100만)
- sim·진입룰·청산·warmup·K: 정본 harness(`scripts/multiverse4_returns_export.py` SPECS) 그대로.
  **U2_PIT = run_one 로직을 스크립트에서 재구성(build_signals → pit_gate_signal_cache → run_portfolio).**

## 3-유니버스 비교표 (전략 × 유니버스)

{_md_table(df)}

- `U0_topvol` = 거래량 상위 top_n(대형주). top_n 별 실제 크기: {u0_sizes}
- `U1_union` = 스크리너 base_filter union (기간 내 scan_date 합집합; 데이터=union, 진입=union 전체)
- `U2_PIT` = 데이터=union(warmup 확보) + 진입신호를 진입봉 시점 스크리너 멤버십으로 게이팅
- `uni_size` = 유니버스 코드 수(요청), `loaded` = 일봉 30행+ 확보돼 실제 로딩된 종목 수

## 전략별 델타 (U0 → U1 → U2)

{chr(10).join(delta_lines)}

## 유니버스 구성 (union 크기 vs 전체시장 {market_size}종목)

{union_pct}

> ⚠️ **union 퇴화**: 풀기간(5.5년) union 은 base_filter 가 느슨한 전략에서 전체시장에
> 근접(Step2 findings 참조). U2_PIT 는 진입봉 시점 멤버십만 인정해 이 퇴화를 우회한다 →
> U1→U2 의 signals/trades/pnl 감소분이 "정적 union 낙관편향"의 크기다.

## harness 미배선
- **deep_mr_dev20**: multiverse4 `SPECS` 에 미배선 → 본 스크립트로 측정 불가.
  (build_signals/adapter spec 부재. 별도 배선 필요.)

## 한계
- **PIT 월별 근사**: 라이브 스크리너는 일별이나 본 측정은 {scan_freq} scan_date 멤버십으로
  근사. 시총·거래대금이 완만해 월별이 분기보다 정밀하나, 월 중 신규 진입/이탈 종목의
  멤버십 전환 시점은 ±수주 오차 가능.
- **union 데이터 로딩 비용**: 풀기간 union(코드 1000~2000+)을 _batch_load_daily(ANY(%s)
  단일쿼리)로 1회 적재하나, build_signals(_precompute_signals)는 종목·봉 루프라 union 이
  클수록 무겁다(전 전략 풀런은 수십분 단위 — 백그라운드 권장).
- **정본 출처**: U0 자체가 정본(top-volume) 재현 시도. U0 가 기존 PAPER_STRATEGIES 수치와
  다르면 그 정본은 다른 기간/사이징 출처.
"""
    out.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
