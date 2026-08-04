"""EOD 요약에 시장 매핑 수집 결과가 드러나는지 — 활성화 선행조건 ③-4.

`collectors/eod_collection.py:37` 이 `_safe(collect_stock_market)` 로 예외를
삼키므로, 규모 하한 거부는 반환 dict 의 `{"error": ...}` 로만 남는다.
그런데 `_run_data_collection` 의 요약 로그는 daily·minute·index·foreign 만
찍고 있었다 ⇒ **거부가 EOD 요약에서 보이지 않았다.**

⚠️ 조용한 거부는 조용한 오염만큼 나쁘다. 하한을 걸어놓고 거부가 안 보이면
   「수집이 며칠째 거부 중인데 아무도 모르는」 상태가 만들어진다.

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
        return "20260803"


def _base(**over):
    out = {
        "daily": {"rows": 1}, "minute": {"rows": 2}, "index": {"KOSPI": 1},
        "stock_market": {"KOSPI": 943, "KOSDAQ": 1820, "overlap": 0},
        "foreign_flow": {"rows": 3}, "corp_events": {"rows": 4}, "reconcile": {},
    }
    out.update(over)
    return out


def test_summary_includes_stock_market_stage(monkeypatch):
    """성공 시에도 요약에 나와야 한다 — 안 나오면 실패도 못 알아본다."""
    mon, rec = _make_monitor(_base(), monkeypatch)
    asyncio.run(mon._run_data_collection(_T()))
    joined = " ".join(rec.info)
    assert "943" in joined and "1820" in joined


def test_scale_floor_rejection_surfaces_as_error(monkeypatch):
    """규모 하한 거부가 ERROR 로 드러나야 한다(요약 INFO 에 묻히면 안 된다)."""
    err = "시장 매핑 규모 하한 미달 — 한 행도 쓰지 않음(기존 매핑 보존): KOSPI 20건 < 기존 943건의 80%(754건)"
    mon, rec = _make_monitor(_base(stock_market={"error": err}), monkeypatch)
    asyncio.run(mon._run_data_collection(_T()))

    joined = " ".join(rec.error)
    assert joined, "거부가 ERROR 로 남지 않았다 — 조용한 거부다"
    assert "KOSPI" in joined and "943" in joined, "사유가 그대로 보여야 한다"


def test_generic_stock_market_failure_also_surfaces(monkeypatch):
    """FDR 장애 등 다른 실패도 같은 경로로 드러나야 한다."""
    mon, rec = _make_monitor(_base(stock_market={"error": "FDR down"}), monkeypatch)
    asyncio.run(mon._run_data_collection(_T()))
    assert any("FDR down" in m for m in rec.error)


def test_success_does_not_emit_error(monkeypatch):
    """정상 수집이 ERROR 를 내면 경보가 무뎌진다."""
    mon, rec = _make_monitor(_base(), monkeypatch)
    asyncio.run(mon._run_data_collection(_T()))
    assert rec.error == []


def test_missing_stock_market_key_does_not_crash(monkeypatch):
    """구 포맷/부분 결과가 와도 EOD 흐름을 죽이지 않는다."""
    res = _base()
    del res["stock_market"]
    mon, rec = _make_monitor(res, monkeypatch)
    asyncio.run(mon._run_data_collection(_T()))  # 예외 없이 끝나야 한다
    assert rec.error == []
