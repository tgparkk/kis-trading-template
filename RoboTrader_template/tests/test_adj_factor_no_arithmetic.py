"""★ adj_factor 산술 금지 규약 — 트리 전역 소스 레벨 가드 (2026-08-03).

================================================================================
규약 (SSOT — 이 파일이 규약의 기계검사 지점이다)
================================================================================

**daily_prices 의 open/high/low/close 에 adj_factor 를 곱하지도 나누지도 말 것.**

이유. `collectors/adj_factors.py` 의 규약은

    adj_close(T) = raw_close(T) / adj_factor(T)

인데, 이 식의 입력은 **raw_close** 다. 그리고 `daily_prices` 는 raw 를 저장하지
않는다 — `close` 는 KIS `adj_prc="0"` 이 준 **이미 조정된 연속 시세**다. 따라서
어느 방향이든 틀린다. 실측(kis_template, 035720 카카오 5:1 분할 2021-04-15 일간수익률):

    정상(그대로)  +7.6%      <- 이것이 실제 시세
    × adj_factor  -78.5%     <- raw 로 되돌아가 분할일 가짜 절벽 (거짓 MaxDD)
    ÷ adj_factor +437.9%     <- 이중조정되어 분할일 가짜 급등

전 감사 대상 5종목의 전환 경계 실측 (2021-01-01~2026-05-29 top-50 유니버스):

    001440  2023-05-16   raw  +6.3%   ×  -89.4%   ÷  +963.0%
    010140  2021-08-10   raw  +2.0%   ×  -79.6%   ÷  +409.9%
    035720  2021-04-15   raw  +7.6%   ×  -78.5%   ÷  +437.9%
    042700  2022-04-06   raw  -3.7%   ×  -51.9%   ÷   +92.6%
    086520  2024-04-25   raw  +4.5%   ×  -79.1%   ÷  +422.7%

전부 KRX 가격제한폭(±30%)을 넘는다 = 물리적으로 불가능 = 판별 가능한 지문.

================================================================================
왜 "적용 함수"(lib/adj_close(df) 등)를 만들지 않았나
================================================================================

1. **올바른 호출처가 0개다.** 전수 감사 결과 정상 소비자는 전부 "그냥 안 쓴다"
   이고, 적용이 필요한 자리는 하나도 없었다. 호출처가 없는 함수는 순수한 사고 표면.
2. **올바른 기본값을 가질 수 없다.** 위 실측대로 × 도 ÷ 도 틀리다. 옳은 변환은
   raw_close 를 입력으로 받아야 하는데 `daily_prices` 에 raw 컬럼이 없다.
   즉 시그니처를 정직하게 쓰면 인자를 채울 방법이 없는 함수가 된다.
3. **잔여 문제는 소비자가 아니라 데이터에 있다.** 「마지막 대량 재적재 이후 기업행위가
   난 종목」(실측 101건/100종목/95,569행)은 close 가 미조정으로 남은 것이라
   **데이터 복구 트랙**에서 푼다. 소비자 측 헬퍼로 덮으면 복구 진척을 관측할 수 없게 된다.
4. 관리자 제약 —「무심코 부르면 이중조정되는 API 는 만들지 말 것」— 을 만족시키는
   유일한 해는 **함수를 두지 않는 것**이다. 안전한 기본 동작이 "호출하지 않기"이므로.

⇒ 규약을 "한 곳에 못 박는" 올바른 형태는 재사용 함수가 아니라 **기계검사(이 파일)** 다.
   docstring 규약은 이미 3번 새어나갔다(data_loader / regime_split ×2).

================================================================================
이 가드가 기존 가드와 다른 점
================================================================================

기존 3개는 전부 **대상이 열거식**이라 새 파일을 못 잡는다. 실제로 셋 다
`scripts/exit_multiverse/data_loader.py` 를 놓쳤다:

  - tests/test_adj_factor_no_split_cliff.py      -> run_minervini_vcp / run_daytrading_3methods 2개만
  - tests/test_research_data_source.py:274       -> multiverse/data/pit_reader.py 1개만
  - backtest/tasso_entry_timing/tests/test_data.py -> DAILY_SQL 상수 1개만

이 가드는 **트리 전역 스캔 + 허용목록**이라 새로 생기는 파일이 기본적으로 검사 대상이다.
DB 접속이 필요 없어 CI 어디서나 돈다.
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# 스캔 제외 디렉토리 (소스가 아니거나 서드파티)
_SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "env", "node_modules",
    "build", "dist", ".pytest_cache", ".mypy_cache", "site-packages",
}

# 이 가드 파일 자신 — 위 실측표와 정규식 리터럴이 스스로에 걸린다. 자기 제외.
_SELF = Path(__file__).resolve()

# ---------------------------------------------------------------------------
# 허용목록: archive/ 의 폐기된 계산 8건.
#
# archive/ 는 「무참조 확정분 보관소」이고, 이 코드가 `reports/` 의 확정 산출물을
# 만든 장본인이다. 고치면 그 리포트를 재현할 수 없게 되므로 **코드는 보존**하고
# 각 지점에 경고 주석만 달았다(2026-08-03).
#
# 🔑 이 목록은 동시에 **양성 대조군**이다 — 아래 test_detector_finds_known_offenders
#    가 탐지기가 이들을 실제로 잡는지 확인한다. 탐지기가 고장나면 (전역 스캔이
#    조용히 0건이 되면) 주 단언이 vacuous 해지는데, 그 사고를 이 대조가 막는다.
# ---------------------------------------------------------------------------
ALLOWLIST: dict[str, str] = {
    "archive/scripts/canslim_backtest.py": "폐기 — close×adj_factor. 확정 리포트 재현용 보존",
    "archive/scripts/canslim_pattern_backtest.py": "폐기 — OHLC×adj_factor. 확정 리포트 재현용 보존",
    "archive/scripts/10pct_strategy/p5_nhb_optimization.py": "폐기 — close×adj_factor. 확정 리포트 재현용 보존",
    "archive/scripts/10pct_strategy/p1_forward_return_matrix.py": "폐기 — close÷adj_factor(이중조정). 보존",
    "archive/scripts/10pct_strategy/p5_ma_align_walkforward.py": "폐기 — close÷adj_factor(이중조정). 보존",
    "archive/scripts/phase1_forward_return_baseline.py": "폐기 — SQL close/adj_factor(이중조정). 보존",
    "archive/scripts/debug_has_adj.py": "폐기 — SQL open*COALESCE(adj_factor). 산출물이 소요시간이라 결론 무영향",
    "archive/scripts/debug_has_adj2.py": "폐기 — SQL open*COALESCE(adj_factor). 산출물이 소요시간이라 결론 무영향",
}

# SQL 문자열 안의 곱셈/나눗셈. 같은 줄에서만 인접을 본다(개행을 건너뛰면
# "SELECT ... adj_factor\n FROM t WHERE a/b" 같은 무관한 조합이 걸린다).
_H = r"[^\S\n]*"  # 수평 공백만
_SQL_BEFORE = re.compile(rf"[*/]{_H}(?:COALESCE{_H}\({_H})?{_H}[\"']?adj_factor")
_SQL_AFTER = re.compile(rf"adj_factor[\"']?{_H}(?:::[a-zA-Z]+)?{_H}\)?{_H}[*/]")

# 인라인 opt-out. 규약을 **검사하는** 코드는 규약 위반 문자열을 리터럴로 가질 수밖에
# 없다(예: test_research_data_source.py 의 `assert "* COALESCE(adj_factor" not in text`).
# 그런 줄에만 붙인다 — 실제 가격 산술을 여기로 숨기지 말 것.
_IGNORE_PRAGMA = "adj-factor-lint: ignore"

# 연산자(`*` `/`)를 쓰지 않는 곱셈/나눗셈 형태. 🔑 변이 주입에서 BinOp 전용
# 탐지기가 `.mul()`/`.div()`/`np.multiply` 를 통째로 놓치는 것을 실측하고 추가했다.
_ARITH_METHODS = {
    "mul", "div", "rmul", "rdiv", "multiply", "divide", "true_divide",
    "truediv", "rtruediv", "divide_", "__mul__", "__truediv__", "__div__",
}


def _iter_py_files():
    for p in REPO.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.resolve() == _SELF:
            continue
        yield p


def _docstring_lines(tree: ast.AST) -> set[int]:
    """독스트링이 차지하는 줄 번호. 규약을 '설명'하는 산문은 위반이 아니다."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def _strip_sql_comments(s: str) -> str:
    """SQL 문자열 안의 `--` 주석 제거 — 규약을 설명하는 주석이 스스로 걸리지 않게."""
    return "\n".join(re.sub(r"--.*$", "", line) for line in s.split("\n"))


def _refs_adj_factor_value(node: ast.AST) -> bool:
    """이 식이 adj_factor **값**을 참조하는가.

    🔑 단순 문자열 포함("adj_factor" in 소스)으로 판정하면 안 된다. 실측 오탐:
       `df = pd.DataFrame(rows, columns=[..., "adj_factor"])` 의 컬럼 이름 목록이
       걸려 `df` 전체가 오염으로 표시되고, 그 뒤의 무관한 `df["open"] * (1-슬리피지)`
       까지 위반으로 잡혔다(portfolio_sim_elder 3건·run_dino_surge 1건).
       → 값 접근(Subscript["adj_factor"] / .adj_factor / 이름 adj_factor)만 인정한다.
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Subscript):
            sl = sub.slice
            if isinstance(sl, ast.Constant) and sl.value == "adj_factor":
                return True
        elif isinstance(sub, ast.Attribute) and sub.attr == "adj_factor":
            return True
        elif isinstance(sub, ast.Name) and sub.id == "adj_factor":
            return True
    return False


def _tainted_names(tree: ast.AST) -> set[str]:
    """adj_factor 값을 담은 변수명. 「변수에 담아서 쓰는 경우」를 잡기 위함.

    실례: p2c_exit_grid 의 `af = grp["adj_factor"].replace(0, np.nan).fillna(1.0)`
    뒤에 오는 `grp["open"] / af` 는 순진한 정규식으로는 안 잡힌다.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if value is None or not _refs_adj_factor_value(value):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for sub in ast.walk(t):
                    if isinstance(sub, ast.Name):
                        names.add(sub.id)
    return names


def find_offenses(path: Path) -> list[tuple[int, str]]:
    """(줄번호, 코드조각) 목록. 비면 규약 준수."""
    # utf-8-sig: BOM 있는 파일(실측 p5_nhb_optimization.py)을 utf-8 로 읽으면
    # 선두 ﻿ 때문에 ast.parse 가 SyntaxError → 조용히 0건이 된다.
    try:
        src = path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError):
        return []
    if "adj_factor" not in src:
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []

    # 인라인 opt-out: 규약을 검사·설명하는 코드(다른 가드의 단언 리터럴 등)를 위한 탈출구.
    ignored = {
        i + 1 for i, line in enumerate(src.split("\n")) if _IGNORE_PRAGMA in line
    }

    out: list[tuple[int, str]] = []
    tainted = _tainted_names(tree)

    # (1) 파이썬 산술 — BinOp(*, /) 의 피연산자가 adj_factor 값 또는 오염 변수
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div))):
            continue
        for operand in (node.left, node.right):
            seg = ast.get_source_segment(src, operand) or ""
            hit = _refs_adj_factor_value(operand) or any(
                re.search(rf"\b{re.escape(n)}\b", seg) for n in tainted
            )
            if hit:
                whole = ast.get_source_segment(src, node) or seg
                out.append((node.lineno, " ".join(whole.split())[:120]))
                break

    # (2) 메서드/함수 형태의 산술 — df.close.mul(df.adj_factor), np.multiply(a, af) 등
    def _hit(n: ast.AST) -> bool:
        seg = ast.get_source_segment(src, n) or ""
        return _refs_adj_factor_value(n) or any(
            re.search(rf"\b{re.escape(t)}\b", seg) for t in tainted
        )

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in _ARITH_METHODS:
            continue
        operands = [node.func.value] + list(node.args)
        if any(_hit(o) for o in operands):
            whole = ast.get_source_segment(src, node) or ""
            out.append((node.lineno, " ".join(whole.split())[:120]))

    # (3) SQL 문자열 안의 산술 — 독스트링·SQL주석·해시주석은 제외
    doc_lines = _docstring_lines(tree)
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        toks = []
    for tok in toks:
        if tok.type != tokenize.STRING:
            continue
        if tok.start[0] in doc_lines:
            continue
        body = _strip_sql_comments(tok.string)
        if _SQL_BEFORE.search(body) or _SQL_AFTER.search(body):
            for i, line in enumerate(body.split("\n")):
                if _SQL_BEFORE.search(line) or _SQL_AFTER.search(line):
                    out.append((tok.start[0] + i, line.strip()[:120]))

    return sorted({(ln, s) for ln, s in out if ln not in ignored})


def _rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


# ---------------------------------------------------------------------------
# 단언
# ---------------------------------------------------------------------------

def test_no_adj_factor_arithmetic_outside_allowlist():
    """★ 주 단언 — 허용목록 밖 어디에도 adj_factor 산술이 없어야 한다."""
    violations: list[str] = []
    for path in _iter_py_files():
        rel = _rel(path)
        if rel in ALLOWLIST:
            continue
        for lineno, snippet in find_offenses(path):
            violations.append(f"  {rel}:{lineno}  {snippet}")

    assert not violations, (
        "adj_factor 산술 금지 규약 위반 — daily_prices.close 는 이미 분할조정된\n"
        "연속 시세다. 곱하면 분할일 가짜 절벽(-78.5%), 나누면 가짜 급등(+437.9%).\n"
        "이 파일 상단 규약 참조. 의도적 보존이면 ALLOWLIST 에 사유와 함께 등재할 것.\n"
        + "\n".join(violations)
    )


@pytest.mark.parametrize("rel", sorted(ALLOWLIST))
def test_detector_finds_known_offenders(rel):
    """양성 대조 — 탐지기가 실제로 작동하는가.

    🔑 이게 없으면 주 단언은 「탐지기가 고장나도 통과」한다. 알려진 위반 8건을
       매번 다시 잡아내는 것이 주 단언의 판별력 증거다.
    """
    path = REPO / rel
    assert path.exists(), f"허용목록 항목이 사라졌다: {rel} (목록에서 제거할 것)"
    assert find_offenses(path), (
        f"{rel} 의 알려진 adj_factor 산술을 탐지기가 못 잡았다 — "
        f"탐지기 회귀. 주 단언이 vacuous 해졌을 수 있다."
    )


_DETECTOR_CASES: dict[str, tuple[str, bool]] = {
    # (이름, 소스, 탐지돼야 하는가)
    "binop_mul": ('df["close"] = df["close"] * df["adj_factor"]\n', True),
    "binop_div": ('df["close"] = df["close"] / df["adj_factor"]\n', True),
    "via_variable": (  # 변수에 담아 쓰는 형태 — 순진한 정규식이 놓치는 자리
        'af = grp["adj_factor"].fillna(1.0)\n'
        'grp["open"] = grp["open"] / af\n', True),
    "method_mul": ('x = df["close"].mul(df["adj_factor"])\n', True),
    "method_div": ('x = df["close"].div(df["adj_factor"])\n', True),
    "numpy": ('import numpy as np\nx = np.multiply(a, df["adj_factor"])\n', True),
    "sql_mul_coalesce": ('SQL = """SELECT close * COALESCE(adj_factor, 1.0) FROM t"""\n', True),
    "sql_div": ('SQL = """SELECT close / adj_factor AS c FROM t"""\n', True),
    "attribute_form": ('x = df.close * df.adj_factor\n', True),
    # --- 아래는 정상 코드. 오탐이면 가드가 못 쓰게 된다 ---
    "plain_select": ('SQL = """SELECT date, close, adj_factor FROM daily_prices"""\n', False),
    "columns_list": (  # 실측 오탐 원인이었던 형태
        'df = pd.DataFrame(rows, columns=["close", "adj_factor"])\n'
        'px = df["close"] * (1 - 0.001)\n', False),
    "count_star_filter": (
        'SQL = """SELECT COUNT(*) FILTER (WHERE adj_factor IS NOT NULL) FROM t"""\n', False),
    "docstring_mention": ('"""규약: adj_close = raw_close / adj_factor 이다."""\n', False),
    "comparison_only": ('SQL = """SELECT * FROM t WHERE adj_factor <> 1.0"""\n', False),
}


@pytest.mark.parametrize("name", sorted(_DETECTOR_CASES))
def test_detector_form_coverage(name, tmp_path):
    """탐지기가 어떤 «형태»를 잡고 어떤 것을 안 잡는지 고정.

    🔑 변이 주입 실측(2026-08-03)에서 BinOp 전용 판본이 `.mul()`/`.div()`/
       `np.multiply` 를 통째로 놓쳤다. 그 구멍이 다시 열리지 않도록 못 박는다.
       음성 사례(오탐 방지)도 같이 고정한다 — 오탐이 나면 가드가 꺼지게 된다.
    """
    src, should_detect = _DETECTOR_CASES[name]
    f = tmp_path / "probe.py"
    f.write_text(src, encoding="utf-8")
    found = find_offenses(f)
    if should_detect:
        assert found, f"[{name}] 탐지 실패 — 가드 구멍:\n{src}"
    else:
        assert not found, f"[{name}] 오탐 — 정상 코드를 위반으로 잡았다:\n{src}\n{found}"


def test_scan_is_not_vacuous():
    """반-공허 — 스캔이 파일을 실제로 훑고 adj_factor 소비자를 보고 있는가."""
    files = list(_iter_py_files())
    assert len(files) > 300, f"스캔 파일 수 {len(files)} — rglob/제외규칙이 깨졌다"
    touching = [p for p in files if "adj_factor" in p.read_text(encoding="utf-8", errors="ignore")]
    assert len(touching) > 20, (
        f"adj_factor 를 언급하는 파일이 {len(touching)}개뿐 — 스캔 범위가 무너졌다"
    )
