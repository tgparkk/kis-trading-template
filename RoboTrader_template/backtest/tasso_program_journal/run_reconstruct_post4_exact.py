# -*- coding: utf-8 -*-
"""C-22 · post4 복원을 **정확 구간법(A-11)으로 재계산** — 잣대 정합용 «병기» 산출물.

사전등록: `PREREG_POST6.md` §5-6 (`RESULTS_RECONSTRUCT_POST5.md` §10 A-11 을 받은 결정)

> *「post4 의 feasible 「개수·폭」과 **Y3 의 1/6** 은 점법으로 계산됐고, 점법 해집합 ⊆ 정확 해집합이므로
>  post4 를 정확법으로 다시 풀면 그 1건이 사라질 수 있다. ⇒ 「1/6 → 4/6」은 잣대가 다른 비교다.」*

🔴 **post4 의 «판정»은 바꾸지 않는다.** `RESULTS_RECONSTRUCT_POST4_NUMBERS.md` 는 **손대지 않는다** —
   발표값은 발표값으로 두고 이 파일이 **옆에 열을 병기**한다(§5-6).

🔴 **열이 «셋»인 이유** — §5-6 은 「정확법 재계산 열」만 요구하지만, 발표값(2026-08-22 스냅샷·점법)과
   오늘의 정확법을 «두 열»로만 놓으면 **「방법이 바뀐 몫」과 「DB 스냅샷이 움직인 몫」이 한 칸에 섞인다.**
   (`RESULTS_SELECTION_POST5.md` §0 이 사람 손으로 적어야 했던 그 이동이다.) 그래서
   **오늘 점법**을 가운데 열로 넣어 두 축을 가른다. 🔑 *숫자가 문서마다 다르면 «원인 규명»이 먼저다 —
   맞추지 말 것.* 이 열은 «맞추기»가 아니라 **가르기**다.

- 왼쪽 열은 **재계산하지 않는다** — `RESULTS_RECONSTRUCT_POST4_NUMBERS.md` 의 표를 **그대로 읽어** 옮긴다.
- 창·대상·레그는 `run_reconstruct_post4.TARGETS` 동결분 그대로. 새 자유도 0.

라이브 트리 import 0건. DB 는 SELECT 만. `adj_factor` 산술 0건.
"""
from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

import psycopg2

from reconstruct_prices import gross_ret
from run_reconstruct_post4 import TARGETS
from run_reconstruct_post5 import feasible_exact, feasible_pointwise, iv_max, iv_measure, iv_min
from run_tests import DSN

BASE = Path(__file__).resolve().parent
PUBLISHED = BASE / "RESULTS_RECONSTRUCT_POST4_NUMBERS.md"
OUT: list[str] = []


def say(s=""):
    print(s)
    OUT.append(s)


def read_published():
    """발표된 §1 표를 **그대로** 읽는다(재계산 아님). 종목 -> {개수, P범위, b1범위, 폭}."""
    want = "feasible P 개수(gross)"
    rows, seen_header = {}, False
    for line in PUBLISHED.read_text(encoding="utf-8").splitlines():
        if want in line:
            seen_header = True
            continue
        if not seen_header:
            continue
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0].startswith("---"):
            continue
        rows[cells[0]] = {"n": cells[5], "P": cells[6], "b1": cells[7], "w": cells[8]}
    if not rows:
        raise SystemExit("발표 표를 못 읽었다: %s" % PUBLISHED.name)
    return rows


def num(s):
    """'**0.58%p**' -> 0.58 · '—' -> None."""
    m = re.search(r"-?\d+(?:\.\d+)?", s.replace(",", ""))
    return float(m.group()) if m else None


def main() -> int:
    pub = read_published()
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    say("# RESULTS_RECONSTRUCT_POST4_EXACT_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_reconstruct_post4_exact.py` · 재사용 `run_reconstruct_post5.py`"
        "(`feasible_exact`·`feasible_pointwise`) · 대상 `run_reconstruct_post4.TARGETS` 동결분")
    say("사전등록 `PREREG_POST6.md` §5-6 (C-22) · 근거 `RESULTS_RECONSTRUCT_POST5.md` §10 A-11\n")
    say("🔴 **이 문서는 post4 의 판정을 바꾸지 않는다.** `RESULTS_RECONSTRUCT_POST4_NUMBERS.md` 는 "
        "손대지 않았고, 여기 왼쪽 열은 그 파일에서 **그대로 읽어 온 발표값**이다.\n")
    say("🔴 **라이브 채택 금지** — 이 문서의 어떤 숫자도 매매 규칙으로 옮기지 않는다.\n")

    cur.execute("SELECT max(date) FROM daily_prices")
    snap = cur.fetchone()[0]
    say(f"DB 스냅샷 최신 봉 **{snap}** (발표 당시 스냅샷은 2026-08-21~22 · "
        "`RESULTS_SELECTION_POST5.md` §0 이 적은 그 이동이 이 사이에 있다)\n")

    say("## §1. 세 열 대조 — 발표(점법) · 오늘(점법) · 오늘(정확법)\n")
    say("| 종목 | 레그 | 창 | **발표 개수/폭** | **오늘 점법 개수/폭** | "
        "**오늘 정확법 구간수/폭** | 정확법 P 범위 | 정확법 측도(원) | 해 0개? |")
    say("|---|---|---|---|---|---|---|---|---|")

    R = []
    for nm, code, d0, d1, legs, tr, typ in TARGETS:
        cur.execute(
            "SELECT date, open, high, low, close FROM daily_prices "
            "WHERE stock_code=%s AND date BETWEEN %s AND %s ORDER BY date", (code, d0, d1))
        rows = cur.fetchall()
        if not rows:
            say(f"| {nm} | {len(legs)} | {d0}~{d1} | — | **데이터 없음** | — | — | — | — |")
            continue
        h0 = rows[0][2]
        pts = feasible_pointwise(rows, legs, gross_ret)
        iv = feasible_exact(rows, legs, "gross")
        p_w = (max(pts) - min(pts)) / h0 * 100 if pts else None
        e_w = (iv_max(iv) - iv_min(iv)) / h0 * 100 if iv else None
        R.append(dict(nm=nm, legs=len(legs), pub=pub.get(nm), pts=pts, iv=iv,
                      p_w=p_w, e_w=e_w, h0=h0))
        say("| {nm} | {L} | {d0}~{d1} | {pn} / {pw} | {tn} / {tw} | {en} / {ew} | {pr} | {ms} | {z} |"
            .format(nm=nm, L=len(legs), d0=d0, d1=d1,
                    pn=(pub.get(nm) or {}).get("n", "—").replace("*", ""),
                    pw=(pub.get(nm) or {}).get("w", "—").replace("*", ""),
                    tn=len(pts), tw=("—" if p_w is None else f"{p_w:.2f}%p"),
                    en=len(iv), ew=("—" if e_w is None else f"{e_w:.2f}%p"),
                    pr=("—" if not iv else f"{iv_min(iv):,.2f}~{iv_max(iv):,.2f}"),
                    ms=("—" if not iv else f"{iv_measure(iv):,.2f}"),
                    z=("🔴 **정확법에서도 0**" if not iv else "아니오")))
    say()
    say("⚠️ **「개수」는 세 열 사이에서 비교 대상이 아니다** — 점법의 개수는 «해가 된 격자점 수»이고 "
        "정확법의 개수는 «구간 덩어리 수»다. 비교 가능한 것은 **폭**·**해 0개 여부**·**측도**뿐이다.")
    say()

    # ── §2. Y3 — 해 0개 비율 (잣대 정합의 본론) ──────────────────────────────
    pub_zero = [nm for nm, v in pub.items() if num(v["n"]) == 0]
    t_zero = [r["nm"] for r in R if not r["pts"]]
    e_zero = [r["nm"] for r in R if not r["iv"]]
    say("## §2. `REC-Y3` 잣대 정합 — 「해 0개 비율」\n")
    say("`RESULTS_RECONSTRUCT_POST4.md` §6 `REC-Y3`: *「해 0개 비율 ≥ 1/3 이면 복원 중단」*\n")
    say("| 잣대 | 해 0개 | 비율 | 건 |")
    say("|---|---|---|---|")
    say(f"| **발표(점법 · 08-22 스냅샷)** | {len(pub_zero)}/{len(pub)} | "
        f"{len(pub_zero)/len(pub)*100:.1f}% | {' · '.join(pub_zero) or '없음'} |")
    say(f"| 오늘 점법(현재 스냅샷) | {len(t_zero)}/{len(R)} | "
        f"{len(t_zero)/len(R)*100:.1f}% | {' · '.join(t_zero) or '없음'} |")
    say(f"| **오늘 정확법(A-11)** | {len(e_zero)}/{len(R)} | "
        f"{len(e_zero)/len(R)*100:.1f}% | {' · '.join(e_zero) or '없음'} |")
    say()
    say("🔑 **A-11 이 예고한 것**: *「점법 해집합 ⊆ 정확 해집합이므로 정확법으로 다시 풀면 "
        "그 1건이 사라질 수 있다」*. 위 표가 그 예고의 **판정**이다 — "
        + ("🔴 **사라지지 않았다**(정확법에서도 해가 0개다) ⇒ post5 의 4/6 과 "
           "**같은 잣대로 비교해도 된다.**" if set(e_zero) == set(pub_zero)
           else "🟢 **달라졌다** ⇒ post5 의 4/6 과 발표 1/6 은 **잣대가 다른 수열이었다.** "
                "다음 회차의 `REC-Y3` 비교는 이 열을 쓴다.") )
    say()
    say("🔴 **그래도 post4 의 발표 판정은 그대로 둔다**(§5-6). 이 표는 «잣대 정합용 숫자»이지 "
        "재판정이 아니다.")

    # ── §3. b₁ 폭 (Y1·Y2 의 잣대) ────────────────────────────────────────────
    say()
    say("## §3. `b₁` 구간 폭 — 점법은 «하한»이었나\n")
    say("| 종목 | 발표 폭 | 오늘 점법 폭 | **오늘 정확법 폭** | 정확법 ≥ 점법? |")
    say("|---|---|---|---|---|")
    ok_dir = []
    for r in R:
        pw = num(r["pub"]["w"]) if r["pub"] else None
        pub_s = "—" if pw is None else "%.2f%%p" % pw
        pt_s = "—" if r["p_w"] is None else "%.2f%%p" % r["p_w"]
        ex_s = "—" if r["e_w"] is None else "%.2f%%p" % r["e_w"]
        if r["e_w"] is None or r["p_w"] is None:
            mark = "—"
        else:
            good = r["e_w"] >= r["p_w"] - 1e-9
            ok_dir.append(good)
            mark = "✅" if good else "🔴 **아니다**"
        say("| %s | %s | %s | %s | %s |" % (r["nm"], pub_s, pt_s, ex_s, mark))
    ew = [r["e_w"] for r in R if r["e_w"] is not None]
    pw_all = [r["p_w"] for r in R if r["p_w"] is not None]
    say()
    if ew:
        say(f"- 정확법 폭: 최소 **{min(ew):.2f}%p** · 중앙 **{statistics.median(ew):.2f}%p** · "
            f"최대 **{max(ew):.2f}%p** (n={len(ew)})")
    if pw_all:
        say(f"- 오늘 점법 폭: 최소 **{min(pw_all):.2f}%p** · 중앙 "
            f"**{statistics.median(pw_all):.2f}%p** · 최대 **{max(pw_all):.2f}%p** (n={len(pw_all)})")
    say(f"- 방향 확인(정확 ⊇ 점): **{sum(ok_dir)}/{len(ok_dir)}** — "
        "A-11 이 *「점법 값은 전부 하한」*이라 한 것과 "
        + ("**일치**" if ok_dir and all(ok_dir) else "🔴 **불일치 — 원인 규명이 먼저다**"))
    say()
    say("- 발표 폭 중앙 **2.58%p**(분모 5·홀수)는 C-20 중앙값 정정으로도 **바뀌지 않는다** — "
        "「결함이 없었다」가 아니라 **「아직 발화하지 않았다」**이다(`PREREG_POST6.md` §5-4-2).")

    (BASE / "RESULTS_RECONSTRUCT_POST4_EXACT_NUMBERS.md").write_text(
        "\n".join(OUT) + "\n", encoding="utf-8")
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
