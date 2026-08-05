# -*- coding: utf-8 -*-
"""[28]·[29] 수집 파이프라인 공용 — 경로·상수·HTTP·텍스트 추출.

🔴 이 파일이 **경로의 단일 출처**다. 다른 모듈에서 상대 경로로 디렉토리를 만들지 말 것.
   구 스크립트(harvest_cat28_29.py:37-38)가 cwd 상대 경로를 써서 수집분 29건이
   저장소에 남지 않았다.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path

HARVEST = Path(__file__).resolve().parent            # backtest/tasso_labels/harvest
TASSO = HARVEST.parent                               # backtest/tasso_labels

POSTS_DIR = HARVEST / "posts28"
TEXT_DIR = HARVEST / "text28"
IMAGES_DIR = HARVEST / "images28"
CLAIMS_BATCH_DIR = HARVEST / "claims_batches"

CATLIST_JSON = HARVEST / "catlist_28_29.json"
POSTMETA_JSON = HARVEST / "postmeta_28_29.json"
CLAIMS_PUBLIC_CSV = HARVEST / "claims_cat2829.csv"
CLAIMS_QUOTED_CSV = HARVEST / "claims_cat2829_quoted.csv"
VERIFY_LOG = HARVEST / "verify_cat2829.log"

BLOG = "mbc3110"
CATEGORIES = {28: "주식기법분석", 29: "시황이슈정리"}

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

# se-text-paragraph = 네이버 스마트에디터 본문 문단. 구 수집기와 동일 패턴을 승계한다.
PARA = re.compile(r'<p[^>]*class="[^"]*se-text-paragraph[^"]*"[^>]*>(.*?)</p>', re.S)
TAG = re.compile(r"<[^>]+>")
IMG = re.compile(r"<img[^>]+")


def _curl(url, referer, timeout=40):
    r = subprocess.run(
        ["curl", "-s", "-m", str(timeout), "-A", UA, "-H", "Referer: " + referer,
         "-H", "Accept: application/json, text/plain, */*", url],
        capture_output=True)
    return r.stdout.decode("utf-8", "replace")


def api_json(cat, page, item_count=30):
    """카테고리 글 목록 API 한 페이지. 파싱 실패 시 None."""
    ref = ("https://m.blog.naver.com/PostList.naver?blogId=" + BLOG
           + "&categoryNo=" + str(cat))
    url = ("https://m.blog.naver.com/api/blogs/" + BLOG + "/post-list"
           "?categoryNo=" + str(cat) + "&itemCount=" + str(item_count)
           + "&page=" + str(page))
    try:
        return json.loads(_curl(url, ref, timeout=30))
    except Exception:
        return None


def category_list():
    """블로그 카테고리 트리. postCnt 를 여기서 얻는다."""
    ref = "https://m.blog.naver.com/PostList.naver?blogId=" + BLOG
    url = "https://m.blog.naver.com/api/blogs/" + BLOG + "/category-list"
    try:
        return json.loads(_curl(url, ref, timeout=30))
    except Exception:
        return None


def fetch_html(log_no):
    """글 본문 HTML."""
    url = ("https://m.blog.naver.com/PostView.naver?blogId=" + BLOG
           + "&logNo=" + str(log_no))
    return _curl(url, "https://m.blog.naver.com/" + BLOG, timeout=40)


def html_to_text(src):
    """본문 문단만 남긴 평문. 문단 사이는 개행 하나."""
    paras = []
    for p in PARA.findall(src):
        t = re.sub(r"[\s​\xa0]+", " ", html.unescape(TAG.sub(" ", p))).strip()
        paras.append(t)
    return "\n".join(paras)


def count_images(src):
    return len(IMG.findall(src))


def ensure_dirs():
    for d in (POSTS_DIR, TEXT_DIR, IMAGES_DIR, CLAIMS_BATCH_DIR):
        d.mkdir(parents=True, exist_ok=True)
