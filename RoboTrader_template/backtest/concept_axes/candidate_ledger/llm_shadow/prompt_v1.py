# ruff: noqa: E501  — 부록 펜스 본문은 한 줄도 바꾸지 않는다(긴 줄 그대로).
"""프롬프트 v1 — 부록 A 🔒 (펜스 안 본문이 해시 대상 · §5-7).

- `A1_SYSTEM`·`A2_USER`·`A3_SCHEMA_JSON`·`A5_RULE2_SEARCH`·`A6_SEARCH_ADD_JSON` = 부록 펜스 본문 «그대로»
  (끝 줄바꿈 제거 · 사전등록 md 에서 기계적으로 옮겼다). `verify_against_prereg()` 가 md 를 다시 읽어 대조하고,
  다르면 런너는 실행을 거부한다(§5-7).
- `PROMPT_SHA256` = sha256(UTF-8(A.1 + LF + A.2 + LF + A.3)) · 검색 팔 = sha256(A.1·A.2·A.3·A.5·A.6 을 LF 로 연결)(A.7).
- `argv_sha256` = sha256(UTF-8(NUL 로 연결한 argv[1:])) — exe 경로(기계마다 다름)는 빼고 `exe_sha256` 로 따로 고정한다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List

from . import settings as S

# ── 부록 A 펜스 본문 🔒 (수정 금지 · 바꾸면 새 가족) ─────────────────────────────────
A1_SYSTEM = '''너는 한국 상장주식의 «재료(촉매)»와 «위험»을 분류하는 분석가다. 다음 규칙을 반드시 지킨다.
1) 사용자가 준 입력만 근거로 판단한다. 입력은 기준일 D 와 그 이전 날짜의 자료뿐이다. D 이후의 사건·주가·뉴스를 알고 있더라도 절대 쓰지 않는다. 입력에 없는 사실을 지어내지 않는다.
2) 도구·검색·외부 자료를 쓰지 않는다.
3) 종목마다 따로 판단한다. 같은 요청의 다른 종목과 비교해서 점수를 매기지 않는다. 입력에 있는 모든 종목을 code 로 구분해 items 에 하나씩 담는다.
4) catalyst_tags 는 아래 사전의 값만 쓴다(여러 개 가능). 재료가 하나도 없으면 ["없음"] 하나만 쓴다. "없음"은 다른 값과 함께 쓰지 않는다.
5) risk_flags 는 아래 사전의 값만 쓴다(여러 개 가능). 위험이 없으면 빈 배열 [] 을 쓴다.
6) score 는 D 다음 거래일 시가에 사서 약 2주~2개월 보유한다고 할 때 입력의 재료·위험만 보고 매긴 매력도다. 0~10 정수. 5 = 재료도 위험도 없음(또는 서로 상쇄). 10 = 매우 강한 긍정 재료이고 위험 없음. 0 = 매우 강한 위험.
7) 가격·거래량·차트 모멘텀으로 점수를 매기지 않는다. 시가총액·수익률은 참고일 뿐이다.
8) rationale 은 한국어 200자 이내로, 판단 근거가 된 입력 항목(날짜와 제목)을 짚는다.
9) 출력은 주어진 JSON 스키마에 맞는 객체 하나뿐이다.
[catalyst_tags 사전 — 재료 유형 · 방향 무관]
유상증자: 유상증자 또는 유무상증자 결정 공시(제3자배정 포함 · 무상증자만인 공시와 발행가 확정·청약 결과 같은 후속 절차는 제외하고 기타로)
CB/BW/EB: 전환사채·신주인수권부사채·교환사채 발행 결정
자기주식취득: 자기주식 취득 결정 또는 취득 신탁계약 체결(처분·소각은 제외)
공급계약: 단일판매·공급계약 체결 공시(해지는 제외)
최대주주변경: 최대주주 변경 또는 그것을 수반하는 주식 양수도·경영권 계약
잠정실적: 영업(잠정)실적 공정공시 또는 매출액·손익구조 30%(대규모법인 15%) 이상 변동 공시
소송·횡령: 소송 등의 제기·신청 또는 횡령·배임 혐의 발생·사실 확인
실적개선: 공시·기사가 전하는 매출·이익 증가, 흑자 전환, 전망 상향
수주: 공급계약 공시 밖에서 기사로 확인되는 수주·납품·계약 소식
신사업: 신규 사업·제품·인허가·기술이전·인수합병 같은 사업 확장 소식
기타: 위에 없는 재료(정책 수혜·테마 편입·무상증자 등) — rationale 에 무엇인지 적는다
없음: 재료 없음(단독으로만)
[risk_flags 사전 — 하방 위험]
유상증자: 지분 희석을 부르는 유상증자 결정
CB/BW: 전환사채·신주인수권부사채·교환사채 발행, 전환가액 하향 조정, 대량 전환 청구
소송: 소송 제기, 횡령·배임, 경영권 분쟁
최대주주변경: 최대주주·경영권 변경, 담보 주식 반대매매 우려
감사의견: 감사의견 비적정(한정·부적정·의견거절), 감사보고서 제출 지연, 계속기업 불확실성
관리종목: 관리종목·투자주의환기종목 지정, 거래정지, 상장폐지 사유 발생, 불성실공시법인 지정
기타: 그 밖의 뚜렷한 하방 위험(대규모 손실·자본잠식 등) — rationale 에 적는다'''

A2_USER = '''기준일 D: {D} (D 다음 거래일 {T} 시가 진입을 가정한다 · D 이후 정보 사용 금지)
아래 {k}개 종목을 각각 따로 판단해 items 에 종목마다 하나씩 담아라.
=== {i}/{k} {name} ({code}) · {market} · 시가총액 {mcap_eok}억원 · 최근 20거래일 수익률 {r20}
재무 (결산월 {stac_yymm}): 매출액증가율 {sales_growth}% · 영업이익증가율 {oi_growth}% · 순이익증가율 {ni_growth}% · ROE {roe}% · 부채비율 {liab}% · 유보율 {reserve}% · EPS {eps}원
DART 공시 제목 (최근 10거래일 {d10}~{D} · 최신순 · 최대 12건 · 전체 {n_dart_all}건):
{dart_lines}
기사 제목 (최근 5거래일 {d5}~{D} · 최신순 · 최대 8건 · 전체 {n_press_all}건):
{press_lines}'''

A3_SCHEMA_JSON = '''{"type":"object","additionalProperties":false,"required":["items"],"properties":{"items":{"type":"array","minItems":1,"maxItems":20,"items":{"type":"object","additionalProperties":false,"required":["code","catalyst_tags","risk_flags","score","rationale"],"properties":{"code":{"type":"string","pattern":"^[0-9][0-9A-Z]{5}$"},"catalyst_tags":{"type":"array","minItems":1,"uniqueItems":true,"items":{"type":"string","enum":["유상증자","CB/BW/EB","자기주식취득","공급계약","최대주주변경","잠정실적","소송·횡령","실적개선","수주","신사업","기타","없음"]}},"risk_flags":{"type":"array","uniqueItems":true,"items":{"type":"string","enum":["유상증자","CB/BW","소송","최대주주변경","감사의견","관리종목","기타"]}},"score":{"type":"integer","minimum":0,"maximum":10},"rationale":{"type":"string","maxLength":200}}}}}}'''

A5_RULE2_SEARCH = '''2) 웹 검색·웹 페이지 도구를 써도 된다. 검색으로 찾아 본 기사·공시는 제목·출처·날짜(YYYY-MM-DD)를 sources 에 전부 적는다. 날짜가 기준일 D 보다 늦은 자료는 판단에 쓰지 말고 excluded_after_D 에 적는다. 날짜를 알 수 없는 자료는 판단에 쓰지 않는다.'''

A6_SEARCH_ADD_JSON = '''{"sources":{"type":"array","maxItems":30,"items":{"type":"object","additionalProperties":false,"required":["title","source","date"],"properties":{"title":{"type":"string"},"source":{"type":"string"},"date":{"type":"string","pattern":"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},"url":{"type":"string"}}}},"excluded_after_D":{"type":"array","maxItems":30,"items":{"type":"object","additionalProperties":false,"required":["title","date"],"properties":{"title":{"type":"string"},"date":{"type":"string","pattern":"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}}}}}'''


A1_RULE2_MAIN = "2) 도구·검색·외부 자료를 쓰지 않는다."
_FENCES = {"A.1": "A1_SYSTEM", "A.2": "A2_USER", "A.3": "A3_SCHEMA_JSON",
           "A.5": "A5_RULE2_SEARCH", "A.6": "A6_SEARCH_ADD_JSON"}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compact(obj) -> str:
    """스키마 JSON 직렬화 규약 = 공백 없는 구분자 · 한글 그대로(A.3 펜스와 같은 모양)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ── A.3 · A.5 · A.6 파생 ─────────────────────────────────────────────────────────
A3_SCHEMA: Dict = json.loads(A3_SCHEMA_JSON)
_ITEM_PROPS = A3_SCHEMA["properties"]["items"]["items"]["properties"]
CATALYST_ENUM: List[str] = list(_ITEM_PROPS["catalyst_tags"]["items"]["enum"])
RISK_ENUM: List[str] = list(_ITEM_PROPS["risk_flags"]["items"]["enum"])
NONE_TAG = "없음"


def search_system_prompt() -> str:
    """A.7 시스템 = A.1 의 규칙 2) 한 줄을 A.5 로 바꾼 것."""
    assert A1_SYSTEM.count(A1_RULE2_MAIN) == 1
    return A1_SYSTEM.replace(A1_RULE2_MAIN, A5_RULE2_SEARCH)


def search_schema() -> Dict:
    """A.6 적용 = A.3 의 `items.items` 객체를 최상위로 · properties 에 sources·excluded_after_D 추가
    · required 에 둘 추가."""
    item = json.loads(compact(A3_SCHEMA["properties"]["items"]["items"]))
    add = json.loads(A6_SEARCH_ADD_JSON)
    item["properties"].update(add)
    item["required"] = list(item["required"]) + list(add.keys())
    return item


A1_SYSTEM_SEARCH = search_system_prompt()
SEARCH_SCHEMA_JSON = compact(search_schema())

PROMPT_SHA256 = _sha(A1_SYSTEM + "\n" + A2_USER + "\n" + A3_SCHEMA_JSON)
PROMPT_SHA256_SEARCH = _sha("\n".join([A1_SYSTEM, A2_USER, A3_SCHEMA_JSON, A5_RULE2_SEARCH, A6_SEARCH_ADD_JSON]))


# ── A.2 렌더 틀 ──────────────────────────────────────────────────────────────────
A2_LINES = A2_USER.split("\n")
A2_HEAD1, A2_HEAD2 = A2_LINES[0], A2_LINES[1]
A2_BLOCK = "\n".join(A2_LINES[2:])          # `=== {i}/{k} …` 부터 {press_lines} 까지(6줄)
BLOCK_PREFIX = "=== {i}/{k} "                # 짝 해시(§5-9)에서 빼는 머리 조각


def render_header(D: str, T: str, k: int, search: bool = False) -> str:
    """머리 1회. 검색 팔(A.7)은 둘째 줄 생략."""
    first = A2_HEAD1.format(D=D, T=T)
    return first if search else first + "\n" + A2_HEAD2.format(k=k)


def render_block(i: int, k: int, fields: Dict[str, object]) -> str:
    """종목 블록 1개(A.2 3~8줄). fields = 틀의 이름 전부(값 없으면 '-' · 목록 없으면 '(없음)' 은 inputs 몫)."""
    return A2_BLOCK.format(i=i, k=k, **fields)


def block_body(block_text: str) -> str:
    """`=== {i}/{k} ` 머리 조각만 뗀 본문 — 본체↔검색 팔 짝 판정 해시 대상(§5-9 · 종목명·시총·r20 은 남긴다)."""
    if not block_text.startswith("=== "):
        raise ValueError("종목 블록이 '=== ' 로 시작하지 않는다")
    return block_text[4:].split(" ", 1)[1]


def renumber(block_text: str, i: int, k: int) -> str:
    return BLOCK_PREFIX.format(i=i, k=k) + block_body(block_text)


def render_user(D: str, T: str, blocks: List[str], search: bool = False) -> str:
    return render_header(D, T, len(blocks), search) + "\n" + "\n".join(blocks)


# ── A.4 · A.7 명령 ───────────────────────────────────────────────────────────────
def argv_main(exe: str, model: str) -> List[str]:
    return [exe, "-p", "--model", model, "--effort", "medium", "--safe-mode", "--tools", "",
            "--no-session-persistence", "--output-format", "json", "--json-schema", A3_SCHEMA_JSON,
            "--system-prompt", A1_SYSTEM]


def argv_search(exe: str, model: str) -> List[str]:
    # 개정 1(2026-09-26 amendment) — dry-run 실측 = `--tools` 허용만으론 WebFetch 가 permission_denials 로 막힌다
    # (web_search_requests 0) ⇒ `--allowedTools` 를 나란히 준다.
    return [exe, "-p", "--model", model, "--effort", "medium", "--safe-mode", "--tools", "WebSearch,WebFetch",
            "--allowedTools", "WebSearch,WebFetch",
            "--no-session-persistence", "--output-format", "json", "--json-schema", SEARCH_SCHEMA_JSON,
            "--system-prompt", A1_SYSTEM_SEARCH]


def argv_sha256(argv: List[str]) -> str:
    return _sha("\x00".join(argv[1:]))


def sha256_text(text: str) -> str:
    return _sha(text)


# ── §5-7 부록 대조 ───────────────────────────────────────────────────────────────
def parse_prereg_fences(md_path: Path = S.PREREG_MD) -> Dict[str, str]:
    """사전등록 md 의 부록 A 펜스 본문(끝 줄바꿈 제거)을 다시 읽는다."""
    md = Path(md_path).read_text(encoding="utf-8").replace("\r\n", "\n")
    out: Dict[str, str] = {}
    for lab in _FENCES:
        i = md.index("**" + lab + " ")
        a = md.index("```\n", i) + 4
        b = md.index("\n```", a)
        out[lab] = md[a:b]
    return out


class AppendixMismatch(RuntimeError):
    """런너 상수 ≠ 부록 — 실행 거부(§5-7)."""


def verify_against_prereg(md_path: Path = S.PREREG_MD) -> Dict[str, str]:
    fences = parse_prereg_fences(md_path)
    bad = [lab for lab, name in _FENCES.items() if fences[lab] != globals()[name]]
    if bad:
        raise AppendixMismatch(f"프롬프트 상수 ≠ 부록 {bad} — 실행 거부(§5-7)")
    if compact(A3_SCHEMA) != A3_SCHEMA_JSON:
        raise AppendixMismatch("A.3 재직렬화 ≠ 펜스 — 실행 거부")
    if len(CATALYST_ENUM) != 12:
        raise AppendixMismatch("catalyst enum 개수 ≠ 12")
    h = _sha(fences["A.1"] + "\n" + fences["A.2"] + "\n" + fences["A.3"])
    hs = _sha("\n".join(fences[k] for k in ("A.1", "A.2", "A.3", "A.5", "A.6")))
    if h != PROMPT_SHA256 or hs != PROMPT_SHA256_SEARCH:
        raise AppendixMismatch("prompt_sha256 ≠ 부록 재계산 — 실행 거부")
    return {"prompt_sha256": PROMPT_SHA256, "prompt_sha256_search": PROMPT_SHA256_SEARCH}
