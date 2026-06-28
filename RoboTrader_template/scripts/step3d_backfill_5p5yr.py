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

# 8전략 — 시총컷 보유(elder·minervini·daytrading·ma5·ma20) + 거래대금만(envelope·rs·deep_mr).
ALL_STRATEGIES = [
    "elder_ema_pullback",
    "minervini_volume_dryup",
    "daytrading_3methods_breakout",
    "book_envelope_200d",
    "book_pullback_ma5",
    "book_pullback_ma20",
    "rs_leader",
    "deep_mr_dev20",
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
# 2024-내재 주식수 — quant daily_prices 에서 market_cap 이 실재하는 첫 시점(연도)의
#   market_cap ÷ close = 내재 주식수. FDR 2026 현재주식수보다 2021–23 에 시간적으로 가깝고
#   (증자/자사주 오차 축소) quant 의 market_cap 정의(상장보통주)와 *동일 규약*이라 floor 게이트
#   일관성이 높다. 표본검증: 삼성 5.92e9(2024내재) vs DART 보통주 5.97e9(역사) 오차 0.85%,
#   FDR 현재 5.85e9 오차 2.1% → 2024내재가 역사주식수에 더 가깝다.
# ---------------------------------------------------------------------------

def build_implied_shares_map(reader: QuantDailyReader, year: int = 2024) -> Dict[str, float]:
    """각 종목의 ``year`` 첫 market_cap>0 시점 ``market_cap ÷ close`` = 내재 주식수."""
    shares: Dict[str, float] = {}
    with reader._conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (stock_code) stock_code, market_cap, close
                FROM daily_prices
                WHERE date >= %s AND date <= %s AND market_cap > 0 AND close > 0
                ORDER BY stock_code, date ASC
                """,
                (f"{year}-01-01", f"{year}-12-31"),
            )
            for code, mc, cl in cur.fetchall():
                try:
                    s = float(mc) / float(cl)
                except (TypeError, ValueError, ZeroDivisionError):
                    continue
                if s > 0:
                    shares[str(code)] = s
    print(f"[shares:implied{year}] built {len(shares)} codes (market_cap/close 첫 시점)")
    return shares


# ---------------------------------------------------------------------------
# DART 역사 주식수 — OPENDART stockTotqySttus 의 *보통주* 발행주식총수(진짜 역사값).
#   키(.env OPENDART_API_KEY)가 있을 때만. corp_code 매핑 + 종목당 1회 조회(json 캐시).
#   주: 합계(보통주+우선주) 아닌 *보통주* se 행을 쓴다(quant market_cap=상장보통주 규약 정합).
# ---------------------------------------------------------------------------

def _load_dotenv_min() -> str:
    """.env 에서 OPENDART_API_KEY 만 최소 로딩(python-dotenv 의존 회피)."""
    key = ""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OPENDART_API_KEY") and "=" in line:
                key = line.split("=", 1)[1].strip()
    return key


def _dart_corp_map(key: str) -> Dict[str, str]:
    import io as _io
    import zipfile
    import xml.etree.ElementTree as ET
    import requests
    z = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                     params={"crtfc_key": key}, timeout=60)
    zf = zipfile.ZipFile(_io.BytesIO(z.content))
    root = ET.fromstring(zf.read(zf.namelist()[0]))
    cmap: Dict[str, str] = {}
    for it in root.iter("list"):
        sc = (it.findtext("stock_code") or "").strip()
        cc = (it.findtext("corp_code") or "").strip()
        if sc and len(sc) == 6 and cc:
            cmap[sc] = cc
    return cmap


def build_dart_shares_map(codes: List[str], cache_path: Path, year: int = 2022,
                          key: Optional[str] = None) -> Dict[str, float]:
    """종목별 DART 보통주 발행주식총수(bsns_year=year 연간보고서). json 캐시. 키 없으면 {}."""
    key = key or _load_dotenv_min()
    if not key:
        print("[shares:dart] OPENDART_API_KEY 미설정 — DART 스킵")
        return {}
    cache: Dict[str, float] = {}
    if cache_path.exists():
        try:
            cache = {str(k): float(v) for k, v in
                     json.loads(cache_path.read_text(encoding="utf-8")).items()}
        except Exception:
            cache = {}
    todo = [c for c in codes if c not in cache]
    if not todo:
        print(f"[shares:dart] cache hit (all {len(codes)} codes) -> {cache_path}")
        return cache
    import time as _t
    import requests
    cmap = _dart_corp_map(key)
    print(f"[shares:dart] year={year} querying {len(todo)} codes (cached {len(cache)}) ...")
    for i, code in enumerate(todo, 1):
        cc = cmap.get(code)
        common = None
        if cc:
            try:
                r = requests.get(
                    "https://opendart.fss.or.kr/api/stockTotqySttus.json",
                    params={"crtfc_key": key, "corp_code": cc,
                            "bsns_year": str(year), "reprt_code": "11011"},
                    timeout=15).json()
                for row in (r.get("list") or []):
                    if "보통주" in str(row.get("se", "")):
                        v = str(row.get("istc_totqy", "")).replace(",", "")
                        if v.isdigit() and int(v) > 0:
                            common = float(int(v))
                        break
            except Exception:
                common = None
        if common is not None:
            cache[code] = common
        if i % 100 == 0 or i == len(todo):
            print(f"[shares:dart]   {i}/{len(todo)} (last {code}={common})")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        _t.sleep(0.12)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"[shares:dart] built {len(cache)} codes -> {cache_path}")
    return cache


def merge_shares_priority(*maps: Dict[str, float]) -> tuple:
    """우선순위대로 종목별 주식수 병합. 앞 map 이 우선. (merged, source_counts) 반환.

    source label = maps 의 인자 순서 인덱스에 대응(호출자가 라벨 매핑). 채울 수 없으면 결측 유지.
    """
    merged: Dict[str, float] = {}
    source: Dict[str, int] = {}
    allcodes = set()
    for m in maps:
        allcodes.update(m.keys())
    for code in allcodes:
        for idx, m in enumerate(maps):
            v = m.get(code)
            if v and v > 0:
                merged[code] = float(v)
                source[code] = idx
                break
    return merged, source


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

    ``shares`` 는 종목별 단일 주식수 dict 로, 정밀도 우선순위(merge_shares_priority)로 미리
    병합되어 주입된다(--shares-mode):
      1. DART 보통주 발행주식총수(역사 실값, OPENDART 키 필요)  — ``dart`` 모드.
      2. 2024-내재 주식수(quant market_cap÷close 첫 시점, 동일 규약·시간적 근접) — 기본.
      3. FDR 현재(2026) 상장주식수 — 폴백.
      4. 결측 유지(fail-closed).
    역사 실주식수(true precision)는 KRX/pykrx 차단으로 한정되나 DART 는 접근 가능
    (단 종목수×API 호출 비용·보통주/우선주 규약 주의 → 기본 off, 표본검증·opt-in).
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
    ap.add_argument("--dart-cache",
                    default=str(ROOT / "scratchpad" / "dart_shares_map.json"))
    ap.add_argument("--shares-mode", choices=["fdr", "implied2024", "dart"],
                    default="implied2024",
                    help="시총 백필 주식수 소스 우선순위. fdr=FDR현재(레거시), "
                         "implied2024=2024내재→FDR(기본·규약정합), dart=DART보통주→2024내재→FDR(역사실값).")
    ap.add_argument("--implied-year", type=int, default=2024,
                    help="내재주식수 산출 연도(market_cap÷close 첫 시점). 기본 2024.")
    ap.add_argument("--dart-year", type=int, default=2022,
                    help="DART 보통주 발행주식총수 조회 연도(2021–23 백필 대표값). 기본 2022.")
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

    base_reader = QuantDailyReader()
    # 정밀화 주식수 맵 — --shares-mode 우선순위로 병합(merge_shares_priority).
    fdr = build_shares_map(Path(args.shares_cache))
    if args.shares_mode == "fdr":
        shares, src = merge_shares_priority(fdr)
        src_labels = ["fdr"]
    else:
        implied = build_implied_shares_map(base_reader, args.implied_year)
        if args.shares_mode == "implied2024":
            shares, src = merge_shares_priority(implied, fdr)
            src_labels = [f"implied{args.implied_year}", "fdr"]
        else:  # dart
            cand = sorted(set(fdr) | set(implied))
            dart = build_dart_shares_map(cand, Path(args.dart_cache), args.dart_year)
            shares, src = merge_shares_priority(dart, implied, fdr)
            src_labels = ["dart", f"implied{args.implied_year}", "fdr"]
    from collections import Counter
    src_counts = dict(Counter(src_labels[i] for i in src.values()))
    print(f"[shares:mode={args.shares_mode}] merged {len(shares)} codes; source={src_counts}")
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
                  unions, market_size, strategies, configs, cov_raw, cov, args.smoke,
                  args.shares_mode, src_counts)
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
                  market_size, strategies, configs, cov_raw, cov, smoke,
                  shares_mode="implied2024", src_counts=None):
    out.parent.mkdir(parents=True, exist_ok=True)
    src_counts = src_counts or {}
    _backfill_desc = {
        "fdr": "FDR 현재주식수(Stocks) × quant 조정종가(close) [레거시]",
        "implied2024": "2024-내재주식수(market_cap÷close 첫 시점) → FDR 폴백, × quant close [규약정합]",
        "dart": "DART 보통주 발행주식총수(역사실값) → 2024-내재 → FDR, × quant close [true precision]",
    }.get(shares_mode, shares_mode)
    content = f"""# Step 3d — market_cap 백필 override 5.5년 PIT 재측정 (raw 출력)

> 측정 전용·SSOT·라이브 무수정. 신규 스크립트 `scripts/step3d_backfill_5p5yr.py` 실행 산출.
> market_cap override = 메모리 보강(quant 테이블 UPDATE 없음).

## 설정
- 기간: **{start} ~ {end}**{" (smoke)" if smoke else ""}, scan_freq={scan_freq}, scan_dates={len(scan_dates)}
- max_per_stock=100만, multiverse4 SPECS 정본 sim/비용/사이징.
- 백필 모드: **{shares_mode}** — {_backfill_desc}
- 주식수 소스 분포: {src_counts}

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
