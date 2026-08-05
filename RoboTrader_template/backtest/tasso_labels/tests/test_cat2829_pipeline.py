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


def _item(log_no, add_date_ms):
    return {"logNo": str(log_no), "addDate": add_date_ms,
            "titleWithInspectMessage": "제목 " + str(log_no)}


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
    body = "".join('<p class="se-text-paragraph">' + p + "</p>" for p in paragraphs)
    imgs = "".join('<img src="x' + str(i) + '.png">' for i in range(n_img))
    return _HTML_HEAD + body + imgs + ("<!--" + "x" * pad + "-->") + _HTML_TAIL


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
