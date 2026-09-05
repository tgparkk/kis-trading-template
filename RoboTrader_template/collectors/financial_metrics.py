"""account_id → 13지표 매핑 + as_of 기준 Wide 파생 함수.

🔴 as_of 필터가 이 파일의 존재 이유다. rcept_dt <= as_of 를 빼면
   백테스트가 «그날 몰랐던 재무»를 본다(look-ahead).

METRIC_MAP 은 추측이 아니라 실측이다 — D:/archive/fund-pit-raw-20260813/f2_raw.jsonl.gz
(17,892건 접수 레코드 · 2,823,446 계정행)의 (sj_div, account_id, account_nm) 빈도를 세어
채웠다. 원자료·집계 스크립트·전체 상위 300행은
D:/GIT/kis-trading-template/scratchpad/financials/account_freq.txt 참조.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

# 지표 → account_id 후보(실측 빈도 내림차순). 총 접수 레코드 17,892건 기준.
# ⚠️ ifrs 표준 50.1% · dart_ 확장 33.6% · 표준계정코드 미사용 16.3% 라
#    한 지표에 여러 account_id 가 대응한다.
# 후보별 실측 건수(전수 카운트, sj_div 불문):
#   total_assets       ifrs-full_Assets 15,686
#   total_equity       ifrs-full_Equity 15,433(BS)/127,615(BS+SCE 재사용 포함)
#   issued_capital     ifrs-full_IssuedCapital 15,323
#   total_liabilities  ifrs-full_Liabilities 15,685
#   revenue            ifrs-full_Revenue 15,295 · RevenueFromContractsWithCustomers 2(무시 가능하나 유지)
#   operating_income   dart_OperatingIncomeLoss 15,522 (표준계정코드 없음 — dart_ 확장이 유일 후보)
#   net_income         ifrs-full_ProfitLoss 91,885(CIS/SCE/CF 재사용 포함 — 사실상 전건 커버)
#   interest_expense   dart_AdjustmentsForInterestExpenses 3,342 > ifrs-full_InterestExpense 224
#                       — 표준계정 커버리지가 너무 낮아(1.3%) CF 조정항목을 1순위로 승격
#   finance_costs      ifrs-full_FinanceCosts 14,713
#   interest_paid_cf   InterestPaidClassifiedAsOperatingActivities 13,427
#                       + …FinancingActivities 1,321(K-IFRS 는 분류 선택 사항 — 실측이 존재를 확인해 추가)
#   cf_operating       ifrs-full_CashFlowsFromUsedInOperatingActivities 15,574
#   cf_investing       ifrs-full_CashFlowsFromUsedInInvestingActivities 15,582
#   cf_financing       ifrs-full_CashFlowsFromUsedInFinancingActivities 15,577
METRIC_MAP = {
    "total_assets":      ["ifrs-full_Assets"],
    "total_equity":      ["ifrs-full_Equity"],
    "issued_capital":    ["ifrs-full_IssuedCapital"],
    "total_liabilities": ["ifrs-full_Liabilities"],
    "revenue":           ["ifrs-full_Revenue", "ifrs-full_RevenueFromContractsWithCustomers"],
    "operating_income":  ["dart_OperatingIncomeLoss"],
    "net_income":        ["ifrs-full_ProfitLoss"],
    "interest_expense":  ["dart_AdjustmentsForInterestExpenses", "ifrs-full_InterestExpense"],
    "finance_costs":     ["ifrs-full_FinanceCosts"],
    "interest_paid_cf":  ["ifrs-full_InterestPaidClassifiedAsOperatingActivities",
                           "ifrs-full_InterestPaidClassifiedAsFinancingActivities"],
    "cf_operating":      ["ifrs-full_CashFlowsFromUsedInOperatingActivities"],
    "cf_investing":      ["ifrs-full_CashFlowsFromUsedInInvestingActivities"],
    "cf_financing":      ["ifrs-full_CashFlowsFromUsedInFinancingActivities"],
}


def _metric_sql(name: str) -> str:
    ids = ", ".join("'%s'" % i.replace("'", "''") for i in METRIC_MAP[name])
    # 분기 IS 는 thstrm_add_amount(누계)를 우선한다 — 당분기만 쓰면 연간과 비교가 안 된다.
    return (f"max(CASE WHEN a.account_id IN ({ids}) "
            f"THEN COALESCE(a.thstrm_add_amount, a.thstrm_amount) END) AS {name}")


def _build_view_sql() -> str:
    metrics = ",\n        ".join(_metric_sql(k) for k in METRIC_MAP)
    cols = ",\n    ".join(f"{k} bigint" for k in METRIC_MAP)
    return f"""
CREATE OR REPLACE FUNCTION fn_financials_as_of(p_as_of date)
RETURNS TABLE (
    stock_code varchar(20),
    bsns_year  varchar(4),
    reprt_code varchar(5),
    rcept_no   varchar(14),
    rcept_dt   date,
    {cols}
) AS $$
    WITH latest AS (
        SELECT DISTINCT ON (f.stock_code, f.bsns_year, f.reprt_code)
               f.rcept_no, f.fs_div, f.stock_code, f.bsns_year, f.reprt_code, f.rcept_dt
        FROM dart_financial_filings f
        WHERE f.rcept_dt IS NOT NULL AND f.rcept_dt <= p_as_of
        ORDER BY f.stock_code, f.bsns_year, f.reprt_code, f.rcept_dt DESC, f.rcept_no DESC
    )
    SELECT l.stock_code, l.bsns_year, l.reprt_code, l.rcept_no, l.rcept_dt,
        {metrics}
    FROM latest l
    JOIN dart_financial_accounts a
      ON a.rcept_no = l.rcept_no AND a.fs_div = l.fs_div
    GROUP BY l.stock_code, l.bsns_year, l.reprt_code, l.rcept_no, l.rcept_dt
$$ LANGUAGE sql STABLE;
"""


DDL_VIEW = _build_view_sql()


def ensure_view(conn) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(DDL_VIEW)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def report_mapping_coverage(conn) -> dict:
    """🔴 비율만 남기지 말 것 — «어느 종목이 빠졌는지» 목록으로 남긴다.
    비율은 어느 종목을 고쳐야 하는지 말해주지 않는다."""
    all_ids = [i for ids in METRIC_MAP.values() for i in ids]
    with conn.cursor() as cur:
        cur.execute("SELECT count(DISTINCT stock_code) FROM dart_financial_filings")
        total = cur.fetchone()[0]
        cur.execute(
            "SELECT DISTINCT f.stock_code FROM dart_financial_filings f "
            "WHERE NOT EXISTS (SELECT 1 FROM dart_financial_accounts a "
            "  WHERE a.rcept_no=f.rcept_no AND a.fs_div=f.fs_div AND a.account_id = ANY(%s)) "
            "ORDER BY 1", (all_ids,))
        unmatched = [r[0] for r in cur.fetchall()]
    if unmatched:
        logger.warning("[financials] 13지표 매핑 실패 종목 %d/%d — 목록은 반환값 참조",
                       len(unmatched), total)
    return {"total_stocks": total, "unmatched_count": len(unmatched),
            "unmatched_stocks": unmatched}
