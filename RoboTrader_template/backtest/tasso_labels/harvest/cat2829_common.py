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
HARVEST_FAIL_JSON = HARVEST / "harvest_fail_28_29.json"
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

# ── 본문 컨테이너 마커 ────────────────────────────────────────────────────────
# 🔴 이 블로그는 **에디터 두 세대**를 쓴다(parse_posts.py:6-10 이 실측으로 기록).
#    아래 두 문자열은 추측이 아니라 이 저장소의 코드에서 그대로 승계한 것이다.
#
#  SE3(2019~) 본문 컨테이너 — parse_posts.py:3 "se-main-container 를 통째로 자르려던
#    첫 판본". 본문이 왔다면 이 컨테이너가 있고, 글자가 있으면 se-text-paragraph 도 있다.
SE3_CONTAINER = "se-main-container"
#  SE2(구 에디터, 2017~2018) 본문 컨테이너 — parse_posts.py:23-24 가 구 에디터 본문을
#    여기서 뽑고(`id="postViewArea"`), harvest_fallback.py:38,46 이 PC 재수집의
#    대상 선정·성공 판정을 **이 문자열 하나로** 한다.
SE2_CONTAINER = "postViewArea"


def classify_body(src, text):
    """본문 수신 상태를 판정한다. `image_only` 하나에 두 상태를 섞지 않는 것이 요점이다.

    🔴 왜 나누는가 (harvest_fallback.py:3-5 가 이미 겪고 기록한 결함):
       `m.blog.naver.com/PostView.naver` 는 **구 에디터 글의 본문을 아예 싣지 않는다**.
       그런 응답도 8KB 쯤 되어 크기 문턱을 통과하고, 본문만 0자다. 이것을
       `image_only=True` 로 적으면 「이미지만 있는 글」과 구분되지 않아
       **원문을 한 번도 안 읽고도 모든 게이트가 초록**이 된다.

    반환 키:
      body_container : "se3" | "se2" | "none"  — 어느 본문 컨테이너를 받았는가
      image_only     : SE3 본문을 **받았는데** 글자가 0자 = 진짜 이미지 전용 글
      legacy_editor  : 본문을 SE3 경로로 **못 읽었다** = 재추출·재수집 대상
    """
    if text:
        return {"body_container": "se3", "image_only": False, "legacy_editor": False}
    if SE2_CONTAINER in src:
        # 구 에디터 본문이 실려 있다. 여기 추출기는 SE3 문단만 읽으므로 아직 못 읽은 것이다.
        return {"body_container": "se2", "image_only": False, "legacy_editor": True}
    if SE3_CONTAINER in src:
        # SE3 본문 컨테이너는 왔는데 문단이 없다 = 이미지·표만 있는 글.
        return {"body_container": "se3", "image_only": True, "legacy_editor": False}
    # 본문 컨테이너 자체가 없다 = 응답에 본문이 안 실렸다. 이미지 전용이 **아니다**.
    return {"body_container": "none", "image_only": False, "legacy_editor": True}


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


def norm_log_no(value):
    """logNo 를 **str 로 정규화**한다. 🔴 소스 한 곳에서만 부른다.

    목록 API 는 logNo 를 **int** 로 준다(tasso_postlist.json 858건 전수 실측).
    반면 catalog["posts"] 는 JSON **객체**라 키가 저장/재적재 후 항상 str 이 된다.
    정규화를 안 하면 V1 이 str 집합과 int 집합을 비교해 전건을
    「missing 이면서 동시에 extra」로 오탐한다.
    """
    return str(value)


def ensure_dirs():
    for d in (POSTS_DIR, TEXT_DIR, IMAGES_DIR, CLAIMS_BATCH_DIR):
        d.mkdir(parents=True, exist_ok=True)
