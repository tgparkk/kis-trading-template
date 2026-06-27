"""Step 3d — market_cap 백필 override 로 5.5년 PIT 재측정 (측정 전용, SSOT·라이브 무수정).

배경(2026-06-27):
  스크리너 시총 가드를 fail-closed 로 고친 뒤(c4df42c), quant ``daily_prices.market_cap``
  채움률이 2021=0% / 2022=0% / 2023=0.3% / 2024=85% / 2025=99.6% / 2026=99.8% 라
  2021–23 시총컷 전략의 유니버스가 *비어서* 5.5년 측정이 불가했다.

  백필 타당성(확정 조사): ``과거 시총 = FDR 현재주식수 × quant 조정종가(close, 이미 조정값)``.
  FinanceDataReader ``StockListing('KRX')['Stocks']`` = 현재 상장주식수(2875종목).
  2021–23 거래종목 99.6% 매칭, 샘플검증 정확(삼성 333조·하이닉스 65조).

설계(step3c 컴포넌트 재사용, SSOT·라이브 무수정, quant 테이블 UPDATE 금지):
  - ``MarketCapOverrideReader``: QuantDailyReader 를 감싸 ``get_universe_snapshot(date)``
    결과에서 ``market_cap`` 이 0/None 인 항목을 ``shares[code] * close(date)`` 로 메모리
    보강한다(채울 수 없으면 0 유지). close 는 같은 resolved date(snapshot 과 동일한
    ``date <= scan_date`` 최대일)의 일봉종가.
  - 이 override reader 를 step3c/step2 의 ``load_screener_universe``·``_build_screener_unions``·
    ``_CachedReader``·resolver 에 reader 로 주입 → base_filter(수정된 fail-closed)가
    보강된 market_cap 으로 올바로 binding.
  - sim/청산/비용/사이징/메트릭 = step3c ``_run_pit_cached`` 정본 그대로(multiverse4 SPECS).

usage:
  python scripts/step3d_backfill_5p5yr.py --smoke   # 짧은 기간 배선 확인
  python scripts/step3d_backfill_5p5yr.py           # 풀런(5.5년·월별 PIT·7전략)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
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

from scripts.book_param_multiverse import _daily_minmax_dates  # noqa: E402
from scripts.multiverse4_returns_export import MAX_PER_STOCK  # noqa: E402
from scripts.step2_universe_rebaseline import (  # noqa: E402
    _build_screener_unions,
    _load_data,
    _scan_dates,
    _CachedReader,
)
from scripts.step3c_size_sector_filter import (  # noqa: E402
    _resolver_for,
    _row,
    _run_pit_cached,
)
from scripts.multiverse4_returns_export import SPECS, _patch_costs  # noqa: E402
from backtest.data_completeness import (  # noqa: E402
    assert_market_cap_coverage,
    market_cap_coverage,
)
from db.quant_daily_reader import QuantDailyReader  # noqa: E402

# 7전략 — 시총컷 보유(elder·minervini·daytrading·ma5·ma20) + 거래대금만(envelope·rs).
ALL_STRATEGIES = [
    "elder_ema_pullback",
    "minervini_volume_dryup",
    "daytrading_3methods_breakout",
    "book_envelope_200d",
    "book_pullback_ma5",
    "book_pullback_ma20",
    "rs_leader",
]

# PIT-clean 시총 플로어 구성만(섹터 제외는 look-ahead 라 본 패스에서 미실행).
CONFIGS = ["baseline", "floor300", "floor500"]


# ---------------------------------------------------------------------------
# FDR 현재주식수 맵 — code(zfill6) -> 상장주식수. json 캐시.
# ---------------------------------------------------------------------------

def build_shares_map(cache_path: Path) -> Dict[str, float]:
    """FinanceDataReader StockListing('KRX') 의 'Stocks'(현재주식수) 맵. 캐시 우선."""
    if cache_path.exists():
        try:
            m = json.loads(cache_path.read_text(encoding="utf-8"))
            if m:
                print(f"[shares] cache hit ({len(m)} codes) -> {cache_path}")
                return {str(k): float(v) for k, v in m.items()}
        except Exception:
            pass
    import FinanceDataReader as fdr  # 지연 import — 캐시 적중 시 불필요.
    print("[shares] FDR StockListing('KRX') ...")
    df = fdr.StockListing("KRX")
    shares: Dict[str, float] = {}
    for _, r in df.iterrows():
        code = str(r["Code"]).zfill(6)
        s = r.get("Stocks")
        try:
            sv = float(s)
        except (TypeError, ValueError):
            continue
        if sv > 0:
            shares[code] = sv
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(shares, ensure_ascii=False), encoding="utf-8")
    print(f"[shares] built {len(shares)} codes -> {cache_path}")
    return shares


# ---------------------------------------------------------------------------
# market_cap override 리더 래퍼 — 결측 시총을 shares*close 로 메모리 보강.
# quant 테이블 UPDATE 금지 — snapshot dict 의 market_cap 만 in-memory 보강.
# ---------------------------------------------------------------------------

class MarketCapOverrideReader:
    """QuantDailyReader 래퍼. get_universe_snapshot 의 결측 market_cap 만 보강한다.

    각 snapshot item 의 market_cap 이 0/None 이면 ``shares[code] * close(date)`` 로 채운다.
    close 는 inner reader 와 동일한 resolved date(``date <= scan_date`` 의 max)에서 조회한다
    (snapshot 쿼리의 ``date = (SELECT max(date) WHERE date<=%s)`` 와 동일 기준일).
    채울 수 없으면(미매칭 shares/close 결측) market_cap 을 그대로 0 유지(fail-closed).
    그 외 모든 속성/메서드는 inner 로 위임.
    """

    def __init__(self, inner: QuantDailyReader, shares: Dict[str, float]):
        self._inner = inner
        self._shares = shares
        self._close_cache: Dict[str, Dict[str, float]] = {}

    def __getattr__(self, name):  # get_daily_prices 등 나머지는 inner 위임
        return getattr(self._inner, name)

    def _closes_for(self, scan_date) -> Dict[str, float]:
        key = scan_date if isinstance(scan_date, str) else scan_date.strftime("%Y-%m-%d")
        if key in self._close_cache:
            return self._close_cache[key]
        closes: Dict[str, float] = {}
        with self._inner._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT stock_code, close FROM daily_prices "
                    "WHERE date = (SELECT max(date) FROM daily_prices WHERE date <= %s)",
                    (key,),
                )
                for c, cl in cur.fetchall():
                    closes[str(c)] = float(cl) if cl is not None else 0.0
        self._close_cache[key] = closes
        return closes

    def get_universe_snapshot(self, scan_date) -> list:
        snap = self._inner.get_universe_snapshot(scan_date) or []
        need = [it for it in snap if not ((it.get("market_cap") or 0) > 0)]
        if not need:
            return snap
        closes = self._closes_for(scan_date)
        for it in snap:
            if (it.get("market_cap") or 0) > 0:
                continue
            code = str(it["stock_code"])
            sh = self._shares.get(code)
            cl = closes.get(code)
            if sh and cl and sh > 0 and cl > 0:
                it["market_cap"] = float(sh) * float(cl)
        return snap


def main(argv: Optional[List[str]] = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2021-01-12")
    ap.add_argument("--end", default=None)
    ap.add_argument("--scan-freq", choices=["monthly", "quarterly"], default="monthly")
    ap.add_argument("--strategies", nargs="*", default=ALL_STRATEGIES)
    ap.add_argument("--configs", nargs="*", default=CONFIGS)
    ap.add_argument("--smoke", action="store_true",
                    help="짧은 기간(2021-01~2021-06)으로 빠른 배선 확인")
    ap.add_argument("--shares-cache",
                    default=str(ROOT / "scratchpad" / "shares_map.json"))
    ap.add_argument("--out", default=str(ROOT / "scratchpad" / "step3d_backfill_5p5yr.md"))
    ap.add_argument("--max-per-stock", type=float, default=MAX_PER_STOCK)
    ap.add_argument("--min-cap-coverage", type=float, default=0.8)
    args = ap.parse_args(argv)

    mn, mx = _daily_minmax_dates()
    start = args.start or mn
    end = args.end or mx
    if args.smoke:
        start = "2021-01-12"
        end = "2021-06-30"

    strategies = list(args.strategies)
    configs = list(args.configs)
    print(f"[period] {start} ~ {end}  scan_freq={args.scan_freq}  "
          f"max_per_stock={args.max_per_stock:,.0f}")
    print(f"[strategies] {strategies}")
    print(f"[configs] {configs}")

    shares = build_shares_map(Path(args.shares_cache))
    base_reader = QuantDailyReader()
    reader = MarketCapOverrideReader(base_reader, shares)

    scan_dates = _scan_dates(start, end, args.scan_freq)
    print(f"[scan] {len(scan_dates)} dates: {scan_dates[0]} .. {scan_dates[-1]}")

    # 백필 전/후 채움률 비교 — 백필 효과 가시화.
    cov_raw = market_cap_coverage(base_reader, scan_dates, min_coverage=args.min_cap_coverage)
    print(f"[coverage:raw    ] {cov_raw.summary()}")
    cov = assert_market_cap_coverage(
        reader, scan_dates, min_coverage=args.min_cap_coverage, strict=False
    )
    print(f"[coverage:backfill] {cov.summary()}")

    cached_reader = _CachedReader(reader)
    unions = _build_screener_unions(strategies, scan_dates, reader)
    market_size = len(reader.get_universe_snapshot(end) or [])
    print(f"[market] snapshot({end}) size={market_size}")
    for s in strategies:
        ratio = (len(unions[s]) / market_size) if market_size else 0.0
        print(f"[union] {s}: size={len(unions[s])} (={ratio:.0%} of market)")

    rows: List[dict] = []
    t0 = time.time()
    with _patch_costs(None, None, None):
        for name in strategies:
            spec = SPECS[name]
            codes = unions[name]
            data, turn = _load_data(codes, start, end)
            print(f"\n[strategy] {name} (union={len(codes)}, loaded={len(data)}) "
                  f"build_signals ...", flush=True)
            base_cache = spec.build_signals(data)
            for config in configs:
                resolver = _resolver_for(config, name, scan_dates,
                                         reader=cached_reader, sector_map={})
                r = _run_pit_cached(spec, data, turn, base_cache, resolver,
                                    args.max_per_stock)
                rows.append(_row(name, config, len(codes), len(data), r))
                print(f"  {config:>10}: sig={r['n_signals']:>6} trades={r['n_trades']:>4} "
                      f"sharpe={r['sharpe']:+.3f} pnl={r['pnl']:+.1%} "
                      f"maxdd={r['maxdd']:.1%}", flush=True)

    df = pd.DataFrame(rows)
    print(f"\n=== SUMMARY ({time.time()-t0:.0f}s) ===")
    print(df.to_string(index=False))

    _write_report(Path(args.out), df, start, end, args.scan_freq, scan_dates,
                  unions, market_size, strategies, configs, cov_raw, cov, args.smoke)
    print(f"\n[out] {args.out}")
    return df


def _md_table(frame: pd.DataFrame) -> str:
    cols = ["strategy", "config", "uni_size", "loaded", "n_signals",
            "n_trades", "sharpe", "pnl", "maxdd"]
    head = "| " + " | ".join(cols) + " |\n"
    sep = "| " + " | ".join("---" for _ in cols) + " |\n"
    body = ""
    for _, r in frame.iterrows():
        vals = [
            str(r["strategy"]), str(r["config"]), str(int(r["uni_size"])),
            str(int(r["loaded"])), str(int(r["n_signals"])), str(int(r["n_trades"])),
            f"{r['sharpe']:+.3f}", f"{r['pnl']:+.2%}", f"{r['maxdd']:.2%}",
        ]
        body += "| " + " | ".join(vals) + " |\n"
    return head + sep + body


def _write_report(out: Path, df, start, end, scan_freq, scan_dates, unions,
                  market_size, strategies, configs, cov_raw, cov, smoke):
    out.parent.mkdir(parents=True, exist_ok=True)
    content = f"""# Step 3d — market_cap 백필 override 5.5년 PIT 재측정 (raw 출력)

> 측정 전용·SSOT·라이브 무수정. 신규 스크립트 `scripts/step3d_backfill_5p5yr.py` 실행 산출.
> market_cap override = 메모리 보강(quant 테이블 UPDATE 없음).

## 설정
- 기간: **{start} ~ {end}**{" (smoke)" if smoke else ""}, scan_freq={scan_freq}, scan_dates={len(scan_dates)}
- max_per_stock=100만, multiverse4 SPECS 정본 sim/비용/사이징.
- 백필: `과거 시총 = FDR 현재주식수(Stocks) × quant 조정종가(close)`.

## 데이터완전성 (백필 전/후)
- raw     : {cov_raw.summary()}
- backfill: {cov.summary()}

## 유니버스 (전체시장 snapshot({end})={market_size})
{chr(10).join(f"- **{s}**: union {len(unions[s])} ({(len(unions[s])/market_size*100 if market_size else 0):.0f}%)" for s in strategies)}

## 비교표 (전략 × 구성)

{_md_table(df)}
"""
    out.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
