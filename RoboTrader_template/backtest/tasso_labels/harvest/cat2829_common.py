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

TAG = re.compile(r"<[^>]+>")
IMG = re.compile(r"<img[^>]+")

# ── 본문 컨테이너 ─────────────────────────────────────────────────────────────
# 🔴 2026-08-05 실측이 뒤집은 것: **부분문자열로 컨테이너를 찾으면 안 된다.**
#    옛 판본은 `"se-main-container" in src` 를 SE3 본문 신호로 썼다. 그런데 네이버
#    모바일 페이지는 에디터 세대와 무관하게 **페이지 골격의 JS 한 줄**에 그 이름을
#    담아 보낸다:
#        var imageLazyLoader = new ImageLazyLoader(".se-main-container,.__se_component_area");
#    그래서 본문이 한 글자도 안 실린 SE2 글 195건이 전부 `body_container="se3"` +
#    `image_only=True` 로 찍혀 **「진짜 이미지 전용 글」로 위장**했다(432건 전수 실측).
#  ⇒ 컨테이너는 **여는 태그 정규식**으로만 인정한다. JS 문자열 리터럴은 태그가 아니다.
#
# 🔴 두 번째로 뒤집힌 것: 「모바일은 구 에디터 본문을 안 준다」는 선행 기록
#    (harvest_fallback.py:3-5)은 **현재 응답에는 해당하지 않는다.** 모바일은 SE2·SE3
#    본문을 **세대별 다른 마크업으로 실어 준다.** 못 읽은 이유는 추출기가 SE4 문단
#    (`se-text-paragraph`)만 읽었기 때문이다. 아래 앵커 4개는 저장된 432건 + PC 응답
#    1건에서 도출했다(추측 0건):
#      se4  235/235 · se3 2/2 · se2 195/195 · postview = PC 엔드포인트 응답
NOISE = re.compile(
    r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>|<!--.*?-->", re.S | re.I)
DIV_TOKEN = re.compile(r"<div\b[^>]*>|</div\s*>", re.I)

BODY_ANCHORS = (
    # SmartEditor ONE(=4). ⚠️ `se-viewer` 를 쓰면 안 된다 — 네이버가 그 안에 글쓴이·
    #    날짜·「이웃추가」·「공유하기」 같은 **UI 크롬을 넣어** 본문에 섞인다(실측).
    ("se4", re.compile(r'<div[^>]*class="[^"]*\bse-main-container\b[^"]*"[^>]*>', re.I)),
    # SmartEditor 3. 머리말 쪽 `<div class="se_component_wrap">` 와 구분하려면
    # `__se_component_area` 를 **함께** 요구해야 한다.
    ("se3", re.compile(r'<div[^>]*class="[^"]*\bse_component_wrap\b[^"]*'
                       r'\b__se_component_area\b[^"]*"[^>]*>', re.I)),
    # SmartEditor 2 (모바일). 이 세대는 본문만 `post_ct` 안에 있고 크롬은 바깥이다.
    ("se2", re.compile(r'<div[^>]*id="viewTypeSelector"[^>]*>', re.I)),
    # PC 엔드포인트(`blog.naver.com/PostView.naver?...&redirect=Dlog`) 응답.
    # harvest_fallback.py:38,46 이 쓰던 마커. 모바일 응답에는 **0건**이라 겹치지 않는다.
    ("postview", re.compile(r'<div[^>]*id="postViewArea"[^>]*>', re.I)),
)

# 페이지가 스스로 밝히는 에디터 세대. 목록 API 의 `smartEditorVersion` 과 **독립**이며
# 응답과 함께 오므로 교차대조에 쓴다(432/432 일치 실측).
PAGE_EDITOR_VERSION = re.compile(r"editorversion\s*=\s*['\"](\d+)['\"]", re.I)

BR = re.compile(r"<br\s*/?>", re.I)
BLOCK_END = re.compile(r"</(p|div|td|tr|li|h[1-6]|blockquote)\s*>", re.I)


def body_region(src):
    """본문 컨테이너 안쪽 HTML 을 잘라 낸다. **(generation, inner_html)**.

    못 찾으면 (None, None). 스크립트·스타일·주석을 먼저 지우고 `<div>` 균형으로
    닫는 위치를 찾는다 — 안 지우면 JS 안의 `</div>` 문자열이 깊이를 흔들어
    페이지 끝까지 삼킨다(실측: SE4 한 건이 155,066자 중 108,173자를 먹었다).
    """
    clean = NOISE.sub(" ", src)
    for name, rx in BODY_ANCHORS:
        m = rx.search(clean)
        if not m:
            continue
        depth, start = 1, m.end()
        for tok in DIV_TOKEN.finditer(clean, start):
            depth += -1 if tok.group(0).lower().startswith("</") else 1
            if depth == 0:
                return name, clean[start:tok.start()]
        # 닫는 태그를 못 찾았다 = 응답이 잘렸다. 조용히 빈 문자열을 주지 않는다.
        return name, clean[start:]
    return None, None


def classify_body(src, text):
    """본문 수신 상태를 판정한다. **판정 축은 「본문 문단이 실제로 추출됐는가」다.**

    🔴 왜 마커 존재만으로 판정하면 안 되는가 (2026-08-05 실측):
       `se-main-container` 는 본문이 0자인 글의 페이지 골격에도 들어 있다. 그 하나에
       기대는 순간 **본문 미수신 195건이 「진짜 이미지 전용」으로 위장**하고,
       `legacy_editor` 는 0건이 되어 아무도 소리를 내지 않는다.

    🔑 왜 `smart_editor_version` 을 판정에 **안** 쓰는가:
       그 값은 「어느 에디터로 썼는가」이지 「이 응답이 본문을 실어 왔는가」가 아니다.
       네이버가 또 서빙을 바꾸면 버전은 그대로 4 인 채 본문만 사라진다 — 이번에
       고치는 무음 손실과 **정확히 같은 형태**로. 게다가 그 값은 다른 산출물
       (catlist)에 있어서 HTML 한 장만으로는 판정이 안 된다.
       ⇒ 판정은 구조로 하고, 버전은 **독립 교차대조**로만 쓴다
         (`smart_editor_version`=목록 API · `page_editor_version`=응답 자체).

    반환 키:
      body_container : "se4"|"se3"|"se2"|"postview"|"none" — **실제 태그**로 찾은 컨테이너
      image_only     : 본문을 **읽었는데** 글자 0자이고 본문 안에 이미지가 있다
                       = 진짜 이미지 전용 글
      body_missing   : 본문을 **못 받았다**(컨테이너 태그 없음, 또는 컨테이너는 있는데
                       글자도 이미지도 0) = 재추출·재수집 대상
    """
    container, region = body_region(src)
    if text:
        return {"body_container": container or "none",
                "image_only": False, "body_missing": False}
    if container is None:
        # 본문 컨테이너 자체가 없다 = 응답에 본문이 안 실렸다. 이미지 전용이 **아니다**.
        return {"body_container": "none", "image_only": False, "body_missing": True}
    if IMG.search(region or ""):
        # 본문을 열어 봤고 그 안에 이미지가 있다. 글자만 없다 = 진짜 이미지 전용 글.
        return {"body_container": container, "image_only": True, "body_missing": False}
    # 컨테이너는 왔는데 글자도 이미지도 없다. 빈 본문은 글이 아니다 —
    # 「이미지 전용」이라고 부르면 아무도 안 읽은 채 초록이 된다. 시끄럽게 둔다.
    return {"body_container": container, "image_only": False, "body_missing": True}


def page_editor_version(src):
    """응답 자체가 밝히는 에디터 세대(int). 없으면 None.

    목록 API 의 `smartEditorVersion` 과 **독립 경로**다. 둘이 어긋나면 가정이 깨진
    것이므로 소리를 내야 한다(현재 432/432 일치).
    """
    m = PAGE_EDITOR_VERSION.search(src)
    return int(m.group(1)) if m else None


def detect_source(src):
    """이 HTML 을 **어느 엔드포인트에서 받았는지**를 응답 자체에서 읽는다.

    🔑 플래그로 적어 두지 않고 산출물에서 되읽는다 — 나중에 「이 글은 어디서 왔나」를
       물었을 때 우리가 적은 메모가 아니라 파일이 답하게 하려는 것이다.
       모바일에는 `id="viewTypeSelector"` 가 432/432, PC 에는 `postViewArea` 가 있고
       서로 겹치지 않는다(양쪽 실측).
    """
    if re.search(r'<div[^>]*id="viewTypeSelector"[^>]*>', src, re.I):
        return "mobile"
    if re.search(r'<div[^>]*id="postViewArea"[^>]*>', src, re.I):
        return "pc"
    return "unknown"


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
    """**본문 컨테이너 안쪽만** 평문으로. 문단 사이는 개행 하나.

    🔴 옛 판본은 `se-text-paragraph`(SmartEditor ONE 문단)만 읽었다. 이 블로그는
       에디터를 **세 세대** 쓰므로(SE2 195 · SE3 2 · SE4 235, 전수 실측) 그 패턴은
       SE4 에만 걸리고 나머지 197건이 **0자로 조용히 사라졌다.** 세대별 마크업은
       서로 완전히 다르다:
         SE2  `<div ... _foo="view">` 안에 그냥 `<p><span>` (클래스 없음)
         SE3  `<p class="se_textarea">`
         SE4  `<p class="se-text-paragraph">`
       ⇒ 문단 클래스를 열거하지 않는다. **컨테이너를 잘라 그 안의 텍스트를 전부** 낸다.
          열거식은 새 세대가 오면 또 조용히 0자가 된다(이번이 그 실패다).

    경계는 `body_region` 이 정한다 — 사이드바·댓글·관련글은 컨테이너 **바깥**이라
    들어오지 않는다. 실증: 같은 글(220000968295)을 모바일 컨테이너에서 4,192자,
    PC `postViewArea` 에서 4,192자로 뽑아 **줄 단위 완전일치**(88줄, 차이 0줄).
    """
    _, region = body_region(src)
    if region is None:
        return ""
    # 블록 끝과 <br> 만 개행으로 바꾼다 — 인라인 태그에서 개행을 만들면 한 문장이
    # 여러 줄로 찢어져 하류의 항목 헤더 정규식(parse_bodies.ITEM)이 못 잡는다.
    s = BLOCK_END.sub("\n", BR.sub("\n", region))
    s = html.unescape(TAG.sub(" ", s))
    lines = (re.sub(r"[\s​\xa0]+", " ", ln).strip() for ln in s.split("\n"))
    return "\n".join(ln for ln in lines if ln)


def count_images(src, body_only=False):
    """페이지 전체(기본) 또는 **본문 안쪽**의 `<img>` 수.

    ⚠️ 기본값이 페이지 전체인 것은 선행 메타와의 연속성 때문이다. `image_only`
       판정은 반드시 본문 안쪽을 봐야 한다 — 페이지 전체를 세면 UI 아이콘 때문에
       **어떤 응답이든 이미지가 있는 것처럼** 보여 판별력이 0 이 된다.
    """
    if body_only:
        _, region = body_region(src)
        return len(IMG.findall(region or ""))
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
