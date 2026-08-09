# -*- coding: utf-8 -*-
"""[1]·[35] 초기 매매일지 + [32] 증분 전수 수집 (2026-08-09).

## 왜 이 스크립트가 생겼나

`CLOSING.md` §2.3 이 [28]·[29] 를 「전수」로 갱신하면서도 *「블로그의 나머지 카테고리는
여전히 미수집이다」* 를 미해소로 남겨 뒀다. 2026-08-09 에 카테고리 트리를 실제로 열어 보니
남은 것이 잡담이 아니라 **매매일지**였다:

    [ 1] 일상 및 잡담론   89건  2009-05-25 ~ 2019-05-07
    [35] 과거 기록        80건  2014-01-06 ~ 2016-12-30   ← [1] 의 **완전 부분집합**
    [32] 트레이딩 기록   859건  2017-01-13 ~ 2026-08-07   ← 라벨 858건의 원천

🔴 **[32] 의 「전수 858건」은 저자 매매일지의 전부가 아니었다.** [32] 는 2017-01 에 시작하고
   그 앞 3년(2014-01~2016-12)의 주차별 매매일지가 [1]/[35] 에 있다. logNo 교집합 0건,
   기존 수집분(`tasso_postlist.json` 858)과도 교집합 0건 — **89건 전부 미수집**이다.

## 이 스크립트가 하는 것과 하지 않는 것

- 한다: 89건 + [32] 증분 1건의 **본문 HTML·평문 저장 + 수신 판정 메타 기록**.
- 안 한다: 라벨 추출·해석. 그건 별도 단계다. 여기서 판정을 섞으면 「수집 실패」와
  「추출 실패」가 한 숫자에 섞인다.

## 지키는 계약 (선행 사고에서 온 것들)

1. 경로는 `cat2829_common` 의 절대경로만 쓴다. cwd 상대경로로 29건이 사라진 적이 있다.
2. 본문 수신 판정은 `classify_body` 로 **구조**로 한다. 마커 존재로 판정하면 본문 0자가
   「이미지 전용」으로 위장한다(195건 실측).
3. 실패는 **조용히 넘어가지 않고** `harvest_fail_early.json` 에 남기고 종료코드로 알린다.
4. 회수율은 **독립 목록**(카테고리 API)과 대조해서 잰다. 놓친 항목은 산출물에 흔적을 안 남긴다.
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cat2829_common as C  # noqa: E402

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

POSTS_DIR = C.HARVEST / "posts_early"
TEXT_DIR = C.HARVEST / "text_early"
CATLIST_JSON = C.HARVEST / "catlist_early.json"
POSTMETA_JSON = C.HARVEST / "postmeta_early.json"
FAIL_JSON = C.HARVEST / "harvest_fail_early.json"

# [1] 이 [35] 를 포함하므로 [1] 만 돌면 89건 전부가 나온다. [35] 는 **교차검증용**으로
# 따로 받아 포함관계를 매 실행마다 다시 확인한다 — 「부분집합이더라」는 관측이지 보장이 아니다.
SOURCE_CATS = (1, 35)
INCREMENT_CAT = 32          # 기존 수집분과 대조해 신규분만 받는다
PRIOR_POSTLIST = C.HARVEST / "tasso_postlist.json"


def category_posts(cat):
    """카테고리 글 목록 전수. (logNo -> {title, date}) — 목록 API 페이지네이션."""
    import datetime

    seen = {}
    for page in range(1, 60):
        d = C.api_json(cat, page)
        items = (d or {}).get("result", {}).get("items", [])
        fresh = [x for x in items if C.norm_log_no(x["logNo"]) not in seen]
        if not fresh:
            break
        for x in fresh:
            dt = datetime.datetime.fromtimestamp(x["addDate"] / 1000)
            seen[C.norm_log_no(x["logNo"])] = {
                "title": x.get("titleWithInspectMessage") or x.get("title", ""),
                "date": dt.strftime("%Y-%m-%d"),
                "smart_editor_version": x.get("smartEditorVersion"),
                "category": cat,
            }
        time.sleep(0.4)
    return seen


def prior_log_nos():
    """기존 [32] 수집분 858건. 없으면 빈 집합(그러면 증분 판정을 하지 않는다)."""
    if not PRIOR_POSTLIST.exists():
        return set()
    import re
    raw = PRIOR_POSTLIST.read_text(encoding="utf-8")
    return set(re.findall(r"\b(2\d{11})\b", raw))


def main() -> int:
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)

    cats = {c: category_posts(c) for c in SOURCE_CATS}
    s1, s35 = set(cats[1]), set(cats[35])
    print(f"[1]={len(s1)} [35]={len(s35)} · [35]⊂[1]={s35 <= s1} · 합집합={len(s1 | s35)}")
    if not s35 <= s1:
        print("🔴 포함관계가 깨졌다 — [35] 단독 항목:", sorted(s35 - s1))

    catalog = dict(cats[1])
    for k, v in cats[35].items():
        catalog.setdefault(k, v)
        catalog[k]["in_cat35"] = True

    # [32] 증분
    prior = prior_log_nos()
    inc = {}
    if prior:
        c32 = category_posts(INCREMENT_CAT)
        inc = {k: v for k, v in c32.items() if k not in prior}
        print(f"[32]={len(c32)} · 기존 수집 {len(prior)} · 증분 {len(inc)}")
        catalog.update(inc)
    else:
        print("⚠️ tasso_postlist.json 없음 — [32] 증분 판정 생략")

    CATLIST_JSON.write_text(json.dumps(catalog, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(f"\n수집 대상 {len(catalog)}건 → 본문 수집 시작")

    meta, fails = {}, []
    for i, (log_no, info) in enumerate(sorted(catalog.items(),
                                              key=lambda kv: kv[1]["date"]), 1):
        src = C.fetch_html(log_no)
        text = C.html_to_text(src)
        cls = C.classify_body(src, text)
        imgs = C.body_images(src)
        (POSTS_DIR / f"{log_no}.html").write_text(src, encoding="utf-8")
        (TEXT_DIR / f"{log_no}.txt").write_text(text, encoding="utf-8")
        kinds = {}
        for im in imgs:
            kinds[im["kind"]] = kinds.get(im["kind"], 0) + 1
        row = dict(info)
        row.update(cls)
        row.update({
            "log_no": log_no,
            "chars": len(text),
            "lines": len(text.splitlines()),
            "img_slots": len(imgs),
            "img_kinds": kinds,
            "page_editor_version": C.page_editor_version(src),
            "source_endpoint": C.detect_source(src),
            "html_bytes": len(src),
        })
        meta[log_no] = row
        if cls["body_missing"]:
            fails.append({"log_no": log_no, "title": info["title"],
                          "date": info["date"], "reason": "body_missing",
                          "container": cls["body_container"],
                          "html_bytes": len(src)})
        if i % 10 == 0 or i == len(catalog):
            print(f"  {i}/{len(catalog)} · 실패 {len(fails)}")
        time.sleep(0.5)

    POSTMETA_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    FAIL_JSON.write_text(json.dumps(fails, ensure_ascii=False, indent=1),
                         encoding="utf-8")

    # ── 회수율 검증 (V1) ──────────────────────────────────────────────────────
    ok = [m for m in meta.values() if not m["body_missing"]]
    print(f"\n=== V1 회수율 ===")
    print(f"  목록 {len(catalog)} · 저장 {len(meta)} · 본문 수신 {len(ok)} · 실패 {len(fails)}")
    vers = {}
    for m in meta.values():
        key = (m["body_container"], m["page_editor_version"])
        vers[key] = vers.get(key, 0) + 1
    print("  컨테이너/에디터:", {f"{a}/{b}": c for (a, b), c in sorted(vers.items(),
                                                                 key=lambda x: str(x[0]))})
    mism = [m["log_no"] for m in meta.values()
            if m["smart_editor_version"] is not None
            and m["page_editor_version"] is not None
            and int(m["smart_editor_version"]) != int(m["page_editor_version"])]
    print(f"  에디터 버전 교차대조 불일치: {len(mism)}건 {mism[:5]}")
    if fails:
        print("\n🔴 본문 미수신:")
        for f in fails:
            print(f"   {f['date']} {f['title'][:50]} · {f['container']} · {f['html_bytes']}B")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
