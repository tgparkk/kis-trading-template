"""갭 지속 조건 — 이벤트·조건·결과 빌드 (사전등록 `docs/prereg_2026-09-30_gap_persistence.md`).

실행(워크트리 `RoboTrader_template/` 에서):
    python -m backtest.gap_persistence.build_events

🔴 DB 는 SELECT 만(세션 `default_transaction_read_only=on`) · 라이브 모듈 수정 0줄(`config.constants` import 만)
   · 출력은 레포 밖 `D:/research-archive/gap_persistence_20260930/`.
사전등록 절 번호: §2 F1(created_at 시간대) · F2(연결 ≤ 3 · 커버리지) · F3(dart 출처 분리) · F4(거래일) ·
§3 U1~U6 · §4 N1/N1b/N1L/N2/N2c/N2b · §5 결과변수.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

_RO = "-c default_transaction_read_only=on"
if _RO not in os.environ.get("PGOPTIONS", ""):
    os.environ["PGOPTIONS"] = (os.environ.get("PGOPTIONS", "") + " " + _RO).strip()

ROOT = Path(__file__).resolve().parents[2]          # …/RoboTrader_template
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:  # cp949 콘솔 대비
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

import numpy as np          # noqa: E402
import pandas as pd         # noqa: E402
import psycopg2             # noqa: E402

from config.constants import SQL_STOCK_ONLY, resolve_daily_source_db  # noqa: E402
from backtest.gap_persistence import dart_tags_copy as DT             # noqa: E402

PREREG = ROOT / "docs" / "prereg_2026-09-30_gap_persistence.md"
DART_TAGS_COPY = Path(DT.__file__)
DART_TAGS_SRC = Path("D:/tmp/kis-wt-dart-events/RoboTrader_template/backtest/concept_axes/"
                     "candidate_ledger/dart_events/dart_tags.py")
OUT = Path(os.environ.get("GAP_PERSIST_OUT", "D:/research-archive/gap_persistence_20260930"))

# ── 사전등록 상수(§2~§5) ────────────────────────────────────────────────────────
WIN_START, WIN_END = "2025-12-11", "2026-09-30"
FETCH_START = "2025-10-01"                 # §3 20거래일 lookback
NEWS_FETCH_START = "2025-11-20"            # 저장값 기준(UTC 구간은 +9h 되므로 창 시작보다 충분히 이르다)
DART_FETCH_START = "2025-11-20"
TZ_CUTOVER = "2026-03-09 12:00:00"         # §2 F1 — 저장값 < 이 시각 = UTC
MIN_ROWS_TRADEDAY = 1000                   # §2 F4
ADTV_N, ADTV_MIN_ROWS, ADTV_MIN = 20, 15, 1e9   # §3 U4
LINK_CAP = 3                               # §4-2
COVER_MIN = 20                             # §4-2 · §4-4
LIMIT = 0.30                               # §3 U6
EPS = 1e-9
GAP_E3, GAP_E5 = 0.03, 0.05
EXAMPLE = ("126340", "2026-09-30")         # 비나텍(리포트 §2)

TAG_COLS = {name: f"tag{t}" for t, name, _ in DT.TAG_TABLE}
TAG_COLS[DT.OTHER] = "tag_other"

Q_PRICES = (
    "SELECT stock_code, date, open, close, volume, trading_value, adj_factor "
    "FROM daily_prices WHERE " + SQL_STOCK_ONLY + " AND date >= %s AND date <= %s"
)
Q_NEWS = (
    "SELECT ns.stock_code, n.id AS news_id, n.source, n.created_at, "
    "(n.created_at = date_trunc('second', n.created_at)) AS whole_sec, k.k "
    "FROM news n JOIN news_stock ns ON ns.news_id = n.id "
    "JOIN (SELECT news_id, COUNT(*) AS k FROM news_stock GROUP BY news_id) k ON k.news_id = n.id "
    "WHERE n.created_at >= %s"
)
Q_DART = (
    "SELECT rcept_no, stock_code, report_nm, rcept_dt, pblntf_ty, is_correction "
    "FROM dart_disclosures WHERE rcept_dt >= %s AND rcept_dt <= %s "
    "AND stock_code IS NOT NULL AND stock_code <> ''"
)
Q_EX_NEWS = (
    "SELECT n.id, n.source, n.created_at, n.title, "
    "(SELECT COUNT(*) FROM news_stock x WHERE x.news_id = n.id) AS k "
    "FROM news n JOIN news_stock ns ON ns.news_id = n.id "
    "WHERE ns.stock_code = %s AND n.created_at >= %s AND n.created_at < %s ORDER BY n.created_at"
)
Q_EX_DART = (
    "SELECT rcept_no, report_nm, rcept_dt, pblntf_ty FROM dart_disclosures "
    "WHERE stock_code = %s AND rcept_dt >= %s AND rcept_dt <= %s ORDER BY rcept_no"
)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def connect():
    return psycopg2.connect(
        host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
        port=int(os.getenv("TIMESCALE_PORT", "5433")),
        dbname=resolve_daily_source_db(),
        user=os.getenv("TIMESCALE_USER", "robotrader"),
        password=os.getenv("TIMESCALE_PASSWORD", "1234"),
    )


def fetch(conn, sql: str, params) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [c.name for c in cur.description]
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


def say(*a) -> None:
    print(*a, flush=True)


def to_kst(created: pd.Series) -> pd.Series:
    """§2 F1 — 저장값 < TZ_CUTOVER 는 UTC 로 보고 +9h."""
    created = pd.to_datetime(created)
    utc_era = created < pd.Timestamp(TZ_CUTOVER)
    return created.where(~utc_era, created + pd.Timedelta(hours=9)), utc_era


def main() -> None:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    meta: dict = {"started_at": time.strftime("%Y-%m-%d %H:%M:%S")}

    say("=" * 100)
    say("갭 지속 조건 — build_events")
    prereg_sha = sha256_file(PREREG)
    copy_sha = sha256_file(DART_TAGS_COPY)
    src_sha = sha256_file(DART_TAGS_SRC) if DART_TAGS_SRC.exists() else None
    say(f"사전등록 sha256 = {prereg_sha}  ({PREREG.name})")
    say(f"dart_tags 사본 sha256 = {copy_sha} · 원본 = {src_sha} · 일치 = {copy_sha == src_sha}")
    say(f"python {platform.python_version()} · pandas {pd.__version__} · numpy {np.__version__}")
    say(f"DB = {resolve_daily_source_db()} · PGOPTIONS = {os.environ['PGOPTIONS']!r}")
    say(f"종목 술어(config/constants.py SQL_STOCK_ONLY) = {SQL_STOCK_ONLY}")
    meta.update(prereg_sha256=prereg_sha, dart_tags_copy_sha256=copy_sha, dart_tags_src_sha256=src_sha,
                python=platform.python_version(), pandas=pd.__version__, numpy=np.__version__)

    conn = connect()
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("SHOW default_transaction_read_only")
        ro = cur.fetchone()[0]
    say(f"세션 default_transaction_read_only = {ro}")
    meta["session_read_only"] = ro

    # ── 가격 ────────────────────────────────────────────────────────────────────
    say("\n[Q_PRICES] " + Q_PRICES + f"  params=({FETCH_START!r}, {WIN_END!r})")
    px = fetch(conn, Q_PRICES, (FETCH_START, WIN_END))
    say(f"  행 수 = {len(px):,} · 종목 수 = {px.stock_code.nunique():,}")
    meta["rows_prices"] = int(len(px))

    cnt = px.groupby("date").size()
    trade_days = sorted(cnt[cnt >= MIN_ROWS_TRADEDAY].index.tolist())
    dropped_days = {d: int(n) for d, n in cnt[cnt < MIN_ROWS_TRADEDAY].items()}
    say(f"  거래일(행 ≥ {MIN_ROWS_TRADEDAY}) = {len(trade_days)} ({trade_days[0]} ~ {trade_days[-1]}) · "
        f"빠진 날짜 = {dropped_days}")
    meta.update(n_trade_days_fetched=len(trade_days), dropped_days=dropped_days)
    px = px[px.date.isin(set(trade_days))].copy()

    codes = sorted(px.stock_code.unique())
    ci = {c: i for i, c in enumerate(codes)}
    di = {d: j for j, d in enumerate(trade_days)}
    S, D = len(codes), len(trade_days)
    r = px.stock_code.map(ci).to_numpy()
    c = px.date.map(di).to_numpy()

    def mat(col):
        m = np.full((S, D), np.nan)
        m[r, c] = pd.to_numeric(px[col], errors="coerce").to_numpy(dtype=float)
        return m

    O, C, V, TVraw, A = mat("open"), mat("close"), mat("volume"), mat("trading_value"), mat("adj_factor")
    E = np.zeros((S, D), dtype=bool)
    E[r, c] = True
    TV = np.where(np.isnan(TVraw), C * V, TVraw)
    TV[~E] = np.nan
    A1 = np.where(E, np.where(np.isnan(A), 1.0, A), np.nan)       # COALESCE(adj_factor, 1)
    Cpos = np.where(C > 0, C, np.nan)
    Opos = np.where(O > 0, O, np.nan)

    win_js = [di[d] for d in trade_days if WIN_START <= d <= WIN_END]
    say(f"  창 거래일 = {len(win_js)} ({trade_days[win_js[0]]} ~ {trade_days[win_js[-1]]})")
    meta["n_trade_days_window"] = len(win_js)
    if win_js[0] < ADTV_N:
        raise SystemExit("lookback 부족")

    # ── 뉴스 ────────────────────────────────────────────────────────────────────
    say("\n[Q_NEWS] " + Q_NEWS + f"  params=({NEWS_FETCH_START!r},)")
    nw = fetch(conn, Q_NEWS, (NEWS_FETCH_START,))
    say(f"  행 수(연결) = {len(nw):,} · 기사 = {nw.news_id.nunique():,}")
    meta["rows_news_links"] = int(len(nw))
    nw["ck"], nw["utc_era"] = to_kst(nw["created_at"])
    xt = pd.crosstab(nw["utc_era"], nw["whole_sec"])
    say("  F1 교차표(행 = 규칙상 UTC 구간 · 열 = 소수초 0 지문) — 연결 행 기준:")
    say("  " + xt.to_string().replace("\n", "\n  "))
    meta["f1_crosstab"] = {f"utc_era={i}|whole_sec={j}": int(xt.loc[i, j]) for i in xt.index for j in xt.columns}

    T_ts = pd.to_datetime(pd.Series(trade_days))
    opens = (T_ts + pd.Timedelta(hours=9)).to_numpy()
    closes = (T_ts + pd.Timedelta(hours=15, minutes=30)).to_numpy()
    ck = nw["ck"].to_numpy()
    jj = np.searchsorted(opens, ck, side="right")               # 첫 j: T[j] 09:00 > ck
    ok_b = (jj >= 1) & (jj < D)                                  # [T[j−1] 09:00, T[j] 09:00)
    prev_close = np.full(len(nw), np.datetime64("NaT"), dtype="datetime64[ns]")
    prev_close[ok_b] = closes[jj[ok_b] - 1]
    ok_pre = ok_b & (ck >= prev_close)                           # [T[j−1] 15:30, T[j] 09:00)
    nw["j"] = jj
    nw["ok_pre"], nw["ok_b"] = ok_pre, ok_b
    nw["sidx"] = nw.stock_code.map(ci)                           # 유니버스 밖 코드는 NaN

    nondart = nw.source != "dart"
    elig = nondart & (nw.k <= LINK_CAP)
    say(f"  비-dart 연결 = {int(nondart.sum()):,} · 그중 연결 ≤ {LINK_CAP} = {int(elig.sum()):,} · "
        f"dart 출처 연결 = {int((~nondart).sum()):,}")

    def cover(mask) -> np.ndarray:
        g = nw.loc[mask].groupby("j").stock_code.nunique()
        out = np.zeros(D, dtype=int)
        out[g.index.to_numpy()] = g.to_numpy()
        return out

    cov1_n = cover(elig & nw.ok_pre)
    cov2b_n = cover((~nondart) & nw.ok_pre)
    cov1 = cov1_n >= COVER_MIN
    cov2b = cov2b_n >= COVER_MIN

    def pairset(mask) -> set:
        sub = nw.loc[mask & nw.sidx.notna(), ["sidx", "j"]]
        return set(zip(sub.sidx.astype(int), sub.j.astype(int)))

    set_n1 = pairset(elig & nw.ok_pre)
    set_n1b = pairset(elig & nw.ok_b)
    set_n1l = pairset(nondart & nw.ok_pre)
    set_n2b = pairset((~nondart) & nw.ok_pre)
    n1_cnt = nw.loc[elig & nw.ok_pre & nw.sidx.notna()].groupby(["sidx", "j"]).news_id.nunique()

    cov_days = [trade_days[j] for j in win_js if cov1[j]]
    say(f"  N1 커버 날짜(창 안 · 적격 연결 종목 ≥ {COVER_MIN}) = {len(cov_days)}일")
    say("    " + ", ".join(cov_days))
    cov2b_days = [trade_days[j] for j in win_js if cov2b[j]]
    say(f"  N2b 커버 날짜(창 안) = {len(cov2b_days)}일 ({cov2b_days[0] if cov2b_days else '-'} ~ "
        f"{cov2b_days[-1] if cov2b_days else '-'})")
    meta.update(n1_cover_days=cov_days, n2b_cover_days=cov2b_days)

    # ── DART ────────────────────────────────────────────────────────────────────
    say("\n[Q_DART] " + Q_DART + f"  params=({DART_FETCH_START!r}, {WIN_END!r})")
    dd = fetch(conn, Q_DART, (DART_FETCH_START, WIN_END))
    say(f"  행 수 = {len(dd):,}")
    meta["rows_dart"] = int(len(dd))
    tg = dd.report_nm.map(DT.tag_of)
    dd["tag"] = tg.map(lambda x: x[0])
    dd["is_corr"] = tg.map(lambda x: x[1])
    mism = int((dd.is_corr != dd.is_correction.astype(bool)).sum())
    say(f"  is_corr(§3-2 재계산) ≠ 적재 is_correction : {mism:,}건(정보용 · 분석은 재계산 값)")
    fmt_ok = dd.stock_code.str.match(r"^[0-9][0-9A-Z]{5}$")
    say(f"  stock_code 형식 통과 = {int(fmt_ok.sum()):,}/{len(dd):,}")
    rd = pd.to_datetime(dd.rcept_dt).to_numpy()
    dj = np.searchsorted(T_ts.to_numpy(), rd, side="right")      # 첫 j: T[j] > rcept_dt
    dd["j"] = dj
    dd["okj"] = (dj >= 1) & (dj < D)                             # T[j−1] ≤ rcept_dt < T[j]
    dd["sidx"] = dd.stock_code.map(ci)
    dsub = dd[dd.okj & dd.sidx.notna()]
    set_n2 = set(zip(dsub.loc[~dsub.is_corr, "sidx"].astype(int), dsub.loc[~dsub.is_corr, "j"].astype(int)))
    set_n2c = set(zip(dsub.sidx.astype(int), dsub.j.astype(int)))
    tag_sets = {}
    for name, col in TAG_COLS.items():
        s = dsub[(~dsub.is_corr) & (dsub.tag == name)]
        tag_sets[col] = set(zip(s.sidx.astype(int), s.j.astype(int)))
    say("  태그 분포(원공시 · 창 매핑된 행): " + ", ".join(
        f"{n}={int(((~dsub.is_corr) & (dsub.tag == n)).sum()):,}" for n in TAG_COLS))

    # ── 이벤트(§3) ──────────────────────────────────────────────────────────────
    recs = []
    att = {k: {"E5": 0, "E3": 0} for k in ("U1-U3", "U4", "U5", "U6")}
    fail_u2 = fail_u3 = 0
    for j in win_js:
        u2 = (Opos[:, j] > 0) & (Cpos[:, j] > 0) & (V[:, j] > 0)
        u3 = Cpos[:, j - 1] > 0
        fail_u2 += int((E[:, j] & ~u2).sum())
        fail_u3 += int((E[:, j] & u2 & ~u3).sum())
        base = u2 & u3
        gap = O[:, j] / C[:, j - 1] - 1.0
        cand = base & (gap >= GAP_E3 - EPS)
        idx = np.where(cand)[0]
        if idx.size == 0:
            continue
        g = gap[idx]
        # U4
        tvw = TV[idx, j - ADTV_N:j]
        nrows = np.sum(~np.isnan(tvw), axis=1)
        with np.errstate(invalid="ignore"):
            adtv = np.where(nrows > 0, np.nansum(tvw, axis=1) / np.maximum(nrows, 1), np.nan)
        u4 = (nrows >= ADTV_MIN_ROWS) & (adtv >= ADTV_MIN)
        # U5
        hi = min(j + 5, D - 1)
        aw = A1[idx, j - 1:hi + 1]
        with np.errstate(invalid="ignore"):
            u5 = ~((np.nanmax(aw, axis=1) - np.nanmin(aw, axis=1)) > 1e-12)
        # U6
        bad = np.zeros(idx.size, dtype=bool)
        for k in range(j, hi + 1):
            pc = Cpos[idx, k - 1]
            with np.errstate(invalid="ignore", divide="ignore"):
                ro = Opos[idx, k] / pc - 1.0
                rc = Cpos[idx, k] / pc - 1.0
            bad |= (np.abs(ro) > LIMIT + EPS) & ~np.isnan(ro)
            bad |= (np.abs(rc) > LIMIT + EPS) & ~np.isnan(rc)
        u6 = ~bad
        # 결과(§5)
        o, cl = O[idx, j], C[idx, j]

        def fwd(k):
            if j + k > D - 1:
                return np.full(idx.size, np.nan)
            return Cpos[idx, j + k]

        c1, c5 = fwd(1), fwd(5)
        c2prev = Cpos[idx, j - 2]
        e5 = g >= GAP_E5 - EPS
        for lab, m in (("E5", e5), ("E3", ~e5)):
            att["U1-U3"][lab] += int(m.sum())
            att["U4"][lab] += int((m & u4).sum())
            att["U5"][lab] += int((m & u4 & u5).sum())
            att["U6"][lab] += int((m & u4 & u5 & u6).sum())
        d_str = trade_days[j]
        for n, s in enumerate(idx):
            key = (int(s), j)
            rec = dict(
                stock_code=codes[s], date=d_str, j=j, gap=float(g[n]),
                close_prev=float(C[s, j - 1]), open=float(o[n]), close=float(cl[n]),
                close_d1=float(c1[n]), close_d5=float(c5[n]),
                r_oc=float(cl[n] / o[n] - 1.0),
                r_c1=float(c1[n] / cl[n] - 1.0), r_c5=float(c5[n] / cl[n] - 1.0),
                r_o5=float(c5[n] / o[n] - 1.0),
                hit=float(cl[n] > o[n]),
                r_prev=float(C[s, j - 1] / c2prev[n] - 1.0),
                adtv20=float(adtv[n]), adtv_rows=int(nrows[n]),
                u4=bool(u4[n]), u5=bool(u5[n]), u6=bool(u6[n]),
                cov1=bool(cov1[j]), cov2b=bool(cov2b[j]),
                N1=float(key in set_n1) if cov1[j] else np.nan,
                N1b=float(key in set_n1b) if cov1[j] else np.nan,
                N1L=float(key in set_n1l) if cov1[j] else np.nan,
                n1_articles=int(n1_cnt.get(key, 0)),
                N2=float(key in set_n2), N2c=float(key in set_n2c),
                N2b=float(key in set_n2b) if cov2b[j] else np.nan,
            )
            for col, st in tag_sets.items():
                rec[col] = float(key in st)
            recs.append(rec)

    ev = pd.DataFrame(recs)
    ev["set"] = np.where(ev.gap >= GAP_E5 - EPS, "E5", "E3")
    ev["gap_bucket"] = pd.cut(ev.gap, [GAP_E3 - EPS, GAP_E5 - EPS, 0.10 - EPS, 0.20 - EPS, 10.0],
                              labels=["3-5", "5-10", "10-20", "20+"], right=False).astype(str)
    say(f"\n이벤트 후보(gap ≥ +3% · U1~U3 통과) = {len(ev):,}행")
    say(f"  (창 안 행 중 U2 탈락 = {fail_u2:,} · U2 통과 후 U3 탈락 = {fail_u3:,})")
    say("  유니버스 단계별 잔존(누적):")
    for k, v in att.items():
        say(f"    {k:6s}  E5 = {v['E5']:,}  E3 = {v['E3']:,}")
    meta.update(attrition=att, fail_u2=fail_u2, fail_u3=fail_u3, rows_events=int(len(ev)))
    fin = ev[ev.u4 & ev.u5 & ev.u6]
    say(f"  최종(U1~U6) E5 = {int((fin.set == 'E5').sum()):,} · E3 = {int((fin.set == 'E3').sum()):,}")
    say(f"  최종 E5 중 N1 커버 날짜 = {int(((fin.set == 'E5') & fin.cov1).sum()):,} · "
        f"N1=1 = {int(((fin.set == 'E5') & (fin.N1 == 1)).sum()):,} · "
        f"N2=1 = {int(((fin.set == 'E5') & (fin.N2 == 1)).sum()):,}")

    cov_df = pd.DataFrame({
        "date": [trade_days[j] for j in win_js],
        "n1_cover_stocks": [int(cov1_n[j]) for j in win_js],
        "n1_covered": [bool(cov1[j]) for j in win_js],
        "n2b_cover_stocks": [int(cov2b_n[j]) for j in win_js],
        "n2b_covered": [bool(cov2b[j]) for j in win_js],
    })

    # ── 예시(비나텍) 원자료 — 제목·연결만 ─────────────────────────────────────────
    ex_code, ex_date = EXAMPLE
    jx = di[ex_date]
    lo_ck = pd.Timestamp(trade_days[jx - 1]) - pd.Timedelta(days=1)
    exn = fetch(conn, Q_EX_NEWS, (ex_code, lo_ck.to_pydatetime(), pd.Timestamp(ex_date).to_pydatetime()
                                  + pd.Timedelta(days=1)))
    exn["ck"], _ = to_kst(exn["created_at"])
    exn["in_pre"] = (exn.ck >= pd.Timestamp(trade_days[jx - 1]) + pd.Timedelta(hours=15, minutes=30)) & \
                    (exn.ck < pd.Timestamp(ex_date) + pd.Timedelta(hours=9))
    exd = fetch(conn, Q_EX_DART, (ex_code, trade_days[jx - 1], ex_date))
    exd["tag"] = exd.report_nm.map(lambda x: DT.tag_of(x)[0])
    exd["is_corr"] = exd.report_nm.map(lambda x: DT.tag_of(x)[1])
    conn.close()

    # ── 저장 ────────────────────────────────────────────────────────────────────
    p_parq, p_csv = OUT / "events.parquet", OUT / "events.csv"
    ev.to_parquet(p_parq, index=False)
    ev.to_csv(p_csv, index=False, encoding="utf-8-sig")
    p_cov = OUT / "coverage_by_day.csv"
    cov_df.to_csv(p_cov, index=False, encoding="utf-8-sig")
    p_ex = OUT / "example_126340.json"
    p_ex.write_text(json.dumps({
        "news": [dict(id=int(a.id), source=a.source, created_at=str(a.created_at), ck=str(a.ck), k=int(a.k),
                      in_pre_window=bool(a.in_pre), title=a.title) for a in exn.itertuples()],
        "dart": [dict(rcept_no=a.rcept_no, report_nm=a.report_nm, rcept_dt=str(a.rcept_dt),
                      pblntf_ty=a.pblntf_ty, tag=a.tag, is_corr=bool(a.is_corr)) for a in exd.itertuples()],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    meta.update(
        queries=dict(prices=Q_PRICES, news=Q_NEWS, dart=Q_DART, ex_news=Q_EX_NEWS, ex_dart=Q_EX_DART),
        params=dict(FETCH_START=FETCH_START, WIN_START=WIN_START, WIN_END=WIN_END,
                    NEWS_FETCH_START=NEWS_FETCH_START, DART_FETCH_START=DART_FETCH_START,
                    TZ_CUTOVER=TZ_CUTOVER, MIN_ROWS_TRADEDAY=MIN_ROWS_TRADEDAY, ADTV_N=ADTV_N,
                    ADTV_MIN_ROWS=ADTV_MIN_ROWS, ADTV_MIN=ADTV_MIN, LINK_CAP=LINK_CAP,
                    COVER_MIN=COVER_MIN, LIMIT=LIMIT),
        elapsed_sec=round(time.time() - t0, 1),
    )
    meta["outputs"] = {str(p_parq): len(ev), str(p_csv): len(ev), str(p_cov): len(cov_df),
                       str(p_ex): f"news {len(exn)} · dart {len(exd)}"}
    meta["events_parquet_sha256"] = sha256_file(p_parq)
    (OUT / "build_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=str),
                                         encoding="utf-8")
    say("\n출력:")
    for p, n in meta["outputs"].items():
        say(f"  {p}  ({n}행)" if isinstance(n, int) else f"  {p}  ({n})")
    say(f"  {OUT / 'build_meta.json'}")
    say(f"events.parquet sha256 = {meta['events_parquet_sha256']}")
    say(f"실행 시간 = {meta['elapsed_sec']}초")


if __name__ == "__main__":
    main()
