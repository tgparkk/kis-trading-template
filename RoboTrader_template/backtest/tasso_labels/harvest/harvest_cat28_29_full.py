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
        fresh = [x for x in items if x["logNo"] not in seen]
        if not fresh:
            return seen
        for x in fresh:
            seen[x["logNo"]] = x
        sleep(PAGE_SLEEP)
    raise RuntimeError(
        "MAX_PAGES(" + str(MAX_PAGES) + ") 도달 — 목록이 안 끝났다. "
        "조용한 절단을 막기 위해 중단한다. 상한을 올리고 재실행할 것.")


def build_catalog():
    """카테고리별 목록 + postCnt 를 모아 CATLIST_JSON 으로 쓴다."""
    counts = category_counts(C.category_list())
    catalog = {"fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
               "post_cnt": {}, "posts": {}}
    for cat in C.CATEGORIES:
        listing = fetch_post_list(cat)
        catalog["post_cnt"][str(cat)] = counts.get(cat)
        for log_no, item in listing.items():
            dt = datetime.datetime.fromtimestamp(item["addDate"] / 1000)
            catalog["posts"][log_no] = {
                "log_no": log_no,
                "category": cat,
                "post_date": dt.strftime("%Y-%m-%d"),
                "add_date_ms": item["addDate"],
                "title": item.get("titleWithInspectMessage", ""),
            }
    C.ensure_dirs()
    C.CATLIST_JSON.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    return catalog
