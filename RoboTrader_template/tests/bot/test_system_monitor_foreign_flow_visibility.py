"""외국인수급(foreign_flow) 전면 결손이 EOD 요약에서 ERROR 로 우는가.

`collectors/foreign_flow_fetcher.py:51-53` 은 네이버가 차단하면(HTTP != 200)
warning 한 줄만 찍고 **빈 DataFrame** 을 돌려준다 — 예외가 없다.
그래서 `collect_foreign_flow` 는 `{"codes": 2788, "rows": 0}` 을 반환하고
`error` 키가 없어 `eod_collection._safe` 도 안 걸린다. 그런데 `_run_data_collection`
의 ERROR 승격은 수급 5축(`flow`)과 시장매핑(`stock_market`)만 대상이었다
⇒ ***foreign_flow 만 그 대열에서 빠져 통째 결손이 INFO 한 줄로 끝났다.***

⚠️ 판정 기준은 **rows == 0** 뿐이다. 정상 실측이 24,080 / 24,320 행이라 0 은
   모호하지 않다. 「rows 가 적다」식 비율 문턱은 종목수·거래일에 흔들려 오탐이
   나고, 오탐은 이 프로젝트의 반복 실패(경보 마비)다.

⚠️ DB·네트워크 미접촉: `run_data_collection` 자체를 스텁으로 갈아끼운다.
"""
import asyncio
import types

import bot.system_monitor as sm


class _RecLogger:
    def __init__(self):
        self.info = []
        self.warning = []
        self.error = []

    def _mk(self, sink):
        def _log(msg, *a, **k):
            sink.append(str(msg))
        return _log


def _make_monitor(result, monkeypatch):
    monkeypatch.setattr(sm, "run_data_collection", lambda td: result, raising=False)
    rec = _RecLogger()
    mon = sm.SystemMonitor.__new__(sm.SystemMonitor)  # __init__ 우회
    mon.logger = types.SimpleNamespace(
        info=rec._mk(rec.info),
        warning=rec._mk(rec.warning),
        error=rec._mk(rec.error),
    )
    return mon, rec


class _T:
    def strftime(self, f):
        return "20260817"


def _base(**over):
    """정상 EOD 반환 형태. foreign_flow 실측 기준값 = {'codes': 2788, 'rows': 24320}."""
    out = {
        "daily": {"rows": 1}, "minute": {"rows": 2}, "index": {"KOSPI": 1},
        "stock_market": {"KOSPI": 943, "KOSDAQ": 1820, "overlap": 0},
        "foreign_flow": {"codes": 2788, "rows": 24320},
        "corp_events": {"rows": 4},
        "investor_trend": {"skipped": True, "reason": "fresh"},
        "program_trade": {"skipped": True, "reason": "fresh"},
        "short_sale": {"skipped": True, "reason": "fresh"},
        "credit_balance": {"skipped": True, "reason": "fresh"},
        "overtime": {"skipped": True, "reason": "fresh"},
        "reconcile": {},
    }
    out.update(over)
    return out


def _run(result, monkeypatch):
    mon, rec = _make_monitor(result, monkeypatch)
    asyncio.run(mon._run_data_collection(_T()))
    return rec


# ── 양성: 울어야 하는 경우 ────────────────────────────────────────────────

def test_zero_rows_with_nonzero_codes_is_error(monkeypatch):
    """네이버 차단 형태({'codes': 2788, 'rows': 0}) — 전면 결손이니 ERROR."""
    rec = _run(_base(foreign_flow={"codes": 2788, "rows": 0}), monkeypatch)
    joined = " ".join(rec.error)
    assert joined, "0행 결손이 ERROR 로 남지 않았다 — 조용한 결손이다"
    assert "외국인수급" in joined
    assert "2788" in joined, "판단 근거(codes/rows)가 그대로 보여야 한다"


def test_safe_swallowed_exception_is_error(monkeypatch):
    """_safe 가 예외를 삼켜 {'error': ...} 로만 남은 경우도 같은 경로로 드러나야 한다."""
    rec = _run(_base(foreign_flow={"error": "connection reset by peer"}), monkeypatch)
    assert any("connection reset by peer" in m for m in rec.error)


# ── 음성: 울면 안 되는 경우(오탐 = 경보 마비) ─────────────────────────────

def test_normal_collection_does_not_emit_error(monkeypatch):
    """정상 수집(24,320행)이 ERROR 를 내면 경보가 무뎌진다."""
    rec = _run(_base(), monkeypatch)
    assert rec.error == []
    assert rec.warning == []


def test_other_observed_normal_volume_is_silent(monkeypatch):
    """실측 두 번째 기준값({'codes': 2592, 'rows': 24080})도 정상이다."""
    rec = _run(_base(foreign_flow={"codes": 2592, "rows": 24080}), monkeypatch)
    assert rec.error == []


def test_skipped_is_not_counted_as_failure(monkeypatch):
    """신선도 가드가 붙을 경우의 {'skipped': True} 는 **정상**이다.

    지금 `collect_foreign_flow` 에는 skip 경로가 없지만(항상 {'codes','rows'}),
    5축과 같은 가드가 나중에 붙어도 정상을 실패로 세면 안 된다.
    """
    rec = _run(
        _base(foreign_flow={"skipped": True, "reason": "최근 적재일이 신선함"}),
        monkeypatch,
    )
    assert rec.error == []
    assert rec.warning == []


def test_empty_universe_is_warning_not_error(monkeypatch):
    """codes == 0 은 「유니버스가 비었다」는 다른 사건 — 수집 실패로 오귀속하지 않는다."""
    rec = _run(_base(foreign_flow={"codes": 0, "rows": 0}), monkeypatch)
    assert rec.error == [], "유니버스 0종목을 외국인수집 실패로 세면 오귀속이다"
    assert any("유니버스" in m for m in rec.warning), "그래도 조용히 넘기면 안 된다"


def test_legacy_shape_without_codes_is_silent(monkeypatch):
    """codes 키가 없는 구/부분 포맷은 판단하지 않는다(추측으로 울지 않는다)."""
    rec = _run(_base(foreign_flow={"rows": 3}), monkeypatch)
    assert rec.error == []
    assert rec.warning == []


def test_missing_foreign_flow_key_does_not_crash(monkeypatch):
    """키 자체가 없어도 EOD 흐름을 죽이지 않는다."""
    res = _base()
    del res["foreign_flow"]
    rec = _run(res, monkeypatch)  # 예외 없이 끝나야 한다
    assert rec.error == []


# ── 기존 계약 불변 ────────────────────────────────────────────────────────

def test_summary_info_still_reports_foreign_flow(monkeypatch):
    """요약 INFO 문구는 그대로다 — 성공값도 보여야 실패를 알아본다."""
    rec = _run(_base(), monkeypatch)
    joined = " ".join(rec.info)
    assert "외국인수급" in joined and "24320" in joined
    assert "시장매핑" in joined and "수급3축" in joined
    assert "(전환완료 비교생략)" in joined


def test_existing_promotions_unchanged(monkeypatch):
    """수급 5축·시장매핑 승격은 foreign_flow 추가와 무관하게 그대로 동작한다."""
    rec = _run(
        _base(stock_market={"error": "FDR down"},
              program_trade={"failed": 7, "failed_codes": ["005930"]}),
        monkeypatch,
    )
    assert any("FDR down" in m for m in rec.error)
    assert any("program_trade" in m and "7" in m for m in rec.error)
