"""§5-2 CLI 고정 호출 · §5-5 한도 오류 · §4 사후 검사.

- 호출 = 고정 exe 를 `subprocess.run([exe, …], shell=False)` 리스트 인자로 직접 · stdin = A.2 렌더(UTF-8).
- env: `ANTHROPIC_API_KEY`·`ANTHROPIC_AUTH_TOKEN` 있으면 즉시 중단(API 과금 경로) · `CLAUDECODE`·`CLAUDE_CODE_*` 제거
  (예외 `CLAUDE_CODE_OAUTH_TOKEN` = 구독 인증일 수 있어 유지) · `DISABLE_AUTOUPDATER=1`.
- 🔒 봉인: 이 모듈은 모델 출력을 «로그하지 않는다». `raw_result`(stdout)·`structured_output` 은 호출자가 봉인 열에만 쓴다.
  `error_text` 는 CLI·검증기 메시지 ≤ 300자(모델 출력 인용 금지).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import prompt_v1 as P
from . import settings as S

LIMIT_RE = re.compile(r"(?i)\b(usage limit|limit reached|rate limit(ed)?|quota( exceeded)?|too many requests)\b")
ERR_MAX = 300
ST_CLI_ERR = S.ST_CLI
ST_OVERLOAD = "overload"          # 429·529 — 180초 뒤 1회 재시도(따로 집계 · 사다리 판정 제외)
_CODE_RE = re.compile(r"^[0-9][0-9A-Z]{5}$")


class ApiKeyPresent(RuntimeError):
    """API 키 env 발견 — 즉시 중단(§5-2 가드)."""


def build_env(base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    src = dict(os.environ if base is None else base)
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        if src.get(k):
            raise ApiKeyPresent(f"{k} 가 설정돼 있다 — API 과금 경로 · 즉시 중단")
    env = {}
    for k, v in src.items():
        ku = k.upper()
        if ku == "CLAUDECODE":
            continue
        if ku.startswith("CLAUDE_CODE_") and ku != "CLAUDE_CODE_OAUTH_TOKEN":
            continue
        env[k] = v
    env["DISABLE_AUTOUPDATER"] = "1"
    return env


@dataclass
class CallResult:
    status: str                       # ok | timeout | cli_error | limit_error | overload | model_mismatch
    is_error: bool = False
    api_error_status: Optional[int] = None
    error_text: Optional[str] = None
    raw_result: Optional[str] = None  # 🔒 봉인(stdout 전체)
    structured: Any = None            # 🔒 봉인
    model: Optional[str] = None
    model_keys: List[str] = field(default_factory=list)
    cost_usd: Optional[float] = None
    latency_ms: Optional[int] = None
    web_search_requests: Optional[int] = None
    web_fetch_requests: Optional[int] = None
    permission_denials: Optional[int] = None
    helper_models: Optional[str] = None       # modelUsage 중 가족 모델이 아닌 키(콤마 조인 · 검색 도구 보조 모델)


def _clip(s: Any) -> Optional[str]:
    if s is None:
        return None
    s = str(s).strip()
    return s[:ERR_MAX] if s else None


def pick_model(model_usage: Dict[str, Any], most_output: bool, expect_model: Optional[str] = None
              ) -> Tuple[Optional[str], List[str]]:
    """본체 = 유일 키. 검색 팔(개정 2 · 2026-09-26 amendment) = 가족 모델 키가 modelUsage 에 있고,
    그 밖의 키(검색 도구 보조 모델)는 전부 webSearchRequests ≥ 1 이어야 한다 — 아니면 model_mismatch.
    (구 규칙 "출력 토큰 최다 키"는 폐기 — 보조 모델이 가족 모델보다 출력 토큰이 더 많을 수 있었다.)"""
    keys = sorted((model_usage or {}).keys())
    if not keys:
        return None, keys
    if not most_output:
        return (keys[0] if len(keys) == 1 else None), keys

    def ws_req(k: str) -> float:
        v = model_usage.get(k) or {}
        return float(v.get("webSearchRequests") or v.get("web_search_requests") or 0)
    if expect_model not in keys:
        return None, keys
    if any(ws_req(k) < 1 for k in keys if k != expect_model):
        return None, keys
    return expect_model, keys


def interpret(stdout: str, stderr: str, expect_model: str, most_output: bool, wall_ms: int) -> CallResult:
    """CLI `--output-format json` 결과 해석(부록 B 키)."""
    try:
        d = json.loads(stdout)
        if not isinstance(d, dict):
            raise ValueError("not an object")
    except Exception:
        return CallResult(ST_CLI_ERR, is_error=True, error_text=_clip(stderr) or "CLI 출력이 JSON 이 아니다",
                          raw_result=stdout or None, latency_ms=wall_ms)
    usage = d.get("usage") or {}
    stu = usage.get("server_tool_use") or {}
    model_usage = d.get("modelUsage") or {}
    model, keys = pick_model(model_usage, most_output, expect_model)
    # 개정 3(2026-09-26 amendment) — 검색 증거는 modelUsage[*].webSearchRequests 합(도구가 검색을 보조 모델에
    # 위임해 top-level usage.server_tool_use.web_search_requests 는 0으로 남을 수 있다) · modelUsage 없으면 top-level 폴백.
    if model_usage:
        web_search_requests = sum(int((v or {}).get("webSearchRequests") or (v or {}).get("web_search_requests") or 0)
                                  for v in model_usage.values())
    else:
        web_search_requests = stu.get("web_search_requests")
    helper_models = ",".join(k for k in keys if k != expect_model) or None
    r = CallResult(status=S.ST_OK, is_error=bool(d.get("is_error")), api_error_status=d.get("api_error_status"),
                   raw_result=stdout, structured=d.get("structured_output"), model=model, model_keys=keys,
                   cost_usd=d.get("total_cost_usd"), latency_ms=int(d.get("duration_ms") or wall_ms),
                   web_search_requests=web_search_requests, web_fetch_requests=stu.get("web_fetch_requests"),
                   permission_denials=len(d.get("permission_denials") or []), helper_models=helper_models)
    try:
        r.api_error_status = int(r.api_error_status) if r.api_error_status is not None else None
    except (TypeError, ValueError):
        r.api_error_status = None
    if r.is_error:
        msg = d.get("result") if isinstance(d.get("result"), str) else None
        r.error_text = _clip(msg) or _clip(stderr) or _clip(d.get("subtype"))
        r.structured = None
        if r.api_error_status in S.OVERLOAD_STATUSES:
            r.status = ST_OVERLOAD
        elif LIMIT_RE.search(" ".join(x for x in (msg or "", stderr or "") if x)):
            r.status = S.ST_LIMIT
        else:
            r.status = ST_CLI_ERR
        return r
    if model != expect_model:
        r.status = S.ST_MODEL
        r.error_text = _clip(f"modelUsage 키 {keys} ≠ 가족 모델 {expect_model}")
    return r



def run_cli(argv: List[str], stdin_text: str, timeout_s: float, env: Dict[str, str], expect_model: str,
            most_output: bool = False, runner: Callable[..., Any] = subprocess.run) -> CallResult:
    t0 = time.monotonic()
    try:
        cp = runner(argv, input=stdin_text.encode("utf-8"), capture_output=True, timeout=timeout_s,
                    shell=False, env=env)
    except subprocess.TimeoutExpired:
        return CallResult(S.ST_TIMEOUT, is_error=True, error_text=f"timeout {int(timeout_s)}s",
                          latency_ms=int((time.monotonic() - t0) * 1000))
    except OSError as e:
        return CallResult(ST_CLI_ERR, is_error=True, error_text=_clip(f"실행 실패 {type(e).__name__}"),
                          latency_ms=int((time.monotonic() - t0) * 1000))
    wall = int((time.monotonic() - t0) * 1000)
    out = cp.stdout.decode("utf-8", "replace") if isinstance(cp.stdout, bytes) else (cp.stdout or "")
    err = cp.stderr.decode("utf-8", "replace") if isinstance(cp.stderr, bytes) else (cp.stderr or "")
    return interpret(out, err, expect_model, most_output, wall)


def call_with_overload_retry(call: Callable[[], CallResult], sleep: Callable[[float], None] = time.sleep
                             ) -> Tuple[CallResult, Optional[CallResult]]:
    """§5-5 — 429·529 면 180초 뒤 1회 재시도. 반환 (첫 결과, 재시도 결과 또는 None)."""
    first = call()
    if first.status != ST_OVERLOAD:
        return first, None
    sleep(S.OVERLOAD_SLEEP_S)
    return first, call()


# ── §4 사후 검사 ─────────────────────────────────────────────────────────────────
def check_item(it: Any, search: bool = False) -> Optional[str]:
    """항목 1개 스키마 + `없음` 단독 규칙. 문제 없으면 None, 있으면 검증기 메시지(모델 출력 인용 없음)."""
    if not isinstance(it, dict):
        return "항목이 객체가 아니다"
    need = {"code", "catalyst_tags", "risk_flags", "score", "rationale"}
    if search:
        need |= {"sources", "excluded_after_D"}
    if set(it.keys()) != need:
        return "항목 키 집합 불일치"
    if not isinstance(it["code"], str) or not _CODE_RE.match(it["code"]):
        return "code 형식 불일치"
    ct, rf = it["catalyst_tags"], it["risk_flags"]
    if not isinstance(ct, list) or not ct or len(set(map(str, ct))) != len(ct) \
            or any(t not in P.CATALYST_ENUM for t in ct):
        return "catalyst_tags 사전·중복 위반"
    if P.NONE_TAG in ct and len(ct) != 1:
        return "'없음' 이 다른 태그와 함께 쓰였다"
    if not isinstance(rf, list) or len(set(map(str, rf))) != len(rf) or any(t not in P.RISK_ENUM for t in rf):
        return "risk_flags 사전·중복 위반"
    sc = it["score"]
    if isinstance(sc, bool) or not isinstance(sc, int) or not 0 <= sc <= 10:
        return "score 0~10 정수 위반"
    if not isinstance(it["rationale"], str) or len(it["rationale"]) > 200:
        return "rationale 형식·길이 위반"
    if search:
        for key, req in (("sources", {"title", "source", "date"}), ("excluded_after_D", {"title", "date"})):
            arr = it[key]
            if not isinstance(arr, list) or len(arr) > 30:
                return f"{key} 형식 위반"
            for s in arr:
                if not isinstance(s, dict) or not req <= set(s.keys()) \
                        or not re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", str(s.get("date", ""))):
                    return f"{key} 항목 형식 위반"
    return None


def validate_batch(structured: Any, codes: List[str]) -> Tuple[Dict[str, Tuple[str, Optional[dict], Optional[str]]],
                                                                 Optional[str]]:
    """본체 묶음 결과 → {code: (status, item, err)}, 묶음 단위 오류.

    묶음 단위(전 종목 parse_error): 객체/items 아님 · 항목 수 범위 밖 · code 중복 · code 집합 불일치.
    항목 단위: 스키마·`없음` 단독 위반 → 그 종목만 parse_error.
    """
    bad = None
    items = structured.get("items") if isinstance(structured, dict) else None
    if not isinstance(structured, dict) or set(structured.keys()) != {"items"} or not isinstance(items, list):
        bad = "structured_output 이 {items:[…]} 가 아니다"
    elif not 1 <= len(items) <= 20:
        bad = "items 개수 범위 밖"
    else:
        got = [it.get("code") if isinstance(it, dict) else None for it in items]
        if len(set(got)) != len(got):
            bad = "code 중복"
        elif set(got) != set(codes):
            bad = "code 집합 불일치"
    if bad:
        return {c: (S.ST_PARSE, None, bad) for c in codes}, bad
    out = {}
    for it in items:
        err = check_item(it)
        out[it["code"]] = (S.ST_PARSE, None, err) if err else (S.ST_OK, it, None)
    return out, None


def validate_search(structured: Any, code: str) -> Tuple[str, Optional[dict], Optional[str]]:
    err = check_item(structured, search=True)
    if err is None and structured["code"] != code:
        err = "code 불일치"
    return (S.ST_PARSE, None, err) if err else (S.ST_OK, structured, None)
