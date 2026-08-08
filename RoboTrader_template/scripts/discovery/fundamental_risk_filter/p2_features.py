"""P(2) 그날 알 수 있었던 재무 피처 — 종목별 계단함수 + merge_asof.

읽기 전용. DB 쓰기 0 · DART 호출 0.

🔴 as-of 로직을 재구현하지 않는다. 접수일 경계마다 `pit_join.asof_financials`
   를 «그대로» 호출한다. 정렬해서 마지막을 취하면 가장 최근 「문서」가 뽑히는데,
   정정공시 때문에 그것이 가장 최근 「사업연도」가 아닐 수 있다(Phase 1 F3).
🔴 임계값을 넣지 않는다. 연속값까지만 만들고 문턱은 Phase 2B 의 PREREG 에서 동결한다.
   유일한 예외가 자본잠식(total_equity <= 0)이고, 그건 자유모수가 없다.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/p2_features.py
"""
import datetime as _dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_client import OUT_DIR, db_conn  # noqa: E402
from p1_target import DATE_MAX, TARGET_PARQUET  # noqa: E402
from pit_join import asof_financials, _daystr  # noqa: E402

FEATURES_PARQUET = os.path.join(OUT_DIR, "frf_features.parquet")

FIN_SQL = """
SELECT stock_code, bsns_year, rcept_dt::text, total_equity, issued_capital,
       total_liabilities, operating_income, finance_costs
FROM dart_financials_asfiled
WHERE rcept_dt IS NOT NULL
ORDER BY stock_code, rcept_dt
"""


def _next_day(daystr):
    d = _dt.date(int(daystr[0:4]), int(daystr[5:7]), int(daystr[8:10]))
    return (d + _dt.timedelta(days=1)).isoformat()


def consec_op_loss(records, as_of):
    """as_of 에 보이는 사업연도들을 최신부터 훑어 «연속» 영업손실 연수를 센다.

    중간 연도가 비면 거기서 끊는다 — 없는 해를 적자로 세지 않는다.
    호출자의 정렬에 의존하지 않는다 — rcept_dt 오름차순으로 정렬한 뒤 처리한다.
    """
    # rcept_dt 오름차순으로 정렬하면 같은 사업연도에서 최신 정정본이 마지막으로 덮어쓴다
    sorted_records = sorted(records, key=lambda r: _daystr(r.get("rcept_dt")) or "")
    visible = {}
    for r in sorted_records:
        cur = asof_financials([r], as_of)
        if cur is None:
            continue
        visible[str(r["bsns_year"])] = r.get("operating_income")
    if not visible:
        return 0
    n = 0
    year = max(int(y) for y in visible)
    while True:
        oi = visible.get(str(year))
        if oi is None or oi >= 0:
            break
        n += 1
        year -= 1
    return n


def _row(rec, records, as_of):
    eq = rec.get("total_equity")
    li = rec.get("total_liabilities")
    oi = rec.get("operating_income")
    fc = rec.get("finance_costs")
    return {
        "from_date": as_of,
        "bsns_year": str(rec["bsns_year"]),
        "rcept_dt": str(rec["rcept_dt"])[:10],
        # 🔴 None = 「자본총계를 읽을 수 없다」. False(정상)와 «반드시» 구별해야 한다.
        #    배제 필터에서 「모른다」를 「안전」으로 접으면 그 종목이 필터를 통과한다.
        #    실측 2026-08-08: 자본총계 null 로 인한 None 이 패널 279행(136490·217190).
        "equity_impaired": (None if eq is None else (eq <= 0)),
        "debt_ratio": (li / eq) if (eq is not None and eq > 0 and li is not None) else None,
        "op_loss_years": consec_op_loss(records, as_of),
        "interest_coverage": (oi / fc) if (fc is not None and fc > 0 and oi is not None) else None,
    }


def step_table(records):
    """종목 하나의 재무 이력 → 계단 구간 목록(from_date 오름차순)."""
    dates = sorted({str(r["rcept_dt"])[:10] for r in records if r.get("rcept_dt")})
    steps = []
    for d in dates:
        as_of = _next_day(d)          # 접수 «다음 날»부터 보인다
        cur = asof_financials(records, as_of)
        if cur is None:
            continue
        steps.append(_row(cur, records, as_of))
    return steps


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = db_conn()
    fin = pd.read_sql(FIN_SQL, conn)
    conn.close()

    rows = []
    for code, g in fin.groupby("stock_code", sort=True):
        recs = g.to_dict("records")
        for s in step_table(recs):
            s["stock_code"] = code
            rows.append(s)
    steps = pd.DataFrame(rows)
    # 🔴 merge_asof 는 `on` 키가 «전역» 단조여야 한다. by= 를 줘도 마찬가지다.
    #    ["stock_code","from_date"] 로 정렬하면 from_date 가 전역 단조가 아니라
    #    ValueError: left keys must be sorted 로 죽는다. on 키«만»으로 정렬한다.
    steps = steps[steps["from_date"] <= DATE_MAX].sort_values(
        "from_date", kind="mergesort").reset_index(drop=True)

    tgt = pd.read_parquet(TARGET_PARQUET, columns=["stock_code", "date"])
    tgt["date"] = pd.to_datetime(tgt["date"])
    tgt = tgt.sort_values("date", kind="mergesort").reset_index(drop=True)

    steps["from_date"] = pd.to_datetime(steps["from_date"])

    merged = pd.merge_asof(
        tgt, steps,
        left_on="date", right_on="from_date", by="stock_code",
        direction="backward", allow_exact_matches=True,
    )
    merged["date"] = merged["date"].astype(str)
    merged["from_date"] = merged["from_date"].astype(str)
    merged.to_parquet(FEATURES_PARQUET, index=False)

    have = merged["bsns_year"].notna()
    print(f"계단 구간 {len(steps):,} · 종목 {steps['stock_code'].nunique():,}")
    print(f"패널 관측 {len(merged):,} · 재무 매칭 {have.sum():,} "
          f"({100*have.mean():.2f}%)")
    print(f"  자본잠식        {merged['equity_impaired'].fillna(False).mean()*100:6.3f}%")
    print(f"  부채비율 有     {merged['debt_ratio'].notna().mean()*100:6.2f}%")
    print(f"  이자보상배율 有 {merged['interest_coverage'].notna().mean()*100:6.2f}%")
    print(f"  연속영업손실≥1  {(merged['op_loss_years'].fillna(0) >= 1).mean()*100:6.2f}%")
    print(f"→ {FEATURES_PARQUET}")


if __name__ == "__main__":
    main()
