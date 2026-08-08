"""F(1) 수집 작업목록 산출 — (stock_code, corp_code, bsns_year).

읽기 전용. DART 호출 0건.

corp_code 는 `stock_industry`(2026-08-07 적재, 커버리지 100%/2,556종목)에서 가져온다.
⚠️ 우선주 36종목은 corp_code 매핑이 구조적으로 불가하므로 여기서 자동 제외된다.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f1_worklist.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_client import OUT_DIR, db_conn  # noqa: E402

# 🔑 2019 부터인 이유: 타겟 시작이 2021-01-04 이고, 그 시점에 공개돼 있던 최신
#    연간재무는 2019 사업연도 보고서(2020-03 접수)다. 2020 사업연도는 2021-03 에나
#    접수되므로 2021-01~03 구간이 비게 된다.
YEARS = ["2019", "2020", "2021", "2022", "2023", "2024", "2025"]

WORKLIST_JSONL = os.path.join(OUT_DIR, "f1_worklist.jsonl")

UNIVERSE_SQL = """
SELECT si.stock_code, si.corp_code
FROM stock_industry si
WHERE si.corp_code IS NOT NULL AND si.corp_code <> ''
  AND si.stock_code IN (
      SELECT DISTINCT stock_code FROM daily_prices
      WHERE stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11')
  )
"""


def build_worklist(rows, years):
    """(stock_code, corp_code) 목록 × 연도 → 결정적 순서의 작업목록."""
    out = []
    for code, corp in sorted(rows):
        if not corp:
            continue
        for y in sorted(years):
            out.append({"stock_code": code, "corp_code": corp, "bsns_year": y})
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(UNIVERSE_SQL)
    # ⚠️ str(None) == "None" 은 진리값이 True 라 build_worklist 의 `if not corp`
    #    가드를 그대로 통과한다. SQL 이 이미 NULL 을 막고 있지만, 두 겹 중
    #    파이썬 쪽만 남는 날 조용히 샌다. None 은 None 으로 넘긴다.
    rows = [(str(a), None if b is None else str(b)) for a, b in cur.fetchall()]
    cur.close()
    conn.close()

    wl = build_worklist(rows, YEARS)
    with open(WORKLIST_JSONL, "w", encoding="utf-8") as f:
        for item in wl:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"종목 {len(rows)} × 연도 {len(YEARS)} = 작업 {len(wl)}건")
    print(f"→ {WORKLIST_JSONL}")


if __name__ == "__main__":
    main()
