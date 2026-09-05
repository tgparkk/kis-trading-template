"""account_id → 13지표 매핑 + as_of 기준 Wide 파생 함수.

🔴 as_of 필터가 이 파일의 존재 이유다. rcept_dt <= as_of 를 빼면
   백테스트가 «그날 몰랐던 재무»를 본다(look-ahead).

METRIC_MAP 은 추측이 아니라 실측이다 — D:/archive/fund-pit-raw-20260813/f2_raw.jsonl.gz
(17,892건 접수 레코드 · 2,823,446 계정행)의 (sj_div, account_id, account_nm) 빈도를 세어
채웠다. 원자료·집계 스크립트·전체 상위 300행은
D:/GIT/kis-trading-template/scratchpad/financials/account_freq.txt 참조.

🔴🔴 fix round 1: account_id 만으로 매칭하면 다른 재무제표가 오염된다 — 같은 account_id
(`ifrs-full_Equity`, `ifrs-full_ProfitLoss`)가 SCE(자본변동표)의 기초/기말/변동 각 줄에도
재사용된다(실측: SCE ifrs-full_Equity 111,959건, SCE ifrs-full_ProfitLoss 70,680건).
sj_div 스코프 없이 MAX() 를 걸면 SCE 의 더 큰 값이 BS/CIS 값을 덮어써 total_equity 17.1%·
net_income 33.3% 가 오염된다(리뷰어 실측, 4,000건 표본). 그래서 후보를 (sj_div, account_id)
쌍으로 바꾸고, 문(statement)별로 스코프를 건다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

# 지표 → (sj_div, account_id) 후보 리스트(우선순위 순 — COALESCE 첫 인자가 1순위).
# sj_div 코드는 account_freq.txt 실측에 나온 그대로: BS(재무상태표)·IS(별도 손익계산서)·
# CIS(포괄손익계산서, 대부분 회사가 이 방식)·CF(현금흐름표)·SCE(자본변동표— 매핑 대상 아님).
# 전수 카운트(부분 표본, 전체는 account_freq.txt 및 task-4-report.md 참조):
#   total_assets       BS ifrs-full_Assets 15,686
#   total_equity       BS ifrs-full_Equity 15,656 (SCE 재사용 111,959건은 스코프 밖 — 매칭 안 함)
#   issued_capital     BS ifrs-full_IssuedCapital 15,323
#   total_liabilities  BS ifrs-full_Liabilities 15,685
#   revenue            IS ifrs-full_Revenue 1,255 · CIS 14,040 · IS RevenueFromContractsWithCustomers 2
#   operating_income   IS dart_OperatingIncomeLoss 1,266 · CIS 14,256
#   net_income         IS ifrs-full_ProfitLoss 1,236 · CIS 15,536 (SCE/CF 재사용은 스코프 밖)
#   interest_expense   IS ifrs-full_InterestExpense 6 · CIS 180 · CF dart_AdjustmentsForInterestExpenses
#                       3,342(폴백 — IS/CIS 표준계정이 없을 때만 쓰는 CF 조정항목 근사치)
#   finance_costs      IS ifrs-full_FinanceCosts 1,220 · CIS 13,493
#   interest_paid_cf   CF InterestPaidClassifiedAsOperatingActivities 13,427
#                       + …FinancingActivities 1,321(K-IFRS 분류 선택 사항 — 실측이 존재를 확인해 추가)
#   cf_operating       CF ifrs-full_CashFlowsFromUsedInOperatingActivities 15,574
#   cf_investing       CF ifrs-full_CashFlowsFromUsedInInvestingActivities 15,582
#   cf_financing       CF ifrs-full_CashFlowsFromUsedInFinancingActivities 15,577
METRIC_MAP = {
    "total_assets":      [("BS", "ifrs-full_Assets")],
    "total_equity":      [("BS", "ifrs-full_Equity")],
    "issued_capital":    [("BS", "ifrs-full_IssuedCapital")],
    "total_liabilities": [("BS", "ifrs-full_Liabilities")],
    "revenue": [
        ("IS", "ifrs-full_Revenue"),
        ("CIS", "ifrs-full_Revenue"),
        ("IS", "ifrs-full_RevenueFromContractsWithCustomers"),
    ],
    "operating_income": [
        ("IS", "dart_OperatingIncomeLoss"),
        ("CIS", "dart_OperatingIncomeLoss"),
    ],
    "net_income": [
        ("IS", "ifrs-full_ProfitLoss"),
        ("CIS", "ifrs-full_ProfitLoss"),
    ],
    "interest_expense": [
        ("IS", "ifrs-full_InterestExpense"),
        ("CIS", "ifrs-full_InterestExpense"),
        # CF 조정항목 폴백 — IS/CIS 에 표준계정이 없는 필터에서만 쓰는 근사치(정확한 값 아님).
        ("CF", "dart_AdjustmentsForInterestExpenses"),
    ],
    "finance_costs": [
        ("IS", "ifrs-full_FinanceCosts"),
        ("CIS", "ifrs-full_FinanceCosts"),
    ],
    "interest_paid_cf": [
        ("CF", "ifrs-full_InterestPaidClassifiedAsOperatingActivities"),
        ("CF", "ifrs-full_InterestPaidClassifiedAsFinancingActivities"),
    ],
    "cf_operating":  [("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities")],
    "cf_investing":  [("CF", "ifrs-full_CashFlowsFromUsedInInvestingActivities")],
    "cf_financing":  [("CF", "ifrs-full_CashFlowsFromUsedInFinancingActivities")],
}


def _metric_sql(name: str) -> str:
    # COALESCE 는 첫 non-null 인자를 취한다 — 후보 우선순위가 SQL 텍스트 순서 그대로 보존된다.
    # 각 MAX(CASE...) 는 sj_div 까지 같이 걸어 다른 재무제표(특히 SCE)의 같은 account_id 재사용이
    # 섞여 들어오지 못하게 한다.
    parts = []
    for sj, account_id in METRIC_MAP[name]:
        sj_esc = sj.replace("'", "''")
        acct_esc = account_id.replace("'", "''")
        # 분기 IS 는 thstrm_add_amount(누계)를 우선한다 — 당분기만 쓰면 연간과 비교가 안 된다.
        parts.append(
            f"max(CASE WHEN a.sj_div = '{sj_esc}' AND a.account_id = '{acct_esc}' "
            f"THEN COALESCE(a.thstrm_add_amount, a.thstrm_amount) END)"
        )
    return f"COALESCE({', '.join(parts)}) AS {name}"


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
        ORDER BY f.stock_code, f.bsns_year, f.reprt_code,
                 f.rcept_dt DESC, f.rcept_no DESC, (f.fs_div = 'CFS') DESC
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
    all_ids = [account_id for pairs in METRIC_MAP.values() for (_sj, account_id) in pairs]
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
    matched = total - len(unmatched)
    return {"matched": matched, "total_stocks": total, "unmatched_count": len(unmatched),
            "unmatched_stocks": unmatched}
