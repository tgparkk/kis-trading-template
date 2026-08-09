# -*- coding: utf-8 -*-
"""초기 매매일지([1]/[35], 2014~2016) + [32] 증분에서 **매매 항목 원장**을 만든다.

## 이 원장이 [28]·[29] 주장 원장과 다른 점

`claims_cat2829.csv` 의 단위는 **「주장」**이라 종목 컬럼이 아예 없다. 그래서
*「글을 더 읽어도 라벨이 한 행도 안 늘어난다」*(CLOSING §2.3)가 참이었다.
이 카테고리는 단위가 **「한 종목의 한 주차 매매」**다. 저자가 본문에 직접 이렇게 적는다:

    1. 제일모직 / 수급주 상승 베팅 / 수익률 16.83%
    2. 아이씨디 / 직전고 돌파 / 수급평단 박스권 베팅 / 수익률 2.72%, 2.74%, 3.38%

⇒ 종목·기법·결과가 한 줄에 있다. **이건 라벨이다.**

## 회수율을 어떻게 재는가 — 저자의 번호가 독립 목록이다

🔑 구조화 추출의 회수율은 **독립적으로 얻은 목록과 대조**해서 재야 한다. 놓친 항목은
   산출물에 흔적을 남기지 않는다(v1 헤더 정규식이 번호 없는 항목을 통째로 누락한 사고).
   여기서는 **저자가 스스로 매긴 항목 번호**가 그 독립 목록 역할을 한다 —
   글 안에서 번호가 `1..N` 으로 연속하지 않으면 **우리가 놓친 것**이다.
   이 게이트를 통과 못 하면 스크립트는 종료코드 1 을 낸다.

## 값 공개 정책 (CLOSING §5)

- **공개판** `journal_items_early.csv` = 구조화 필드만(종목·기법·수익률 수치).
  `claims_schema.PUBLIC_COLUMNS` 와 같은 원칙 — **원문 문장을 열에 담지 않는다.**
- **로컬판** `journal_items_early_quoted.csv` = 항목 줄 원문 포함. `.gitignore` 로 차단한다
  (`claims_cat2829_quoted.csv`·`img_claims_28_29_quoted.csv` 와 같은 2층 경계).

## 🔴 소스의 데이터 품질 — 부호 규약이 일정하지 않다

저자는 손실을 두 방식으로 적는다(둘 다 실측):
    `손실률 0.83%`      ← 부호 없음. 「손실률」이라는 낱말이 부호다.
    `손실률 -1.81%`     ← 부호 있음
⇒ 손실은 **크기(abs)로 저장**하고 방향은 `result_kind` 열이 갖는다. 원문 토큰도 같이 남긴다.
   숫자에 그냥 부호를 붙이면 `-(-1.81)` 로 뒤집히는 행이 생긴다.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cat2829_common as C  # noqa: E402

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

POSTMETA = C.HARVEST / "postmeta_early.json"
TEXT_DIR = C.HARVEST / "text_early"
LEDGER_PUBLIC = C.HARVEST / "journal_items_early.csv"
LEDGER_QUOTED = C.HARVEST / "journal_items_early_quoted.csv"
RECALL_LOG = C.HARVEST / "journal_recall_early.log"

# `N. 종목명 / …` — 항목 헤더.
#
# 🔴 초판은 마침표만 허용했다(`\s*\.\s*`). 쉼표를 막은 이유는 `135,000원 부근까지…` 류
#    산문을 걸러내려던 것인데, **저자가 항목 하나에 쉼표를 찍었다**:
#        `2, SKC / 추세돌파 / 수급 평단 박스권 베팅 / 수익률 0.29%, 1.44%`
#    항목이 조용히 사라졌고 **번호 연속성 게이트(아래)가 `found=[1,3] missing=[2]` 로 잡았다.**
#    ⇒ 이 게이트가 없었으면 원장은 308행으로 초록불이었을 것이다.
#
# 🔑 그래서 구분자를 넓히되 **판별을 다른 축이 지게** 한다 — 산문 오탐 19건은 전부
#    `/` 가 없다(실측). 구분자가 아니라 **슬래시 구조**가 항목의 정의다.
#    실측 구분자 분포: `.` 301 · `,` 1 · 공백 1. 헐거운 탐지기(숫자시작+슬래시+결과어)와
#    대조했을 때 차집합은 위 SKC 한 줄뿐이었다.
HEAD = re.compile(r"^\s*(\d{1,2})\s*[.,]\s*([^/]{1,30}?)\s*/(.*)$")
RESULT_KW = re.compile(r"(수익률|손실률)")
PCT = re.compile(r"-?\d+(?:\.\d+)?\s*%")

PUBLIC_COLUMNS = ("log_no", "post_date", "category", "item_no", "stock_name",
                  "techniques", "n_technique", "gain_pcts", "loss_pcts",
                  "n_gain", "n_loss", "result_kind")
QUOTED_COLUMNS = PUBLIC_COLUMNS + ("line",)


def parse_results(tail):
    """`수익률 …` / `손실률 …` 구획별로 % 토큰을 나눈다. (gains, losses) — 둘 다 abs 값."""
    gains, losses = [], []
    parts = RESULT_KW.split(tail)
    # parts = [머리, 키워드, 본문, 키워드, 본문, ...]
    for i in range(1, len(parts) - 1, 2):
        kw, seg = parts[i], parts[i + 1]
        vals = [abs(float(t.replace("%", "").strip())) for t in PCT.findall(seg)]
        (gains if kw == "수익률" else losses).extend(vals)
    return gains, losses


def main() -> int:
    meta = json.loads(POSTMETA.read_text(encoding="utf-8"))
    rows, gaps, no_item = [], [], []

    for log_no, m in sorted(meta.items(), key=lambda kv: kv[1]["date"]):
        text = (TEXT_DIR / f"{log_no}.txt").read_text(encoding="utf-8")
        seen_nos = []
        for ln in text.splitlines():
            hd = HEAD.match(ln.strip())
            if not hd:
                continue
            item_no, stock, tail = int(hd.group(1)), hd.group(2).strip(), hd.group(3)
            # 기법 필드 = 결과 키워드 앞까지의 슬래시 구획
            cut = RESULT_KW.split(tail)[0]
            techs = [t.strip(" ,.·") for t in cut.split("/") if t.strip(" ,.·")]
            gains, losses = parse_results(tail)
            if not techs and not gains and not losses:
                continue          # 슬래시 하나짜리 산문 — 항목이 아니다
            seen_nos.append(item_no)
            kind = ("mixed" if gains and losses else
                    "gain" if gains else "loss" if losses else "none")
            rows.append({
                "log_no": log_no, "post_date": m["date"], "category": m["category"],
                "item_no": item_no, "stock_name": stock,
                "techniques": " / ".join(techs), "n_technique": len(techs),
                "gain_pcts": ";".join(f"{v:g}" for v in gains),
                "loss_pcts": ";".join(f"{v:g}" for v in losses),
                "n_gain": len(gains), "n_loss": len(losses), "result_kind": kind,
                "line": ln.strip(),
            })
        if not seen_nos:
            no_item.append((m["date"], m["title"]))
            continue
        # ── 회수율 게이트: 저자 번호가 1..N 연속인가 ────────────────────────────
        uniq = sorted(set(seen_nos))
        expect = list(range(1, max(uniq) + 1))
        missing = [n for n in expect if n not in uniq]
        if missing:
            gaps.append({"log_no": log_no, "date": m["date"], "title": m["title"],
                         "found": uniq, "missing": missing})

    for path, cols in ((LEDGER_QUOTED, QUOTED_COLUMNS), (LEDGER_PUBLIC, PUBLIC_COLUMNS)):
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    lines = []
    lines.append(f"글 {len(meta)} · 항목 {len(rows)}")
    lines.append(f"항목 0개인 글 {len(no_item)}건 (잡담·출간·이슈 등)")
    for d, t in no_item:
        lines.append(f"  0items {d} {t[:60]}")
    lines.append(f"\n=== 회수율 게이트: 항목 번호 연속성 ===")
    lines.append(f"번호 결번이 있는 글: {len(gaps)}건")
    for g in gaps:
        lines.append(f"  GAP {g['date']} {g['title'][:45]} found={g['found']} missing={g['missing']}")
    yr = Counter(r["post_date"][:4] for r in rows)
    lines.append(f"\n연도별 항목: {dict(sorted(yr.items()))}")
    names = Counter(r["stock_name"] for r in rows)
    lines.append(f"고유 종목명 {len(names)} · 상위 10 {names.most_common(10)}")
    lines.append(f"결과 유형: {dict(Counter(r['result_kind'] for r in rows))}")
    lines.append(f"체결 토큰: 수익 {sum(r['n_gain'] for r in rows)} · 손실 {sum(r['n_loss'] for r in rows)}")
    out = "\n".join(lines)
    RECALL_LOG.write_text(out + "\n", encoding="utf-8")
    print(out)
    return 1 if gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
