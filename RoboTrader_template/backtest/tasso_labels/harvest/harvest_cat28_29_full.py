# -*- coding: utf-8 -*-
"""[28] 주식기법 분석 · [29] 시황이슈 정리 — **전 범위** 수집.

🔴 구 harvest_cat28_29.py 와의 차이:
   ① 날짜 컷(CUT=2024-08-01) 없음 — 전 페이지를 끝까지 돈다
   ② 출력 경로가 cwd 상대가 아니라 cat2829_common 의 절대경로
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import datetime
import json
import time

import cat2829_common as C

MAX_PAGES = 60      # 282건/30 = 10페이지. 상한은 넉넉히 두되 닿으면 **중단**한다.
PAGE_SLEEP = 0.4
LIST_RETRIES = 3    # 목록 API 파싱 실패 시 재시도 횟수


def category_counts(payload):
    """카테고리 트리를 평탄화해 {categoryNo: postCnt} 를 만든다."""
    out = {}
    if not payload or not payload.get("isSuccess"):
        return out
    res = payload.get("result", {})
    items = (res.get("mylogCategoryList") or res.get("categories")
             or res.get("categoryList") or [])

    def walk(lst):
        for c in lst:
            no = c.get("categoryNo")
            if no is not None:
                out[no] = c.get("postCnt", c.get("count"))
            for k in ("subCategoryList", "children", "subCategories"):
                if c.get(k):
                    walk(c[k])

    walk(items)
    return out


def fetch_post_list(cat, fetch=None, sleep=None):
    """카테고리의 **전 페이지**를 돌아 {logNo: item} 을 만든다.

    🔑 날짜로 끊지 않는다. 종료 조건은 「새 logNo 가 하나도 없는 페이지」뿐이다.
    """
    fetch = fetch or C.api_json
    sleep = sleep if sleep is not None else time.sleep
    seen = {}
    for page in range(1, MAX_PAGES + 1):
        d = None
        for attempt in range(LIST_RETRIES):
            d = fetch(cat, page)
            if d is not None:
                break
            if attempt < LIST_RETRIES - 1:
                sleep(PAGE_SLEEP * (attempt + 1))
        if d is None:
            # 🔑 빈 목록으로 넘어가면 「글이 없다」와 구분되지 않는다.
            raise RuntimeError("LIST_API_FAILED: cat=" + str(cat) + " page=" + str(page))
        items = d.get("result", {}).get("items", [])
        # 🔴 정규화 지점 ① — 목록 API 는 logNo 를 int 로 준다. 여기서 str 로 고정해
        #    이후 전 경로(_stem·메타·V1 집합비교)가 같은 타입만 본다.
        fresh = [x for x in items if C.norm_log_no(x["logNo"]) not in seen]
        if not fresh:
            return seen
        for x in fresh:
            seen[C.norm_log_no(x["logNo"])] = x
        sleep(PAGE_SLEEP)
    raise RuntimeError(
        "MAX_PAGES(" + str(MAX_PAGES) + ") 도달 — 목록이 안 끝났다. "
        "조용한 절단을 막기 위해 중단한다. 상한을 올리고 재실행할 것.")


# 🔴 이 API 의 제목 필드명은 **불안정하다**. 같은 URL 의 두 관측이 서로 반대다:
#
#   2026-08-01 · `harvest_list.py:41-43` 이 가공 없이 저장한 tasso_postlist.json
#       키 **4개** ['addDate','categoryNo','logNo','title']
#       title 858/858 · titleWithInspectMessage **0건**
#   2026-08-05 · 같은 엔드포인트 라이브 1건 (categoryNo=28&itemCount=1&page=1)
#       키 **44개** (addDate…videoPlayTime)
#       title **없음** · titleWithInspectMessage 있음
#
# ⚠️ 어느 한쪽 스냅샷을 계약으로 못 박으면 반대편 시점에 조용히 빈 제목이 된다.
#    실제로 그렇게 두 번 틀렸다 — 옛 코드는 08-01 관측에서, 그 교정판은 08-05
#    라이브에서. 두 이름을 **모두** 받아들이는 것이 측정된 사실에 맞는 대응이다.
# 우선순위: title 이 먼저. 둘 다 있으면 title 을 쓴다.
TITLE_KEYS = ("title", "titleWithInspectMessage")


def item_title(item):
    """목록 항목의 제목. 알려진 두 키 중 **존재하고 값이 있는** 쪽을 쓴다.

    🔑 지키는 성질(이번에 실제로 작동한 부분이다): 아는 키가 **하나도 없으면**
       조용한 빈 문자열이 아니라 실제 키 목록과 함께 raise 한다. 스키마가 또
       바뀌면 432건을 제목 전부 빈 채로 수집하는 대신 첫 글에서 멈춘다.

    ⚠️ 값이 빈 제목은 **막지 않는다**(판단 근거는 아래). 키는 있는데 값만 비었다면
       그건 스키마 변화가 아니라 그 글의 성질일 수 있다. 글 하나 때문에 432건
       파이프라인을 죽이는 것은 I4 에서 고친 실패 방식과 같다. 대신 침묵하지도
       않는다 — main() 이 빈 제목 건수와 log_no 를 출력한다.
    """
    present = [k for k in TITLE_KEYS if k in item]
    if not present:
        raise RuntimeError(
            "LIST_ITEM_NO_TITLE: 목록 항목에 제목 키가 없다 — API 스키마가 바뀌었다. "
            "찾은 키=" + repr(TITLE_KEYS) + " · 실제 keys=" + repr(sorted(item.keys())))
    for key in present:
        value = item[key]
        if value is not None and str(value).strip():
            return value
    return ""


def build_catalog():
    """카테고리별 목록 + postCnt 를 모아 CATLIST_JSON 으로 쓴다."""
    counts = category_counts(C.category_list())
    catalog = {"fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
               "post_cnt": {}, "posts": {}}
    for cat in C.CATEGORIES:
        listing = fetch_post_list(cat)
        catalog["post_cnt"][str(cat)] = counts.get(cat)
        for log_no, item in listing.items():
            # 🔴 정규화 지점 ② — 이 딕셔너리는 JSON **객체**로 직렬화되므로 키가
            #    재적재 후 반드시 str 이 된다. 값(log_no)도 같은 타입이어야
            #    V1 의 집합 비교가 성립한다.
            log_no = C.norm_log_no(log_no)
            dt = datetime.datetime.fromtimestamp(item["addDate"] / 1000)
            catalog["posts"][log_no] = {
                "log_no": log_no,
                "category": cat,
                "post_date": dt.strftime("%Y-%m-%d"),
                "add_date_ms": item["addDate"],
                "title": item_title(item),
                # 🔑 2026-08-05 라이브 응답에서 발견 — 목록 API 가 **글별 에디터 세대**를
                #    준다(실측값 4 = SmartEditor ONE). C2 의 본문 컨테이너 판정
                #    (se3/se2/none)을 **독립 경로로 대조**할 수 있는 유일한 재료다.
                #    여기서 안 담으면 나중에 대조하려고 432건 목록을 다시 받아야 한다.
                # ⚠️ 분류에는 **쓰지 않는다** — 순수 기록이다. title 과 달리 없어도
                #    조용히 None 을 둔다(제목은 산출물의 내용이라 소리를 내야 하지만
                #    이건 대조용 부가정보라 부재가 곧 결함은 아니다).
                "smart_editor_version": item.get("smartEditorVersion"),
            }
    C.ensure_dirs()
    C.CATLIST_JSON.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    return catalog


MIN_HTML_BYTES = 5000       # 구 수집기(harvest_cat28_29.py:62)의 실패 판정 기준을 승계
BODY_SLEEP = 1.0


def _stem(entry):
    # log_no 는 정규화 지점 ①②에서 이미 str 이다. str() 는 파일명이 타입 때문에
    # 갈리지 않게 하는 방어이며, 정규화를 대신하지 않는다(메타·V1 은 위에서 고정된다).
    return (str(entry["category"]) + "_" + entry["post_date"].replace("-", "")
            + "_" + C.norm_log_no(entry["log_no"]))


def harvest_one(entry, fetch=None, retries=3, sleep=None):
    """글 하나의 HTML 을 받아 저장하고 텍스트를 뽑아 메타를 만든다.

    🔑 이미 받아 둔 파일이 충분히 크면 **다시 받지 않는다**(선행 2본
       harvest_cat28_29.py:62 · harvest_bodies.py:70 의 존재-스킵을 승계).
       432건 중 431번째에서 실패했을 때 전량 재요청하지 않기 위한 것이다.
    """
    fetch = fetch or C.fetch_html
    sleep = sleep if sleep is not None else time.sleep
    stem = _stem(entry)
    html_path = C.POSTS_DIR / (stem + ".html")
    text_path = C.TEXT_DIR / (stem + ".txt")

    src, from_cache = None, False
    # 스킵 문턱은 아래 수신 판정과 **같은 술어**를 쓴다. 둘이 어긋나면 매 실행마다
    # 경계 크기의 파일을 다시 받으면서 스킵이 듣는 것처럼 보인다.
    if html_path.exists() and html_path.stat().st_size >= MIN_HTML_BYTES:
        src, from_cache = html_path.read_text(encoding="utf-8"), True

    if src is None:
        for attempt in range(retries):
            got = fetch(entry["log_no"])
            if got is not None and len(got.encode("utf-8")) >= MIN_HTML_BYTES:
                src = got
                break
            if attempt < retries - 1:
                sleep(BODY_SLEEP * (attempt + 1))
    if src is None:
        # str() 없이 int 를 이으면 TypeError 가 **진짜 실패 사유를 덮어쓴다**.
        raise RuntimeError("HTML_TOO_SHORT:" + C.norm_log_no(entry["log_no"]))

    if not from_cache:
        html_path.write_text(src, encoding="utf-8")
    text = C.html_to_text(src)
    text_path.write_text(text, encoding="utf-8")

    meta = {
        "log_no": C.norm_log_no(entry["log_no"]),
        "category": entry["category"],
        "post_date": entry["post_date"],
        "title": entry.get("title", ""),
        "html_bytes": len(src.encode("utf-8")),
        "text_len": len(text),
        "text_file": stem + ".txt",
        "img_count": C.count_images(src),
        "from_cache": from_cache,
    }
    # image_only / legacy_editor / body_container — 두 상태를 한 플래그에 섞지 않는다.
    meta.update(C.classify_body(src, text))
    return meta


def harvest_bodies(catalog, sleep=None):
    """카탈로그 전건을 수집하고 POSTMETA_JSON 을 쓴다. **(metas, failures)** 를 돌려준다.

    🔑 글 하나가 안 받아진다고 파이프라인 전체를 죽이지 않는다 — 비공개·삭제 글은
       우리 잘못이 아니다. 대신 실패를 **모아서** 끝까지 돈 뒤 목록으로 올린다.
    ⚠️ 실패를 성공으로 보고하지 않는다: 실패는 반환값·파일·main() 종료코드에 전부 드러난다.
    """
    sleep = sleep if sleep is not None else time.sleep
    C.ensure_dirs()
    metas, failures = [], []
    for log_no in sorted(catalog["posts"]):
        entry = catalog["posts"][log_no]
        try:
            metas.append(harvest_one(entry, sleep=sleep))
        except Exception as exc:
            failures.append({
                "log_no": C.norm_log_no(entry.get("log_no", log_no)),
                "category": entry.get("category"),
                "post_date": entry.get("post_date"),
                "title": entry.get("title", ""),
                "error": type(exc).__name__ + ": " + str(exc),
            })
        sleep(BODY_SLEEP)
    C.POSTMETA_JSON.write_text(
        json.dumps(metas, ensure_ascii=False, indent=1), encoding="utf-8")
    # 🔑 실패 0건이어도 **덮어쓴다**. 지난 실행의 실패 목록이 남아 이번 실행을
    #    잘못 말하는 일(거짓 경보·거짓 안심 둘 다)을 막는다.
    C.HARVEST_FAIL_JSON.write_text(
        json.dumps(failures, ensure_ascii=False, indent=1), encoding="utf-8")
    return metas, failures


def main():
    catalog = build_catalog()
    metas, failures = harvest_bodies(catalog)
    cached = sum(1 for m in metas if m.get("from_cache"))
    print("카탈로그", len(catalog["posts"]), "건 · 본문", len(metas),
          "건(기존 재사용", cached, "건) · 실패", len(failures), "건")
    print("postCnt", catalog["post_cnt"])
    legacy = [m for m in metas if m.get("legacy_editor")]
    print("본문 미수신(legacy_editor)", len(legacy), "건 ·",
          "이미지 전용", sum(1 for m in metas if m.get("image_only")), "건")
    for m in legacy:
        print("   본문 못 읽음", m["log_no"], m["post_date"],
              "container=" + str(m.get("body_container")))
    # 제목 키는 있는데 값이 빈 글 — 막지는 않되 침묵하지도 않는다(item_title 참조).
    blank = [m for m in metas if not str(m.get("title") or "").strip()]
    if blank:
        print("⚠️ 제목이 빈 글", len(blank), "건:", [m["log_no"] for m in blank][:20])
    if failures:
        print("🔴 수집 실패", len(failures), "건 — 「전수」를 주장할 수 없다:")
        for f in failures:
            print("   ", f["log_no"], f["post_date"], f["error"])
        print("->", C.HARVEST_FAIL_JSON)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
