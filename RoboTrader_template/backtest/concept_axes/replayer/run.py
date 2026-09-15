"""매수후보 원장 재현기 CLI — 설계서 §9 S2~S6.

    python backtest/concept_axes/replayer/run.py --strategy ma20 \
        --start 2024-03-13 --end 2026-09-11 --out scratchpad/replayer

    python backtest/concept_axes/replayer/run.py --strategy both \
        --start 2026-06-05 --end 2026-09-11 --gate --out scratchpad/replayer_gate

🔴 **출력은 «후보 원장»뿐이다** — 전방 수익률·꼬리 값·PnL·체결은 만들지 않는다.
🔴 **DB 는 SELECT 전용** · 라이브 코드는 import 만 한다(0줄 변경).
🔴 **V5-a** — 평일 09:00~09:20 KST 에는 실행을 거부한다.
🔴 **V5-b** — 실행 직전·직후 지문이 다르면 산출물을 무효로 표시한다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import psycopg2

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]                       # …/RoboTrader_template
REPO = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import warnings                                                   # noqa: E402
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

from backtest.concept_axes.replayer import flags as flg           # noqa: E402
from backtest.concept_axes.replayer import gate as gt             # noqa: E402
from backtest.concept_axes.replayer import ledger as ldg          # noqa: E402
from backtest.concept_axes.replayer import loader as ldr          # noqa: E402
from backtest.concept_axes.replayer import scan as scn            # noqa: E402

HIST0 = "2021-01-01"                  # 워밍업 (설계서 §1-3)
W0, W1 = "2024-03-13", "2026-05-31"   # 판정 창 537 거래일
GEN_END = "2026-09-11"                # 원장 생성 끝 (그 뒤는 인쇄 전용)

STRATEGIES: Dict[str, Dict[str, Any]] = {
    "ma20": {
        "name": "book_pullback_ma20",
        "module": "strategies.book_pullback_ma20.screener",
        "cls": "BookPullbackMa20ScreenerAdapter",
    },
    "daytrading": {
        "name": "daytrading_3methods_breakout",
        "module": "strategies.daytrading_3methods_breakout.screener",
        "cls": "Daytrading3MethodsBreakoutScreenerAdapter",
    },
}


def require_parquet(args, written: Dict[str, str]) -> None:
    """리뷰 L-5 — parquet 실패를 «조용히» 넘기지 않는다.

    기본은 경고 + 리포트 머리 표 인쇄, `--require-parquet` 면 즉시 중단.
    """
    pq = str(written.get("parquet", ""))
    if not pq.startswith("("):
        return
    msg = "parquet 미생성 — {}".format(pq)
    if getattr(args, "require_parquet", False):
        raise RuntimeError(msg + " (`--require-parquet`)")
    log("      🟡 " + msg + " · csv 는 생성됨")


def log(msg: str = "") -> None:
    print(msg, file=sys.stderr, flush=True)


def make_adapter(key: str):
    """🟢 라이브 어댑터를 «생성만» 한다 — `scan()` 은 부르지 않으므로 커넥션이 안 열린다."""
    spec = STRATEGIES[key]
    mod = __import__(spec["module"], fromlist=[spec["cls"]])
    return getattr(mod, spec["cls"])()


def params_hash(p: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(p, sort_keys=True,
                                     default=str).encode("utf-8")).hexdigest()[:12]


# ────────────────────────────────────────────────────────────────────────────
# 라이브 스냅샷 (게이트 대조용) — SELECT 전용
# ────────────────────────────────────────────────────────────────────────────
def load_live_snapshots(conn, strategy: str, start: str, end: str) -> pd.DataFrame:
    # 리뷰 L-6 — 파라미터 바인딩.
    df = pd.read_sql("""
        SELECT scan_date, stock_code, rank_in_snapshot, score, params_hash,
               params_json, created_at
        FROM screener_snapshots
        WHERE strategy = %s AND scan_date BETWEEN %s AND %s
        ORDER BY scan_date, rank_in_snapshot
    """, conn, params=(strategy, start, end))
    df["scan_date"] = pd.to_datetime(df["scan_date"])
    return df


def params_segments(live: pd.DataFrame) -> List[Dict[str, Any]]:
    """`params_hash` 별 구간 — daytrading 은 **창 «안»에서 파라미터가 바뀌었다**(§4-2)."""
    out = []
    for h, g in live.groupby("params_hash"):
        pj = g["params_json"].iloc[0]
        if isinstance(pj, str):
            pj = json.loads(pj)
        out.append({
            "params_hash": str(h),
            "params": pj or {},
            "dates": sorted(g["scan_date"].unique().tolist()),
            "n_rows": int(len(g)),
        })
    return sorted(out, key=lambda s: s["dates"][0])


# ────────────────────────────────────────────────────────────────────────────
# 재현 1회 (한 전략 · 한 파라미터 구간)
# ────────────────────────────────────────────────────────────────────────────
def replay(px: pd.DataFrame, bar_flags: pd.DataFrame, key: str, *,
           scan_dates: List[pd.Timestamp], params: Optional[Dict[str, Any]],
           excluded: set, names: Dict[str, str], markets: Dict[str, str],
           corp_events: Dict[Any, str], meta: Dict[str, str],
           max_candidates: int):
    adapter = make_adapter(key)
    merged = {**adapter.default_params(), **(params or {})}
    uni = ldr.build_universe(px)
    elig, uni_info = scn.eligible_for_dates(uni, adapter, scan_dates, exclude=excluded)
    t0 = time.perf_counter()
    matched, diag, impossible = scn.scan_strategy(
        px, elig, adapter, merged, adapter.lookback_days,
        scan_dates=scan_dates, max_candidates=max_candidates)
    secs = time.perf_counter() - t0
    run_meta = dict(meta, replayer_params_hash=params_hash(merged))
    led, ties = ldg.build_ledger(
        matched, px, bar_flags, strategy=STRATEGIES[key]["name"],
        uni_info=uni_info, names=names, markets=markets, corp_events=corp_events,
        max_candidates=max_candidates)
    diag_df = ldg.build_diag(diag, uni_info, ties, led)
    # 리뷰 L-1 — 로더가 «임의로» 건드린 행 수를 진단 CSV 에도 올린다(라이브에 없는 처리).
    for _k, _v in (px.attrs.get("normalize_counts") or {}).items():
        diag_df[_k] = _v
    by_code = {c: g for c, g in px.groupby("stock_code", sort=False)}

    def vol_lookup(code, scan_date):
        g = by_code.get(code)
        if g is None:
            return None
        v = g.loc[g["date"] <= pd.Timestamp(scan_date), "volume"].to_numpy(dtype=float)
        return v if len(v) else None

    return {"ledger": led, "diag": diag_df, "uni_info": uni_info, "ties": ties,
            "impossible": impossible, "params": merged, "secs": secs,
            "n_matched": len(matched), "vol_lookup": vol_lookup, "meta": run_meta}


# ────────────────────────────────────────────────────────────────────────────
# 게이트
# ────────────────────────────────────────────────────────────────────────────
def build_day_pairs(live: pd.DataFrame, led: pd.DataFrame) -> List[gt.DayPair]:
    days: List[gt.DayPair] = []
    lg = {d: g for d, g in live.groupby("scan_date")}
    rg = {d: g for d, g in led.groupby("scan_date")} if len(led) else {}
    for d in sorted(set(lg) | set(rg)):
        L = lg.get(d)
        R = rg.get(d)
        days.append(gt.DayPair(
            scan_date=pd.Timestamp(d).strftime("%Y-%m-%d"),
            live=(list(L["stock_code"].astype(str)) if L is not None else []),
            replay=(list(R["stock_code"].astype(str)) if R is not None else []),
            live_scores=(dict(zip(L["stock_code"].astype(str),
                                  L["score"].astype(float))) if L is not None else {}),
            replay_scores=(dict(zip(R["stock_code"].astype(str),
                                    R["score"].astype(float))) if R is not None else {}),
        ))
    return days


def _naive(ts):
    """tz 유무에 관계없이 naive `Timestamp` 로."""
    if ts is None or ts != ts:
        return None
    t = pd.Timestamp(ts)
    return t.tz_localize(None) if t.tzinfo is not None else t


def created_at_by_date(live: pd.DataFrame) -> Dict[Any, Any]:
    out = {}
    for d, g in live.groupby("scan_date"):
        out[pd.Timestamp(d)] = _naive(pd.to_datetime(g["created_at"]).max())
    return out


def c1_signature_table(live: pd.DataFrame, cal: List[pd.Timestamp]) -> pd.DataFrame:
    """§4-5 C1 서명 ② — **구(달력 3일) 대 신(다음 거래일 + 12h)** 을 둘 다 인쇄하기 위한 표.

    🔴 구판은 사실상 **금요일 탐지기**였다 — 그걸 여기서 숫자로 보인다.
    """
    rows = []
    for d, ca in sorted(created_at_by_date(live).items()):
        old_sig = bool(ca is not None and ca > d + pd.Timedelta(days=3))
        rows.append({
            "scan_date": d,
            "weekday": d.day_name(),
            "created_at": ca,
            "next_trading_day": gt.next_trading_day(cal, d),
            "old_calendar_3d": old_sig,
            "new_trading_day_12h": gt.created_late(ca, d, cal),
        })
    return pd.DataFrame(rows, columns=["scan_date", "weekday", "created_at",
                                       "next_trading_day", "old_calendar_3d",
                                       "new_trading_day_12h"])


def classify_days(days: List[gt.DayPair], live: pd.DataFrame,
                  impossible: Dict[Any, set],
                  uni_info: Dict[Any, Dict[str, Any]],
                  boundary_dates: set,
                  excluded: Optional[set] = None,
                  cal: Optional[List[pd.Timestamp]] = None) -> pd.DataFrame:
    """불일치를 **양방향**으로 펼치고 §4-5 라벨을 붙인다."""
    created = created_at_by_date(live)
    excl = excluded or set()
    rows = []
    for dp in days:
        d = pd.Timestamp(dp.scan_date)
        sL, sR = set(dp.live), set(dp.replay)
        only_live, only_replay = sL - sR, sR - sL
        swept = bool(uni_info.get(d, {}).get("universe_fallback", False)) or (
            sL and sR and len(only_live) >= 0.5 * len(sL)
            and len(only_replay) >= 0.5 * len(sR))
        ca = created.get(d)
        # 🔴 H-2 — 달력 3일이 아니라 **다음 거래일 + 12h**(`gate.created_late`).
        created_late = gt.created_late(ca, d, cal or [])
        # C7 «배제 승격» — 같은 날 §1-2-b 배제 종목의 live_only 수와 replay_only 수가 같으면
        # 재현 상위 20 은 «그만큼 밀려 올라온» 상황이다 — C6(미상)과 같은 칸에 넣지 않는다.
        n_excl_live_only = sum(1 for c in only_live if c in excl)
        promoted_day = bool(n_excl_live_only and n_excl_live_only == len(only_replay))
        imp = impossible.get(d, set())
        for code in sorted(only_live) + sorted(only_replay):
            side = "live_only" if code in only_live else "replay_only"
            lr = (dp.live.index(code) + 1) if code in sL else None
            rr = (dp.replay.index(code) + 1) if code in sR else None
            lab = gt.classify_mismatch(
                code=code, side=side, live_rank=lr, replay_rank=rr,
                score_match=True, created_late=created_late, hash_changed=False,
                impossible_in_window=(code in imp), at_params_boundary=(d in boundary_dates),
                set_swept=swept,
                exclusion_promoted=(promoted_day and side == "replay_only"))
            rows.append({"scan_date": dp.scan_date, "stock_code": code, "side": side,
                         "live_rank": lr, "replay_rank": rr, "label": lab,
                         # 🔴 §1-2-b 배제는 «사전등록된 의도적 차이»다 — C6(미상)이 아니다.
                         "excl_1_2_b": bool(code in excl)})
    return pd.DataFrame(rows, columns=["scan_date", "stock_code", "side",
                                       "live_rank", "replay_rank", "label", "excl_1_2_b"])


def fmt_metrics(title: str, m: Dict[str, Any]) -> List[str]:
    def f(x):
        return "n/a" if (x is None or x != x) else "{:.4f}".format(x)
    return [
        "| {} | {} | {} | {} | {} | {} | {} |".format(
            title, m["n_days"], f(m["M1"]), f(m["M2"]), f(m["M3"]), f(m["M4"]),
            gt.verdict(m)),
    ]


# ────────────────────────────────────────────────────────────────────────────
# main
# ────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="매수후보 원장 재현기 (ma20 · daytrading)")
    ap.add_argument("--strategy", choices=["ma20", "daytrading", "both"], required=True)
    ap.add_argument("--start", default=W0)
    ap.add_argument("--end", default=GEN_END)
    ap.add_argument("--hist-start", default=HIST0,
                    help="워밍업 시작(기본 2021-01-01 · 스모크에서만 줄인다)")
    ap.add_argument("--out", default=str(REPO / "scratchpad" / "replayer"))
    ap.add_argument("--gate", action="store_true",
                    help="라이브 `screener_snapshots` 와 일치율 게이트(§4)")
    ap.add_argument("--max-candidates", type=int, default=scn.MAX_CANDIDATES_PER_STRATEGY)
    ap.add_argument("--require-parquet", action="store_true",
                    help="parquet 생성 실패를 **오류로** 취급한다(리뷰 L-5 · 기본은 경고·인쇄)")
    args = ap.parse_args(argv)

    # V5-a — 실행 시간창
    gt.require_time_window()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = dt.datetime.now()
    run_id = started.strftime("%Y%m%dT%H%M%S")
    sha = ldg.git_sha(ROOT)

    conn = psycopg2.connect(**ldr.dsn())
    conn.set_session(readonly=True)          # 🔴 SELECT 전용
    try:
        log("[1/6] 지문(실행 «직전») …")
        t0 = time.perf_counter()
        fp1 = ldr.db_fingerprint(conn, args.hist_start, args.end)
        log("      sha256={} · {:,}행 / {:,}종목 · {:.0f}s".format(
            fp1["sha256"][:16], fp1["n_rows"], fp1["n_stocks"], time.perf_counter() - t0))

        log("[2/6] 일봉 벌크 로드 {}~{} …".format(args.hist_start, args.end))
        t0 = time.perf_counter()
        px = ldr.load_prices(conn, args.hist_start, args.end)
        log("      {:,}행 / {:,}종목 · {:.0f}s".format(
            len(px), px["stock_code"].nunique(), time.perf_counter() - t0))

        cal = ldr.load_trading_calendar(conn, args.start, args.end)
        names = ldr.load_stock_names(conn)
        markets = ldr.load_market_labels(conn)
        corp = ldr.load_corp_events(conn)
        log("      거래일 {}일 (달력 SSOT = stock_code='KOSPI') · 종목명 {:,}".format(
            len(cal), len(names)))

        log("[3/6] §1-2-b 배제 분류(원장 생성 «전») …")
        codes = sorted(px["stock_code"].astype(str).unique())
        cls = ldr.classify_exclusions(codes, names)
        excluded = {c for c, v in cls.items() if v["excluded"]}
        excl_counts = ldr.exclusion_counts(cls)
        log("      " + " · ".join("{}={}".format(k, v) for k, v in excl_counts.items()))

        log("[4/6] 봉 플래그(§8-10) …")
        t0 = time.perf_counter()
        bar_flags = flg.compute_bar_flags(px)
        year_agg = flg.flag_counts_by_year(px, bar_flags)
        pref_month = flg.preferred_month_counts(px)
        log("      cliff={:,} · padding={:,} · locked={:,} · {:.0f}s".format(
            int(bar_flags["flag_cliff"].sum()), int(bar_flags["flag_padding"].sum()),
            int(bar_flags["flag_locked_limit"].sum()), time.perf_counter() - t0))

        meta = {"run_id": run_id, "git_sha": sha, "db_fingerprint_hash": fp1["sha256"]}
        keys = ["ma20", "daytrading"] if args.strategy == "both" else [args.strategy]
        report: List[str] = []
        results: Dict[str, Any] = {}

        log("[5/6] 재현 …")
        for key in keys:
            sname = STRATEGIES[key]["name"]
            if args.gate:
                live = load_live_snapshots(conn, sname, args.start, args.end)
                segs = params_segments(live)
                log("   {} — 라이브 {:,}행 / {}일 / params_hash {}".format(
                    sname, len(live), live["scan_date"].nunique(), len(segs)))
                seg_out = []
                for s in segs:
                    log("     · {} ({}~{}, {}일) params={}".format(
                        s["params_hash"][:8],
                        pd.Timestamp(s["dates"][0]).date(),
                        pd.Timestamp(s["dates"][-1]).date(), len(s["dates"]), s["params"]))
                    r = replay(px, bar_flags, key, scan_dates=s["dates"],
                               params=s["params"], excluded=excluded, names=names,
                               markets=markets, corp_events=corp, meta=meta,
                               max_candidates=int(s["params"].get(
                                   "max_candidates", args.max_candidates)))
                    # 리뷰 M-3 — 보조 지표는 「랭킹 «전» 배제 없이 재현한 상위 20」 으로 낸다.
                    #    라이브 집합에서 배제를 «사후» 빼는 것은 밀려 올라온 슬롯을 되돌리지 못한다.
                    r["ledger_noexcl"] = replay(
                        px, bar_flags, key, scan_dates=s["dates"],
                        params=s["params"], excluded=set(), names=names,
                        markets=markets, corp_events=corp, meta=meta,
                        max_candidates=int(s["params"].get(
                            "max_candidates", args.max_candidates)))["ledger"]
                    r["seg"] = s
                    r["live"] = live[live["scan_date"].isin(s["dates"])]
                    w = ldg.write_outputs(
                        r["ledger"], r["diag"],
                        out_dir / key / s["params_hash"][:8], meta=r["meta"])
                    r["written"] = w
                    require_parquet(args, w)
                    log("       " + " · ".join("{}={}".format(a_, b_)
                                               for a_, b_ in w.items()))
                    seg_out.append(r)
                    log("       재현 {:,}건 발화 · {:.0f}s".format(r["n_matched"], r["secs"]))
                results[key] = seg_out
            else:
                r = replay(px, bar_flags, key, scan_dates=cal, params=None,
                           excluded=excluded, names=names, markets=markets,
                           corp_events=corp, meta=meta,
                           max_candidates=args.max_candidates)
                log("   {} — 후보 {:,}행 / {}일 · {:.0f}s".format(
                    sname, len(r["ledger"]), len(cal), r["secs"]))
                w = ldg.write_outputs(r["ledger"], r["diag"], out_dir / key,
                                      meta=r["meta"])
                r["written"] = w
                require_parquet(args, w)
                log("      " + " · ".join("{}={}".format(k, v) for k, v in w.items()))
                results[key] = [r]

        log("[6/6] 지문(실행 «직후») …")
        fp2 = ldr.db_fingerprint(conn, args.hist_start, args.end)
        fp_ok = fp1["sha256"] == fp2["sha256"]
        log("      V5-b {}".format("일치 ✅" if fp_ok else "🔴 불일치 — 산출물 폐기·재실행"))
    finally:
        conn.close()

    # ── 리포트 ──────────────────────────────────────────────────────────────
    ended = dt.datetime.now()
    rep = _report(args, started, ended, sha, run_id, fp1, fp2, fp_ok, px, cal,
                  excl_counts, cls, bar_flags, year_agg, pref_month, results, keys,
                  excluded)
    path = out_dir / ("GATE_REPORT_{}.md".format(started.strftime("%Y%m%d")) if args.gate
                      else "REPLAY_REPORT_{}.md".format(started.strftime("%Y%m%d")))
    path.write_text("\n".join(rep), encoding="utf-8")
    log("리포트 → {}".format(path))
    print(path)
    return 0


def _report(args, started, ended, sha, run_id, fp1, fp2, fp_ok, px, cal,
            excl_counts, cls, bar_flags, year_agg, pref_month, results, keys,
            excluded=None) -> List[str]:
    r: List[str] = []
    a = r.append
    a("# 재현기 {} 리포트 — {}".format("일치율 게이트" if args.gate else "원장 생성",
                                      started.strftime("%Y-%m-%d %H:%M")))
    a("")
    a("> {}".format(gt.NOT_BUYABLE_CAVEAT))
    a("> 🔴 이 재현기의 출력은 «후보 원장»뿐이다 — **전방 수익률·꼬리 값·PnL 은 없다**"
      "(`BookBacktester` 를 import 하지 않는다).")
    a("> {}".format(gt.V6_HEADER))
    a("> {}".format(gt.C1_CAVEAT))
    a("")
    a("## 0. 실행 지문")
    a("")
    a("| 항목 | 값 |")
    a("|---|---|")
    a("| run_id | `{}` |".format(run_id))
    a("| git_sha | `{}` |".format(sha))
    a("| 시작 / 종료 (로컬) | {} / {} |".format(started.strftime("%Y-%m-%d %H:%M:%S"),
                                                ended.strftime("%Y-%m-%d %H:%M:%S")))
    a("| V5-a 실행 시간창 | {} (평일 09:00~09:20 KST 회피) |".format(
        "OK" if gt.time_window_ok(started) else "🔴 위반"))
    a("| 지문 창 | `{}` |".format(fp1["window"]))
    a("| 지문 컬럼 10 | `{}` |".format("`, `".join(fp1["cols"])))
    a("| **V5-b 지문 «직전»** | `{}` (md5 `{}`) |".format(fp1["sha256"], fp1["md5"]))
    a("| **V5-b 지문 «직후»** | `{}` (md5 `{}`) |".format(fp2["sha256"], fp2["md5"]))
    a("| **V5-b 판정** | {} |".format("✅ 일치 — 산출물 유효" if fp_ok
                                      else "🔴 불일치 — **산출물 폐기·재실행**"))
    a("| 지문 대상 | {:,}행 / {:,}종목 |".format(fp1["n_rows"], fp1["n_stocks"]))
    a("| 로드 일봉 | {:,}행 / {:,}종목 (`{}`~`{}`) |".format(
        len(px), px["stock_code"].nunique(), args.hist_start, args.end))
    pq_bad = []
    for _k in keys:
        for _seg in results[_k]:
            _w = _seg.get("written") or {}
            if str(_w.get("parquet", "")).startswith("("):
                pq_bad.append("{}: {}".format(_k, _w.get("parquet")))
    a("| parquet 산출(리뷰 L-5) | {} |".format(
        "✅ 전부 생성" if not pq_bad
        else "🔴 **미생성** — " + " · ".join(pq_bad)
        + " (원장은 csv 로만 남는다 · `--require-parquet` 면 중단)"))
    nc = px.attrs.get("normalize_counts") or {}
    a("| 로더 위생 처리(리뷰 L-1 · **라이브에 없는 처리** · 설계서 근거 없음) | "
      "`date` 손상 제거 {:,}행 · `n_dropped_close` {:,}행 · `n_patched_ohl` {:,}행 |".format(
          nc.get("n_dropped_bad_date", 0), nc.get("n_dropped_close", 0),
          nc.get("n_patched_ohl", 0)))
    a("| 거래일 달력 | **{}일** (SSOT = `stock_code='KOSPI'` 행 · `{}`~`{}`) |".format(
        len(cal), args.start, args.end))
    a("")
    a("## 1. §1-2-b 배제 (원장 생성 «전»)")
    a("")
    a("| 축 | 종목 수 |")
    a("|---|---:|")
    for k, v in excl_counts.items():
        a("| `{}` | {:,} |".format(k, v))
    a("| **배제 합계(고유)** | {:,} |".format(sum(1 for v in cls.values() if v["excluded"])))
    a("")
    a("🔴 **이름 미상은 배제하지 않는다** — `flag_name_unknown` 으로 원장에 남긴다. "
      "「이름이 없어서 못 걸렀다」와 「걸러 봤더니 아니었다」를 같은 칸에 넣지 않는다.")
    a("🔴 배제 대상은 **6번째 자리가 `[5-9]` 또는 `[K-M]`** 인 것뿐이다 — "
      "`0001A0`·`0007C0`·`0009K0` 같은 **신형 코드 보통주는 배제하지 않는다**.")
    a("")
    a("## 2. V6-5 측정기 드리프트 · V6-4 모집단 불연속")
    a("")
    a("```")
    a(year_agg.to_string())
    a("```")
    d = gt.v6_5_drift(year_agg)
    a("")
    a("- 연도 간 「거래일당 패딩」 최대비 = **{:.2f}×** ⇒ {}".format(
        d["ratio_max"],
        "🔴 **연도 pooled 판정 금지 · 판정문 병기 의무**" if d["pooled_forbidden"]
        else "2배 이하"))
    a("- 🔴 2021~2023 구간과의 pooled 검정은 **어떤 경우에도 금지**(공정 경계).")
    a("")
    a("우선주 모집단(월별 · V6-4 · 거친 식 `right(code,1)<>'0'` 과 정본 식의 차이 포함):")
    a("")
    a("```")
    a(pref_month[pref_month["n_pref_canonical"] > 0].to_string())
    a("```")
    a("")

    if not args.gate:
        a("## 3. 원장 생성 요약")
        a("")
        a("| 전략 | 후보 행 | 거래일 | 소요(초) |")
        a("|---|---:|---:|---:|")
        for k in keys:
            rr = results[k][0]
            a("| `{}` | {:,} | {} | {:.0f} |".format(
                STRATEGIES[k]["name"], len(rr["ledger"]),
                rr["ledger"]["scan_date"].nunique() if len(rr["ledger"]) else 0,
                rr["secs"]))
        a("")
        for k in keys:
            rr = results[k][0]
            a("### `{}` 진단 (V6-3 연속성 ±50% 이탈일)".format(STRATEGIES[k]["name"]))
            a("")
            dev = gt.v6_3_continuity(rr["diag"])
            a("- 이탈일 **{}건**".format(len(dev)))
            if len(dev):
                a("")
                a("```")
                a(dev.head(60).to_string(index=False))
                a("```")
            a("")
        return r

    # ── 게이트 ──────────────────────────────────────────────────────────────
    a("## 3. 일치율 게이트 (§4)")
    a("")
    a("🔒 **문턱은 실행 «전» 동결** — `{}`. 🔴 **결과를 보고 내리지 않는다.**".format(
        json.dumps(gt.THRESHOLDS, ensure_ascii=False)))
    a("")
    for k in keys:
        sname = STRATEGIES[k]["name"]
        a("### `{}`".format(sname))
        a("")
        for seg in results[k]:
            s = seg["seg"]
            days = build_day_pairs(seg["live"], seg["ledger"])
            a("#### params_hash `{}` ({}~{} · {}일)".format(
                s["params_hash"][:12], pd.Timestamp(s["dates"][0]).date(),
                pd.Timestamp(s["dates"][-1]).date(), len(s["dates"])))
            a("")
            a("- 라이브 params_json = `{}`".format(json.dumps(s["params"], ensure_ascii=False)))
            a("- 재현 실효 params = `{}`".format(json.dumps(seg["params"], ensure_ascii=False,
                                                            default=str)))
            a("")
            a("| 구간 | 거래일 | M1 | M2 | M3 | M4 | 판정 |")
            a("|---|---:|---:|---:|---:|---:|---|")
            total = gt.compute_metrics(days)
            r.extend(fmt_metrics("**전체**", total))
            for label, sub in gt.split_windows(days).items():
                if sub:
                    r.extend(fmt_metrics(label, gt.compute_metrics(sub)))
            a("")
            # 🔴 «보조» 인쇄 — 판정은 위 표(동결 정의)로 한다. 이 줄로 문턱을 우회하지 않는다.
            if excluded and "ledger_noexcl" in seg:
                aux = gt.compute_metrics(build_day_pairs(seg["live"],
                                                         seg["ledger_noexcl"]))
                a("> **보조(판정 아님)** — 「랭킹 «전» §1-2-b 배제 없이 "
                  "다시 재현한 상위 20」 vs 라이브: M1 = {:.4f} · M3 = {:.4f} "
                  "(거래일 {}일). 🔴 **판정은 위 표의 값이다** — 이 줄은 "
                  "«사전등록된 의도적 차이»의 크기를 재는 원인 귀속일 뿐 문턱 우회가 아니다. "
                  "🔑 예전처럼 «라이브 집합에서 배제 종목을 사후에 빼는» 방식은 "
                  "배제로 비운 슬롯에 20위 밖이 밀려 올라온 효과를 되돌리지 못해 "
                  "지표를 «한쪽으로» 움직였다(리뷰 M-3).".format(
                      aux["M1"], aux["M3"], aux["n_days"]))
                a("")
            a("- 라이브 {:,}종목-일 · 재현 {:,}종목-일 · 교집합 {:,} · 합집합 {:,}".format(
                total["n_live"], total["n_replay"], total["n_inter"], total["n_union"]))
            a("- M2 분모 제외일(교집합 원소 < 2) = **{}일**".format(total["M2_skipped_days"]))
            a("- M4 대조 가능 행 = **{:,}**".format(total["M4_n"]))
            n_tie = sum(seg["ties"].values())
            a("- 20위 경계 동점 = **{}건** / 동점 발생 날짜 {}일".format(
                n_tie, sum(1 for v in seg["ties"].values() if v)))
            nfb = sum(1 for v in seg["uni_info"].values() if v.get("universe_fallback"))
            a("- 유니버스 일자 폴백 발생일 = **{}일**".format(nfb))
            a("")
            # C4 — `params_hash` 구간 경계일(§4-5). 구간이 하나면 경계가 없다.
            bset = set()
            if len(results[k]) > 1:
                for s2 in results[k]:
                    bset.add(pd.Timestamp(s2["seg"]["dates"][0]))
                    bset.add(pd.Timestamp(s2["seg"]["dates"][-1]))
            cdf = classify_days(days, seg["live"], seg["impossible"],
                                seg["uni_info"], bset, excluded, cal=cal)
            sig = c1_signature_table(seg["live"], cal)
            n_old = int(sig["old_calendar_3d"].sum())
            n_new = int(sig["new_trading_day_12h"].sum())
            fri_old = int((sig["old_calendar_3d"] & (sig["weekday"] == "Friday")).sum())
            fri_new = int((sig["new_trading_day_12h"] & (sig["weekday"] == "Friday")).sum())
            a("**§4-5 C1 서명 ② — 구/신 대조**(리뷰 H-2)")
            a("")
            a("| 서명 | 발화일 | 그중 금요일 |")
            a("|---|---:|---:|")
            a("| 구: `created_at > scan_date + 3일(달력)` | {} | **{}** |".format(n_old, fri_old))
            a("| 신: `created_at > 다음 «거래일» + 12h` | {} | {} |".format(n_new, fri_new))
            a("")
            a("🔴 구 서명은 **금요일 탐지기**였다 — 발화 {}일 중 **{}일이 금요일**"
              "(금요일은 다음 거래일이 사흘 뒤라 일상적인 재수집도 «지연» 으로 읽힌다). "
              "이 리포트의 C1 라벨은 **신 서명**으로 붙였다.".format(n_old, fri_old))
            a("")
            if n_old or n_new:
                a("```")
                a(sig[sig["old_calendar_3d"] | sig["new_trading_day_12h"]]
                  .to_string(index=False))
                a("```")
                a("")
            a("**§4-5 불일치 원인 분류** (양방향 집합 차분 · 「몇 %」가 아니다)")
            a("")
            if len(cdf):
                a("전체:")
                a("")
                a("```")
                a(cdf.groupby(["label", "side"]).size().unstack(fill_value=0).to_string())
                a("```")
                a("")
                a("§1-2-b 배제분을 뺀 **잔여**(= 설명되지 않은 몫):")
                a("")
                a("```")
                res = cdf[~cdf["excl_1_2_b"]]
                a(res.groupby(["label", "side"]).size().unstack(fill_value=0).to_string()
                  if len(res) else "(없음)")
                a("```")
                a("")
                a("표본 (최대 10건):")
                a("")
                a("```")
                a(cdf.head(10).to_string(index=False))
                a("```")
                # §4-5 C6 — 「노출 구간 미상 건은 «전수 목록» 인쇄」(PASS 를 막지는 않는다)
                c6 = cdf[(cdf["label"] == "C6") & (~cdf["excl_1_2_b"])]
                a("")
                a("**C6 미상 잔여 전수** ({}건):".format(len(c6)))
                a("")
                a("```")
                a(c6.to_string(index=False) if len(c6) else "(없음)")
                a("```")
            else:
                a("- 불일치 **0건**")
            if len(cdf):
                n_ex = int(cdf["excl_1_2_b"].sum())
                a("")
                a("- 그중 **§1-2-b 배제 종목 = {}건**(우선주·리츠·외국주·ETF). "
                  "🔴 이건 «사전등록된 의도적 차이»이지 C6(미상)이 아니다 — "
                  "라이브 `STOCK_ONLY` 는 이들을 거르지 않는다.".format(n_ex))
            a("")
            # 🔑 이 역산은 `score = mean(volume[-20:])` 인 ma20 에서만 성립한다.
            #    daytrading 의 score 는 비(比)라 같은 역산이 안 된다.
            if k == "ma20":
                dg = gt.m4_lag_profile(days, seg["vol_lookup"])
                if dg.get("n"):
                    a("**M4 불일치의 lag 프로파일** — 「D−k 봉«만» 바뀌었다」고 "
                      "**가정**했을 때의 함의값 비 `implied / stored` ({:,}행 · 교집합 행 한정):".format(
                          dg["n"]))
                    a("")
                    a("| k (D−k) | n | 중앙값 | p05 | p95 | `< 1` 비율 |")
                    a("|---:|---:|---:|---:|---:|---:|")
                    for row in dg["lags"]:
                        a("| {} | {:,} | {:.6f} | {:.6f} | {:.6f} | {:.3f} |".format(
                            row["k"], row["n"], row["median"], row["p05"],
                            row["p95"], row["frac_below_1"]))
                    a("")
                    ww = dg.get("whole_window") or {}
                    a("🔴 **채널 미결** — 「마지막 봉만 바뀌었다」고 **가정**하면 "
                      "k=0 의 {:,}건이 전부 `< 1` 이다. 하지만 그건 «가정 위의 수치»이지 "
                      "측정된 채널이 아니다 — 「창 전체가 미세하게 커졌다」는 설명과 "
                      "**관측상 구분되지 않는다**(위 표가 k 에 걸쳐 평탄하면 한 봉 채널이 아니다). "
                      "같은 불일치를 「창 20봉이 균일하게 바뀌었다」로 읽으면 "
                      "라이브 전량 함의비 = **{} ~ {}**(중앙값 {})다.".format(
                          (dg["lags"][0]["n"] if dg["lags"] else 0),
                          ("{:+.2f}%".format(ww["min_pct"]) if ww else "n/a"),
                          ("{:+.2f}%".format(ww["max_pct"]) if ww else "n/a"),
                          ("{:+.2f}%".format(ww["median_pct"]) if ww else "n/a")))
                    a("")
                    a("🔴 이건 원인 **가설별 인쇄**이지 문턱 완화가 아니다 — M4 문턱 99% 는 그대로다. "
                      "그리고 이 표는 **교집합 행에서만** 재어진다(한쪽에만 있는 종목은 M4 대조 자체가 안 된다).")
            a("")
            # 리뷰 M-1 — §4-6 조건 ④ `M1_exposed_floor` 충족/미달을 «명시» 인쇄한다.
            exposed = [d for d in days if d.scan_date < gt.PROTECTED_FROM]
            if exposed:
                m_exp = gt.compute_metrics(exposed)["M1"]
                floor = gt.THRESHOLDS["M1_exposed_floor"]
                a("- 노출 구간 M1 = **{:.4f}** vs `M1_exposed_floor` {:.2f} ⇒ {}".format(
                    m_exp, floor,
                    "충족" if (m_exp == m_exp and m_exp >= floor)
                    else "🔴 **미달**"))
            else:
                a("- 노출 구간 거래일 0 ⇒ `M1_exposed_floor` 재지 불가")
            prot = [d for d in days if d.scan_date >= gt.PROTECTED_FROM]
            a("- 보호 구간 거래일 = **{}일** (조건부 통과 최소 {}일) ⇒ {}".format(
                len(prot), int(gt.THRESHOLDS["protected_min_days"]),
                "충족" if len(prot) >= gt.THRESHOLDS["protected_min_days"]
                else "🔴 **미달 — 조건부 통과 조항 사용 불가**"))
            a("")
    a("## 4. 판정 요약")
    a("")
    a("| 전략 | params_hash | 구간 | 거래일 | M1 | M3 | M4 | 판정 |")
    a("|---|---|---|---:|---:|---:|---:|---|")
    for k in keys:
        for seg in results[k]:
            s2 = seg["seg"]
            days = build_day_pairs(seg["live"], seg["ledger"])
            for label, sub in [("**전체**", days)] + list(gt.split_windows(days).items()):
                if not sub:
                    continue
                if label not in ("**전체**", "노출(≤2026-09-02)", "보호(≥2026-09-03)"):
                    continue
                mm = gt.compute_metrics(sub)
                a("| `{}` | `{}` | {} | {} | {:.4f} | {:.4f} | {:.4f} | {} |".format(
                    STRATEGIES[k]["name"], s2["params_hash"][:8], label, mm["n_days"],
                    mm["M1"], mm["M3"], mm["M4"], gt.verdict(mm)))
    a("")
    a("🔴 문턱 미달이면 **고치지 않고** 위 분류표와 함께 보고한다 — "
      "문턱·정렬·룰을 결과를 보고 바꾸는 것은 금지다(REGISTRY 규칙 3).")
    a("🔴 **조건부 통과 제안 불가** — 설계서 §4-6 3 조건 ⑤(보호 구간 ≥ 15거래일)를 "
      "실측 보호 구간 **7거래일**이 못 채운다. 채우려면 대조 창을 **2026-09-30** 까지 "
      "연장한 뒤 재판정해야 한다(연장은 게이트 대조 창만이고 **판정 창 537일은 건드리지 않는다**).")
    a("")
    return r


if __name__ == "__main__":
    raise SystemExit(main())
