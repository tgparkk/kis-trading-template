"""Step 2 파일럿 — 유니버스 재베이스라인 측정 (측정 전용, 라이브 무수정).

목적: 정본 harness(scripts/multiverse4_returns_export.py)의 유니버스를
top-volume(대형주)에서 *스크리너-정합 유니버스(전략 의도)*로 바꿔, 어느 전략 수치가
"잘못된 유니버스 아티팩트"였는지 측정한다. sim·룰·청산·비용·사이징은 정본을 그대로
재사용하고, **유니버스(=data dict의 키)만 교체**한다.

두 유니버스:
  U0(베이스라인) = scripts.book_param_multiverse._load_top_volume_daily(start,end,spec.top_n)
                   — 정적 거래량 상위N(대형주). 정본 harness 와 동일.
  U1(스크리너-정합) = backtest.screener_universe.load_screener_universe(strategy, d) 를
                   기간 내 월/분기 scan_date 들에 호출 → union. 각 날짜의 스냅샷은 전략
                   무관 동일하므로 **날짜별 1회 DB 조회 후 캐시**하고 각 전략 base_filter 만
                   다르게 적용(중복 조회 회피).

대상 전략: book_pullback_ma5, book_pullback_ma20, daytrading_3methods_breakout,
           elder_ema_pullback(대조군).

지표: 유니버스 크기, n_signals, n_trades, net Sharpe, pnl(총수익률), MaxDD. U0 vs U1.

한계:
  - U1 은 "정적 union"(기간 내 한 번이라도 스크리너 통과한 종목 전체)이라 PIT
    (진입일에 그 종목이 그 날 스크리너 통과했는지)보다 낙관적일 수 있다. PIT 게이팅은
    1차 측정에서 미적용(union)으로 명시.
  - 정본 수치(예: ma5 -52%)가 어느 harness/기간 출처인지 본 스크립트로는 불확실하므로,
    본 스크립트의 U0 자체가 그 정본 재현 시도임을 명시.

usage:
  python scripts/step2_universe_rebaseline.py                       # 전체 기간·분기 샘플
  python scripts/step2_universe_rebaseline.py --scan-freq monthly   # 월 1회 scan
  python scripts/step2_universe_rebaseline.py --smoke               # 빠른 검증(짧은 기간)
  python scripts/step2_universe_rebaseline.py --start 2021-01-12 --end 2026-06-25
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

from scripts.book_param_multiverse import (  # noqa: E402
    _daily_minmax_dates,
    _load_daily_adj,
    _load_top_volume_daily,
)
from scripts.multiverse4_returns_export import (  # noqa: E402
    MAX_PER_STOCK,
    SPECS,
    _patch_costs,
    run_one,
)
from backtest.screener_universe import load_screener_universe  # noqa: E402
from db.quant_daily_reader import QuantDailyReader  # noqa: E402

# 대상 전략(대조군 elder 포함)
TARGET_STRATEGIES = [
    "book_pullback_ma5",
    "book_pullback_ma20",
    "daytrading_3methods_breakout",
    "elder_ema_pullback",
]


# ---------------------------------------------------------------------------
# scan_date 생성 + 스크리너 union 유니버스
# ---------------------------------------------------------------------------

def _scan_dates(start: str, end: str, freq: str) -> List[str]:
    """[start, end] 의 scan_date 시퀀스 (월말 또는 분기말 기준일).

    freq="monthly" → 매월 말일, "quarterly" → 분기 말일. reader 가 date<=scan_date
    방어 폴백을 하므로 휴장/미적재일이어도 직전 거래일 스냅샷으로 안전하게 떨어진다.
    """
    rule = "ME" if freq == "monthly" else "QE"
    rng = pd.date_range(start=start, end=end, freq=rule)
    dates = [d.strftime("%Y-%m-%d") for d in rng]
    # 마지막 구간 보강: 마지막 scan_date 가 end 보다 한참 전이면 end 도 포함
    if not dates or dates[-1] < end:
        dates.append(end)
    # 첫 scan_date 가 start 보다 한참 뒤면 start 도 포함(초반 워밍업 구간 커버)
    if not dates or dates[0] > start:
        dates.insert(0, start)
    return dates


def _build_screener_unions(
    strategies: List[str], scan_dates: List[str], reader: QuantDailyReader
) -> Dict[str, List[str]]:
    """전략별 스크리너 union 코드집합.

    각 scan_date 의 스냅샷은 전략 무관 동일하므로, load_screener_universe 내부의
    get_universe_snapshot 호출은 reader 캐시로 1회만 일어나게 한다(아래 _CachedReader).
    """
    cached = _CachedReader(reader)
    unions: Dict[str, set] = {s: set() for s in strategies}
    for d in scan_dates:
        for s in strategies:
            codes = load_screener_universe(s, d, reader=cached)
            unions[s].update(codes)
    return {s: sorted(codes) for s, codes in unions.items()}


class _CachedReader:
    """get_universe_snapshot(scan_date) 결과를 날짜별 1회만 DB 조회하도록 캐싱.

    load_screener_universe 가 전략마다 같은 날짜로 호출해도 DB 는 날짜당 1번만 친다.
    """

    def __init__(self, inner: QuantDailyReader):
        self._inner = inner
        self._cache: Dict[str, list] = {}

    def get_universe_snapshot(self, scan_date) -> list:
        key = scan_date if isinstance(scan_date, str) else scan_date.strftime("%Y-%m-%d")
        if key not in self._cache:
            self._cache[key] = self._inner.get_universe_snapshot(key) or []
        return self._cache[key]


# ---------------------------------------------------------------------------
# 데이터 로딩 (U0 / U1)
# ---------------------------------------------------------------------------

# 전역 일봉 캐시 — U0/U1 4전략이 겹치는 종목을 중복 로딩하지 않게 1회만 적재.
# (정본 _load_daily_adj 는 코드당 1쿼리 직렬 → 풀기간 union(코드 2000+) 에서 8000+ 왕복
#  =22분 병목. 아래 _batch_load_daily 는 ANY(%s) 단일쿼리로 미적재 코드만 1회 적재.)
_DAILY_STORE: Dict[str, pd.DataFrame] = {}


def _batch_load_daily(codes: List[str], start: str, end: str) -> None:
    """미적재 코드만 단일 배치 쿼리로 _DAILY_STORE 에 채운다(정본 _load_daily_adj 정합).

    _load_daily_adj 와 동일한 컬럼/정제(quant close basis, adj_factor 미적용, 30행 미만
    제외, open/high/low<=0 → close 보정)를 유지하되, 코드당 1쿼리 대신 ANY(%s) 1쿼리로
    전부 가져와 코드별로 분할한다.
    """
    from scripts.book_param_multiverse import _quant_daily_connection, _DAILY_CODE_RE

    todo = [c for c in codes if c not in _DAILY_STORE]
    if not todo:
        return
    with _quant_daily_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT stock_code, date, open, high, low, close, volume
            FROM daily_prices
            WHERE stock_code = ANY(%s) AND date >= %s AND date <= %s
              AND stock_code ~ %s
            ORDER BY stock_code ASC, date ASC
            """,
            (todo, start, end, _DAILY_CODE_RE),
        )
        rows = cur.fetchall()
    if rows:
        big = pd.DataFrame(
            rows, columns=["stock_code", "date", "open", "high", "low", "close", "volume"]
        )
        for code, g in big.groupby("stock_code", sort=False):
            df = g.drop(columns=["stock_code"]).copy()
            df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
            df = df.dropna(subset=["date"])
            if len(df) < 30:
                continue
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            drop_mask = df["close"].isna() | (df["close"] <= 0)
            df = df[~drop_mask].copy()
            for col in ["open", "high", "low"]:
                fill_mask = df[col].isna() | (df[col] <= 0)
                df.loc[fill_mask, col] = df.loc[fill_mask, "close"]
            df = df.dropna(subset=["open", "high", "low", "close"])
            if len(df) < 30:
                continue
            df["datetime"] = df["date"]
            _DAILY_STORE[str(code)] = (
                df[["datetime", "open", "high", "low", "close", "volume"]]
                .reset_index(drop=True)
            )
    # 적재 실패(데이터 부족) 코드도 키로 마킹(빈 df) → 재시도 회피
    for c in todo:
        _DAILY_STORE.setdefault(c, None)  # type: ignore[assignment]


def _load_data(codes: List[str], start: str, end: str):
    """코드리스트 → {code: df} + turnover dict (run_one 입력). 전역 캐시 재사용."""
    _batch_load_daily(codes, start, end)
    data = {c: _DAILY_STORE[c] for c in codes
            if _DAILY_STORE.get(c) is not None}
    turnover = {c: float((df["close"] * df["volume"]).sum()) for c, df in data.items()}
    return data, turnover


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------

def _row(strategy: str, universe_label: str, uni_size: int, loaded: int, r: dict) -> dict:
    return dict(
        strategy=strategy,
        universe=universe_label,
        uni_size=uni_size,
        loaded=loaded,
        n_signals=r["n_signals"],
        n_trades=r["n_trades"],
        sharpe=round(r["sharpe"], 3),
        pnl=round(r["pnl"], 4),
        maxdd=round(r["maxdd"], 4),
    )


def main(argv: Optional[List[str]] = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--scan-freq", choices=["monthly", "quarterly"], default="quarterly",
                    help="U1 union 을 만들 scan_date 빈도 (기본 분기)")
    ap.add_argument("--strategies", nargs="*", default=TARGET_STRATEGIES)
    ap.add_argument("--smoke", action="store_true",
                    help="짧은 기간(최근 1년)·분기 샘플로 빠른 검증")
    ap.add_argument("--out", default=str(ROOT / "docs" / "superpowers" / "plans"
                                         / "2026-06-25-step2-rebaseline-findings.md"))
    ap.add_argument("--commission", type=float, default=None)
    ap.add_argument("--tax", type=float, default=None)
    ap.add_argument("--slippage", type=float, default=None)
    ap.add_argument("--max-per-stock", type=float, default=MAX_PER_STOCK)
    args = ap.parse_args(argv)

    mn, mx = _daily_minmax_dates()
    start = args.start or mn
    end = args.end or mx
    if args.smoke:
        # 최근 1년·분기 샘플로 축소
        start = "2025-06-01"
        end = mx
        args.scan_freq = "quarterly"

    print(f"[period] {start} ~ {end}  scan_freq={args.scan_freq}  "
          f"max_per_stock={args.max_per_stock:,.0f}")

    reader = QuantDailyReader()
    scan_dates = _scan_dates(start, end, args.scan_freq)
    print(f"[scan] {len(scan_dates)} dates: {scan_dates[0]} .. {scan_dates[-1]}")

    # U1 union 유니버스 (전략별) — 날짜당 1회 스냅샷
    unions = _build_screener_unions(args.strategies, scan_dates, reader)
    # 전체시장 기준 크기(스냅샷 종목수) — union 이 시장 전체에 얼마나 근접했는지(=union 퇴화)
    market_size = len(reader.get_universe_snapshot(end) or [])
    print(f"[market] snapshot({end}) size={market_size}")
    for s in args.strategies:
        ratio = (len(unions[s]) / market_size) if market_size else 0.0
        print(f"[U1] {s}: union size={len(unions[s])} (={ratio:.0%} of market)")

    # U0 데이터는 top_n 별로 1회 로드 후 공유 (4 전략 중 top_n 다른 것만 별도 로드)
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
        for name in args.strategies:
            spec = SPECS[name]

            # --- U0 (top-volume baseline) ---
            data0, turn0, uni0 = _u0_data(spec.top_n)
            print(f"[run] {name} U0 (top_n={spec.top_n}, loaded={len(data0)}) ...")
            r0 = run_one(spec, data0, turn0, max_per_stock=args.max_per_stock)
            rows.append(_row(name, "U0_topvol", len(uni0), len(data0), r0))
            print(f"  U0: sig={r0['n_signals']} trades={r0['n_trades']} "
                  f"sharpe={r0['sharpe']:.2f} pnl={r0['pnl']:+.1%} maxdd={r0['maxdd']:.1%}")

            # --- U1 (screener-aligned union) ---
            codes1 = unions[name]
            data1, turn1 = _load_data(codes1, start, end)
            print(f"[run] {name} U1 (union={len(codes1)}, loaded={len(data1)}) ...")
            r1 = run_one(spec, data1, turn1, max_per_stock=args.max_per_stock)
            rows.append(_row(name, "U1_screener", len(codes1), len(data1), r1))
            print(f"  U1: sig={r1['n_signals']} trades={r1['n_trades']} "
                  f"sharpe={r1['sharpe']:.2f} pnl={r1['pnl']:+.1%} maxdd={r1['maxdd']:.1%}")

    df = pd.DataFrame(rows)
    print("\n=== SUMMARY ===")
    print(df.to_string(index=False))

    _write_findings(Path(args.out), df, start, end, args.scan_freq, scan_dates,
                    unions, u0_cache, market_size)
    print(f"\n[out] {args.out}")
    return df


def _write_findings(out: Path, df: pd.DataFrame, start: str, end: str, scan_freq: str,
                    scan_dates: List[str], unions: Dict[str, List[str]],
                    u0_cache: Dict[int, tuple], market_size: int = 0):
    out.parent.mkdir(parents=True, exist_ok=True)

    # U0 vs U1 비교표 (전략 × 지표) 마크다운
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

    # 전략별 델타 요약
    delta_lines = []
    for strat in df["strategy"].unique():
        sub = df[df["strategy"] == strat]
        u0 = sub[sub["universe"] == "U0_topvol"].iloc[0]
        u1 = sub[sub["universe"] == "U1_screener"].iloc[0]
        delta_lines.append(
            f"- **{strat}**: pnl {u0['pnl']:+.2%} → {u1['pnl']:+.2%} "
            f"(Δ {u1['pnl'] - u0['pnl']:+.2%}), "
            f"sharpe {u0['sharpe']:.2f} → {u1['sharpe']:.2f}, "
            f"trades {int(u0['n_trades'])} → {int(u1['n_trades'])}, "
            f"uni {int(u0['uni_size'])} → {int(u1['uni_size'])}"
        )

    u0_sizes = {tn: len(uni) for tn, ((_d, _t), uni) in u0_cache.items()}

    content = f"""# Step 2 파일럿 — 유니버스 재베이스라인 측정 결과

> 측정 전용(라이브 코드/config 무수정). 영구룰: 숫자 검증·추정 금지 — 아래 수치는
> `scripts/step2_universe_rebaseline.py` 실행 산출(워킹트리, 커밋 안 함).

## 측정 설정
- 기간: **{start} ~ {end}**
- scan 빈도(U1 union): **{scan_freq}** — scan_date {len(scan_dates)}개 ({scan_dates[0]} .. {scan_dates[-1]})
- 비용/사이징: 정본 동일 (commission 0.015% / tax 0.18% / slippage 0.10%, max_per_stock=100만)
- sim·진입룰·청산·warmup·K: 정본 harness(`scripts/multiverse4_returns_export.py` SPECS) 그대로.
  **유니버스(=data dict 키)만 교체.**

## U0 vs U1 비교표 (전략 × 지표)

{_md_table(df)}

- `U0_topvol` = 거래량 상위 top_n(대형주). top_n 별 실제 크기: {u0_sizes}
- `U1_screener` = 스크리너 base_filter union (기간 내 scan_date 합집합)
- `uni_size` = 유니버스 코드 수(요청), `loaded` = 일봉 30행+ 확보돼 실제 로딩된 종목 수

## 전략별 델타 (U0 → U1)

{chr(10).join(delta_lines)}

## 유니버스 구성 차이 (U1 union 크기 vs 전체시장 {market_size}종목)

{chr(10).join(f'- **{s}**: {len(c)} 종목 (= 전체시장의 {(len(c)/market_size*100 if market_size else 0):.0f}%)' for s, c in unions.items())}

> ⚠️ **union 퇴화 경고**: 기간이 길수록(특히 풀기간 2021~2026) base_filter 가 느슨한
> 전략(ma5/ma20/daytrading)의 union 은 전체시장의 ~97% 까지 부풀어 "스크리너 의도"가
> 아니라 "거의 전종목"이 된다. 즉 풀기간 U1 은 *스크리너-정합*이라기보다 *전체시장
> 백테스트*에 가깝다. 짧은 창(단일일/연단위)에서 union 이 선택적(예: ma5 단일일 ~911,
> 연 union ~1300, 풀기간 union 2290)이라 헤드라인은 **짧은 창** 결과를 우선한다.

## 핵심 판정 (어느 전략이 유니버스 아티팩트였나)

> (실행 후 수동 해석 필요 — 아래는 가설 점검 틀)
> - 중소형 의도 전략(ma5·ma20·daytrading)이 U1 에서 U0 대비 **의미있게 달라지면**
>   해당 정본 수치는 "대형주 유니버스 아티팩트"였을 가능성.
> - elder(대조군): U0 와 U1 의 유니버스 성격(대형 top-volume vs base_filter union)이
>   실제로 다르므로 단순 U0≈U1 sanity 는 성립하지 않을 수 있음 — 표의 실제 델타로 판단.

## 한계
- **union vs PIT**: U1 은 기간 내 한 번이라도 스크리너 통과한 종목 전체(정적 union).
  진입일 시점 PIT 게이팅(그 날 스크리너 통과 여부)은 미적용 → U1 은 낙관 가능.
- **표본기간**: scan_date 를 {scan_freq} 샘플(union)로 만들어, 그 사이 진입/이탈한
  단기 후보가 union 에 더해지거나 빠질 수 있음.
- **정본 수치 출처 불확실**: ma5 -52% 등 기존 정본 수치가 어느 harness/기간 산출인지
  본 스크립트로 단정 불가. 본 스크립트의 U0 자체가 그 정본(top-volume) 재현 시도이며,
  U0 수치가 정본과 다르면 정본은 다른 기간/유니버스/사이징 출처임.
"""
    out.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
