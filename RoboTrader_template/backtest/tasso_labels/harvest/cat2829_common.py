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
IMAGE_FAIL_JSON = HARVEST / "image_fail_28_29.json"
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
    """페이지 전체(기본) 또는 **본문 안쪽**의 `<img>` **태그** 수.

    ⚠️ 기본값이 페이지 전체인 것은 선행 메타와의 연속성 때문이다. `image_only`
       판정은 반드시 본문 안쪽을 봐야 한다 — 페이지 전체를 세면 UI 아이콘 때문에
       **어떤 응답이든 이미지가 있는 것처럼** 보여 판별력이 0 이 된다.

    🔴 이 값은 「본문 그림 수」가 **아니다**. 재는 것은 `<img>` 태그 수뿐이고,
       SE2 세대는 그림을 `<img>` 로 싣지 않는다(아래 `body_images` 참조).
       실측: SE2 195글의 본문 `<img>` 는 183개인데 실제 그림 슬롯은 2,169개이고,
       그중 **127글이 「0장」으로 찍혔다.** 그림을 세거나 내려받으려면
       `body_images()` 를 쓸 것 — 이 함수는 선행 메타(postmeta 의 `img_count`·
       `body_img_count`)의 정의를 고정하기 위해 그대로 둔 것이다.
    """
    if body_only:
        _, region = body_region(src)
        return len(IMG.findall(region or ""))
    return len(IMG.findall(src))


# ── 본문 이미지 ───────────────────────────────────────────────────────────────
# 🔴 2026-08-06 실측이 뒤집은 것: **`<img>` 만 세면 SE2 의 그림이 통째로 안 보인다.**
#    이 블로그의 SE2 세대(195글, 2009-08-22~2018-12-01)는 그림을 `<img>` 가 아니라
#    `<span>` 속성으로 싣는다:
#        <span class="_img _inl fx" thumburl="https://mblogthumb-phinf…/조광페인트1.png?type=">
#    그래서 SE2 195글 중 **127글이 「이미지 0장」**으로 찍혀 있었다. T9 에서
#    `html_to_text` 가 SE4 문단 마크업만 읽어 197건이 조용히 0자가 된 것과 **같은 클래스**다.
#
# 🔑 그래서 이 함수는 **모르는 형태를 버리지 않는다.** 슬롯을 찾으면 전부 돌려주고
#    정체는 `kind` 로 표시만 한다(무엇을 뺄지는 부르는 쪽이 정한다). 「내가 아는 것만
#    남기는」 열거식 필터는 새 세대가 오면 또 조용히 0장을 만든다 — 이번이 그 실패다.
#
# 아래 슬롯·정체는 전부 저장된 433건에서 도출했다(추측 0건 · 슬롯 합 5,886):
#   슬롯   span.thumburl 1,986(se2 전량) · img.data-lazy-src 2,623 · img.src 1,160
#          video.data-gif-url 117 · video.poster(대체) 0
#   정체   photo 4,627 · oglink 1,042 · gif 117 · spacer 84 · sticker 16
#   세대   se2 195글 2,170슬롯(photo 2,004) · se3 2글 21(15) · se4 236글 3,695(2,608)
IMG_TAG_ANY = re.compile(r"<(img|span|video)\b[^>]*>", re.I)
TAG_ATTRS = re.compile(r'([-\w:]+)\s*=\s*"([^"]*)"')

# 링크카드(오픈그래프 미리보기)는 저자의 그림이 아니라 **남의 사이트 썸네일**이다.
# 🔴 호스트로는 못 가른다 — 2012년 SE2 글의 저자 차트도 같은 프록시(dthumb-phinf)로
#    나온다(`<차트-1>` 캡션 바로 뒤, 17장 실측). 가르는 것은 **감싸는 컴포넌트**다.
#    세대별 class 가 다르지만(se2 `og _oglink` · se3 `se_oglink` · se4 `se-oglink`)
#    셋 다 `oglink` 를 포함한다 — 토큰을 열거하지 않고 그 사실만 쓴다.
OGLINK_DIV = re.compile(r'<div[^>]*class="[^"]*oglink[^"]*"[^>]*>', re.I)

# 레이아웃 스페이서(SE2 84장). 그림이 아니라 자리를 띄우는 1픽셀 gif 다.
SPACER_NAME = "blank.gif"

# `body_images` 가 낼 수 있는 정체 전부. 🔑 부르는 쪽의 필터가 이 목록을 검증에 쓴다 —
# 오타(`"Photo"`)를 「해당 없음 0장」으로 조용히 통과시키지 않기 위해서다.
IMAGE_KINDS = ("photo", "oglink", "sticker", "spacer", "gif")


def normalize_image_url(url, type_param="w966"):
    """썸네일 URL 의 `type` 파라미터만 **교체**한다. 나머지 쿼리는 그대로 둔다.

    🔴 선행 코드(`extract_calc_images.py:43`)는 `re.sub(r"\\?type=w\\d+", "", url)
       + "?type=w966"` 이었다. 두 형태에서 깨진다(둘 다 실측):
         · SE2 는 값이 빈 `?type=` 라 정규식에 안 걸려 `…?type=?type=w966` 이 된다(1,986건)
         · 링크카드는 `?src=%22…%22&type=ff120` 이라 `?` 가 두 번 붙는다(1,042건)
    ⇒ 문자열로 쿼리를 다시 쓴다. `urlencode` 를 쓰면 안 된다 — `src=%22…%22` 의
      퍼센트 인코딩을 **다시 인코딩**해 URL 이 달라진다.
    """
    base, _, query = url.partition("?")
    kept = [p for p in query.split("&") if p and p.split("=", 1)[0] != "type"]
    kept.append("type=" + type_param)
    return base + "?" + "&".join(kept)


def _oglink_spans(region):
    """링크카드 컴포넌트가 차지하는 (시작, 끝) 구간들. `body_region` 과 같은 방식이다."""
    spans = []
    for m in OGLINK_DIV.finditer(region):
        depth, end = 1, len(region)
        for tok in DIV_TOKEN.finditer(region, m.end()):
            depth += -1 if tok.group(0).lower().startswith("</") else 1
            if depth == 0:
                end = tok.end()
                break
        spans.append((m.start(), end))
    return spans


def _image_kind(url, cls, in_oglink):
    """이 슬롯이 무엇인가. **버리지 않고 이름만 붙인다.**"""
    if in_oglink or "oglink" in cls:
        return "oglink"
    if "sticker" in cls:
        return "sticker"
    if url.partition("?")[0].endswith(SPACER_NAME):
        return "spacer"
    return "photo"


def body_images(src):
    """**본문 안쪽**의 이미지 슬롯 전부를 **문서 등장 순서 그대로** 낸다.

    반환: `[{"url": 정규화된 URL, "kind": ..., "slot": ...}, ...]` · 본문이 없으면 `[]`.

    지키는 계약(전부 저장된 433건에서 도출):
      ① 경계는 `body_region` 안쪽뿐이다. 페이지 전체를 훑으면 블로거 프로필 썸네일
         (`blogpfthumb-phinf`)이 **글당 4장** 섞인다(433/433 균일 실측, 본문 안쪽 0장).
      ② SE2 = `class` 에 `_img` 가 있는 `<span>` 의 `thumburl`.
      ③ SE3/SE4 = `<img>`. **`data-lazy-src` 우선, 없으면 `src`** — `src` 는 흐림
         placeholder 다(2,623/2,623 이 `?type=w80_blur`, lazy 는 `w800`/`w400`).
      ④ GIF 는 `<video>` 로 온다(117건). `data-gif-url` 이 원본 GIF, `poster` 가 대체.
      ⑤ URL 은 HTML 엔티티가 이스케이프돼 있다 — `&amp;` 961 · `&#x3D;` 955 ·
         `&#61;` 6. 안 풀면 `?src&#x3D;%22…` 라는 **없는 주소**를 받는다.
      ⑥ 순서는 정렬이 아니라 **한 번의 스캔**으로 보존한다. 슬롯 종류가 섞인 글이
         67건 실재하므로(span+img 공존) 종류별로 모아 나중에 이으면 순서가 깨진다.
    """
    _, region = body_region(src)
    if not region:
        return []
    spans = _oglink_spans(region)
    out = []
    for m in IMG_TAG_ANY.finditer(region):
        tag = m.group(1).lower()
        attrs = {k.lower(): v for k, v in TAG_ATTRS.findall(m.group(0))}
        cls = attrs.get("class") or ""
        if tag == "img":
            names = ("data-lazy-src", "src")
        elif tag == "video":
            names = ("data-gif-url", "poster")
        elif "_img" in cls.split():
            names = ("thumburl",)
        else:
            continue
        raw = next((attrs[n] for n in names if attrs.get(n)), None)
        if not raw:
            # 주소가 없는 슬롯은 내려받을 것이 없다. 조용히 버려도 되는 유일한 경우다.
            continue
        url = normalize_image_url(html.unescape(raw))
        in_og = any(a <= m.start() < b for a, b in spans)
        out.append({"url": url,
                    "kind": "gif" if tag == "video" else _image_kind(url, cls, in_og),
                    "slot": tag + "." + next(n for n in names if attrs.get(n))})
    return out


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
