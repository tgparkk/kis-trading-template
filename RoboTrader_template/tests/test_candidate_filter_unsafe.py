"""CandidateSelector 안전성 필터 — 실응답 채록본 기반 값 계약 회귀.

배경 (2026-08-09):
  이 파일의 옛 버전은 `_make_info(iscd_stat_cls_code="00", vi_cls_code="0",
  mang_issu_yn=..., ssts_hot_yn=...)` 로 **코드의 가정을 그대로 베낀 픽스처**를
  손으로 만들어 주입했다. 그래서 필드 이름과 값 도메인이 통째로 틀렸는데도
  테스트는 전부 초록불이었다. 심지어 공급자 함수
  `api.kis_market_api.get_stock_basic_info` 는 **존재조차 하지 않았고**,
  호출부의 try/except 가 ImportError 를 삼켜 필터는 수개월간 전건 통과였다.

  → 자기가 만든 픽스처로 자기 가정을 검사하면 계약 오류는 영원히 안 잡힌다.

수정 구조:
  1. 술어 테스트는 **채록본**(tests/fixtures/kis_stock_basic_info_recorded.json,
     2026-08-09 전 유니버스 2,574종목 실응답)에서만 입력을 얻는다.
     이 케이스들에 대해 응답 dict 를 손으로 쓰지 말 것.
  2. 공급자 심볼의 **계약 테스트**(import 가능·호출 가능)를 둔다. 이 회귀가
     없어서 결함이 살아남았다. 네트워크는 쓰지 않는다.
  3. 배제 주장뿐 아니라 **통과 주장도 대칭으로** 검사한다(프로젝트 규칙).
     특히 ssts_yn='Y'(공매도가능 = 시장의 2,566/2,574)와 시장경고 종목은
     반드시 통과해야 한다.
  4. 안전필터를 우회하던 screener_snapshots 경로 회귀.

값 계약 (실측):
  거래정지 iscd_stat_cls_code=='58' | 임시정지 temp_stop_yn=='Y'
  관리종목 mang_issu_cls_code=='Y'   | 정리매매 sltr_yn=='Y'
  VI       vi_cls_code=='Y'
  배제 대상 아님: mrkt_warn_cls_code(시장경고) · invt_caful_yn(투자유의)
"""

import json
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional

import pytest
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.candidate_selector import CandidateSelector, CandidateStock
from core.models import TradingConfig


# ============================================================================
# 채록본 로더 — 이 파일에서 KIS 응답 dict 를 손으로 만드는 유일한 예외는
# VI 파생(아래 _with_vi_active)뿐이며 그 이유를 거기 명시한다.
# ============================================================================

FIXTURE_PATH = ROOT / "tests" / "fixtures" / "kis_stock_basic_info_recorded.json"

with open(FIXTURE_PATH, "r", encoding="utf-8") as _f:
    _FIXTURE = json.load(_f)

GROUPS: Dict[str, List[Dict]] = _FIXTURE["groups"]

# 전 유니버스 2,574행 집계표. 주석·docstring 이 인용하는 headline 카운트의 근거이며,
# 원본 채록(948KB)을 리포에 넣지 않는 대신 이 표를 커밋한다.
COUNTS_PATH = ROOT / "tests" / "fixtures" / "kis_field_value_counts.json"
with open(COUNTS_PATH, "r", encoding="utf-8") as _f:
    COUNTS = json.load(_f)
BY_CODE: Dict[str, Dict] = {
    row["code"]: row for rows in GROUPS.values() for row in rows
}


def group(name: str) -> List[Dict]:
    """채록본 그룹을 꺼낸다. 그룹이 사라지면 즉시 실패시킨다(픽스처 표류 방지)."""
    assert name in GROUPS, f"채록본에 '{name}' 그룹이 없다: {sorted(GROUPS)}"
    rows = GROUPS[name]
    assert rows, f"채록본 '{name}' 그룹이 비어 있다"
    return rows


def all_rows() -> List[Dict]:
    return [row for rows in GROUPS.values() for row in rows]


def normal_rows() -> List[Dict]:
    return group("정상_신용가능") + group("정상_증거금100")


def _with_vi_active(row: Dict) -> Dict:
    """VI 발동 응답 파생.

    채록 시각이 일요일이라 vi_cls_code=='Y' 인 종목이 0건이었다(값 도메인 자체는
    2,574종목 전수에서 Y/N 으로 확인됨). 따라서 VI 만큼은 **채록된 정상 응답의
    vi_cls_code 한 칸만** 도메인 내 값으로 바꿔 파생한다. 다른 필드는 손대지 않는다.
    """
    derived = dict(row)
    derived["vi_cls_code"] = "Y"
    return derived


@contextmanager
def capture_logs(logger, level=logging.INFO):
    """이 프로젝트의 로거는 propagate=False 라 caplog 로는 안 잡힌다.

    → 대상 로거에 직접 핸들러를 붙여 레코드를 모은다.
    """
    records: List[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Collector(level=level)
    prev_level = logger.level
    logger.setLevel(min(prev_level, level) if prev_level else level)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)


@pytest.fixture
def selector():
    return CandidateSelector(config=TradingConfig(), broker=MagicMock())


def _make_candidate(code: str, name: str = "테스트종목") -> CandidateStock:
    return CandidateStock(code=code, name=name, market="KOSPI", score=50.0, reason="test")


def run_snapshot_path(selector, monkeypatch, codes, max_candidates=10, queried=None):
    """screener_snapshots 1순위 분기를 네트워크·DB 없이 태운다.

    queried 리스트를 주면 안전정보를 **실제로 조회한 코드**가 순서대로 쌓인다
    (지연 필터링 검증용).
    """
    import core.screener_snapshot_provider as provider_mod

    monkeypatch.setattr(
        provider_mod, "make_screener_snapshot_provider",
        lambda strategy_name: (lambda name, day: list(codes)),
    )

    # 폴백 경로로 새면 테스트 의미가 없다(DB·파일 접근도 막는다).
    def _no_fallback(*args, **kwargs):
        pytest.fail("스냅샷 분기가 아니라 스크리너 JSON 폴백으로 샜다")

    monkeypatch.setattr(selector, "load_from_screener", _no_fallback)

    def _lookup(code):
        if queried is not None:
            queried.append(code)
        return BY_CODE.get(code)

    monkeypatch.setattr(selector, "_get_stock_safety_info", _lookup)
    return selector._fetch_candidates_for_strategy("test_strategy", max_candidates)


def _filter_codes(selector: CandidateSelector, rows: List[Dict]) -> List[str]:
    """채록 행 목록을 후보로 만들어 안전필터를 태우고 통과 코드를 돌려준다."""
    candidates = [_make_candidate(r["code"], r.get("name", "")) for r in rows]
    by_code = {r["code"]: r for r in rows}
    result = selector._filter_unsafe_stocks(candidates, _get_info_fn=lambda c: by_code.get(c))
    return [c.code for c in result]


# ============================================================================
# 0-A. headline 카운트 재현 — 코드 주석이 인용하는 숫자의 출처
# ============================================================================

class TestRecordedCounts:
    """주석·docstring 이 인용하는 122/116/43/2,566/1,584/44 를 재현 가능하게 고정한다.

    원본 2,574행 채록은 리포에 없다. 이 집계표가 그 자리를 대신하므로, 표가
    자기모순이면(합계 불일치 등) 인용된 숫자도 못 믿는다 → 여기서 깨져야 한다.
    """

    UNIVERSE = 2574

    def test_meta_universe(self):
        assert COUNTS["_meta"]["universe"] == self.UNIVERSE

    @pytest.mark.parametrize("field", [
        "iscd_stat_cls_code", "mang_issu_cls_code", "sltr_yn",
        "vi_cls_code", "temp_stop_yn", "mrkt_warn_cls_code",
        "invt_caful_yn", "ssts_yn",
    ])
    def test_value_counts_sum_to_universe(self, field):
        """필드별 값 카운트 합 == 유니버스. 어긋나면 표가 깨진 것."""
        counts = COUNTS["field_value_counts"][field]
        assert sum(counts.values()) == self.UNIVERSE, field

    @pytest.mark.parametrize("key,field,value", [
        ("iscd_stat_cls_code_58_거래정지", "iscd_stat_cls_code", "58"),
        ("iscd_stat_cls_code_51_관리종목슬롯", "iscd_stat_cls_code", "51"),
        ("iscd_stat_cls_code_57_증거금100", "iscd_stat_cls_code", "57"),
        ("mang_issu_cls_code_Y_관리종목", "mang_issu_cls_code", "Y"),
        ("sltr_yn_Y_정리매매", "sltr_yn", "Y"),
        ("ssts_yn_Y_공매도가능", "ssts_yn", "Y"),
    ])
    def test_derived_matches_raw_counts(self, key, field, value):
        """derived 의 headline 숫자가 원시 카운트에서 그대로 나오는지."""
        assert COUNTS["derived"][key] == COUNTS["field_value_counts"][field].get(value, 0)

    def test_headline_numbers_quoted_in_code(self):
        """코드 주석이 인용하는 숫자 그 자체."""
        d = COUNTS["derived"]
        assert d["iscd_stat_cls_code_58_거래정지"] == 122
        assert d["mang_issu_cls_code_Y_관리종목"] == 116
        assert d["iscd_stat_cls_code_51_관리종목슬롯"] == 43
        assert d["ssts_yn_Y_공매도가능"] == 2566
        assert d["iscd_stat_cls_code_57_증거금100"] == 1584
        assert d["mrkt_warn_cls_code_non_00_시장경고"] == 44
        assert d["iscd_stat_cls_code_not_55"] == 1798
        assert d["sltr_yn_Y_정리매매"] == 1

    def test_iscd51_is_strict_subset_of_managed(self):
        """'51'로 관리종목을 판별하면 73종목을 놓친다는 주장의 근거."""
        d = COUNTS["derived"]
        assert d["iscd51_is_strict_subset_of_mang_Y"] is True
        assert d["mang_Y_missed_if_using_iscd51"] == 73
        assert (d["mang_issu_cls_code_Y_관리종목"]
                - d["iscd_stat_cls_code_51_관리종목슬롯"]) == 73

    def test_vi_active_was_never_observed(self):
        """🔴 'Y'=발동 은 추정이지 관측이 아니다 — 그 사실 자체를 고정한다.

        누군가 주석을 «2,574종목에서 Y/N 도메인 확인» 으로 되돌리면, 근거가 될
        관측치가 0 이라는 이 테스트와 정면으로 어긋난다.
        """
        assert COUNTS["derived"]["vi_cls_code_Y_관측"] == 0
        assert COUNTS["field_value_counts"]["vi_cls_code"] == {"N": self.UNIVERSE}

    def test_excerpt_values_exist_in_full_recording(self):
        """18행 발췌의 모든 값이 전수 집계표에 존재해야 한다(두 픽스처 정합)."""
        tracked = set(COUNTS["field_value_counts"])
        for row in all_rows():
            for field, value in row.items():
                if field not in tracked:
                    continue
                key = "<absent>" if value is None else str(value)
                counts = COUNTS["field_value_counts"][field]
                assert counts.get(key, 0) > 0, f"{row['code']} {field}={key}"

    def test_empty_shell_codes_include_excerpt(self):
        shells = set(COUNTS["derived"]["empty_shell_codes"])
        assert len(shells) == 5
        assert {r["code"] for r in group("빈응답")} <= shells


# ============================================================================
# 0-B. 공급자 심볼 계약 — 결함의 본체였던 회귀
# ============================================================================

class TestSupplierContract:
    """`api.kis_market_api.get_stock_basic_info` 가 실재해야 한다.

    이 심볼이 없던 게 결함의 뿌리다(호출부 2곳이 try/except 로 ImportError 를
    삼켜 안전필터·라이브 VI 가드가 동시에 영구 무효였다). 심볼이 다시 사라지면
    여기서 반드시 깨져야 한다. 네트워크는 호출하지 않는다.
    """

    def test_supplier_symbol_is_importable(self):
        from api.kis_market_api import get_stock_basic_info
        assert callable(get_stock_basic_info)

    def test_supplier_accepts_single_stock_code_argument(self):
        import inspect
        from api.kis_market_api import get_stock_basic_info

        params = list(inspect.signature(get_stock_basic_info).parameters)
        assert params == ["stock_code"], f"공급자 시그니처 변경: {params}"

    def test_supplier_returns_none_on_empty_response(self, monkeypatch):
        """응답이 None/빈 DataFrame 이면 None (호출부의 «보수적 통과» 분기 진입)."""
        import pandas as pd
        import api.kis_market_api as market_api

        monkeypatch.setattr(market_api, "get_inquire_price", lambda **kw: None)
        assert market_api.get_stock_basic_info("005930") is None

        monkeypatch.setattr(market_api, "get_inquire_price", lambda **kw: pd.DataFrame())
        assert market_api.get_stock_basic_info("005930") is None

    def test_supplier_returns_first_row_as_dict(self, monkeypatch):
        """정상 응답이면 output 1행을 dict 로 돌려준다 (채록 행으로 왕복 검사)."""
        import pandas as pd
        import api.kis_market_api as market_api

        recorded = group("거래정지_58")[0]
        monkeypatch.setattr(
            market_api, "get_inquire_price",
            lambda **kw: pd.DataFrame([recorded], index=[0]),
        )
        info = market_api.get_stock_basic_info(recorded["code"])
        assert isinstance(info, dict)
        assert info["iscd_stat_cls_code"] == "58"


# ============================================================================
# 1. 거래정지 — iscd_stat_cls_code == '58'
# ============================================================================

class TestTradingHalt:
    def test_halted_rows_are_detected(self, selector):
        for row in group("거래정지_58"):
            assert selector._is_trading_halted(row) is True, row["code"]

    def test_halted_rows_are_excluded(self, selector):
        rows = group("거래정지_58")
        assert _filter_codes(selector, rows) == []

    def test_normal_rows_are_not_halted(self, selector):
        """대칭 주장: 정상 종목은 거래정지로 잡히면 안 된다."""
        for row in normal_rows():
            assert selector._is_trading_halted(row) is False, row["code"]

    def test_margin100_status_is_not_halt(self, selector):
        """함정: iscd_stat_cls_code != '55' 를 이상으로 보면 안 된다.

        '57'(증거금100%)이 유니버스 최다(1,584종목)이며 정상 거래된다.
        """
        for row in group("정상_증거금100"):
            assert row["iscd_stat_cls_code"] == "57"
            assert selector._is_trading_halted(row) is False

    def test_temp_stop_is_halt(self, selector):
        """임시정지(temp_stop_yn=='Y')도 거래정지로 본다."""
        row = dict(normal_rows()[0], temp_stop_yn="Y")
        assert selector._is_trading_halted(row) is True


# ============================================================================
# 2. VI — vi_cls_code == 'Y'
# ============================================================================

class TestVIActive:
    def test_vi_y_is_active(self, selector):
        assert selector._is_vi_active(_with_vi_active(normal_rows()[0])) is True

    def test_vi_y_row_is_excluded(self, selector):
        rows = [_with_vi_active(normal_rows()[0])]
        assert _filter_codes(selector, rows) == []

    def test_vi_n_is_not_active(self, selector):
        """대칭 주장: 채록된 2,574종목 전부 vi_cls_code=='N' 이었다."""
        checked = 0
        for row in all_rows():
            if row.get("vi_cls_code") == "N":
                assert selector._is_vi_active(row) is False, row["code"]
                checked += 1
        assert checked > 0, "vi_cls_code='N' 행이 하나도 없다 — 픽스처 표류"

    @pytest.mark.parametrize("legacy_code", ["1", "2", "3"])
    def test_numeric_vi_codes_are_not_the_contract(self, selector, legacy_code):
        """옛 계약('1'/'2'/'3')은 실응답 값 도메인에 없다.

        숫자로 읽던 구현이 항상 False 를 내며 가드를 영구 no-op 으로 만들었다.
        이 테스트는 «숫자를 VI 로 되돌리면» 실패한다.
        """
        row = dict(normal_rows()[0], vi_cls_code=legacy_code)
        assert selector._is_vi_active(row) is False


# ============================================================================
# 3. 관리종목 — mang_issu_cls_code == 'Y'
# ============================================================================

class TestManagedIssue:
    def test_managed_rows_detected_regardless_of_iscd_slot(self, selector):
        """함정: iscd_stat_cls_code=='51' 은 관리종목 SSOT 가 아니다.

        {iscd=='51'}(43종목)은 {mang_issu_cls_code=='Y'}(116종목)의 진부분집합이라
        '51'로 판별하면 73종목을 놓친다. iscd 가 '51'이든 '58'이든 mang 이 'Y'면
        관리종목으로 잡혀야 한다.
        """
        for row in group("관리종목_iscd51") + group("관리종목_iscd58"):
            assert row["mang_issu_cls_code"] == "Y"
            assert selector._is_managed_issue(row) is True, row["code"]

        iscd_slots = {r["iscd_stat_cls_code"] for r in group("관리종목_iscd58")}
        assert iscd_slots == {"58"}, "iscd 가 51이 아닌 관리종목 표본이 필요하다"

    def test_managed_rows_are_excluded(self, selector):
        assert _filter_codes(selector, group("관리종목_iscd51")) == []

    def test_normal_rows_are_not_managed(self, selector):
        for row in normal_rows():
            assert selector._is_managed_issue(row) is False, row["code"]

    def test_legacy_field_name_does_not_exist(self):
        """함정: mang_issu_yn 은 실응답에 없는 필드다(옛 구현이 이걸 읽었다).

        18행 발췌가 아니라 **전 유니버스 2,574행 집계표**의 필드 목록으로 검사한다
        (발췌만 보면 «아무도 그 이름을 픽스처에 타이핑하지 않았다» 밖에 증명 못 한다).
        """
        assert "mang_issu_yn" not in COUNTS["observed_fields"]
        assert "mang_issu_yn" in COUNTS["absent_field_names"]["names"]


# ============================================================================
# 4. 정리매매 — sltr_yn == 'Y'  (❌ ssts_yn 아님)
# ============================================================================

class TestLiquidationTrading:
    def test_sltr_row_is_detected(self, selector):
        row = group("정리매매_sltr")[0]
        assert row["sltr_yn"] == "Y"
        assert selector._is_liquidation_trading(row) is True

    def test_sltr_row_is_excluded(self, selector):
        assert _filter_codes(selector, group("정리매매_sltr")) == []

    def test_ssts_yn_is_short_sale_eligibility_not_liquidation(self, selector):
        """🔴 최대 함정: ssts_yn 은 «공매도가능여부»다.

        실측상 2,566/2,574(삼성전자 포함)가 'Y' 라서 정리매매로 오독하면 시장
        거의 전체가 후보에서 사라진다. ssts_yn=='Y' 인 정상 종목은 반드시 통과해야
        한다(대칭 주장).
        """
        ssts_y_normals = [r for r in normal_rows() if r.get("ssts_yn") == "Y"]
        assert ssts_y_normals, "채록본에 ssts_yn='Y' 정상 종목이 있어야 한다"

        for row in ssts_y_normals:
            assert selector._is_liquidation_trading(row) is False, row["code"]

        assert _filter_codes(selector, ssts_y_normals) == [r["code"] for r in ssts_y_normals]

    def test_legacy_field_name_does_not_exist(self):
        """함정: ssts_hot_yn / mrkt_trtm_cls_code 는 실응답에 없는 필드다.

        전 유니버스 2,574행 집계표의 필드 목록으로 검사한다(발췌 18행이 아니라).
        """
        for name in ("ssts_hot_yn", "mrkt_trtm_cls_code"):
            assert name not in COUNTS["observed_fields"], name
            assert name in COUNTS["absent_field_names"]["names"], name


# ============================================================================
# 5. 시장경고·투자유의 — **배제 사유가 아니다** (사장님 결정 2026-08-09)
# ============================================================================

class TestMarketWarningIsNotExcluded:
    """주문 적격성이 아니라 알파 주장이므로 후보에서 빼지 않는다.

    옛 구현은 mrkt_warn_cls_code != '00' 과 invt_caful_yn=='Y' 를 «관리종목» 으로
    묶어 배제했다. 범위를 되돌리면 여기서 깨진다.
    """

    def test_market_warning_02_passes(self, selector):
        rows = group("시장경고_02")
        assert _filter_codes(selector, rows) == [r["code"] for r in rows]

    def test_market_warning_01_passes(self, selector):
        rows = group("시장경고_01")
        assert _filter_codes(selector, rows) == [r["code"] for r in rows]

    def test_invt_caful_passes(self, selector):
        row = dict(normal_rows()[0], invt_caful_yn="Y")
        assert _filter_codes(selector, [row]) == [row["code"]]

    def test_warning_is_still_visible_as_log_note(self, selector):
        """배제하지 않되 보이기는 해야 한다(로그용 주석)."""
        assert "시장경고" in selector._market_warning_note(group("시장경고_02")[0])
        assert selector._market_warning_note(normal_rows()[0]) == ""


# ============================================================================
# 6. 판정불가(빈껍데기 응답) — dict 를 받았다고 안전이 아니다
# ============================================================================

class TestUndecidable:
    def test_empty_shell_rows_are_detected(self, selector):
        for row in group("빈응답"):
            assert selector._is_undecidable(row) is True, row["code"]

    def test_empty_shell_rows_are_excluded(self, selector):
        """빈껍데기는 비거래 종목이다. 통과시키면 «모른다»를 «안전»으로 접는 것."""
        assert _filter_codes(selector, group("빈응답")) == []

    def test_empty_shell_is_not_mistaken_for_normal(self, selector):
        """함정: 빈껍데기는 iscd_stat_cls_code 가 '00'(정상처럼 보임)이고
        temp_stop_yn/vi_cls_code 는 'N' 이라 술어 4종으로는 전부 통과한다.
        """
        for row in group("빈응답"):
            assert selector._is_trading_halted(row) is False
            assert selector._is_vi_active(row) is False
            assert selector._is_managed_issue(row) is False
            assert selector._is_liquidation_trading(row) is False

    def test_real_rows_are_decidable(self, selector):
        """대칭 주장: 실제 응답이 온 종목은 판정불가가 아니다."""
        shells = {r["code"] for r in group("빈응답")}
        checked = 0
        for row in all_rows():
            if row["code"] in shells:
                continue
            assert selector._is_undecidable(row) is False, row["code"]
            checked += 1
        assert checked > 0, "빈응답 아닌 행이 하나도 없다 — 픽스처 표류"

    def test_aggregate_undecidable_raises_warning(self, selector):
        """스키마 파손은 전역 사건이므로 전역 사건처럼 보여야 한다.

        판정불가가 임계(20%·최소 3건)를 넘으면 종목별 INFO 말고 WARNING 한 줄이
        떠야 한다. 안 그러면 «전 종목 제외 → 전 전략 후보 0건» 이 조용히 벌어진다.
        """
        shell = group("빈응답")[0]
        candidates = [_make_candidate(f"90000{i}") for i in range(5)]

        with capture_logs(selector.logger, logging.WARNING) as records:
            result = selector._filter_unsafe_stocks(
                candidates, _get_info_fn=lambda c: dict(shell)
            )

        assert result == []
        matched = [r for r in records if "스키마 변경을 의심" in r.getMessage()]
        assert matched, [r.getMessage() for r in records]
        assert all(r.levelno >= logging.WARNING for r in matched)

    def test_isolated_undecidable_does_not_raise_warning(self, selector):
        """대칭 주장: 비거래 종목 1건이 섞인 정상 상황은 경보가 아니다."""
        rows = normal_rows() + group("시장경고_02") + [group("빈응답")[0]]

        with capture_logs(selector.logger, logging.WARNING) as records:
            _filter_codes(selector, rows)

        assert not [r for r in records if "스키마 변경을 의심" in r.getMessage()]


# ============================================================================
# 6-B. 필드 정규화 — 15개 변이 중 유일하게 살아남았던 구멍
# ============================================================================

class TestFieldNormalization:
    """`_field` 의 .strip()/.upper() 를 지워도 다른 테스트가 전부 통과했다.

    KIS 는 값에 공백을 붙여 보낸다(채록본의 빈껍데기 응답은 name 이 ' ').
    정규화가 사라지면 ' Y' 가 «판정 가능한 정상값» 으로 읽혀 지뢰가 통과한다.
    """

    PADDED_YES = ["Y", "Y ", " Y", " Y ", "y", "\tY"]
    BLANKS = [" ", "", None, "\t", "   "]

    @pytest.mark.parametrize("value", PADDED_YES)
    def test_managed_issue_survives_padding(self, selector, value):
        row = dict(normal_rows()[0], mang_issu_cls_code=value)
        assert selector._is_managed_issue(row) is True, repr(value)

    @pytest.mark.parametrize("value", PADDED_YES)
    def test_liquidation_survives_padding(self, selector, value):
        row = dict(normal_rows()[0], sltr_yn=value)
        assert selector._is_liquidation_trading(row) is True, repr(value)

    @pytest.mark.parametrize("value", PADDED_YES)
    def test_vi_survives_padding(self, selector, value):
        row = dict(normal_rows()[0], vi_cls_code=value)
        assert selector._is_vi_active(row) is True, repr(value)

    @pytest.mark.parametrize("value", ["58", "58 ", " 58", " 58 "])
    def test_halt_survives_padding(self, selector, value):
        row = dict(normal_rows()[0], iscd_stat_cls_code=value)
        assert selector._is_trading_halted(row) is True, repr(value)

    @pytest.mark.parametrize("value", PADDED_YES)
    def test_temp_stop_survives_padding(self, selector, value):
        row = dict(normal_rows()[0], temp_stop_yn=value)
        assert selector._is_trading_halted(row) is True, repr(value)

    @pytest.mark.parametrize("blank", BLANKS)
    def test_blank_decisive_fields_are_undecidable(self, selector, blank):
        """공백/빈 문자열/None 은 전부 «값 없음» → 판정불가."""
        row = dict(normal_rows()[0])
        for field in CandidateSelector._DECISIVE_INFO_FIELDS:
            row[field] = blank
        assert selector._is_undecidable(row) is True, repr(blank)

    @pytest.mark.parametrize("value", PADDED_YES)
    def test_padded_unsafe_row_is_excluded_end_to_end(self, selector, value):
        """술어뿐 아니라 필터 결과까지 — 공백 붙은 관리종목은 배제돼야 한다."""
        row = dict(normal_rows()[0], mang_issu_cls_code=value)
        assert _filter_codes(selector, [row]) == []

    def test_nan_is_treated_as_missing(self, selector):
        """NaN 을 값으로 읽으면 'NAN' 이 «판정 가능한 안전값» 이 된다.

        공급자가 pandas 경유(df.iloc[0].to_dict())라 결측이 None 이 아니라 NaN 으로
        들어올 수 있다 — 「모른다」를 「안전」으로 접는 경로.
        """
        nan = float("nan")
        row = dict(normal_rows()[0])
        for field in CandidateSelector._DECISIVE_INFO_FIELDS:
            row[field] = nan
        assert selector._is_undecidable(row) is True
        assert selector._field(row, "mang_issu_cls_code") == ""

    def test_normal_values_are_unaffected(self, selector):
        """대칭 주장: 정규화가 정상 종목을 지뢰로 만들지 않는다."""
        for row in normal_rows():
            assert selector._is_managed_issue(row) is False
            assert selector._is_liquidation_trading(row) is False
            assert selector._is_vi_active(row) is False
            assert selector._is_trading_halted(row) is False
            assert selector._is_undecidable(row) is False


class TestMarketHoursFieldNormalization:
    """`arm_circuit_breaker_from_info` 의 필드 리더도 같은 정규화를 지켜야 한다."""

    @pytest.mark.parametrize("value", ["Y", "Y ", " Y", "y"])
    def test_vi_padding_arms(self, value):
        from config.market_hours import arm_circuit_breaker_from_info, CircuitBreakerState

        cb = CircuitBreakerState()
        info = dict(normal_rows()[0], vi_cls_code=value)
        assert arm_circuit_breaker_from_info("005930", info, cb) is True, repr(value)

    @pytest.mark.parametrize("value", ["58", "58 ", " 58"])
    def test_halt_padding_arms(self, value):
        from config.market_hours import arm_circuit_breaker_from_info, CircuitBreakerState

        cb = CircuitBreakerState()
        info = dict(normal_rows()[0], iscd_stat_cls_code=value)
        assert arm_circuit_breaker_from_info("005930", info, cb) is True, repr(value)

    @pytest.mark.parametrize("value", ["Y", " Y", "y"])
    def test_temp_stop_padding_arms(self, value):
        from config.market_hours import arm_circuit_breaker_from_info, CircuitBreakerState

        cb = CircuitBreakerState()
        info = dict(normal_rows()[0], temp_stop_yn=value)
        assert arm_circuit_breaker_from_info("005930", info, cb) is True, repr(value)

    def test_nan_does_not_arm_and_does_not_crash(self):
        from config.market_hours import arm_circuit_breaker_from_info, CircuitBreakerState

        cb = CircuitBreakerState()
        info = dict(normal_rows()[0], vi_cls_code=float("nan"),
                    iscd_stat_cls_code=float("nan"), temp_stop_yn=float("nan"))
        assert arm_circuit_breaker_from_info("005930", info, cb) is False

    def test_blank_values_do_not_arm(self):
        """대칭 주장: 공백은 «발동» 이 아니다(오탐으로 정상매수를 막지 않는다)."""
        from config.market_hours import arm_circuit_breaker_from_info, CircuitBreakerState

        cb = CircuitBreakerState()
        info = dict(normal_rows()[0], vi_cls_code=" ", temp_stop_yn="  ")
        assert arm_circuit_breaker_from_info("005930", info, cb) is False


# ============================================================================
# 7. 혼합 풀 / API 실패 시 보수적 통과
# ============================================================================

class TestMixedPoolAndFailures:
    def test_mixed_pool_keeps_only_tradable(self, selector):
        rows = (
            normal_rows()
            + group("거래정지_58")
            + group("관리종목_iscd51")
            + group("정리매매_sltr")
            + group("시장경고_02")
            + group("빈응답")
        )
        passed = set(_filter_codes(selector, rows))
        expected = {r["code"] for r in normal_rows() + group("시장경고_02")}
        assert passed == expected

    def test_api_failure_passes_conservatively(self, selector):
        candidates = [_make_candidate("999999")]
        result = selector._filter_unsafe_stocks(candidates, _get_info_fn=lambda c: None)
        assert [c.code for c in result] == ["999999"]

    def test_api_failure_is_logged_at_info(self, selector):
        """조회 실패가 «보이지 않던» 것이 결함의 수명이었다 → debug 아니고 INFO."""
        with capture_logs(selector.logger, logging.INFO) as records:
            selector._filter_unsafe_stocks(
                [_make_candidate("999999")], _get_info_fn=lambda c: None
            )
        matched = [r for r in records if "보수적 통과" in r.getMessage()]
        assert matched, [r.getMessage() for r in records]
        assert all(r.levelno >= logging.INFO for r in matched)

    def test_empty_candidates(self, selector):
        assert selector._filter_unsafe_stocks([], _get_info_fn=lambda c: None) == []

    def test_predicates_are_false_on_empty_dict(self, selector):
        assert selector._is_trading_halted({}) is False
        assert selector._is_vi_active({}) is False
        assert selector._is_managed_issue({}) is False
        assert selector._is_liquidation_trading({}) is False


# ============================================================================
# 8. 공급자 연결 — 조회 실패/캐시
# ============================================================================

class TestSafetyInfoSupplierWiring:
    def test_import_failure_is_logged_at_warning(self, selector, monkeypatch):
        """공급자 import 실패는 WARNING 이어야 한다.

        정확히 이 실패가 debug 로도 안 남아서 필터 무효가 수개월간 안 보였다.
        """
        import types

        broken = types.ModuleType("api.kis_market_api")  # get_stock_basic_info 없음
        monkeypatch.setitem(sys.modules, "api.kis_market_api", broken)

        with capture_logs(selector.logger, logging.WARNING) as records:
            assert selector._get_stock_safety_info("005930") is None

        matched = [r for r in records if "import 실패" in r.getMessage()]
        assert matched, [r.getMessage() for r in records]
        assert all(r.levelno >= logging.WARNING for r in matched)

    def test_result_is_memoized_per_instance(self, selector, monkeypatch):
        """8개 전략이 같은 코드를 재조회하지 않도록 인스턴스 메모 캐시."""
        import api.kis_market_api as market_api

        calls = []

        def fake_supplier(stock_code):
            calls.append(stock_code)
            return dict(BY_CODE["000050"])

        monkeypatch.setattr(market_api, "get_stock_basic_info", fake_supplier)

        first = selector._get_stock_safety_info("000050")
        second = selector._get_stock_safety_info("000050")

        assert calls == ["000050"], "같은 코드를 두 번 조회했다"
        assert first == second

    def test_failures_are_not_memoized(self, selector, monkeypatch):
        """🔴 실패는 캐시하지 않는다.

        토큰 갱신·유량제한 같은 일시적 실패를 캐시하면 그 종목은 하루 종일
        «보수적 통과»로 굳고, bot/candidate_loader 의 3회 재시도가 캐시된 None 만
        읽어 무의미해진다. 관리종목·정리매매는 매수 시점 재조회라는 2차 방어선이
        없으므로 그대로 통과한다.
        """
        import api.kis_market_api as market_api

        attempts = []

        def flaky(stock_code):
            attempts.append(stock_code)
            if len(attempts) == 1:
                raise RuntimeError("일시적 실패(토큰 갱신)")
            return dict(BY_CODE["000300"])  # 재조회하면 거래정지가 드러난다

        monkeypatch.setattr(market_api, "get_stock_basic_info", flaky)

        assert selector._get_stock_safety_info("000300") is None
        second = selector._get_stock_safety_info("000300")

        assert len(attempts) == 2, "실패가 캐시돼 재조회하지 않았다"
        assert second is not None
        assert selector._is_trading_halted(second) is True

    def test_clear_safety_cache_forces_requery(self, selector, monkeypatch):
        """장중 재로드는 09:00 판정을 다시 내주면 안 된다."""
        import api.kis_market_api as market_api

        calls = []

        def supplier(stock_code):
            calls.append(stock_code)
            return dict(BY_CODE["000050"])

        monkeypatch.setattr(market_api, "get_stock_basic_info", supplier)

        selector._get_stock_safety_info("000050")
        selector._get_stock_safety_info("000050")
        assert calls == ["000050"]

        selector.clear_safety_cache()
        selector._get_stock_safety_info("000050")
        assert calls == ["000050", "000050"], "캐시를 비웠는데 재조회하지 않았다"

    def test_reload_candidates_clears_the_cache(self, selector):
        """장중 재로드가 캐시를 비우는지 — 배선까지 확인한다.

        reload_candidates 는 _candidates_loaded 와 재시도 카운터만 리셋하고
        캐시는 그대로 뒀다. 그러면 재로드해도 09:00 판정을 다시 내준다.
        """
        import asyncio
        from unittest.mock import AsyncMock
        from bot.candidate_loader import CandidateLoader

        bot = MagicMock()
        bot.candidate_selector = selector
        loader = CandidateLoader(bot)
        loader._load_screener_candidates = AsyncMock()

        selector._safety_info_cache["000050"] = dict(BY_CODE["000050"])
        asyncio.run(loader.reload_candidates())

        assert selector._safety_info_cache == {}, "재로드가 캐시를 비우지 않았다"
        assert bot._candidates_loaded is False
        loader._load_screener_candidates.assert_awaited_once()

    def test_supplier_exception_returns_none(self, selector, monkeypatch):
        import api.kis_market_api as market_api

        def boom(stock_code):
            raise RuntimeError("API 연결 실패")

        monkeypatch.setattr(market_api, "get_stock_basic_info", boom)
        assert selector._get_stock_safety_info("000050") is None


# ============================================================================
# 9. screener_snapshots 경로 — 안전필터를 우회하던 회귀
# ============================================================================

class TestSnapshotPathAppliesFilter:
    """`_fetch_candidates_for_strategy` 의 1순위(DB 스냅샷) 분기는 아무 필터도
    걸지 않고 반환했다. 라이브 후보의 실제 공급원이 이 경로다.
    (손실 블랙리스트는 사장님 보류 결정으로 여기 적용하지 않는다.)
    """

    def test_snapshot_pool_excludes_unsafe(self, selector, monkeypatch):
        normal = normal_rows()[0]["code"]          # 000050
        halted = group("거래정지_58")[0]["code"]    # 000300
        managed = group("관리종목_iscd51")[0]["code"]
        sltr = group("정리매매_sltr")[0]["code"]

        pool = run_snapshot_path(selector, monkeypatch, [normal, halted, managed, sltr])
        assert [c.code for c in pool] == [normal]

    def test_snapshot_pool_keeps_normal_and_warned(self, selector, monkeypatch):
        """대칭 주장: 정상·시장경고 종목은 스냅샷 경로에서도 남아야 한다."""
        codes = [r["code"] for r in normal_rows() + group("시장경고_02")]
        pool = run_snapshot_path(selector, monkeypatch, codes)
        assert [c.code for c in pool] == codes

    def test_snapshot_pool_excludes_empty_shell(self, selector, monkeypatch):
        codes = [normal_rows()[0]["code"]] + [r["code"] for r in group("빈응답")]
        pool = run_snapshot_path(selector, monkeypatch, codes)
        assert [c.code for c in pool] == [normal_rows()[0]["code"]]


# ============================================================================
# 10. 스냅샷 경로의 지연 필터링 — 슬롯이 줄지 않아야 한다
# ============================================================================

class TestSnapshotLazyFilling:
    """`codes[:max_candidates]` → 필터 순서면 앞머리 제외분만큼 슬롯이 그냥 사라진다.

    랭크 순서대로 «안전한» 후보가 max_candidates 개 모일 때까지 지연 조회해서
    슬롯을 채우되, 그 뒤 종목은 조회조차 하지 않아야 한다(2배 버퍼 대신).
    """

    # 앞머리 2건 + 중간 1건이 제외 대상, 뒤에 정상 종목이 더 있는 배치
    HEAD_UNSAFE_POOL = [
        "000300",  # 거래정지 58
        "000880",  # 거래정지 58
        "000050",  # 정상  → 1
        "000020",  # 정상  → 2
        "043090",  # 정리매매
        "000070",  # 정상  → 3 (여기서 limit 도달)
        "000040",  # 정상 (조회되면 안 됨)
        "000720",  # 시장경고(통과 대상이지만 조회되면 안 됨)
    ]

    def test_unsafe_head_does_not_shrink_pool(self, selector, monkeypatch):
        """앞머리가 제외돼도 max_candidates 개를 채우고, 랭크 순서를 지킨다."""
        pool = run_snapshot_path(selector, monkeypatch, self.HEAD_UNSAFE_POOL, max_candidates=3)

        assert [c.code for c in pool] == ["000050", "000020", "000070"]
        assert len(pool) == 3  # 잘라놓고 걸렀다면 1건(000050)만 남았을 배치

    def test_lookup_stops_at_limit(self, selector, monkeypatch):
        """지연성: limit 도달 뒤의 종목은 API 조회조차 하지 않는다."""
        queried = []
        run_snapshot_path(
            selector, monkeypatch, self.HEAD_UNSAFE_POOL,
            max_candidates=3, queried=queried,
        )

        # 소비 = 통과 3 + 도중 제외 3 (2배 버퍼였다면 6건이 아니라 최소 8건 조회)
        assert queried == ["000300", "000880", "000050", "000020", "043090", "000070"]
        assert "000040" not in queried
        assert "000720" not in queried

    def test_exhausted_snapshot_returns_fewer(self, selector, monkeypatch):
        """풀이 먼저 소진되면 모인 만큼만 반환한다(fail-closed, 폴백 없음)."""
        codes = ["000300", "000050", "000880"]  # 안전한 건 1건뿐
        queried = []
        pool = run_snapshot_path(selector, monkeypatch, codes, max_candidates=5, queried=queried)

        assert [c.code for c in pool] == ["000050"]
        assert queried == codes  # 소진까지 전부 조회

    def test_no_exclusion_costs_exactly_max_candidates(self, selector, monkeypatch):
        """제외가 없으면 조회 수는 정확히 max_candidates (초과 조회 금지)."""
        codes = [r["code"] for r in normal_rows()] + [r["code"] for r in group("시장경고_02")]
        queried = []
        pool = run_snapshot_path(selector, monkeypatch, codes, max_candidates=2, queried=queried)

        assert [c.code for c in pool] == codes[:2]
        assert queried == codes[:2]

    def test_memo_cache_is_not_defeated(self, selector, monkeypatch):
        """지연 필터링이 메모 캐시를 우회하지 않는다(전략 8개가 같은 코드 재조회 금지)."""
        import api.kis_market_api as market_api

        calls = []

        def fake_supplier(stock_code):
            calls.append(stock_code)
            return BY_CODE.get(stock_code)

        monkeypatch.setattr(market_api, "get_stock_basic_info", fake_supplier)

        import core.screener_snapshot_provider as provider_mod
        codes = ["000300", "000050", "000020"]
        monkeypatch.setattr(
            provider_mod, "make_screener_snapshot_provider",
            lambda strategy_name: (lambda name, day: list(codes)),
        )
        monkeypatch.setattr(
            selector, "load_from_screener",
            lambda *a, **k: pytest.fail("폴백으로 샜다"),
        )

        first = selector._fetch_candidates_for_strategy("strategy_a", 2)
        second = selector._fetch_candidates_for_strategy("strategy_b", 2)

        assert [c.code for c in first] == ["000050", "000020"]
        assert [c.code for c in second] == ["000050", "000020"]
        assert calls == codes, "두 번째 전략이 같은 코드를 재조회했다"
