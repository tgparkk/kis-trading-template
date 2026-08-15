# -*- coding: utf-8 -*-
"""KIS 과거 분봉 API 가 우리 창(2026-07-28~08-14)을 실제로 돌려주는지 «시험 호출».

🔴 이 스크립트는 이 디렉토리의 「라이브 트리 import 0건」 관례를 **의도적으로 깬다.**
   `api/kis_chart_api.py` 를 쓰므로 KIS 인증 토큰과 `utils/logger.py` 를 건드린다.
   그래서 조건을 못박는다:
     - **봇이 안 도는 날에만** 실행할 것(토큰 충돌 방지). 재기동 예정 2026-08-18.
     - 호출은 **읽기 전용**이고 주문 API 는 import 하지 않는다.
     - 목적은 «되는지 확인»이지 수집이 아니다. 수집은 별도 스크립트로 분리한다.

판정 기준(먼저 적어둔다):
  - 🟢 가능: 7/28 같은 «가장 오래된» 날짜가 그 날짜의 봉을 돌려준다.
  - 🔴 불가: 빈 응답이거나, **폴백이 작동해 다른 날짜를 돌려준다**.
    ⚠️ `get_historical_minute_data` 는 실패 시 최대 `FALLBACK_MAX_DAYS` 일 «이전»으로
       조용히 폴백한다 ⇒ ***돌려받은 날짜를 반드시 대조해야 한다.*** 안 그러면
       「됐다」고 오판한다(요청 날짜 ≠ 응답 날짜).
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = BASE.parent.parent          # RoboTrader_template/
sys.path.insert(0, str(REPO))

PROBES = [
    ("199430", "20260728", "케이엔알시스템 · 가장 오래된 등록일"),
    ("413630", "20260730", "씨피시스템 · DB 에 분봉 없음"),
    ("0039P0", "20260806", "매드업 · 신형 종목코드(중간 영문)"),
]


def main() -> int:
    from api.kis_auth import auth                      # noqa: E402
    from api.kis_chart_api import get_historical_minute_data  # noqa: E402

    if not auth():
        print("🔴 KIS 인증 실패 — .env 확인")
        return 2

    ok = 0
    for code, date, note in PROBES:
        df = get_historical_minute_data(code, date)
        if df is None or df.empty:
            print(f"🔴 {code} {date} — 빈 응답 ({note})")
            continue
        cols = list(df.columns)
        # 🔑 폴백 탐지: 응답에 날짜 컬럼이 있으면 요청 날짜와 대조한다.
        datecol = next((c for c in cols if "date" in c.lower() or "일자" in c), None)
        got = sorted({str(v) for v in df[datecol]}) if datecol else ["(날짜컬럼 없음)"]
        match = "🟢 일치" if datecol and got == [date] else "🔴 불일치/미확인"
        print(f"{match}  {code} {date} — {len(df)}행 · 응답날짜 {got[:3]} · 컬럼 {cols[:6]} ({note})")
        if datecol and got == [date]:
            ok += 1
    print(f"\n요청 날짜와 «일치»한 건: {ok}/{len(PROBES)}")
    return 0 if ok == len(PROBES) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
