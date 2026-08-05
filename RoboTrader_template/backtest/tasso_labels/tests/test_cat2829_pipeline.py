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


def _post_html(paragraphs, n_img=0, pad=6000):
    """SE3(2019~) 글 — 본문 컨테이너 `se-main-container` 안에 문단·이미지가 들어간다.

    🔑 옛 판본은 컨테이너를 빼고 문단만 넣었다. 그러면 「본문을 받았는데 글자가 없다」와
       「본문을 아예 못 받았다」가 같은 HTML 이 되어 C2 를 구조적으로 못 잡는다.
       parse_posts.py:3 이 실제 SE3 페이지의 컨테이너로 기록한 이름을 그대로 쓴다.
    """
    body = "".join('<p class="se-text-paragraph">' + p + "</p>" for p in paragraphs)
    imgs = "".join('<img src="x' + str(i) + '.png">' for i in range(n_img))
    return (_HTML_HEAD + '<div class="se-main-container">' + body + imgs + "</div>"
            + ("<!--" + "x" * pad + "-->") + _HTML_TAIL)


def _legacy_html(pad=6000):
    """구 에디터(SE2, 2017~2018) 글 — 본문이 `#postViewArea` 에 `<br>` 로만 들어간다.

    parse_posts.py:23-24 가 구 에디터 본문을 뽑는 컨테이너이자,
    harvest_fallback.py:38,46 이 PC 재수집 성패를 판정하는 바로 그 마커다.
    """
    return (_HTML_HEAD + '<div id="postViewArea">본문 첫 줄<br>둘째 줄</div>'
            + ("<!--" + "x" * pad + "-->") + _HTML_TAIL)


def _body_missing_html(pad=6000):
    """모바일 엔드포인트가 구 에디터 글의 **본문을 아예 안 실어 준** 응답.

    harvest_fallback.py:3-5 가 2017~2018 글 11건에서 실측해 기록한 형태다.
    UI 아이콘만 있고 본문 컨테이너가 SE3·SE2 어느 쪽도 없다. 크기는 문턱을 통과한다.
    """
    return (_HTML_HEAD + '<div class="blog_header">머리말</div><img src="ui_icon.png">'
            + ("<!--" + "x" * pad + "-->") + _HTML_TAIL)


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


# ------------------- C2: 구 에디터 위장 (image_only) -------------------

def _classify(tmp_path, monkeypatch, html_src):
    h = _load("harvest_cat28_29_full")
    _install_tmp_dirs(h, tmp_path, monkeypatch)
    return h.harvest_one(_entry(), fetch=lambda n: html_src, sleep=lambda s: None)


def test_legacy_editor_post_is_flagged_not_image_only(tmp_path, monkeypatch):
    """🔴 구 에디터(SE2) 글은 `image_only` 로 위장되면 안 된다.

    본문이 `#postViewArea` 에 있는데 이 추출기는 SE3 문단만 읽는다 = **아직 못 읽은 글**.
    image_only 로 적으면 V1(파일 있음)·V2(⑧기타 1행)가 전부 초록인 채
    원문을 한 번도 안 읽고 「전수」를 주장하게 된다.
    """
    meta = _classify(tmp_path, monkeypatch, _legacy_html())
    assert meta["text_len"] == 0
    assert meta["legacy_editor"] is True, "구 에디터 신호를 못 잡았다"
    assert meta["image_only"] is False, "🔴 못 읽은 글이 이미지 전용으로 위장됐다"
    assert meta["body_container"] == "se2"


def test_response_without_any_body_container_is_flagged_not_image_only(tmp_path, monkeypatch):
    """🔴 harvest_fallback.py:3-5 가 기록한 **실제** 사례 — 모바일이 구 에디터 글의
    본문을 아예 안 실어 준다. 8KB 라 크기 문턱을 통과하고 본문만 0자다.
    """
    meta = _classify(tmp_path, monkeypatch, _body_missing_html())
    assert meta["html_bytes"] >= 5000, "크기 문턱을 통과하는 응답이어야 재현이 된다"
    assert meta["text_len"] == 0
    assert meta["legacy_editor"] is True
    assert meta["image_only"] is False, "🔴 본문 미수신이 이미지 전용으로 위장됐다"
    assert meta["body_container"] == "none"


def test_true_image_only_post_is_image_only_and_not_legacy(tmp_path, monkeypatch):
    """🔑 반대 방향 — 진짜 이미지 전용 글은 여전히 image_only 여야 한다.

    이걸 안 걸면 「전부 legacy_editor 로 찍으면 되지」로 되돌려도 아무도 못 잡는다.
    SE3 본문 컨테이너를 **받았는데** 문단만 없는 경우가 그것이다.
    """
    meta = _classify(tmp_path, monkeypatch, _post_html([], n_img=9))
    assert meta["text_len"] == 0
    assert meta["image_only"] is True
    assert meta["legacy_editor"] is False, "진짜 이미지 전용 글이 미수신으로 오분류됐다"
    assert meta["body_container"] == "se3"
    assert meta["img_count"] == 9


def test_normal_post_is_neither_image_only_nor_legacy(tmp_path, monkeypatch):
    meta = _classify(tmp_path, monkeypatch, _post_html(["본문 있음"], n_img=2))
    assert meta["text_len"] > 0
    assert meta["image_only"] is False
    assert meta["legacy_editor"] is False
    assert meta["body_container"] == "se3"


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
