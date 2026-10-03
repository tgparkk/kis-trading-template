# -*- coding: utf-8 -*-
"""K 상향 사전등록 1차 판정 — 원자료 산출 스크립트 (2026-10-03).

대상 사전등록: docs/prereg_2026-09-15_focus3_K_raise.md (동결 · §④ P1~P6 · 2026-09-17 개정 P2 보정 SQL)
판정문:       docs/verdict_2026-10-03_focus3_K_raise.md

규칙
- DB kis_template **SELECT 만** (세션 readonly=True). 쓰기 0건.
- 라이브 로그는 읽기만 (D:/GIT/kis-trading-template/RoboTrader_template/logs).
- 날짜 창 = 동결 SQL 그대로 `BETWEEN '2026-09-18' AND '2026-10-05'` (실제 거래일 9일 · 10-05 휴장).

실행:
  D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe -X utf8 k_raise_verdict.py > k_raise_verdict_out.txt
"""
import glob
import os
import re
import statistics
from collections import defaultdict
from decimal import Decimal

import psycopg2

LOG_DIR = "D:/GIT/kis-trading-template/RoboTrader_template/logs"

FOCUS3 = ["book_pullback_ma20", "minervini_volume_dryup", "daytrading_3methods_breakout"]
CONTROL5 = ["book_pullback_ma5", "elder_ema_pullback", "book_envelope_200d", "deep_mr_dev20", "rs_leader"]
K_NEW = {"book_pullback_ma20": 10, "minervini_volume_dryup": 6, "daytrading_3methods_breakout": 10}
K_OLD = {"book_pullback_ma20": 5, "minervini_volume_dryup": 3, "daytrading_3methods_breakout": 5}
K_CONTROL = {"book_pullback_ma5": 5, "elder_ema_pullback": 20, "book_envelope_200d": 5,
             "deep_mr_dev20": 5, "rs_leader": 10}
BAND = {"book_pullback_ma20": (6, 10), "daytrading_3methods_breakout": (6, 10),
        "minervini_volume_dryup": (4, 6)}

PRE_FROM, PRE_TO = "2026-09-04", "2026-09-17"      # 발효 전 10거래일 (사전등록 §④-P2 기준선 주와 같은 창)
POST_FROM, POST_TO = "2026-09-18", "2026-10-05"    # 동결 SQL 창 그대로

# W2′ 기준선 박제값 — docs/reports/2026-09/report_2026-09-17_장마감.md 부록 A-2 (09-17 2차 · 16:03:16)
W2P_PINNED = {
    "book_pullback_ma20": Decimal("8513505.39"),
    "minervini_volume_dryup": Decimal("10263426.47"),
    "daytrading_3methods_breakout": Decimal("10228221.85"),
    "book_envelope_200d": Decimal("7367427.49"),
    "book_pullback_ma5": Decimal("8123673.77"),
    "deep_mr_dev20": Decimal("6381767.93"),
    "elder_ema_pullback": Decimal("8683634.08"),
    "rs_leader": Decimal("6395270.59"),
}


def hr(title):
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def run(cur, title, sql, params=None, show_sql=True):
    print()
    print("-" * 100)
    print(f"[SQL] {title}")
    if show_sql:
        print(sql.strip())
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    print("-- 출력 --")
    print(" | ".join(cols))
    for r in rows:
        print(" | ".join("" if v is None else str(v) for v in r))
    print(f"({len(rows)} rows)")
    return cols, rows


def main():
    conn = psycopg2.connect(host="127.0.0.1", port=5433, dbname="kis_template",
                            user="robotrader", password="1234")
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()

    # ------------------------------------------------------------------ S0
    hr("S0. 메타 — 세션 시간대 · 거래일 달력 · K 발효 로그")
    run(cur, "S0-a 세션 timezone (timestamp::date 가 KST 날짜인지)", "SHOW timezone;")
    _, cal_rows = run(cur, "S0-b 거래일 달력 (daily_prices 의사티커 'KOSPI' · 사전등록 개정 SQL 과 같은 달력)", """
SELECT date::date AS d
FROM daily_prices
WHERE stock_code = 'KOSPI'
  AND date BETWEEN '2026-09-01' AND '2026-10-06'
ORDER BY 1;
""")
    cal = [str(r[0]) for r in cal_rows]
    pre_days = [d for d in cal if PRE_FROM <= d <= PRE_TO]
    post_days = [d for d in cal if POST_FROM <= d <= POST_TO]
    print(f"\n발효 전 창 {PRE_FROM}~{PRE_TO} 거래일 {len(pre_days)}: {pre_days}")
    print(f"발효 후 창 {POST_FROM}~{POST_TO} 거래일 {len(post_days)}: {post_days}")
    print("※ 10-05 행 부재 = 휴장(개천절 대체공휴일). 10-06 은 아직 미래(오늘 10-03).")

    print("\n[로그] 기동 38행 계열 `동시 보유 한도 정정(ΣK)` — 일자별 3전략 K")
    for f in sorted(glob.glob(os.path.join(LOG_DIR, "robotrader_template_2026091[6-9]_*.log"))
                    + glob.glob(os.path.join(LOG_DIR, "robotrader_template_202609[23]*_*.log"))
                    + glob.glob(os.path.join(LOG_DIR, "robotrader_template_202610*_*.log"))):
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                if "동시 보유 한도 정정(ΣK)" in line:
                    ks = {s: re.search(rf"{s}=(\d+)", line) for s in FOCUS3}
                    tot = re.search(r"ΣK\D*?=\s*(\d+)|합계\D*(\d+)|total\D*(\d+)", line)
                    allk = [int(x) for x in re.findall(r"=(\d+)", line)]
                    print(f"  {os.path.basename(f)}:{i}  "
                          + " ".join(f"{s.split('_')[0] if s != 'book_pullback_ma20' else 'ma20'}="
                                     f"{ks[s].group(1) if ks[s] else '?'}" for s in FOCUS3)
                          + f"  Σ(줄의 모든 K)={sum(allk[:8])}")
                    break

    # ------------------------------------------------------------------ S1 P1
    hr("S1. P1 — 발효 후 창 EOD 캡 포화율 (3전략 · 새 K 10/6/10 · 문턱 < 50%)")
    print("※ §①-1 의 SQL 은 원문에 「요지」로만 있다(LANE_C_gate_guards.md §3-b: DISTINCT ON (trade_date, strategy)"
          " … ORDER BY updated_at DESC 로 2차만 남기고 K 를 VALUES 로 조인해 n_open >= K 인 거래일을 센다)."
          " 아래는 그 요지를 그대로 옮긴 재구성이다. 창만 사전등록 P1 의 09-18~10-05.")
    p1_sql = """
WITH k(strategy, k) AS (
    VALUES ('book_pullback_ma20', 10),
           ('minervini_volume_dryup', 6),
           ('daytrading_3methods_breakout', 10)
),
eod AS (
    SELECT DISTINCT ON (trade_date, strategy) trade_date, strategy, n_open
    FROM paper_strategy_equity
    ORDER BY trade_date, strategy, updated_at DESC
)
SELECT e.strategy, k.k,
       COUNT(*)                                             AS n_days,
       SUM(CASE WHEN e.n_open >= k.k THEN 1 ELSE 0 END)     AS n_sat,
       ROUND(100.0 * SUM(CASE WHEN e.n_open >= k.k THEN 1 ELSE 0 END) / COUNT(*), 1) AS sat_pct
FROM eod e
JOIN k USING (strategy)
WHERE e.trade_date BETWEEN '2026-09-18' AND '2026-10-05'
GROUP BY 1, 2
ORDER BY 1;
"""
    _, p1_rows = run(cur, "S1-a P1 주 판정 SQL (EOD 포화일 / 거래일)", p1_sql)
    p1 = {r[0]: (r[1], r[2], r[3], float(r[4])) for r in p1_rows}

    _, p1_daily = run(cur, "S1-b 일자별 EOD n_open (3전략 · 09-16~10-02 · 참고: 09-16·17 은 구 K 기준선)", """
SELECT trade_date,
       MAX(CASE WHEN strategy = 'book_pullback_ma20'           THEN n_open END) AS ma20_n_open,
       MAX(CASE WHEN strategy = 'minervini_volume_dryup'       THEN n_open END) AS minervini_n_open,
       MAX(CASE WHEN strategy = 'daytrading_3methods_breakout' THEN n_open END) AS daytrading_n_open
FROM paper_strategy_equity
WHERE trade_date BETWEEN '2026-09-16' AND '2026-10-05'
GROUP BY 1 ORDER BY 1;
""")

    run(cur, "S1-c (참고 · 판정 아님) 발효 전 10거래일 EOD 포화 — 구 K 5/3/5 · 같은 재구성 SQL", """
WITH k(strategy, k) AS (
    VALUES ('book_pullback_ma20', 5),
           ('minervini_volume_dryup', 3),
           ('daytrading_3methods_breakout', 5)
),
eod AS (
    SELECT DISTINCT ON (trade_date, strategy) trade_date, strategy, n_open
    FROM paper_strategy_equity
    ORDER BY trade_date, strategy, updated_at DESC
)
SELECT e.strategy, k.k, COUNT(*) AS n_days,
       SUM(CASE WHEN e.n_open >= k.k THEN 1 ELSE 0 END) AS n_sat,
       ROUND(100.0 * SUM(CASE WHEN e.n_open >= k.k THEN 1 ELSE 0 END) / COUNT(*), 1) AS sat_pct
FROM eod e JOIN k USING (strategy)
WHERE e.trade_date BETWEEN '2026-09-04' AND '2026-09-17'
GROUP BY 1, 2 ORDER BY 1;
""")

    print("\n[로그] S1-d P1 보조 관측 — 09-16 계기 `[캡] <폴더키> <종목> 평가 스킵 사유=max_positions` 발생 종목-일 (3전략)")
    print("  (같은 (전략·종목·사유)는 거래일당 1회만 찍힌다 · robotrader_template_*.log 상위집합)")
    print("  (보유=n/K = 그 전략 «자기» 보유수/K — strategies/base.py _log_cap_skip. 09-28 07:40 부터 줄 끝 `경로=`"
          " 태그(매수루프/매도루프/루프밖) — 09-27 이전 줄은 태그 없음)")
    cap_re = re.compile(r"\[캡\] (\S+) (\S+) 평가 스킵 사유=(\S+) 보유=(\d+)/(\d+)(?:.*?경로=(\S+))?")
    cap_mp = defaultdict(lambda: defaultdict(set))       # day -> strategy -> stocks (max_positions)
    cap_mp_buy = defaultdict(lambda: defaultdict(set))   # day -> strategy -> stocks (max_positions · 경로=매수루프)
    cap_all = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # day -> strat -> reason -> lines
    cap_hold = defaultdict(lambda: defaultdict(set))     # day -> strat -> set("n/K") for max_positions
    for d in post_days + ["2026-09-16", "2026-09-17"]:
        ymd = d.replace("-", "")
        for f in glob.glob(os.path.join(LOG_DIR, f"robotrader_template_{ymd}_*.log")):
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if "[캡]" not in line:
                        continue
                    m = cap_re.search(line)
                    if not m:
                        continue
                    strat, code, reason, n, k, path = m.groups()
                    if strat not in FOCUS3:
                        continue
                    cap_all[d][strat][reason] += 1
                    if reason == "max_positions":
                        cap_mp[d][strat].add(code)
                        cap_hold[d][strat].add(f"{n}/{k}")
                        if path == "매수루프":
                            cap_mp_buy[d][strat].add(code)
    print("  날짜 | 전략 | max_positions 종목-일 | (그중 경로=매수루프) | 보유=n/K 값들 | 사유별 줄수(timeframe/daily_trades/max_positions)")
    tot_mp = defaultdict(int)
    for d in ["2026-09-16", "2026-09-17"] + post_days:
        for s in FOCUS3:
            ra = cap_all[d][s]
            nmp = len(cap_mp[d][s])
            nbuy = len(cap_mp_buy[d][s]) if d >= "2026-09-28" else "태그없음"
            if d >= POST_FROM:
                tot_mp[s] += nmp
            print(f"  {d} | {s} | {nmp} | {nbuy} | {','.join(sorted(cap_hold[d][s])) or '-'} | "
                  f"{ra.get('timeframe', 0)}/{ra.get('daily_trades', 0)}/{ra.get('max_positions', 0)}")
    print("  발효 후 창 합계 max_positions 종목-일: " + " · ".join(f"{s}={tot_mp[s]}" for s in FOCUS3))
    days_with_mp = {s: sum(1 for d in post_days if cap_mp[d][s]) for s in FOCUS3}
    print("  발효 후 창 max_positions 발생 «거래일» 수: " + " · ".join(f"{s}={days_with_mp[s]}/{len(post_days)}" for s in FOCUS3))
    tagged = [d for d in post_days if d >= "2026-09-28"]
    print(f"  (경로 태그 있는 {len(tagged)}거래일 {tagged[0]}~{tagged[-1]}) 경로=매수루프 max_positions 발생 거래일: "
          + " · ".join(f"{s}={sum(1 for d in tagged if cap_mp_buy[d][s])}/{len(tagged)}" for s in FOCUS3)
          + " | 매수루프 종목-일 합: "
          + " · ".join(f"{s}={sum(len(cap_mp_buy[d][s]) for d in tagged)}" for s in FOCUS3))

    # ------------------------------------------------------------------ S2 P2
    hr("S2. P2 — 새로 닿는 순위대 매수 (ma20·daytrading 6~10위 · minervini 4~6위 · 문턱 ≥1건) — 🔧 2026-09-17 개정 보정 SQL")
    p2_sql = """
-- 🔧 2026-09-17 개정 — 발효 후 신규 매수의 「스냅샷 순위」 분포
--    매수일 D ⇒ scan_date = D 의 직전 거래일(거래일 달력 = daily_prices 'KOSPI')
WITH td AS (
    SELECT date::date                           AS d,
           LAG(date::date) OVER (ORDER BY date) AS prev_d
    FROM daily_prices
    WHERE stock_code = 'KOSPI'
      AND date BETWEEN '2026-09-01' AND '2026-10-05'
)
SELECT v.strategy,
       s.rank_in_snapshot AS rk,
       COUNT(*)           AS n_buy
FROM virtual_trading_records v
JOIN td
  ON td.d = v.timestamp::date
JOIN screener_snapshots s
  ON s.strategy   = v.strategy
 AND s.stock_code = v.stock_code
 AND s.scan_date  = td.prev_d          -- 원문(결함): s.scan_date = v.timestamp::date
WHERE v.is_test = true
  AND v.action  = 'BUY'
  AND v.timestamp::date BETWEEN '2026-09-18' AND '2026-10-05'
  AND v.strategy IN ('book_pullback_ma20',
                     'minervini_volume_dryup',
                     'daytrading_3methods_breakout')
GROUP BY 1,2 ORDER BY 1,2;
"""
    _, p2_rows = run(cur, "S2-a P2 주 판정 SQL (사전등록 :401-426 개정 SQL «원문 그대로»)", p2_sql)
    band_n = {s: 0 for s in FOCUS3}
    joined_n = {s: 0 for s in FOCUS3}
    for strat, rk, n in p2_rows:
        joined_n[strat] += n
        lo, hi = BAND[strat]
        if rk is not None and lo <= rk <= hi:
            band_n[strat] += n
    print("\n  밴드 매수 집계: " + " · ".join(f"{s} [{BAND[s][0]}~{BAND[s][1]}위]={band_n[s]}" for s in FOCUS3))

    run(cur, "S2-b 조인 커버리지 점검 (창 안 3전략 매수 전건 vs 순위가 붙은 건) — 같은 조인을 LEFT 로", """
WITH td AS (
    SELECT date::date AS d, LAG(date::date) OVER (ORDER BY date) AS prev_d
    FROM daily_prices
    WHERE stock_code = 'KOSPI' AND date BETWEEN '2026-09-01' AND '2026-10-05'
)
SELECT v.strategy,
       COUNT(DISTINCT v.id)                                         AS n_buy_all,
       COUNT(DISTINCT v.id) FILTER (WHERE s.id IS NOT NULL)         AS n_buy_ranked,
       COUNT(*) FILTER (WHERE s.id IS NOT NULL)                     AS n_join_rows
FROM virtual_trading_records v
LEFT JOIN td ON td.d = v.timestamp::date
LEFT JOIN screener_snapshots s
  ON s.strategy = v.strategy AND s.stock_code = v.stock_code AND s.scan_date = td.prev_d
WHERE v.is_test = true AND v.action = 'BUY'
  AND v.timestamp::date BETWEEN '2026-09-18' AND '2026-10-05'
  AND v.strategy IN ('book_pullback_ma20','minervini_volume_dryup','daytrading_3methods_breakout')
GROUP BY 1 ORDER BY 1;
""")

    run(cur, "S2-c 매수 건별 명세 (KST 시각 · 직전 거래일 스냅샷 순위 · 그날 스냅샷 후보 수)", """
WITH td AS (
    SELECT date::date AS d, LAG(date::date) OVER (ORDER BY date) AS prev_d
    FROM daily_prices
    WHERE stock_code = 'KOSPI' AND date BETWEEN '2026-09-01' AND '2026-10-05'
),
snap_n AS (
    SELECT strategy, scan_date, COUNT(*) AS n_rows, MAX(rank_in_snapshot) AS max_rk
    FROM screener_snapshots GROUP BY 1, 2
)
SELECT to_char(v.timestamp AT TIME ZONE 'Asia/Seoul', 'MM-DD HH24:MI:SS') AS kst,
       v.strategy, v.stock_code, v.quantity, v.price::bigint AS price,
       td.prev_d AS scan_date, s.rank_in_snapshot AS rk,
       sn.n_rows AS snap_rows
FROM virtual_trading_records v
LEFT JOIN td ON td.d = v.timestamp::date
LEFT JOIN screener_snapshots s
  ON s.strategy = v.strategy AND s.stock_code = v.stock_code AND s.scan_date = td.prev_d
LEFT JOIN snap_n sn ON sn.strategy = v.strategy AND sn.scan_date = td.prev_d
WHERE v.is_test = true AND v.action = 'BUY'
  AND v.timestamp::date BETWEEN '2026-09-18' AND '2026-10-05'
  AND v.strategy IN ('book_pullback_ma20','minervini_volume_dryup','daytrading_3methods_breakout')
ORDER BY v.strategy, v.timestamp;
""")

    p2_base_sql = p2_sql.replace("v.timestamp::date BETWEEN '2026-09-18' AND '2026-10-05'",
                                 "v.timestamp::date BETWEEN '2026-09-04' AND '2026-09-17'")
    _, p2b_rows = run(cur, "S2-d 기준선 재현 (같은 보정 SQL · 창만 09-04~09-17 — 사전등록 :443-452 병기 의무)",
                      p2_base_sql)
    band_base = {s: 0 for s in FOCUS3}
    for strat, rk, n in p2b_rows:
        lo, hi = BAND[strat]
        if rk is not None and lo <= rk <= hi:
            band_base[strat] += n
    print("\n  기준선 밴드 매수: " + " · ".join(f"{s}={band_base[s]}" for s in FOCUS3)
          + "   (사전등록 병기값: ma20 1 · minervini 1 · daytrading 0)")

    run(cur, "S2-e 스냅샷 저장 규모 (전략×scan_date 행수 · 09-28 발효 「룰 통과 전수 저장」 전후 · 3전략)", """
SELECT scan_date,
       MAX(CASE WHEN strategy='book_pullback_ma20'           THEN cnt END) AS ma20_rows,
       MAX(CASE WHEN strategy='minervini_volume_dryup'       THEN cnt END) AS minervini_rows,
       MAX(CASE WHEN strategy='daytrading_3methods_breakout' THEN cnt END) AS daytrading_rows
FROM (SELECT strategy, scan_date, COUNT(*) AS cnt FROM screener_snapshots
      WHERE scan_date BETWEEN '2026-09-15' AND '2026-10-02' GROUP BY 1, 2) t
GROUP BY 1 ORDER BY 1;
""")

    # ------------------------------------------------------------------ S3 P3
    hr("S3. P3 — minervini 2차 equity vs W2′ 기준선(09-17 2차 · 박제 10,263,426.47) · 문턱 −30% (≤ 7,184,398.529)")
    _, g4 = run(cur, "S3-a 09-17 행 불변 대조 (DB 현재값 vs 09-17 보고 부록 A-2 박제값)", """
SELECT strategy, equity, cash, position_value, n_open
FROM paper_strategy_equity
WHERE trade_date = '2026-09-17'
ORDER BY strategy;
""")
    print("\n  대조: 전략 | DB equity | 박제 equity | 차")
    for strat, eq, *_ in g4:
        pin = W2P_PINNED.get(strat)
        print(f"  {strat} | {eq} | {pin} | {None if pin is None else eq - pin}")

    _, p3_rows = run(cur, "S3-b minervini 일자별 2차 equity (09-17~10-02)", """
SELECT trade_date, equity, cash, position_value, n_open
FROM paper_strategy_equity
WHERE strategy = 'minervini_volume_dryup'
  AND trade_date BETWEEN '2026-09-17' AND '2026-10-05'
ORDER BY trade_date;
""")
    base = W2P_PINNED["minervini_volume_dryup"]
    thr = base * Decimal("0.70")
    print(f"\n  기준선 {base} · 문턱(×0.70) {thr}")
    print("  날짜 | equity | 기준선 대비 % | 문턱 도달?")
    min_ratio = None
    for d, eq, *_ in p3_rows:
        ratio = (eq / base - 1) * 100
        if str(d) >= POST_FROM:
            min_ratio = ratio if min_ratio is None else min(min_ratio, ratio)
        print(f"  {d} | {int(eq.to_integral_value())} | {ratio:.3f}% | {'YES' if eq <= thr else 'no'}")
    print(f"  창 안 최저 = {min_ratio:.3f}%")
    # 일일 σ (참고)
    eqs = [float(r[1]) for r in p3_rows]
    rets = [eqs[i] / eqs[i - 1] - 1 for i in range(1, len(eqs))]
    if len(rets) > 1:
        print(f"  (참고) 창 안 일일 수익률 σ = {statistics.stdev(rets) * 100:.3f}% · n={len(rets)}")

    # ------------------------------------------------------------------ S4 P4 / P4′
    hr("S4. P4 · P4′ — 일 «매수» 건수 (action='BUY' 한정)")
    p4_sql = """
SELECT strategy, timestamp::date AS d,
       COUNT(*) FILTER (WHERE action = 'BUY') AS n_buy,
       COUNT(*)                               AS n_all
FROM virtual_trading_records
WHERE is_test = true
  AND timestamp::date BETWEEN %s AND %s
GROUP BY 1, 2
ORDER BY 1, 2;
"""
    _, post_rows = run(cur, f"S4-a 발효 후 창 {POST_FROM}~{POST_TO} 전략×날짜 매수/총체결 (8전략)",
                       p4_sql, (POST_FROM, POST_TO))
    _, pre_rows = run(cur, f"S4-b 발효 전 10거래일 {PRE_FROM}~{PRE_TO} 전략×날짜 매수/총체결 (8전략)",
                      p4_sql, (PRE_FROM, PRE_TO))

    def per_day(rows, days):
        m = defaultdict(lambda: {d: 0 for d in days})
        m_all = defaultdict(lambda: {d: 0 for d in days})
        off = []
        for strat, d, nb, na in rows:
            d = str(d)
            if d not in days:
                off.append((strat, d, nb, na))
                continue
            m[strat][d] = nb
            m_all[strat][d] = na
        return m, m_all, off

    post_m, post_all, post_off = per_day(post_rows, post_days)
    pre_m, pre_all, pre_off = per_day(pre_rows, pre_days)
    print(f"\n  거래일 아닌 날짜의 체결(있으면 표시): 후 {post_off} · 전 {pre_off}")

    print("\n  [P4] 발효 후 창 전략별 일 «매수» 최대 (8전략) — 반증 = 어느 전략이든 하루 매수 ≥ 6")
    p4_max = {}
    for s in FOCUS3 + CONTROL5:
        mx = max(post_m[s].values()) if post_m[s] else 0
        mx_all = max(post_all[s].values()) if post_all[s] else 0
        p4_max[s] = mx
        print(f"  {s}: 일 매수 최대 {mx} · (참고·판정 아님) 일 총체결 최대 {mx_all}")

    print("\n  [P4′] 3전략 합산 일 «매수» — 발효 전 10거래일 vs 발효 후 창")
    print("  날짜 | ma20 | minervini | daytrading | 3전략 합")
    for label, m, days in (("전", pre_m, pre_days), ("후", post_m, post_days)):
        for d in days:
            row = [m[s][d] for s in FOCUS3]
            print(f"  {label} {d} | " + " | ".join(str(x) for x in row) + f" | {sum(row)}")
    pre_sum = sum(pre_m[s][d] for s in FOCUS3 for d in pre_days)
    post_sum = sum(post_m[s][d] for s in FOCUS3 for d in post_days)
    pre_mean = pre_sum / len(pre_days)
    post_mean = post_sum / len(post_days)
    print(f"\n  발효 전: 합 {pre_sum} / {len(pre_days)}거래일 = 일평균 {pre_mean:.3f}")
    print(f"  발효 후: 합 {post_sum} / {len(post_days)}거래일 = 일평균 {post_mean:.3f}")
    for s in FOCUS3:
        a = sum(pre_m[s].values()) / len(pre_days)
        b = sum(post_m[s].values()) / len(post_days)
        print(f"  (전략별·서술) {s}: 전 {sum(pre_m[s].values())}건 ({a:.3f}/일) → 후 {sum(post_m[s].values())}건 ({b:.3f}/일)"
              f" · 후 일 최대 {max(post_m[s].values())}")
    daily_tot_post = [sum(post_m[s][d] for s in FOCUS3) for d in post_days]
    daily_tot_pre = [sum(pre_m[s][d] for s in FOCUS3) for d in pre_days]

    # ------------------------------------------------------------------ S5 P5
    hr("S5. P5 — 대조군 5전략(ma5·elder·envelope·deep_mr·rs_leader) 포화율·일 매수 분포 — 발효 전 10거래일 vs 발효 후 창 (서술)")
    print("  전략 | K | 매수 합(전→후) | 일평균(전→후) | 분산(전→후) | 일 최대(전→후) | 매수>0 일수(전→후)")
    for s in CONTROL5:
        a = [pre_m[s][d] for d in pre_days]
        b = [post_m[s][d] for d in post_days]
        print(f"  {s} | {K_CONTROL[s]} | {sum(a)}→{sum(b)} | {statistics.mean(a):.3f}→{statistics.mean(b):.3f} | "
              f"{statistics.pvariance(a):.3f}→{statistics.pvariance(b):.3f} | {max(a)}→{max(b)} | "
              f"{sum(1 for x in a if x > 0)}→{sum(1 for x in b if x > 0)}")
        print(f"      일별 전 {a}")
        print(f"      일별 후 {b}")
    ca = [sum(pre_m[s][d] for s in CONTROL5) for d in pre_days]
    cb = [sum(post_m[s][d] for s in CONTROL5) for d in post_days]
    print(f"  5전략 합 | — | {sum(ca)}→{sum(cb)} | {statistics.mean(ca):.3f}→{statistics.mean(cb):.3f} | "
          f"{statistics.pvariance(ca):.3f}→{statistics.pvariance(cb):.3f} | {max(ca)}→{max(cb)} | —")

    run(cur, "S5-b 대조군 EOD 포화일 (n_open >= K 불변) — 전 10거래일 vs 후 창", """
WITH k(strategy, k) AS (
    VALUES ('book_pullback_ma5', 5), ('elder_ema_pullback', 20), ('book_envelope_200d', 5),
           ('deep_mr_dev20', 5), ('rs_leader', 10)
),
eod AS (
    SELECT DISTINCT ON (trade_date, strategy) trade_date, strategy, n_open
    FROM paper_strategy_equity
    ORDER BY trade_date, strategy, updated_at DESC
)
SELECT e.strategy, k.k,
       CASE WHEN e.trade_date <= '2026-09-17' THEN '1_pre(09-04~09-17)' ELSE '2_post(09-18~10-05)' END AS win,
       COUNT(*) AS n_days,
       SUM(CASE WHEN e.n_open >= k.k THEN 1 ELSE 0 END) AS n_sat,
       ROUND(100.0 * SUM(CASE WHEN e.n_open >= k.k THEN 1 ELSE 0 END) / COUNT(*), 1) AS sat_pct,
       ROUND(AVG(e.n_open), 2) AS avg_n_open
FROM eod e JOIN k USING (strategy)
WHERE e.trade_date BETWEEN '2026-09-04' AND '2026-10-05'
GROUP BY 1, 2, 3 ORDER BY 1, 3;
""")

    # ------------------------------------------------------------------ S6 P6
    hr("S6. P6 — 8전략 n_open 합 < 100 (매 EOD)")
    _, p6_rows = run(cur, "S6-a 일자별 n_open 합 (8전략)", """
SELECT trade_date, SUM(n_open) AS n_open_sum, COUNT(*) AS n_strat
FROM paper_strategy_equity
WHERE trade_date BETWEEN '2026-09-17' AND '2026-10-05'
GROUP BY 1 ORDER BY 1;
""")
    p6_max = max(int(r[1]) for r in p6_rows if str(r[0]) >= POST_FROM)
    print(f"\n  창 안 최대 n_open 합 = {p6_max}")

    # ------------------------------------------------------------------ S7 P7 대체 관측
    hr("S7. P7(강등 · 미측정) 대체 관측 — 3전략 매수 체결가 분포 (사전등록 §④-P7 주 「주가 분포만 인쇄」)")
    run(cur, "S7-a 매수 체결가 분포 (전 10거래일 vs 후 창)", """
SELECT strategy,
       CASE WHEN timestamp::date <= '2026-09-17' THEN '1_pre' ELSE '2_post' END AS win,
       COUNT(*) AS n_buy,
       MIN(price)::bigint AS p_min,
       (percentile_cont(0.5) WITHIN GROUP (ORDER BY price))::bigint AS p_median,
       MAX(price)::bigint AS p_max,
       COUNT(*) FILTER (WHERE price >= 400000) AS n_ge_400k,
       ROUND(AVG(quantity * price))::bigint AS avg_amount
FROM virtual_trading_records
WHERE is_test = true AND action = 'BUY'
  AND timestamp::date BETWEEN '2026-09-04' AND '2026-10-05'
  AND strategy IN ('book_pullback_ma20','minervini_volume_dryup','daytrading_3methods_breakout')
GROUP BY 1, 2 ORDER BY 1, 2;
""")

    # ------------------------------------------------------------------ S8 10-06 민감도
    hr("S8. 10-06(10번째 거래일) 하루를 더하면 뒤집힐 수 있는 칸 — 산술 (데이터 아님 · 10-06 은 미래)")
    last = post_days[-1]
    last_open = {}
    for r in p1_daily:
        if str(r[0]) == last:
            last_open = dict(zip(FOCUS3, r[1:4]))
    for s in FOCUS3:
        k, n, sat, pct = p1[s]
        pct_if_sat = 100.0 * (sat + 1) / (n + 1)
        pct_if_not = 100.0 * sat / (n + 1)
        reach = (last_open.get(s) or 0) + 5 >= k
        print(f"  P1 {s}: 현재 {sat}/{n}={pct:.1f}% → 10-06 포화 시 {sat + 1}/{n + 1}={pct_if_sat:.1f}% · "
              f"비포화 시 {sat}/{n + 1}={pct_if_not:.1f}% · 10-02 EOD n_open {last_open.get(s)}/{k}"
              f" (하루 매수 상한 5 로 K 도달 가능? {reach})")
    for s in FOCUS3:
        print(f"  P2 {s}: 현재 밴드 매수 {band_n[s]} → "
              + ("≥1 이라 10-06 로 바뀌지 않음" if band_n[s] >= 1 else "0 이라 10-06 밴드 매수 1건이면 뒤집힘"))
    # P4′
    max_add = 15
    lo_mean = post_sum / (len(post_days) + 1)
    hi_mean = (post_sum + max_add) / (len(post_days) + 1)
    print(f"  P4′: 전 일평균 {pre_mean:.3f} · 후 9일 {post_mean:.3f} → 10-06 매수 0건이면 {lo_mean:.3f} · "
          f"15건(3전략×상한5)이면 {hi_mean:.3f}")
    print(f"  P4′: 10-06 매수 0건(최소)이어도 10거래일 평균 {lo_mean:.3f} > 전 평균 {pre_mean:.3f} → "
          f"{'뒤집히지 않음' if lo_mean > pre_mean else '뒤집힐 수 있음'}")
    sigma_k = sum(K_NEW.values()) + sum(K_CONTROL.values())
    print(f"  P6: 10-02 n_open 합 {[int(r[1]) for r in p6_rows if str(r[0]) == last]} · 이론 상한 ΣK = {sigma_k}"
          f" (n_open ≤ K 캡) → 100 도달 {'불가' if sigma_k < 100 else '가능'} (캡이 지켜지는 한)")
    last_eq, last_cash, last_pv = (Decimal(p3_rows[-1][1]), Decimal(p3_rows[-1][2]), Decimal(p3_rows[-1][3]))
    print(f"  P3: 창 안 최저 {min_ratio:.3f}% · 10-06 하루에 문턱 도달하려면 10-02 equity 대비 "
          f"{(thr / last_eq - 1) * 100:.2f}% = 보유 평가액 {int(last_pv)} 의 {((last_eq - thr) / last_pv) * 100:.2f}% 하락 필요"
          f" (현금 {int(last_cash)} 불변 가정)")

    # ------------------------------------------------------------------ S9 요약
    hr("S9. 판정 입력 요약 (숫자만 — 판정 문구는 판정문 §0)")
    print("  P1 sat%: " + " · ".join(f"{s}={p1[s][3]}% ({p1[s][2]}/{p1[s][1]})" for s in FOCUS3))
    print("  P2 band: " + " · ".join(f"{s}={band_n[s]}" for s in FOCUS3) + "  | 기준선: "
          + " · ".join(f"{s}={band_base[s]}" for s in FOCUS3))
    print(f"  P3 min ratio: {min_ratio:.3f}%")
    print("  P4 max daily BUY: " + " · ".join(f"{s}={p4_max[s]}" for s in FOCUS3 + CONTROL5))
    print(f"  P4′ mean: pre {pre_mean:.3f} ({pre_sum}/{len(pre_days)}) → post {post_mean:.3f} ({post_sum}/{len(post_days)})")
    print(f"     daily totals pre {daily_tot_pre} · post {daily_tot_post}")
    print(f"  P6 max n_open sum: {p6_max}")

    conn.close()


if __name__ == "__main__":
    main()
