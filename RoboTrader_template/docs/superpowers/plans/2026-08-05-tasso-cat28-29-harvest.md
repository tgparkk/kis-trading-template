# 태쏘 [28]·[29] 432건 전수 수집 → METHOD 2판 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버 블로그 `mbc3110` 카테고리 [28] 주식기법 분석·[29] 시황이슈 정리 **432건을 전수 수집·전건 정독**해 주장 단위 원장으로 정규화하고, 그것으로 `METHOD.md` 2판과 기존 결론 영향 판정을 낸다.

**Architecture:** 수집(①②) → 정독(③) → 이미지 2차(④) → 원장 병합(⑤) → 집필·판정(⑥)의 6단계. 각 단계 사이에 기계 검증 게이트(V1·V2·V5)가 있고, 정독의 품질은 V3(1판 서술 역방향 대조)·V4(독립 재정독 표본)로 잰다. 코드는 작은 단일책임 모듈 5본으로 나누고, 실행 단계는 에이전트에 분산한다.

**Tech Stack:** Python 3.9.13 · pandas 2.2.3 · pytest · `curl` subprocess (기존 수집기 관례 승계) · 표준 라이브러리 `json`/`csv`/`re`/`html`

**설계 문서:** `docs/superpowers/specs/2026-08-05-tasso-cat28-29-harvest-design.md` (커밋 `ffd0842`)

## Global Constraints

모든 태스크의 요구사항에 아래가 **암묵적으로 포함**된다.

- **작업 위치**: 워크트리 `D:/tmp/wt-tasso-cat2829`, 브랜치 `research/tasso-cat2829-harvest`
- 🔴 **라이브 트리 `D:/GIT/kis-trading-template` 는 항상 `main`.** 이 계획은 라이브 트리를 건드리지 않는다.
- 🔴 **라이브 트리에서 pytest 실행 금지.** 테스트는 워크트리에서, **디렉토리 한정**으로만:
  `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v`
- 🔴 **전체 테스트 스위트 금지** — `tests/` 하위에 라이브 DB 통합 테스트가 실재한다.
- 🔴 **장중(09:00~15:30) `main` 머지 금지.** 머지는 장 마감 후.
- 🔴 **git commit·push 는 사장님 확인 필요.** 각 태스크의 커밋 단계는 확인을 받고 실행한다.
- **Python 3.9 호환** — `from __future__ import annotations` 를 쓰고, 런타임 `X | Y` 유니온·`list[str]` 어노테이션 평가를 피한다 (`pyproject.toml` `target-version = "py39"`)
- **ruff line-length 120**
- **원문 인용 상한 40자** (`claims_schema.QUOTE_MAX`). 타인 저작물이므로 커밋되는 산출물에는 원문 인용을 싣지 않는다.
- **경로는 전부 `Path(__file__)` 기준 절대경로.** cwd 상대 경로 금지 — 지난 수집분 29건이 사라진 원인이다.
- **비목표**: `labels_v4.csv`·`labels_v5.csv`·`PREREG_v3.md`·`frozen_constants.py` 는 **건드리지 않는다.** 검정 실행 안 한다.

---

## File Structure

| 파일 | 책임 | 태스크 |
|---|---|---|
| `backtest/tasso_labels/harvest/cat2829_common.py` | 경로 상수(절대)·카테고리·HTTP 호출·HTML→텍스트. **cwd 의존을 없애는 유일한 지점** | 1 |
| `backtest/tasso_labels/harvest/claims_schema.py` | 주장 행의 계약. 열 정의·enum·`validate_row()`. 병합기·검증기·테스트의 단일 출처 | 2 |
| `backtest/tasso_labels/harvest/harvest_cat28_29_full.py` | ①목록 확보 + ②본문 수집 실행 | 3, 4 |
| `backtest/tasso_labels/harvest/verify_cat2829.py` | V1(수집 회수율)·V2(원장 회수율)·V5(revision 재판정) | 5, 6, 7 |
| `backtest/tasso_labels/harvest/build_claims_cat2829.py` | 배치 JSONL → 원장 CSV 2벌(quote 유/무) | 6 |
| `backtest/tasso_labels/harvest/batch_cat2829.py` | 글 목록을 정독 에이전트 배치로 결정적 분할 | 8 |
| `backtest/tasso_labels/tests/test_cat2829_pipeline.py` | 위 전부의 단위 테스트 | 1~8 |
| `RoboTrader_template/.gitignore` | 원문 캐시 차단 + 검증 로그 되살림 | 1 |

`harvest/` 는 패키지가 아니다(`__init__.py` 없음). 테스트는 `importlib.util.spec_from_file_location` 으로 **경로 직접 로드**한다.

---

## Task 1: 경로 모듈 + `.gitignore` 교정

**Files:**
- Create: `backtest/tasso_labels/harvest/cat2829_common.py`
- Create: `backtest/tasso_labels/tests/test_cat2829_pipeline.py`
- Modify: `RoboTrader_template/.gitignore` (173행 뒤에 삽입)

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: `HARVEST`·`POSTS_DIR`·`TEXT_DIR`·`IMAGES_DIR`·`CATLIST_JSON`·`POSTMETA_JSON`·`CLAIMS_BATCH_DIR`·`CLAIMS_PUBLIC_CSV`·`CLAIMS_QUOTED_CSV`·`VERIFY_LOG` (모두 `pathlib.Path`, 절대) · `BLOG: str` · `CATEGORIES: Dict[int, str]` · `UA: str` · `api_json(cat, page)` · `fetch_html(log_no)` · `html_to_text(src) -> str` · `count_images(src) -> int`

**배경 — 이 태스크가 막는 두 가지 실패**

1. **cwd 상대 경로.** 구 스크립트 `harvest_cat28_29.py:37-38` 이 `os.makedirs("posts2")` 로 썼고, 그 29건은 저장소에 안 남았다(2026-08-05 트리 전역 검색 결과 0개).
2. **`.gitignore` 3건.** 2026-08-05 `git check-ignore` 실측:
   - `harvest/posts28/x.html` → **tracked** (타인 저작물이 커밋된다)
   - `harvest/claims_cat2829_quoted.csv` → **tracked** (`.gitignore:169` 의 `!harvest/*.csv` 가 되살린다)
   - `harvest/verify_cat2829.log` → **IGNORED** (`.gitignore:68,138` 의 `*.log` 가 삼킨다)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backtest/tasso_labels/tests/test_cat2829_pipeline.py` 를 만든다:

```python
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
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v`
Expected: `test_paths_*` 는 `FileNotFoundError`(모듈 없음), `test_gitignore_blocks_*` 는 5건 FAIL, `test_gitignore_keeps_*` 는 `verify_cat2829.log` 1건 FAIL

- [ ] **Step 3: `cat2829_common.py` 를 만든다**

```python
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
        t = re.sub(r"[\s\u200b\xa0]+", " ", html.unescape(TAG.sub(" ", p))).strip()
        paras.append(t)
    return "\n".join(paras)


def count_images(src):
    return len(IMG.findall(src))


def ensure_dirs():
    for d in (POSTS_DIR, TEXT_DIR, IMAGES_DIR, CLAIMS_BATCH_DIR):
        d.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: `.gitignore` 를 고친다**

`RoboTrader_template/.gitignore` 의 **173행**(`backtest/tasso_labels/harvest/prose_only_candidates.csv`) **바로 뒤**에 삽입한다. 169행의 `!backtest/tasso_labels/harvest/*.csv` 보다 **뒤여야** 재차단이 이긴다.

```gitignore
# 🔴 [28]·[29] 전수 수집(2026-08-05)의 원문 캐시 — posts/·text/ 와 같은 사유(타인 저작물).
#    ⚠️ 실측: 이 줄들이 없으면 posts28/*.html 이 그대로 커밋 대상이 된다.
backtest/tasso_labels/harvest/posts28/
backtest/tasso_labels/harvest/text28/
backtest/tasso_labels/harvest/images28/
# 🔴 정독 에이전트의 배치 출력(JSONL)에도 원문 인용이 들어 있다.
backtest/tasso_labels/harvest/claims_batches/
# 🔴 주장 원장 중 `quote`(원문 인용) 열이 든 판본은 되살리지 않는다 — prose_only_candidates.csv 와 동일 사유.
#    공개판은 claims_cat2829.csv(quote 제거)이며 위 `!harvest/*.csv` 로 이미 추적된다.
backtest/tasso_labels/harvest/claims_cat2829_quoted.csv
# 🔑 반대 방향: 검증 로그는 V1·V2·V5 의 **유일한 근거**인데 `*.log`(68·138행)가 삼킨다.
#    survivorship_recount.log·c_rate_by_year.log 와 같은 예외 처리 — 순수 수치표이고 원문 인용이 없다.
!backtest/tasso_labels/harvest/verify_cat2829.log
```

- [ ] **Step 5: 테스트를 돌려 통과를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v`
Expected: 10 passed

- [ ] **Step 6: 커밋 (사장님 확인 후)**

```bash
git add RoboTrader_template/.gitignore \
        RoboTrader_template/backtest/tasso_labels/harvest/cat2829_common.py \
        RoboTrader_template/backtest/tasso_labels/tests/test_cat2829_pipeline.py
git diff --cached --name-only     # 🔴 원문 캐시가 섞이지 않았는지 육안 확인
git commit -m "feat(tasso): [28]·[29] 수집 공용 모듈 + gitignore 3건 교정

실측 확인 결과 조치 전 상태:
- harvest/posts28/*.html      tracked  (타인 저작물이 커밋된다)
- harvest/claims_*_quoted.csv tracked  (!harvest/*.csv 가 되살림)
- harvest/verify_cat2829.log  IGNORED  (*.log 가 삼킴)

경로를 Path(__file__) 기준 절대경로로 고정 — 구 수집기의 cwd 상대 경로가
수집분 29건을 저장소 밖에 남긴 원인이다. 회귀 테스트로 고정."
```

---

## Task 2: 주장 행 계약 (`claims_schema.py`)

**Files:**
- Create: `backtest/tasso_labels/harvest/claims_schema.py`
- Modify: `backtest/tasso_labels/tests/test_cat2829_pipeline.py` (테스트 추가)

**Interfaces:**
- Consumes: 없음
- Produces: `TOPICS: Tuple[str, ...]` · `VS_V1: Tuple[str, ...]` · `COLUMNS: Tuple[str, ...]` · `PUBLIC_COLUMNS: Tuple[str, ...]` · `QUOTE_MAX: int = 40` · `ANCHOR_REQUIRED: Tuple[str, ...]` · `validate_row(row: Dict) -> List[str]` (빈 리스트 = 통과)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`test_cat2829_pipeline.py` 끝에 추가한다:

```python
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
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v -k "row or column or quote or anchor or enum"`
Expected: FAIL — `FileNotFoundError: .../claims_schema.py`

- [ ] **Step 3: `claims_schema.py` 를 만든다**

```python
# -*- coding: utf-8 -*-
"""주장 원장의 행 계약 — 병합기·검증기·테스트의 단일 출처.

🔑 열거식 가드는 반드시 빠뜨린다. 열·enum·상한을 **여기 한 곳**에만 두고
   소비자는 전부 이 모듈을 읽는다.
"""
from __future__ import annotations

TOPICS = (
    "①후보선정", "②앵커", "③분할매수", "④분할매도",
    "⑤데이터기반", "⑥국면대응", "⑦프로그램·상품", "⑧기타",
)

VS_V1 = ("new", "agree", "conflict", "revision", "none")

# 원장 전체 열 (quote 포함 = 로컬 전용 판본)
COLUMNS = (
    "log_no", "post_date", "category", "claim_id", "topic",
    "claim", "numbers", "quote", "para_idx", "image_ref",
    "vs_v1", "v1_anchor",
)

# 공개 판본 = quote 제거. 커밋되는 쪽에는 타인의 원문을 싣지 않는다.
PUBLIC_COLUMNS = tuple(c for c in COLUMNS if c != "quote")

QUOTE_MAX = 40

# 이 값들이면 1판의 어느 절과 관계 맺는지 반드시 밝혀야 한다.
ANCHOR_REQUIRED = ("agree", "conflict", "revision")
# 이 값들이면 1판과 무관하므로 anchor 가 있으면 안 된다(반대 방향 결속).
ANCHOR_FORBIDDEN = ("new", "none")


def validate_row(row):
    """위반 사유 리스트를 반환한다. 빈 리스트 = 통과."""
    bad = []
    for col in COLUMNS:
        if col not in row:
            bad.append("MISSING_COLUMN:" + col)
    if bad:
        return bad

    if row["category"] not in (28, 29):
        bad.append("BAD_CATEGORY:" + repr(row["category"]))
    if row["topic"] not in TOPICS:
        bad.append("BAD_TOPIC:" + repr(row["topic"]))
    if row["vs_v1"] not in VS_V1:
        bad.append("BAD_VS_V1:" + repr(row["vs_v1"]))

    quote = "" if row["quote"] is None else str(row["quote"])
    if len(quote) > QUOTE_MAX:
        bad.append("QUOTE_TOO_LONG:" + str(len(quote)) + ">" + str(QUOTE_MAX))

    anchor = ("" if row["v1_anchor"] is None else str(row["v1_anchor"])).strip()
    if row["vs_v1"] in ANCHOR_REQUIRED and not anchor:
        bad.append("ANCHOR_REQUIRED_FOR:" + str(row["vs_v1"]))
    if row["vs_v1"] in ANCHOR_FORBIDDEN and anchor:
        bad.append("ANCHOR_FORBIDDEN_FOR:" + str(row["vs_v1"]))

    if not str(row["claim"] or "").strip():
        bad.append("EMPTY_CLAIM")
    return bad
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v`
Expected: 21 passed

- [ ] **Step 5: 커밋 (사장님 확인 후)**

```bash
git add RoboTrader_template/backtest/tasso_labels/harvest/claims_schema.py \
        RoboTrader_template/backtest/tasso_labels/tests/test_cat2829_pipeline.py
git commit -m "feat(tasso): 주장 원장 행 계약 + 양방향 anchor 결속

vs_v1 이 agree/conflict/revision 이면 v1_anchor 필수, new/none 이면 금지.
한 방향만 걸면 '전부 채우면 통과' 로 되돌려도 안 잡힌다."
```

---

## Task 3: 목록 확보 (①)

**Files:**
- Create: `backtest/tasso_labels/harvest/harvest_cat28_29_full.py`
- Modify: `backtest/tasso_labels/tests/test_cat2829_pipeline.py`

**Interfaces:**
- Consumes: `cat2829_common.api_json`·`category_list`·`CATEGORIES`·`CATLIST_JSON`
- Produces: `MAX_PAGES: int` · `fetch_post_list(cat, fetch=None, sleep=None) -> Dict[str, dict]` (logNo → item) · `category_counts(payload) -> Dict[int, int]` (categoryNo → postCnt)

**배경 — 구 스크립트를 그대로 쓰면 안 되는 이유**

`harvest_cat28_29.py:21,55-56` 은 `CUT = 2024-08-01` 이고, 페이지의 최고(最古) 글이 CUT 이전이면 `break` 한다. **최근 2년 표본 수집 전용**이다. 전 범위 수집에 그대로 쓰면 오래된 글이 통째로 빠지고, 그 사실은 산출물에 흔적을 남기지 않는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
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
    h = _load("harvest_cat28_29_full")
    pages = [[_item(1, MS_2025), _item(2, MS_2025)],
             [_item(2, MS_2025), _item(3, MS_2025)],
             []]
    got = h.fetch_post_list(28, fetch=_fake_pages(pages), sleep=lambda s: None)
    assert set(got) == {"1", "2", "3"}


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
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v -k "post_list or category_counts"`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: 목록 확보를 구현한다**

`harvest_cat28_29_full.py` 를 만든다 (본문 수집은 Task 4 에서 같은 파일에 더한다):

```python
# -*- coding: utf-8 -*-
"""[28] 주식기법 분석 · [29] 시황이슈 정리 — **전 범위** 수집.

🔴 구 harvest_cat28_29.py 와의 차이:
   ① 날짜 컷(CUT=2024-08-01) 없음 — 전 페이지를 끝까지 돈다
   ② 출력 경로가 cwd 상대가 아니라 cat2829_common 의 절대경로
"""
from __future__ import annotations

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
```

⚠️ `import cat2829_common as C` 가 성립하려면 스크립트가 `harvest/` 를 cwd 로 두고 실행되거나 `sys.path` 에 있어야 한다. **테스트는 `_load()` 가 파일 경로로 로드하므로** 같은 디렉토리의 모듈을 찾도록 파일 맨 위에 다음을 넣는다:

```python
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

(`import cat2829_common` 앞에 둔다.)

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v`
Expected: 27 passed

- [ ] **Step 5: 커밋 (사장님 확인 후)**

```bash
git add RoboTrader_template/backtest/tasso_labels/harvest/harvest_cat28_29_full.py \
        RoboTrader_template/backtest/tasso_labels/tests/test_cat2829_pipeline.py
git commit -m "feat(tasso): [28]·[29] 목록 전 페이지 확보

구 수집기는 CUT=2024-08-01 에서 break 하는 최근-2년 전용이었다.
날짜 컷 제거 + MAX_PAGES 도달 시 조용한 절단 대신 RuntimeError."
```

---

## Task 4: 본문 수집 (②)

**Files:**
- Modify: `backtest/tasso_labels/harvest/harvest_cat28_29_full.py`
- Modify: `backtest/tasso_labels/tests/test_cat2829_pipeline.py`

**Interfaces:**
- Consumes: Task 3 의 `build_catalog()` 산출 `CATLIST_JSON`
- Produces: `MIN_HTML_BYTES: int = 5000` · `harvest_one(entry, fetch=None, retries=3) -> dict` (메타 1건) · `harvest_bodies(catalog, ...) -> List[dict]` · `POSTMETA_JSON` 파일. 메타 키: `log_no`·`category`·`post_date`·`title`·`text_len`·`img_count`·`image_only`·`html_bytes`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
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
    assert "상승폭 45~48%" in (h.C.TEXT_DIR / (meta["text_file"])).read_text(encoding="utf-8")
    assert meta["text_len"] > 0


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
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v -k harvest_one`
Expected: FAIL — `AttributeError: module has no attribute 'harvest_one'`

- [ ] **Step 3: 본문 수집을 구현한다**

`harvest_cat28_29_full.py` 에 더한다:

```python
MIN_HTML_BYTES = 5000       # 구 수집기(harvest_cat28_29.py:62)의 실패 판정 기준을 승계
BODY_SLEEP = 1.0


def _stem(entry):
    return (str(entry["category"]) + "_" + entry["post_date"].replace("-", "")
            + "_" + entry["log_no"])


def harvest_one(entry, fetch=None, retries=3, sleep=None):
    """글 하나의 HTML 을 받아 저장하고 텍스트를 뽑아 메타를 만든다."""
    fetch = fetch or C.fetch_html
    sleep = sleep if sleep is not None else time.sleep
    stem = _stem(entry)
    html_path = C.POSTS_DIR / (stem + ".html")
    text_path = C.TEXT_DIR / (stem + ".txt")

    src = None
    for attempt in range(retries):
        src = fetch(entry["log_no"])
        if src is not None and len(src.encode("utf-8")) >= MIN_HTML_BYTES:
            break
        src = None
        if attempt < retries - 1:
            sleep(BODY_SLEEP * (attempt + 1))
    if src is None:
        raise RuntimeError("HTML_TOO_SHORT:" + entry["log_no"])

    html_path.write_text(src, encoding="utf-8")
    text = C.html_to_text(src)
    text_path.write_text(text, encoding="utf-8")

    return {
        "log_no": entry["log_no"],
        "category": entry["category"],
        "post_date": entry["post_date"],
        "title": entry.get("title", ""),
        "html_bytes": len(src.encode("utf-8")),
        "text_len": len(text),
        "text_file": stem + ".txt",
        "img_count": C.count_images(src),
        "image_only": len(text) == 0,
    }


def harvest_bodies(catalog, sleep=None):
    """카탈로그 전건을 수집하고 POSTMETA_JSON 을 쓴다. 실패는 즉시 올린다."""
    sleep = sleep if sleep is not None else time.sleep
    C.ensure_dirs()
    metas = []
    for log_no in sorted(catalog["posts"]):
        metas.append(harvest_one(catalog["posts"][log_no], sleep=sleep))
        sleep(BODY_SLEEP)
    C.POSTMETA_JSON.write_text(
        json.dumps(metas, ensure_ascii=False, indent=1), encoding="utf-8")
    return metas


def main():
    catalog = build_catalog()
    metas = harvest_bodies(catalog)
    print("카탈로그", len(catalog["posts"]), "건 · 본문", len(metas), "건")
    print("postCnt", catalog["post_cnt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v`
Expected: 30 passed

- [ ] **Step 5: 커밋 (사장님 확인 후)**

```bash
git add RoboTrader_template/backtest/tasso_labels/harvest/harvest_cat28_29_full.py \
        RoboTrader_template/backtest/tasso_labels/tests/test_cat2829_pipeline.py
git commit -m "feat(tasso): [28]·[29] 본문 수집 + image_only 자동 승격

텍스트 0자 글은 '이미지를 가리키는 문장' 도 없어서 ④단계 선별을 그냥
통과한다. image_only 플래그로 무조건 승격시킨다."
```

---

## Task 5: V1 — 수집 회수율 게이트

**Files:**
- Create: `backtest/tasso_labels/harvest/verify_cat2829.py`
- Modify: `backtest/tasso_labels/tests/test_cat2829_pipeline.py`

**Interfaces:**
- Consumes: `CATLIST_JSON`·`POSTMETA_JSON`
- Produces: `v1_coverage(catalog_lognos, saved_lognos, post_cnt, listed_cnt) -> dict` — 키 `status`(`"PASS"`/`"FAIL"`)·`missing`(list)·`extra`(list)·`post_cnt_delta`(dict)

**설계 근거 (스펙 §5 「V1 에서 postCnt 가 안 맞으면」)**

`postCnt` 와 목록 API 반환 수는 비공개·삭제 글로 어긋날 수 있다. **어긋남 자체는 실패가 아니다** — 수치로 기록하고, 규명 전에는 「전수」라는 표현을 안 쓴다. 반면 **목록 ↔ 저장 파일의 차집합 0 은 무조건 강제**한다. 이쪽은 우리 책임이다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
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
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v -k v1_`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: V1 을 구현한다**

```python
# -*- coding: utf-8 -*-
"""[28]·[29] 파이프라인 검증 — V1(수집) · V2(원장) · V5(revision 재판정).

각 검사가 **서로 다른 실패 방식**을 잡는다. 하나가 다른 하나를 대체하지 않는다.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cat2829_common as C          # noqa: E402
import claims_schema as S           # noqa: E402


def v1_coverage(catalog_lognos, saved_lognos, post_cnt, listed_cnt):
    """목록 ↔ 저장 파일 차집합 0 강제 + postCnt 차이 기록.

    catalog_lognos / saved_lognos : set[str]
    post_cnt   : {categoryNo: int|None}   카테고리 API 가 주장하는 글 수
    listed_cnt : {categoryNo: int}        목록 API 가 실제로 준 글 수
    """
    missing = sorted(set(catalog_lognos) - set(saved_lognos))
    extra = sorted(set(saved_lognos) - set(catalog_lognos))
    delta = {}
    for cat, claimed in post_cnt.items():
        delta[cat] = None if claimed is None else listed_cnt.get(cat, 0) - claimed
    return {
        "status": "FAIL" if (missing or extra) else "PASS",
        "missing": missing,
        "extra": extra,
        "post_cnt_delta": delta,
    }
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v`
Expected: 35 passed

- [ ] **Step 5: 커밋 (사장님 확인 후)**

```bash
git add RoboTrader_template/backtest/tasso_labels/harvest/verify_cat2829.py \
        RoboTrader_template/backtest/tasso_labels/tests/test_cat2829_pipeline.py
git commit -m "feat(tasso): V1 수집 회수율 — 우리 책임 구간만 강제

목록↔파일 차집합 0 은 FAIL. postCnt 차이는 기록만 하고 통과시킨다
(비공개·삭제 글로 어긋날 수 있고, 그건 우리 잘못이 아니다)."
```

---

## Task 6: 원장 병합 + V2

**Files:**
- Create: `backtest/tasso_labels/harvest/build_claims_cat2829.py`
- Modify: `backtest/tasso_labels/harvest/verify_cat2829.py`
- Modify: `backtest/tasso_labels/tests/test_cat2829_pipeline.py`

**Interfaces:**
- Consumes: `claims_schema.COLUMNS`·`PUBLIC_COLUMNS`·`validate_row` · `CLAIMS_BATCH_DIR`
- Produces: `load_batches(batch_dir) -> List[dict]` · `write_ledgers(rows, public_path, quoted_path) -> None` · `verify_cat2829.v2_ledger_coverage(rows, expected_lognos) -> dict` — 키 `status`·`missing_lognos`·`rows`·`posts`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
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
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v -k "batches or ledgers or v2_"`
Expected: FAIL — 모듈/함수 없음

- [ ] **Step 3: 병합기를 만든다**

`build_claims_cat2829.py`:

```python
# -*- coding: utf-8 -*-
"""정독 에이전트의 배치 JSONL → 주장 원장 CSV 2벌.

- claims_cat2829.csv        quote 제거 = 커밋본
- claims_cat2829_quoted.csv quote 포함 = 로컬 전용 (gitignore 재차단)
"""
from __future__ import annotations

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cat2829_common as C          # noqa: E402
import claims_schema as S           # noqa: E402


def load_batches(batch_dir):
    """배치 디렉토리의 *.jsonl 을 전부 읽고 **행마다 스키마 검증**한다."""
    rows = []
    for path in sorted(os.listdir(str(batch_dir))):
        if not path.endswith(".jsonl"):
            continue
        full = os.path.join(str(batch_dir), path)
        with open(full, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                bad = S.validate_row(row)
                if bad:
                    raise ValueError(path + ":" + str(lineno) + " " + ";".join(bad))
                rows.append(row)
    return rows


def write_ledgers(rows, public_path, quoted_path):
    """두 벌을 쓴다. 열 순서는 claims_schema 가 정한다."""
    for path, cols in ((quoted_path, S.COLUMNS), (public_path, S.PUBLIC_COLUMNS)):
        with open(str(path), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(cols), extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)


def main():
    rows = load_batches(C.CLAIMS_BATCH_DIR)
    write_ledgers(rows, C.CLAIMS_PUBLIC_CSV, C.CLAIMS_QUOTED_CSV)
    print("주장", len(rows), "행 · 글", len({r["log_no"] for r in rows}), "건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: V2 를 `verify_cat2829.py` 에 더한다**

```python
def v2_ledger_coverage(rows, expected_lognos):
    """원장이 **모든 글**을 덮는가.

    「글당 최소 1행」 규칙 덕에, 원장에 없는 log_no = 정독이 안 된 글이다.
    (주장이 없는 글도 topic=⑧기타 · vs_v1=none 행을 남기게 돼 있다.)
    """
    seen = {r["log_no"] for r in rows}
    missing = sorted(set(expected_lognos) - seen)
    return {
        "status": "FAIL" if missing else "PASS",
        "missing_lognos": missing,
        "rows": len(rows),
        "posts": len(seen),
    }
```

- [ ] **Step 5: 테스트를 돌려 통과를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v`
Expected: 40 passed

- [ ] **Step 6: 커밋 (사장님 확인 후)**

```bash
git add RoboTrader_template/backtest/tasso_labels/harvest/build_claims_cat2829.py \
        RoboTrader_template/backtest/tasso_labels/harvest/verify_cat2829.py \
        RoboTrader_template/backtest/tasso_labels/tests/test_cat2829_pipeline.py
git commit -m "feat(tasso): 원장 병합(quote 유/무 2벌) + V2 원장 회수율"
```

---

## Task 7: V5 — `conflict` 인가 저자의 개정인가

**Files:**
- Modify: `backtest/tasso_labels/harvest/verify_cat2829.py`
- Modify: `backtest/tasso_labels/tests/test_cat2829_pipeline.py`

**Interfaces:**
- Consumes: 원장 행 리스트
- Produces: `v5_revision_candidates(rows) -> List[dict]` — 각 원소 키 `topic`·`v1_anchor`·`timeline`(list of `{post_date, log_no, numbers, claim_id}`)

**설계 근거**

저자는 같은 규칙을 몇 년에 걸쳐 반복 서술하고 그때마다 수치가 바뀐다. 1판이 이미 잡은 예 — 누적 통계 **1만 건 이상(2025-08) → 12,500여 건(2025-10) → 13,503건(2026-07)** (`METHOD.md:107`). `conflict` 로 묶으면 저자의 버전업이 우리의 모순으로 기록된다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
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
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v -k v5_`
Expected: FAIL — `AttributeError: v5_revision_candidates`

- [ ] **Step 3: V5 를 구현한다**

```python
def v5_revision_candidates(rows):
    """`conflict` 로 분류된 행 중, **같은 (topic, v1_anchor)** 안에서 시간에 따라
    numbers 가 바뀐 묶음을 revision 후보로 올린다.

    ⚠️ 판정이 아니라 **후보 제시**다. 최종 분류는 사람이 한다.
    """
    groups = {}
    for r in rows:
        if r.get("vs_v1") != "conflict":
            continue
        key = (r["topic"], str(r.get("v1_anchor") or ""))
        groups.setdefault(key, []).append(r)

    out = []
    for (topic, anchor), grp in sorted(groups.items()):
        grp = sorted(grp, key=lambda r: (r["post_date"], r["log_no"]))
        numbers = [str(r.get("numbers") or "") for r in grp]
        if len(grp) < 2 or len(set(numbers)) < 2:
            continue
        out.append({
            "topic": topic,
            "v1_anchor": anchor,
            "timeline": [{"post_date": r["post_date"], "log_no": r["log_no"],
                          "numbers": str(r.get("numbers") or ""),
                          "claim_id": r["claim_id"]} for r in grp],
        })
    return out
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v`
Expected: 44 passed

- [ ] **Step 5: 커밋 (사장님 확인 후)**

```bash
git add RoboTrader_template/backtest/tasso_labels/harvest/verify_cat2829.py \
        RoboTrader_template/backtest/tasso_labels/tests/test_cat2829_pipeline.py
git commit -m "feat(tasso): V5 — conflict 중 저자의 개정을 분리

같은 (topic, v1_anchor) 안에서 시간에 따라 수치가 바뀌면 revision 후보.
오경보를 안 내는 성질(다른 topic·동일 수치)도 테스트로 고정."
```

---

## Task 8: 정독 배치 분할기

**Files:**
- Create: `backtest/tasso_labels/harvest/batch_cat2829.py`
- Modify: `backtest/tasso_labels/tests/test_cat2829_pipeline.py`

**Interfaces:**
- Consumes: `POSTMETA_JSON` 의 메타 리스트 (`text_len` 필요)
- Produces: `make_batches(metas, target_chars=60000) -> List[List[dict]]` — 결정적(입력이 같으면 출력이 같다)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
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
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v -k make_batches`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: 분할기를 구현한다**

```python
# -*- coding: utf-8 -*-
"""정독 에이전트에게 줄 배치를 **결정적으로** 나눈다.

정렬 키가 (category, post_date, log_no) 이므로 입력 순서와 무관하게 같은 결과가 나온다.
"""
from __future__ import annotations


def make_batches(metas, target_chars=60000):
    """누적 텍스트 길이가 target_chars 를 넘기 직전에 배치를 끊는다.

    한 글이 혼자 target 을 넘으면 그 글만 담은 배치를 만든다(쪼개지 않는다).
    """
    ordered = sorted(metas, key=lambda m: (m["category"], m["post_date"], m["log_no"]))
    batches = []
    cur = []
    cur_len = 0
    for m in ordered:
        n = int(m.get("text_len") or 0)
        if cur and cur_len + n > target_chars:
            batches.append(cur)
            cur, cur_len = [], 0
        cur.append(m)
        cur_len += n
        if cur_len >= target_chars:
            batches.append(cur)
            cur, cur_len = [], 0
    if cur:
        batches.append(cur)
    return batches
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v`
Expected: 48 passed

- [ ] **Step 5: 커밋 (사장님 확인 후)**

```bash
git add RoboTrader_template/backtest/tasso_labels/harvest/batch_cat2829.py \
        RoboTrader_template/backtest/tasso_labels/tests/test_cat2829_pipeline.py
git commit -m "feat(tasso): 정독 배치 결정적 분할 — 전건 정확히 1회 커버"
```

---

## Task 9: 【실행】 수집 + V1 게이트

여기부터는 TDD 가 아니라 **실행**이다. 각 태스크는 게이트를 통과해야 다음으로 간다.

**Files:**
- Create (로컬, 커밋 안 됨): `harvest/posts28/*.html` · `harvest/text28/*.txt`
- Create (커밋): `harvest/catlist_28_29.json` · `harvest/postmeta_28_29.json` · `harvest/verify_cat2829.log`

- [ ] **Step 1: 수집을 돌린다**

```bash
cd D:/tmp/wt-tasso-cat2829/RoboTrader_template/backtest/tasso_labels/harvest
python harvest_cat28_29_full.py 2>&1 | tee harvest_cat2829_run.log
```

예상 소요: 432건 × (본문 1.0초 + 목록 페이지 15회 × 0.4초) ≈ **8~10분**

- [ ] **Step 2: V1 을 돌려 게이트를 통과한다**

```bash
python -c "
import json, sys
sys.path.insert(0,'.')
import cat2829_common as C, verify_cat2829 as V
cat = json.loads(C.CATLIST_JSON.read_text(encoding='utf-8'))
meta = json.loads(C.POSTMETA_JSON.read_text(encoding='utf-8'))
listed = {}
for p in cat['posts'].values():
    listed[p['category']] = listed.get(p['category'], 0) + 1
r = V.v1_coverage(set(cat['posts']), {m['log_no'] for m in meta},
                  {int(k): v for k, v in cat['post_cnt'].items()}, listed)
print(json.dumps(r, ensure_ascii=False, indent=1))
open(str(C.VERIFY_LOG),'a',encoding='utf-8').write('V1 '+json.dumps(r,ensure_ascii=False)+'\n')
sys.exit(0 if r['status']=='PASS' else 1)
"
```

Expected: `status: PASS` · `missing: []` · `extra: []`

🔴 **`status: FAIL` 이면 여기서 멈춘다.** 원인을 규명하기 전에는 다음 태스크로 가지 않는다.
🔧 **`post_cnt_delta` 가 0이 아니면 값을 기록하고 진행한다.** 다만 이후 문서에서 「전수」라는 표현을 쓰기 전에 사유를 규명한다.

- [ ] **Step 3: 텍스트 규모를 실측한다 (D-1 을 닫는다)**

```bash
python -c "
import json, sys
sys.path.insert(0,'.')
import cat2829_common as C
meta = json.loads(C.POSTMETA_JSON.read_text(encoding='utf-8'))
tot = sum(m['text_len'] for m in meta)
img_only = [m for m in meta if m['image_only']]
print('글', len(meta), '· 총 텍스트', format(tot, ','), '자 · 평균', tot//max(len(meta),1))
print('image_only', len(img_only), '건 · 총 이미지', sum(m['img_count'] for m in meta), '장')
"
```

스펙 §1의 추정(약 100만 자)과 **2배 이상 어긋나면 `make_batches` 의 `target_chars` 를 재산정**한다.

- [ ] **Step 4: 원문이 커밋에 안 섞였는지 확인하고 커밋 (사장님 확인 후)**

```bash
cd D:/tmp/wt-tasso-cat2829
git status --ignored --short RoboTrader_template/backtest/tasso_labels/harvest/ | head -20
git add RoboTrader_template/backtest/tasso_labels/harvest/catlist_28_29.json \
        RoboTrader_template/backtest/tasso_labels/harvest/postmeta_28_29.json \
        RoboTrader_template/backtest/tasso_labels/harvest/verify_cat2829.log
git diff --cached --name-only     # 🔴 posts28/·text28/ 이 한 줄도 없어야 한다
git commit -m "data(tasso): [28]·[29] 전 범위 목록·메타 수집 + V1 통과"
```

---

## Task 10: 【실행】 전건 정독 (③) + V2 게이트

- [ ] **Step 1: 배치를 만든다**

```bash
cd D:/tmp/wt-tasso-cat2829/RoboTrader_template/backtest/tasso_labels/harvest
python -c "
import json, sys
sys.path.insert(0,'.')
import cat2829_common as C, batch_cat2829 as B
meta = json.loads(C.POSTMETA_JSON.read_text(encoding='utf-8'))
bs = B.make_batches(meta, target_chars=60000)
for i, b in enumerate(bs, 1):
    print('batch', i, len(b), '글', sum(m[\"text_len\"] for m in b), '자')
json.dump([[m['log_no'] for m in b] for b in bs],
          open('batch_plan.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
print('총', len(bs), '배치')
"
```

- [ ] **Step 2: 배치마다 정독 에이전트를 띄운다**

각 에이전트에게 주는 지시(배치 N):

```
너는 태쏘 블로그 방법론 정독 담당이다. 아래 텍스트 파일들을 **전문 정독**하고
주장 단위 JSONL 을 만든다.

읽을 파일: backtest/tasso_labels/harvest/text28/ 의 {배치의 파일명 목록}
스키마 정의: backtest/tasso_labels/harvest/claims_schema.py 를 **직접 읽어라.**
   ⚠️ 이 지시문에 옮겨 적은 목록을 믿지 말고 코드에서 값을 가져올 것.
1판 대조 대상: backtest/tasso_labels/METHOD.md 를 읽고 vs_v1·v1_anchor 를 채운다.

출력: backtest/tasso_labels/harvest/claims_batches/b{NN}.jsonl (한 줄 = 한 행)

규칙:
- 🔴 **글당 최소 1행.** 방법론 주장이 없는 글도
  topic="⑧기타", claim="방법론 주장 없음", vs_v1="none", v1_anchor="" 행을 남긴다.
- quote 는 **40자 이내**. 넘으면 검증기가 배치 전체를 거부한다.
- para_idx 는 텍스트 파일에서 0-base 문단 인덱스(개행으로 나눈 순번).
- image_ref 는 본문이 이미지를 가리킬 때만 true
  (예: "아래 표", "그림 참조", 수치가 문장 중간에서 끊김).
- vs_v1 이 agree/conflict/revision 이면 v1_anchor 필수(예: "§1-③"),
  new/none 이면 v1_anchor 는 빈 문자열이어야 한다.
- 수치는 **원문 표기 그대로** numbers 에 넣는다(반올림·환산 금지).
- **topic 은 단일 배정이다(D-4).** 두 단계에 걸치는 주장은 topic 을 골라 담지 말고
  **행을 나눠라** — 예: "하락장에서는 HDR 을 좁혀 전량 매도" 는 ④분할매도 1행 +
  ⑥국면대응 1행. 한 행에 두 topic 을 적을 자리는 없다.

마지막에 처리한 글 수와 생성한 행 수를 보고하라.
```

⚠️ **에이전트가 준 목록을 그대로 베끼지 말 것** — 이 트랙의 규칙: *「목록을 받아 적으면 조용히 다른 것을 검사한다」*. 지시문이 스키마를 **코드에서 읽으라고** 요구하는 이유다.

- [ ] **Step 3: 원장을 병합한다**

```bash
python build_claims_cat2829.py
```

Expected: 스키마 위반 0 (위반이 있으면 `ValueError` 로 파일:줄 을 찍고 멈춘다 → 해당 배치 재실행)

- [ ] **Step 4: V2 게이트**

```bash
python -c "
import csv, json, sys
sys.path.insert(0,'.')
import cat2829_common as C, verify_cat2829 as V
rows = list(csv.DictReader(open(str(C.CLAIMS_QUOTED_CSV), encoding='utf-8-sig')))
meta = json.loads(C.POSTMETA_JSON.read_text(encoding='utf-8'))
r = V.v2_ledger_coverage(rows, {m['log_no'] for m in meta})
print(json.dumps(r, ensure_ascii=False, indent=1)[:2000])
open(str(C.VERIFY_LOG),'a',encoding='utf-8').write('V2 '+json.dumps({k:v for k,v in r.items() if k!='missing_lognos'})+' missing='+str(len(r['missing_lognos']))+'\n')
sys.exit(0 if r['status']=='PASS' else 1)
"
```

🔴 `FAIL` 이면 `missing_lognos` 에 해당하는 배치를 **재실행**한다.

- [ ] **Step 5: V5 를 돌리고 후보를 사람이 재분류한다**

```bash
python -c "
import csv, json, sys
sys.path.insert(0,'.')
import cat2829_common as C, verify_cat2829 as V
rows = list(csv.DictReader(open(str(C.CLAIMS_QUOTED_CSV), encoding='utf-8-sig')))
c = V.v5_revision_candidates(rows)
print(json.dumps(c, ensure_ascii=False, indent=1))
open(str(C.VERIFY_LOG),'a',encoding='utf-8').write('V5 후보 '+str(len(c))+'묶음\n')
"
```

후보를 검토해 실제 개정이면 원장의 `vs_v1` 을 `revision` 으로 고치고 병합을 다시 돌린다.

- [ ] **Step 6: 커밋 (사장님 확인 후)**

```bash
cd D:/tmp/wt-tasso-cat2829
git add RoboTrader_template/backtest/tasso_labels/harvest/claims_cat2829.csv \
        RoboTrader_template/backtest/tasso_labels/harvest/verify_cat2829.log
git diff --cached --name-only   # 🔴 claims_batches/·*_quoted.csv 가 없어야 한다
git commit -m "data(tasso): [28]·[29] 전건 정독 주장 원장 + V2·V5 통과"
```

---

## Task 11: 【실행】 이미지 2차 판독 (④)

- [ ] **Step 1: 판독 대상을 센다 (D-3 을 닫는다)**

```bash
cd D:/tmp/wt-tasso-cat2829/RoboTrader_template/backtest/tasso_labels/harvest
python -c "
import csv, json, sys
sys.path.insert(0,'.')
import cat2829_common as C
rows = list(csv.DictReader(open(str(C.CLAIMS_QUOTED_CSV), encoding='utf-8-sig')))
meta = {m['log_no']: m for m in json.loads(C.POSTMETA_JSON.read_text(encoding='utf-8'))}
refs = {r['log_no'] for r in rows if str(r['image_ref']).lower() in ('true','1')}
only = {k for k, m in meta.items() if m['image_only']}
tgt = sorted((refs | only) & set(meta))
print('image_ref', len(refs), '· image_only', len(only), '· 합집합', len(tgt), '글')
print('이미지 총', sum(meta[k]['img_count'] for k in tgt), '장')
stems = [str(meta[k]['category']) + '_' + meta[k]['post_date'].replace('-','') + '_' + k for k in tgt]
json.dump(stems, open('image_targets.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
print('image_targets.json 에', len(stems), '건 저장')
"
```

`stems` 는 `harvest_cat28_29_full._stem()` 과 **같은 규칙**(`{cat}_{yyyymmdd}_{logNo}`)이라 `posts28/` 파일명과 일치한다.

🔴 **이미지가 300장을 넘으면 진행 전에 사장님께 보고**하고 범위를 정한다. 무단으로 줄이지 않는다 — 줄이면 **줄였다는 사실을 로그에 남긴다.**

- [ ] **Step 2: 대상 글의 이미지를 내려받는다**

```bash
python -c "
import json, re, subprocess, sys
sys.path.insert(0,'.')
import cat2829_common as C
targets = json.load(open('image_targets.json', encoding='utf-8'))  # Step 1 에서 저장
for stem in targets:
    src = (C.POSTS_DIR / (stem + '.html')).read_text(encoding='utf-8')
    urls = re.findall(r'<img[^>]+src=\"([^\"]+)\"', src)
    for i, u in enumerate(urls):
        u = u.split('?')[0] + '?type=w966'
        out = C.IMAGES_DIR / (stem + '_' + str(i).zfill(3) + '.jpg')
        if not out.exists():
            subprocess.run(['curl','-s','-m','40','-A',C.UA,'-H','Referer: https://m.blog.naver.com/'+C.BLOG,'-o',str(out),u])
"
```

- [ ] **Step 3: 판독 에이전트를 띄운다**

지시: *"`images28/` 의 지정 이미지를 보고, 텍스트에 없는 방법론 수치·규칙·표가 있으면 `claims_batches/img_{NN}.jsonl` 에 같은 스키마로 추가하라. `image_ref=true`, `para_idx=-1`, `quote=""` 로 둔다. 이미지에서 새 정보가 없으면 행을 만들지 않는다."*

- [ ] **Step 4: 병합·V2 재실행 후 커밋 (사장님 확인 후)**

```bash
python build_claims_cat2829.py && cd D:/tmp/wt-tasso-cat2829
git add RoboTrader_template/backtest/tasso_labels/harvest/claims_cat2829.csv
git commit -m "data(tasso): 이미지 2차 판독 주장 편입"
```

---

## Task 12: 【실행】 V3 · V4 — 정독 품질 측정

**V3 이 이 계획의 판별력 게이트다.** V1·V2 는 「많이 모았나」를 재고, V3 만 「알아야 할 것을 놓쳤는가」를 잰다.

- [ ] **Step 1: V3 — 1판 서술 항목을 열거한다**

에이전트 A 에게: *"`METHOD.md` 를 읽고 **검증 가능한 서술 항목**을 전부 열거하라 (§1 파이프라인 4단계의 각 규칙, §2 데이터 규모 수치, §5 프리셋 표, §6 주의사항). 항목마다 고유 id(`v1-01`…)와 §절 위치, 핵심 주장 한 줄, 관련 수치를 `v3_v1_items.csv` 로 내라. 원장은 보지 마라."*

🔑 **원장을 안 보고 열거하게 하는 것이 핵심**이다. 원장을 보면 있는 것만 열거하게 된다.

- [ ] **Step 2: V3 — 각 항목이 원장에 있는지 대조한다**

에이전트 B 에게: *"`v3_v1_items.csv` 의 각 항목이 `claims_cat2829.csv` 에서 `agree`/`conflict`/`revision` 중 무엇으로 재등장하는지, 아니면 **미등장**인지 판정해 `v3_result.csv` 를 내라. 미등장 항목은 사유를 추정하지 말고 미등장으로 두어라."*

- [ ] **Step 3: V3 결과를 기록한다 — 0건일 필요는 없다**

```
V3: 1판 서술 N항목 중 agree A · conflict B · revision C · 미등장 D
```

🔴 **미등장 D 가 0이 아니어도 실패가 아니다.** 다만 **각각에 설명이 붙어야 한다** (예: *"해당 서술의 출처 글이 [32] 트레이딩 기록에 있어 [28]·[29] 원장에 없는 것이 정상"*). 설명 없는 미등장은 정독 재실행 사유다.

**기지 불일치 1건을 여기서 처리한다** — `METHOD.md:25`·`:177` 은 계산기 캡처를 **52장**, `calc_table.csv` 는 **51 데이터행**(2026-08-05 실측, 헤더 제외), `TASSO_OVERVIEW.md` 는 **51장**이라 쓴다. ⚠️ *52장을 읽었으나 1장이 판독 불가였다* 도 성립하므로 **1판이 틀렸다고 단정하지 않는다.** 해소하거나, 못 하면 **불일치로 명시**한다.

- [ ] **Step 4: V4 — 무작위 12건 독립 재정독 (D-2 를 닫는다)**

```bash
cd D:/tmp/wt-tasso-cat2829/RoboTrader_template/backtest/tasso_labels/harvest
python -c "
import json, random, sys
sys.path.insert(0,'.')
import cat2829_common as C
SEED = 20260805                      # 🔑 시드를 로그에 남긴다
N = 12
meta = json.loads(C.POSTMETA_JSON.read_text(encoding='utf-8'))
lognos = sorted(m['log_no'] for m in meta)          # 정렬 = 결정적 출발점
picked = sorted(random.Random(SEED).sample(lognos, min(N, len(lognos))))
by = {m['log_no']: m for m in meta}
cov = {}
for p in picked:
    k = str(by[p]['category']) + '/' + by[p]['post_date'][:4]
    cov[k] = cov.get(k, 0) + 1
print('SEED', SEED, '· 표본', len(picked))
print('실현 분포', cov)
print(picked)
json.dump({'seed': SEED, 'n': N, 'sample': picked, 'coverage': cov},
          open('v4_sample.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
"
```

**층화가 아니라 단순 무작위 추출(SRS)이다 — D-2 를 이렇게 닫는다.**
스펙 초안은 「카테고리·연도 층화」였으나, 2026-08-05 합성 데이터로 검증해 보니
**층 20개에 표본 12건이면 층화가 「20개 층 중 12개 고르기」로 퇴화**한다. 층 크기
(150 vs 282건)를 무시해 비례성이 없어지고, 실측 draw 가 cat28 9 / cat29 3 으로
치우쳤다. SRS 는 기댓값상 정확히 비례하고 이 아티팩트가 없다 —
같은 합성 데이터에서 cat28 **4**(모집단 비율 기대 4.2), 2000 시드 평균 **4.09**.

⚠️ **대신 「실현 분포」를 반드시 출력한다.** SRS 는 운 나쁘면 한 해에 몰릴 수 있고,
그때는 관리자가 보고 판단해야 한다. **분포를 안 찍으면 몰렸다는 사실 자체가 안 보인다.**

에이전트 C(원장을 **안 본** 새 에이전트)에게: *"이 12건의 텍스트를 정독하고 주장 JSONL 을 독립적으로 만들어라."* 그 결과를 원장과 대조해 **놓친 주장 수**를 센다.

- [ ] **Step 5: V4 를 분자·분모로 기록한다**

```
V4: 표본 12건 · 독립 추출 M주장 · 원장에 없던 것 N주장 (N/M)
```

⚠️ **"놓친 주장 없음" 이라고 쓰지 않는다.** 12/432 = 2.8% 표본이므로 신뢰구간이 넓다. 이 트랙의 규칙 — *「비율이 재현된다고 분수가 맞은 것이 아니다. 분자·분모를 각각 세라」*.

- [ ] **Step 6: 커밋 (사장님 확인 후)**

```bash
cd D:/tmp/wt-tasso-cat2829
git add RoboTrader_template/backtest/tasso_labels/harvest/v3_v1_items.csv \
        RoboTrader_template/backtest/tasso_labels/harvest/v3_result.csv \
        RoboTrader_template/backtest/tasso_labels/harvest/v4_sample.json \
        RoboTrader_template/backtest/tasso_labels/harvest/verify_cat2829.log
git commit -m "verify(tasso): V3 1판 역방향 대조 + V4 독립 재정독 회수율"
```

---

## Task 13: METHOD.md 2판 집필

**Files:**
- Modify: `backtest/tasso_labels/METHOD.md`

- [ ] **Step 1: 집필 에이전트를 띄운다**

지시:

```
`claims_cat2829.csv`(주장 원장) · `v3_result.csv` · `METHOD.md`(1판) 를 읽고
METHOD.md 2판을 만든다.

원칙:
- 🔴 **1판을 덮지 않는다.** 뒤집힌 서술은 삭제가 아니라 **취소선 + 사유**로 남긴다.
  (이 트랙의 정정 이력이 「정정도 정정의 대상이 된다」를 실증했다.)
- §0 자료범위 표를 갱신한다. **[28]·[29] 에 대해서만 전수**임을 쓰고,
  [1] 일상·잡담 · [35] 과거기록 **169건 미수집**을 함께 명시한다.
  ⚠️ postCnt 차이가 규명 안 됐으면 「전수」라는 표현을 쓰지 말고 실제 수치를 쓴다.
- V3 결과(미등장 항목과 그 설명)와 V4 회수율(분자/분모)을 §0 에 싣는다.
- 모든 수치는 원장·검증 산출물에서 **직접 인용**한다. 재계산·추정 금지.
- 새 주장은 topic 별로 §1 파이프라인 4단계 구조에 편입한다.
- ⑥국면대응 주장은 1판에 대응 절이 없으므로 **새 절**을 만든다.
```

- [ ] **Step 2: 숫자를 관리자가 직접 검산한다**

🔴 **에이전트 자기보고를 머지 게이트로 쓰지 않는다.** 2판이 인용한 수치를 원장에서 직접 세어 대조한다:

```bash
cd D:/tmp/wt-tasso-cat2829/RoboTrader_template/backtest/tasso_labels/harvest
python -c "
import csv, collections, sys
rows = list(csv.DictReader(open('claims_cat2829.csv', encoding='utf-8-sig')))
print('행', len(rows), '· 글', len({r[\"log_no\"] for r in rows}))
print('topic', dict(collections.Counter(r['topic'] for r in rows)))
print('vs_v1', dict(collections.Counter(r['vs_v1'] for r in rows)))
print('category', dict(collections.Counter(r['category'] for r in rows)))
"
```

- [ ] **Step 3: 커밋 (사장님 확인 후)**

```bash
cd D:/tmp/wt-tasso-cat2829
git add RoboTrader_template/backtest/tasso_labels/METHOD.md
git commit -m "docs(tasso): METHOD 2판 — [28]·[29] 432건 전수 기반"
```

---

## Task 14: 기존 결론 영향 판정 + 문서 정정

- [ ] **Step 1: 판정 에이전트를 띄운다 (집필자와 다른 에이전트)**

🔴 **집필자가 자기 글의 영향 판정을 겸하면 자가승인이다.** 새 에이전트에게 원장과 2판을 주고 판정시킨다.

지시:

```
`claims_cat2829.csv` 와 `METHOD.md` 2판을 읽고, 새로 확인된 사실이 아래 **셋 각각**을
흔드는지 판정하라. 흔들지 않았다면 **흔들지 않았다고, 근거와 함께** 적어라.

① `tasso_entry_timing/README.md` 의 **7차 FAIL 해석**
   — 7차는 "매도·후보 선정에 대해 아무 말도 하지 않는다" 고 명시했다.
     그 명시가 여전히 유효한가? 새 사실이 7차의 **범위 선언 자체**를 흔드는가?
② `CLOSING.md` 의 **2막 종결 사유**
   — 종결 사유는 검정력(MDE 연 21~22%p)이다. 새 사실이 MDE 계산의 **입력**
     (표본 수·분산·비용)을 바꾸는가? 재개 조건 R1~R5 중 충족되는 것이 생겼는가?
③ `METHOD.md` **1판 서술**
   — v3_result.csv 의 conflict 항목별로, 1판이 틀렸는지 저자가 개정했는지.

각 판정에 **원장의 claim_id 를 근거로 달아라.** 근거 없는 판정은 반려된다.
출력: `backtest/tasso_labels/harvest/impact_v2.md`
```

- [ ] **Step 2: 판정 결과를 `METHOD.md` §8 로 편입한다**

- [ ] **Step 3: 판정이 요구할 때만 상위 문서를 정정한다**

- `CLOSING.md` §2.3 수집범위표는 **무조건 갱신**한다 (수집 사실이 바뀌었다).
- `CLOSING.md` 결론부·`TASSO_OVERVIEW.md` 는 **①②가 흔들렸을 때만** 고친다.
- 🔴 **흔들지 않았으면 고치지 않는다.** 「고칠 게 없었다」도 결과다.

- [ ] **Step 4: 최종 확인 후 커밋 (사장님 확인 후)**

```bash
cd D:/tmp/wt-tasso-cat2829
pytest RoboTrader_template/backtest/tasso_labels/tests/test_cat2829_pipeline.py -v
git status --ignored --short RoboTrader_template/backtest/tasso_labels/harvest/ | head -20
git add -A RoboTrader_template/backtest/tasso_labels/ RoboTrader_template/backtest/TASSO_OVERVIEW.md
git diff --cached --name-only    # 🔴 posts28/ text28/ images28/ claims_batches/ *_quoted.csv 가 없어야 한다
git commit -m "docs(tasso): 기존 결론 영향 판정 + 수집범위표 갱신"
```

- [ ] **Step 5: 🔴 장 마감(15:30) 이후에 `main` 머지 (사장님 확인 후)**

```bash
cd D:/GIT/kis-trading-template
git log --oneline main..research/tasso-cat2829-harvest    # 실제 커밋 목록을 눈으로 확인
git merge --no-ff research/tasso-cat2829-harvest
```

⚠️ 에이전트의 "커밋됨" 보고를 믿지 말고 `git log main..branch` 로 직접 확인한다 (이 프로젝트의 전례).

---

## 완료 기준 (스펙 §10)

- [ ] V1 PASS — 목록 API 집합 ↔ 저장 파일 집합 차집합 0. `post_cnt_delta` 는 수치로 기록
- [ ] V2 PASS — 원장 distinct `log_no` == 수집 파일 수
- [ ] V3 결과가 수치로 기록됨 — 미등장 건수와 **각각의 설명**
- [ ] V4 누락률이 **분자/분모**로 기록됨
- [ ] `METHOD.md` 2판이 **[28]·[29] 한정 전수**임을 명시하고 [1]·[35] 169건 미수집을 함께 명시
- [ ] 영향 판정이 ①7차 FAIL 해석 ②2막 종결 사유 ③1판 서술 **각각에 명시 결론** (흔들지 않았다도 근거와 함께)
- [ ] `pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py` 48 passed
- [ ] 커밋에 원문 캐시(`posts28/`·`text28/`·`images28/`·`claims_batches/`·`*_quoted.csv`)가 **한 건도 없음**
