# -*- coding: utf-8 -*-
"""[28]·[29] 전수 수집 파이프라인 — 단위 테스트.

⚠️ 라이브 트리에서 실행 금지. 워크트리에서 이 파일로 한정해 돌린다:
    pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

TASSO = Path(__file__).resolve().parents[1]        # backtest/tasso_labels
HARVEST = TASSO / "harvest"
REPO = TASSO.parents[1]                            # RoboTrader_template (.gitignore 위치)


def _load(name):
    """harvest/ 는 패키지가 아니므로(=__init__.py 없음) 경로로 직접 로드한다."""
    path = HARVEST / (name + ".py")
    spec = importlib.util.spec_from_file_location("_tasso_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ignored(rel):
    """git check-ignore: 무시되면 exit 0, 아니면 1."""
    r = subprocess.run(["git", "check-ignore", "-q", rel], cwd=str(REPO))
    return r.returncode == 0


# ============================ Task 1 ============================

def test_paths_are_absolute_and_cwd_independent(tmp_path, monkeypatch):
    """🔑 지난 수집분 29건이 사라진 원인의 회귀 테스트.

    구 스크립트는 os.makedirs("posts2") 로 **cwd 상대** 경로에 썼다. 다른 cwd 에서
    돌리면 산출물이 엉뚱한 곳에 생기고 저장소에는 흔적이 남지 않는다.
    """
    before = _load("cat2829_common").POSTS_DIR
    monkeypatch.chdir(tmp_path)
    after = _load("cat2829_common").POSTS_DIR
    assert before == after, "cwd 를 바꾸니 출력 경로가 달라졌다"
    assert after.is_absolute()
    assert after.parent == HARVEST


@pytest.mark.parametrize("rel", [
    "backtest/tasso_labels/harvest/posts28/x.html",
    "backtest/tasso_labels/harvest/text28/x.txt",
    "backtest/tasso_labels/harvest/images28/x.png",
    "backtest/tasso_labels/harvest/claims_batches/b01.jsonl",
    "backtest/tasso_labels/harvest/claims_cat2829_quoted.csv",
])
def test_gitignore_blocks_copyrighted_artifacts(rel):
    """타인 저작물(원문 HTML·텍스트·이미지·인용 포함 원장)은 커밋되면 안 된다.

    ⚠️ 2026-08-05 실측: 조치 전에는 **다섯 개 전부 tracked** 였다.
       .gitignore:169 의 `!backtest/tasso_labels/harvest/*.csv` 가 quoted 판까지 되살린다.
    """
    assert _ignored(rel), rel + " 이 커밋 대상이다"


@pytest.mark.parametrize("rel", [
    "backtest/tasso_labels/harvest/claims_cat2829.csv",
    "backtest/tasso_labels/harvest/catlist_28_29.json",
    "backtest/tasso_labels/harvest/postmeta_28_29.json",
    "backtest/tasso_labels/harvest/harvest_fail_28_29.json",
    "backtest/tasso_labels/harvest/verify_cat2829.log",
])
def test_gitignore_keeps_derived_evidence(rel):
    """🔑 반대 방향도 고정한다 — 파생 사실·검증 근거는 반드시 추적돼야 한다.

    ⚠️ 2026-08-05 실측: verify_cat2829.log 는 `*.log`(.gitignore:68,138) 에 삼켜져
       **IGNORED** 였다. 범용 패턴이 우리 산출물을 삼키는 6번째 사례다.
    이 방향을 안 고정하면 다음 사람이 "그냥 harvest/ 전체를 차단" 으로 되돌려도 안 잡힌다.
    """
    assert not _ignored(rel), rel + " 이 조용히 무시된다"


# ============================ Task 2 ============================

def _good_row(**over):
    row = {
        "log_no": "223000000001", "post_date": "2024-05-02", "category": 28,
        "claim_id": "223000000001-1", "topic": "③분할매수",
        "claim": "상승폭이 클수록 매수 밴드를 더 깊게 잡는다",
        "numbers": "45~48%;481건", "quote": "평균은 점 하나인데 현실은 퍼짐",
        "para_idx": 12, "image_ref": False,
        "vs_v1": "agree", "v1_anchor": "§1-③",
    }
    row.update(over)
    return row


def test_public_columns_exclude_quote():
    """커밋되는 판본에는 원문 인용이 없어야 한다."""
    s = _load("claims_schema")
    assert "quote" in s.COLUMNS
    assert "quote" not in s.PUBLIC_COLUMNS
    assert len(s.PUBLIC_COLUMNS) == len(s.COLUMNS) - 1


def test_valid_row_passes():
    s = _load("claims_schema")
    assert s.validate_row(_good_row()) == []


def test_missing_column_is_reported():
    s = _load("claims_schema")
    row = _good_row()
    del row["numbers"]
    assert any(v.startswith("MISSING_COLUMN:numbers") for v in s.validate_row(row))


@pytest.mark.parametrize("field,bad,prefix", [
    ("category", 32, "BAD_CATEGORY"),
    ("topic", "③분할매수 ", "BAD_TOPIC"),      # 뒤 공백 = 다른 값이다
    ("vs_v1", "New", "BAD_VS_V1"),             # 대소문자 오타
])
def test_enum_violations_are_reported(field, bad, prefix):
    """🔑 오타를 「정상」으로 보고하는 것이 거짓 안심의 전형이다.

    2026-08-04 급락게이트에서 독립검증이 잡은 결정적 결함이 정확히 이것이었다 —
    `"Auto"`·null 을 정상으로 보고했다.
    """
    s = _load("claims_schema")
    assert any(v.startswith(prefix) for v in s.validate_row(_good_row(**{field: bad})))


def test_quote_length_cap():
    s = _load("claims_schema")
    assert s.QUOTE_MAX == 40
    long_quote = "가" * 41
    assert any(v.startswith("QUOTE_TOO_LONG") for v in s.validate_row(_good_row(quote=long_quote)))
    assert s.validate_row(_good_row(quote="가" * 40)) == []


def test_anchor_required_when_related_to_v1():
    s = _load("claims_schema")
    for vs in ("agree", "conflict", "revision"):
        bad = s.validate_row(_good_row(vs_v1=vs, v1_anchor=""))
        assert any(v.startswith("ANCHOR_REQUIRED_FOR:" + vs) for v in bad), vs


def test_anchor_forbidden_when_unrelated_to_v1():
    """🔑 반대 방향을 고정한다.

    안 하면 "전부 v1_anchor 를 채우면 통과" 로 되돌려도 아무도 못 잡는다.
    `if not FLAG:` 형태의 단방향 가드는 플래그를 뒤집으면 실패가 아니라 **꺼진다.**
    """
    s = _load("claims_schema")
    for vs in ("new", "none"):
        bad = s.validate_row(_good_row(vs_v1=vs, v1_anchor="§1-③"))
        assert any(v.startswith("ANCHOR_FORBIDDEN_FOR:" + vs) for v in bad), vs
    assert s.validate_row(_good_row(vs_v1="new", v1_anchor="")) == []


def test_empty_claim_is_reported():
    s = _load("claims_schema")
    assert any(v == "EMPTY_CLAIM" for v in s.validate_row(_good_row(claim="   ")))


# ============================ Task 3 ============================

def _fake_pages(pages):
    """pages = [[item, ...], ...]. 페이지 번호(1-base)로 꺼내 쓴다."""
    def fetch(cat, page):
        if page > len(pages):
            return {"result": {"items": []}}
        return {"result": {"items": pages[page - 1]}}
    return fetch


# 🔴 제목 키는 시점에 따라 다르다 — **두 관측 다 실측**이며 서로 반대다.
#    한쪽만 픽스처로 굳히면 반대편 시점에 조용히 빈 제목이 된다. 실제로 두 번 그랬다.
TITLE_KEY_0801 = "title"                      # 2026-08-01 tasso_postlist.json (4키, 858/858)
TITLE_KEY_0805 = "titleWithInspectMessage"    # 2026-08-05 라이브 (44키) ← Task 9 가 만날 쪽

# 2026-08-05 라이브 응답의 **실제 키 44개**(categoryNo=28&itemCount=1&page=1 로 1건 확인).
# 값이 아니라 **스키마**만 옮겨 왔다 — 타인의 본문·제목은 담지 않는다.
LIVE_KEYS_0805 = (
    "addDate", "allOpenPost", "blogNo", "bothBuddyOpen", "briefContents", "buddyOpen",
    "buyWithMyOwnMoney", "categoryBlockYn", "categoryName", "categoryNo",
    "categoryOpenYn", "commentArrowVisible", "commentCnt", "domainIdOrBlogId",
    "hasThumbnail", "isPortraitThumbnail", "isVRThumbnail", "isVideoThumbnail",
    "logNo", "logNoObject", "marketPost", "memolog", "mp4", "notOpen", "openGraphLink",
    "outSideAllow", "placeName", "postBlocked", "product", "readCount", "scrapType",
    "scraped", "searchYn", "shareCnt", "smartEditorVersion", "sympathyArrowVisible",
    "sympathyCnt", "thisDayPostInfo", "thumbnailCount", "thumbnailList", "thumbnailUrl",
    "titleWithInspectMessage", "videoAniThumbnailUrl", "videoPlayTime",
)


def _item(log_no, add_date_ms, cat=28, title_key=TITLE_KEY_0805):
    """목록 API 항목 — **실제 응답과 같은 키·타입**.

    🔴 실측 두 건(둘 다 진짜 API 응답이다):
         2026-08-01 `harvest/tasso_postlist.json` 858건 — 키 4개, `title` 858/858,
                    `titleWithInspectMessage` 0건
         2026-08-05 라이브 1건 — 키 44개, `title` **없음**,
                    `titleWithInspectMessage` 있음, `smartEditorVersion`=4
       공통: `logNo` 는 **int**(예: 224364189017).

    기본값을 08-05 키로 두는 이유 = **Task 9 가 실제로 만날 쪽**이기 때문이다.
    옛 판본은 `"logNo": str(log_no)` 로 현실에 없는 정규화를 하고 제목 키도 한쪽만
    굳혀 C1·I1 을 둘 다 가렸다. 이번엔 두 시점을 파라미터로 **둘 다** 고정한다.
    """
    return {"logNo": int(log_no), "addDate": add_date_ms,
            "categoryNo": cat, title_key: "제목 " + str(log_no)}


def _live_item(log_no=224361924061, add_date_ms=1785314089138, cat=28):
    """2026-08-05 라이브 응답의 **키 44개를 그대로** 갖춘 항목(값은 대체).

    스키마를 현실에서 도출한다 — 이번 사고의 원인이 「픽스처가 현실에 없는 계약을
    고정」이었으므로, 실제로 받은 키 집합 자체를 회귀 대상으로 삼는다.
    """
    item = {k: None for k in LIVE_KEYS_0805}
    item.update({"logNo": int(log_no), "logNoObject": int(log_no),
                 "addDate": add_date_ms, "categoryNo": cat,
                 "categoryName": "주식기법 분석", "smartEditorVersion": 4,
                 "titleWithInspectMessage": "제목 " + str(log_no)})
    return item


MS_2019 = 1_546_300_800_000     # 2019-01-01
MS_2025 = 1_735_689_600_000     # 2025-01-01


def test_fetch_post_list_walks_every_page():
    h = _load("harvest_cat28_29_full")
    pages = [[_item(i, MS_2025) for i in range(p * 10, p * 10 + 10)] for p in range(3)]
    got = h.fetch_post_list(28, fetch=_fake_pages(pages), sleep=lambda s: None)
    assert len(got) == 30


def test_fetch_post_list_does_not_stop_at_old_posts():
    """🔑 회귀 테스트 — 구 스크립트의 CUT-break 가 재발하면 여기서 잡힌다.

    2페이지가 통째로 2019년이어도 3페이지까지 계속 돌아야 한다.
    """
    h = _load("harvest_cat28_29_full")
    pages = [
        [_item(1, MS_2025), _item(2, MS_2025)],
        [_item(3, MS_2019), _item(4, MS_2019)],
        [_item(5, MS_2019)],
    ]
    got = h.fetch_post_list(28, fetch=_fake_pages(pages), sleep=lambda s: None)
    assert set(got) == {"1", "2", "3", "4", "5"}


def test_fetch_post_list_dedupes_across_pages():
    """🔑 종료 조건은 「빈 페이지」가 아니라 「새 logNo 가 없는 페이지」다.

    2페이지가 **비어 있지 않은데 전부 중복**이다. 여기서 멈춰야 하므로
    3페이지의 항목 3 은 절대 수집되면 안 된다.
    구 구현(items 가 literally 빈 페이지에서만 중단)이면 3 까지 걷어와 실패한다.
    """
    h = _load("harvest_cat28_29_full")
    fetched = []
    inner = _fake_pages([[_item(1, MS_2025), _item(2, MS_2025)],
                         [_item(2, MS_2025)],
                         [_item(3, MS_2025)]])

    def fetch(cat, page):
        fetched.append(page)
        return inner(cat, page)

    got = h.fetch_post_list(28, fetch=fetch, sleep=lambda s: None)
    assert set(got) == {"1", "2"}, "전부 중복인 페이지에서 멈추지 않았다"
    assert fetched == [1, 2], "3페이지를 걷어왔다 = 종료 조건이 「빈 페이지」다"


def test_fetch_post_list_raises_instead_of_truncating():
    """🔑 조용한 절단 금지 — 상한에 닿으면 중단하고 소리를 낸다."""
    h = _load("harvest_cat28_29_full")

    def endless(cat, page):
        base = page * 100
        return {"result": {"items": [_item(base + i, MS_2025) for i in range(30)]}}

    with pytest.raises(RuntimeError, match="MAX_PAGES"):
        h.fetch_post_list(28, fetch=endless, sleep=lambda s: None)


def test_fetch_post_list_retries_then_raises_on_api_failure():
    """목록 API 파싱 실패(None)는 3회 재시도 후 중단한다.

    🔑 조용히 빈 목록으로 처리하면 「그 카테고리에 글이 없다」와 구분되지 않는다.
    """
    h = _load("harvest_cat28_29_full")
    calls = []

    def broken(cat, page):
        calls.append(page)
        return None

    with pytest.raises(RuntimeError, match="LIST_API_FAILED"):
        h.fetch_post_list(28, fetch=broken, sleep=lambda s: None)
    assert len(calls) == h.LIST_RETRIES


def test_category_counts_reads_post_cnt():
    h = _load("harvest_cat28_29_full")
    payload = {"isSuccess": True, "result": {"mylogCategoryList": [
        {"categoryNo": 28, "categoryName": "주식기법 분석", "postCnt": 150},
        {"categoryNo": 29, "categoryName": "시황이슈 정리", "postCnt": 282,
         "subCategoryList": [{"categoryNo": 99, "categoryName": "하위", "postCnt": 7}]},
    ]}}
    assert h.category_counts(payload) == {28: 150, 29: 282, 99: 7}


# ============================ Task 4 ============================

_HTML_HEAD = "<html><body>"
_HTML_TAIL = "</body></html>"

# ── 실제 응답에서 도출한 조각들 ────────────────────────────────────────────────
# 🔴 이번 사고의 원인이 「픽스처가 현실에 없는 계약을 고정」이었다. 아래 문자열은
#    전부 `posts28/` 의 실제 수집본(432건) 과 PC 응답 1건에서 **그대로 옮긴 것**이다.
#    타인의 본문은 담지 않는다 — 옮긴 것은 **마크업 골격**뿐이고 글은 자리표시자다.
#
# 🔴 결정적 조각: 네이버 모바일은 에디터 세대와 무관하게 **모든** 페이지 골격에
#    이 JS 한 줄을 넣는다. 옛 `classify_body` 는 `"se-main-container" in src` 로
#    판정했기에 **이 한 줄만으로** SE3 본문이 있다고 믿었고, 본문 0자 글 197건이
#    「진짜 이미지 전용」으로 위장했다. 픽스처에 이 줄이 없으면 그 결함을 재현할 수 없다.
DECOY_LAZYLOADER = (
    '<script type="text/javascript">\n'
    '    $Fn(function() {\n'
    '        var imageLazyLoader = new ImageLazyLoader('
    '".se-main-container,.__se_component_area");\n'
    '        imageLazyLoader.loadImages();\n'
    '    }).attach(window, "DOMContentLoaded");\n'
    '</script>')

# 응답이 스스로 밝히는 에디터 세대(432/432 존재, 목록 API 값과 432/432 일치).
_EDITOR_ATTR = "<div class=\"photo_view_property\" style=\"display: none\" editorversion='{v}'></div>"

# SE4 의 `se-viewer` 안에는 **UI 크롬**이 들어 있다(글쓴이·날짜·이웃추가·공유하기·신고하기).
# 본문 컨테이너를 `se-viewer` 로 잡으면 이것이 본문에 섞인다 — 실측으로 확인한 함정이라
# 픽스처에 그대로 넣어 회귀를 잡는다.
_SE4_CHROME = (
    '<div class="se-component se-documentTitle se-l-default ">'
    '<div class="se-section se-section-documentTitle">'
    '<p class="se-text-paragraph">글제목자리</p></div></div>'
    '<div class="blog_author"><strong class="ell">글쓴이자리</strong></div>'
    '<p class="blog_date">2021. 6. 6. 17:09</p>'
    '<a href="#" class="btn_buddyadd"><span class="sp"></span> 이웃추가</a>'
    '<div class="post_function_t1"><ul><li><a href="#">공유하기</a></li>'
    '<li><a href="#">URL복사</a></li><li><a href="#">신고하기</a></li></ul></div>')


def _page(inner, editor_version, pad=6000):
    """모바일 응답 한 장. 골격(크롬·JS 미끼·패딩)은 모든 세대가 공유한다."""
    return (_HTML_HEAD + _EDITOR_ATTR.format(v=editor_version)
            + '<div class="_postView">' + inner + "</div>"
            + DECOY_LAZYLOADER + ("<!--" + "x" * pad + "-->") + _HTML_TAIL)


def _post_html(paragraphs, n_img=0, pad=6000):
    """SE4(SmartEditor ONE, 2019~) 글 — 본문은 `se-main-container` 안에 있다.

    🔑 실제 응답과 같은 중첩을 쓴다: post_ct > se-viewer > (크롬) + se-main-container.
       크롬이 se-viewer **안**에 있다는 것이 실측이며, 그래서 본문 앵커는
       se-viewer 가 아니라 se-main-container 여야 한다.
    """
    body = "".join('<p class="se-text-paragraph se-text-paragraph-align-" style="">'
                   + p + "</p>" for p in paragraphs)
    imgs = "".join('<img src="x' + str(i) + '.png">' for i in range(n_img))
    return _page('<div class="post_ct   wrap_rabbit " id="viewTypeSelector">'
                 '<div class="se-viewer se-theme-default" lang="ko-KR">'
                 + _SE4_CHROME
                 + '<div class="se-main-container">'
                 '<div class="se-component se-text se-l-default">'
                 '<div class="se-component-content">' + body + imgs
                 + "</div></div></div></div></div>", 4, pad)


def _se3_html(paragraphs, n_img=0, pad=6000):
    """SE3(2018 무렵) 글 — `se_component_wrap sect_dsc __se_component_area` 안.

    ⚠️ 머리말 쪽에도 `<div class="se_component_wrap">` 가 따로 있다(실측).
       앵커가 `__se_component_area` 를 함께 요구하지 않으면 머리말을 본문으로 잡는다.
    """
    body = "".join('<div class="se_component se_paragraph default">'
                   '<p class="se_textarea">' + p + "</p></div>" for p in paragraphs)
    imgs = "".join('<img src="y' + str(i) + '.png">' for i in range(n_img))
    return _page('<div class="post_ct   se3_view " id="viewTypeSelector">'
                 '<div id="SEDOC-1544336565523" class="se_doc_viewer se_body_wrap se_m"'
                 ' data-docversion="1.0">'
                 '<div class="se_component_wrap"><p class="se_textarea">머리말자리</p></div>'
                 '<div class="se_component_wrap sect_dsc __se_component_area">'
                 + body + imgs + "</div></div></div>", 3, pad)


def _se2_html(paragraphs=("본문 첫 줄", "둘째 줄"), n_img=0, pad=6000):
    """SE2(구 에디터) 글 — 모바일은 본문을 `post_ct` 안에 **클래스 없는 `<p>`** 로 준다.

    🔴 여기가 이번 손실의 핵심이다. 본문은 왔는데 `se-text-paragraph` 가 하나도 없어
       옛 추출기가 0자를 냈고, 옛 판정기는 위 JS 미끼를 보고 「SE3 본문 있음 +
       이미지 전용」이라고 적었다. 195건이 이 형태였다.
    """
    body = "".join('<p><span style="" _foo="FONT-FAMILY: 돋움,dotum">' + p
                   + "</span></p>" for p in paragraphs)
    imgs = "".join('<img src="z' + str(i) + '.png">' for i in range(n_img))
    return _page('<div class="post_ct  " id="viewTypeSelector">'
                 '<div style="font-size:10pt;" _foo="view">' + body + imgs
                 + "</div></div>", 2, pad)


def _pc_html(paragraphs=("PC 본문 첫 줄",), pad=6000):
    """PC 엔드포인트 응답 — 본문이 `#postViewArea` 에 있다(harvest_fallback.py 의 마커).

    모바일 응답에는 `postViewArea` 가 **0건**, PC 응답에는 `viewTypeSelector` 가
    **0건**이다(양쪽 실측) — 그래서 이 한 쌍으로 출처를 판별할 수 있다.
    """
    body = "".join("<p>" + p + "</p>" for p in paragraphs)
    return (_HTML_HEAD + '<div id="postViewArea">'
            '<div id="post-view220000968295" class="post-view pcol2">' + body
            + "</div></div>" + ("<!--" + "x" * pad + "-->") + _HTML_TAIL)


def _body_missing_html(pad=6000):
    """본문 컨테이너가 **하나도** 없는 응답 — 본문을 못 받았다.

    ⚠️ JS 미끼는 그대로 들어 있다. 즉 「`se-main-container` 라는 문자열이 있다」는
       사실만으로는 본문 유무를 하나도 말해 주지 못한다는 것을 이 픽스처가 고정한다.
       크기는 문턱(5,000B)을 통과한다.
    """
    return (_HTML_HEAD + _EDITOR_ATTR.format(v=2)
            + '<div class="blog_header">머리말</div><img src="ui_icon.png">'
            + DECOY_LAZYLOADER + ("<!--" + "x" * pad + "-->") + _HTML_TAIL)


def _entry(log_no="221000000001", cat=28):
    return {"log_no": log_no, "category": cat, "post_date": "2021-03-04", "title": "t"}


def test_harvest_one_extracts_text_and_counts_images(tmp_path, monkeypatch):
    h = _load("harvest_cat28_29_full")
    monkeypatch.setattr(h.C, "POSTS_DIR", tmp_path / "posts28")
    monkeypatch.setattr(h.C, "TEXT_DIR", tmp_path / "text28")
    h.C.POSTS_DIR.mkdir(parents=True)
    h.C.TEXT_DIR.mkdir(parents=True)

    html_src = _post_html(["상승폭 45~48%", "하락폭 통계"], n_img=3)
    meta = h.harvest_one(_entry(), fetch=lambda log_no: html_src)

    assert meta["img_count"] == 3
    assert meta["image_only"] is False
    content = (h.C.TEXT_DIR / (meta["text_file"])).read_text(encoding="utf-8")
    assert "상승폭 45~48%" in content
    assert "하락폭 통계" in content
    # 🔑 raw HTML 을 그대로 쓰는 회귀를 잡는다 — 위 부분문자열은 HTML 안에도 그대로
    #    들어 있어(태그 없는 순문자열) 그것만으로는 「추출했다」의 증거가 되지 않는다.
    assert "<p" not in content, "텍스트 파일에 HTML 태그가 남아 있다"
    assert "<img" not in content
    assert "x" * 100 not in content, "패딩 주석이 텍스트에 새어 들어왔다"
    assert meta["text_len"] > 0
    assert meta["text_len"] == len(content)


def test_harvest_one_marks_image_only_when_no_text(tmp_path, monkeypatch):
    """🔑 텍스트 0자 글은 ④단계로 **자동 승격**돼야 한다.

    텍스트가 없으면 「이미지를 가리키는 문장」도 없어서, 선별 기준을 그냥 통과해
    아무도 안 본 채 끝난다.
    """
    h = _load("harvest_cat28_29_full")
    monkeypatch.setattr(h.C, "POSTS_DIR", tmp_path / "posts28")
    monkeypatch.setattr(h.C, "TEXT_DIR", tmp_path / "text28")
    h.C.POSTS_DIR.mkdir(parents=True)
    h.C.TEXT_DIR.mkdir(parents=True)

    meta = h.harvest_one(_entry(), fetch=lambda log_no: _post_html([], n_img=9))
    assert meta["text_len"] == 0
    assert meta["image_only"] is True
    assert meta["img_count"] == 9


def test_harvest_one_retries_short_html_then_raises(tmp_path, monkeypatch):
    h = _load("harvest_cat28_29_full")
    monkeypatch.setattr(h.C, "POSTS_DIR", tmp_path / "posts28")
    monkeypatch.setattr(h.C, "TEXT_DIR", tmp_path / "text28")
    h.C.POSTS_DIR.mkdir(parents=True)
    h.C.TEXT_DIR.mkdir(parents=True)

    calls = []

    def short(log_no):
        calls.append(log_no)
        return "<html>too short</html>"

    with pytest.raises(RuntimeError, match="HTML_TOO_SHORT"):
        h.harvest_one(_entry(), fetch=short, retries=3, sleep=lambda s: None)
    assert len(calls) == 3, "재시도 횟수가 다르다"


def test_harvest_one_retries_param_is_not_hardcoded(tmp_path, monkeypatch):
    """🔑 판별력 자체 점검 — 위 테스트는 retries=3 만 쓰므로 구현이 `range(retries)`
    대신 `range(3)` 을 하드코딩해도 똑같이 통과한다(Task 3 dedup 테스트와 동형 결함).

    `retries` 를 기본값과 다른 2 로 호출해 실제로 파라미터에 묶였는지를 가른다.
    """
    h = _load("harvest_cat28_29_full")
    monkeypatch.setattr(h.C, "POSTS_DIR", tmp_path / "posts28")
    monkeypatch.setattr(h.C, "TEXT_DIR", tmp_path / "text28")
    h.C.POSTS_DIR.mkdir(parents=True)
    h.C.TEXT_DIR.mkdir(parents=True)

    calls = []

    def short(log_no):
        calls.append(log_no)
        return "<html>too short</html>"

    with pytest.raises(RuntimeError, match="HTML_TOO_SHORT"):
        h.harvest_one(_entry(), fetch=short, retries=2, sleep=lambda s: None)
    assert len(calls) == 2, "retries=2 인데 3회 시도했다 — 하드코딩 의심"


# ============================ Task 5 ============================

def test_v1_passes_when_listing_matches_files():
    v = _load("verify_cat2829")
    r = v.v1_coverage({"1", "2", "3"}, {"1", "2", "3"},
                      post_cnt={28: 2, 29: 1}, listed_cnt={28: 2, 29: 1})
    assert r["status"] == "PASS"
    assert r["missing"] == [] and r["extra"] == []
    assert r["post_cnt_delta"] == {28: 0, 29: 0}


def test_v1_fails_on_missing_file():
    """우리 책임 구간 — 목록에 있는데 파일이 없다."""
    v = _load("verify_cat2829")
    r = v.v1_coverage({"1", "2", "3"}, {"1", "2"},
                      post_cnt={28: 3}, listed_cnt={28: 3})
    assert r["status"] == "FAIL"
    assert r["missing"] == ["3"]


def test_v1_fails_on_extra_file():
    v = _load("verify_cat2829")
    r = v.v1_coverage({"1", "2"}, {"1", "2", "9"},
                      post_cnt={28: 2}, listed_cnt={28: 2})
    assert r["status"] == "FAIL"
    assert r["extra"] == ["9"]


def test_v1_records_post_cnt_gap_without_failing():
    """🔑 postCnt 어긋남은 네이버 쪽 사정(비공개·삭제)일 수 있다.

    실패로 처리하면 우리 잘못이 아닌 것 때문에 파이프라인이 서고,
    무시하면 근거 없이 「전수」를 주장하게 된다. ⇒ 기록하되 통과.
    """
    v = _load("verify_cat2829")
    r = v.v1_coverage({"1", "2"}, {"1", "2"},
                      post_cnt={28: 150, 29: 282}, listed_cnt={28: 148, 29: 282})
    assert r["status"] == "PASS"
    assert r["post_cnt_delta"] == {28: -2, 29: 0}


def test_v1_handles_unknown_post_cnt():
    """카테고리 API 가 postCnt 를 안 주면 None 으로 남긴다 — 0 으로 세지 않는다."""
    v = _load("verify_cat2829")
    r = v.v1_coverage({"1"}, {"1"}, post_cnt={28: None}, listed_cnt={28: 1})
    assert r["status"] == "PASS"
    assert r["post_cnt_delta"] == {28: None}


def test_v1_missing_and_extra_are_sorted():
    """🔑 인터페이스가 「정렬 list」를 약속한다 — 원소 1개짜리 픽스처로는 증명되지 않는다.

    Task 9 가 이 목록을 게이트 출력으로 사람에게 보여준다.
    sorted() 를 list() 로 바꾸면 이 테스트가 실패해야 한다.
    """
    v = _load("verify_cat2829")
    r = v.v1_coverage({"30", "4", "200", "1"}, {"1", "99", "10"},
                      post_cnt={28: 4}, listed_cnt={28: 4})
    assert r["status"] == "FAIL"
    assert r["missing"] == ["200", "30", "4"], "문자열 정렬이 아니다"
    assert r["extra"] == ["10", "99"]


# ============================ Task 6 ============================

import csv as _csv
import json as _json


def _write_batch(d, name, rows):
    p = d / name
    with open(str(p), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(_json.dumps(r, ensure_ascii=False) + "\n")
    return p


def test_load_batches_merges_all_jsonl(tmp_path):
    b = _load("build_claims_cat2829")
    _write_batch(tmp_path, "b01.jsonl", [_good_row(claim_id="a-1")])
    _write_batch(tmp_path, "b02.jsonl", [_good_row(claim_id="b-1"), _good_row(claim_id="b-2")])
    rows = b.load_batches(tmp_path)
    assert len(rows) == 3
    assert {r["claim_id"] for r in rows} == {"a-1", "b-1", "b-2"}


def test_load_batches_rejects_schema_violation(tmp_path):
    b = _load("build_claims_cat2829")
    _write_batch(tmp_path, "b01.jsonl", [_good_row(vs_v1="Nope")])
    with pytest.raises(ValueError, match="BAD_VS_V1"):
        b.load_batches(tmp_path)


def test_write_ledgers_splits_quote_column(tmp_path):
    """공개판에는 원문 인용이 없어야 한다."""
    b = _load("build_claims_cat2829")
    pub, quo = tmp_path / "pub.csv", tmp_path / "quo.csv"
    b.write_ledgers([_good_row()], pub, quo)

    with open(str(pub), encoding="utf-8-sig") as f:
        pub_rows = list(_csv.DictReader(f))
    with open(str(quo), encoding="utf-8-sig") as f:
        quo_rows = list(_csv.DictReader(f))

    assert "quote" not in pub_rows[0]
    assert quo_rows[0]["quote"] == "평균은 점 하나인데 현실은 퍼짐"
    assert pub_rows[0]["claim_id"] == quo_rows[0]["claim_id"]


def test_v2_fails_when_a_post_has_no_row():
    """🔑 배치를 조용히 건너뛴 것을 잡는다.

    「글당 최소 1행」 이 강제되므로, 원장에 없는 log_no 는 정독이 안 된 것이다.
    """
    v = _load("verify_cat2829")
    rows = [_good_row(log_no="1"), _good_row(log_no="2")]
    r = v.v2_ledger_coverage(rows, {"1", "2", "3"})
    assert r["status"] == "FAIL"
    assert r["missing_lognos"] == ["3"]


def test_v2_passes_when_every_post_has_at_least_one_row():
    v = _load("verify_cat2829")
    rows = [_good_row(log_no="1"), _good_row(log_no="1"), _good_row(log_no="2")]
    r = v.v2_ledger_coverage(rows, {"1", "2"})
    assert r["status"] == "PASS"
    assert r["rows"] == 3 and r["posts"] == 2


# ---- Task 6 갭 보강 (판별력 자체 점검 — 브리프 테스트가 안 잡는 계약들) ----

def test_load_batches_is_sorted_by_filename_and_preserves_line_order(tmp_path):
    """🔑 병합 순서가 결정적이지 않으면 원장 diff 가 실행마다 흔들린다.

    파일명 역순으로 써도 항상 파일명 오름차순으로, 파일 내부는 줄 순서대로 나와야 한다.
    """
    b = _load("build_claims_cat2829")
    _write_batch(tmp_path, "b02.jsonl", [_good_row(claim_id="b-1"), _good_row(claim_id="b-2")])
    _write_batch(tmp_path, "a01.jsonl", [_good_row(claim_id="a-1")])
    rows = b.load_batches(tmp_path)
    assert [r["claim_id"] for r in rows] == ["a-1", "b-1", "b-2"], "파일명·줄 순서가 아니다"


def test_load_batches_ignores_non_jsonl_files(tmp_path):
    """배치 디렉토리에 *.jsonl 이 아닌 파일이 섞여도 무시해야 한다."""
    b = _load("build_claims_cat2829")
    (tmp_path / "README.txt").write_text("이것은 JSON 이 아니다", encoding="utf-8")
    _write_batch(tmp_path, "b01.jsonl", [_good_row(claim_id="only-1")])
    rows = b.load_batches(tmp_path)
    assert len(rows) == 1
    assert rows[0]["claim_id"] == "only-1"


def test_load_batches_error_message_has_file_and_line_number(tmp_path):
    """🔑 인터페이스가 「파일:줄 사유」 형태를 명시로 약속한다.

    브리프 테스트는 `match="BAD_VS_V1"` 로 메시지 어딘가에 그 문자열이 있는지만 본다
    (re.search 는 부분일치). 파일명·줄번호가 아예 안 들어가도 그 테스트는 통과한다.
    여기서는 위반이 3번째 줄에 있을 때 그 줄번호가 정확히 찍히는지를 고정한다.
    """
    b = _load("build_claims_cat2829")
    _write_batch(tmp_path, "zz.jsonl", [
        _good_row(claim_id="ok-1"),
        _good_row(claim_id="ok-2"),
        _good_row(claim_id="bad-1", vs_v1="Nope"),
    ])
    with pytest.raises(ValueError) as ei:
        b.load_batches(tmp_path)
    msg = str(ei.value)
    assert msg.startswith("zz.jsonl:3 "), "파일명:줄번호 접두사가 다르다 — " + msg
    assert "BAD_VS_V1" in msg


def test_write_ledgers_column_order_matches_schema(tmp_path):
    """🔑 "열 순서는 claims_schema 가 정한다" — 헤더 순서 자체를 고정한다.

    DictReader 로만 읽으면 열 순서가 바뀌어도 딕셔너리 키 존재 여부만 보므로 안 잡힌다.
    """
    b = _load("build_claims_cat2829")
    s = _load("claims_schema")
    pub, quo = tmp_path / "pub.csv", tmp_path / "quo.csv"
    b.write_ledgers([_good_row()], pub, quo)

    with open(str(pub), encoding="utf-8-sig", newline="") as f:
        pub_header = next(_csv.reader(f))
    with open(str(quo), encoding="utf-8-sig", newline="") as f:
        quo_header = next(_csv.reader(f))

    assert pub_header == list(s.PUBLIC_COLUMNS)
    assert quo_header == list(s.COLUMNS)


def test_write_ledgers_preserves_row_order_and_all_rows(tmp_path):
    """행이 여럿일 때 전부·같은 순서로 두 판본에 쓰여야 한다(브리프 테스트는 1행뿐)."""
    b = _load("build_claims_cat2829")
    pub, quo = tmp_path / "pub.csv", tmp_path / "quo.csv"
    rows = [_good_row(claim_id="r1"), _good_row(claim_id="r2"), _good_row(claim_id="r3")]
    b.write_ledgers(rows, pub, quo)

    with open(str(pub), encoding="utf-8-sig") as f:
        pub_ids = [r["claim_id"] for r in _csv.DictReader(f)]
    with open(str(quo), encoding="utf-8-sig") as f:
        quo_ids = [r["claim_id"] for r in _csv.DictReader(f)]

    assert pub_ids == ["r1", "r2", "r3"]
    assert quo_ids == ["r1", "r2", "r3"]


def test_v2_missing_lognos_are_sorted():
    """🔑 Task 5 와 동형 결함 계열 — 브리프의 v2 FAIL 테스트는 missing_lognos 원소가 1개뿐이라
    `sorted()` 를 `list()` 로 바꿔도 우연히 통과한다(정렬 여부를 판별 못 함).

    문자열 정렬(사전식)이 되는지를 여러 원소로 고정한다. "200" < "30" < "4" 는
    숫자 정렬이면 절대 나오지 않는 순서다.
    """
    v = _load("verify_cat2829")
    rows = [_good_row(log_no="1")]
    r = v.v2_ledger_coverage(rows, {"30", "4", "200", "1"})
    assert r["status"] == "FAIL"
    assert r["missing_lognos"] == ["200", "30", "4"], "문자열 정렬이 아니다"


def test_v2_fail_still_reports_rows_and_posts():
    """FAIL 이어도 rows·posts 집계가 조기 반환으로 생략되면 안 된다."""
    v = _load("verify_cat2829")
    rows = [_good_row(log_no="1"), _good_row(log_no="1"), _good_row(log_no="2")]
    r = v.v2_ledger_coverage(rows, {"1", "2", "3"})
    assert r["status"] == "FAIL"
    assert r["rows"] == 3
    assert r["posts"] == 2


def test_v2_passes_even_with_extra_lognos_not_expected():
    """🔑 V2 는 「모든 글이 최소 1행 있는가」만 본다 — 기대 밖 log_no 가 섞여도 실패가 아니다.

    V1(v1_coverage)의 `extra` 개념과 섞으면(대칭 차집합) 이 테스트가 실패해야 한다.
    """
    v = _load("verify_cat2829")
    rows = [_good_row(log_no="1"), _good_row(log_no="2"), _good_row(log_no="99")]
    r = v.v2_ledger_coverage(rows, {"1", "2"})
    assert r["status"] == "PASS"
    assert r["rows"] == 3 and r["posts"] == 3


def test_main_merges_batches_and_writes_ledgers(tmp_path, monkeypatch, capsys):
    """load_batches 와 write_ledgers 가 main() 에서 실제로 이어붙었는지 — 부품 테스트만으론
    배선 자체(어느 경로에서 읽어 어느 경로에 쓰는지)가 안 잡힌다."""
    b = _load("build_claims_cat2829")
    batch_dir = tmp_path / "claims_batches"
    batch_dir.mkdir()
    pub, quo = tmp_path / "claims_cat2829.csv", tmp_path / "claims_cat2829_quoted.csv"

    monkeypatch.setattr(b.C, "CLAIMS_BATCH_DIR", batch_dir)
    monkeypatch.setattr(b.C, "CLAIMS_PUBLIC_CSV", pub)
    monkeypatch.setattr(b.C, "CLAIMS_QUOTED_CSV", quo)

    _write_batch(batch_dir, "b01.jsonl", [_good_row(log_no="1", claim_id="1-1")])
    _write_batch(batch_dir, "b02.jsonl", [_good_row(log_no="2", claim_id="2-1")])

    rc = b.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert pub.exists() and quo.exists()
    with open(str(pub), encoding="utf-8-sig") as f:
        assert len(list(_csv.DictReader(f))) == 2
    assert out == "주장 2 행 · 글 2 건\n", "요약 출력 전체가 계약과 다르다 — " + repr(out)

    # 🔴 저작권 경계 — write_ledgers(rows, public_path, quoted_path) 인자 순서가
    #    main() 에서 뒤바뀌면 quote(타인의 원문 인용)가 커밋 대상 claims_cat2829.csv 로
    #    새어 들어간다. 위의 존재/행수/출력 단언 3개는 이 누출을 전혀 못 잡는다 —
    #    스왑된 상태에서도 파일 2개가 생기고 행수도 2고 출력도 똑같기 때문이다.
    #    양방향을 전부 고정한다: 한쪽만 걸면 "둘 다 public 열로 씀" 같은 다른 회귀를
    #    못 잡는다.
    pub_header = open(str(b.C.CLAIMS_PUBLIC_CSV), encoding="utf-8-sig", newline="").readline()
    quo_header = open(str(b.C.CLAIMS_QUOTED_CSV), encoding="utf-8-sig", newline="").readline()
    assert "quote" not in pub_header, "🔴 커밋되는 원장에 원문 인용이 새어 들어갔다"
    assert "quote" in quo_header, "로컬 전용 원장에 quote 가 없다 = 인자가 뒤바뀌었다"


# ============================ Task 7 ============================

def _claim_row(log_no, date, topic, numbers, vs="conflict", anchor="§2"):
    return _good_row(log_no=log_no, claim_id=log_no + "-1", post_date=date,
                     topic=topic, numbers=numbers, vs_v1=vs, v1_anchor=anchor)


def test_v5_flags_same_topic_changing_numbers_over_time():
    """누적 통계 1만 → 12,500 → 13,503 은 모순이 아니라 개정이다."""
    v = _load("verify_cat2829")
    rows = [
        _claim_row("1", "2025-08-01", "⑤데이터기반", "10000건"),
        _claim_row("2", "2025-10-01", "⑤데이터기반", "12500건"),
        _claim_row("3", "2026-07-01", "⑤데이터기반", "13503건"),
    ]
    cands = v.v5_revision_candidates(rows)
    assert len(cands) == 1
    assert cands[0]["topic"] == "⑤데이터기반"
    assert [t["numbers"] for t in cands[0]["timeline"]] == ["10000건", "12500건", "13503건"]


def test_v5_does_not_flag_across_different_topics():
    """🔑 오경보를 안 내는 성질도 고정한다.

    안 하면 다음 사람이 '전부 후보로 올리면 되지' 로 되돌려도 아무도 못 잡는다.
    """
    v = _load("verify_cat2829")
    rows = [
        _claim_row("1", "2025-08-01", "⑤데이터기반", "10000건"),
        _claim_row("2", "2025-10-01", "③분할매수", "12500건"),
    ]
    assert v.v5_revision_candidates(rows) == []


def test_v5_does_not_flag_identical_numbers():
    v = _load("verify_cat2829")
    rows = [
        _claim_row("1", "2025-08-01", "⑤데이터기반", "13503건"),
        _claim_row("2", "2026-07-01", "⑤데이터기반", "13503건"),
    ]
    assert v.v5_revision_candidates(rows) == []


def test_v5_ignores_rows_not_marked_conflict():
    """이미 revision 으로 표시된 것은 재판정 대상이 아니다."""
    v = _load("verify_cat2829")
    rows = [
        _claim_row("1", "2025-08-01", "⑤데이터기반", "10000건", vs="revision"),
        _claim_row("2", "2026-07-01", "⑤데이터기반", "13503건", vs="revision"),
    ]
    assert v.v5_revision_candidates(rows) == []


# ---- Task 7 갭 보강 (판별력 자체 점검 — 브리프 테스트가 안 잡는 계약들) ----

def test_v5_groups_by_topic_and_anchor_not_topic_alone():
    """🔑 계약은 「같은 (topic, v1_anchor)」다 — topic 만으로 묶으면 다른 절(§)의
    별개 규칙을 같은 개정 이력으로 섞어버린다.

    같은 topic 에 서로 다른 anchor 두 묶음을 넣는다. topic 만으로 묶는 결함이면
    4행이 한 후보로 합쳐지지만, 올바른 구현은 anchor 별로 별개 후보 2개를 낸다.
    🔑 동시에 출력 리스트의 정렬 계약(anchor 오름차순)도 고정한다 — 입력을
    §2 그룹을 먼저 주고 §1 그룹을 나중에 줘서, 정렬 없이 입력 순서를 그대로
    돌려주면 이 테스트가 실패하게 만든다.
    """
    v = _load("verify_cat2829")
    rows = [
        # §2 그룹을 먼저 입력한다 — 출력은 anchor 오름차순이어야 하므로 §1 이 앞에 와야 한다.
        _claim_row("21", "2025-08-01", "⑤데이터기반", "10000건", anchor="§2"),
        _claim_row("22", "2026-07-01", "⑤데이터기반", "13503건", anchor="§2"),
        _claim_row("11", "2025-08-01", "⑤데이터기반", "45%", anchor="§1"),
        _claim_row("12", "2026-07-01", "⑤데이터기반", "48%", anchor="§1"),
    ]
    cands = v.v5_revision_candidates(rows)
    assert len(cands) == 2, "topic 만으로 묶었다면 1개로 합쳐졌을 것이다"
    assert [c["v1_anchor"] for c in cands] == ["§1", "§2"], "출력이 anchor 오름차순 정렬이 아니다"
    assert [t["numbers"] for t in cands[0]["timeline"]] == ["45%", "48%"]
    assert [t["numbers"] for t in cands[1]["timeline"]] == ["10000건", "13503건"]


def test_v5_timeline_is_sorted_chronologically_regardless_of_input_order():
    """🔑 Task 5·6 에서 두 번 연속 갭이었던 정렬 계약 — 브리프 테스트는 입력이
    이미 시간순이라 「정렬 안 해도 우연히 통과」할 수 있다. 여기서는 입력을
    일부러 뒤섞어 timeline 이 실제로 post_date 기준 재정렬되는지를 가른다.
    """
    v = _load("verify_cat2829")
    rows = [
        _claim_row("3", "2026-07-01", "⑤데이터기반", "13503건"),
        _claim_row("1", "2025-08-01", "⑤데이터기반", "10000건"),
        _claim_row("2", "2025-10-01", "⑤데이터기반", "12500건"),
    ]
    cands = v.v5_revision_candidates(rows)
    assert len(cands) == 1
    timeline = cands[0]["timeline"]
    assert [t["post_date"] for t in timeline] == ["2025-08-01", "2025-10-01", "2026-07-01"]
    assert [t["numbers"] for t in timeline] == ["10000건", "12500건", "13503건"]
    assert [t["log_no"] for t in timeline] == ["1", "2", "3"]
    assert [t["claim_id"] for t in timeline] == ["1-1", "2-1", "3-1"]


def test_v5_filters_out_non_conflict_rows_within_mixed_group():
    """같은 (topic, anchor) 안에 conflict 아닌 행이 섞여 있으면 timeline 에서 빠져야 한다.

    브리프의 `test_v5_ignores_rows_not_marked_conflict` 는 **전부** non-conflict 인
    경우만 본다 — 필터가 통째로 꺼져 있어도(전부 통과) 그 뒤 `len(grp) < 2` 나
    numbers 동일성 체크가 우연히 같은 결론(빈 리스트)에 도달할 여지가 있다.
    여기서는 conflict 2건 + agree 1건을 같은 묶음에 섞어, 필터가 정확히
    conflict 행만 남기는지(개수·내용 둘 다)를 직접 확인한다.
    """
    v = _load("verify_cat2829")
    rows = [
        _claim_row("9", "2025-01-01", "⑤데이터기반", "999건", vs="agree"),
        _claim_row("1", "2025-08-01", "⑤데이터기반", "10000건"),
        _claim_row("3", "2026-07-01", "⑤데이터기반", "13503건"),
    ]
    cands = v.v5_revision_candidates(rows)
    assert len(cands) == 1
    timeline = cands[0]["timeline"]
    assert len(timeline) == 2, "non-conflict 행(999건)이 timeline 에 새어 들어갔다"
    assert [t["numbers"] for t in timeline] == ["10000건", "13503건"]


def test_v5_single_conflict_row_amid_other_vs_v1_values_is_not_a_candidate():
    """필터링 후 conflict 행이 1건만 남으면(다른 값 섞여 있어도) 후보가 아니다."""
    v = _load("verify_cat2829")
    rows = [
        _claim_row("1", "2025-01-01", "③분할매수", "100건", vs="new"),
        _claim_row("2", "2025-06-01", "③분할매수", "200건", vs="conflict"),
    ]
    assert v.v5_revision_candidates(rows) == []


# ============================ Task 8 ============================

def _meta(log_no, cat, date, text_len):
    return {"log_no": str(log_no), "category": cat, "post_date": date,
            "text_len": text_len, "image_only": text_len == 0}


def test_make_batches_respects_target_size():
    b = _load("batch_cat2829")
    metas = [_meta(i, 28, "2024-01-0" + str(i % 9 + 1), 25000) for i in range(1, 10)]
    batches = b.make_batches(metas, target_chars=60000)
    assert all(sum(m["text_len"] for m in batch) <= 60000 or len(batch) == 1
               for batch in batches)


def test_make_batches_covers_every_post_exactly_once():
    """🔑 분할이 글을 잃거나 겹치면 V2 가 잡기 전에 여기서 잡는다."""
    b = _load("batch_cat2829")
    metas = [_meta(i, 28 if i % 2 else 29, "2024-01-01", 7000) for i in range(1, 31)]
    batches = b.make_batches(metas, target_chars=20000)
    flat = [m["log_no"] for batch in batches for m in batch]
    assert sorted(flat) == sorted(m["log_no"] for m in metas)
    assert len(flat) == len(set(flat))


def test_make_batches_is_deterministic():
    b = _load("batch_cat2829")
    metas = [_meta(i, 28, "2024-01-01", 5000) for i in range(1, 21)]
    assert b.make_batches(metas, 20000) == b.make_batches(list(reversed(metas)), 20000)


def test_make_batches_keeps_oversized_post_alone():
    b = _load("batch_cat2829")
    metas = [_meta(1, 28, "2024-01-01", 500000), _meta(2, 28, "2024-01-02", 1000)]
    batches = b.make_batches(metas, target_chars=20000)
    assert [m["log_no"] for m in batches[0]] == ["1"]


# ---- Task 8 갭 보강 (판별력 자체 점검 — 브리프 테스트가 안 잡는 계약들) ----

def test_make_batches_sort_key_precedence_is_category_then_date_then_lognos():
    """🔑 브리프의 `test_make_batches_is_deterministic` 은 category·post_date 가
    **상수**라 log_no 하나만 바뀐다 — 정렬 키를 `m["log_no"]` 로만 구현해도
    (reversed 입력 == 원본 입력) 은 여전히 성립해 실패하지 않는다(실측 확인함).

    여기서는 세 키가 전부 다르게 움직이도록 배치해 (category, post_date, log_no)
    3중 정렬이 실제로 그 순서로 동작하는지 직접 고정한다 — log_no 단독 정렬,
    (post_date, log_no) 정렬(category 무시), (category, log_no, post_date)
    정렬(log_no 가 date 보다 우선) 전부 아래 fixture 에서 다른 순서를 낸다.
    """
    b = _load("batch_cat2829")
    a = _meta("999", 28, "2024-05-01", 10)   # cat28, 가장 늦은 date, 가장 큰 log_no
    bb = _meta("500", 28, "2024-01-01", 10)  # cat28, 가장 이른 date 그룹, log_no 큰 쪽
    c = _meta("100", 29, "2023-01-01", 10)   # cat29 — date·log_no 는 전부 가장 작지만 category 가 커서 맨 뒤
    d = _meta("200", 28, "2024-01-01", 10)   # cat28, 가장 이른 date 그룹, log_no 작은 쪽
    e = _meta("150", 28, "2024-03-01", 10)   # cat28, 중간 date, log_no 는 그룹 내 최소

    for order in (
        [a, bb, c, d, e],
        [e, d, c, bb, a],
        [c, a, d, bb, e],
    ):
        batches = b.make_batches(order, target_chars=100000)
        assert len(batches) == 1, "target 이 커서 한 배치에 다 들어가야 한다"
        got = [m["log_no"] for m in batches[0]]
        assert got == ["200", "500", "150", "999", "100"], (
            "정렬 순서가 (category, post_date, log_no) 가 아니다 — " + repr(got))


def test_make_batches_groups_posts_that_fit_together_not_one_per_batch():
    """🔑 브리프의 `test_make_batches_respects_target_size` 단언은
    `... or len(batch) == 1` 을 포함한다 — **모든 배치를 원소 1개로 쪼개는**
    망가진 구현(`[[m] for m in ordered]`)도 이 단언을 우연히 통과한다(실측 확인함).
    `test_make_batches_covers_every_post_exactly_once`·`_is_deterministic`·
    `_keeps_oversized_post_alone` 도 마찬가지로 통과한다 — 넷 다 갭이었다.

    5건(각 3000자, target 10000)을 넣어 정확한 배치 구성 자체를 고정한다 —
    누적이 10000 을 넘기 직전(4번째에서)에 끊겨 [1,2,3] 과 [4,5] 두 배치가
    나와야 한다. 원소 1개짜리 배치 5개나, 전부 한 배치로 뭉친 결과는 모두 FAIL.
    """
    b = _load("batch_cat2829")
    metas = [_meta(i, 28, "2024-01-01", 3000) for i in range(1, 6)]
    batches = b.make_batches(metas, target_chars=10000)
    got = [[m["log_no"] for m in batch] for batch in batches]
    assert got == [["1", "2", "3"], ["4", "5"]], (
        "배치 구성이 다르다 — 원소 1개씩 쪼개졌거나 하나로 뭉쳤을 수 있다: " + repr(got))


# ================= 브랜치 리뷰 교정 (C1·C2·I1·I2·I4·M1) =================
#
# 실행 직전 리뷰가 잡은 블로커들. 전부 「경보가 조용하다」로 통과하던 계열이라
# 각 항목마다 **양방향**(결함이면 실패 / 정상이면 통과)을 고정한다.

def _install_tmp_dirs(h, tmp_path, monkeypatch):
    """수집 산출물 경로를 전부 tmp 로 돌린다. 네트워크·저장소를 건드리지 않는다."""
    for name, sub in (("POSTS_DIR", "posts28"), ("TEXT_DIR", "text28"),
                      ("IMAGES_DIR", "images28"), ("CLAIMS_BATCH_DIR", "claims_batches")):
        monkeypatch.setattr(h.C, name, tmp_path / sub)
    monkeypatch.setattr(h.C, "CATLIST_JSON", tmp_path / "catlist_28_29.json")
    monkeypatch.setattr(h.C, "POSTMETA_JSON", tmp_path / "postmeta_28_29.json")
    monkeypatch.setattr(h.C, "HARVEST_FAIL_JSON", tmp_path / "harvest_fail_28_29.json")
    monkeypatch.setattr(h.C, "VERIFY_LOG", tmp_path / "verify_cat2829.log")
    h.C.ensure_dirs()


def _fake_api(by_cat):
    """{cat: [item, ...]} 를 1페이지에 전부 주는 가짜 목록 API."""
    def api_json(cat, page, item_count=30):
        return {"result": {"items": by_cat.get(cat, []) if page == 1 else []}}
    return api_json


def _fake_category_list(counts):
    return lambda: {"isSuccess": True, "result": {"mylogCategoryList": [
        {"categoryNo": c, "postCnt": n} for c, n in counts.items()]}}


# ---------------------------- C1: logNo 타입 ----------------------------

def test_fetch_post_list_normalizes_int_lognos_to_str():
    """🔴 목록 API 는 logNo 를 **int** 로 준다(858/858 실측). 여기서 str 로 고정해야
    이후 전 경로가 한 타입만 본다. 정규화를 걷어내면 키가 int 가 되어 실패한다.
    """
    h = _load("harvest_cat28_29_full")
    got = h.fetch_post_list(28, fetch=_fake_pages([[_item(224364189017, MS_2025),
                                                   _item(224364189018, MS_2025)]]),
                            sleep=lambda s: None)
    assert set(got) == {"224364189017", "224364189018"}
    assert all(isinstance(k, str) for k in got), (
        "logNo 가 str 로 정규화되지 않았다 — " + repr([type(k).__name__ for k in got]))


def test_fetch_post_list_dedupes_int_and_str_forms_of_same_logno():
    """🔑 정규화가 **중복 판정**에도 걸려야 한다.

    같은 글이 1페이지엔 int, 2페이지엔 str 로 오면(또는 그 반대) 정규화 없이는
    서로 다른 키로 보여 종료 조건이 안 걸리고 같은 글을 두 번 담는다.
    """
    h = _load("harvest_cat28_29_full")
    pages = [[_item(224364189017, MS_2025)],
             [dict(_item(224364189017, MS_2025), logNo="224364189017")],
             [_item(224364189099, MS_2025)]]
    fetched = []

    def fetch(cat, page):
        fetched.append(page)
        return _fake_pages(pages)(cat, page)

    got = h.fetch_post_list(28, fetch=fetch, sleep=lambda s: None)
    assert set(got) == {"224364189017"}
    assert fetched == [1, 2], "int/str 형태 차이를 새 글로 봤다 = 정규화가 빠졌다"


def test_stem_accepts_int_log_no():
    """🔴 재현했던 TypeError: `str + int`. 파일명이 타입 때문에 갈리면 안 된다."""
    h = _load("harvest_cat28_29_full")
    as_int = h._stem({"log_no": 224364189017, "category": 28, "post_date": "2021-03-04"})
    as_str = h._stem({"log_no": "224364189017", "category": 28, "post_date": "2021-03-04"})
    assert as_int == as_str == "28_20210304_224364189017"


def test_harvest_one_raises_html_too_short_not_typeerror_for_int_log_no(tmp_path, monkeypatch):
    """🔑 진짜 실패 사유가 TypeError 로 **덮이면** 안 된다.

    수정 전에는 int logNo + 짧은 응답이면 HTML_TOO_SHORT 를 만들다가 TypeError 로 죽어
    「본문을 못 받았다」는 사실이 사라졌다.
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="HTML_TOO_SHORT:224364189017"):
        h.harvest_one(_entry(log_no=224364189017), fetch=lambda n: "<html>짧다</html>",
                      retries=1, sleep=lambda s: None)


def test_harvest_one_meta_log_no_is_str_for_int_entry(tmp_path, monkeypatch):
    """메타의 log_no 는 V1 이 집합 비교에 쓰는 값이다 — 반드시 str."""
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    meta = h.harvest_one(_entry(log_no=224364189017),
                         fetch=lambda n: _post_html(["본문"]), sleep=lambda s: None)
    assert meta["log_no"] == "224364189017"
    assert isinstance(meta["log_no"], str)


def test_build_catalog_normalizes_keys_and_values_to_str(tmp_path, monkeypatch):
    """🔴 V1 배선 오탐의 근원 — catalog['posts'] 는 JSON **객체**라 재적재 후 키가 항상
    str 인데, postmeta 는 JSON **배열**이라 원 타입을 유지한다. 둘이 어긋나면
    전건이 「missing 이면서 동시에 extra」로 잡힌다(432 missing + 432 extra).
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    monkeypatch.setattr(h.C, "category_list", _fake_category_list({28: 1, 29: 1}))
    monkeypatch.setattr(h.C, "api_json", _fake_api({
        28: [_item(224364189017, MS_2025, 28)],
        29: [_item(224364189018, MS_2025, 29)]}))

    catalog = h.build_catalog()
    assert set(catalog["posts"]) == {"224364189017", "224364189018"}
    assert all(isinstance(k, str) for k in catalog["posts"])
    assert all(isinstance(e["log_no"], str) for e in catalog["posts"].values())
    # JSON 왕복 후에도 키와 값이 같은 타입이어야 한다.
    reloaded = _json.loads(h.C.CATLIST_JSON.read_text(encoding="utf-8"))
    assert set(reloaded["posts"]) == {str(e["log_no"]) for e in reloaded["posts"].values()}


def test_build_catalog_normalizes_even_if_listing_yields_int_keys(tmp_path, monkeypatch):
    """정규화 지점 ②를 **단독으로** 고정한다.

    ①(fetch_post_list)이 int 키를 흘려도 카탈로그는 str 로 나와야 한다. 이 테스트가
    없으면 ①만 있는 구현과 ①②가 다 있는 구현을 구분할 수 없다.
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    monkeypatch.setattr(h.C, "category_list", _fake_category_list({28: 1, 29: 0}))
    monkeypatch.setattr(h, "fetch_post_list",
                        lambda cat: ({224364189017: _item(224364189017, MS_2025, 28)}
                                     if cat == 28 else {}))
    catalog = h.build_catalog()
    assert set(catalog["posts"]) == {"224364189017"}
    assert catalog["posts"]["224364189017"]["log_no"] == "224364189017"


# ---------------------------- I1: 제목 키 ----------------------------

@pytest.mark.parametrize("title_key,label", [
    (TITLE_KEY_0801, "2026-08-01 관측(4키)"),
    (TITLE_KEY_0805, "2026-08-05 라이브(44키)"),
])
def test_build_catalog_reads_whichever_title_key_the_api_used(
        tmp_path, monkeypatch, title_key, label):
    """🔴 제목 키가 **시점에 따라 다르다**. 두 관측 다 실측이며 서로 반대다.

    한쪽만 계약으로 못 박아 두 번 틀렸다 — 옛 코드는 08-01 에서, 그 교정판은
    08-05 라이브에서(Task 9 첫 API 호출에서 가드에 걸려 멈췄다).
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    monkeypatch.setattr(h.C, "category_list", _fake_category_list({28: 1, 29: 0}))
    monkeypatch.setattr(h.C, "api_json", _fake_api({
        28: [_item(224364189017, MS_2025, 28, title_key=title_key)]}))
    catalog = h.build_catalog()
    assert catalog["posts"]["224364189017"]["title"] == "제목 224364189017", label


def test_build_catalog_accepts_the_real_live_44_key_item(tmp_path, monkeypatch):
    """🔑 픽스처를 **현실에서 도출**한다 — 2026-08-05 라이브 응답의 키 44개 전부.

    이번 사고의 원인이 정확히 「픽스처가 현실에 없는 계약을 고정」이었다.
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    monkeypatch.setattr(h.C, "category_list", _fake_category_list({28: 1, 29: 0}))
    monkeypatch.setattr(h.C, "api_json", _fake_api({28: [_live_item()]}))
    catalog = h.build_catalog()
    entry = catalog["posts"]["224361924061"]
    assert entry["title"] == "제목 224361924061"
    assert entry["log_no"] == "224361924061"
    # 목록 API 가 주는 글별 에디터 세대 — C2 판정을 독립 경로로 대조할 재료다.
    assert entry["smart_editor_version"] == 4


def test_build_catalog_records_none_when_editor_version_absent(tmp_path, monkeypatch):
    """🔑 부가정보는 부재가 곧 결함이 아니다 — 조용히 None 이면 된다.

    제목과 **정책이 다른** 이유를 고정한다: 제목은 산출물의 내용이라 소리를 내야 하고,
    이건 대조용이라 없으면 없는 대로 기록한다.
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    monkeypatch.setattr(h.C, "category_list", _fake_category_list({28: 1, 29: 0}))
    monkeypatch.setattr(h.C, "api_json", _fake_api({28: [_item(1, MS_2025, 28)]}))
    catalog = h.build_catalog()
    assert catalog["posts"]["1"]["smart_editor_version"] is None


def test_build_catalog_raises_when_no_known_title_key_is_present(tmp_path, monkeypatch):
    """🔑 반대 방향 — 아는 키가 **하나도** 없으면 조용한 빈 문자열이 아니라 소리가 나야 한다.

    이 성질이 이번에 실제로 작동했다(Task 9 를 첫 글에서 세웠다). 잃으면 안 된다.
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    monkeypatch.setattr(h.C, "category_list", _fake_category_list({28: 1, 29: 0}))
    monkeypatch.setattr(h.C, "api_json", _fake_api({
        28: [{"logNo": 224364189017, "addDate": MS_2025, "categoryNo": 28,
              "subject": "또 바뀐 이름"}]}))
    with pytest.raises(RuntimeError, match="LIST_ITEM_NO_TITLE"):
        h.build_catalog()


# ---- item_title 네 경우를 직접 고정한다 ----

def test_item_title_uses_title_when_only_title_present():
    h = _load("harvest_cat28_29_full")
    assert h.item_title({"title": "가"}) == "가"


def test_item_title_uses_inspect_message_when_only_that_present():
    """← 2026-08-05 현재 라이브가 이 경우다."""
    h = _load("harvest_cat28_29_full")
    assert h.item_title({"titleWithInspectMessage": "나"}) == "나"


def test_item_title_prefers_title_when_both_present():
    h = _load("harvest_cat28_29_full")
    assert h.item_title({"title": "가", "titleWithInspectMessage": "나"}) == "가"


def test_item_title_error_lists_the_actual_keys():
    """🔑 메시지에 **실제 키 목록**이 있어야 다음 사람이 새 이름을 바로 안다.

    `match=` 는 부분일치라 키 목록이 통째로 빠져도 위 raise 테스트는 통과한다.
    """
    h = _load("harvest_cat28_29_full")
    with pytest.raises(RuntimeError) as ei:
        h.item_title({"logNo": 1, "subject": "새 이름", "addDate": 0})
    msg = str(ei.value)
    assert "LIST_ITEM_NO_TITLE" in msg
    assert "'subject'" in msg and "'logNo'" in msg, "실제 키 목록이 없다 — " + msg


def test_item_title_falls_back_when_preferred_key_is_blank():
    """🔑 「존재」가 아니라 「값이 있는가」로 고른다.

    `title` 이 있지만 비었고 다른 키에 값이 있으면 그 값을 써야 한다. 존재만 보면
    빈 문자열을 반환해 I1 이 고치려던 무음 손실이 좁은 형태로 되살아난다.
    """
    h = _load("harvest_cat28_29_full")
    assert h.item_title({"title": "   ", "titleWithInspectMessage": "실제 제목"}) == "실제 제목"
    assert h.item_title({"title": None, "titleWithInspectMessage": "실제 제목"}) == "실제 제목"


def test_item_title_returns_blank_without_raising_when_all_values_blank():
    """⚠️ 값이 빈 제목은 **막지 않는다**(판단: 아래 근거).

    키는 있는데 값만 비었다면 스키마 변화가 아니라 그 글의 성질일 수 있다.
    글 하나 때문에 432건을 죽이는 것은 I4 에서 고친 실패 방식과 같다.
    대신 침묵하지도 않는다 — main() 이 건수와 log_no 를 출력한다(아래 테스트).
    """
    h = _load("harvest_cat28_29_full")
    assert h.item_title({"title": "", "titleWithInspectMessage": ""}) == ""
    assert h.item_title({"title": "   "}) == ""


def test_harvest_main_reports_blank_titles_without_failing(tmp_path, monkeypatch, capsys):
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    monkeypatch.setattr(h.time, "sleep", lambda s: None)
    monkeypatch.setattr(h.C, "category_list", _fake_category_list({28: 2, 29: 0}))
    monkeypatch.setattr(h.C, "api_json", _fake_api({28: [
        dict(_item(1, MS_2025, 28), titleWithInspectMessage=""),
        _item(2, MS_2025, 28)]}))
    monkeypatch.setattr(h.C, "fetch_html", lambda n: _post_html(["본문"]))

    rc = h.main()
    out = capsys.readouterr().out
    assert rc == 0, "빈 제목은 실패가 아니다"
    assert "제목이 빈 글 1 건" in out, "빈 제목이 조용히 지나갔다 — " + out


def test_harvest_main_stays_quiet_when_no_blank_titles(tmp_path, monkeypatch, capsys):
    """🔑 오경보를 안 내는 성질도 고정한다."""
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    monkeypatch.setattr(h.time, "sleep", lambda s: None)
    monkeypatch.setattr(h.C, "category_list", _fake_category_list({28: 1, 29: 0}))
    monkeypatch.setattr(h.C, "api_json", _fake_api({28: [_item(1, MS_2025, 28)]}))
    monkeypatch.setattr(h.C, "fetch_html", lambda n: _post_html(["본문"]))
    h.main()
    assert "제목이 빈 글" not in capsys.readouterr().out


# ------------------- C2: 본문 유무 판별 (2026-08-05 재교정) -------------------
#
# 🔴 무엇이 틀렸었나: 옛 판정기는 `"se-main-container" in src` 라는 **부분문자열**을
#    SE3 본문 신호로 썼다. 그 문자열은 본문이 0자인 글의 **페이지 골격 JS 한 줄**에도
#    들어 있다(위 DECOY_LAZYLOADER). 그래서 Task 9 실전 수집에서
#      · `text_len == 0` 197건이 전부 `body_container="se3"` + `image_only=True`
#      · 「본문 미수신」은 **0건** 으로 보고됨
#    즉 본문을 한 글자도 못 읽은 글들이 「진짜 이미지 전용 글」로 위장했다.
#  ⇒ 판정 축을 **「본문 문단이 실제로 추출됐는가」**로 바꾼다. 컨테이너는 **여는 태그**로만
#    인정하고, 「미수신」과 「이미지 전용」은 *본문 안에 이미지가 있는가* 로 가른다.

_CLASSIFY_SEQ = [0]


def _classify(tmp_path, monkeypatch, html_src):
    """⚠️ log_no 를 매번 다르게 준다 — 같은 값이면 `harvest_one` 의 존재-스킵이 걸려
    **한 테스트 안의 두 번째 호출부터 첫 HTML 을 되돌려준다**(실제로 여기서 겪었다).
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    _CLASSIFY_SEQ[0] += 1
    return h.harvest_one(_entry(log_no="22100000%04d" % _CLASSIFY_SEQ[0]),
                         fetch=lambda n: html_src, sleep=lambda s: None)


def test_marker_alone_does_not_mean_the_body_arrived(tmp_path, monkeypatch):
    """🔴 이번 결함의 **직접 재현** — 본문이 없는데 `se-main-container` 문자열은 있다.

    이 픽스처에는 본문 컨테이너 태그가 하나도 없고, 그 이름을 담은 JS 미끼만 있다.
    부분문자열 판정으로 되돌리면 여기서 `image_only=True` 가 나와 실패한다.
    """
    src = _body_missing_html()
    assert "se-main-container" in src, "미끼가 없으면 이 결함을 재현할 수 없다"
    assert '<div class="se-main-container' not in src, "픽스처에 진짜 컨테이너가 있다"
    meta = _classify(tmp_path, monkeypatch, src)
    assert meta["html_bytes"] >= 5000, "크기 문턱을 통과하는 응답이어야 재현이 된다"
    assert meta["text_len"] == 0
    assert meta["body_missing"] is True
    assert meta["image_only"] is False, "🔴 본문 미수신이 이미지 전용으로 위장됐다"
    assert meta["body_container"] == "none"


@pytest.mark.parametrize("make,gen,ver", [
    (_se2_html, "se2", 2),
    (_se3_html, "se3", 3),
    (_post_html, "se4", 4),
])
def test_every_editor_generation_yields_body_text(tmp_path, monkeypatch, make, gen, ver):
    """🔴 세 세대 **전부** 본문이 나와야 한다.

    옛 추출기는 `se-text-paragraph`(SE4) 하나만 읽어 SE2 195건·SE3 2건을
    **0자로** 만들었다. 세대별 마크업은 서로 완전히 다르다(전부 실측):
      SE2 클래스 없는 `<p><span>` · SE3 `<p class="se_textarea">` ·
      SE4 `<p class="se-text-paragraph">`
    """
    meta = _classify(tmp_path, monkeypatch, make(["첫 문단입니다", "둘째 문단입니다"]))
    assert meta["text_len"] > 0, "🔴 " + gen + " 본문이 또 0자다"
    assert meta["body_missing"] is False
    assert meta["image_only"] is False
    assert meta["body_container"] == gen
    assert meta["page_editor_version"] == ver, "응답이 밝힌 세대를 못 읽었다"
    h = _load("harvest_cat28_29_full")
    content = (h.C.TEXT_DIR / meta["text_file"]).read_text(encoding="utf-8")
    assert "첫 문단입니다" in content and "둘째 문단입니다" in content


def test_body_text_excludes_ui_chrome(tmp_path, monkeypatch):
    """🔴 경계가 틀리면 정독 에이전트가 **남의 글을 저자의 주장으로** 기록한다.

    SE4 는 글쓴이·날짜·「이웃추가」·「공유하기」·「신고하기」가 `se-viewer` **안**에
    들어 있다(실측). 본문 앵커를 se-viewer 로 잡으면 그게 전부 본문에 섞인다.
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    meta = h.harvest_one(_entry(), fetch=lambda n: _post_html(["진짜 본문"]),
                         sleep=lambda s: None)
    content = (h.C.TEXT_DIR / meta["text_file"]).read_text(encoding="utf-8")
    assert "진짜 본문" in content
    for chrome in ("이웃추가", "공유하기", "URL복사", "신고하기", "글쓴이자리"):
        assert chrome not in content, "🔴 UI 크롬이 본문에 섞였다: " + chrome


def test_se3_anchor_does_not_grab_the_header_component_wrap(tmp_path, monkeypatch):
    """🔑 SE3 머리말에도 `se_component_wrap` 이 따로 있다 — `__se_component_area` 를
    함께 요구하지 않으면 머리말을 본문으로 집는다.
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    meta = h.harvest_one(_entry(), fetch=lambda n: _se3_html(["진짜 본문"]),
                         sleep=lambda s: None)
    content = (h.C.TEXT_DIR / meta["text_file"]).read_text(encoding="utf-8")
    assert "진짜 본문" in content
    assert "머리말자리" not in content, "🔴 머리말 컴포넌트를 본문으로 집었다"


def test_true_image_only_post_is_image_only_not_missing(tmp_path, monkeypatch):
    """🔑 반대 방향 — 진짜 이미지 전용 글은 여전히 `image_only` 여야 한다.

    이걸 안 걸면 「전부 body_missing 으로 찍으면 되지」로 되돌려도 아무도 못 잡는다.
    가르는 기준은 **본문 컨테이너 안에 이미지가 있는가**다.
    """
    meta = _classify(tmp_path, monkeypatch, _post_html([], n_img=9))
    assert meta["text_len"] == 0
    assert meta["image_only"] is True
    assert meta["body_missing"] is False, "진짜 이미지 전용 글이 미수신으로 오분류됐다"
    assert meta["body_container"] == "se4"
    assert meta["body_img_count"] == 9


def test_empty_container_with_no_images_is_missing_not_image_only(tmp_path, monkeypatch):
    """🔑 컨테이너는 왔는데 글자도 이미지도 없다 = 빈 본문. 글이 아니다.

    「이미지 전용」이라 부르면 아무도 안 읽은 채 모든 게이트가 초록이 된다.
    """
    meta = _classify(tmp_path, monkeypatch, _post_html([], n_img=0))
    assert meta["text_len"] == 0
    assert meta["image_only"] is False, "🔴 빈 본문이 이미지 전용으로 위장됐다"
    assert meta["body_missing"] is True
    assert meta["body_container"] == "se4"


def test_body_img_count_ignores_ui_icons_outside_the_body(tmp_path, monkeypatch):
    """🔑 `image_only` 판정이 **본문 안** 이미지를 봐야 하는 이유.

    페이지 전체를 세면 UI 아이콘 때문에 어떤 응답이든 이미지가 있는 것처럼 보여
    판별력이 0 이 된다. 본문 밖 아이콘 1장 + 본문 안 0장 = 이미지 전용이 아니다.
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    src = _post_html([], n_img=0).replace("</body>", '<img src="ui_icon.png"></body>')
    meta = h.harvest_one(_entry(), fetch=lambda n: src, sleep=lambda s: None)
    assert meta["img_count"] == 1, "페이지 전체 이미지 수가 안 세어졌다"
    assert meta["body_img_count"] == 0
    assert meta["image_only"] is False
    assert meta["body_missing"] is True


def test_normal_post_is_neither_image_only_nor_missing(tmp_path, monkeypatch):
    meta = _classify(tmp_path, monkeypatch, _post_html(["본문 있음"], n_img=2))
    assert meta["text_len"] > 0
    assert meta["image_only"] is False
    assert meta["body_missing"] is False
    assert meta["body_container"] == "se4"


# ---- 출처(source) — 「이 글은 어디서 왔나」를 산출물에서 되읽는다 ----

def test_source_is_read_from_the_saved_html_not_asserted(tmp_path, monkeypatch):
    """🔑 우리가 적은 메모가 아니라 **응답 자체**가 출처를 답해야 한다.

    모바일 응답에는 `viewTypeSelector` 가 432/432, PC 응답에는 `postViewArea` 가
    있고 서로 0건 겹친다(양쪽 실측). 메모 방식이면 파일과 어긋나도 아무도 모른다.
    """
    assert _classify(tmp_path, monkeypatch, _post_html(["본문"]))["source"] == "mobile"
    assert _classify(tmp_path, monkeypatch, _se2_html())["source"] == "mobile"
    assert _classify(tmp_path, monkeypatch, _pc_html())["source"] == "pc"
    assert _classify(tmp_path, monkeypatch, _body_missing_html())["source"] == "unknown"


def test_pc_endpoint_body_is_extracted_without_network(tmp_path, monkeypatch):
    """PC 응답(`#postViewArea`)에서도 본문이 나와야 한다 — 저장된 HTML 을 입력으로.

    실증(관리자 승인 하 1회 호출): logNo=220000968295 을 두 경로에서 뽑으면
    모바일 4,192자 / PC 4,192자 · **88줄 완전일치, 차이 0줄**.
    """
    meta = _classify(tmp_path, monkeypatch, _pc_html(["PC 본문 첫 줄", "PC 본문 둘째 줄"]))
    assert meta["body_container"] == "postview"
    assert meta["body_missing"] is False
    assert meta["text_len"] > 0
    h = _load("harvest_cat28_29_full")
    content = (h.C.TEXT_DIR / meta["text_file"]).read_text(encoding="utf-8")
    assert "PC 본문 첫 줄" in content and "PC 본문 둘째 줄" in content


def test_summary_shouts_about_missing_bodies_and_stays_quiet_otherwise():
    """🔑 양방향 — 미수신이 있으면 시끄럽고, 없으면 오경보를 안 낸다.

    「0건」이 성공인지 판별 불능인지 구분되게 **컨테이너·출처 분포**도 함께 낸다.
    이번 사고는 `legacy_editor` 가 정확히 0건이었는데 실제로는 197건이 사라진 것이다.
    """
    h = _load("harvest_cat28_29_full")
    ok = {"log_no": "1", "post_date": "2021-01-01", "text_len": 10,
          "image_only": False, "body_missing": False, "body_container": "se4",
          "source": "mobile"}
    bad = dict(ok, log_no="2", text_len=0, body_missing=True,
               body_container="none", source="unknown")
    quiet = h.summarize_bodies([ok])
    assert "본문 미수신 0 건" in quiet
    assert "본문 못 읽음" not in quiet, "오경보를 냈다"
    assert "'se4': 1" in quiet and "'mobile': 1" in quiet, "분포가 없다 — " + quiet
    loud = h.summarize_bodies([ok, bad])
    assert "본문 미수신 1 건" in loud
    assert "본문 못 읽음 2 2021-01-01" in loud, "빠진 글의 log_no 가 없다 — " + loud


def test_summary_flags_editor_version_disagreement_between_the_two_signals():
    """🔑 목록 API 와 응답 자체가 세대를 다르게 말하면 소리가 나야 한다(현재 432/432 일치).

    반대 방향(일치하면 조용)도 함께 고정한다.
    """
    h = _load("harvest_cat28_29_full")
    meta = {"log_no": "1", "post_date": "2021-01-01", "text_len": 10,
            "image_only": False, "body_missing": False, "body_container": "se4",
            "source": "mobile", "page_editor_version": 4}
    agree = {"posts": {"1": {"smart_editor_version": 4}}}
    disagree = {"posts": {"1": {"smart_editor_version": 2}}}
    assert "불일치 0 건" in h.summarize_bodies([meta], agree)
    out = h.summarize_bodies([meta], disagree)
    assert "불일치 1 건" in out and "'1'" in out, out


# ---------------------- I2: 배치 중복 (claim_id) ----------------------

def test_load_batches_rejects_duplicate_claim_id_across_files(tmp_path):
    """🔴 중복이 원장을 조용히 배로 불린다. V2 는 커버리지만 보므로 PASS 를 낸다.

    계획이 중복을 적극적으로 유발한다: V2 FAIL 시 배치 재실행 · Task 11 의 img_NN.jsonl ·
    Task 12 의 독립 재정독 출력이 전부 같은 디렉토리에 쌓인다.
    """
    b = _load("build_claims_cat2829")
    _write_batch(tmp_path, "b01.jsonl", [_good_row(claim_id="1-1")])
    _write_batch(tmp_path, "b02.jsonl", [_good_row(claim_id="1-1")])
    with pytest.raises(ValueError, match="DUPLICATE_CLAIM_ID:1-1"):
        b.load_batches(tmp_path)


def test_load_batches_rejects_duplicate_claim_id_within_one_file(tmp_path):
    b = _load("build_claims_cat2829")
    _write_batch(tmp_path, "b01.jsonl", [_good_row(claim_id="x-1"),
                                         _good_row(claim_id="x-1")])
    with pytest.raises(ValueError, match="DUPLICATE_CLAIM_ID:x-1"):
        b.load_batches(tmp_path)


def test_duplicate_error_names_both_conflicting_locations(tmp_path):
    """🔑 「어느 파일 어느 줄이 충돌하는가」가 계약이다 — match= 는 부분일치라
    위치가 아예 없어도 위 두 테스트는 통과한다.
    """
    b = _load("build_claims_cat2829")
    _write_batch(tmp_path, "b01.jsonl", [_good_row(claim_id="a-1"),
                                         _good_row(claim_id="dup")])
    _write_batch(tmp_path, "b02.jsonl", [_good_row(claim_id="b-1"),
                                         _good_row(claim_id="b-2"),
                                         _good_row(claim_id="dup")])
    with pytest.raises(ValueError) as ei:
        b.load_batches(tmp_path)
    msg = str(ei.value)
    assert msg.startswith("b02.jsonl:3 "), "충돌한 쪽의 파일:줄이 앞에 없다 — " + msg
    assert "b01.jsonl:2" in msg, "먼저 있던 쪽의 위치가 없다 — " + msg


def test_load_batches_still_accepts_distinct_claim_ids(tmp_path):
    """🔑 반대 방향 — 유일성 검사가 정상 원장을 막으면 안 된다."""
    b = _load("build_claims_cat2829")
    _write_batch(tmp_path, "b01.jsonl", [_good_row(claim_id="1-1"), _good_row(claim_id="1-2")])
    _write_batch(tmp_path, "b02.jsonl", [_good_row(claim_id="2-1")])
    assert len(b.load_batches(tmp_path)) == 3


# ------------------- I4: 재개 · 개별 실패 내성 -------------------

def test_harvest_one_skips_already_downloaded_file(tmp_path, monkeypatch):
    """🔴 432건 중 431번째에서 실패하면 전량 재요청이었다.

    선행 2본(harvest_cat28_29.py:62 · harvest_bodies.py:70)의 존재-스킵을 승계한다.
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    entry = _entry()
    saved = _post_html(["이미 받아 둔 본문"])
    (h.C.POSTS_DIR / (h._stem(entry) + ".html")).write_text(saved, encoding="utf-8")

    calls = []

    def fetch(log_no):
        calls.append(log_no)
        return _post_html(["새로 받은 본문"])

    meta = h.harvest_one(entry, fetch=fetch, sleep=lambda s: None)
    assert calls == [], "이미 받아 둔 글을 다시 요청했다"
    assert meta["from_cache"] is True
    assert "이미 받아 둔 본문" in (h.C.TEXT_DIR / meta["text_file"]).read_text(encoding="utf-8")


def test_harvest_one_refetches_when_saved_file_is_too_small(tmp_path, monkeypatch):
    """🔑 반대 방향 — 잘린 파일이 남아 있으면 **다시 받아야** 한다.

    안 걸면 「파일만 있으면 스킵」으로 되돌려도 안 잡히고, 잘린 응답이 영구히 굳는다.
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    entry = _entry()
    (h.C.POSTS_DIR / (h._stem(entry) + ".html")).write_text("<html>잘림</html>",
                                                            encoding="utf-8")
    calls = []

    def fetch(log_no):
        calls.append(log_no)
        return _post_html(["온전한 본문"])

    meta = h.harvest_one(entry, fetch=fetch, sleep=lambda s: None)
    assert len(calls) == 1, "잘린 파일을 그대로 재사용했다"
    assert meta["from_cache"] is False
    assert meta["text_len"] > 0


def _catalog_of(*entries):
    return {"post_cnt": {"28": len(entries)},
            "posts": {e["log_no"]: e for e in entries}}


def test_harvest_bodies_finishes_all_posts_despite_one_failure(tmp_path, monkeypatch):
    """🔴 계획서는 "비공개·삭제 글은 우리 잘못이 아니다" 라는데 코드는 글 하나에 즉사했다.

    끝까지 돌되 실패를 **성공으로 보고하지 않는다** — 목록으로 남긴다.
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    entries = [_entry(log_no="1"), _entry(log_no="2"), _entry(log_no="3")]

    def fetch(log_no):
        return "<html>비공개</html>" if str(log_no) == "2" else _post_html(["본문"])

    monkeypatch.setattr(h.C, "fetch_html", fetch)
    metas, failures = h.harvest_bodies(_catalog_of(*entries), sleep=lambda s: None)

    assert [m["log_no"] for m in metas] == ["1", "3"], "실패 뒤 글을 안 받았다"
    assert len(failures) == 1
    assert failures[0]["log_no"] == "2"
    assert "HTML_TOO_SHORT" in failures[0]["error"], "왜 실패했는지가 안 남았다"
    on_disk = _json.loads(h.C.HARVEST_FAIL_JSON.read_text(encoding="utf-8"))
    assert [f["log_no"] for f in on_disk] == ["2"]


def test_harvest_bodies_reports_zero_failures_when_all_succeed(tmp_path, monkeypatch):
    """🔑 반대 방향 — 정상 실행이 실패를 지어내면 안 된다(오경보 금지)."""
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    monkeypatch.setattr(h.C, "fetch_html", lambda n: _post_html(["본문"]))
    metas, failures = h.harvest_bodies(_catalog_of(_entry(log_no="1"), _entry(log_no="2")),
                                       sleep=lambda s: None)
    assert len(metas) == 2 and failures == []
    assert _json.loads(h.C.HARVEST_FAIL_JSON.read_text(encoding="utf-8")) == []


def test_harvest_bodies_overwrites_stale_failure_file(tmp_path, monkeypatch):
    """🔑 지난 실행의 실패 목록이 남아 이번 실행을 잘못 말하면 안 된다.

    거짓 경보(이미 고친 실패가 계속 보임)와 거짓 안심(반대 방향) 둘 다 막는다.
    """
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    h.C.HARVEST_FAIL_JSON.write_text('[{"log_no": "옛날실패"}]', encoding="utf-8")
    monkeypatch.setattr(h.C, "fetch_html", lambda n: _post_html(["본문"]))
    h.harvest_bodies(_catalog_of(_entry(log_no="1")), sleep=lambda s: None)
    assert _json.loads(h.C.HARVEST_FAIL_JSON.read_text(encoding="utf-8")) == []


def test_harvest_main_returns_nonzero_and_lists_failures(tmp_path, monkeypatch, capsys):
    """🔑 Task 9 게이트가 **볼 수 있어야** 한다 — 종료코드와 출력 둘 다에 드러난다."""
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    monkeypatch.setattr(h.time, "sleep", lambda s: None)   # main() 은 sleep 주입구가 없다
    monkeypatch.setattr(h.C, "category_list", _fake_category_list({28: 2, 29: 0}))
    monkeypatch.setattr(h.C, "api_json", _fake_api({
        28: [_item(1, MS_2025, 28), _item(2, MS_2025, 28)]}))
    monkeypatch.setattr(h.C, "fetch_html",
                        lambda n: "<html>비공개</html>" if str(n) == "2" else _post_html(["본문"]))

    rc = h.main()
    out = capsys.readouterr().out
    assert rc == 1, "실패가 있는데 성공으로 보고했다"
    assert "실패 1 건" in out
    assert "HTML_TOO_SHORT" in out


def test_harvest_main_returns_zero_when_everything_succeeds(tmp_path, monkeypatch, capsys):
    """🔑 반대 방향 — 정상 실행이 실패로 보고되면 게이트가 무의미해진다."""
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    monkeypatch.setattr(h.time, "sleep", lambda s: None)   # main() 은 sleep 주입구가 없다
    monkeypatch.setattr(h.C, "category_list", _fake_category_list({28: 1, 29: 1}))
    monkeypatch.setattr(h.C, "api_json", _fake_api({
        28: [_item(224364189017, MS_2025, 28)], 29: [_item(224364189018, MS_2025, 29)]}))
    monkeypatch.setattr(h.C, "fetch_html", lambda n: _post_html(["본문"]))
    assert h.main() == 0
    assert "실패 0 건" in capsys.readouterr().out


# ---------------------- M1: V1 배선 진입점 ----------------------

def _run_harvest_into(tmp_path, monkeypatch, h, items_by_cat, fetch=None):
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    monkeypatch.setattr(h.C, "category_list",
                        _fake_category_list({c: len(v) for c, v in items_by_cat.items()}))
    monkeypatch.setattr(h.C, "api_json", _fake_api(items_by_cat))
    monkeypatch.setattr(h.C, "fetch_html", fetch or (lambda n: _post_html(["본문"])))
    catalog = h.build_catalog()
    metas, failures = h.harvest_bodies(catalog, sleep=lambda s: None)
    return catalog, metas, failures


def test_verify_main_passes_end_to_end_with_int_lognos(tmp_path, monkeypatch, capsys):
    """🔴 C1 회귀 방지의 핵심 — **logNo 가 int 인 카탈로그**로 V1 배선이 통과하는가.

    부품 테스트(v1_coverage 단독)는 이미 다 통과하고 있었다. 배선이 없어서
    「JSON 객체 키(str) vs JSON 배열 값(원 타입)」 비교가 사각지대였고 거기서
    432 missing + 432 extra 오탐이 났을 것이다.
    """
    h = _load("harvest_cat28_29_full")
    v = _load("verify_cat2829")
    _run_harvest_into(tmp_path, monkeypatch, h, {
        28: [_item(224364189017, MS_2025, 28), _item(224364189018, MS_2025, 28)],
        29: [_item(224364189019, MS_2025, 29)]})
    monkeypatch.setattr(v.C, "CATLIST_JSON", h.C.CATLIST_JSON)
    monkeypatch.setattr(v.C, "POSTMETA_JSON", h.C.POSTMETA_JSON)
    monkeypatch.setattr(v.C, "VERIFY_LOG", h.C.VERIFY_LOG)

    rc = v.main()
    out = capsys.readouterr().out
    assert rc == 0, "int logNo 카탈로그에서 V1 이 통과하지 못했다 — " + out
    assert "V1 PASS" in out
    assert "목록 3 건" in out and "저장 3 건" in out


def test_verify_main_writes_result_to_log(tmp_path, monkeypatch):
    """판정이 VERIFY_LOG 에 append 로 남아야 한다(실행마다 한 줄)."""
    h = _load("harvest_cat28_29_full")
    v = _load("verify_cat2829")
    _run_harvest_into(tmp_path, monkeypatch, h, {28: [_item(1, MS_2025, 28)], 29: []})
    monkeypatch.setattr(v.C, "CATLIST_JSON", h.C.CATLIST_JSON)
    monkeypatch.setattr(v.C, "POSTMETA_JSON", h.C.POSTMETA_JSON)
    monkeypatch.setattr(v.C, "VERIFY_LOG", h.C.VERIFY_LOG)

    v.main()
    v.main()
    lines = [l for l in h.C.VERIFY_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2, "append 가 아니라 덮어썼다"
    rec = _json.loads(lines[0])
    assert rec["check"] == "V1" and rec["status"] == "PASS"
    assert rec["catalog_posts"] == 1 and rec["saved_posts"] == 1
    assert rec["checked_at"]


def test_verify_main_returns_1_when_a_post_was_not_saved(tmp_path, monkeypatch, capsys):
    """🔑 반대 방향 — FAIL 이 1 을 돌려줘야 Task 9 게이트가 선다."""
    h = _load("harvest_cat28_29_full")
    v = _load("verify_cat2829")
    catalog, metas, failures = _run_harvest_into(
        tmp_path, monkeypatch, h,
        {28: [_item(1, MS_2025, 28), _item(2, MS_2025, 28)], 29: []},
        fetch=lambda n: "<html>비공개</html>" if str(n) == "2" else _post_html(["본문"]))
    assert len(failures) == 1, "픽스처 전제: 한 건이 실패해야 한다"
    monkeypatch.setattr(v.C, "CATLIST_JSON", h.C.CATLIST_JSON)
    monkeypatch.setattr(v.C, "POSTMETA_JSON", h.C.POSTMETA_JSON)
    monkeypatch.setattr(v.C, "VERIFY_LOG", h.C.VERIFY_LOG)

    rc = v.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "V1 FAIL" in out
    assert "'2'" in out or '"2"' in out, "빠진 글의 log_no 가 출력에 없다 — " + out


def test_verify_main_shouts_when_post_cnt_is_entirely_unknown(tmp_path, monkeypatch, capsys):
    """🔑 post_cnt 가 전부 None = 「전수」의 **독립 증거가 없다**.

    중단하지는 않는다(사람이 판단). 다만 눈에 띄어야 한다.
    """
    h = _load("harvest_cat28_29_full")
    v = _load("verify_cat2829")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    monkeypatch.setattr(h.C, "category_list", lambda: None)      # 카테고리 API 실패
    monkeypatch.setattr(h.C, "api_json", _fake_api({28: [_item(1, MS_2025, 28)]}))
    monkeypatch.setattr(h.C, "fetch_html", lambda n: _post_html(["본문"]))
    catalog = h.build_catalog()
    h.harvest_bodies(catalog, sleep=lambda s: None)
    assert catalog["post_cnt"] == {"28": None, "29": None}, "픽스처 전제가 깨졌다"

    monkeypatch.setattr(v.C, "CATLIST_JSON", h.C.CATLIST_JSON)
    monkeypatch.setattr(v.C, "POSTMETA_JSON", h.C.POSTMETA_JSON)
    monkeypatch.setattr(v.C, "VERIFY_LOG", h.C.VERIFY_LOG)

    rc = v.main()
    out = capsys.readouterr().out
    assert rc == 0, "근거 부재는 우리 결함이 아니므로 FAIL 이 아니다"
    assert "독립 증거가 없다" in out


def test_verify_main_stays_quiet_when_post_cnt_is_known(tmp_path, monkeypatch, capsys):
    """🔑 오경보를 안 내는 성질도 고정한다 — 안 걸면 「항상 경고 출력」으로 되돌려도 안 잡힌다."""
    h = _load("harvest_cat28_29_full")
    v = _load("verify_cat2829")
    _run_harvest_into(tmp_path, monkeypatch, h, {28: [_item(1, MS_2025, 28)], 29: []})
    monkeypatch.setattr(v.C, "CATLIST_JSON", h.C.CATLIST_JSON)
    monkeypatch.setattr(v.C, "POSTMETA_JSON", h.C.POSTMETA_JSON)
    monkeypatch.setattr(v.C, "VERIFY_LOG", h.C.VERIFY_LOG)
    v.main()
    assert "독립 증거가 없다" not in capsys.readouterr().out


def test_verify_listed_counts_uses_same_key_type_as_post_cnt(tmp_path, monkeypatch):
    """🔑 post_cnt 는 JSON 객체라 키가 str 이다. listed_cnt 를 int 키로 세면
    `listed_cnt.get(cat, 0)` 이 전부 0 을 집어 delta 가 통째로 거짓이 된다.
    """
    h = _load("harvest_cat28_29_full")
    v = _load("verify_cat2829")
    catalog, _, _ = _run_harvest_into(tmp_path, monkeypatch, h, {
        28: [_item(1, MS_2025, 28), _item(2, MS_2025, 28)], 29: [_item(3, MS_2025, 29)]})
    counts = v.listed_counts(catalog)
    assert counts == {"28": 2, "29": 1}
    assert set(counts) == set(catalog["post_cnt"]), "post_cnt 와 키 타입이 어긋난다"

    monkeypatch.setattr(v.C, "CATLIST_JSON", h.C.CATLIST_JSON)
    monkeypatch.setattr(v.C, "POSTMETA_JSON", h.C.POSTMETA_JSON)
    monkeypatch.setattr(v.C, "VERIFY_LOG", h.C.VERIFY_LOG)
    v.main()
    rec = _json.loads(h.C.VERIFY_LOG.read_text(encoding="utf-8").splitlines()[0])
    assert rec["post_cnt_delta"] == {"28": 0, "29": 0}, "delta 가 0 이 아니다 = 키가 안 맞는다"


# ---- 실제 수집본 432건에 대한 회귀 (posts28/ 이 있을 때만) ----

def _corpus():
    """저장된 수집본 + 카탈로그. 없으면 skip — `posts28/` 는 타인 저작물이라 미추적이다."""
    c = _load("cat2829_common")
    if not (c.POSTS_DIR.exists() and c.CATLIST_JSON.exists()):
        pytest.skip("posts28/ 또는 catlist_28_29.json 이 없다 (수집 전 환경)")
    catalog = _json.loads(c.CATLIST_JSON.read_text(encoding="utf-8"))
    files = sorted(c.POSTS_DIR.glob("*.html"))
    if not files:
        pytest.skip("posts28/ 이 비어 있다")
    return c, catalog, files


def test_real_corpus_has_no_post_without_body():
    """🔴 이번 사고의 **실물 회귀**. 저장된 432건 중 본문이 안 나오는 글이 있으면 실패한다.

    수정 전 실측: 197건이 `text_len=0` 이면서 전부 `image_only=True`(위장).
    수정 후 실측: `body_missing` 0건 · `image_only` 0건 — 이 코퍼스에 진짜
    이미지 전용 글은 **한 건도 없었다**.
    """
    c, _, files = _corpus()
    bad = []
    for p in files:
        src = p.read_text(encoding="utf-8")
        cls = c.classify_body(src, c.html_to_text(src))
        if cls["body_missing"]:
            bad.append((p.name, cls["body_container"]))
    assert bad == [], "본문을 못 읽은 글이 남아 있다: " + repr(bad[:10])


def test_real_corpus_container_matches_the_editor_version_the_api_reported():
    """🔑 판정을 **독립 신호 두 개**와 대조한다 — 목록 API 의 `smartEditorVersion`,
    응답 자체의 `editorversion=`. 셋이 어긋나면 판정 근거가 흔들린 것이다.

    실측(432건): se2 195 / se3 2 / se4 235, 세 신호 **전건 일치**.
    """
    c, catalog, files = _corpus()
    gen_of = {"se2": 2, "se3": 3, "se4": 4}
    mismatch = []
    for p in files:
        log_no = p.stem.split("_")[-1]
        entry = catalog["posts"].get(log_no)
        if not entry or entry.get("smart_editor_version") is None:
            continue
        src = p.read_text(encoding="utf-8")
        container, _ = c.body_region(src)
        if gen_of.get(container) != entry["smart_editor_version"]:
            mismatch.append((p.name, container, entry["smart_editor_version"]))
        if c.page_editor_version(src) != entry["smart_editor_version"]:
            mismatch.append((p.name, "page_editor_version", c.page_editor_version(src)))
    assert mismatch == [], "세대 신호가 어긋난다: " + repr(mismatch[:10])


def test_real_corpus_body_text_is_free_of_ui_chrome_and_plausibly_sized():
    """🔴 경계 검증 — 사이드바·댓글·관련글이 섞이면 정독이 남의 글을 저자 주장으로 적는다.

    ⚠️ 길이도 함께 본다. 관리자의 급조 정규식은 같은 글에서 39,723자를 냈는데
       올바른 경계로는 4,192자였다 — **4만 자짜리가 즐비하면 경계가 틀린 것**이다.
       실측 상한: 12,668자(SE4). 20,000자 넘는 글이 하나라도 나오면 경계를 의심해야 한다.
    """
    c, _, files = _corpus()
    chrome = ("이웃추가", "본문 폰트 크기", "URL복사", "이 블로그 홈", "카테고리 이동")
    leaks, oversized = [], []
    for p in files:
        t = c.html_to_text(p.read_text(encoding="utf-8"))
        hit = [w for w in chrome if w in t]
        if hit:
            leaks.append((p.name, hit))
        if len(t) > 20000:
            oversized.append((p.name, len(t)))
    assert leaks == [], "UI 크롬이 본문에 섞였다: " + repr(leaks[:10])
    assert oversized == [], "본문이 비정상적으로 길다 = 경계 의심: " + repr(oversized[:10])


# ============ 재추출 (reextract_cat2829) — 네트워크 0회가 계약이다 ============

def _install_reextract_dirs(tmp_path, monkeypatch):
    r = _load("reextract_cat2829")
    for name, sub in (("POSTS_DIR", "posts28"), ("TEXT_DIR", "text28"),
                      ("IMAGES_DIR", "images28"), ("CLAIMS_BATCH_DIR", "claims_batches")):
        monkeypatch.setattr(r.C, name, tmp_path / sub)
    monkeypatch.setattr(r.C, "CATLIST_JSON", tmp_path / "catlist_28_29.json")
    monkeypatch.setattr(r.C, "POSTMETA_JSON", tmp_path / "postmeta_28_29.json")
    monkeypatch.setattr(r.C, "HARVEST_FAIL_JSON", tmp_path / "harvest_fail_28_29.json")
    r.C.ensure_dirs()
    return r


def _save_post(r, entry, html_src, suffix=".html"):
    stem = r.H._stem(entry)
    (r.C.POSTS_DIR / (stem + suffix)).write_text(html_src, encoding="utf-8")
    return stem


def test_reextract_recovers_body_from_already_saved_html(tmp_path, monkeypatch):
    """🔴 이번 복구의 핵심 — 본문은 **이미 디스크에 있었다.** 네트워크 없이 되살아나야 한다.

    실증: 같은 글(220000968295)을 모바일 저장본에서 4,192자, PC 응답에서 4,192자로
    뽑아 88줄 **완전일치**(차이 0줄) ⇒ PC 재수집으로 얻을 것이 없다.
    """
    r = _install_reextract_dirs(tmp_path, monkeypatch)
    entry = _entry(log_no="220000968295")
    _save_post(r, entry, _se2_html(["구 에디터 본문 첫 줄", "둘째 줄"]))
    meta = r.reextract_one(entry)
    assert meta["text_len"] > 0
    assert meta["body_missing"] is False and meta["image_only"] is False
    assert meta["body_container"] == "se2" and meta["source"] == "mobile"
    text = (r.C.TEXT_DIR / meta["text_file"]).read_text(encoding="utf-8")
    assert "구 에디터 본문 첫 줄" in text


def test_reextract_meta_contract_matches_harvest_one(tmp_path, monkeypatch):
    """🔑 두 경로가 다른 모양의 메타를 내면 하류가 어느 쪽을 보느냐로 조용히 갈린다."""
    r = _install_reextract_dirs(tmp_path, monkeypatch)
    entry = _entry(log_no="221000000009")
    src = _post_html(["본문"], n_img=2)
    _save_post(r, entry, src)
    from_reextract = r.reextract_one(entry)
    monkeypatch.setattr(r.H.C, "POSTS_DIR", r.C.POSTS_DIR)
    monkeypatch.setattr(r.H.C, "TEXT_DIR", r.C.TEXT_DIR)
    from_harvest = r.H.harvest_one(entry, fetch=lambda n: src, sleep=lambda s: None)
    assert set(from_reextract) == set(from_harvest), "메타 키 집합이 다르다"
    for k in from_harvest:
        assert from_reextract[k] == from_harvest[k], "키 " + k + " 값이 다르다"


def test_reextract_raises_loudly_when_html_was_never_saved(tmp_path, monkeypatch):
    """🔑 없는 글을 조용히 0자로 처리하지 않는다 — 「본문이 없다」와 구분돼야 한다."""
    r = _install_reextract_dirs(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="HTML_NOT_SAVED:221000000077"):
        r.reextract_one(_entry(log_no="221000000077"))


def test_reextract_prefers_pc_copy_over_mobile_original(tmp_path, monkeypatch):
    """🔑 PC 재수집본은 **별도 이름**으로 두고 모바일 원본을 덮지 않는다.

    모바일 원본은 「모바일이 무엇을 줬는가」의 유일한 증거다. 덮어쓰면 이번 결함의
    재현이 불가능해지고 「이 글은 어디서 왔나」를 파일로 답할 수 없다.
    """
    r = _install_reextract_dirs(tmp_path, monkeypatch)
    entry = _entry(log_no="220000968295")
    _save_post(r, entry, _body_missing_html())                       # 모바일 원본(본문 없음)
    _save_post(r, entry, _pc_html(["PC 로 되살린 본문"]), r.PC_SUFFIX)  # PC 보강본
    meta = r.reextract_one(entry)
    assert meta["source"] == "pc" and meta["body_missing"] is False
    assert "PC 로 되살린 본문" in (r.C.TEXT_DIR / meta["text_file"]).read_text(encoding="utf-8")
    stem = r.H._stem(entry)
    assert (r.C.POSTS_DIR / (stem + ".html")).exists(), "🔴 모바일 원본이 사라졌다"
    assert "se-main-container" in (r.C.POSTS_DIR / (stem + ".html")).read_text(encoding="utf-8")


def test_refetch_pc_targets_nothing_and_makes_no_request_when_bodies_are_fine(tmp_path, monkeypatch):
    """🔑 **요청 0회**가 계약이다. 2026-08-05 현재 본문 미수신은 0건이므로 대상도 0건이다."""
    r = _install_reextract_dirs(tmp_path, monkeypatch)
    calls = []
    got, failures = r.refetch_pc([], fetch=lambda n: calls.append(n) or "",
                                 sleep=lambda s: None)
    assert (got, failures, calls) == (0, [], [])


def test_refetch_pc_fetches_only_targets_and_skips_existing(tmp_path, monkeypatch):
    """존재-스킵 + 실패를 모아 끝까지 진행 — `harvest_one`/`harvest_bodies` 방식 승계."""
    r = _install_reextract_dirs(tmp_path, monkeypatch)
    done, todo, bad = _entry(log_no="1"), _entry(log_no="2"), _entry(log_no="3")
    _save_post(r, done, _pc_html(["이미 받아 둠"]) + "x" * r.PC_MIN_BYTES, r.PC_SUFFIX)
    calls = []

    def fetch(log_no):
        calls.append(str(log_no))
        if str(log_no) == "3":
            return "<html>비공개</html>"
        return _pc_html(["새로 받은 본문"]) + "x" * r.PC_MIN_BYTES

    got, failures = r.refetch_pc([done, todo, bad], fetch=fetch, sleep=lambda s: None)
    assert calls == ["2", "3"], "이미 받아 둔 글을 다시 요청했다 — " + repr(calls)
    assert got == 1
    assert [f["log_no"] for f in failures] == ["3"]
    assert "PC_FETCH_FAILED" in failures[0]["error"]
    assert (r.C.POSTS_DIR / (r.H._stem(todo) + r.PC_SUFFIX)).exists()


# ============================ Task 11: 본문 이미지 ============================
#
# 🔴 무엇이 틀렸었나 (2026-08-06 실측): `count_images()` 는 `<img>` 태그만 센다.
#    이 블로그의 SE2 세대(195글)는 그림을 `<img>` 로 싣지 않고 `<span thumburl>` 로
#    싣는다. 그 결과 **SE2 195글 중 127글이 「이미지 0장」**으로 찍혀 있었다.
#    T9 에서 `html_to_text` 가 SE4 문단만 읽어 197건이 0자가 된 것과 **같은 클래스**다.
#
# 아래 픽스처는 전부 `posts28/` 실제 수집본 433건에서 **마크업 골격만** 옮긴 것이다
# (타인의 그림·본문은 담지 않고 자산 이름은 자리표시자로 바꿨다).

# SE2 — 그림 슬롯이 `<span>` 속성이다. `?type=` 는 **값이 비어 있다**(1,986/1,986).
_SE2_SPAN = ('<span class="_img _inl fx" thumburl="https://mblogthumb-phinf.pstatic.net'
             '/20090910_132/mbc3110_x/{n}.jpg?type=">')
# SE2 저자 그림 — 외부(카페) 원본이라 dthumb 프록시로 나온다. `<차트-1>` 캡션 뒤 17장 실측.
# 🔴 `=`·`&` 가 HTML 엔티티로 이스케이프돼 있다(`&#x3D;` 955 · `&amp;` 961 실측).
_SE2_CONTENT_IMG = ('<img src="https://dthumb-phinf.pstatic.net/?src&#x3D;%22https%3A%2F%2F'
                    'cafefiles.pstatic.net%2F{n}.jpg%22&amp;type&#x3D;w1" alt=""'
                    ' class="fx _postImage">')
# SE2 링크카드 — 감싸는 `og _oglink` 가 유일한 단서다(안쪽 `<img>` 에는 class 가 **없다**).
_SE2_OGLINK = ('<div class="og _oglink"><div class="box"><div class="thumb b_size">'
               '<a href="https://news.example/1"><img src="https://dthumb-phinf.pstatic.net'
               '/?src=%22http%3A%2F%2Fimgnews.naver.net%2F{n}.jpg%22&type=f560_336"></a>'
               '</div><div class="txt"><div class="ell tit">남의 기사 제목</div></div>'
               '</div></div>')
# SE2 레이아웃 스페이서 84장 — 그림이 아니라 자리를 띄우는 1픽셀 gif.
_SE2_SPACER = '<img src="https://ssl.pstatic.net/static/blog/blank.gif" class="m20" alt="">'

# SE4 — `src` 는 **흐림 placeholder**(2,623/2,623 이 `?type=w80_blur`), 진짜는 lazy.
_SE4_IMG = ('<img src="https://mblogthumb-phinf.pstatic.net/{n}.png?type=w80_blur"'
            ' data-lazy-src="https://mblogthumb-phinf.pstatic.net/{n}.png?type=w800"'
            ' data-width="886" data-height="524" alt="" class="se-image-resource" />')
_SE4_OGLINK = ('<div class="se-component se-oglink se-l-image" id="SE-{n}">'
               '<div class="se-section se-section-oglink se-l-image se-section-align-">'
               '<div class="se-module se-module-oglink"><a href="https://news.example/{n}">'
               '<img src="https://dthumb-phinf.pstatic.net/?src&#x3D;%22https%3A%2F%2F'
               'imgnews.pstatic.net%2F{n}.jpg%22&amp;type&#x3D;ff120"'
               ' class="se-oglink-thumbnail-resource"></a></div></div></div>')
_SE4_STICKER = ('<img src="https://storep-phinf.pstatic.net/ogq_{n}/original_22.png'
                '?type=p100_100" alt="" class="se-sticker-image" />')
# GIF 는 `<video>` 로 온다(117건). 원본 GIF 는 `data-gif-url` 에 있다.
_SE4_VIDEO = ('<video src="https://mblogvideo-phinf.pstatic.net/{n}.gif?type=mp4w800"'
              ' loop="loop" muted="muted" playsinline class="_gifmp4"'
              ' data-gif-url="https://mblogthumb-phinf.pstatic.net/{n}.gif?type=w800"'
              ' poster="https://mblogthumb-phinf.pstatic.net/{n}.gif?type=w80_blur">'
              '</video>')


def _se2_page(parts, pad=6000):
    """SE2 본문에 조각들을 **준 순서 그대로** 넣는다."""
    return _page('<div class="post_ct  " id="viewTypeSelector">'
                 '<div style="font-size:10pt;" _foo="view">' + "".join(parts)
                 + "</div></div>", 2, pad)


def _se4_page(parts, pad=6000):
    return _page('<div class="post_ct   wrap_rabbit " id="viewTypeSelector">'
                 '<div class="se-viewer se-theme-default" lang="ko-KR">' + _SE4_CHROME
                 + '<div class="se-main-container">' + "".join(parts)
                 + "</div></div></div>", 4, pad)


def _urls(items):
    return [i["url"] for i in items]


def _kinds(items):
    return [i["kind"] for i in items]


# ---- C1: 경계는 body_region 안쪽뿐이다 ----

def test_body_images_ignore_everything_outside_the_body_region():
    """🔴 페이지 전체를 훑으면 블로거 프로필 썸네일이 **글당 4장** 섞인다(433/433 실측).

    계획서 초안(Task 11 Step 2)이 정확히 그 형태였다: `re.findall(r'<img[^>]+src="…"', src)`.
    """
    c = _load("cat2829_common")
    src = _se4_page([_SE4_IMG.format(n="본문그림")]).replace(
        "</body>",
        '<img src="https://blogpfthumb-phinf.pstatic.net/프로필.jpg?type=s1">'
        '<img src="https://ssl.pstatic.net/ui_icon.png"></body>')
    items = c.body_images(src)
    assert len(items) == 1, "본문 밖 이미지가 섞였다 — " + repr(_urls(items))
    assert "blogpfthumb" not in items[0]["url"]
    assert "본문그림" in items[0]["url"]


def test_body_images_returns_empty_list_when_the_body_never_arrived():
    """🔑 본문 컨테이너가 없으면 **빈 목록**이다 — 페이지 골격에서 주워 담지 않는다."""
    c = _load("cat2829_common")
    assert c.body_images(_body_missing_html()) == []


# ---- C2: SE2 는 `<span thumburl>` 이다 ----

def test_body_images_reads_se2_thumburl_spans():
    """🔴 이번 결함의 **직접 재현** — `<img>` 가 0개인데 그림은 3장이다.

    SE2 분기를 걷어내면 여기서 0장이 나와 실패한다.
    """
    c = _load("cat2829_common")
    src = _se2_page([_SE2_SPAN.format(n="차트" + str(i)) for i in range(3)])
    assert c.count_images(src, body_only=True) == 0, "픽스처 전제: <img> 가 없어야 재현이 된다"
    items = c.body_images(src)
    assert len(items) == 3, "🔴 SE2 그림이 또 0장이다"
    assert _kinds(items) == ["photo"] * 3
    assert [i["slot"] for i in items] == ["span.thumburl"] * 3
    assert [("차트%d" % i) in items[i]["url"] for i in range(3)] == [True] * 3


def test_body_images_ignores_spans_that_are_not_image_slots():
    """🔑 반대 방향 — 본문의 평범한 `<span>`(SE2 는 문단마다 쓴다)을 그림으로 세면 안 된다."""
    c = _load("cat2829_common")
    src = _se2_page(['<p><span style="" _foo="FONT-FAMILY: 돋움">본문 한 줄</span></p>',
                     _SE2_SPAN.format(n="진짜차트")])
    items = c.body_images(src)
    assert len(items) == 1 and "진짜차트" in items[0]["url"]


# ---- C3: data-lazy-src 우선, 없으면 src ----

def test_body_images_prefer_data_lazy_src_over_the_blur_placeholder():
    """🔴 SE4 의 `src` 는 흐림 placeholder 다(`?type=w80_blur`, 2,623/2,623 실측).

    우선순위를 뒤집으면 판독 에이전트가 **흐린 그림**을 보고 수치를 읽게 된다.
    """
    c = _load("cat2829_common")
    items = c.body_images(_se4_page([_SE4_IMG.format(n="지표")]))
    assert len(items) == 1
    assert items[0]["slot"] == "img.data-lazy-src", "흐림 placeholder 를 골랐다"
    assert "w80_blur" not in items[0]["url"]


def test_body_images_fall_back_to_src_when_there_is_no_lazy_attribute():
    """SE2 의 `<img>` 와 SE3 일부(6건)는 `data-lazy-src` 가 아예 없다."""
    c = _load("cat2829_common")
    items = c.body_images(_se2_page([_SE2_CONTENT_IMG.format(n="차트")]))
    assert len(items) == 1
    assert items[0]["slot"] == "img.src"


def test_body_images_drops_an_img_tag_that_has_no_url_at_all():
    """주소가 없는 슬롯은 내려받을 것이 없다 — 조용히 버려도 되는 유일한 경우다."""
    c = _load("cat2829_common")
    src = _se4_page(['<img alt="" class="se-image-resource" />', _SE4_IMG.format(n="진짜")])
    items = c.body_images(src)
    assert len(items) == 1 and "진짜" in items[0]["url"]


# ---- C4: 문서 등장 순서 ----

def test_body_images_preserve_document_order_across_mixed_slot_kinds():
    """🔴 이 트랙에서 정렬·순서 계약이 T5·T6·T7·T8 **네 번 연속** 테스트 갭이었다.

    원인은 매번 픽스처 원소가 1개거나 입력이 이미 정렬돼 있어 **순서가 관측되지
    않은 것**이다. 여기서는 슬롯 종류를 일부러 **섞어** 넣는다 — 종류별로 모아
    이어붙이는 구현(span 먼저 · img 나중 같은)이면 순서가 어긋나 실패한다.
    한 글에 span 과 img 가 **둘 다** 있는 글이 67건 실재한다(실측).
    """
    c = _load("cat2829_common")
    src = _se2_page([
        _SE2_CONTENT_IMG.format(n="AAA"),      # img
        _SE2_SPAN.format(n="BBB"),             # span
        _SE2_SPACER,                           # img(스페이서)
        _SE2_SPAN.format(n="DDD"),             # span
        _SE2_CONTENT_IMG.format(n="EEE"),      # img
    ])
    items = c.body_images(src)
    order = ["AAA", "BBB", "blank.gif", "DDD", "EEE"]
    got = [next(t for t in order if t in i["url"]) for i in items]
    assert got == order, "문서 등장 순서가 아니다 — " + repr(got)
    assert _kinds(items) == ["photo", "photo", "spacer", "photo", "photo"]


def test_body_images_order_is_preserved_in_se4_too():
    """SE4 에서도 그림·링크카드·스티커·GIF 가 **섞인 순서 그대로** 나와야 한다."""
    c = _load("cat2829_common")
    src = _se4_page([_SE4_OGLINK.format(n="og1"), _SE4_IMG.format(n="p1"),
                     _SE4_VIDEO.format(n="g1"), _SE4_STICKER.format(n="s1"),
                     _SE4_IMG.format(n="p2")])
    items = c.body_images(src)
    assert _kinds(items) == ["oglink", "photo", "gif", "sticker", "photo"], repr(_kinds(items))
    got = [next(t for t in ("og1", "p1", "g1", "s1", "p2") if t in i["url"]) for i in items]
    assert got == ["og1", "p1", "g1", "s1", "p2"]


# ---- C5: HTML 엔티티 이스케이프 ----

@pytest.mark.parametrize("make,page", [
    (_SE2_CONTENT_IMG, _se2_page), (_SE4_OGLINK, _se4_page)])
def test_body_images_unescape_html_entities_in_urls(make, page):
    """🔴 URL 이 HTML 엔티티로 이스케이프돼 있다 — `&amp;` 961 · `&#x3D;` 955 ·
    `&#61;` 6 (전수 실측). 안 풀면 `?src&#x3D;%22…` 라는 **없는 주소**를 받는다.

    ⚠️ `%22`·`%2F` 같은 퍼센트 인코딩은 **그대로 둬야** 한다 — 그건 URL 의 일부다.
    """
    c = _load("cat2829_common")
    items = c.body_images(page([make.format(n="X")]))
    url = items[0]["url"]
    for bad in ("&amp;", "&#x3D;", "&#61;"):
        assert bad not in url, "엔티티가 안 풀렸다: " + bad + " — " + url
    assert "src=%22" in url and "%3A%2F%2F" in url, "퍼센트 인코딩이 훼손됐다 — " + url


# ---- C6: type 파라미터만 교체 ----

@pytest.mark.parametrize("raw,expect", [
    # SE2 span — 값이 **빈** type. 선행 정규식(`\?type=w\d+`)이 못 잡던 형태다.
    ("https://mblogthumb-phinf.pstatic.net/a/b.jpg?type=",
     "https://mblogthumb-phinf.pstatic.net/a/b.jpg?type=w966"),
    # SE4 lazy
    ("https://mblogthumb-phinf.pstatic.net/a/b.png?type=w800",
     "https://mblogthumb-phinf.pstatic.net/a/b.png?type=w966"),
    # 링크카드 — type 앞에 다른 파라미터가 있다. 선행 코드는 `?` 를 두 번 붙였다.
    ("https://dthumb-phinf.pstatic.net/?src=%22https%3A%2F%2Fx%2Fy.jpg%22&type=ff120",
     "https://dthumb-phinf.pstatic.net/?src=%22https%3A%2F%2Fx%2Fy.jpg%22&type=w966"),
    # 쿼리가 아예 없는 경우
    ("https://ssl.pstatic.net/static/blog/blank.gif",
     "https://ssl.pstatic.net/static/blog/blank.gif?type=w966"),
])
def test_normalize_image_url_replaces_only_the_type_parameter(raw, expect):
    c = _load("cat2829_common")
    assert c.normalize_image_url(raw) == expect


def test_normalize_image_url_matches_the_prior_convention_for_plain_thumbnails():
    """🔑 선행 코드(`extract_calc_images.py:43`)와 **같은 결과**를 내야 한다 —
    그 코드가 실제로 처리하던 형태(`?type=w\\d+`)에서는 규약을 바꾸지 않는다.
    """
    c = _load("cat2829_common")
    import re as _re
    for raw in ("https://mblogthumb-phinf.pstatic.net/a/b.png?type=w800",
                "https://mblogthumb-phinf.pstatic.net/a/b.png?type=w400"):
        prior = _re.sub(r"\?type=w\d+", "", raw) + "?type=w966"
        assert c.normalize_image_url(raw) == prior


def test_normalize_image_url_is_idempotent():
    """두 번 적용해도 같아야 한다 — 안 그러면 재실행마다 다른 파일을 받는다."""
    c = _load("cat2829_common")
    once = c.normalize_image_url("https://x/y.png?type=w800")
    assert c.normalize_image_url(once) == once


# ---- C7·C8·C9·C10: 정체 라벨 ----

def test_body_images_label_link_cards_in_every_generation():
    """🔴 링크카드는 저자의 그림이 아니라 **남의 사이트 썸네일**이다.

    ⚠️ 호스트로는 못 가른다 — 2012년 SE2 글의 **저자 차트**도 같은 dthumb 프록시로
       나온다(`<차트-1>` 캡션 뒤 17장 실측). 「dthumb 는 링크카드」로 구현하면
       저자의 차트를 통째로 버린다. 가르는 것은 **감싸는 컴포넌트**다.
    """
    c = _load("cat2829_common")
    se2 = c.body_images(_se2_page([_SE2_OGLINK.format(n="og"),
                                   _SE2_CONTENT_IMG.format(n="저자차트")]))
    assert _kinds(se2) == ["oglink", "photo"], repr(se2)
    assert "dthumb" in se2[0]["url"] and "dthumb" in se2[1]["url"], (
        "픽스처 전제: 둘 다 같은 호스트여야 「호스트로 가르는」 구현이 실패한다")
    se4 = c.body_images(_se4_page([_SE4_OGLINK.format(n="og"), _SE4_IMG.format(n="차트")]))
    assert _kinds(se4) == ["oglink", "photo"]


def test_body_images_label_stickers_and_spacers_and_gifs():
    """🔑 정체를 붙이되 **버리지는 않는다** — 무엇을 뺄지는 부르는 쪽이 정한다.

    숨기면 다음 세대의 새 형태가 또 조용히 사라진다(이번이 그 실패다).
    """
    c = _load("cat2829_common")
    items = c.body_images(_se4_page([_SE4_STICKER.format(n="s"), _SE4_VIDEO.format(n="g")]))
    assert _kinds(items) == ["sticker", "gif"]
    assert items[1]["slot"] == "video.data-gif-url", "mp4 를 골랐다 — 원본 GIF 가 아니다"
    assert "mblogvideo" not in items[1]["url"]
    spacer = c.body_images(_se2_page([_SE2_SPACER]))
    assert _kinds(spacer) == ["spacer"]


def test_body_images_fall_back_to_poster_when_the_gif_url_is_absent():
    c = _load("cat2829_common")
    tag = ('<video src="https://mblogvideo-phinf.pstatic.net/x.gif?type=mp4w800"'
           ' poster="https://mblogthumb-phinf.pstatic.net/대체.gif?type=w800"></video>')
    items = c.body_images(_se4_page([tag]))
    assert [i["slot"] for i in items] == ["video.poster"]
    assert "대체" in items[0]["url"]


def test_every_kind_body_images_can_emit_is_declared():
    """🔑 `IMAGE_KINDS` 는 `--kinds` 오타를 잡는 데 쓰인다. 목록이 실제와 어긋나면
    그 검증이 거짓 안심이 된다 — 실물 코퍼스로 대조한다."""
    c, _, files = _corpus()
    seen = set()
    for p in files:
        seen |= {i["kind"] for i in c.body_images(p.read_text(encoding="utf-8"))}
    assert seen <= set(c.IMAGE_KINDS), "선언에 없는 정체가 나왔다: " + repr(seen)
    assert seen == set(c.IMAGE_KINDS), "선언에만 있고 실물에 없는 정체가 있다: " + repr(
        set(c.IMAGE_KINDS) - seen)


# ---- 실물 코퍼스 433건 회귀 ----

def test_real_corpus_se2_posts_that_read_as_zero_images_actually_have_images():
    """🔴 이번 결함의 **실물 회귀**. `count_images(body_only=True)==0` 인 SE2 글이
    127건 있었는데, 그중 123건은 실제로 그림이 있다(전수 실측).

    SE2 분기를 걷어내면 123건이 다시 0장이 되어 여기서 실패한다.
    """
    c, _, files = _corpus()
    silent_zero, still_zero = 0, []
    for p in files:
        src = p.read_text(encoding="utf-8")
        if c.count_images(src, body_only=True):
            continue
        photos = [i for i in c.body_images(src) if i["kind"] == "photo"]
        if photos:
            silent_zero += 1
        else:
            still_zero.append(p.name)
    assert silent_zero == 123, "옛 계수기가 0으로 읽던 글의 회복 건수가 다르다: " + str(silent_zero)
    assert len(still_zero) == 4, "진짜 그림 없는 글 수가 다르다: " + repr(still_zero)


def test_real_corpus_image_totals_by_generation():
    """🔑 「내 보고를 안 믿는 사람」이 재현할 수 있게 수치 자체를 고정한다(2026-08-06 실측)."""
    c, _, files = _corpus()
    total, photo, posts = {}, {}, {}
    for p in files:
        src = p.read_text(encoding="utf-8")
        gen, _r = c.body_region(src)
        items = c.body_images(src)
        posts[gen] = posts.get(gen, 0) + 1
        total[gen] = total.get(gen, 0) + len(items)
        photo[gen] = photo.get(gen, 0) + sum(1 for i in items if i["kind"] == "photo")
    assert posts == {"se2": 195, "se3": 2, "se4": 236}
    assert total == {"se2": 2170, "se3": 21, "se4": 3695}, repr(total)
    assert photo == {"se2": 2004, "se3": 15, "se4": 2608}, repr(photo)


def test_real_corpus_image_urls_are_normalized_and_unescaped():
    """모든 URL 이 `type=w966` 으로 끝나고 엔티티가 남아 있지 않아야 한다."""
    c, _, files = _corpus()
    bad = []
    for p in files:
        for i in c.body_images(p.read_text(encoding="utf-8")):
            u = i["url"]
            if not (u.endswith("?type=w966") or u.endswith("&type=w966")):
                bad.append((p.name, u[:100]))
            if "&amp;" in u or "&#x3D;" in u or "&#61;" in u:
                bad.append((p.name, "ESCAPED " + u[:100]))
            if "blogpfthumb" in u:
                bad.append((p.name, "PROFILE " + u[:100]))
    assert bad == [], repr(bad[:5])


def test_real_corpus_link_card_labeling_agrees_with_the_independent_class_signal():
    """🔑 판정을 **독립 신호 두 개**로 대조한다 — 감싸는 컴포넌트 구간(우리 판정 축)과
    `<img>` 자신의 class(`se-oglink-thumbnail-resource`, SE4/SE3 에만 있다).
    둘이 어긋나면 판정 근거가 흔들린 것이다. 실측 433건: 어긋남 0건.
    """
    import re as _re
    c, _, files = _corpus()
    mismatch = []
    for p in files:
        _gen, region = c.body_region(p.read_text(encoding="utf-8"))
        spans = c._oglink_spans(region or "")
        for m in _re.finditer(r"<img\b[^>]*>", region or "", _re.I):
            cls = dict((k.lower(), v) for k, v in
                       c.TAG_ATTRS.findall(m.group(0))).get("class") or ""
            in_region = any(a <= m.start() < b for a, b in spans)
            if "oglink" in cls and not in_region:
                mismatch.append((p.name, cls))
    assert mismatch == [], "class 는 링크카드라는데 컴포넌트 구간 밖이다: " + repr(mismatch[:5])


# ================= Task 11: 이미지 다운로더 =================

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40
_JPG = b"\xff\xd8\xff\xe0" + b"0" * 40
_GIF = b"GIF89a" + b"0" * 40
_HTML_ERROR = b"<html><head><title>404</title></head><body>none</body></html>"


def _install_image_dirs(d, tmp_path, monkeypatch):
    for name, sub in (("POSTS_DIR", "posts28"), ("TEXT_DIR", "text28"),
                      ("IMAGES_DIR", "images28"), ("CLAIMS_BATCH_DIR", "claims_batches")):
        monkeypatch.setattr(d.C, name, tmp_path / sub)
    monkeypatch.setattr(d.C, "IMAGE_FAIL_JSON", tmp_path / "image_fail_28_29.json")
    d.C.ensure_dirs()
    return d


def _dl(tmp_path, monkeypatch):
    return _install_image_dirs(_load("download_images_28_29"), tmp_path, monkeypatch)


@pytest.mark.parametrize("blob,ext", [
    (_PNG, "png"), (_JPG, "jpg"), (_GIF, "gif"),
    (b"BM" + b"0" * 20, "bmp"), (b"RIFF1234WEBP" + b"0" * 20, "webp"),
])
def test_image_ext_reads_the_format_from_the_bytes(blob, ext):
    """⚠️ 확장자를 URL 이나 `.jpg` 하드코딩으로 정하면 안 된다 — 원본이 png/jpg 혼재이고
    링크카드 URL 에는 경로 확장자가 아예 없다(104건 실측)."""
    d = _load("download_images_28_29")
    assert d.image_ext(blob) == ext


@pytest.mark.parametrize("blob", [b"", _HTML_ERROR, b"not an image at all"])
def test_image_ext_rejects_anything_that_is_not_an_image(blob):
    """🔑 반대 방향 — HTML 오류응답·빈 응답을 이미지로 받아들이면 안 된다."""
    d = _load("download_images_28_29")
    assert d.image_ext(blob) is None


def test_download_leaves_no_file_when_curl_exits_nonzero(tmp_path, monkeypatch):
    """🔴 계획서 초안의 결함 ① — 종료코드를 안 보고 `-o` 로 직접 썼다.

    실패했는데 파일이 남으면 재실행이 **영구히 스킵**한다. 파일이 없어야 재시도된다.
    """
    d = _dl(tmp_path, monkeypatch)
    jobs = [{"stem": "28_20200101_1", "index": 0, "url": "https://x/a.png", "kind": "photo"}]
    got, skipped, failures = d.download(
        jobs, fetch=lambda u: (None, None, "CURL_EXIT:22"), sleep=lambda s: None)
    assert (got, skipped) == (0, 0)
    assert [f["error"] for f in failures] == ["CURL_EXIT:22"]
    assert list(d.C.IMAGES_DIR.iterdir()) == [], "🔴 실패했는데 파일이 남았다"


def test_download_leaves_no_file_when_the_response_is_not_an_image(tmp_path, monkeypatch):
    """🔑 종료코드 0 + HTML 오류 본문 — curl 은 성공했다고 말한다. 매직바이트가 유일한 방어다."""
    d = _dl(tmp_path, monkeypatch)

    def fake_run(cmd, capture_output=False):
        class R:
            returncode = 0
            stdout = _HTML_ERROR
        return R()

    monkeypatch.setattr(d.subprocess, "run", fake_run)
    blob, ext, error = d.fetch_image("https://x/a.png")
    assert (blob, ext) == (None, None)
    assert error.startswith("NOT_AN_IMAGE"), error
    got, _s, failures = d.download(
        [{"stem": "s", "index": 0, "url": "https://x/a.png", "kind": "photo"}],
        sleep=lambda s: None)
    assert got == 0 and len(failures) == 1
    assert list(d.C.IMAGES_DIR.iterdir()) == []


def test_fetch_image_reports_the_curl_exit_code(tmp_path, monkeypatch):
    d = _dl(tmp_path, monkeypatch)

    def fake_run(cmd, capture_output=False):
        class R:
            returncode = 22
            stdout = b""
        return R()

    monkeypatch.setattr(d.subprocess, "run", fake_run)
    assert d.fetch_image("https://x/a.png")[2] == "CURL_EXIT:22"


def test_fetch_image_uses_fail_and_referer_flags(tmp_path, monkeypatch):
    """`-f` 가 없으면 404 페이지가 종료코드 0 으로 들어온다 — 방어가 매직바이트 하나만 남는다."""
    d = _dl(tmp_path, monkeypatch)
    seen = {}

    def fake_run(cmd, capture_output=False):
        seen["cmd"] = cmd

        class R:
            returncode = 0
            stdout = _PNG
        return R()

    monkeypatch.setattr(d.subprocess, "run", fake_run)
    d.fetch_image("https://x/a.png")
    assert "-f" in seen["cmd"]
    assert any(str(a).startswith("Referer: ") for a in seen["cmd"])
    assert d.C.UA in seen["cmd"]


def test_download_writes_the_extension_the_response_declares(tmp_path, monkeypatch):
    """⚠️ `.jpg` 하드코딩 금지 — URL 이 `.png` 여도 응답이 정한다(그 반대도)."""
    d = _dl(tmp_path, monkeypatch)
    jobs = [{"stem": "st", "index": 0, "url": "https://x/a.png", "kind": "photo"},
            {"stem": "st", "index": 1, "url": "https://x/b.jpg", "kind": "photo"}]
    d.download(jobs, fetch=lambda u: ((_JPG, "jpg", None) if u.endswith("a.png")
                                      else (_PNG, "png", None)), sleep=lambda s: None)
    assert sorted(p.name for p in d.C.IMAGES_DIR.iterdir()) == ["st_000.jpg", "st_001.png"]


def test_download_retries_a_zero_byte_leftover_and_replaces_it(tmp_path, monkeypatch):
    """🔴 지금 저장소에 실제로 남아 있는 상태다(`images28/x.png` 0바이트).

    「존재」로 스킵하면 그 글은 **영원히** 못 받는다.
    """
    d = _dl(tmp_path, monkeypatch)
    (d.C.IMAGES_DIR / "st_000.png").write_bytes(b"")
    calls = []
    got, skipped, failures = d.download(
        [{"stem": "st", "index": 0, "url": "https://x/a.png", "kind": "photo"}],
        fetch=lambda u: calls.append(u) or (_PNG, "png", None), sleep=lambda s: None)
    assert calls == ["https://x/a.png"], "0바이트 잔해를 「존재」로 보고 스킵했다"
    assert (got, skipped, failures) == (1, 0, [])
    assert (d.C.IMAGES_DIR / "st_000.png").read_bytes() == _PNG


def test_download_retries_an_html_error_body_left_by_a_previous_run(tmp_path, monkeypatch):
    d = _dl(tmp_path, monkeypatch)
    (d.C.IMAGES_DIR / "st_000.jpg").write_bytes(_HTML_ERROR)
    calls = []
    d.download([{"stem": "st", "index": 0, "url": "https://x/a.png", "kind": "photo"}],
               fetch=lambda u: calls.append(u) or (_PNG, "png", None), sleep=lambda s: None)
    assert calls == ["https://x/a.png"]
    assert not (d.C.IMAGES_DIR / "st_000.jpg").exists(), "무효한 잔해가 남아 다음 실행을 또 속인다"
    assert (d.C.IMAGES_DIR / "st_000.png").exists()


def test_download_skips_a_valid_file_without_requesting(tmp_path, monkeypatch):
    """🔑 반대 방향 — 재개가 실제로 걸려야 한다. 안 걸면 매 실행이 전량 재요청이다."""
    d = _dl(tmp_path, monkeypatch)
    (d.C.IMAGES_DIR / "st_000.png").write_bytes(_PNG)
    calls = []
    got, skipped, failures = d.download(
        [{"stem": "st", "index": 0, "url": "https://x/a.png", "kind": "photo"}],
        fetch=lambda u: calls.append(u) or (_JPG, "jpg", None), sleep=lambda s: None)
    assert calls == [], "이미 받아 둔 유효한 파일을 다시 요청했다"
    assert (got, skipped) == (0, 1)
    assert (d.C.IMAGES_DIR / "st_000.png").read_bytes() == _PNG


def test_download_sleeps_once_per_request_and_never_for_a_skip(tmp_path, monkeypatch):
    """🔴 계획서 초안의 결함 ② — sleep 이 없어 수백 연속 요청이었다.

    ⚠️ 동시에 반대 방향도 고정한다: 스킵에도 쉬면 재개 실행이 아무 일도 안 하면서
       몇 분씩 걸린다(433글 × 그림 수 만큼).
    """
    d = _dl(tmp_path, monkeypatch)
    h = _load("harvest_cat28_29_full")
    assert d.IMAGE_SLEEP == h.BODY_SLEEP, "본문 수집과 다른 간격을 쓴다"
    (d.C.IMAGES_DIR / "st_000.png").write_bytes(_PNG)
    naps = []
    d.download([{"stem": "st", "index": 0, "url": "https://x/a.png", "kind": "photo"},
                {"stem": "st", "index": 1, "url": "https://x/b.png", "kind": "photo"},
                {"stem": "st", "index": 2, "url": "https://x/c.png", "kind": "photo"}],
               fetch=lambda u: (_PNG, "png", None), sleep=naps.append)
    assert naps == [d.IMAGE_SLEEP, d.IMAGE_SLEEP], "요청 수와 쉬는 횟수가 안 맞는다 — " + repr(naps)


def test_download_writes_the_failure_list_and_overwrites_a_stale_one(tmp_path, monkeypatch):
    """🔑 지난 실행의 실패 목록이 남아 이번 실행을 잘못 말하면 안 된다
    (`harvest_bodies` 의 규약 승계 — 거짓 경보와 거짓 안심을 둘 다 막는다)."""
    d = _dl(tmp_path, monkeypatch)
    d.C.IMAGE_FAIL_JSON.write_text('[{"stem": "old"}]', encoding="utf-8")
    d.download([{"stem": "st", "index": 0, "url": "https://x/a.png", "kind": "photo"}],
               fetch=lambda u: (_PNG, "png", None), sleep=lambda s: None)
    assert _json.loads(d.C.IMAGE_FAIL_JSON.read_text(encoding="utf-8")) == []

    d.download([{"stem": "st", "index": 9, "url": "https://x/z.png", "kind": "photo"}],
               fetch=lambda u: (None, None, "CURL_EXIT:6"), sleep=lambda s: None)
    on_disk = _json.loads(d.C.IMAGE_FAIL_JSON.read_text(encoding="utf-8"))
    assert [f["url"] for f in on_disk] == ["https://x/z.png"]
    assert on_disk[0]["stem"] == "st" and on_disk[0]["index"] == 9


def test_download_finishes_the_rest_after_one_failure(tmp_path, monkeypatch):
    d = _dl(tmp_path, monkeypatch)
    jobs = [{"stem": "st", "index": i, "url": "https://x/%d.png" % i, "kind": "photo"}
            for i in range(3)]
    got, _s, failures = d.download(
        jobs, fetch=lambda u: ((None, None, "CURL_EXIT:28") if "1.png" in u
                               else (_PNG, "png", None)), sleep=lambda s: None)
    assert got == 2 and [f["index"] for f in failures] == [1]
    assert sorted(p.name for p in d.C.IMAGES_DIR.iterdir()) == ["st_000.png", "st_002.png"]


# ---- 대상 선정(plan_jobs) ----

def test_plan_jobs_numbers_are_assigned_before_download_so_a_failure_shifts_nothing():
    """🔴 판독 에이전트에게 **「몇 번째 그림」이 맥락**이다.

    성공한 것만 세어 번호를 매기면 한 장이 실패했을 때 뒤가 전부 밀려 조용히 틀린
    판독이 된다. 번호는 필터를 통과한 **순서**로 내려받기 전에 정해진다.
    """
    d = _load("download_images_28_29")
    src = _se4_page([_SE4_IMG.format(n="p0"), _SE4_OGLINK.format(n="og"),
                     _SE4_IMG.format(n="p1"), _SE4_IMG.format(n="p2")])
    jobs, skipped, missing = d.plan_jobs(["st"], read=lambda s: src)
    assert [j["index"] for j in jobs] == [0, 1, 2], "링크카드를 건너뛴 만큼 번호가 밀렸다"
    assert [("p%d" % i) in jobs[i]["url"] for i in range(3)] == [True] * 3
    assert skipped == {"oglink": 1}, "제외한 것을 조용히 삼켰다 — " + repr(skipped)
    assert missing == []


def test_plan_jobs_numbers_restart_per_post():
    d = _load("download_images_28_29")
    src = _se4_page([_SE4_IMG.format(n="a"), _SE4_IMG.format(n="b")])
    jobs, _s, _m = d.plan_jobs(["one", "two"], read=lambda s: src)
    assert [(j["stem"], j["index"]) for j in jobs] == [
        ("one", 0), ("one", 1), ("two", 0), ("two", 1)]


def test_plan_jobs_kind_filter_actually_selects():
    """🔑 필터가 실제로 고른다는 것을 양방향으로 고정한다."""
    d = _load("download_images_28_29")
    src = _se4_page([_SE4_IMG.format(n="p"), _SE4_OGLINK.format(n="og"),
                     _SE4_STICKER.format(n="s"), _SE4_VIDEO.format(n="g")])
    photos, _s, _m = d.plan_jobs(["st"], kinds=("photo",), read=lambda s: src)
    assert [j["kind"] for j in photos] == ["photo"]
    both, skipped, _m = d.plan_jobs(["st"], kinds=("photo", "gif"), read=lambda s: src)
    assert [j["kind"] for j in both] == ["photo", "gif"]
    assert skipped == {"oglink": 1, "sticker": 1}


def test_plan_jobs_reports_a_stem_whose_html_was_never_saved():
    """🔑 없는 글을 조용히 0장으로 넘기면 「그림이 없는 글」과 구분되지 않는다."""
    d = _load("download_images_28_29")

    def read(stem):
        if stem == "gone":
            raise OSError("없다")
        return _se4_page([_SE4_IMG.format(n="p")])

    jobs, _s, missing = d.plan_jobs(["ok", "gone"], read=read)
    assert missing == ["gone"]
    assert [j["stem"] for j in jobs] == ["ok"]


def test_plan_jobs_reads_the_saved_html_from_posts_dir(tmp_path, monkeypatch):
    """기본 경로 배선 — 부품 테스트만으론 어느 디렉토리를 읽는지가 안 잡힌다."""
    d = _dl(tmp_path, monkeypatch)
    (d.C.POSTS_DIR / "28_20200101_9.html").write_text(
        _se2_page([_SE2_SPAN.format(n="차트")]), encoding="utf-8")
    jobs, _s, missing = d.plan_jobs(["28_20200101_9"])
    assert missing == [] and len(jobs) == 1 and "차트" in jobs[0]["url"]


# ---- main() 배선 ----

def test_main_refuses_an_unknown_kind(tmp_path, monkeypatch, capsys):
    """🔑 오타를 「해당 없음 0장」으로 통과시키지 않는다.

    2026-08-04 급락게이트에서 독립검증이 잡은 결정적 결함이 정확히 이 형태였다
    (`"Auto"` 를 「정상」으로 보고).
    """
    d = _dl(tmp_path, monkeypatch)
    rc = d.main(["--stems", "st", "--kinds", "Photo"])
    assert rc == 2
    assert "알 수 없는 --kinds" in capsys.readouterr().out


def test_main_refuses_to_run_without_an_explicit_target(tmp_path, monkeypatch, capsys):
    """🔴 대상을 스스로 정하지 않는다 — 기본값이 「전부」면 무단 대량 요청이 된다."""
    d = _dl(tmp_path, monkeypatch)
    assert d.main([]) == 2
    assert "대상이 없다" in capsys.readouterr().out


def test_main_dry_run_makes_no_request_and_says_what_it_would_do(tmp_path, monkeypatch, capsys):
    d = _dl(tmp_path, monkeypatch)
    (d.C.POSTS_DIR / "28_20200101_9.html").write_text(
        _se4_page([_SE4_IMG.format(n="p"), _SE4_OGLINK.format(n="og")]), encoding="utf-8")
    monkeypatch.setattr(d, "fetch_image",
                        lambda u, timeout=None: pytest.fail("dry-run 인데 요청했다"))
    rc = d.main(["--stems", "28_20200101_9", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "내려받을 1 장" in out
    assert "제외한 슬롯 {'oglink': 1}" in out, "제외를 조용히 삼켰다 — " + out
    assert list(d.C.IMAGES_DIR.iterdir()) == []


def test_main_says_out_loud_when_limit_truncates(tmp_path, monkeypatch, capsys):
    """계획서 Task 11 의 규칙 — 「줄이면 줄였다는 사실을 로그에 남긴다」."""
    d = _dl(tmp_path, monkeypatch)
    (d.C.POSTS_DIR / "28_20200101_9.html").write_text(
        _se4_page([_SE4_IMG.format(n=str(i)) for i in range(5)]), encoding="utf-8")
    d.main(["--stems", "28_20200101_9", "--limit", "2", "--dry-run"])
    out = capsys.readouterr().out
    assert "--limit 2 로 줄인다 — 3 장을 안 받는다" in out, out


def test_main_returns_nonzero_when_a_download_fails(tmp_path, monkeypatch, capsys):
    d = _dl(tmp_path, monkeypatch)
    (d.C.POSTS_DIR / "28_20200101_9.html").write_text(
        _se4_page([_SE4_IMG.format(n="p")]), encoding="utf-8")
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    monkeypatch.setattr(d, "fetch_image", lambda u, timeout=40: (None, None, "CURL_EXIT:6"))
    rc = d.main(["--stems", "28_20200101_9"])
    out = capsys.readouterr().out
    assert rc == 1, "실패가 있는데 성공으로 보고했다"
    assert "실패 1 장" in out and "CURL_EXIT:6" in out


def test_main_returns_zero_and_saves_when_everything_succeeds(tmp_path, monkeypatch, capsys):
    """🔑 반대 방향 — 정상 실행이 실패로 보고되면 게이트가 무의미해진다."""
    d = _dl(tmp_path, monkeypatch)
    (d.C.POSTS_DIR / "28_20200101_9.html").write_text(
        _se2_page([_SE2_SPAN.format(n="a"), _SE2_SPAN.format(n="b")]), encoding="utf-8")
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    monkeypatch.setattr(d, "fetch_image", lambda u, timeout=40: (_PNG, "png", None))
    rc = d.main(["--stems", "28_20200101_9"])
    assert rc == 0, capsys.readouterr().out
    assert sorted(p.name for p in d.C.IMAGES_DIR.iterdir()) == [
        "28_20200101_9_000.png", "28_20200101_9_001.png"]


def test_downloaded_image_files_are_gitignored():
    """⚠️ 타인 저작물이다. 파일명이 달라져도 디렉토리 전체가 막혀 있어야 한다."""
    assert _ignored("backtest/tasso_labels/harvest/images28/28_20090910_80090262097_000.png")
    assert _ignored("backtest/tasso_labels/harvest/images28/x_012.jpg")


def test_image_failure_list_is_tracked_evidence():
    """🔑 반대 방향 — 실패 목록은 파생 근거라 추적돼야 한다
    (`harvest_fail_28_29.json` 과 같은 규약). 범용 패턴이 우리 산출물을 삼킨 사례가
    이 저장소에 6번 있었다.
    """
    assert not _ignored("backtest/tasso_labels/harvest/image_fail_28_29.json")
