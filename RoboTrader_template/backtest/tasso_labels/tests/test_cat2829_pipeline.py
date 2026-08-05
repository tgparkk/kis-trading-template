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
