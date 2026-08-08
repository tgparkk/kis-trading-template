"""P(3) 패널 결합 + 진단 — Phase 2B 가 검정 가능한지 여기서 판정한다.

읽기 전용. DB 접근 0 · DART 호출 0.

🔑 이 파일의 «진짜» 산출물은 parquet 이 아니라 리포트다. 배제 필터를 검정하려면
   배제될 관측이 충분히 있어야 하고, 그게 없으면 Phase 2B 는 설계할 값어치가 없다.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/p3_panel.py
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_client import OUT_DIR  # noqa: E402
from p1_target import TARGET_PARQUET  # noqa: E402
from p2_features import FEATURES_PARQUET  # noqa: E402

PANEL_PARQUET = os.path.join(OUT_DIR, "frf_panel.parquet")
REPORT_TXT = os.path.join(OUT_DIR, "frf_panel_report.txt")


def usable(df):
    """창이 완결됐고 재무가 붙은 관측만. 원본을 건드리지 않는다."""
    return df[df["window_full"].fillna(False) & df["bsns_year"].notna()].copy()


def monthly_rates(df):
    if len(df) == 0:
        return pd.DataFrame(columns=["ym", "n", "crash_rate"])
    g = df.assign(ym=df["date"].str[:7]).groupby("ym")["crash"]
    return g.agg(n="size", crash_rate="mean").reset_index()


def main():
    tgt = pd.read_parquet(TARGET_PARQUET)
    feat = pd.read_parquet(FEATURES_PARQUET)
    panel = tgt.merge(feat.drop(columns=["from_date"], errors="ignore"),
                      on=["stock_code", "date"], how="left")
    panel.to_parquet(PANEL_PARQUET, index=False)

    u = usable(panel)
    lines = []
    lines.append(f"패널 {len(panel):,}행 · 종목 {panel['stock_code'].nunique():,}")
    lines.append(f"사용 가능(창 완결 ∧ 재무 매칭) {len(u):,}행 "
                 f"({100*len(u)/max(len(panel),1):.2f}%) · 종목 {u['stock_code'].nunique():,}")
    lines.append("")
    lines.append(f"기저 폭락률 {100*u['crash'].mean():.2f}%")
    lines.append("")
    lines.append("연속 축의 «분포» — 문턱을 제시하지 않는다")
    lines.append("  🔑 후보 문턱을 여기 찍으면 리포트를 읽은 사람이 그 값에 끌린다.")
    lines.append("     분위수만 보여주고 문턱 선택은 Phase 2B 의 PREREG 로 넘긴다.")
    for col in ("debt_ratio", "interest_coverage"):
        s = u[col].dropna()
        if len(s) == 0:
            lines.append(f"  {col:<18s} 값 없음")
            continue
        q = s.quantile([0.01, 0.05, 0.50, 0.95, 0.99])
        lines.append(f"  {col:<18s} n={len(s):>9,}  "
                     f"p01={q.loc[0.01]:9.3f} p05={q.loc[0.05]:9.3f} "
                     f"p50={q.loc[0.50]:9.3f} p95={q.loc[0.95]:9.3f} "
                     f"p99={q.loc[0.99]:9.3f}")
    ol = u["op_loss_years"].fillna(0)
    lines.append(f"  op_loss_years      분포 { {int(k): int(v) for k, v in ol.value_counts().sort_index().items()} }")
    lines.append("")
    lines.append("국면 진폭 (월별 폭락률, 창 완결분):")
    mr = monthly_rates(u)
    lines.append(f"  최소 {100*mr['crash_rate'].min():.2f}% · "
                 f"최대 {100*mr['crash_rate'].max():.2f}% · 월 {len(mr)}개")
    lines.append("")
    lines.append("🔑 Phase 2B 진행 판정 — 블록이 몇 개 생기는가:")
    lines.append("   관측 수가 아니라 «종목 수»를 본다. 블록 SE 의 블록이 종목이고,")
    lines.append("   관측 3만 개가 종목 20개에서 나왔다면 사실상 n=20 이다.")
    lines.append("   ⚠️ 아래 꼬리 마스크는 «분위수» 기반이라 후보 문턱을 제시하지 않는다.")
    # 🔴 fillna(False) 로 결측(자본총계를 못 읽음)을 채우면 「모른다」가 「비잠식(클린)」이
    #    된다 — p2_features.py 에서 두 라운드 전 제거된 것과 같은 결함이 마스크 계층에서
    #    재발한 것이다(279행 · 종목 2). 이 표는 잠식군만 세지만, Phase 2B 가 이 표현을
    #    그대로 복사해 대조군(비잠식)을 `~mask` 로 만들면 결측이 조용히 대조군에 들어간다.
    #    eq(True) 는 결측을 True 도 False 도 아닌 「선택 안 됨」으로만 두어 결측이
    #    양쪽(잠식군·비잠식군) 어디에도 «클린»으로 계상되지 않게 한다.
    masks = [("자본잠식(모수없음)", u["equity_impaired"].eq(True))]
    for col, tail in (("debt_ratio", "hi"), ("interest_coverage", "lo")):
        s = u[col]
        for p in (0.01, 0.05):
            if s.notna().sum() == 0:
                continue
            cut = s.quantile(1 - p if tail == "hi" else p)
            m = s.gt(cut) if tail == "hi" else s.lt(cut)
            masks.append((f"{col} {tail} {int(p*100)}%", m.fillna(False)))
    for p in (0.01, 0.05):
        cut = ol.quantile(1 - p)
        masks.append((f"op_loss_years hi {int(p*100)}%", ol.gt(cut)))
    for name, mask in masks:
        sub = u[mask]
        lines.append(f"   {name:<26s} 관측 {len(sub):>9,} · 종목 "
                     f"{sub['stock_code'].nunique():>5,}")
    lines.append("")
    lines.append("   이 표는 문턱을 고르는 데 쓰지 않는다 — 그러면 사후 선택이다.")
    lines.append("   축의 «검정 가능성»만 본다.")

    text = "\n".join(lines)
    with open(REPORT_TXT, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)
    print(f"\n→ {PANEL_PARQUET}\n→ {REPORT_TXT}")


if __name__ == "__main__":
    main()
