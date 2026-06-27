"""Step 3c — 시총 플로어·섹터 제외 필터의 OOS 검증 (측정 전용, 라이브 무수정).

배경(2026-06-27 in-sample 반사실 검증 → OOS 확인 목적):
  페이퍼 상위4전략(daytrading_3methods_breakout, elder_ema_pullback,
  book_envelope_200d, rs_leader)의 116 SELL 분석에서 두 가설:
    가설A(시총 플로어): 초소형주(시총<300억=3e10원) 진입 컷 → 갭 손절관통 감소.
    가설B(섹터 제외): 반도체와반도체장비·전자장비와기기 제외.
  in-sample(6월) 적용 시 실현 −1.12M→+1.17M(4전략 전부 흑자전환)이나 과적합·6월
  반도체약세 특수성 위험 → 정식 다년 PIT 백테스트로 OOS 검증.

설계(step3_pit_rebaseline 하니스 재사용, step3 원본·라이브 무수정):
  step3 의 _run_pit(build_signals → pit_gate_signal_cache → run_portfolio)·_load_data·
  _build_screener_unions·_scan_dates·_CachedReader·SPECS·_patch_costs 를 그대로 import.
  유일 추가 = PIT resolver 변형(make_filtered_resolver): step3 의 통과집합(load_screener_
  universe) 위에 *scan_date 시점 snapshot 의 market_cap 플로어*(PIT-clean)와 섹터 제외
  (근사)를 곱한다.

구성(전략별):
  baseline            : 필터 없음 = step3 U2_PIT (make_scan_eligible_resolver).
  floor300            : market_cap >= 3e10 (300억).  ← PIT-clean(snapshot market_cap).
  floor500            : market_cap >= 5e10 (500억).  민감도용.
  ex_sector           : 반도체와반도체장비·전자장비와기기 제외.  ← 근사(현재 섹터 소급).
  floor300_ex_sector  : 둘 다.

섹터맵: 네이버 종목페이지 스크랩(현재 정적값). union 코드 1회 스크랩 →
  scratchpad/sector_map.json 캐시(있으면 재사용). 현재 섹터를 과거에 소급적용 =
  look-ahead·상폐누락 한계(리포트에 명시).

usage:
  python scripts/step3c_size_sector_filter.py --smoke   # 짧은 기간 배선 확인
  python scripts/step3c_size_sector_filter.py           # 풀런(5.5년·월별 PIT)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
from scripts.exit_multiverse.portfolio_sim import run_portfolio  # noqa: E402
from scripts.multiverse4_returns_export import (  # noqa: E402
    INITIAL,
    MAX_PER_STOCK,
    SPECS,
    _maxdd,
    _patch_costs,
    _sharpe,
)
from backtest.screener_universe import pit_gate_signal_cache  # noqa: E402
from backtest.data_completeness import assert_market_cap_coverage  # noqa: E402
from scripts.step2_universe_rebaseline import (  # noqa: E402
    _build_screener_unions,
    _load_data,
    _scan_dates,
    _CachedReader,
)
from backtest.screener_universe import (  # noqa: E402
    load_screener_universe,
    make_scan_eligible_resolver,
    _to_date_str,
)
from db.quant_daily_reader import QuantDailyReader  # noqa: E402

# 대상 4전략(페이퍼 상위4 = 116 SELL 가설 출처).
TARGET_STRATEGIES = [
    "daytrading_3methods_breakout",
    "elder_ema_pullback",
    "book_envelope_200d",
    "rs_leader",
]

# 제외 대상 업종명(네이버 표기). 가설B.
EX_SECTOR_NAMES = {"반도체와반도체장비", "전자장비와기기"}

FLOOR_300 = 3e10   # 300억원
FLOOR_500 = 5e10   # 500억원


# ---------------------------------------------------------------------------
# 필터 PIT resolver — step3 통과집합 위에 (PIT market_cap 플로어 + 섹터 제외)를 곱한다.
# ---------------------------------------------------------------------------

def make_filtered_resolver(
    strategy_name: str,
    scan_dates: List[str],
    *,
    reader,
    floor: float = 0.0,
    ex_sectors: Optional[set] = None,
    sector_map: Optional[Dict[str, str]] = None,
) -> Callable[[str, Any], bool]:
    """make_scan_eligible_resolver 변형 — 통과집합에 시총 플로어·섹터 제외를 추가.

    각 scan_date 의 base_filter 통과집합(load_screener_universe)을 구한 뒤:
      - floor>0 : 그 scan_date snapshot 의 market_cap >= floor 인 코드만 유지(PIT-clean).
      - ex_sectors: sector_map[code] 가 제외 업종이면 제거(근사 — 현재 섹터 소급).
    resolver(code, d) 는 가장 최근 scan_date <= d 의 (필터링된) 통과집합 멤버십을 본다.
    """
    ex_sectors = set(ex_sectors or set())
    sector_map = sector_map or {}
    sorted_dates = sorted(
        {(d if isinstance(d, str) else _to_date_str(d)) for d in scan_dates}
    )
    passers: Dict[str, set] = {}

    def _passers_for(scan_date: str) -> set:
        if scan_date not in passers:
            codeset = set(load_screener_universe(strategy_name, scan_date, reader=reader))
            if floor and floor > 0:
                snap = reader.get_universe_snapshot(scan_date) or []
                mc = {str(it["stock_code"]): float(it.get("market_cap", 0) or 0)
                      for it in snap}
                codeset = {c for c in codeset if mc.get(c, 0.0) >= floor}
            if ex_sectors:
                codeset = {c for c in codeset
                           if sector_map.get(c, "?") not in ex_sectors}
            passers[scan_date] = codeset
        return passers[scan_date]

    def resolver(code: str, d: Any) -> bool:
        d_str = d if isinstance(d, str) else _to_date_str(d)
        chosen: Optional[str] = None
        for sd in reversed(sorted_dates):
            if sd <= d_str:
                chosen = sd
                break
        if chosen is None:
            return False
        return code in _passers_for(chosen)

    return resolver


# ---------------------------------------------------------------------------
# 섹터맵 — 네이버 종목페이지 스크랩(현재 정적값). union 코드 1회 스크랩 → json 캐시.
# ---------------------------------------------------------------------------

def build_sector_map(codes: List[str], cache_path: Path) -> Dict[str, str]:
    """code → 업종명 맵. cache_path 가 있고 모든 코드를 덮으면 스크랩 생략.

    실패/404 는 '?' 로 둔다. euc-kr 아님(UTF-8). 0.07s sleep.
    """
    cache: Dict[str, str] = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    todo = [c for c in codes if c not in cache]
    if not todo:
        print(f"[sector] cache hit (all {len(codes)} codes) -> {cache_path}")
        return cache

    import requests  # 지연 import — 캐시 적중 시 의존성 불필요.
    print(f"[sector] scraping {len(todo)} codes (cached {len(cache)}) ...")
    pat = re.compile(r'upjong&no=\d+["\']>([^<]+)</a>')
    headers = {"User-Agent": "Mozilla/5.0"}
    for i, code in enumerate(todo, 1):
        sector = "?"
        try:
            html = requests.get(
                f"https://finance.naver.com/item/main.naver?code={code}",
                headers=headers, timeout=10,
            ).content.decode("utf-8", "replace")
            m = pat.search(html)
            if m:
                sector = m.group(1).strip()
        except Exception:
            sector = "?"
        cache[code] = sector
        if i % 50 == 0 or i == len(todo):
            print(f"[sector]   {i}/{len(todo)} (last {code}={sector})")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=0),
                                  encoding="utf-8")
        time.sleep(0.07)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=0),
                          encoding="utf-8")
    print(f"[sector] done -> {cache_path}")
    return cache


# ---------------------------------------------------------------------------
# 구성 정의
# ---------------------------------------------------------------------------

CONFIGS = ["baseline", "floor300", "floor500", "ex_sector", "floor300_ex_sector"]


def _resolver_for(config: str, strategy: str, scan_dates: List[str], *, reader,
                  sector_map: Dict[str, str]):
    if config == "baseline":
        # step3 U2_PIT 정확 재현.
        return make_scan_eligible_resolver(strategy, scan_dates, reader=reader)
    floor = 0.0
    ex = None
    if config == "floor300":
        floor = FLOOR_300
    elif config == "floor500":
        floor = FLOOR_500
    elif config == "ex_sector":
        ex = EX_SECTOR_NAMES
    elif config == "floor300_ex_sector":
        floor = FLOOR_300
        ex = EX_SECTOR_NAMES
    else:
        raise ValueError(f"unknown config {config}")
    return make_filtered_resolver(strategy, scan_dates, reader=reader,
                                  floor=floor, ex_sectors=ex, sector_map=sector_map)


def _run_pit_cached(spec, data, turnover, base_cache, eligible_resolver,
                    max_per_stock: float) -> dict:
    """step3 `_run_pit` 와 동일하되 build_signals 산출(base_cache)을 재사용한다.

    step3 _run_pit 은 config 마다 spec.build_signals(data) 를 재계산(전략당 5회 중복).
    base_cache(전략당 1회 build_signals 결과)를 받아 PIT 게이팅·sim 만 config 별로 수행.
    sim/청산/비용/사이징/메트릭은 multiverse4 정본 그대로(_run_pit 와 수식 동일).
    """
    cache = pit_gate_signal_cache(base_cache, data, eligible_resolver)
    n_sig = sum(len(v) for v in cache.values())
    res = run_portfolio(data=data, signal_cache=cache, adapter=spec.adapter,
                        params=spec.params, turnover=turnover,
                        initial_capital=INITIAL, max_positions=spec.K,
                        max_per_stock=max_per_stock)
    dr = res["daily_returns"]
    dr.index = pd.to_datetime(dr.index)
    dr = dr.sort_index()
    eq = INITIAL * (1.0 + dr).cumprod()
    sells = [t for t in res["trades"] if t["side"] == "sell"]
    return dict(n_signals=n_sig, n_trades=len(sells),
                sharpe=_sharpe(dr.to_numpy()),
                pnl=float(eq.iloc[-1] / INITIAL - 1.0) if len(eq) else 0.0,
                maxdd=_maxdd(eq.to_numpy()))


def _row(strategy: str, config: str, uni_size: int, loaded: int, r: dict) -> dict:
    return dict(
        strategy=strategy, config=config, uni_size=uni_size, loaded=loaded,
        n_signals=r["n_signals"], n_trades=r["n_trades"],
        sharpe=round(r["sharpe"], 3), pnl=round(r["pnl"], 4),
        maxdd=round(r["maxdd"], 4),
    )


def main(argv: Optional[List[str]] = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--scan-freq", choices=["monthly", "quarterly"], default="monthly")
    ap.add_argument("--strategies", nargs="*", default=TARGET_STRATEGIES)
    ap.add_argument("--configs", nargs="*", default=CONFIGS)
    ap.add_argument("--smoke", action="store_true",
                    help="짧은 기간(최근 1년)으로 빠른 배선 확인")
    ap.add_argument("--sector-cache",
                    default=str(ROOT / "scratchpad" / "sector_map.json"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "superpowers" / "plans"
                                         / "2026-06-27-size-sector-filter-backtest.md"))
    ap.add_argument("--max-per-stock", type=float, default=MAX_PER_STOCK)
    ap.add_argument("--min-cap-coverage", type=float, default=0.8,
                    help="측정 구간 market_cap 채움률 임계(미만이면 경고). 기본 0.8")
    ap.add_argument("--strict-coverage", action="store_true",
                    help="채움률 임계 미만이면 경고 대신 즉시 실패(오염 구간 측정 차단)")
    args = ap.parse_args(argv)

    mn, mx = _daily_minmax_dates()
    start = args.start or mn
    end = args.end or mx
    if args.smoke:
        start = "2025-06-01"
        end = mx

    strategies = list(args.strategies)
    configs = list(args.configs)
    print(f"[period] {start} ~ {end}  scan_freq={args.scan_freq}  "
          f"max_per_stock={args.max_per_stock:,.0f}")
    print(f"[strategies] {strategies}")
    print(f"[configs] {configs}")

    reader = QuantDailyReader()
    scan_dates = _scan_dates(start, end, args.scan_freq)
    print(f"[scan] {len(scan_dates)} dates: {scan_dates[0]} .. {scan_dates[-1]}")

    # 데이터완전성 가드 — 측정 구간 market_cap 채움률이 임계 미만이면 경고/실패.
    # 2021–23 처럼 시총 결측 지배 구간을 모르고 측정하는 사일런트 재발을 막는다.
    cov = assert_market_cap_coverage(
        reader, scan_dates, min_coverage=args.min_cap_coverage, strict=args.strict_coverage
    )
    print(f"[coverage] {cov.summary()}")

    cached_reader = _CachedReader(reader)
    unions = _build_screener_unions(strategies, scan_dates, reader)
    market_size = len(reader.get_universe_snapshot(end) or [])
    print(f"[market] snapshot({end}) size={market_size}")
    for s in strategies:
        ratio = (len(unions[s]) / market_size) if market_size else 0.0
        print(f"[union] {s}: size={len(unions[s])} (={ratio:.0%} of market)")

    # 섹터맵 — 4전략 union 코드 전체에 대해 1회 스크랩(필요 시).
    need_sector = any(c in ("ex_sector", "floor300_ex_sector") for c in configs)
    sector_map: Dict[str, str] = {}
    if need_sector:
        all_codes = sorted({c for s in strategies for c in unions[s]})
        sector_map = build_sector_map(all_codes, Path(args.sector_cache))
        ex_hits = sum(1 for v in sector_map.values() if v in EX_SECTOR_NAMES)
        unknown = sum(1 for c in all_codes if sector_map.get(c, "?") == "?")
        print(f"[sector] union codes={len(all_codes)} ex_sector_hits={ex_hits} "
              f"unknown={unknown}")

    # 전략별 union 일봉 1회 로드 후 전 구성 공유(데이터=union, 진입만 resolver 게이팅).
    rows: List[dict] = []
    with _patch_costs(None, None, None):
        for name in strategies:
            spec = SPECS[name]
            codes = unions[name]
            data, turn = _load_data(codes, start, end)
            print(f"\n[strategy] {name} (union={len(codes)}, loaded={len(data)}) "
                  f"build_signals ...", flush=True)
            base_cache = spec.build_signals(data)  # 전략당 1회(전 config 공유).
            for config in configs:
                resolver = _resolver_for(config, name, scan_dates,
                                         reader=cached_reader, sector_map=sector_map)
                r = _run_pit_cached(spec, data, turn, base_cache, resolver,
                                    args.max_per_stock)
                rows.append(_row(name, config, len(codes), len(data), r))
                print(f"  {config:>18}: sig={r['n_signals']:>5} trades={r['n_trades']:>4} "
                      f"sharpe={r['sharpe']:+.2f} pnl={r['pnl']:+.1%} "
                      f"maxdd={r['maxdd']:.1%}")

    df = pd.DataFrame(rows)
    print("\n=== SUMMARY ===")
    print(df.to_string(index=False))

    _write_report(Path(args.out), df, start, end, args.scan_freq, scan_dates,
                  unions, market_size, strategies, configs, sector_map, args.smoke)
    print(f"\n[out] {args.out}")
    return df


def _write_report(out: Path, df: pd.DataFrame, start: str, end: str, scan_freq: str,
                  scan_dates: List[str], unions: Dict[str, List[str]], market_size: int,
                  strategies: List[str], configs: List[str],
                  sector_map: Dict[str, str], smoke: bool):
    out.parent.mkdir(parents=True, exist_ok=True)

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

    # 전략별 baseline 대비 델타.
    delta_lines = []
    for strat in df["strategy"].unique():
        sub = df[df["strategy"] == strat].set_index("config")
        if "baseline" not in sub.index:
            continue
        b = sub.loc["baseline"]
        delta_lines.append(f"\n**{strat}** (baseline: sharpe {b['sharpe']:+.2f}, "
                           f"pnl {b['pnl']:+.2%}, maxdd {b['maxdd']:.2%}, "
                           f"trades {int(b['n_trades'])})")
        for config in configs:
            if config == "baseline" or config not in sub.index:
                continue
            c = sub.loc[config]
            delta_lines.append(
                f"  - `{config}`: Δsharpe {c['sharpe'] - b['sharpe']:+.2f}, "
                f"Δpnl {c['pnl'] - b['pnl']:+.2%}, "
                f"Δmaxdd {c['maxdd'] - b['maxdd']:+.2%}, "
                f"trades {int(b['n_trades'])}→{int(c['n_trades'])}"
            )

    # 가설 검증 — A(floor300, PIT-clean): sharpe↑ AND maxdd↓ 면 YES. B(ex_sector, 근사):
    # 방향만(sharpe 부호). baseline 대비 델타로 판정.
    verdict_a, verdict_b = [], []
    for strat in df["strategy"].unique():
        sub = df[df["strategy"] == strat].set_index("config")
        if "baseline" not in sub.index:
            continue
        b = sub.loc["baseline"]
        if "floor300" in sub.index:
            f = sub.loc["floor300"]
            ds, dd = f["sharpe"] - b["sharpe"], f["maxdd"] - b["maxdd"]
            yes = (ds > 0) and (dd < 0)
            verdict_a.append(
                f"- **{strat}**: {'YES' if yes else 'NO'} — "
                f"sharpe {b['sharpe']:+.2f}→{f['sharpe']:+.2f} ({ds:+.2f}), "
                f"maxdd {b['maxdd']:.1%}→{f['maxdd']:.1%} ({dd:+.1%}), "
                f"pnl {b['pnl']:+.0%}→{f['pnl']:+.0%}"
            )
        if "ex_sector" in sub.index:
            e = sub.loc["ex_sector"]
            ds, dd = e["sharpe"] - b["sharpe"], e["maxdd"] - b["maxdd"]
            direction = "양(+)" if ds > 0.03 else ("음(-)" if ds < -0.03 else "중립")
            verdict_b.append(
                f"- **{strat}**: {direction} — "
                f"sharpe {b['sharpe']:+.2f}→{e['sharpe']:+.2f} ({ds:+.2f}), "
                f"maxdd {b['maxdd']:.1%}→{e['maxdd']:.1%} ({dd:+.1%}), "
                f"pnl {b['pnl']:+.0%}→{e['pnl']:+.0%}"
            )

    ex_hits = sum(1 for v in sector_map.values() if v in EX_SECTOR_NAMES)
    unknown = sum(1 for v in sector_map.values() if v == "?")
    sector_note = (
        f"섹터맵 코드 {len(sector_map)}개 중 제외대상(반도체와반도체장비·전자장비와기기) "
        f"{ex_hits}개, 미상('?') {unknown}개."
        if sector_map else "섹터 구성 미사용(ex_sector 계열 미실행)."
    )

    content = f"""# Step 3c — 시총 플로어·섹터 제외 필터 OOS 백테스트 결과

> 측정 전용(라이브 코드/config 무수정). 영구룰: 숫자 검증·추정 금지 — 아래 수치는
> `scripts/step3c_size_sector_filter.py` 실행 산출(워킹트리). step3·라이브 무수정,
> 신규 스크립트 1개로 한정.

## 목적
2026-06-27 in-sample 반사실 검증(116 페이퍼 SELL: 두 필터 적용 시 실현
−1.12M→+1.17M, 4전략 전부 손실→흑자)을 **다년 PIT 백테스트로 OOS 검증**한다.
- **가설A(시총 플로어)**: 초소형주(시총<300억) 진입 컷 → 갭 손절관통 감소.
- **가설B(섹터 제외)**: 반도체와반도체장비·전자장비와기기 제외.

## 측정 설정
- 기간: **{start} ~ {end}**{" (smoke)" if smoke else ""}
- scan 빈도(PIT): **{scan_freq}** — scan_date {len(scan_dates)}개 ({scan_dates[0]} .. {scan_dates[-1]})
- 하니스: step3_pit_rebaseline `_run_pit`(build_signals → pit_gate_signal_cache →
  run_portfolio) 재사용. sim·진입룰·청산·비용·사이징·K = multiverse4 SPECS 정본 그대로.
- **유일 차이 = PIT resolver**: baseline 은 step3 U2_PIT(make_scan_eligible_resolver),
  나머지는 통과집합에 시총 플로어/섹터 제외를 곱한 변형(make_filtered_resolver).
- 데이터=전략별 union(warmup 확보), 진입신호만 resolver 게이팅.

## 구성
- `baseline` = step3 U2_PIT (필터 없음).
- `floor300` = scan_date snapshot market_cap ≥ **3e10(300억)**. **PIT-clean**.
- `floor500` = market_cap ≥ **5e10(500억)**. 민감도용. PIT-clean.
- `ex_sector` = 반도체와반도체장비·전자장비와기기 제외. **근사**(아래 한계).
- `floor300_ex_sector` = 둘 다.

## 비교표 (전략 × 구성)

{_md_table(df)}

- `uni_size` = union 코드 수, `loaded` = 일봉 30행+ 확보돼 실제 로딩된 종목 수
- `n_signals` = PIT 게이팅 후 진입신호 수, `n_trades` = 청산(sell) 수

## 전략별 baseline 대비 델타
{chr(10).join(delta_lines)}

## 핵심 판정

### 가설A (시총 플로어 floor300, **PIT-clean**) — sharpe↑ AND maxdd↓ 면 YES
{chr(10).join(verdict_a)}

### 가설B (섹터 제외 ex_sector, **근사** — 방향만)
{chr(10).join(verdict_b)}

## 유니버스/섹터 구성
- 전체시장 snapshot({end}) = {market_size}종목.
{chr(10).join(f"- **{s}**: union {len(unions[s])} (전체의 {(len(unions[s])/market_size*100 if market_size else 0):.0f}%)" for s in strategies)}
- {sector_note}

## 한계 (반드시 함께 해석)
- **섹터 근사(가설B)**: 섹터맵은 네이버 종목페이지의 *현재* 업종명을 스크랩한 정적값이다.
  이를 과거 진입봉에 소급적용 = **look-ahead/생존편향**(과거 다른 업종이었거나 상장폐지로
  현재 페이지가 없는 종목은 '?'). 따라서 `ex_sector` 계열은 *방향성 참고*일 뿐 PIT-clean 이
  아니다. (시총 플로어 `floor*` 는 scan_date snapshot market_cap 사용 → PIT-clean.)
- **6월 특수성**: in-sample 신호는 2026-06 반도체 약세 국면 특수성을 반영했을 수 있다.
  OOS(5.5년)는 다양한 국면을 포함하므로 in-sample 흑자전환이 OOS 에서 재현되지 않을 수
  있다(이것이 본 검증의 핵심).
- **PIT 월별 근사**: 라이브 스크리너는 일별이나 본 측정은 {scan_freq} scan_date 멤버십으로
  근사. 월 중 신규 진입/이탈 종목의 멤버십 전환 시점에 ±수주 오차 가능.
- **union 데이터 로딩**: 풀기간 union 은 base_filter 가 느슨한 전략에서 전체시장에 근접.
  U2_PIT 게이팅이 이를 우회하나, 데이터 적재 자체는 union 전체(무거움).
"""
    out.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
