# -*- coding: utf-8 -*-
"""★ 동결 상수 완전성 — `backtest/tasso_labels/` 트리 전역 AST 기계검사 (2026-08-03).

================================================================================
무엇을 강제하는가
================================================================================

`PREREG.md` §6 게이트 C 는 원래 해시 대상을 **열거**했다 —
*"§5.2 의 층 정의 **및** §2.3-(c) 정규식 원본의 sha256"*.
`CLOSING.md` §5-C6 이 그 열거가 **최소 둘을 빠뜨렸다**고 잡았다:

  ① **난수 시드 숫자** — 문서가 *"시드 고정"* 이라고만 적고 숫자를 안 적었다
  ② **`N`(룩백) 파서 정규식** — 파싱 결과(276/52)만 싣고 파서 자체를 안 실었다

⇒ 교정은 **열거를 더 길게 쓰는 것이 아니라 열거를 그만두는 것**이다.
   결과영향 상수를 `frozen_constants.py` **한 파일**에 모으고, 게이트 C 의 해시 대상을
   **그 파일 전체 바이트**로 바꾼다. 그리고 **열거식이 반드시 빠뜨린다는 것 자체**를
   이 파일이 기계로 막는다.

🔑 **같은 클래스의 선례가 이 저장소에 있다.** 커밋 `6c4cffc` 에서 `adj_factor` 오용
   가드 3본이 전부 열거식이라 **셋 다 `exit_multiverse/data_loader.py` 를 놓쳤고**,
   트리 전역 AST 검사(`RoboTrader_template/tests/test_adj_factor_no_arithmetic.py`)로
   교체해서 잡았다. 이 파일은 그 구현의 구조와 실패 모드 처리를 승계한 것이다.

================================================================================
승계한 실패 모드 — 그 트랙이 변이 주입으로 실측한 구멍들
================================================================================

1. 🔴 **`BinOp` 만 보면 `.mul()`·numpy 형태를 통째로 놓친다.**
   ⇒ 여기서는 **호출 형태·속성 접근·키워드 인자**를 전부 커버한다. 특히
   **pandas `.str.extract/contains/...`** 를 반드시 포함한다 —
   §2.3-(f) 의 `N` 파서가 실제로 `re.*` 가 아니라 `Series.str.extract` 였다.
   `re.*` 만 봤으면 **이 트랙의 실제 위반을 놓쳤을 것**이다.

2. 🔴 **`ast.parse` 실패는 「조용히 0건」이 되어 검사기를 무력화한다.**
   `adj_factor` 트랙 실측: BOM 붙은 `p5_nhb_optimization.py` 를 `utf-8` 로 읽으면
   `ast.parse` 가 SyntaxError → 그 파일이 검사에서 통째로 증발했다.
   ⇒ 여기서는 **파싱 실패를 스킵이 아니라 명시적 위반(`UNPARSEABLE`)** 으로 올린다.
   ⚠️ 그래서 이 파일은 선례와 달리 `utf-8-sig` 가 **아니라** 엄격 `utf-8` 로 읽는다.
   BOM 자체가 위반이기 때문이다(BOM 이 붙으면 검사기가 꺼진다).

3. 🔴 **반-공허(vacuity).** 스캔이 아무것도 안 봐도 주 단언은 통과한다.
   ⇒ 파일 수·AST 노드 수·비허용목록 파일 수를 **전부 단언**한다.

================================================================================
허용목록의 의미 — 그리고 이 가드의 실제 사정거리
================================================================================

`harvest/` **36본**과 `power/` **5본**은 **동결 이전에 산출물을 이미 만든 코드**다
(`labels_v4.csv`·`labels_v5.csv`·`power/mde_final.csv` 등). 고치면 그 산출물을
재현할 수 없으므로 **코드는 보존**하고 허용목록에 사유와 함께 등재한다.

🔴 **정직하게 적는다 — 스캔 대상 44본 중 41본이 허용목록이다.** 즉 이 가드가 *지금*
   실효적으로 보고 있는 것은 나머지 **3본**과 **앞으로 생길 파일**이다.
   그것이 이 설계의 요점이다: **스캔 대상이 아니라 «면제»가 열거식**이므로,
   본실행 코드(`run_selection.py` 등)는 **기본적으로 검사 대상**이 된다.
   열거의 방향이 fail-closed 로 뒤집혀 있다 — 놓치면 통과가 아니라 실패로 기운다.

🔧 **3판에서 이 숫자가 크게 움직였다 (33/4 · 31 → 36/5 · 41), 그리고 그 이유가 중요하다.**
   ⚠️ 초판 docstring 의 「harvest 33본 · power 4본」은 **실제 목록(26 · 5)과 달랐다** —
      손으로 센 값이었다.
   🔴 그리고 검사기를 **상수 대입까지 넓히자 harvest 10본이 «새로» 발화**해 등재됐다.
   ⇒ 🔑 ***허용목록이 짧았던 것은 트리가 깨끗해서가 아니라 검사기가 좁아서였다.***
      **면제 목록의 길이는 위생 지표가 아니라 「검사기 사정거리」의 함수다.**
      짧은 면제 목록을 보고 「거의 다 검사되고 있다」로 읽으면 정확히 거꾸로 읽는 것이다.

🔴 **이 가드가 실제로 잡은 것 하나** — `power/` 4본에 **UTF-8 BOM 이 붙어 있다.**
   엄격 `utf-8` 로 읽는 스캐너에서 이 파일들은 **조용히 0건**이 되고, 그러면
   `step2_power.py` 의 시드 리터럴이 검사에서 통째로 증발한다. 위 실패 모드 2번이
   가설이 아니라 **이 트리의 현재 상태**라는 뜻이다. `BOM_FILES` 로 못 박았다.

🔑 허용목록은 동시에 **양성 대조군**이다 — `test_detector_finds_known_offenders` 가
   탐지기가 이들을 실제로 잡는지 매번 확인한다. 탐지기가 고장나 전역 스캔이 조용히
   0건이 되면 주 단언이 vacuous 해지는데, 그 사고를 이 대조가 막는다.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import re
import types
from pathlib import Path

import pytest

TASSO = Path(__file__).resolve().parents[1]          # backtest/tasso_labels
FROZEN = TASSO / "frozen_constants.py"
TESTS_DIR = Path(__file__).resolve().parent

_SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", "node_modules"}

# ---------------------------------------------------------------------------
# 허용목록 — 동결 이전 산출물 생성 코드. 값은 사유.
# ---------------------------------------------------------------------------
_HARVEST_REASON = "동결 전 라벨 수집·파싱 코드 — labels_v4/v5.csv 재현용 보존"
_POWER_REASON = "동결 전 검정력(MDE) 코드 — power/*.csv·mde_final.csv 재현용 보존"

# 🔴 **BOM 표기 항목에 주의.** 아래 `power/` 4본은 실제로 UTF-8 BOM(`ef bb bf`)이
#    붙어 있어 `UNPARSEABLE` 로 잡힌다 — 즉 **선례가 경고한 사고가 이 트리에 실재한다.**
#    엄격 `utf-8` 로 읽는 AST 스캐너는 이 파일들에서 **조용히 0건**이 됐을 것이고,
#    그러면 `step2_power.py` 의 시드 리터럴(`default_rng(RNG_MASTER + k*17 + ...)`)이
#    검사에서 통째로 증발한다. 파싱 실패를 위반으로 올린 덕에 드러났다.
#    ⇒ 여기서는 **고치지 않는다**(동결 전 산출물 재현용 보존). 사실만 기록한다.
_BOM = " · 🔴 UTF-8 BOM 있음 → UNPARSEABLE 로 잡힘 (수정하지 않음: 산출물 재현용 보존)"

# 🔧 **3판에서 10본이 추가됐다 — 그리고 그 사실 자체가 실측 결과다.**
#    검사기를 「상수 대입」까지 넓히자 **그 전에는 조용했던 harvest 10본이 발화**했다.
#    전부 동결 이전 라벨 수집 코드(= 같은 사유)인데, **초판 검사기가 이 클래스를 아예 못 봐서**
#    허용목록에 오를 «필요조차 없었던» 것이다.
#    🔑 ***허용목록이 짧았던 것은 트리가 깨끗해서가 아니라 검사기가 좁아서였다.***
#       면제 목록의 길이를 「위생 지표」로 읽지 말 것 — 그것은 **검사기 사정거리의 함수**다.
_HARVEST_WIDENED = _HARVEST_REASON + " — 🔧 3판 검사기 확장(상수 대입)으로 신규 발화"

ALLOWLIST = {
    # --- harvest/ : labels_v4.csv · labels_v5.csv 를 만든 코드 -------------
    "harvest/aggregate_survivorship.py": _HARVEST_WIDENED,
    "harvest/calc_table.py": _HARVEST_WIDENED,
    "harvest/check_categories.py": _HARVEST_WIDENED,
    "harvest/classify_unmapped_v4.py": _HARVEST_WIDENED,
    "harvest/codename_census.py": _HARVEST_WIDENED,
    "harvest/finalize_unmapped_v4.py": _HARVEST_WIDENED,
    "harvest/finalize_v3.py": _HARVEST_WIDENED,
    "harvest/harvest_list.py": _HARVEST_WIDENED,
    "harvest/probe_unmapped_v4.py": _HARVEST_WIDENED,
    "harvest/verify_coverage.py": _HARVEST_WIDENED,
    "harvest/analyze_posts.py": _HARVEST_REASON,
    "harvest/build_labels_v4.py": _HARVEST_REASON,
    "harvest/build_labels_v5.py": _HARVEST_REASON,
    "harvest/calibrate_naver_index.py": _HARVEST_REASON,
    "harvest/extract_anchor_text.py": _HARVEST_REASON,
    "harvest/extract_calc_images.py": _HARVEST_REASON,
    "harvest/extract_timing.py": _HARVEST_REASON,
    "harvest/fetch_all_calc.py": _HARVEST_REASON,
    "harvest/harvest_bodies.py": _HARVEST_REASON,
    "harvest/harvest_cat28_29.py": _HARVEST_REASON,
    "harvest/harvest_fallback.py": _HARVEST_REASON,
    "harvest/parse_bodies.py": _HARVEST_REASON,
    "harvest/parse_posts.py": _HARVEST_REASON,
    "harvest/parse_prose.py": _HARVEST_REASON,
    "harvest/parse_titles.py": _HARVEST_REASON,
    "harvest/rebuild_labels_v3.py": _HARVEST_REASON,
    "harvest/regime_markers.py": _HARVEST_REASON,
    "harvest/resolve_codes_prose.py": _HARVEST_REASON,
    "harvest/resolve_codes_v4.py": _HARVEST_REASON,
    "harvest/scan_rest.py": _HARVEST_REASON,
    "harvest/test_c_rate_by_year.py": _HARVEST_REASON,
    "harvest/verify_anchor_text.py": _HARVEST_REASON,
    "harvest/verify_preset.py": _HARVEST_REASON,
    "harvest/verify_rationale.py": _HARVEST_REASON,
    "harvest/verify_recall.py": _HARVEST_REASON,
    "harvest/verify_recall_v4.py": _HARVEST_REASON,
    # --- power/ : MDE 계산 (종결). step1 은 T1~T5 정규식의 «복사 원본» ------
    "power/step1_freeze_and_data.py":
        _POWER_REASON + " — 🔑 T1~T5 정규식의 복사 원본이며, "
        "test_type_patterns_match_upstream_original 이 이 파일과 바이트 대조한다",
    "power/step2_power.py": _POWER_REASON + _BOM,
    "power/step3_mde.py":
        _POWER_REASON + " — 🔴 ROUNDTRIP_COST_BY_YEAR 의 출처(:42)" + _BOM,
    "power/step4_sensitivity.py": _POWER_REASON + _BOM,
    "power/step5_summary.py": _POWER_REASON + _BOM,
}

# 🔴 위 4본이 실제로 BOM 을 갖고 있다는 사실 자체를 회귀로 못 박는다 —
#    누가 BOM 을 제거하면 그 파일은 «파싱 가능»해지고 그때부터 진짜 내용이 검사되므로,
#    허용목록 사유(_BOM)가 거짓이 된다. 아래 test_bom_files_are_declared 참조.
BOM_FILES = (
    "power/step2_power.py",
    "power/step3_mde.py",
    "power/step4_sensitivity.py",
    "power/step5_summary.py",
)

# ---------------------------------------------------------------------------
# 탐지 규칙
# ---------------------------------------------------------------------------

# 시드를 받는 호출. 속성명 기준(수신자는 안 따진다 — `np.random.seed` / `random.seed` /
# `torch.manual_seed` 가 전부 같은 형태이고, 오탐이 나도 frozen import 로 통과 가능하다).
_SEED_CALLS = {
    "seed", "manual_seed", "default_rng", "RandomState", "Random", "Generator",
    "PCG64", "PCG64DXSM", "MT19937", "SFC64", "Philox",
}
_SEED_KWARGS = {"seed", "random_state", "random_seed"}

# `re` 모듈 함수 — 첫 인자가 패턴.
_RE_FUNCS = {
    "compile", "search", "match", "fullmatch", "findall", "finditer",
    "sub", "subn", "split",
}
_RE_MODULES = {"re", "regex"}

# 🔴 pandas `.str.<fn>` — 첫 인자가 패턴. **이 트랙의 `N` 파서가 바로 이 형태였다**
#    (`ma["method"].str.extract(r"(\d+)\s*일...")`). `re.*` 만 봤으면 놓쳤다.
_PANDAS_STR_FUNCS = {
    "extract", "extractall", "contains", "match", "fullmatch",
    "replace", "split", "rsplit", "count", "findall",
}

# 🔧 **3판 확장 ① — 패턴을 «키워드 인자» 로 넘기는 형태.**
#    실측 미탐: `re.compile(pattern=r"...")` · `s.str.extract(pat=r"...")`.
#    원인은 `node.args[0]`(위치 인자)만 본 것. 파이썬은 둘을 구분하지 않는다.
_REGEX_KWARGS = {"pattern", "pat", "repl", "regex"}

_UPPER_SNAKE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# 🔧 **3판 확장 ② — 정규식처럼 «보이는» 문자열.**
#    상수 대입 탐지에서 「그냥 문자열」과 「패턴」을 가르는 데 쓴다.
#    ⚠️ 완전하지 않다(예: `r"돌파"` 는 메타문자가 없어 안 걸린다). 그 한계는 문서
#    §6-C 의 「사정거리」 표에 적혀 있다. 여기서 노리는 것은 **오탐을 내지 않으면서**
#    실제 패턴 대부분을 덮는 것이다.
_REGEX_METACHARS = set("\\()[]|+*?{}^$")


def _read_source(path: Path):
    """(소스, 오류사유). 🔴 BOM 을 흡수하지 않는다 — BOM 은 그 자체가 위반이다."""
    try:
        return path.read_text(encoding="utf-8"), None
    except (UnicodeDecodeError, OSError) as exc:
        return None, "읽기 실패: %s" % exc


def _has_numeric_literal(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, (int, float)) \
                and not isinstance(sub.value, bool):
            return True
    return False


def _has_string_literal(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.JoinedStr):
            return True
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            return True
    return False


def _frozen_bindings(tree: ast.AST) -> set:
    """`frozen_constants` 에서 온 이름 + 모듈 별칭."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.split(".")[-1] == "frozen_constants":
                for a in node.names:
                    names.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[-1] == "frozen_constants":
                    names.add(a.asname or a.name.split(".")[0])
    return names


def _references_frozen(node: ast.AST, frozen: set) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in frozen:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr in frozen:
            return True
    return False


def _frozen_derived(tree: ast.AST, frozen: set) -> set:
    """frozen 값에서 파생된 지역 이름까지 전파(고정점).

    🔑 선례(`_tainted_names`)를 그대로 따른다. 이게 없으면
       `pat = T1_PRIOR_HIGH_PATTERN` 뒤의 `rx.search(pat)` 같은 정상 코드가 오탐된다.
       `for name, pat in TYPE_PATTERNS_IN_PRIORITY_ORDER:` 형태도 같은 이유로 필요하다.

    🔴 **컴프리헨션을 빠뜨리면 안 된다.** 실측(2026-08-03): `ast.For` 만 다루는
       판본이 규약을 **정확히 지킨** 코드
       `[(n, re.compile(pat)) for n, pat in TYPE_PATTERNS_IN_PRIORITY_ORDER]` 를
       `REGEX_UNFROZEN` 으로 **오탐**했다. 가드가 정답을 틀렸다고 하면 꺼지게 된다 —
       오탐은 미탐과 같은 결과를 낳는다.
    """
    out = set(frozen)
    for _ in range(8):                       # 고정점 (얕은 체인이라 8회면 충분)
        before = len(out)
        for node in ast.walk(tree):
            targets, value = [], None
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                targets, value = [node.target], node.iter
            elif isinstance(node, ast.comprehension):
                targets, value = [node.target], node.iter
            elif isinstance(node, ast.withitem) and node.optional_vars is not None:
                targets, value = [node.optional_vars], node.context_expr
            elif isinstance(node, ast.NamedExpr):
                targets, value = [node.target], node.value
            if value is None:
                continue
            if _has_numeric_literal(value) or _has_string_literal(value):
                continue
            if not _references_frozen(value, out):
                continue
            for t in targets:
                for sub in ast.walk(t):
                    if isinstance(sub, ast.Name):
                        out.add(sub.id)
        if len(out) == before:
            break
    return out


def _classify(expr: ast.AST, frozen: set, literal_kind: str, unfrozen_kind: str):
    """seed/pattern 자리의 식을 판정. None 이면 통과."""
    if literal_kind == "SEED_LITERAL":
        if _has_numeric_literal(expr):
            return literal_kind
    else:
        if _has_string_literal(expr):
            return literal_kind
    if not _references_frozen(expr, frozen):
        return unfrozen_kind
    return None


def _call_attr_name(func: ast.AST):
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _re_module_aliases(tree: ast.AST) -> set:
    """`re`/`regex` 를 가리키는 **이름 전부**를 import 문에서 뽑는다.

    🔴 **모듈명을 하드코딩하면 안 된다** — 실측 미탐: `import re as _r` 뒤의
       `_r.compile(...)`. 그 판본은 `func.value.id in {"re","regex"}` 로 **이름을 박아**
       두었고, 별칭 하나로 검사기가 통째로 꺼졌다.
    ⇒ AST 로 **별칭 맵을 만들어** 추적한다. 하드코딩은 `_RE_MODULES`(원본 모듈명)에만 남는다.
    """
    aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in _RE_MODULES:
                    aliases.add(a.asname or a.name.split(".")[0])
    return aliases


def _re_direct_names(tree: ast.AST) -> set:
    """`from re import compile, sub as _sub` 형태로 **직접 들여온 함수 이름**.

    🔴 실측 미탐: `from re import compile` 뒤의 `compile(r"...")` —
       속성 접근(`re.compile`)이 아니라 **이름 호출**이라 `ast.Attribute` 검사에 안 걸렸다.
    """
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") in _RE_MODULES:
            for a in node.names:
                if a.name in _RE_FUNCS:
                    names.add(a.asname or a.name)
    return names


def _is_re_module_call(func: ast.AST, aliases: set, direct: set) -> bool:
    if isinstance(func, ast.Attribute) and func.attr in _RE_FUNCS:
        # `re.compile` · `_r.compile` · `mod.re.compile` 전부 커버
        base = func.value
        if isinstance(base, ast.Name) and base.id in aliases:
            return True
        if isinstance(base, ast.Attribute) and base.attr in _RE_MODULES:
            return True
    if isinstance(func, ast.Name) and func.id in direct:
        return True
    return False


def _is_pandas_str_call(func: ast.AST) -> bool:
    return (isinstance(func, ast.Attribute)
            and func.attr in _PANDAS_STR_FUNCS
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "str")


def _looks_like_regex_literal(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if any(c in _REGEX_METACHARS for c in sub.value):
                return True
    return False


def find_offenses(path: Path):
    """[(줄번호, 종류, 코드조각)]. 비면 규약 준수.

    🔴 파싱 실패는 **스킵이 아니라 위반**이다 (`UNPARSEABLE`).

    🔧 **3판 확장 — 초판 검사기는 «검증자 신규 프로브 10종» 중 7종을 미탐했다** (실측).
       (원장 SSOT: 초판 발화 13종 · 신규 프로브 10종 중 7종 미탐 · 회귀 10종 신설
        ⇒ 현행 발화 23 / 음성 13, 계 36. `PREREG_v3.md` §0 `0-j` 와 같은 문장이어야 한다.)
       확장 내역:
       ① 키워드 인자로 넘긴 패턴 (`pattern=` · `pat=` · `repl=`)
       ② `import re as _r` 별칭 추적 (모듈명 하드코딩 폐기)
       ③ `from re import compile` 직접 import
       ④ 🔴 **상수 «대입»** — `COST = {2021: 0.0026, ...}` · 문턱 `THR = 0.50` 등.
          초판은 `ast.Call` 만 순회해서 **대입문이 원리적으로 시야 밖**이었고,
          그래서 §6-C 자신이 C6 의 누락으로 열거한 `COST` 를 못 잡았다.
    """
    src, err = _read_source(path)
    if src is None:
        return [(0, "UNPARSEABLE", err)]
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError) as exc:
        return [(getattr(exc, "lineno", 0) or 0, "UNPARSEABLE", str(exc))]

    frozen = _frozen_derived(tree, _frozen_bindings(tree))
    aliases = _re_module_aliases(tree)
    direct = _re_direct_names(tree)
    out = []

    def add(node, kind):
        seg = ast.get_source_segment(src, node) or ""
        out.append((node.lineno, kind, " ".join(seg.split())[:120]))

    for node in ast.walk(tree):

        # ---- (4) 상수 대입: `UPPER_SNAKE = <리터럴>` ---------------------------
        # 🔴 이 절이 3판에서 신설됐다. 호출만 보면 상수 파일 «복제» 를 영원히 못 잡는다.
        targets, value = [], None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        if value is not None:
            for tg in targets:
                if not (isinstance(tg, ast.Name) and _UPPER_SNAKE.match(tg.id)):
                    continue
                if _has_numeric_literal(value):
                    add(node, "CONST_LITERAL")
                elif _looks_like_regex_literal(value):
                    add(node, "REGEX_LITERAL")

        if not isinstance(node, ast.Call):
            continue
        name = _call_attr_name(node.func)

        # (1) 시드 — 위치 인자
        if name in _SEED_CALLS and node.args:
            kind = _classify(node.args[0], frozen, "SEED_LITERAL", "SEED_UNFROZEN")
            if kind:
                add(node, kind)

        # (2) 시드 — 키워드 인자 (`seed=`, `random_state=`)
        for kw in node.keywords:
            if kw.arg in _SEED_KWARGS:
                kind = _classify(kw.value, frozen, "SEED_LITERAL", "SEED_UNFROZEN")
                if kind:
                    add(node, kind)

        # (3) 정규식 — `re.*(...)` · 별칭 · `from re import ...` · pandas `.str.*(...)`
        is_pattern_call = (_is_re_module_call(node.func, aliases, direct)
                           or _is_pandas_str_call(node.func))
        if is_pattern_call:
            if node.args:
                kind = _classify(node.args[0], frozen, "REGEX_LITERAL", "REGEX_UNFROZEN")
                if kind:
                    add(node, kind)
            # 🔧 키워드로 넘긴 패턴 — 위치 인자만 보던 판본이 통째로 놓친 형태
            for kw in node.keywords:
                if kw.arg in _REGEX_KWARGS:
                    kind = _classify(kw.value, frozen, "REGEX_LITERAL", "REGEX_UNFROZEN")
                    if kind:
                        add(node, kind)

    return sorted(set(out))


def _iter_scanned_files():
    """검사 대상 — `frozen_constants.py` 자신과 `tests/` 는 제외."""
    for p in sorted(TASSO.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        rp = p.resolve()
        if rp == FROZEN.resolve() or TESTS_DIR in rp.parents:
            continue
        yield p


def _rel(p: Path) -> str:
    return p.relative_to(TASSO).as_posix()


# ===========================================================================
# 해시 정규화 — 게이트 C 가 대조할 바이트열의 정의 (SSOT)
# ===========================================================================

def normalized_bytes(path: Path) -> bytes:
    """게이트 C 해시 대상의 정규화 규약.

    **줄바꿈만 LF 로 통일한 UTF-8 바이트열.**

    🔴 Windows 환경이라 이건 실제 위험이다. `core.autocrlf` / 에디터 / git 체크아웃이
       **내용을 안 바꾸고도** CRLF↔LF 를 뒤집는다. 동결 커밋에서 잰 해시와 본실행
       시점에 잰 해시가 그 이유로 달라지면, 게이트 C 는 **실재하지 않는 변조를 보고**
       중단한다 — 그리고 그 오경보를 끄는 가장 쉬운 방법이 게이트를 끄는 것이다.
       ⇒ 해시를 **체크아웃의 성질이 아니라 내용의 성질**로 만든다.

    ⚠️ **BOM 은 정규화하지 않는다 (일부러).** BOM 을 흡수하면 BOM 이 붙어도 해시가
       같아지는데, BOM 은 `ast.parse` 를 깨뜨려 이 파일의 검사기를 통째로 꺼버린다
       (선례: `p5_nhb_optimization.py`). ⇒ BOM 삽입은 **해시가 바뀌어야 하는 변경**이다.
    """
    raw = path.read_bytes()
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def frozen_sha256() -> str:
    return hashlib.sha256(normalized_bytes(FROZEN)).hexdigest()


# ===========================================================================
# 검사 1 — 주 단언: 파일 밖 결과영향 상수 차단
# ===========================================================================

def test_no_result_affecting_constants_outside_frozen():
    """★ 주 단언 — 허용목록 밖 어디에도 시드/정규식 리터럴이 없어야 한다."""
    violations = []
    for path in _iter_scanned_files():
        rel = _rel(path)
        if rel in ALLOWLIST:
            continue
        for lineno, kind, snippet in find_offenses(path):
            violations.append("  %s:%d  [%s]  %s" % (rel, lineno, kind, snippet))

    assert not violations, (
        "결과영향 상수가 frozen_constants.py 밖에 있다 (게이트 C 의 해시가 안 잡는다).\n"
        "CLOSING.md §5-C6: 열거식 해시가 시드 숫자와 N 파서를 빠뜨렸다.\n"
        "값은 frozen_constants.py 에 두고 **import** 할 것. 동결 전 산출물 코드면\n"
        "ALLOWLIST 에 사유와 함께 등재할 것.\n" + "\n".join(violations)
    )


def test_allowlist_entries_all_exist():
    """허용목록에 유령 항목이 남지 않게 — 파일이 사라지면 목록에서 지운다."""
    missing = [rel for rel in sorted(ALLOWLIST) if not (TASSO / rel).exists()]
    assert not missing, "허용목록 항목이 실재하지 않는다: %s" % missing


def test_bom_files_are_declared():
    """🔴 BOM 실태를 고정한다 — 이 트리에 **실재하는** 선례 사고.

    `power/` 4본에 UTF-8 BOM(`ef bb bf`)이 붙어 있다. 엄격 `utf-8` AST 스캐너는
    이런 파일에서 **조용히 0건**이 되어 무력화된다(`adj_factor` 트랙이 실측한
    `p5_nhb_optimization.py` 사고와 같은 형태). 여기서는 파싱 실패를 위반으로 올려
    드러냈고, 허용목록 사유에 그 사실을 적었다.

    ⇒ BOM 이 사라지거나 새로 생기면 이 단언이 깨지고 허용목록 사유를 갱신하게 된다.
    """
    actual = tuple(
        rel for rel in sorted(ALLOWLIST)
        if (TASSO / rel).read_bytes().startswith(b"\xef\xbb\xbf")
    )
    assert actual == BOM_FILES, (
        "BOM 실태가 바뀌었다.\n  선언: %s\n  실제: %s\n"
        "허용목록의 _BOM 사유를 갱신할 것." % (list(BOM_FILES), list(actual))
    )
    for rel in BOM_FILES:
        kinds = {k for _, k, _ in find_offenses(TASSO / rel)}
        assert "UNPARSEABLE" in kinds, (
            "%s 는 BOM 이 있는데 UNPARSEABLE 로 안 잡혔다 — 파싱 실패가 "
            "조용한 스킵으로 되돌아갔다 (검사기 무력화)" % rel
        )


@pytest.mark.parametrize("rel", sorted(ALLOWLIST))
def test_detector_finds_known_offenders(rel):
    """양성 대조 — 탐지기가 실제로 작동하는가.

    🔑 이게 없으면 주 단언은 「탐지기가 고장나도 통과」한다. 알려진 위반 파일을
       매번 다시 잡아내는 것이 주 단언의 판별력 증거다.
    """
    assert find_offenses(TASSO / rel), (
        "%s 의 알려진 시드/정규식 리터럴을 탐지기가 못 잡았다 — 탐지기 회귀. "
        "주 단언이 vacuous 해졌을 수 있다." % rel
    )


# ===========================================================================
# 검사 2 — vacuity 가드
# ===========================================================================

def test_scan_is_not_vacuous():
    """반-공허 — 스캔이 파일과 AST 노드를 실제로 보고 있는가."""
    files = list(_iter_scanned_files())
    assert len(files) >= 40, (
        "스캔 파일 수 %d — rglob/제외규칙이 깨졌다 (동결 시점 실측 **44본**. "
        "이 수는 frozen_constants.py 와 tests/ 를 «이미 제외한» 뒤의 값이다 — "
        "🔧 초안 메시지의 「44개 중 frozen 제외 = 43」은 두 번 뺀 것이라 틀렸다)" % len(files)
    )

    nodes = 0
    parsed = 0
    for p in files:
        src, err = _read_source(p)
        if src is None:
            continue
        try:
            nodes += sum(1 for _ in ast.walk(ast.parse(src)))
            parsed += 1
        except SyntaxError:
            continue
    assert parsed >= 40, "실제로 파싱된 파일이 %d개뿐 — 스캔이 무너졌다" % parsed
    assert nodes > 10000, "훑은 AST 노드가 %d개뿐 — 스캔이 무너졌다" % nodes

    # 허용목록 밖 파일이 실제로 존재해야 주 단언에 사정거리가 있다.
    scanned_live = [p for p in files if _rel(p) not in ALLOWLIST]
    assert scanned_live, (
        "허용목록이 스캔 대상을 전부 삼켰다 — 주 단언이 공허해졌다"
    )


def test_frozen_constants_file_exists_and_is_scanned_target():
    """해시 대상 파일이 실재하고 비어 있지 않은가."""
    assert FROZEN.exists(), "frozen_constants.py 가 없다"
    assert len(FROZEN.read_bytes()) > 2000, "frozen_constants.py 가 비정상적으로 작다"


# ===========================================================================
# 검사 3 — 해시 안정성 / 정규화 규약
# ===========================================================================

def test_hash_is_deterministic():
    assert frozen_sha256() == frozen_sha256()
    assert len(frozen_sha256()) == 64


def test_hash_is_line_ending_invariant(tmp_path):
    """🔴 CRLF/LF 로 해시가 흔들리면 안 된다 (Windows 실위험)."""
    body = "MASTER_SEED = 20260803\nALPHA = 0.05\n"
    lf = tmp_path / "lf.py"
    crlf = tmp_path / "crlf.py"
    cr = tmp_path / "cr.py"
    lf.write_bytes(body.encode("utf-8"))
    crlf.write_bytes(body.replace("\n", "\r\n").encode("utf-8"))
    cr.write_bytes(body.replace("\n", "\r").encode("utf-8"))

    h = [hashlib.sha256(normalized_bytes(p)).hexdigest() for p in (lf, crlf, cr)]
    assert h[0] == h[1] == h[2], "정규화가 줄바꿈을 흡수하지 못했다: %s" % h

    # 비-공허: 정규화가 없었다면 실제로 달랐어야 한다.
    raw = {p.read_bytes() for p in (lf, crlf, cr)}
    assert len(raw) == 3, "세 판본의 원본 바이트가 같다 — 이 테스트가 아무것도 안 재고 있다"


def test_hash_changes_on_bom_insertion(tmp_path):
    """⚠️ BOM 은 «흡수하지 않는다». BOM 이 붙으면 검사기가 꺼지므로 해시가 바뀌어야 한다."""
    body = b"MASTER_SEED = 20260803\n"
    plain = tmp_path / "plain.py"
    bom = tmp_path / "bom.py"
    plain.write_bytes(body)
    bom.write_bytes(b"\xef\xbb\xbf" + body)
    assert (hashlib.sha256(normalized_bytes(plain)).hexdigest()
            != hashlib.sha256(normalized_bytes(bom)).hexdigest())


def test_frozen_file_has_no_bom():
    """🔴 BOM 이 있으면 `ast.parse` 가 깨져 이 파일의 검사기가 통째로 무력화된다."""
    assert not FROZEN.read_bytes().startswith(b"\xef\xbb\xbf"), (
        "frozen_constants.py 에 UTF-8 BOM 이 붙었다 — 제거할 것"
    )


def test_hash_report(capsys):
    """게이트 C 가 동결 커밋에 기록할 값. 실패하지 않고 값을 남긴다."""
    with capsys.disabled():
        print("\n[게이트 C] frozen_constants.py sha256(LF 정규화) = %s" % frozen_sha256())


# ===========================================================================
# 검사 4 — 🔴 변이 주입: 검사기 자신의 판별력 실증
# ===========================================================================

_MUTATIONS = {
    # (이름, 소스, 탐지돼야 하는가)
    "seed_random_literal": ("import random\nrandom.seed(12345)\n", True),
    "seed_numpy_literal": ("import numpy as np\nnp.random.seed(999)\n", True),
    "seed_default_rng_literal": (
        "import numpy as np\nrng = np.random.default_rng(20260803)\n", True),
    "seed_kwarg_literal": (
        "import numpy as np\nx = sample(pool, seed=7)\n", True),
    "seed_random_state_literal": (
        "m = train(X, y, random_state=0)\n", True),
    "seed_generator_call": (
        "from numpy.random import Generator, PCG64\ng = Generator(PCG64(42))\n", True),
    "regex_re_compile_literal": (
        "import re\nRX = re.compile(r\"직전\\s*고|전고\\b|신고가\")\n", True),
    "regex_re_search_literal": (
        "import re\nm = re.search(r\"전일\\s*고\", s)\n", True),
    # 🔴 이 트랙의 실제 `N` 파서 형태 — `re.*` 만 봤으면 놓쳤을 자리
    "regex_pandas_str_extract_literal": (
        "ma[\"N\"] = ma[\"method\"].str.extract(r\"(\\d+)\\s*일\\s*(?:이평선|이평)\")[0]\n", True),
    "regex_fstring_pattern": (
        "import re\nm = re.search(f\"{prefix}고\", s)\n", True),
    "bom_breaks_parser": ("﻿MASTER_SEED = 20260803\n", True),
    "syntax_error": ("def broken(:\n", True),
    "seed_unfrozen_name": (
        "import numpy as np\nrng = np.random.default_rng(cfg.seed)\n", True),

    # ======================================================================
    # 🔴 3판 신설 — **검증자 신규 프로브 10종** (find_offenses 를 직접 돌려 실측:
    #    그중 **7종이 미탐**이었고, 나머지 3종은 같은 클래스라 함께 회귀로 넣었다).
    #    ⚠️ **이 블록은 7개가 아니라 10개다** — 「미탐 7종」과 「신설 10종」은 다른 수다.
    #      (초판 판본은 헤더에 「7종」이라 적고 내용은 10개였다. 원장 SSOT 는
    #       `PREREG_v3.md` §0 `0-j` 와 이 파일 `find_offenses` 독스트링에 같은 문장으로 있다.)
    # ======================================================================
    # ① 🔴 가장 아픈 것 — §6-C 자신이 C6 의 누락으로 «열거한» COST 상수인데,
    #    그것을 잡으라고 만든 검사가 못 잡고 있었다. 원인: ast.Call 만 순회.
    "const_cost_dict_literal": (
        "COST = {2021: 0.0026, 2022: 0.0026, 2023: 0.0023, 2024: 0.0021}\n", True),
    # ② 문턱 상수 대입 — 커버율 0.50 · 게이트 A 0.0005 · m=10 · L=20 · Q=5 · 풀 30/300
    "const_threshold_scalar": ("CB_COVERAGE_MIN = 0.50\n", True),
    "const_gate_threshold": ("GATE_A_NULL_DELTA_MAX = 0.0005\n", True),
    "const_sampling_params": ("M_CTRL = 10\nL_LOOKBACK = 20\nQ = 5\n", True),
    "const_pool_thresholds": ("POOL_MIN = 30\nCA_POOL_MIN = 300\n", True),
    # ③ 층 정의 — 연도 튜플에 숫자 리터럴이 있다
    "const_strata_definition": (
        "STRATA_YEARS = (2021, 2022, 2023, 2024)\n", True),
    # ④ `import re as _r` — 초판은 func.value.id in {\"re\",\"regex\"} 로 모듈명을 박아 뒀다
    "regex_module_alias_import": (
        "import re as _r\nRX2 = _r.compile(r\"전일\\s*고\")\n", True),
    # ⑤ `from re import compile` — 속성 접근이 아니라 «이름 호출» 이라 안 걸렸다
    "regex_from_import_direct": (
        "from re import compile\nrx = compile(r\"직전\\s*고|신고가\")\n", True),
    # ⑥⑦ 키워드 인자로 넘긴 패턴 — 초판은 node.args[0](위치 인자)만 봤다
    "regex_kwarg_pattern": (
        "import re\nrx = re.compile(pattern=r\"연속\\s*상승|연속\\s*양봉\")\n", True),
    "regex_kwarg_pandas_pat": (
        "ma[\"N\"] = ma[\"method\"].str.extract(pat=r\"(\\d+)\\s*일\\s*(?:이평선|이평)\")[0]\n", True),

    # --- 아래는 정상 코드. 오탐이면 가드가 못 쓰게 된다 -----------------------
    "ok_seed_from_frozen": (
        "import numpy as np\n"
        "from frozen_constants import MASTER_SEED, ARM_SEED_OFFSETS\n"
        "rng = np.random.default_rng(MASTER_SEED + ARM_SEED_OFFSETS[arm])\n", False),
    "ok_regex_from_frozen": (
        "import re\n"
        "from frozen_constants import T1_PRIOR_HIGH_PATTERN\n"
        "RX = re.compile(T1_PRIOR_HIGH_PATTERN)\n", False),
    "ok_regex_from_frozen_via_loop": (
        "import re\n"
        "from frozen_constants import TYPE_PATTERNS_IN_PRIORITY_ORDER\n"
        "for name, pat in TYPE_PATTERNS_IN_PRIORITY_ORDER:\n"
        "    rx = re.compile(pat)\n", False),
    # 🔴 실측 오탐(2026-08-03). `ast.For` 만 다루던 판본이 이 «정답» 코드를
    #    REGEX_UNFROZEN 으로 잡았다. 오탐은 미탐과 같은 결과를 낳는다 — 가드가 꺼진다.
    "ok_regex_from_frozen_via_comprehension": (
        "import re\n"
        "from frozen_constants import TYPE_PATTERNS_IN_PRIORITY_ORDER\n"
        "RX = [(n, re.compile(pat)) for n, pat in TYPE_PATTERNS_IN_PRIORITY_ORDER]\n", False),
    "ok_pandas_str_from_frozen": (
        "from frozen_constants import N_LOOKBACK_PARSER_PATTERN as NP\n"
        "ma[\"N\"] = ma[\"method\"].str.extract(NP)[0]\n", False),
    "ok_plain_string_split": (          # 정규식이 아니다 — 오탐 방지
        "parts = line.split(\",\")\n", False),
    "ok_arithmetic_literal": (          # 시드가 아닌 숫자는 대상이 아니다
        "n = len(rows) * 2 + 1\n", False),
    "ok_module_alias_import": (
        "import numpy as np\n"
        "import frozen_constants as fc\n"
        "rng = np.random.default_rng(fc.MASTER_SEED)\n", False),
    # 🔴 상수 «대입» 탐지의 음성 대조 — 소문자 지역변수·frozen 재노출은 오탐이면 안 된다.
    #    (오탐은 미탐과 같은 결과를 낳는다 — 가드가 꺼진다.)
    "ok_lowercase_local_number": (
        "threshold = 0.50\ncount = 30\n", False),
    "ok_const_from_frozen": (
        "from frozen_constants import CB_COVERAGE_MIN\n"
        "COVERAGE_MIN = CB_COVERAGE_MIN\n", False),
    "ok_const_plain_string": (          # 메타문자 없는 문자열은 패턴이 아니다
        "ARM_NAMES = (\"C-B-raw\", \"C-A\")\n", False),
    "ok_const_bool_flag": (             # bool 은 숫자 리터럴로 세지 않는다
        "VERIFIED = False\nRESOLVED = True\n", False),
    "ok_const_none_placeholder": (      # D-12 미결 표기 형태
        "MATCH_METHOD = None\n", False),
}


# ---------------------------------------------------------------------------
# 🔴 변이 원장(ledger) — **세지 말고 «유도»한다**
# ---------------------------------------------------------------------------
#
# **무엇이 틀렸나**: 원장 수치가 문서 7곳·테스트 5곳에 **손으로** 적혀 있었고,
# 3차 라운드가 *"실측 원장을 하나로 고정 … 5곳 통일"* 이라 적고 **문서만 고쳤다.**
# 게다가 고정한 값 자체가 틀렸다 — *"초판 발화 13종 중 10종 미탐"* 인데
# **그 라운드는 71 passed 였다**(13종이 전부 잡혔다는 뜻이다).
#
# 🔑 ***세 개의 다른 명제가 「미탐」 하나로 뭉개져 있었다:***
#      · **초판 발화 스위트 = 13종**            (그 라운드에 이미 전건 차단)
#      · **검증자 «신규 프로브» 10종 중 7종 미탐** (아래 튜플의 길이가 그 7이다)
#      · **회귀 신설 = 10종**                    (미탐 7 + 같은 클래스 3)
#    ⇒ **현행 발화 23 / 음성 13 (계 36)**
#
# ⇒ 교정은 「이번엔 정확히 세는 것」이 아니라 **수를 목록에서 «유도»하고, 문서에 적힌
#   수를 그 유도값과 기계 대조하는 것**이다 (이 파일 ALLOWLIST·검사 8·검사 9 와 같은 설계).

# 🔴 검증자가 **실측으로** 미탐을 확인한 형태. 원장의 「미탐 7종」 = 이 튜플의 길이.
_VERIFIER_MEASURED_MISSES = (
    "const_cost_dict_literal",
    "const_threshold_scalar",
    "const_strata_definition",
    "regex_module_alias_import",
    "regex_from_import_direct",
    "regex_kwarg_pattern",
    "regex_kwarg_pandas_pat",
)

# 🔴 3판에서 **신설된 발화 프로브 전부**. 원장의 「회귀 10종 신설」 = 이 튜플의 길이.
#    미탐 7종 + **같은 클래스라 함께 넣은 3종**(문턱·표본·풀 상수 대입).
_THIRD_EDITION_NEW_PROBES = _VERIFIER_MEASURED_MISSES + (
    "const_gate_threshold",
    "const_sampling_params",
    "const_pool_thresholds",
)


@pytest.mark.parametrize("name", sorted(_MUTATIONS))
def test_detector_mutation_injection(name, tmp_path):
    """🔴 탐지기가 «실제로» 잡는지 임시 파일에 위반을 주입해 실증한다.

    🔑 선례(`adj_factor` 가드)가 이 방식으로 **자기 구멍 두 개**를 찾았다:
       `BinOp` 만 보는 판본이 `.mul()`/`np.multiply` 를 통째로 놓쳤고,
       BOM 파일이 조용히 스캔에서 증발했다. 같은 사고를 여기서 미리 막는다.

    ⚠️ 임시 파일은 `tmp_path`(워크트리 밖 OS 임시 트리)에 만들고 pytest 가 정리한다.
    """
    src, should_detect = _MUTATIONS[name]
    f = tmp_path / "probe.py"
    f.write_bytes(src.encode("utf-8"))
    found = find_offenses(f)
    if should_detect:
        assert found, "[%s] 탐지 실패 — 가드 구멍:\n%s" % (name, src)
    else:
        assert not found, "[%s] 오탐 — 정상 코드를 위반으로 잡았다:\n%s\n%s" % (name, src, found)


def test_mutation_suite_covers_required_forms():
    """변이 주입 스위트 자체가 얇아지지 않게 못 박는다.

    🔧 **3판에서 문턱을 올렸다.** 검증자가 초판 `find_offenses()` 에 **신규 프로브 10종**을
       돌려 **7종 미탐**을 실측했고, 그 **프로브 10종이 전부** 여기 회귀로 들어왔다
       (미탐 7종 + 같은 클래스 3종). ⇒ 초판 발화 13 + 신설 10 = **현행 발화 23**.
       ⚠️ **스위트가 얇으면 「전부 잡는다」는 주장이 실측 없이 통과한다** — 그것이
       게이트 C 자문 3 이 🟢 「구조상 자명」으로 적혀 있던 경로다.
    """
    firing = [k for k, (_, d) in _MUTATIONS.items() if d]
    negative = [k for k, (_, d) in _MUTATIONS.items() if not d]
    assert len(firing) >= 20, "발화 사례가 %d종뿐" % len(firing)
    assert len(negative) >= 8, "음성 대조가 %d종뿐 — 오탐을 못 잡는다" % len(negative)
    assert sum(1 for k in firing if k.startswith("seed_")) >= 3, "시드 형태 3종 미만"
    assert sum(1 for k in firing if k.startswith("regex_")) >= 6, "정규식 형태 6종 미만"
    # 🔴 상수 «대입» 계열 — 초판이 원리적으로 못 보던 범주(ast.Call 만 순회했다)
    assert sum(1 for k in firing if k.startswith("const_")) >= 6, "상수 대입 형태 6종 미만"
    assert "bom_breaks_parser" in firing, "BOM/파싱실패 사례가 빠졌다"
    # 🔑 초판이 «실측으로» 미탐한 형태는 이름으로 못 박는다 — 조용히 빠지면 안 된다.
    #    ⚠️ 개수를 여기 «다시 적지» 않는다 — 원장의 「미탐 7종」은 이 튜플의 길이다.
    for required in _VERIFIER_MEASURED_MISSES:
        assert required in firing, (
            "%s 가 스위트에서 빠졌다 — 초판이 «실측으로» 미탐한 형태다" % required)
    for required in _THIRD_EDITION_NEW_PROBES:
        assert required in firing, (
            "%s 가 스위트에서 빠졌다 — 3판 신설 프로브다 (원장의 「회귀 10종 신설」)" % required)


def test_mutation_ledger_in_doc_matches_actual_suite():
    """🔴 문서에 적힌 변이 원장이 **실제 스위트 계수와 같은가** — 기계 대조.

    🔑 **이 검사가 왜 생겼는지가 요점이다.** 3차 라운드는 원장을 *"하나로 고정"* 했다고
       적었지만 (i) **고정한 값이 틀렸고**(초판 발화 13종을 「10종 미탐」이라 적었다 —
       그 라운드는 71 passed 였다) (ii) **문서만 고치고 이 파일은 안 고쳤다.**
       ⇒ 사람이 12곳을 맞추는 일이 아니라, **한 곳(목록)에서 유도하고 문서를 대조**한다.
    """
    firing = [k for k, (_, d) in _MUTATIONS.items() if d]
    negative = [k for k, (_, d) in _MUTATIONS.items() if not d]

    # ① 원장 수치를 «목록에서» 유도한다 — 손으로 세지 않는다.
    n_new = len(_THIRD_EDITION_NEW_PROBES)
    n_miss = len(_VERIFIER_MEASURED_MISSES)
    n_first = len(firing) - n_new
    ledger = {
        "초판 발화": n_first, "신규 프로브": n_new, "미탐": n_miss,
        "회귀 신설": n_new, "현행 발화": len(firing),
        "음성": len(negative), "계": len(firing) + len(negative),
    }

    # ② 신설 프로브가 실제로 발화 목록 안에 있고, 미탐 ⊆ 신설 인가 (유도의 전제).
    assert set(_THIRD_EDITION_NEW_PROBES) <= set(firing), (
        "3판 신설 프로브가 발화 목록 밖이다: %s"
        % sorted(set(_THIRD_EDITION_NEW_PROBES) - set(firing)))
    assert set(_VERIFIER_MEASURED_MISSES) <= set(_THIRD_EDITION_NEW_PROBES)

    # ③ 🔴 문서의 원장 문장을 파싱해 대조한다.
    flat = re.sub(r"\s+", " ", _doc_text())
    m = re.search(
        r"원장\(SSOT\)\*\*: 초판 발화 \*\*(\d+)종\*\* · 검증자 신규 프로브 "
        r"\*\*(\d+)종 중 (\d+)종 미탐\*\* · 회귀 \*\*(\d+)종 신설\*\* ⇒ "
        r"\*\*현행 발화 (\d+) / 음성 (\d+) \(계 (\d+)\)\*\*", flat)
    assert m, (
        "문서(§0 `0-j`)에서 변이 원장 문장을 못 찾았다 — 표기가 바뀌었거나 원장이 "
        "사라졌다. 둘 다 「문서와 테스트의 원장이 갈라졌다」는 뜻이다.\n"
        "  기대 형태: 원장(SSOT)**: 초판 발화 **N종** · 검증자 신규 프로브 "
        "**N종 중 N종 미탐** · 회귀 **N종 신설** ⇒ **현행 발화 N / 음성 N (계 N)**")
    doc = dict(zip(("초판 발화", "신규 프로브", "미탐", "회귀 신설",
                    "현행 발화", "음성", "계"), (int(x) for x in m.groups())))

    diff = {k: (doc[k], ledger[k]) for k in ledger if doc[k] != ledger[k]}
    assert not diff, (
        "🔴 변이 원장이 문서와 실제 스위트에서 갈라졌다 (문서값, 실측값):\n  %s\n"
        "🔑 세 명제를 섞지 말 것 — 「초판 발화 스위트」·「신규 프로브 중 미탐」·"
        "「회귀 신설」은 서로 다른 수다." % diff)

    # ④ 비-공허: 원장이 자기정합인가 (초판 + 신설 = 현행).
    assert ledger["초판 발화"] + ledger["회귀 신설"] == ledger["현행 발화"]
    assert ledger["현행 발화"] + ledger["음성"] == ledger["계"]


# ===========================================================================
# 검사 5 — 정규식이 «손으로 옮겨 적히지» 않았음을 기계로 증명
# ===========================================================================
#
# §13.2-1 실측: `\s*` 포함 판본 **72글** vs 리터럴 공백 전사판 **67글** —
# **5글 차이가 무경고로 났다.** 그리고 C6 은 *"이 규칙을 세운 문서가 룩백 파서에
# 대해서는 다시 어겼다"* 는 지적이다. ⇒ 사람의 대조에 맡기지 않는다.

def _load_frozen_module(source=None):
    """`frozen_constants.py` 를 모듈로 만든다. `source` 를 주면 그 소스로 (변이 주입용).

    🔴 **바이트코드 캐시를 «원리적으로» 타지 않는다.**
       이전 판본은 `importlib` 의 `exec_module` 을 썼는데, `SourceFileLoader.get_code`
       는 `__pycache__/*.pyc` 헤더의 **(mtime 초, 소스 크기)** 만 보고 캐시를 재사용한다.
       ⇒ **크기가 같은 두 변이를 같은 초에 쓰면 두 번째가 첫 번째의 코드로 로드된다.**

    🔑 **가설이 아니라 이 워크트리에서의 실측이다 (2026-08-04)**:
         ① `MATCH_R4_SATISFIED = True` (49,757 B · mtime T) → 146 passed
         ② `D12_RESOLVED      = True` (49,757 B · mtime T) → **146 passed** ← 캐시 재사용
         ③ 같은 ② 상태를 `__pycache__` 삭제 후 재실행      → **1 failed**
       ②와 ③은 **같은 파일 내용인데 결과가 다르다.** 즉 이 스위트는 변이 주입 결과를
       조용히 뒤바꿀 수 있는 경로를 갖고 있었고, 아래 플래그 변이 회귀가 바로 그 경로를 탄다.

    ⚠️ `sys.dont_write_bytecode` 로는 부족하다 — 그것은 «쓰기»만 막고 **이미 있는 캐시의
       «읽기»를 못 막는다.** `compile()` + `exec()` 는 캐시 경로 자체를 지나가지 않는다.
    """
    src = FROZEN.read_text(encoding="utf-8") if source is None else source
    mod = types.ModuleType("_frozen_constants_under_test")
    mod.__file__ = str(FROZEN)
    exec(compile(src, str(FROZEN), "exec"), mod.__dict__)
    return mod


def _mutated_frozen_source(overrides: dict) -> str:
    """모듈 레벨 상수 대입을 «소스에서» 갈아끼운 사본을 만든다 (변이 주입).

    🔴 워크트리의 실제 파일은 건드리지 않는다 — 변이는 **메모리 안에서만** 산다.
    """
    src = FROZEN.read_text(encoding="utf-8")
    for name, literal in overrides.items():
        pattern = r"(?m)^%s = .*$" % re.escape(name)
        src, n = re.subn(pattern, lambda _m, k=name, v=literal: "%s = %s" % (k, v),
                         src, count=1)
        assert n == 1, (
            "변이 주입 실패 — `%s = …` 모듈 레벨 대입을 못 찾았다. 상수가 개명됐다면 "
            "이 회귀도 함께 갱신할 것 (안 하면 변이 회귀가 조용히 vacuous 해진다)" % name)
    return src


def _raises_assertion(fn) -> bool:
    try:
        fn()
    except AssertionError:
        return True
    return False


def _extract_upstream_patterns(text: str) -> dict:
    """`MA_TOK`/`RX` 블록에서 패턴 «소스 텍스트»를 뽑는다 (재타이핑 없음)."""
    m = re.search(r"^MA_TOK = (r\".*?\")\s*$", text, re.M)
    assert m, "상류에서 MA_TOK 을 못 찾았다"
    out = {"MA_TOK": m.group(1)}
    for key in ("T3_ma_bounce", "T4_ma_break", "T2_prev_high",
                "T1_prior_high", "T5_consec_up"):
        mm = re.search(r'\("%s",\s*re\.compile\((.*?)\)\),\s*$' % key, text, re.M)
        assert mm, "상류에서 %s 를 못 찾았다" % key
        out[key] = mm.group(1).strip()
    return out


@pytest.mark.parametrize(
    "upstream",
    ["power/step1_freeze_and_data.py", "PREREG.md", "PREREG_v3.md"])
def test_type_patterns_match_upstream_original(upstream):
    """T1~T5 정규식이 **상류 원본과 바이트 동일**한가.

    상류가 셋이다 — 실행 코드(`step1`)와 사전등록 문서 **2판·3판** §2.3-(c).

    🔧 **`PREREG_v3.md` 가 3판에서 추가됐다.** 그 전에는 대조가 **2판에만 앵커**돼 있었는데,
       🔴 **동결 커밋에 들어가는 것은 3판(`PREREG_v3.md`)이다.**
       ⇒ 3판 §2.3-(c) 블록이 조용히 달라져도 아무도 못 잡는 상태였다.
       (2판은 동결 보존판이라 한 글자도 안 고치지만, «안 고친다»는 규약은 검사가 아니다.)
    """
    text = (TASSO / upstream).read_text(encoding="utf-8")
    up = _extract_upstream_patterns(text)
    fc = _load_frozen_module()

    # 상류의 소스 텍스트를 그대로 평가해 «값»으로 만든 뒤 비교한다.
    ns = {"MA_TOK": eval(up["MA_TOK"])}
    assert fc.MA_TOK_PATTERN == ns["MA_TOK"], (
        "MA_TOK 불일치\n  frozen: %r\n  %s: %r" % (fc.MA_TOK_PATTERN, upstream, ns["MA_TOK"]))

    expected = {
        "T3_ma_bounce": fc.T3_MA_BOUNCE_PATTERN,
        "T4_ma_break": fc.T4_MA_BREAK_PATTERN,
        "T2_prev_high": fc.T2_PREV_HIGH_PATTERN,
        "T1_prior_high": fc.T1_PRIOR_HIGH_PATTERN,
        "T5_consec_up": fc.T5_CONSEC_UP_PATTERN,
    }
    for key, frozen_value in expected.items():
        upstream_value = eval(up[key], dict(ns))
        assert frozen_value == upstream_value, (
            "%s 불일치 — 손으로 옮겨 적었는가?\n  frozen  : %r\n  %s: %r"
            % (key, frozen_value, upstream, upstream_value))


def test_priority_order_matches_upstream():
    """`PRI` 순서 = `RX` 삽입 순서. 바꾸면 단일배정 민감도 결과가 조용히 바뀐다."""
    text = (TASSO / "power/step1_freeze_and_data.py").read_text(encoding="utf-8")
    order = re.findall(r'\("(T\d_[a-z_]+)",\s*re\.compile', text)
    fc = _load_frozen_module()
    assert [k for k, _ in fc.TYPE_PATTERNS_IN_PRIORITY_ORDER] == order


# ===========================================================================
# 검사 6 — `N` 파서를 «데이터로» 동결한다
# ===========================================================================

def test_n_lookback_parser_reproduces_prereg_counts():
    """🔴 C6 누락 ② — 파서가 §2.3-(f) 의 276/52 를 **실제로 재현**하는가.

    원본 파서는 세션 스크래치패드(OS 임시 트리)에만 있었고 저장소에 없었다.
    ⇒ 정규식 텍스트만 옮기면 「옮겨 적었을 뿐」이므로, **`labels_v4.csv` 에 돌려
      수치를 재현**하는 것으로 동결한다. 이건 표기 대조가 아니라 동작 대조다.

    ⚠️ 우선순위 단일배정(`priority_single`) 기준이다 — 주 판정의 교집합 배정으로는
       이 수치가 그대로 성립하지 않는다. `frozen_constants.py` 의 경고 참조.
    """
    fc = _load_frozen_module()
    exp = fc.N_LOOKBACK_PARSE_EXPECTED
    assert exp["assignment"] == fc.N_LOOKBACK_PARSER_SCOPE_ASSIGNMENT == "priority_single"

    rx = [(k, re.compile(p)) for k, p in fc.TYPE_PATTERNS_IN_PRIORITY_ORDER]
    np_rx = re.compile(fc.N_LOOKBACK_PARSER_PATTERN)

    csv_path = TASSO / "labels_v4.csv"
    assert csv_path.exists(), "labels_v4.csv 가 없다 — 재현 불가"
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.DictReader(fh)
                if r["regime"] == "검색기단타" and r["usable"] == "True"]

    n_rows = success = failure = long_term = 0
    counts = {}
    for r in rows:
        method = r["method"] or ""
        assigned = next((k for k, r_ in rx if r_.search(method)), None)
        if assigned not in fc.N_LOOKBACK_PARSER_SCOPE:
            continue
        n_rows += 1
        m = np_rx.search(method)
        if m:
            success += 1
            counts[int(m.group(1))] = counts.get(int(m.group(1)), 0) + 1
        else:
            failure += 1
            if "장기" in method:
                long_term += 1

    assert n_rows == exp["rows_t3_t4"], "T3/T4 행수 %d != %d" % (n_rows, exp["rows_t3_t4"])
    assert success == exp["success"], "파싱 성공 %d != %d" % (success, exp["success"])
    assert failure == exp["failure"], "파싱 실패 %d != %d" % (failure, exp["failure"])
    assert counts == exp["value_counts"], "N 분포 불일치: %s != %s" % (counts, exp["value_counts"])
    assert long_term == exp["failure_with_장기"], (
        "「장기」 표기 %d != %d" % (long_term, exp["failure_with_장기"]))

    # 🔴 재현이 «성립했으므로» 플래그는 True 여야 한다 — 여기가 그 결속의 자리다.
    _assert_n_parser_state(fc)


# ===========================================================================
# 검사 7 — 계약: 순수 데이터 모듈
# ===========================================================================

def test_frozen_module_is_pure_data():
    """모듈 레벨 `UPPER_SNAKE_CASE` 상수만. 함수·클래스·import·실행 코드 금지.

    🔑 해시 대상 안에 실행 가능한 자유도가 있으면 「해시가 같다」가
       「거동이 같다」를 함의하지 않게 된다.
    """
    tree = ast.parse(FROZEN.read_text(encoding="utf-8"))
    problems = []
    for i, node in enumerate(tree.body):
        if i == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            continue                                    # 모듈 독스트링
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if not (isinstance(t, ast.Name) and _UPPER_SNAKE.match(t.id)):
                    problems.append("%d행: UPPER_SNAKE 아닌 대입" % node.lineno)
            continue
        problems.append("%d행: %s — 순수 데이터 모듈에 허용되지 않는 구문"
                        % (node.lineno, type(node).__name__))
    assert not problems, "\n".join(problems)


def _assert_match_r4_state(fc):
    """R4 충족 여부 ↔ 매칭 축 구성. 🔴 **양방향이다.**

    ⚠️ 이전 판본은 `if not fc.MATCH_R4_SATISFIED:` **하나뿐**이었다. 그래서
       플래그를 True 로 바꾸면 **검사가 실패하는 게 아니라 검사할 것이 없어졌다**
       (관리자 실측: `MATCH_R4_SATISFIED = True` → 전건 통과).
    🔑 ***`if not FLAG:` 가드는 플래그를 True 로 만드는 변경에 대해 원리적으로 무력하다*** —
       그 변경이 가드의 «조건» 을 끄기 때문이다. ⇒ True 쪽에도 검사할 것을 둔다.
    """
    if not fc.MATCH_R4_SATISFIED:
        assert "log_market_cap" not in fc.MATCH_AXES, (
            "R4(외부 시총 시계열) 미충족인데 시총이 주 매칭 축에 있다 — "
            "처치군 82.51% 에서 셀을 만들 수 없고, 되는 구간(2024-03-13~)만 남으면 "
            "생존편향이 가장 약한 연도로 표본이 쏠려 결과가 계통적으로 낙관된다")
    else:
        assert "log_market_cap" in fc.MATCH_AXES, (
            "MATCH_R4_SATISFIED = True 인데 주 매칭 축 %r 에 시총이 없다.\n"
            "🔴 R4 충족의 «의미» 는 2축 매칭이 가능해졌다는 것이다(§4.3 · MATCH_AXES_"
            "R4_SENSITIVITY). 플래그만 뒤집으면 「조건이 풀렸다고 선언했는데 아무것도 "
            "안 바뀐」 상태가 되고, 그 상태는 산출물에 흔적을 남기지 않는다."
            % (fc.MATCH_AXES,))


# --- §3.3 거래세율 표 — `COST_SOURCE_VERIFIED` 의 «구조» 대조 ------------------
#
# 🔴 관리자 실측: `COST_SOURCE_VERIFIED = True` 를 박아도 전건 통과했고, 그때
#    §3.3 표는 `⟨____⟩` 로 **비어 있는 채였다.** 「확인됐다」는 선언과 「표가 비어 있다」는
#    사실이 공존해도 아무 검사가 없었다는 뜻이다.
# 🔑 문구 대조(위 두 표)에 더해 **표 자체를 파싱해** 빈칸 유무를 본다 — 문구는 옮겨
#    적힐 수 있지만 표의 빈칸은 값이 채워져야만 사라진다.
_COST_TABLE_RE = re.compile(r"####[^\n]*거래세율 표[^\n]*\n\n((?:\|[^\n]*\n)+)")
_COST_PLACEHOLDER = "⟨____⟩"


def _cost_rate_table(text: str) -> str:
    m = _COST_TABLE_RE.search(text)
    assert m, (
        "§3.3 거래세율 표를 못 찾았다 — 문서 구조가 바뀌었다. 이 검사가 vacuous 해졌으므로 "
        "추출 패턴을 갱신할 것 (표가 없어진 것이라면 0-d 절차 자체를 다시 볼 것)")
    return m.group(1)


def _assert_cost_source_state(fc, text):
    """🔴 `COST_SOURCE_VERIFIED` ↔ §3.3 거래세율 표의 «빈칸». 양방향."""
    table = _cost_rate_table(text)
    n_blank = table.count(_COST_PLACEHOLDER)
    if fc.COST_SOURCE_VERIFIED:
        assert n_blank == 0, (
            "🔴 COST_SOURCE_VERIFIED = True 인데 §3.3 거래세율 표에 빈칸(%s)이 %d개 "
            "남아 있다.\n"
            "   이 플래그는 «동결을 여는 스위치»(§0-d)이고, **절대 판정의 통과선이 이 표 "
            "위에 선다.**\n"
            "   확정 절차: 기획재정부/한국거래소 고시를 원출처로 확인하고 코스피·코스닥 "
            "구분과 적용 시점까지 확인해 표를 «채운 뒤» 플래그를 올릴 것."
            % (_COST_PLACEHOLDER, n_blank))
    else:
        assert n_blank > 0, (
            "🔴 COST_SOURCE_VERIFIED = False 인데 §3.3 거래세율 표에 빈칸이 없다 — "
            "표는 채워졌는데 플래그가 안 올라갔거나, 표가 «확인 없이» 채워졌다. "
            "둘 다 0-d 절차 위반이다.")


def _assert_n_parser_state(fc):
    """🔴 `N_LOOKBACK_PARSER_RESOLVED` ↔ 파서 재현의 성립.

    🔑 이 스위트는 매 실행마다 `labels_v4.csv` 로 276/52 를 **실제로 재현**한다
       (`test_n_lookback_parser_reproduces_prereg_counts`). 재현이 성립하는데
       플래그가 False 면 그것은 상태 기술이 아니라 **모순**이다.
    """
    assert fc.N_LOOKBACK_PARSER_RESOLVED, (
        "🔴 N_LOOKBACK_PARSER_RESOLVED = False 인데 파서 재현(276/52)은 성립한다 — "
        "「파서가 없다」와 「파서가 수치를 재현한다」가 공존할 수 없다.\n"
        "   플래그를 내리려면 재현이 «실제로» 깨져야 하고, 그때는 재현 테스트가 먼저 FAIL 한다.")


def test_matching_axis_invariants():
    """🔴 3판 C1 교정(매칭 축 = 거래대금 단독)을 못 박는다.

    🔑 **이 테스트가 왜 생겼는지가 요점이다.** C1 교정으로 `MATCH_AXES`·
       `MATCH_CELL_EXPANSION_AXIS`·arm 이름이 전부 뒤집혔는데 **기존 70개 테스트 중
       하나도 깨지지 않았다.** 즉 그 시점의 스위트는 2판 2축 설계로 조용히 되돌려도
       통과했다 — 축은 결과를 바꾸는 설계인데 단언이 없었다.
       (열거식이 빠뜨린다는 이 파일의 주제가 «테스트 목록» 에서도 반복된 것이다.)
    """
    fc = _load_frozen_module()

    # ① 주 매칭 축은 거래대금 «단독». 2판의 2축 25셀로 되돌아가면 실패한다.
    assert fc.MATCH_AXES == ("log_trading_value",), (
        "주 매칭 축이 바뀌었다: %r — 2판(시총+거래대금 2축)으로 되돌린 것이라면 "
        "frozen_constants.py §4 의 커버율 곡선(처치군 82.51% 결측)을 먼저 읽을 것"
        % (fc.MATCH_AXES,))

    # ② 확장 축은 «활성 축 중 하나» 여야 한다. 축을 뒤집으면서 확장 축을 안 뒤집는
    #    부분 교정을 막는다 — 2판은 「시총 축으로만 확장」이었다.
    assert fc.MATCH_CELL_EXPANSION_AXIS in fc.MATCH_AXES, (
        "셀 확장 축 %r 이 활성 매칭 축 %r 밖이다 — 존재하지 않는 축으로 확장하게 된다"
        % (fc.MATCH_CELL_EXPANSION_AXIS, fc.MATCH_AXES))

    # ③ R4 충족 여부 ↔ 축 구성. **양방향**이다 (`_assert_match_r4_state` 참조).
    _assert_match_r4_state(fc)

    # ④ 조건부 민감도 축은 2축이며 주 축을 포함해야 한다(같은 격자 위에서 비교 가능하게).
    assert set(fc.MATCH_AXES) <= set(fc.MATCH_AXES_R4_SENSITIVITY)
    assert "log_market_cap" in fc.MATCH_AXES_R4_SENSITIVITY


def test_arm_seed_offsets_are_stable_across_rename():
    """🔑 arm 개명이 시드 좌표를 흔들지 않았는가.

    `C-B-matched` → `C-B-matched-TV` 개명 시 arm 의 «슬롯»을 유지했다.
    이름은 설계 기술이고 오프셋은 난수 좌표다 — 개명만으로 추출 결과가 바뀌면
    「같은 설계인데 다른 대조군」이 되고, 그 사실은 산출물에 흔적을 안 남긴다.

    🔧 **2026-08-04: 간격이 1,000 → 10,000,000 으로 벌어졌다**(🔴-B 교정).
       ⚠️ 지키려던 것은 **슬롯 순서**이지 리터럴 1,000 이 아니다 — 슬롯은 그대로다
       (raw 0 · matched-TV 1 · C-A 2 · shuffle 3). 간격 자체의 요건은
       `test_arm_seed_streams_do_not_overlap` 이 도달집합으로 단언한다.
    """
    fc = _load_frozen_module()
    assert fc.ARM_SEED_OFFSETS["C-B-raw"] == 0

    # 🔑 슬롯 순서 — 개명·간격 조정 어느 쪽으로도 흔들리면 안 되는 것.
    slots = [a for a, _ in sorted(fc.ARM_SEED_OFFSETS.items(), key=lambda kv: kv[1])]
    assert slots == ["C-B-raw", "C-B-matched-TV", "C-A", "gate_A_null_shuffle"], (
        "arm 슬롯 순서가 바뀌었다: %s — 개명 시 «유지»하기로 한 것이 이 순서다" % slots)
    assert fc.ARM_SEED_OFFSETS["C-B-matched-TV"] == 10_000_000, (
        "교정 arm 의 시드 오프셋이 10,000,000 에서 벗어났다 — 간격 근거는 "
        "frozen_constants.py 의 ARM_SEED_OFFSETS 주석(파생 폭의 100배 여유)")
    assert "C-B-matched" not in fc.ARM_SEED_OFFSETS, (
        "구 arm 이름이 남아 있다 — 두 이름이 공존하면 어느 쪽이 도는지 알 수 없다")
    # 오프셋이 서로 다른가. 🔴 **구간이 겹치지 않는가는 여기서 보지 않는다** —
    #    `test_arm_seed_streams_do_not_overlap` 이 «도달집합»으로 본다. 아래 참조.
    offs = sorted(fc.ARM_SEED_OFFSETS.values())
    assert len(set(offs)) == len(offs), "arm 오프셋 중복 — 두 arm 이 같은 난수열을 쓴다"


# ---------------------------------------------------------------------------
# 🔴 arm 시드 «도달집합» 분리 — 간격이 아니라 집합으로 본다
# ---------------------------------------------------------------------------
#
# 🔴 **이 절이 왜 생겼는가 — 테스트가 「주석이 주장한 불변식」을 검사하지 않았다.**
#
# `frozen_constants.py` 의 오프셋 표 주석은 *"간격(1000)은 파생 폭보다 크게 잡아
# arm 사이의 시드 구간이 겹치지 않게 한 값"* 이라고 적었다. **거짓이었다.**
# 파생 폭은 `ARM_SEED_K_MULTIPLIER(31) × max(k)(20) + max(rep) = 1,619` 인데
# 간격은 1,000 이라 **인접 arm 쌍마다 589개 시드가 충돌**했다.
# ⚠️ **589 이지 590 이 아니다** — 590 은 `rep ∈ [0, 1000]`(1,001개)으로 셌을 때의 값이고,
#    현행 «선언된» 정의역은 `[ARM_SEED_REP_BASE, ARM_SEED_MAX_REP] = [0, 999]`(1,000개
#    = `GATE_A_SHUFFLE_REPS`)다. 🔑 ***정의역이 선언돼 있지 않으면 결함의 크기조차
#    사람마다 다르게 나온다*** — 그 1건 차이가 근본원인의 작은 증거다
#    (`frozen_constants.py` 의 `ARM_SEED_K_VALUES` 위 주석과 같은 문장이어야 한다).
#
# 그리고 `test_arm_seed_offsets_are_stable_across_rename` 은 **`min(gap) >= 1000`**,
# 즉 **간격이 「어떤 상수」 이상인가**만 단언했다. 주석이 주장한 명제는
# **「도달집합이 서로소인가」**였는데 테스트는 **그 명제를 한 번도 안 물었다.**
#
# 🔑 ***불변식을 주석에 적었으면 테스트는 그 문장 그대로를 단언해야 한다.***
#    「간격 ≥ 상수」는 불변식의 **대리 지표**이고, 대리 지표는 상수가 틀리면
#    같이 틀린다 — 여기서는 **파생 폭이 상수로 존재하지 않아** 대리 지표의
#    문턱(1000)이 **아무것과도 대조되지 않는 숫자**였다.
#
# 🔴 가장 나쁜 쌍은 **`C-A × gate_A_null_shuffle`** 이었다 — 귀무 실측 팔이 추정 팔과
#    같은 난수열을 쓸 수 있고, `frozen_constants.py:136-137` 이 스스로 적어 둔 대로
#    **그 사실은 산출물에 흔적을 남기지 않는다.**


def _arm_reachable_seeds(fc, arm: str) -> set:
    """arm 이 «실제로 도달할 수 있는» 시드 전부.

    `ARM_SEED_DERIVATION_RULE` 을 정의역(`ARM_SEED_K_VALUES` × `[REP_BASE, MAX_REP]`)
    전체에 대해 전개한 집합이다. 🔴 정의역이 상수로 없으면 이 집합을 만들 수 없고,
    만들 수 없으면 「겹치는가」를 물을 수 없다 — 그것이 이 결함의 근본원인이었다.
    """
    base = fc.ARM_BASE_SEEDS[arm]
    return {
        base + fc.ARM_SEED_K_MULTIPLIER * k + rep
        for k in fc.ARM_SEED_K_VALUES
        for rep in range(fc.ARM_SEED_REP_BASE, fc.ARM_SEED_MAX_REP + 1)
    }


def test_arm_seed_domain_is_declared():
    """🔴 `(k, rep)` 의 정의역이 상수로 선언돼 있는가 — 도달집합 계산의 전제.

    ⚠️ **`rep` 의 기점과 「비셔플 arm 이 rep 을 쓰는가」까지 선언해야 한다.**
       재검증자가 *"해석 A/B 중 B 를 고르면 충돌이 실제로 발생하고 흔적이 안 남는다"*
       고 지적한 자리이며, 미선언이면 **읽는 사람마다 다른 도달집합**을 계산한다.
    """
    fc = _load_frozen_module()
    assert fc.ARM_SEED_K_VALUES == (1, 5, 20), (
        "청산 창 k 의 정의역이 바뀌었다: %r" % (fc.ARM_SEED_K_VALUES,))
    assert tuple(sorted({fc.PRIMARY_K, *fc.SECONDARY_K_FAMILY})) \
        == tuple(sorted(fc.ARM_SEED_K_VALUES)), (
        "시드 정의역의 k 가 판정 k 가족과 갈라졌다: %r ↔ %r"
        % (fc.ARM_SEED_K_VALUES, (fc.PRIMARY_K, fc.SECONDARY_K_FAMILY)))

    # 🔴 기점(0-base) — 1-base 로 읽으면 도달집합이 한 칸 밀린다.
    assert fc.ARM_SEED_REP_BASE == 0, "rep 기점이 0-base 가 아니다"
    n_reps = fc.ARM_SEED_MAX_REP - fc.ARM_SEED_REP_BASE + 1
    assert n_reps == fc.GATE_A_SHUFFLE_REPS, (
        "rep 스트림 수 %d 가 GATE_A_SHUFFLE_REPS(%d) 와 다르다 — 셔플 반복 하나가 "
        "시드를 못 받거나 남는다" % (n_reps, fc.GATE_A_SHUFFLE_REPS))

    # 🔴 비셔플 arm 의 rep 사용 여부 — 「넓은 쪽」으로만 선언 가능하게 한다.
    assert fc.ARM_SEED_REP_SCOPE == "all_arms", (
        "rep 적용 범위가 %r 다 — 좁게 선언하면 나중에 부트스트랩·재추출이 붙는 순간 "
        "도달집합이 조용히 넓어지고, 그 사실은 산출물에 흔적을 안 남긴다"
        % (fc.ARM_SEED_REP_SCOPE,))

    # 🔴 k 보폭이 rep 폭 «이상» 이어야 `(k, rep) ↦ 시드` 가 단사다.
    #    실측(2026-08-04): 보폭 31 · rep 폭 1,000 이던 판본은 arm 하나의 도달집합이
    #    3,000 이 아니라 **1,589** 였다 — 청산 창이 다른 두 검정이 같은 난수열을 돌았다.
    assert fc.ARM_SEED_K_MULTIPLIER == n_reps, (
        "ARM_SEED_K_MULTIPLIER(%d) 가 rep 스트림 수(%d) 와 다르다 — 작으면 arm 내부에서 "
        "시드가 겹치고, 크면 k 블록 사이에 «도달 불가» 구간이 생겨 파생 폭만 늘어난다"
        % (fc.ARM_SEED_K_MULTIPLIER, n_reps))

    # 🔴 🔴-2 — `k` 의 «적용 범위» 도 선언돼 있어야 한다. `rep` 과 «같은» 처방이다.
    #    미선언이면 §4.1-4 서술(추출 1회)과 파생 규칙(k 별 분기)이 **둘 다 성립**하고,
    #    (A) k 무관 단일 추출 / (B) k 마다 재추출 은 **결과가 갈린다** — §8 max-t 가
    #    짝 자료인지 여부까지 바뀐다.
    assert fc.ARM_SEED_K_SCOPE == "shuffle_and_bootstrap_only", (
        "k 적용 범위가 %r 다 — 대조군 추출을 k 마다 재추출하면 k 사이 Δ 차이에 "
        "재추출 잡음이 섞이고, §8 의 max-t 가 짝 자료가 아니게 된다"
        % (fc.ARM_SEED_K_SCOPE,))

    # 파생 규칙 문자열이 정의역·적용 범위를 이름으로 부르는가 (규칙과 선언이 갈라지지 않게).
    rule = fc.ARM_SEED_DERIVATION_RULE
    for name in ("ARM_SEED_K_VALUES", "ARM_SEED_REP_BASE", "ARM_SEED_MAX_REP",
                 "ARM_SEED_K_SCOPE"):
        assert name in rule, (
            "파생 규칙이 정의역 상수 %s 를 안 부른다: %r" % (name, rule))


def test_arm_seed_streams_do_not_overlap():
    """🔴 **arm 쌍 도달집합의 교집합이 전부 공집합인가.**

    🔑 이것이 오프셋 표 주석이 «주장»한 불변식 그 자체다. 이전 판본은
       `min(gap) >= 1000` 이라는 **대리 지표**만 단언했고, 실제 도달집합은
       인접 쌍마다 **589개씩 겹쳐 있었다** (현행 정의역 `rep ∈ [0, 999]` 기준.
       `[0, 1000]` 으로 세면 590 이며, 그 1건 차이 자체가 「정의역 미선언」의 증거다).
    """
    fc = _load_frozen_module()
    arms = sorted(fc.ARM_BASE_SEEDS)
    reach = {a: _arm_reachable_seeds(fc, a) for a in arms}
    width = fc.ARM_SEED_K_MULTIPLIER * max(fc.ARM_SEED_K_VALUES) + fc.ARM_SEED_MAX_REP
    offs = sorted(fc.ARM_SEED_OFFSETS.values())
    min_gap = min(b - a for a, b in zip(offs, offs[1:]))
    expected_size = len(fc.ARM_SEED_K_VALUES) * (
        fc.ARM_SEED_MAX_REP - fc.ARM_SEED_REP_BASE + 1)

    # 🔑 **문제를 전부 모아 한 번에 보고한다.** 앞선 단언이 뒤 단언을 가로막으면
    #    「고쳤더니 새 실패가 나온다」가 반복되고, 무엇보다 **arm «내부» 충돌 때문에
    #    arm «사이» 충돌이 화면에 안 나오는** 일이 생긴다 — 실제로 그랬다.
    problems = []

    # ① 비-공허 + arm «내부» 단사성 — 도달집합이 정의역 크기와 같아야 한다.
    #    🔴 실측(2026-08-04): `ARM_SEED_K_MULTIPLIER = 31` 이던 판본에서 3,000 이 아니라
    #       **1,589** 였다 = 청산 창이 다른 두 검정이 같은 난수열을 돌고 있었다.
    for a in arms:
        if len(reach[a]) != expected_size:
            problems.append(
                "  [arm 내부] %-22s 도달집합 %d != %d — (k, rep) ↦ 시드가 단사가 아니다. "
                "ARM_SEED_K_MULTIPLIER(%d) 가 rep 폭(%d) 이하다"
                % (a, len(reach[a]), expected_size, fc.ARM_SEED_K_MULTIPLIER,
                   fc.ARM_SEED_MAX_REP - fc.ARM_SEED_REP_BASE + 1))

    # ② 🔴 주 단언 — arm «쌍» 도달집합의 교집합.
    for i, a in enumerate(arms):
        for b in arms[i + 1:]:
            inter = reach[a] & reach[b]
            if inter:
                problems.append(
                    "  [arm 쌍]   %-22s × %-22s : %d개 충돌 (최소 예 %d)"
                    % (a, b, len(inter), min(inter)))

    # ③ 부수 단언 — 간격이 파생 폭을 «넘는가». 도달집합 검사의 필요조건이며,
    #    이것만으로는 불충분하다는 것이 이 절의 요점이다. 둘 다 둔다.
    if min_gap <= width:
        problems.append(
            "  [간격]     오프셋 최소 간격 %d 이 파생 폭 %d 이하다" % (min_gap, width))
    elif min_gap < 100 * width:
        # 🔑 여유 배수를 못 박는다. 값이 아니라 «여유»가 요건이다 —
        #    정의역이 조금만 늘어도(k 추가·rep 증가) 다시 겹치기 때문이다.
        problems.append(
            "  [여유]     오프셋 간격 %d 이 파생 폭 %d 의 100배(%d) 미만이다"
            % (min_gap, width, 100 * width))

    assert not problems, (
        "🔴 arm 시드 도달집합이 분리돼 있지 않다 — 두 검정이 «같은 난수열»을 쓸 수 있고,\n"
        "   그 사실은 산출물에 흔적을 남기지 않는다 (frozen_constants.py:136-137).\n"
        "   특히 `C-A × gate_A_null_shuffle` 이 겹치면 귀무 실측 팔이 추정 팔과\n"
        "   같은 스트림을 돈다.\n"
        "   교정 ①: ARM_SEED_K_MULTIPLIER ≥ rep 스트림 수 (arm 내부 단사성)\n"
        "   교정 ②: ARM_SEED_OFFSETS 간격 ≥ 100 × (K_MULTIPLIER×max(k) + MAX_REP)\n"
        "   ── 실측 ──\n" + "\n".join(problems))


def test_arm_base_seeds_are_explicit_constants():
    """🔴 §6-C 계약 — arm 기저 시드는 **명시적 상수**이고 산술로 유도하지 않는다.

    🔑 **왜 이 단언이 생겼는가.** §6-C 계약은 *"난수 시드 (arm 별로 명시적 상수)"* 를
       요구하는데, 상수 파일은 `MASTER_SEED + ARM_SEED_OFFSETS[arm] + ...` 라는
       **파생 규칙 하나만** 갖고 있었다. 문서와 상수가 정면으로 모순이었고,
       문서가 이름으로 부르던 `SEED_CB`·`SEED_CA`·`SEED_SHUFFLE` 은 **존재하지 않았다.**

    ⇒ 교정 후 구조: **기저는 명시 상수 · `(k, rep)` 스트림만 명시된 규칙으로 파생.**
       여기서는 그 구조가 유지되는지와, 오프셋 표와 기저 시드가 **갈라지지 않았는지**를 본다.
    """
    fc = _load_frozen_module()

    # ① 문서가 이름으로 부르는 네 개가 모듈 레벨 «상수» 로 실재하는가.
    for name in ("SEED_CB", "SEED_CB_MATCHED_TV", "SEED_CA", "SEED_SHUFFLE"):
        assert hasattr(fc, name), "%s 가 없다 — 문서(§4.1·§4.3·§6-A)가 이름으로 부른다" % name
        assert isinstance(getattr(fc, name), int), "%s 는 정수 상수여야 한다" % name

    # ② arm 표가 그 상수들을 그대로 쓰는가 (본실행이 읽는 것은 이 표다).
    assert fc.ARM_BASE_SEEDS == {
        "C-B-raw": fc.SEED_CB,
        "C-B-matched-TV": fc.SEED_CB_MATCHED_TV,
        "C-A": fc.SEED_CA,
        "gate_A_null_shuffle": fc.SEED_SHUFFLE,
    }, "ARM_BASE_SEEDS 가 명시 시드 상수와 갈라졌다: %r" % (fc.ARM_BASE_SEEDS,)

    # ③ 🔑 오프셋 표와의 항등식 — 시드 «체계» 가 흔들리지 않았는가.
    #    (오프셋 표는 배치 기록으로만 남기지만, 두 표가 갈라지면 어느 쪽이 도는지 모른다.)
    for arm, base in fc.ARM_BASE_SEEDS.items():
        assert base == fc.MASTER_SEED + fc.ARM_SEED_OFFSETS[arm], (
            "%s: 기저 시드 %d != MASTER_SEED + 오프셋 %d — 두 표가 갈라졌다"
            % (arm, base, fc.MASTER_SEED + fc.ARM_SEED_OFFSETS[arm]))
    assert set(fc.ARM_BASE_SEEDS) == set(fc.ARM_SEED_OFFSETS), (
        "arm 집합이 두 표에서 다르다: %s ↔ %s"
        % (sorted(fc.ARM_BASE_SEEDS), sorted(fc.ARM_SEED_OFFSETS)))
    assert len(set(fc.ARM_BASE_SEEDS.values())) == len(fc.ARM_BASE_SEEDS), (
        "두 arm 이 같은 기저 시드를 쓴다 — 같은 난수열이 돈다")

    # ④ 파생 규칙의 «기점» 이 명시 상수 표인가. (MASTER_SEED 기점으로 되돌아가면 실패)
    rule = fc.ARM_SEED_DERIVATION_RULE
    assert "ARM_BASE_SEEDS[arm]" in rule, (
        "파생 규칙의 기점이 명시 상수 표가 아니다: %r\n"
        "§6-C 계약(«arm 별로 명시적 상수»)과 모순된다." % rule)
    # ⚠️ 이전 판본은 `rule.replace(" ", " ")` 였다 — **양쪽이 같은 U+0020 이라 no-op**.
    #    「전각·비분리 공백을 정규화한다」는 의도였다면 그 의도가 코드에 도달하지 않았다.
    assert "MASTER_SEED +" not in re.sub(r"\s+", " ", rule), (
        "파생 규칙이 MASTER_SEED 산술로 되돌아갔다: %r" % rule)


def test_gate_b_scale_invariants():
    """🔴 D-19 — 게이트 B ⑥ 의 문턱은 **로그차**이고, 2판의 「비」 해석은 폐기다.

    🔑 **이 테스트가 왜 생겼는지가 요점이다** (`test_matching_axis_invariants` 와 같은 사고).
       C7 교정으로 문턱의 **척도**가 바뀌었는데 **기존 71개 테스트 중 하나도 깨지지 않았다.**
       그 시점의 스위트는 상수 파일이 **C7 이전 형태(`(0.90, 1.10)`)** 를 들고 있어도
       통과했다 — 척도는 판정을 뒤집는 설계인데 단언이 없었다.
    """
    import math
    fc = _load_frozen_module()

    # ① 문턱은 로그차 하나. 2판의 「비 구간」 상수는 되살아나면 안 된다.
    assert not hasattr(fc, "GATE_B_MEDIAN_RATIO_RANGE"), (
        "2판의 `GATE_B_MEDIAN_RATIO_RANGE` 가 되살아났다 — D-19 가 폐기한 형태다.\n"
        "척도가 안 적혀 있어 `med(log tv)` 비에 적용될 수 있고, 그 해석은 실측상 "
        "판별력 0(6개 격자 전부 통과, 유동성 9.14배도 통과)이다.")
    assert hasattr(fc, "GATE_B_LOG_DIFF_MAX"), "로그차 문턱 상수가 없다 (D-19)"

    # ② 값이 정확히 ln(1.10) 인가. 🔴 손으로 옮겨 적으면 조용히 다른 것을 검사한다(§13.2-1).
    assert fc.GATE_B_LOG_DIFF_MAX == math.log(1.10), (
        "로그차 문턱이 ln(1.10) 과 다르다: %.17g != %.17g"
        % (fc.GATE_B_LOG_DIFF_MAX, math.log(1.10)))

    # ③ 🔑 허용 «배수» 병기 규약(D-19)의 실체 — 원척도 구간이 1/1.10 ~ 1.10 인가.
    #    2판 상수의 하한은 0.90 이었고, 그것은 1/1.10 = 0.909091 이 아니다.
    lo, hi = math.exp(-fc.GATE_B_LOG_DIFF_MAX), math.exp(fc.GATE_B_LOG_DIFF_MAX)
    assert abs(lo - 1 / 1.10) < 1e-12 and abs(hi - 1.10) < 1e-12, (
        "허용 배수가 0.909091~1.100000 이 아니다: %.6f ~ %.6f" % (lo, hi))
    assert abs(lo - 0.90) > 1e-3, (
        "허용 배수 하한이 2판의 0.90 으로 되돌아갔다 — 비 0.905 인 설계가 "
        "상수로는 통과하고 D-19 로그차로는 차단되는 갈라짐이 다시 생긴다")

    # ④ 비대칭이 아닌가 (로그차는 척도불변·대칭이어야 한다).
    assert abs(math.log(hi) + math.log(lo)) < 1e-12


def test_gate_a_threshold_invariants():
    """🔴 D-16 — 게이트 A 의 통과 기준은 `|평균 Δ_null| ≤ 0.05%p` **단독**이다.

    ⚠️ C2-b 가 드러낸 것: `평균|Δ|`(산포)와 `|평균 Δ|`(중심)는 **표기가 거의 같고 뜻이
       정반대**다. 산포로 읽으면 귀무 세계에서 문턱의 **5~6배**가 나와 깨끗한 FAIL 을
       보고할 수 없다. 상수는 «중심» 검사의 문턱이며, 그 크기가 귀무 SD 대비
       4~5σ 여유라는 것이 D-16 의 근거다.
    """
    fc = _load_frozen_module()
    assert fc.GATE_A_NULL_DELTA_MAX == 0.0005, (
        "게이트 A 문턱이 0.05%%p(=0.0005) 에서 벗어났다: %r" % fc.GATE_A_NULL_DELTA_MAX)
    assert fc.GATE_A_SHUFFLE_REPS == 1000, (
        "셔플 반복 수가 1,000 에서 벗어났다 — 귀무 하 mean Δ_null 의 SD 가 "
        "SE/√B 이므로 B 를 줄이면 문턱 0.05%p 의 σ 여유(4~5σ)가 함께 줄어든다")
    # 🔑 C2 교정의 실체 — 게이트 A 는 «관측 Δ 를 쓰는» 어떤 상수도 갖지 않는다.
    observed = [n for n in dir(fc) if n.startswith("GATE_A_") and "OBS" in n]
    assert not observed, (
        "게이트 A 에 관측 Δ 관련 상수가 생겼다: %s — C2 가 삭제한 조건("
        "「셔플 95분위 < 관측 Δ」)이 되돌아온 것이라면 §12.2-7 보고 항목으로 되돌릴 것"
        % observed)


def _assert_d12_state(fc):
    """D-12 해소 여부 ↔ 매칭 방식·ε 의 상태."""
    if not fc.D12_RESOLVED:
        assert fc.MATCH_METHOD is None, (
            "D-12 가 안 닫혔는데 매칭 방식이 %r 로 채워져 있다 — §13.2-6: "
            "기본값 대입은 「채워졌다」가 아니라 「틀린 것으로 채워졌다」일 수 있다"
            % (fc.MATCH_METHOD,))
        assert fc.MATCH_CALIPER_EPS is None, (
            "D-12 가 안 닫혔는데 ε 가 %r 로 채워져 있다 — §4.1-(g-2) 는 ε 를 "
            "«실측 후» 확정하라고 못 박았다" % (fc.MATCH_CALIPER_EPS,))
    else:
        assert fc.MATCH_METHOD is not None, (
            "D12_RESOLVED = True 인데 매칭 방식이 None 이다 — 「닫혔다」가 「골랐다」를 "
            "함의하지 않는다. 플래그만 뒤집으면 이 자리가 빈 채로 본실행이 시작된다")
        assert fc.MATCH_METHOD in ("quantile_grid", "caliper"), (
            "알 수 없는 매칭 방식: %r" % (fc.MATCH_METHOD,))
        if fc.MATCH_METHOD == "caliper":
            assert fc.MATCH_CALIPER_EPS is not None, "캘리퍼를 택했는데 ε 가 비어 있다"
            assert fc.MATCH_CALIPER_EPS <= fc.GATE_B_LOG_DIFF_MAX, (
                "ε(%r) 가 게이트 B ⑥ 문턱(%r) 보다 크다 — 매칭이 게이트를 "
                "구성상 만족시키지 못한다"
                % (fc.MATCH_CALIPER_EPS, fc.GATE_B_LOG_DIFF_MAX))


def test_d12_matching_method_is_open():
    """🔴 D-12 — 매칭 «방식» 이 미결이면 그 상태가 상수 파일에 드러나 있어야 한다.

    🔑 **왜 상수 파일에 있어야 하는가.** §12.1 이 *"D-12 가 닫히기 전에는 PASS 조건 ③ 의
       충족 가능성이 미확정"* 이라고 적었는데, 상수 파일에는 **선택자도 미결 표시도 없었다.**
       그러면 실행자는 「격자 5분위(=`MATCH_QUANTILE_BINS`)가 확정된 방식」으로 읽게 되고,
       그 판본은 게이트 B ⑥ 에서 **원척도 비 9.14 로 차단**되어 ③ 이 불성립한다.
       ⇒ 「돌지 않음」과 「효과 없음」을 문서 차원에서 구분하라는 §13.2-14 의 코드판이다.
    """
    fc = _load_frozen_module()
    assert hasattr(fc, "MATCH_METHOD"), "매칭 방식 선택자가 없다 (D-12)"
    assert hasattr(fc, "MATCH_CALIPER_EPS"), "캘리퍼 ε 자리가 없다 (D-12-③)"
    assert hasattr(fc, "D12_RESOLVED") and isinstance(fc.D12_RESOLVED, bool)
    _assert_d12_state(fc)


def test_freeze_blocking_flags_are_declared():
    """🔴 동결 차단 플래그가 조용히 사라지지 않게 못 박는다.

    🔧 **D-12 가 3판 교정에서 추가됐다.** 그 전 목록은 ①② 둘뿐이었고,
       하필 빠진 것이 **C7 이 새로 만든 결정**이었다 — *열거식 가드는 반드시
       빠뜨린다*(§13.2-12)를 규칙으로 세운 판본이 **자기 동결 체크리스트에서**
       같은 짓을 한 것이다(§13.2-17 다섯 번째 사례).
    """
    fc = _load_frozen_module()
    for name in ("COST_SOURCE_VERIFIED", "N_LOOKBACK_PARSER_RESOLVED", "D12_RESOLVED"):
        assert hasattr(fc, name), "%s 가 사라졌다 — 동결 차단 조건이다" % name
        assert isinstance(getattr(fc, name), bool), "%s 는 bool 이어야 한다" % name


def test_cost_source_still_unverified_is_visible():
    """⚠️ `COST_SOURCE_VERIFIED` 가 False 인 동안은 동결 불가(§0-d)임을 드러낸다.

    🔑 값이 True 로 바뀌는 것이 목표이므로 「미확인」 자체로는 실패시키지 않고 xfail 로
       가시화한다. (검정을 차단하는 것은 게이트 C 가 아니라 `PREREG.md` §0-d 절차다.)

    🔴 **단 「가시화」와 「검사」는 다르다.** 이전 판본은 xfail «뿐» 이라, 플래그를 True 로
       박으면 §3.3 표가 `⟨____⟩` 로 비어 있어도 그냥 통과했다 — **동결을 여는 스위치가
       아무 대조 없이 켜졌다.** ⇒ 표 자체를 파싱하는 `_assert_cost_source_state` 를
       **xfail 앞에** 둔다: 상태 대조를 먼저 하고, 그 다음에 가시화한다.
    """
    fc = _load_frozen_module()
    _assert_cost_source_state(fc, _doc_text())
    if not fc.COST_SOURCE_VERIFIED:
        pytest.xfail("PREREG §0-d 미충족 — 연도별 거래세율 원출처 미확인. 동결 불가.")


# ===========================================================================
# 검사 8 — 🔴 문서 ↔ 상수 정합을 «기계가» 검사한다
# ===========================================================================
#
# 🔴 **이 절이 왜 생겼는가 — 근본원인은 개별 오류가 아니라 「두 파일이 갈라지는 것」이다.**
#
# 지난 라운드는 **문서 담당과 상수 담당을 분리**했고, 새 발견(C7)이 **문서 담당에만**
# 전달됐다. 그 결과 **C7 교정이 해시 대상 파일에 한 글자도 도달하지 않았다** —
# `PREREG_v3.md` §12.3 D-19 는 문턱을 로그차로 재선언했는데 `frozen_constants.py` 는
# **C7 이전의 「비 ∈ [0.90,1.10]」을 그대로** 들고 있었고, **71 passed 가 그것을 통과시켰다.**
# 같은 누락이 C1·C4 에서도 한 번 있었다.
#
# ⇒ 🔑 **교정의 산출물은 개별 수정이 아니라 「갈라짐을 기계가 막는 장치」다.**
#    아래 세 검사가 그 장치다:
#      (1) 문서가 부르는 이름은 실재해야 한다        — `frozen_constants.<NAME>` 전수 추출
#      (2) 문서가 선언한 문턱 수치는 상수와 일치해야 한다 — 계약표·게이트 표 파싱 후 대조
#      (3) 양방향 — 기계 대조가 «닿지 않는» 상수를 명시적으로 선언하게 한다(fail-closed)
#
# 🔑 **실측 — 이 검사를 도입한 시점(고치기 «전») 에 돌려 3건을 잡았다:**
#      · `test_doc_referenced_constants_exist`           → SEED_CB · SEED_CA · SEED_SHUFFLE 부재
#      · `test_doc_declared_thresholds_match_constants`  → 게이트 B ⑥ 로그차 문턱 상수 부재
#      · `test_strata_status_matches_doc`                → `year` 층 지위 문서(부수) ↔ 상수(필수 부수 판정)

DOC = TASSO / "PREREG_v3.md"

# 🔴 모듈 레벨 상수는 UPPER_SNAKE 만 허용되므로(test_frozen_module_is_pure_data)
#    이 패턴이 «전수»다. 소문자 속성(`frozen_constants.py` 같은 파일명 표기)은 상수가 아니다.
_DOC_FROZEN_REF = re.compile(r"frozen_constants\.([A-Z][A-Z0-9_]*)")


def _doc_text() -> str:
    return DOC.read_text(encoding="utf-8")


def _contract_block(text: str) -> str:
    """§6-C 의 `frozen_constants.py` 계약 코드블록."""
    m = re.search(r"####\s+`frozen_constants\.py`\s+계약.*?\n```\n(.*?)\n```", text, re.S)
    assert m, "§6-C 의 `frozen_constants.py` 계약 블록을 못 찾았다 — 문서 구조가 바뀌었다"
    return m.group(1)


def test_doc_referenced_constants_exist():
    """🔴 (1) 문서가 `frozen_constants.<NAME>` 으로 부르는 이름이 실재하는가.

    🔑 문서가 실행 절차 안에서 상수를 이름으로 지목하면(예: *"시드 = frozen_constants.SEED_CB"*),
       그 이름은 **실행 가능한 참조**다. 실재하지 않으면 실행자는 그 자리를 **자기 판단으로**
       채우게 되고, 그것이 동결의 구멍이다.
    """
    text = _doc_text()
    names = sorted(set(_DOC_FROZEN_REF.findall(text)))
    assert names, (
        "문서에서 `frozen_constants.<NAME>` 참조를 하나도 못 찾았다 — "
        "추출 정규식이 깨졌고 이 검사가 vacuous 해졌다")
    fc = _load_frozen_module()
    missing = [n for n in names if not hasattr(fc, n)]
    assert not missing, (
        "문서가 부르는 상수가 frozen_constants.py 에 없다: %s\n"
        "  (문서가 참조하는 전체: %s)\n"
        "문서와 상수 파일이 갈라졌다 — 이것이 C7 교정이 해시 대상에 도달하지 못한 경로다."
        % (missing, names))


# --- (2) 문서가 선언한 문턱 수치 ↔ 상수 --------------------------------------
#
# 각 항목: (라벨, 어디서 뽑나, 정규식, 문서값 변환, 상수 이름, 상수값 변환, 허용오차)
#   scope "contract" = §6-C 계약 블록 / "doc" = 문서 전체
_THRESHOLD_CHECKS = (
    ("C-A 풀 문턱", "contract", r"C-A\s*(\d+)", float,
     "CA_POOL_MIN_STOCKS", float, 0.0),
    ("C-B 풀 문턱", "contract", r"C-B\s*(\d+)", float,
     "CB_POOL_MIN_STOCKS", float, 0.0),
    ("m (추출 수)", "contract", r"\bm\s*=\s*(\d+)", float,
     "CB_SAMPLE_M", float, 0.0),
    ("L (T1 룩백)", "contract", r"\bL\s*=\s*(\d+)", float,
     "CB_T1_LOOKBACK_L", float, 0.0),
    ("분위 격자 수", "contract", r"거래대금\s*(\d+)\s*분위", float,
     "MATCH_QUANTILE_BINS", float, 0.0),
    ("커버율 문턱", "contract", r"커버율 문턱\s*([\d.]+)", float,
     "CB_COVERAGE_MIN", float, 0.0),
    ("게이트 A 문턱", "contract", r"A:\s*([\d.]+)\s*%p", lambda s: float(s) / 100,
     "GATE_A_NULL_DELTA_MAX", float, 1e-12),
    ("게이트 B 비율차 문턱", "contract", r"①~④\s*([\d.]+)\s*%p", lambda s: float(s) / 100,
     "GATE_B_RATE_DIFF_MAX", float, 1e-12),
    ("게이트 B 로그차 문턱", "contract", r"ln\(1\.10\)\s*=\s*([\d.]+)", float,
     "GATE_B_LOG_DIFF_MAX", float, 1e-5),
    ("게이트 D 문턱", "contract", r"D:\s*([\d.]+)\s*배", float,
     "GATE_D_SE_RATIO_MAX", float, 0.0),
    ("게이트 F 가용률", "contract", r"가용률\s*([\d.]+)", float,
     "MATCH_VAR_AVAILABILITY_MIN", float, 0.0),
    # --- 계약 블록 밖의 사전 선언 -------------------------------------------
    ("D-19 로그차 문턱", "doc", r"≤\s*ln\(1\.10\)\s*=\s*([\d.]+)", float,
     "GATE_B_LOG_DIFF_MAX", float, 1e-5),
    ("주 판정 k", "doc", r"✅\s*\*\*k\s*=\s*(\d+)\.\*\*", float,
     "PRIMARY_K", float, 0.0),
    ("유의수준 α", "doc", r"α\s*=\s*([\d.]+)\s*\(양측\)", float,
     "ALPHA", float, 0.0),
    ("검정력 power", "doc", r"power\s*=\s*([\d.]+)", float,
     "POWER", float, 0.0),
    ("게이트 A 셔플 반복", "doc", r"반복\s*\|\s*\*\*([\d,]+)회\*\*",
     lambda s: float(s.replace(",", "")), "GATE_A_SHUFFLE_REPS", float, 0.0),

    # ======================================================================
    # 🔧 **Y2 교정 — 「민감도라서」·「문턱이 아니라서」로 면제됐던 것을 대조로 올린다.**
    #
    # 🔴 재검증자 지적: 면제 사유의 다수가 «불가능» 이 아니라 «중요치 않음» 이었다.
    #    그런데 §4.1-(c) 표(:851-857)와 §3.3 표(:730-736)는 이 값들을 **명시**한다 —
    #    ***문서에 값이 있으면 대조 가능하다.*** 「중요치 않다」는 대조를 못 하는
    #    이유가 아니라 **대조를 안 하기로 한 이유**이고, 그것은 면제가 아니라 방치다.
    #
    # ⚠️ 특히 `COMMISSION_RATE_ONE_WAY` 의 옛 사유(*"0-d 확인 대상이라 보류"*)는
    #    **사실과 달랐다** — `0-d` 의 `⟨____⟩` 는 **거래세율**이고, 수수료 0.015%×2 는
    #    §3.3 에 **확정 기재**돼 있다. 🔑 ***면제 사유 자체가 틀릴 수 있다는 것이
    #    「사유를 적으면 면제」가 위험한 이유다*** (§9-17 `N` 파서와 같은 형태).
    # ======================================================================
    ("신고가 룩백 기본안", "doc", r"같은 풀\(L=(\d+)\)로 취급", float,
     "CB_NEW_HIGH_LOOKBACK_L", float, 0.0),
    ("신고가 룩백 민감도", "doc", r"52주\(`L=(\d+)`\)", float,
     "CB_NEW_HIGH_LOOKBACK_SENSITIVITY_L", float, 0.0),
    ("N 미파싱 민감도", "doc", r"`N=(\d+)` 대입", float,
     "CB_N_UNPARSED_SENSITIVITY_VALUE", float, 0.0),
    ("편도 수수료", "doc", r"수수료 \| \*\*([\d.]+)% × 2\*\*", lambda s: float(s) / 100,
     "COMMISSION_RATE_ONE_WAY", float, 1e-12),
    ("고정 비용 민감도", "doc", r"\*\*([\d.]+)% 고정\*\*\(초판값\)", lambda s: float(s) / 100,
     "ROUNDTRIP_COST_FIXED_SENSITIVITY", float, 1e-12),
    ("슬리피지", "doc", r"슬리피지 \| \*\*(\d+) 가정\*\*", float,
     "SLIPPAGE", float, 0.0),
    ("T5 연속 일수", "doc", r"\((\d+)일 연속 확정\)", float,
     "CB_T5_CONSECUTIVE_DAYS", float, 0.0),
)


@pytest.mark.parametrize("spec", _THRESHOLD_CHECKS, ids=[c[0] for c in _THRESHOLD_CHECKS])
def test_doc_declared_thresholds_match_constants(spec):
    """🔴 (2) 문서가 선언한 문턱 수치가 상수와 일치하는가.

    🔑 **문서 쪽에서 못 찾는 것도 실패다.** 「문서가 그 문턱을 더는 선언하지 않는다」는
       상태 역시 갈라짐이며, 조용히 통과시키면 이 검사가 그때부터 vacuous 해진다.
    """
    label, scope, pattern, to_doc, const_name, to_const, tol = spec
    text = _doc_text()
    haystack = _contract_block(text) if scope == "contract" else text

    m = re.search(pattern, haystack)
    assert m, (
        "[%s] 문서(%s)에서 선언을 못 찾았다 — 패턴 %r.\n"
        "문서가 이 문턱을 더는 선언하지 않거나 표기가 바뀌었다. "
        "둘 다 「문서와 상수가 갈라졌다」는 뜻이다." % (label, scope, pattern))
    doc_value = to_doc(m.group(1))

    fc = _load_frozen_module()
    assert hasattr(fc, const_name), (
        "[%s] 문서는 %r 를 선언하는데 frozen_constants.py 에 상수 `%s` 가 없다.\n"
        "🔴 이것이 정확히 C7 이 남긴 형태다 — 교정이 문서에만 도달하고 «해시 대상»에는 "
        "도달하지 않았다." % (label, m.group(0), const_name))
    const_value = to_const(getattr(fc, const_name))

    assert abs(doc_value - const_value) <= tol, (
        "[%s] 문서 ↔ 상수 불일치\n  문서(%s): %r → %r\n  상수 %s: %r\n"
        "🔴 둘 중 하나만 고친 것이다. 해시 대상은 상수 파일이므로, 상수를 안 고치면 "
        "교정이 실행에 도달하지 않는다."
        % (label, scope, m.group(0), doc_value, const_name, const_value))


def test_doc_declared_k_family_matches_constants():
    """청산 창 가족 `k ∈ {1,5,20}` ↔ `PRIMARY_K` + `SECONDARY_K_FAMILY`."""
    block = _contract_block(_doc_text())
    m = re.search(r"k\s*∈\s*\{([\d,\s]+)\}", block)
    assert m, "계약 블록에서 `k∈{...}` 선언을 못 찾았다"
    doc_k = tuple(sorted(int(x) for x in m.group(1).split(",")))
    fc = _load_frozen_module()
    const_k = tuple(sorted({fc.PRIMARY_K, *fc.SECONDARY_K_FAMILY}))
    assert doc_k == const_k, "청산 창 가족 불일치 — 문서 %s ↔ 상수 %s" % (doc_k, const_k)


# --- 층 정의 (§5.2) ----------------------------------------------------------

_STRATA_DOC_LABEL = {
    "year": "연도",
    "src": "src",
    "trigger_type": "트리거 유형",
    "date_density": "날짜 밀집도",
}


def _strata_rows(text: str) -> dict:
    """§5.2 「층 목록」 표 → {층 라벨: (값 셀, 지위 셀)}."""
    m = re.search(r"###\s*5\.2\s*층 목록.*?\n(\|.*?)\n\n", text, re.S)
    assert m, "§5.2 층 목록 표를 못 찾았다"
    out = {}
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 3 or cells[0].startswith("---") or cells[0] == "층":
            continue
        out[cells[0].replace("*", "").replace("`", "").strip()] = (cells[1], cells[2])
    assert len(out) == 4, "§5.2 표에서 층 4개를 못 뽑았다: %s" % list(out)
    return out


# 🔴 층 «지위» 의 닫힌 어휘. §5.2 에는 이 둘 말고 없다.
_STATUS_VOCABULARY = {
    "부수": False,
    "필수 부수 판정": True,
}

# 지위 셀에서 연혁 서술을 떼는 구분자. em dash · en dash · `·` · `(` · `（` · `,` 전부 실사용된다.
_STATUS_SEPARATORS = "[(（—–·•,]"


def _status_is_essential(cell: str) -> bool:
    """지위 셀의 «판정» 부분을 **닫힌 어휘로** 대조한다.

    🔴 **이전 판본은 fail-open 이었다** (2026-08-04 재검증자 실증).
       `head = re.split(r"[(—]", cell, 1)[0]` 뒤 `"필수" in head` —
       **휴리스틱 절단 + 부분문자열 포함**이라 세 형태 중 둘을 못 잡았다:

         · `🔴 **필수 아님** — 부수로 강등한다`  → 「필수」가 들어 있어 True → **PASS(못 잡음)**
         · `**부수** · 2판은 「필수 부수 판정」`  → `·` 를 안 자르니 연혁까지 읽어 True → **PASS(못 잡음)**
         · `**부수** — 2판은 「필수 부수 판정」`  → em dash 일 때만 FAIL

       🔑 ***「필수」라는 «부분문자열» 은 「필수 부수 판정」이라는 «지위» 가 아니다.***
          부분문자열 포함은 부정형(`필수 아님`)과 연혁 인용에 **원리적으로** 열려 있다.

    ⇒ 교정: 마크다운·머리 마커를 떼고 **정확히 `부수` 또는 `필수 부수 판정`** 이어야 하며,
       **둘 다 아니면 AssertionError** 로 올린다 — 모르는 표기는 통과가 아니라 실패다.
    """
    text = cell
    for junk in ("*", "`", "「", "」"):
        text = text.replace(junk, "")
    head = re.split(_STATUS_SEPARATORS, text, 1)[0]
    # 머리의 🔴🔧🟡 등 마커·공백을 뗀다 (한글이 시작되는 지점부터가 지위다).
    head = re.sub(r"^[^가-힣]+", "", head)
    key = re.sub(r"\s+", " ", head).strip()
    if key not in _STATUS_VOCABULARY:
        raise AssertionError(
            "§5.2 지위 셀이 닫힌 어휘 밖이다: %r → 판정부 %r\n"
            "  허용: %s\n"
            "🔴 «모르는 표기» 를 조용히 통과시키지 않는다 — 이전 판본은 부분문자열 "
            "포함이라 `필수 아님` 을 「필수」로 읽었다."
            % (cell, key, sorted(_STATUS_VOCABULARY)))
    return _STATUS_VOCABULARY[key]


# 🔴 Y3 회귀 — 재검증자가 실증한 세 변형. 상수 지위가 「필수 부수 판정」인 층(`src`)에
#    이 셀들이 들어오면 **갈라짐으로 잡혀야** 한다. 이전 판본은 둘을 통과시켰다.
_STATUS_DEMOTION_PROBES = (
    ("\U0001f534 **필수 아님** — 부수로 강등한다", "부정형(필수 아님)"),
    ("**부수** · 2판은 「필수 부수 판정」", "· 구분자 + 연혁 인용"),
    ("**부수** — 2판은 「필수 부수 판정」", "em dash + 연혁 인용"),
)


@pytest.mark.parametrize("cell,label", _STATUS_DEMOTION_PROBES,
                         ids=[p[1] for p in _STATUS_DEMOTION_PROBES])
def test_status_parser_rejects_demotion_of_essential_stratum(cell, label):
    """🔴 Y3 회귀 — 세 형태가 「필수 부수 판정」으로 «안» 읽히는가.

    🔑 이전 판본은 셋 중 **둘을 「필수」로 읽었다**(재검증자 실증). 그러면 문서가
       지위를 강등해도 상수(필수)와의 갈라짐이 `test_strata_status_matches_doc` 에
       한 번도 안 걸린다 — 검사가 켜져 있는데 아무것도 안 보는 상태다.
    """
    try:
        doc_essential = _status_is_essential(cell)
    except AssertionError:
        return                       # 닫힌 어휘 밖 ⇒ 이미 FAIL 이다. 이것도 「잡았다」.
    assert doc_essential is False, (
        "[%s] %r 가 「필수 부수 판정」으로 읽혔다 — 상수(필수)와의 갈라짐이 안 잡힌다"
        % (label, cell))


def test_strata_status_matches_doc():
    """🔴 §5.2 가 선언한 층 «지위» 가 `STRATA` 와 일치하는가.

    🔑 §5.1 이 연도 층을 **부수로 강등**했는데 상수는 2판 지위(`필수 부수 판정`)를
       그대로 들고 있었다. 지위는 보고 의무의 등급이자 §12.1 판정 해석에 들어가는
       설계값이므로, 갈라지면 문서와 실행이 다른 설계를 돌리게 된다.
    """
    rows = _strata_rows(_doc_text())
    fc = _load_frozen_module()
    problems = []
    for key, label in _STRATA_DOC_LABEL.items():
        matched = [k for k in rows if label in k]
        assert matched, "§5.2 표에서 층 %r 행을 못 찾았다 (표: %s)" % (label, list(rows))
        _, status_cell = rows[matched[0]]
        doc_essential = _status_is_essential(status_cell)
        const_essential = fc.STRATA[key]["status"] == "필수 부수 판정"
        if doc_essential != const_essential:
            problems.append(
                "  %s: 문서 %r ↔ 상수 %r"
                % (key, "필수 부수 판정" if doc_essential else "부수",
                   fc.STRATA[key]["status"]))
    assert not problems, "층 지위가 문서와 상수에서 갈라졌다:\n" + "\n".join(problems)


def test_strata_src_values_cover_doc_buckets():
    """🔴 §5.2 의 `src` 결손표가 세는 칸이 `STRATA["src"]["values"]` 안에 전부 있는가.

    🔑 결손표는 `both+prose` 2행을 **스스로 세면서** 층 열거에는 그 값이 없었다.
       §6-C 는 실행 중 층 추가를 금지하므로, 열거에 없는 칸의 행은 **갈 곳이 없다.**
    """
    text = _doc_text()
    m = re.search(r"\|\s*`src`\s*칸\s*\|.*?\n((?:\|.*\n)+)", text)
    assert m, "§5.2 의 `src` 결손표를 못 찾았다"
    buckets = []
    for line in m.group(1).splitlines():
        cell = line.strip().strip("|").split("|")[0]
        cell = cell.replace("*", "").replace("`", "").replace(" ", "")
        if cell and not cell.startswith("---"):
            buckets.append(cell)
    assert len(buckets) >= 4, (
        "결손표에서 src 칸을 %d개밖에 못 뽑았다: %s" % (len(buckets), buckets))
    fc = _load_frozen_module()
    declared = set(fc.STRATA["src"]["values"])
    missing = [b for b in buckets if b not in declared]
    assert not missing, (
        "문서가 세는 `src` 칸이 층 열거에 없다: %s\n  층 열거: %s\n"
        "§6-C 가 실행 중 층 추가를 금지하므로 이 행들은 분류될 곳이 없다."
        % (missing, sorted(declared)))


# --- (2-b) 🔧 Y2 — 수치가 아닌 «구조» 선언도 문서와 대조한다 ------------------
#
# 🔴 스칼라가 아니라서(튜플·문자열) 면제됐던 것들이다. 그러나 §4.1-(c) 표와
#    §12.3 D-2 는 이 값들을 **명시**하므로 대조 «가능» 하다.
#    🔑 ***「기계 파싱 대상이 아니다」는 파서를 안 썼다는 뜻이지 못 쓴다는 뜻이 아니다.***

_STRUCTURED_DOC_CHECKS = (
    ("T1 룩백 민감도", r"`L ∈ \{([\d,\s]+)\}`",
     lambda s: tuple(sorted(int(x) for x in s.split(","))),
     "CB_T1_LOOKBACK_SENSITIVITY_L", lambda v: tuple(sorted(v))),
    ("셀 확장 순서", r"q(−\d) → q(\+\d) → q(−\d) → q(\+\d)",
     lambda g: tuple(int(x.replace("−", "-").replace("+", "")) for x in g),
     "MATCH_CELL_EXPANSION_ORDER", tuple),
    ("배정 기본안", r"\| 배정 \| \*\*(\S+)\*\* \|",
     lambda s: {"교집합": "intersection"}.get(s, s),
     "CB_TYPE_ASSIGNMENT", str),
    ("배정 민감도", r"\| 배정 \| \*\*\S+\*\* \| ([^|]+?) \|",
     lambda s: {"우선순위 단일배정": "priority_single"}.get(s.strip(), s.strip()),
     "CB_TYPE_ASSIGNMENT_SENSITIVITY", str),
    # 🔧 🔴-2 — `k` 의 적용 범위. 문서 §4.1-4·§4.3 이 값을 «문자열 그대로» 적으므로
    #    이것은 면제가 아니라 대조 대상이다.
    ("k 적용 범위", r'ARM_SEED_K_SCOPE = "(\w+)"', lambda s: s,
     "ARM_SEED_K_SCOPE", str),
)


@pytest.mark.parametrize("spec", _STRUCTURED_DOC_CHECKS,
                         ids=[c[0] for c in _STRUCTURED_DOC_CHECKS])
def test_doc_declared_structures_match_constants(spec):
    """🔧 Y2 — 문서가 선언한 «구조» (순서 튜플·정책 문자열)가 상수와 일치하는가."""
    label, pattern, to_doc, const_name, to_const = spec
    m = re.search(pattern, _doc_text())
    assert m, ("[%s] 문서에서 선언을 못 찾았다 — 패턴 %r. 표기가 바뀌었다면 "
               "그것도 「문서와 상수가 갈라졌다」다." % (label, pattern))
    groups = m.groups()
    doc_value = to_doc(groups if len(groups) > 1 else groups[0])
    fc = _load_frozen_module()
    const_value = to_const(getattr(fc, const_name))
    assert doc_value == const_value, (
        "[%s] 문서 ↔ 상수 불일치\n  문서: %r\n  상수 %s: %r"
        % (label, doc_value, const_name, const_value))


# --- (2-c) 🔴 Y2 + 🔴-C — **bool 플래그도 문서와 대조한다** --------------------
#
# 🔴 **이것이 🔴-C 가 드러낸 구멍이다.** `N_LOOKBACK_PARSER_RESOLVED` 는
#    *"동결 차단 플래그(bool) — 수치 문턱이 아니다"* 라는 **그럴듯한 사유로 면제**돼
#    있었다. 그래서 **상수는 `True`(파서 작성·재현 완료)인데 문서 5곳이 여전히
#    「파서가 없다·재현 불가」라고 적고 있는 상태**를 검사 8 이 한 번도 못 봤다.
#
# 🔑 ***「사유를 적으면 면제」가 새 열거식 구멍이다.*** 사유는 그럴듯할수록 다시
#    안 열어보게 되고, 사유 자체가 틀릴 수도 있다(`COMMISSION_RATE_ONE_WAY` 참조).
#    ⇒ bool 은 **수치가 아니라 «상태»** 이므로, 문서가 그 상태를 어떻게 적고 있는지와
#      대조한다. 값 대조가 안 되면 **상태 대조**를 하는 것이지 면제하는 것이 아니다.

# ---------------------------------------------------------------------------
# 🔴 **두 표는 «양방향» 이다 — 한쪽만 채우면 그 플래그는 한 방향으로 자유롭게 뒤집힌다**
# ---------------------------------------------------------------------------
#
# **무엇이 틀렸나** (관리자 실측 2026-08-04): `_FLAG_STALE_PHRASES` 에 하나,
# `_FLAG_OPEN_PHRASES` 에 셋뿐이라 **네 플래그 전부 반대 방향이 비어 있었다.**
# `dict.get(flag, ())` 는 빈 튜플을 조용히 돌려주고, 빈 목록에 대한 포함 검사는
# **공허하게 참**이다 ⇒ 뒤집어도 아무 일도 일어나지 않는다.
#
# 🔑 ***플래그의 «상태» 를 검사한다는 것은 두 상태를 «둘 다» 검사한다는 뜻이다.***
#    한 상태만 검사하는 것은 검사가 아니라 **그 상태를 가정하는 것**이다.
#
# ⇒ 각 플래그마다 **True 를 «반증» 하는 문구**(= 미해소 주장)와 **False 를 «뒷받침»
#   하는 문구**(= 미해소 표시)를 둘 다 등재한다. 어느 쪽으로 뒤집어도 문서와 갈라지면
#   FAIL 하며, 등재 자체를 `test_every_freeze_flag_is_bound_in_both_directions` 가 강제한다.
#
# 🔑 **양쪽에 같이 넣은 문구가 「두 방향 표지」다** — `⟨____⟩` · `열린 결정 D-12` ·
#    `R4 여전히 미충족` · `파서가 존재하지 않는다`. 그 문구가 있으면 False, 없으면 True 가
#    되어 **iff 결속**이 된다. (나머지는 한쪽 방향을 두껍게 하는 보강 문구다.)

# 플래그가 «해소됨(True)» 이면 문서에 남아 있으면 안 되는 문구.
_FLAG_STALE_PHRASES = {
    "N_LOOKBACK_PARSER_RESOLVED": (
        "파서 미커밋", "파서 자체가 미작성", "파서가 존재하지 않는다",
        "이 수치는 현재 재현 불가능하다", "에 **새로 작성해야** 한다",
    ),
    # 🔴 가장 위험한 플래그 — 이것이 «동결을 여는 스위치» 다 (§0-d).
    "COST_SOURCE_VERIFIED": (
        "⟨____⟩",                       # §3.3 세율 표의 빈칸 (두 방향 표지)
        "원출처 미확인",                # §3.3 소제목
        "원출처로 확인되지 않았다",     # §0 0-d 주석
    ),
    "D12_RESOLVED": (
        "열린 결정 D-12",               # §4.1-(g-2) · §6-B (두 방향 표지)
        "D-12 가 닫히기 전에는",        # §12.1 PASS 조건 ③ 의 전제
        "D-12 미결",                    # §6-C 계약 블록 · §9
    ),
    "MATCH_R4_SATISFIED": (
        "R4 여전히 미충족",             # §0.2 재개 조건 현황표 (두 방향 표지)
        "R4 미충족 ⇒ 돌지 않음",        # §4.3 조건부 민감도 arm
    ),
}

# 플래그가 «미해소(False)» 인 동안 문서에 **있어야** 하는 문구.
_FLAG_OPEN_PHRASES = {
    "COST_SOURCE_VERIFIED": ("⟨____⟩", "원출처 미확인"),   # §3.3 세율 표가 비어 있어야 한다
    "D12_RESOLVED": ("**D-12**", "열린 결정 D-12"),        # §12.4 열린 결정에 남아야 한다
    "MATCH_R4_SATISFIED": ("**R4**", "R4 여전히 미충족"),  # §0.2 에 미충족으로 남아야 한다
    # 🔴 현행 문서에 **없는** 문구다 (플래그가 True 라 맞다). False 로 되돌리려면
    #    문서에 미해소 표시를 «먼저» 적어야 통과한다 — 그것이 이 방향의 결속이다.
    "N_LOOKBACK_PARSER_RESOLVED": ("파서가 존재하지 않는다",),
}


def _assert_flag_matches_doc(fc, flag, text):
    """bool 플래그의 «상태» ↔ 문서 문구."""
    if getattr(fc, flag):
        stale = [p for p in _FLAG_STALE_PHRASES.get(flag, ()) if p in text]
        assert not stale, (
            "%s = True 인데 문서에 미해소 문구가 남아 있다: %s\n"
            "🔴 상수는 「됐다」, 문서는 「안 됐다」 — 실행자는 문서를 읽고 "
            "이미 있는 것을 다시 만든다.\n"
            "⚠️ **연혁 인용 때문에 걸렸을 수 있다** — 이 검사는 «살아 있는 주장»과 «옛 문구의 "
            "인용»을 구분하지 못하며, 그것은 일부러 그렇게 뒀다(fail-closed). "
            "연혁을 적을 때는 **옛 문구를 그대로 따옴표에 넣지 말고 요약해서** 쓸 것."
            % (flag, stale))
    else:
        missing = [p for p in _FLAG_OPEN_PHRASES.get(flag, ()) if p not in text]
        assert not missing, (
            "%s = False 인데 문서에서 미해소 표시가 사라졌다: %s\n"
            "🔴 문서만 「닫혔다」로 읽히면 동결 차단 조건이 조용히 없어진다."
            % (flag, missing))


@pytest.mark.parametrize("flag", sorted(set(_FLAG_STALE_PHRASES) | set(_FLAG_OPEN_PHRASES)))
def test_freeze_flags_match_doc_state(flag):
    """🔴 bool 동결 플래그의 «상태» 가 문서와 일치하는가.

    ⚠️ 이 검사가 없던 동안 `N_LOOKBACK_PARSER_RESOLVED = True` 와
       *"`N` 파서가 존재하지 않는다"*(§9-17) 가 **같은 라운드에 공존**했다.
       실행자는 이미 있는 파서를 **손으로 다시 쓰게 되고**, 그것이 §13.2-1
       (*정규식을 손으로 옮겨 적으면 조용히 다른 것을 검사한다*)의 재발이다.

    ⚠️ **사정거리**: 이 검사는 «살아 있는 주장» 과 «연혁 인용» 을 구분하지 못한다.
       옛 문구를 그대로 따옴표에 넣어도 걸린다 — **일부러 그렇게 뒀다.**
       문서를 그 문구로 검색하는 사람은 인용인지 주장인지 모르고 걸리기 때문이며,
       모호하면 통과가 아니라 실패로 기울이는 것이 이 파일의 규약이다(fail-closed).
       ⇒ 연혁을 적을 때는 **옛 문구를 요약해서** 쓸 것.
    """
    _assert_flag_matches_doc(_load_frozen_module(), flag, _doc_text())


# --- (2-d) 🔴 **동결 차단 플래그 변이 주입** — 어느 방향으로 뒤집어도 잡히는가 -----
#
# 🔴 **이 절이 왜 생겼는가 — 이 트랙이 잡으려던 클래스를 이 트랙의 장치가 저지르고 있었다.**
#
# 관리자 실측(2026-08-04): 동결 차단 플래그 **4건을 한 줄씩 뒤집어도 스위트가 전건 통과**했다.
# 원인이 둘이고, 둘 다 「검사가 실패하는 것」이 아니라 **「검사가 꺼지는 것」**이다:
#
#   ① **한 방향만 등재돼 있었다.** `_FLAG_STALE_PHRASES` 에 하나(=True 를 반증하는 문구),
#      `_FLAG_OPEN_PHRASES` 에 셋(=False 를 뒷받침하는 문구)뿐이라 **각 플래그의 반대
#      방향이 통째로 비어 있었다.** `dict.get(flag, ())` 는 빈 튜플을 조용히 돌려주고,
#      빈 목록에 대한 `all/any` 는 **공허하게 참**이다.
#   ② 🔴 **`if not FLAG:` 가드는 플래그를 True 로 바꾸면 «가드 자체가» 꺼진다.**
#      `MATCH_R4_SATISFIED` 가 정확히 그랬다 — 검사가 실패하는 게 아니라 검사할 것이
#      없어진다. ⇒ **True 쪽에도 검사할 것을 둔다**(else 절).
#
# 🔑 ***공허 통과는 「통과」로 보고되므로, 스위트 색깔로는 원리적으로 구분되지 않는다.***
#    ⇒ 변이를 주입해 **「잡히는가」를 직접 묻는 것** 말고 확인할 방법이 없다.
#
# ⚠️ **관리자 실측과 이 회귀의 «한 줄» 차이 — 기록해 둔다.**
#    관리자는 `D12_RESOLVED` 단순 뒤집기도 미탐이라고 봤으나, 이 워크트리에서 캐시를
#    지우고 재현하면 **`test_d12_matching_method_is_open` 이 잡는다**(else 절이 있다).
#    관리자 측 결과는 **바이트코드 캐시 오염**으로 설명된다 — `_load_frozen_module`
#    독스트링의 ①②③ 실측 참조(같은 파일 내용인데 캐시 유무로 146 passed ↔ 1 failed).
#    🔴 **그렇다고 D-12 가 결속돼 있던 것은 아니다.** 아래 `D12_RESOLVED=True+정합마감`
#    이 그것을 보인다 — 상수끼리 «정합하게» 닫으면(방식·ε 까지 채우면) **문서가 여전히
#    D-12 를 열린 결정으로 적고 있어도 전건 통과**했다. ⇒ 결속은 문서 쪽에 있어야 한다.

# 동결 차단 플래그 전수. 🔴 **양방향 등재를 강제하는 목록이다** (아래 두 테스트가 쓴다).
_FREEZE_FLAGS = (
    "COST_SOURCE_VERIFIED",
    "D12_RESOLVED",
    "MATCH_R4_SATISFIED",
    "N_LOOKBACK_PARSER_RESOLVED",
)

# (라벨, 상수 → 새 리터럴). 🔴 **관리자가 실제로 주입한 4종 + 정합 마감 1종.**
_FLAG_MUTATIONS = (
    ("COST_SOURCE_VERIFIED=True", {"COST_SOURCE_VERIFIED": "True"}),
    ("MATCH_R4_SATISFIED=True", {"MATCH_R4_SATISFIED": "True"}),
    ("N_LOOKBACK_PARSER_RESOLVED=False", {"N_LOOKBACK_PARSER_RESOLVED": "False"}),
    ("D12_RESOLVED=True", {"D12_RESOLVED": "True"}),
    # 🔴 상수끼리는 «정합» 한 마감 — 단순 뒤집기보다 나쁘다. 문서만 갈라진다.
    ("D12_RESOLVED=True+정합마감", {"D12_RESOLVED": "True",
                                    "MATCH_METHOD": '"caliper"',
                                    "MATCH_CALIPER_EPS": "0.05"}),
)


def _flag_state_checks(fc, text):
    """플래그 «상태» 에 걸린 단언 전부. 하나라도 AssertionError 면 「잡았다」.

    🔑 실제 테스트와 **같은 함수**를 쓴다. 변이 회귀가 자기 사본을 들고 있으면
       「교정을 적은 파일과 도달해야 할 파일이 다른」 그 패턴이 여기서 재발한다.
    """
    yield "매칭 축(R4)", lambda: _assert_match_r4_state(fc)
    yield "D-12 상태", lambda: _assert_d12_state(fc)
    yield "§3.3 세율 표", lambda: _assert_cost_source_state(fc, text)
    yield "N 파서 재현", lambda: _assert_n_parser_state(fc)
    for flag in _FREEZE_FLAGS:
        yield "문서 상태:%s" % flag, (lambda f=flag: _assert_flag_matches_doc(fc, f, text))


def test_flag_state_checks_pass_on_current_constants():
    """음성 대조 — 위 검사들이 **현행 상수에서는 전부 통과**하는가.

    🔑 이게 없으면 변이 회귀가 「항상 잡는다」로 공허하게 통과할 수 있다
       (검사가 늘 예외를 던지면 어떤 변이든 잡힌 것처럼 보인다).
    """
    fc = _load_frozen_module()
    text = _doc_text()
    firing = [name for name, chk in _flag_state_checks(fc, text)
              if _raises_assertion(chk)]
    assert not firing, (
        "현행 상수에서 플래그 상태 검사가 발화했다: %s — 변이 회귀가 «항상 잡는» "
        "상태라 판별력이 없다" % firing)


@pytest.mark.parametrize("label,overrides", _FLAG_MUTATIONS,
                         ids=[m[0] for m in _FLAG_MUTATIONS])
def test_freeze_flag_mutation_is_detected(label, overrides):
    """🔴 동결 차단 플래그를 뒤집으면 **어느 방향이든** 갈라짐으로 잡히는가.

    🔴 **가장 위험한 것은 `COST_SOURCE_VERIFIED = True` 다** — 이것은 «동결을 여는
       스위치»이고, §3.3 거래세율 표가 `⟨____⟩` 로 **비어 있는 채로** True 를 박아도
       그 전에는 전건 통과했다.
    """
    fc = _load_frozen_module(_mutated_frozen_source(overrides))
    text = _doc_text()
    caught = [name for name, chk in _flag_state_checks(fc, text)
              if _raises_assertion(chk)]
    assert caught, (
        "[%s] 변이가 **미탐**이다 — 플래그를 뒤집었는데 아무 검사도 발화하지 않았다.\n"
        "🔴 이것은 「검사가 실패하지 않았다」가 아니라 **「검사가 꺼졌다」** 다.\n"
        "   · 반대 방향 문구가 `_FLAG_STALE_PHRASES`/`_FLAG_OPEN_PHRASES` 에 없거나,\n"
        "   · `if not FLAG:` 가드라 True 쪽에 검사할 것이 없다.\n"
        "⇒ 두 문구 표에 **양방향**으로 등재하고, 가드에 else 절을 둘 것." % label)


def test_every_freeze_flag_is_bound_in_both_directions():
    """🔴 **양방향 등재를 fail-closed 로 강제한다.**

    🔑 원 결함은 개별 누락이 아니라 **「한 방향이 비어 있어도 통과하는 구조」** 였다.
       빈 튜플에 대한 포함 검사는 조용히 참이므로, 표를 채우는 일을 사람 기억에
       맡기면 다음 플래그에서 같은 일이 난다.
    """
    missing = []
    for flag in _FREEZE_FLAGS:
        if not _FLAG_STALE_PHRASES.get(flag):
            missing.append(
                "  %s — True 를 «반증» 하는 문구(_FLAG_STALE_PHRASES)가 없다: "
                "True 로 뒤집어도 문서와 대조되지 않는다" % flag)
        if not _FLAG_OPEN_PHRASES.get(flag):
            missing.append(
                "  %s — False 를 «뒷받침» 하는 문구(_FLAG_OPEN_PHRASES)가 없다: "
                "False 로 뒤집어도 문서와 대조되지 않는다" % flag)
    assert not missing, (
        "동결 차단 플래그가 «한 방향만» 결속돼 있다:\n" + "\n".join(missing))


# --- (3) 양방향 — 기계 대조가 닿지 않는 상수를 «선언»하게 한다 ------------------
#
# 🔴 문서는 §6-C 의 SSOT 규약에 따라 **상수 값을 전재하지 않는다.** 그래서 「문서가
#    이름으로 부르지 않는 상수」를 전부 위반으로 볼 수는 없다. 대신 **위 (2) 의 기계
#    대조가 실제로 닿는 상수**와 **닿지 않는 상수**를 갈라 적고, 후자에 사유를 붙인다.
#    새 상수를 추가하면 둘 중 하나로 «분류해야만» 통과한다(fail-closed).
_CROSSCHECKED_CONSTANTS = frozenset(
    [c[4] for c in _THRESHOLD_CHECKS]
    + [c[3] for c in _STRUCTURED_DOC_CHECKS]
    + list(_FLAG_STALE_PHRASES) + list(_FLAG_OPEN_PHRASES)
    + ["PRIMARY_K", "SECONDARY_K_FAMILY", "STRATA"]
)

# ---------------------------------------------------------------------------
# 🔴 면제 사유는 **두 범주뿐이다** (🔧 Y2 교정)
# ---------------------------------------------------------------------------
#
# **무엇이 틀렸나**: 이전 판본의 면제 사유 45건 중 다수가 «불가능» 이 아니라
# «중요치 않음» 이었다 — *"민감도(판정 아님)"* · *"수치 문턱이 아니다"* ·
# *"기계 파싱 대상이 아니다"* · *"문자열"*. 그런데 §4.1-(c)·§3.3·§12.3 D-2 는
# 그 값들을 **명시**한다.
#
# 🔑 ***문서에 값이 있으면 대조 가능하다.*** 「중요치 않다」는 대조를 못 하는
#    이유가 아니라 **대조를 안 하기로 한 이유**이고, 그것은 면제가 아니라 방치다.
#
# ⚠️ 그리고 사유는 **틀릴 수도 있다** — `COMMISSION_RATE_ONE_WAY` 의 옛 사유
#    (*"0-d 확인 대상이라 보류"*)는 사실과 달랐다. `0-d` 의 `⟨____⟩` 는 **거래세율**
#    이고 수수료 0.015%×2 는 §3.3 에 **확정 기재**돼 있다.
#    🔴 ***「사유를 적으면 면제」가 새 열거식 구멍이다*** — 🔴-C 가 실증했다
#    (`N_LOOKBACK_PARSER_RESOLVED` 가 *"bool 이라 수치 문턱이 아니다"* 로 면제돼,
#     상수는 True 인데 문서 5곳이 「파서 없음」인 상태를 아무도 못 봤다).
#
# ⇒ **면제 사유를 두 범주로 못 박고, 태그를 강제한다**(fail-closed):
#      `[값없음]`    — 문서에 그 값이 «수치·문자열로» 적혀 있지 않다
#      `[대체대조]`  — 값 대조 대신 **바이트 대조 또는 동작 재현**으로 동결됐다
#    ⚠️ 「중요치 않음」·「민감도라서」·「bool 이라서」는 **더는 사유가 아니다.**
_EXEMPTION_CATEGORIES = ("[값없음]", "[대체대조]")

# 상수 이름 → (범주 태그) 왜 문서와 «수치 대조»가 안 되는가
_NOT_CROSSCHECKED_CONSTANTS = {
    # --- 시드 계열: 시드는 임의여야 하므로 문서에 근거 수치가 «있을 수 없다» ---
    "MASTER_SEED": "[값없음] 시드는 임의값이라 문서에 근거 수치가 없다(값이 아니라 고정만이 요건)",
    "SEED_CB": "[값없음] 문서는 이름만 부르고 값을 적지 않는다(§4.1)",
    "SEED_CB_MATCHED_TV": "[값없음] 문서는 arm 이름만 적는다(§4.1-g)",
    "SEED_CA": "[값없음] 문서는 이름만 부른다(§4.3)",
    "SEED_SHUFFLE": "[값없음] 문서는 이름만 부른다(§6-A)",
    "ARM_SEED_DERIVATION_RULE": "[값없음] 파생 규칙 문자열 — 문서는 규칙의 «존재»만 계약한다",
    "ARM_SEED_REP_SCOPE": "[값없음] rep 적용 범위 선언 — 문서에 없다(불변식 테스트가 'all_arms' 를 강제)",
    "ARM_BASE_SEEDS": "[대체대조] test_arm_base_seeds_are_explicit_constants 가 명시 시드·오프셋 표와의 항등식을 단언",
    "ARM_SEED_OFFSETS": "[대체대조] test_arm_seed_streams_do_not_overlap 가 «도달집합 서로소»를 단언",
    "ARM_SEED_K_MULTIPLIER": "[대체대조] test_arm_seed_domain_is_declared 가 rep 스트림 수와의 단사성 항등식을 단언",
    "ARM_SEED_K_VALUES": "[대체대조] 판정 k 가족(PRIMARY_K + SECONDARY_K_FAMILY)과의 정합을 단언",
    "ARM_SEED_REP_BASE": "[대체대조] MAX_REP − REP_BASE + 1 == GATE_A_SHUFFLE_REPS 항등식",
    "ARM_SEED_MAX_REP": "[대체대조] 동상",
    "POWER_TRACK_LEGACY_SEED": "[대체대조] 검사 9(출처 대조)가 power/step2_power.py:13 과 값을 대조한다",

    # --- 정규식 계열: 값 대조가 아니라 «바이트 대조»가 정공법이다 (§13.2-1) ---
    "MA_TOK_PATTERN": "[대체대조] test_type_patterns_match_upstream_original 바이트 대조",
    "T3_MA_BOUNCE_PATTERN": "[대체대조] 동상",
    "T4_MA_BREAK_PATTERN": "[대체대조] 동상",
    "T2_PREV_HIGH_PATTERN": "[대체대조] 동상",
    "T1_PRIOR_HIGH_PATTERN": "[대체대조] 동상",
    "T5_CONSEC_UP_PATTERN": "[대체대조] 동상",
    "TYPE_PATTERNS_IN_PRIORITY_ORDER": "[대체대조] test_priority_order_matches_upstream 순서 대조",
    "N_LOOKBACK_PARSER_PATTERN": "[대체대조] 상류가 휘발성이라 «동작 재현»으로 동결 — test_n_lookback_parser_reproduces_prereg_counts",
    "N_LOOKBACK_PARSER_SCOPE_ASSIGNMENT": "[대체대조] 동작 재현 테스트가 배정 규약 일치를 단언",
    "N_LOOKBACK_PARSE_EXPECTED": "[대체대조] 재현 기대값 — labels_v4.csv 실행으로 대조",
    "N_LOOKBACK_PARSER_APPLY": "[값없음] 적용 함수 표기(pandas API)는 문서에 없다",
    "N_LOOKBACK_PARSER_SCOPE": "[값없음] 적용 대상 유형 집합은 문서에 열거돼 있지 않다",

    # --- 열린 결정: 확정 전이라 문서에 «값 자체가» 없다 ---
    "CB_N_UNPARSED_POLICY": "[값없음] 문서는 「C-B 표본 밖」이라 적고 정책 «문자열»은 적지 않는다",
    "MATCH_METHOD": "[값없음] 🔴 D-12 열린 결정 — 확정 전까지 문서에 값이 없다",
    "MATCH_CALIPER_EPS": "[값없음] 🔴 D-12 미결 — §4.1-(g-2) 절차로 실측 후 확정(현재 None)",
    "ROUNDTRIP_COST_BY_YEAR": "[값없음] 🔴 0-d 미충족 — 문서 §3.3 표가 `⟨____⟩` 라 대조할 확정값이 없다",
    "PRIMARY_STRATUM": "[값없음] 문서는 「전체」로 적고 'all' 이라는 토큰을 쓰지 않는다",

    # --- 축 구성: 불변식 테스트가 «구성» 자체를 단언한다 ---
    "MATCH_AXES": "[대체대조] test_matching_axis_invariants 가 축 구성 불변식을 단언",
    "MATCH_AXES_R4_SENSITIVITY": "[대체대조] 동상",
    "MATCH_CELL_EXPANSION_AXIS": "[대체대조] test_matching_axis_invariants (확장 축 ∈ 활성 축)",
}


def test_every_constant_is_classified_for_doc_crosscheck():
    """🔴 (3) 양방향 — 모든 상수가 「문서와 기계 대조됨」/「안 됨(사유)」 중 하나인가.

    🔑 **이 검사의 값어치는 새 상수가 생겼을 때 나온다.** 분류하지 않으면 통과하지
       못하므로, 「상수만 늘고 문서는 모르는」 상태가 조용히 성립할 수 없다.
       (열거하는 것이 «대조 대상» 이 아니라 «면제» 이므로 방향이 fail-closed 다 —
        이 파일의 ALLOWLIST 와 같은 설계다.)
    """
    tree = ast.parse(FROZEN.read_text(encoding="utf-8"))
    names = [t.id for n in tree.body if isinstance(n, ast.Assign)
             for t in n.targets if isinstance(t, ast.Name)]
    assert len(names) > 30, "상수를 %d개밖에 못 뽑았다 — 파싱이 깨졌다" % len(names)

    classified = _CROSSCHECKED_CONSTANTS | set(_NOT_CROSSCHECKED_CONSTANTS)
    # 🔴 한 상수가 「대조됨」과 「면제됨」에 동시에 있으면 안 된다 — 합집합으로만
    #    검사하면 그 모순이 조용히 통과한다(면제 표를 갱신 안 한 채 승격한 경우).
    both = sorted(_CROSSCHECKED_CONSTANTS & set(_NOT_CROSSCHECKED_CONSTANTS))
    assert not both, (
        "「기계 대조됨」과 「면제됨」에 동시에 등재된 상수: %s — 대조로 «승격» 했으면 "
        "면제 표에서 지울 것." % both)
    unclassified = sorted(set(names) - classified)
    stale = sorted(classified - set(names))
    assert not unclassified, (
        "문서 대조 분류가 없는 상수: %s\n"
        "_CROSSCHECKED_CONSTANTS(기계 대조됨) 또는 "
        "_NOT_CROSSCHECKED_CONSTANTS(사유 명시) 중 하나에 넣을 것." % unclassified)
    assert not stale, (
        "분류표에만 있고 실재하지 않는 상수: %s — 분류표를 갱신할 것." % stale)


def test_crosscheck_exemption_reasons_are_in_allowed_categories():
    """🔴 Y2 — 면제 사유가 **두 범주 안**에 있는가 (fail-closed).

    🔑 이전 판본은 사유가 자유 서술이라 *"민감도(판정 아님)"* · *"수치 문턱이 아니다"* ·
       *"기계 파싱 대상이 아니다"* 같은 **「중요치 않음」** 이 「불가능」과 섞여 있었다.
       ⚠️ 그리고 사유 자체가 틀린 것도 있었다(`COMMISSION_RATE_ONE_WAY`).
       ⇒ 태그를 강제하면 **새 상수를 면제할 때 둘 중 하나를 «고르게» 되고**,
         「중요치 않아서」라는 선택지가 애초에 없다.
    """
    bad = sorted(n for n, r in _NOT_CROSSCHECKED_CONSTANTS.items()
                 if not r.startswith(_EXEMPTION_CATEGORIES))
    assert not bad, (
        "면제 사유가 허용 범주 밖이다: %s\n"
        "  허용: %s\n"
        "🔴 「민감도라서」·「bool 이라서」·「중요치 않아서」는 사유가 아니다 — "
        "문서에 값이 있으면 대조 대상으로 올릴 것." % (bad, list(_EXEMPTION_CATEGORIES)))

    # 비-공허: 두 범주가 «둘 다» 실제로 쓰이고 있는가.
    used = {c for c in _EXEMPTION_CATEGORIES
            if any(r.startswith(c) for r in _NOT_CROSSCHECKED_CONSTANTS.values())}
    assert used == set(_EXEMPTION_CATEGORIES), (
        "면제 범주 %s 가 아무 데도 안 쓰인다 — 범주가 실효를 잃었다"
        % sorted(set(_EXEMPTION_CATEGORIES) - used))


def test_doc_crosscheck_coverage_report(capsys):
    """기계 대조의 «사정거리» 를 매번 출력한다. 실패하지 않는다.

    🔴 이 숫자가 이 장치의 정직한 한계다 — 대조되는 상수만이 「갈라지면 잡힌다」.
    """
    with capsys.disabled():
        print("\n[문서↔상수] 기계 대조 %d개 · 미대조 %d개 (사유 명시)"
              % (len(_CROSSCHECKED_CONSTANTS), len(_NOT_CROSSCHECKED_CONSTANTS)))


# ===========================================================================
# 검사 9 — 🔴 `출처:` 줄번호가 «정말 그 줄» 을 가리키는가
# ===========================================================================
#
# 🔴 **이 절이 왜 생겼는가 — 정정 자체가 열거식이었다.**
#
# §13.2-17 은 *"손으로 옮겨 적으면 조용히 다른 것을 가리킨다"* 의 6번째 동형으로
# `출처:` 줄번호 **4건**(D-5·D-6·D-9·D-10)이 어긋난 것을 잡고 **손으로 고쳤다.**
# 그런데 다음 라운드의 기계 대조에서 **또 4건이 남아 있었고**, 이 검사를 만들자
# 거기서 **더 나왔다** — 최종적으로 **열거 10개 항목 = 정정된 인용 11건**이다.
# 🔧 **4차 정정**: 이전 판본은 *"총 9건"* 이라 적고 **아래 목록에 10개를 나열**했다.
#    단위가 둘이라 어긋난 것이다 — **항목(상수 묶음) 10** vs **인용 11**
#    (`ALPHA` 만 `:1082`·`:1039` **두 곳**이 어긋나 두 항목에 걸친다).
#    ⇒ 원본은 `frozen_constants.py` 의 `초안` 주석이며, 세어서 맞춘 값이다.
#
# 🔑 ***「열거식은 반드시 빠뜨린다」를 세운 판본이, 그 규칙의 정정 자체를 열거식으로 했다.***
#    ⇒ 교정은 「이번엔 더 꼼꼼히 세는 것」이 아니라 **세는 일을 그만두는 것**이다.
#      이 파일의 ALLOWLIST·검사 8 과 같은 설계다.
#
# ⚠️ **사정거리** — 이 검사가 «닿는» 것과 «안 닿는» 것:
#     🟢 파일 실재 · 줄 범위 · 인용 양끝이 빈 줄인가
#     🟢 `(§S …)` 앵커 ↔ 그 줄의 직전 «번호 붙은 절 제목»
#     🟢 `(D-N …)` 앵커 ↔ 그 줄에 `D-N` 이 있는가
#     🟢 괄호 안 인용부호/백틱 키워드 ↔ 그 줄에 있는가
#     🟢 **상수의 «값» 이 그 줄에 있는가** (원척도 · ×100(%) 두 표기 허용)
#     ❌ 값이 문서에 «수치로» 안 적힌 상수(정책 문자열·순서 튜플·bool)는 값 대조 불가
#     ❌ 절 «안에서» 한 행 어긋난 인용 중 값이 우연히 양쪽에 다 있는 경우
#
# 🔴 🔧 **4차 추가 — 값 대조가 `any` 라서 생기는 두 하위 경우 (실측 확인).**
#    `_value_is_present` 는 **상수 리터럴 집합 중 «하나라도»** 인용 줄에 있으면 통과한다.
#    ⇒ 아래 둘은 **원리적으로 못 잡는다.**
#     ❌ **복합 상수는 원소 하나만 살아 있어도 통과한다.**
#        실측: `ROUNDTRIP_COST_BY_YEAR` 의 `2021: 0.0026 → 0.0030` 변조가 **미탐**이다 —
#        `_const_abs_numbers` 가 **딕셔너리 «키»(2021…)까지** 값 집합에 넣는데 인용 줄
#        (`power/step3_mde.py:42`)에 그 키가 그대로 있어서, **세율이 바뀌어도 매치가 산다.**
#        🔴 하필 이 상수가 **0-d(동결 차단)의 대상**이다.
#     ❌ **×100 허용이 우연 충돌을 만든다.** 실측: `ALPHA` 의 인용을 `PREREG.md:1084`
#        → **1085 로 밀어도 통과**한다 — `0.05 × 100 = 5` 가 1085 줄의 `k=5` 와 매치한다.
#        (「원척도·×100 둘뿐」이라는 좁힘은 옳은 방향이지만 **충돌을 0 으로 만들지는 못한다.**)
#    ⇒ 🔑 ***이 두 경우는 「검사가 통과했다」가 「인용이 옳다」를 함의하지 않는 구간이다.***
#      복합 상수의 인용과 `α`·`k` 처럼 작은 정수와 충돌하는 값은 **사람이 한 번 더 볼 것.**

_CITE_RE = re.compile(
    r"([A-Za-z0-9_./]+\.(?:md|py)):(\d+)(?:-(\d+))?[ \t]*(?:\(([^)]*)\))?")
_DOC_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_NUMBERED_HEADING_RE = re.compile(r"^#{2,6}\s+(\d+(?:\.\d+)*)[.\s]")
_CITE_KEYWORD_RE = re.compile(r"[\"'`]([^\"'`]{2,})[\"'`]")

# 🔴 실재하지 않는 인용 원본 — **사유가 「휘발성 원본」 하나뿐이어야 한다.**
#    (Y2 와 같은 규약: 「중요치 않음」은 면제 사유가 아니다.)
_CITE_SOURCE_EXEMPT = {
    "cb_coverage2.py":
        "세션 스크래치패드(OS 임시 트리) — frozen_constants.py 가 이제 유일한 영속 사본이며, "
        "정규식은 «동작 재현»(test_n_lookback_parser_reproduces_prereg_counts)으로 동결됐다",
}


def _numbered_headings(text: str):
    return [(i, m.group(1))
            for i, line in enumerate(text.split("\n"), 1)
            for m in [_NUMBERED_HEADING_RE.match(line)] if m]


def _doc_numbers(text: str) -> set:
    return {float(x.replace(",", "")) for x in _DOC_NUM_RE.findall(text)}


def _citation_blocks():
    """[(상수이름들, 출처 주석 텍스트)] — `출처:` 주석과 그것이 설명하는 상수를 묶는다."""
    src = FROZEN.read_text(encoding="utf-8")
    lines = src.split("\n")
    tree = ast.parse(src)
    assigns = [(n.lineno, [t.id for t in n.targets if isinstance(t, ast.Name)])
               for n in tree.body if isinstance(n, ast.Assign)]

    starts = [i for i, l in enumerate(lines) if "출처:" in l]
    assert starts, "`출처:` 주석을 하나도 못 찾았다 — 이 검사가 vacuous 해졌다"

    out = []
    for idx, i in enumerate(starts):
        block = [lines[i]]
        j = i + 1
        while j < len(lines) and lines[j].lstrip().startswith("#"):
            if "출처:" in lines[j]:
                break
            block.append(lines[j])
            j += 1
        nxt = starts[idx + 1] + 1 if idx + 1 < len(starts) else len(lines) + 1
        owned = [nm for ln, names in assigns if i + 1 < ln < nxt for nm in names]
        out.append((owned, "\n".join(block)))
    return out


def _const_abs_numbers(name: str) -> set:
    """상수 리터럴의 절댓값 집합 (bool 제외)."""
    tree = ast.parse(FROZEN.read_text(encoding="utf-8"))
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in n.targets):
            return {abs(float(s.value)) for s in ast.walk(n.value)
                    if isinstance(s, ast.Constant)
                    and isinstance(s.value, (int, float))
                    and not isinstance(s.value, bool)}
    return set()


def _value_is_present(const_values: set, doc_values: set) -> bool:
    """상수 값이 인용 줄에 «어떤 표기로든» 있는가.

    ⚠️ 허용 표기는 **원척도와 ×100(백분율) 둘뿐**이다. 문서가 `0.50` 을 `50%` 로,
       `0.0005` 를 `0.05%p` 로 적기 때문이며, 그 이상 넓히면 아무 숫자나 맞는다.
    """
    for v in const_values:
        for scaled in (v, v * 100):
            if any(abs(scaled - d) <= 1e-9 * max(1.0, abs(scaled)) for d in doc_values):
                return True
    return False


def test_source_citations_point_at_the_right_lines():
    """🔴 `출처: FILE:N` 이 실제로 그 내용을 담은 줄인가 — 기계 대조.

    🔑 **고치기 «전» 에 돌려 9건을 잡았다** (직전 라운드가 손으로 4건을 찾은 뒤였다):
       `CB_T1_LOOKBACK_SENSITIVITY_L`(588→587) · `CB_N_UNPARSED_*`(591→589) ·
       `ROUNDTRIP_COST_FIXED_SENSITIVITY`(464→466) · `SLIPPAGE`(466→467) ·
       `MATCH_CELL_EXPANSION_*`(676-677→675-676) · `PRIMARY_K`·`ALPHA`(1082→1084) ·
       `SECONDARY_K_FAMILY`(1086→1087) · `ALPHA`·`POWER`(1039→1032) ·
       `PRIMARY_STRATUM`(849-850→848-849) · `STRATA`(839-863→839-862).
    """
    problems = []
    checked = 0
    file_cache = {}

    for owned, block in _citation_blocks():
        const_values = set()
        for nm in owned:
            const_values |= _const_abs_numbers(nm)
        who = ",".join(owned) or "(상수 없음)"

        for m in _CITE_RE.finditer(block):
            rel, a = m.group(1), int(m.group(2))
            b = int(m.group(3)) if m.group(3) else a
            anchor = (m.group(4) or "").strip()

            if Path(rel).name in _CITE_SOURCE_EXEMPT:
                continue
            path = TASSO / rel
            if not path.exists():
                problems.append("  [%s] %s:%d — 인용 원본이 없다 (면제하려면 "
                                "_CITE_SOURCE_EXEMPT 에 «휘발성» 사유로 등재)" % (who, rel, a))
                continue

            if rel not in file_cache:
                file_cache[rel] = path.read_text(encoding="utf-8-sig")
            text = file_cache[rel]
            flines = text.split("\n")
            checked += 1

            if not (1 <= a <= b <= len(flines)):
                problems.append("  [%s] %s:%d-%d — 줄 범위 밖 (총 %d줄)"
                                % (who, rel, a, b, len(flines)))
                continue

            seg = flines[a - 1:b]
            segtext = "\n".join(seg)

            # ① 인용 «양끝» 이 빈 줄이면 안 된다. (범위 내부의 빈 줄은 정상이다.)
            for edge, ln in ((seg[0], a), (seg[-1], b)):
                if not edge.strip():
                    problems.append("  [%s] %s:%d-%d — 인용 경계 %d 가 «빈 줄» 이다"
                                    % (who, rel, a, b, ln))

            # ② 괄호 안 인용부호/백틱 키워드가 그 줄에 있는가.
            #    ⚠️ `…`/`...` 로 «줄인» 인용은 조각별로 본다 — 생략 부호 자체는 원본에 없다.
            keywords = [k for k in _CITE_KEYWORD_RE.findall(anchor)] if anchor else []
            for kw in keywords:
                frags = [f.strip() for f in re.split(r"\.{3}|…", kw) if f.strip()]
                missing = [f for f in frags if f not in segtext]
                if missing:
                    problems.append("  [%s] %s:%d-%d — 앵커 키워드 %r 의 조각 %s 가 "
                                    "인용 줄에 없다" % (who, rel, a, b, kw, missing))

            sec = re.match(r"§(\d+(?:\.\d+)*)", anchor) if anchor else None
            dec = re.match(r"(D-\d+)", anchor) if anchor else None

            # ③ `(D-N …)` — 키워드가 따로 없을 때만. (`D-7 아래 "…"` 는 키워드가 판정한다.)
            if dec and not keywords and dec.group(1) not in segtext:
                problems.append("  [%s] %s:%d-%d — 앵커 %s 가 인용 줄에 없다"
                                % (who, rel, a, b, dec.group(1)))

            # ④ `(§S …)` — 그 줄의 직전 «번호 붙은 절 제목» 과 정합하는가.
            if sec and rel.endswith(".md"):
                heads = [s for ln, s in _numbered_headings(text) if ln <= a]
                cur = heads[-1] if heads else None
                want = sec.group(1)
                if cur is None or not (want.startswith(cur) or cur.startswith(want)):
                    problems.append(
                        "  [%s] %s:%d-%d — 앵커 §%s 인데 직전 절 제목은 §%s"
                        % (who, rel, a, b, want, cur))

            # ⑤ 🔴 상수의 «값» 이 그 줄에 있는가. 값 대조가 이 검사의 판별력 대부분이다.
            if const_values and (sec or rel.endswith(".py")):
                if not _value_is_present(const_values, _doc_numbers(segtext)):
                    problems.append(
                        "  [%s] %s:%d-%d — 상수값 %s 이 인용 줄에 없다 (원척도·×100 둘 다 대조)\n"
                        "        인용 내용: %s"
                        % (who, rel, a, b, sorted(const_values), segtext.strip()[:90]))

    assert checked >= 25, (
        "인용을 %d건밖에 못 뽑았다 — 추출 정규식이 깨졌고 이 검사가 vacuous 해졌다" % checked)
    header = ("🔴 `출처:` 줄번호가 실제 내용과 갈라졌다 (%d건 대조 중).\n"
              "   §13.2-1: 손으로 옮겨 적으면 «값» 이 아니라 «출처» 가 조용히 옮겨간다.\n"
              % checked)
    assert not problems, header + "\n".join(problems)


def test_source_citation_coverage_report(capsys):
    """`출처:` 기계 대조의 사정거리를 매번 출력한다. 실패하지 않는다."""
    n_cite = sum(len(_CITE_RE.findall(b)) for _, b in _citation_blocks())
    n_exempt = sum(1 for _, b in _citation_blocks()
                   for m in _CITE_RE.finditer(b)
                   if Path(m.group(1)).name in _CITE_SOURCE_EXEMPT)
    with capsys.disabled():
        print("\n[출처 대조] 인용 %d건 · 원본 부재 면제 %d건 (휘발성 사유)"
              % (n_cite, n_exempt))
