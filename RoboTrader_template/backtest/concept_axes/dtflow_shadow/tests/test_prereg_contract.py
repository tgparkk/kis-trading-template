"""PREREG ↔ 코드 기계 대조(critic I10 · C3) — 부록 A 의 sql 블록 = ddl.sql 바이트 · pins 블록(상수 = 값) = settings.py·러너 값.
문서가 코드와 한 곳이라도 어긋나면 실패한다(동결 문서 머리말 «코드와 다르면 동결하지 않는다» 의 기계판)."""
import ast
import hashlib
import importlib.util
import re
import sys
from datetime import time
from pathlib import Path

from backtest.concept_axes.dtflow_shadow import settings as S

PREREG = S.PKG / "PREREG.md"
DDL = S.PKG / "ddl.sql"
RUNNER = S.RT_ROOT / "scripts" / "dtflow_shadow_recorder.py"
DERIVED = {"PKG", "RT_ROOT", "REPO_ROOT", "PREREG"}      # 파일 위치에서 계산되는 경로 — 동결 «값» 이 아님
RUNNER_PINNED = ("CAL_DAYS", "EXIT2")                     # 러너 쪽 상수(PREREG 가 인용)
_NAME = re.compile(r"(runner\.)?[A-Z][A-Z0-9_]*")
_TIME = re.compile(r"time\((\d{1,2}),\s*(\d{1,2})\)")


def _text() -> str:
    return PREREG.read_bytes().decode("utf-8")


def _fenced(text: str, info: str):
    """```<info> … ``` 블록 본문들(본문 끝 줄바꿈 포함) — 줄 전체가 정확히 펜스여야 한다."""
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        if lines[i] == "```" + info:
            j = lines.index("```", i + 1)
            out.append("\n".join(lines[i + 1:j]) + "\n")
            i = j + 1
        else:
            i += 1
    return out


def _value(src: str):
    m = _TIME.fullmatch(src)
    if m:
        return time(int(m.group(1)), int(m.group(2)))
    return ast.literal_eval(src)


def parse_pins(text: str) -> dict:
    blocks = _fenced(text, "pins")
    assert len(blocks) == 1, f"pins 블록은 정확히 1개여야 한다(지금 {len(blocks)})"
    pins = {}
    for ln in blocks[0].splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        name, sep, val = s.partition(" = ")
        assert sep and _NAME.fullmatch(name), f"pins 줄 형식 «{s}» — `NAME = 파이썬 값`"
        assert name not in pins, f"pins 이름 중복 «{name}»"
        pins[name] = _value(val)
    assert pins, "pins 블록이 비어 있다"
    return pins


def _runner():
    spec = importlib.util.spec_from_file_location("dtflow_runner_contract", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _settings_constants() -> dict:
    return {k: v for k, v in vars(S).items()
            if _NAME.fullmatch(k) and not k.startswith("runner.") and k not in DERIVED}


def test_prereg_is_lf_utf8():
    raw = PREREG.read_bytes()
    assert b"\r" not in raw
    raw.decode("utf-8")


def test_appendix_sql_block_equals_ddl_bytes():
    blocks = _fenced(_text(), "sql")
    assert len(blocks) == 1, "PREREG 의 ```sql 블록은 부록 A 하나뿐이어야 한다"
    assert blocks[0].encode("utf-8") == DDL.read_bytes()


def test_appendix_cites_current_ddl_sha256():
    text = _text()
    appendix = text[text.index("## 부록 A"):]
    head = appendix[:appendix.index("```sql")]
    assert hashlib.sha256(DDL.read_bytes()).hexdigest() in head


def test_pins_equal_settings_and_runner_values():
    pins = parse_pins(_text())
    R = _runner()
    bad = []
    for name, want in pins.items():
        got = getattr(R, name[len("runner."):]) if name.startswith("runner.") else getattr(S, name)
        if got != want or type(got) is not type(want):
            bad.append((name, want, got))
    assert not bad, bad


def test_pins_cover_every_settings_constant_and_runner_pins():
    pins = parse_pins(_text())
    missing = sorted(set(_settings_constants()) - set(pins))
    assert not missing, f"settings.py 상수가 PREREG pins 에 없다: {missing}"
    assert all(f"runner.{n}" in pins for n in RUNNER_PINNED)


def test_every_settings_tag_in_prereg_names_a_pin_or_path_function():
    """본문 꼬리표 `(settings.py: A, B)` 의 이름은 pins 의 상수이거나 settings 의 경로 함수여야 한다(`…` = 규약 설명용 자리표시)."""
    text = _text()
    pins = parse_pins(text)
    names = set()
    for m in re.finditer(r"\(settings\.py: ([^)]*)\)", text):
        names |= {n.strip() for n in m.group(1).split(",")} - {"…"}
    assert len(names) >= 20
    bad = sorted(n for n in names if n not in pins and not callable(getattr(S, n, None)))
    assert not bad, bad


def test_credit_switches_consistent():
    """B-3: 신용 ④ 를 뺐으면 k 는 없어야 한다(둘 다 켜진 상태 금지)."""
    assert not (S.CREDIT_DROPPED and S.CREDIT_LAG_K is not None)
