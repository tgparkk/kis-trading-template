"""N_cut 근거표 · 제외 테마 목록(스펙 §4-2) — 결과 없음 · DB SELECT 전용.

    python -X utf8 -m backtest.concept_axes.theme_rank.ncut_evidence

출력 `results/NCUT_EVIDENCE.md`: theme_no ≥ 500 테마의 이름·크기·설명 앞 120자·설명에 나온 연도들 + 사건형 제외 목록.
PREREG 작성자가 표를 읽고 「설명이 2024-03-13 이후 사건을 다루는 첫 번호」를 N_cut 으로 고른다(애매하면 작은 번호).
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import re                                                              # noqa: E402
from pathlib import Path                                               # noqa: E402

from backtest.concept_axes.candidate_ledger import run as CL           # noqa: E402
from backtest.concept_axes.theme_rank import membership as MB          # noqa: E402
from backtest.concept_axes.theme_rank import snapshot as SN            # noqa: E402

OUT = Path(__file__).resolve().parent / "results" / "NCUT_EVIDENCE.md"
FROM_NO = 500


def main() -> int:
    conn = CL._connect()
    snap = SN.load_snapshot(conn, MB.SNAP_DATE)
    cur = conn.cursor()
    cur.execute("SELECT theme_no, description FROM theme_daily WHERE snap_date = %s", (MB.SNAP_DATE,))
    desc = {int(t): (d or "") for t, d in cur.fetchall()}
    conn.close()
    lines = [f"# N_cut 근거표 — 스냅샷 {MB.SNAP_DATE} · theme_no ≥ {FROM_NO}", "",
             "| theme_no | 이름 | 크기 | 설명 속 연도 | 설명(앞 120자) |", "|---|---|---|---|---|"]
    for t in sorted(x for x in snap.theme_name if x >= FROM_NO):
        years = sorted(set(re.findall(r"20[0-2]\d", desc.get(t, ""))))
        text = desc.get(t, "").replace("|", "/").replace("\n", " ")[:120]
        lines.append(f"| {t} | {snap.theme_name[t]} | {len(snap.members[t])} | {','.join(years)} | {text} |")
    ex = sorted(MB.excluded_themes(snap.theme_name))
    lines += ["", f"## 사건·분류형 제외({len(ex)}개 · 패턴 {MB.EXCLUDED_NAME_PATTERNS})", ""]
    lines += [f"- {t} {snap.theme_name[t]} ({len(snap.members[t])})" for t in ex]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"출력 → {OUT} · 테마 {len(snap.theme_name)} · 표 {sum(1 for x in snap.theme_name if x >= FROM_NO)}행 · 제외 {len(ex)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
