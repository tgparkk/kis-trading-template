"""TT 배선 «충실도» 검증 — 라이브 경로의 DT/D 비율이 백테스트와 같은가.

백테스트 1단계 실측(`RESULTS.md` §10-5 항목 12):
    D 트리거 55,239 · DT 트리거 8,915  ⇒  DT/D = 16.1%

같은 창(2024-03-13~2026-05-31) 안의 날짜들을 «라이브 스크리너 경로»로 돌려
같은 비율을 잰다. 크게 다르면 내가 배선한 TT 는 백테스트가 시험한 TT 가 아니다.

⚠️ 완전히 같은 수를 기대하면 안 된다 — 백테스트는 「그날 base_filter 통과 전체」를
   평가하고 라이브는 같은 집합을 쓰지만, 유니버스 스냅샷 생성 방식과 불가능봉 가드가
   다르다. 자릿수가 맞는지, 특히 «0 이 아닌지»를 본다.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # …/RoboTrader_template
sys.path.insert(0, str(ROOT))

envf = ROOT / ".env"
if envf.exists():
    for line in envf.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import logging  # noqa: E402
logging.disable(logging.WARNING)

from db.quant_daily_reader import QuantDailyReader  # noqa: E402
from strategies.minervini_volume_dryup.screener import (  # noqa: E402
    MinerviniVolumeDryupScreenerAdapter,
)

# 백테스트 창 §3 (PREREG) 안에서 고르게 뽑은 날짜.
DATES = [
    "2024-04-15", "2024-06-17", "2024-08-19", "2024-10-15", "2024-12-16",
    "2025-02-17", "2025-04-15", "2025-06-16", "2025-08-18", "2025-10-15",
    "2025-12-15", "2026-02-16", "2026-04-15", "2026-05-28",
]
BACKTEST_RATIO = 8915 / 55239  # 16.14%


def main() -> int:
    qr = QuantDailyReader()
    tot_d = tot_tt = 0
    rows = []
    print(f"{'date':<12}{'univ':>6}{'eval':>6}{'220봉':>7}{'rs':>6}"
          f"{'dryup(D)':>10}{'TT통과(DT)':>12}{'DT/D':>9}")
    print("-" * 70)
    for ds in DATES:
        d = date.fromisoformat(ds)
        ad = MinerviniVolumeDryupScreenerAdapter()
        p = {**ad.default_params(), "tt_filter_mode": "shadow"}
        try:
            ad.scan(d, p)
        except Exception as exc:  # noqa: BLE001
            print(f"{ds:<12}  !! {type(exc).__name__}: {exc}")
            continue
        t, rs = ad._tally, ad._rs_diag
        n_d = t.get("n_dry", 0)
        n_tt = t.get("n_tt", 0)
        tot_d += n_d
        tot_tt += n_tt
        ratio = (n_tt / n_d * 100) if n_d else float("nan")
        rows.append((ds, n_d, n_tt))
        print(f"{ds:<12}{rs.get('n_input',0):>6}{t.get('n_eval',0):>6}"
              f"{t.get('n_bars_ok',0):>7}{rs.get('n_rs',0):>6}"
              f"{n_d:>10}{n_tt:>12}{ratio:>8.1f}%")

    print("-" * 70)
    live_ratio = tot_tt / tot_d if tot_d else 0.0
    print(f"{'합계':<12}{'':>6}{'':>6}{'':>7}{'':>6}{tot_d:>10}{tot_tt:>12}"
          f"{live_ratio*100:>8.1f}%")
    print()
    print(f"백테스트 DT/D  = {BACKTEST_RATIO*100:.1f}%  (55,239 → 8,915)")
    print(f"라이브   DT/D  = {live_ratio*100:.1f}%  ({tot_d:,} → {tot_tt:,})")
    if tot_d == 0:
        print("\n❌ dryup 트리거가 0 — 유니버스 스냅샷이 이 날짜에 없을 수 있다")
        return 2
    if tot_tt == 0:
        print("\n❌ TT 통과가 «0» — 배선이 끊겼다(220봉 또는 rs_value 미공급)")
        return 1
    rel = live_ratio / BACKTEST_RATIO
    print(f"비 = {rel:.2f}배")
    if 0.5 <= rel <= 2.0:
        print("\n✅ 자릿수 일치 — 라이브 TT 가 백테스트 TT 와 같은 룰로 동작한다고 볼 근거")
    else:
        print("\n⚠️ 비율이 2배 이상 벌어졌다 — 배선 차이를 규명해야 한다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
