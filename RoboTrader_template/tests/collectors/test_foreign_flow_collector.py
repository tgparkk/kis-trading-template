import pandas as pd
from datetime import date

import collectors.foreign_flow_collector as ffc


# ── DB mock helpers (test_index_collector 패턴 미러) ──────────────────────────

class _MockCursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _MockConn:
    def __init__(self, *cursors_rows):
        self._queue = [_MockCursor(r) for r in cursors_rows]
        self._pos = 0

    def cursor(self):
        if self._pos >= len(self._queue):
            return _MockCursor()  # 큐 소진 후(upsert 등)엔 빈 커서 반환
        c = self._queue[self._pos]
        self._pos += 1
        return c

    def commit(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _CM:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *a):
        pass


# ── collect_foreign_flow ──────────────────────────────────────────────────────

def test_collect_foreign_flow_upserts_universe(monkeypatch):
    """universe 종목별 네이버 fetch → upsert. 반환 {codes, rows}."""
    # load_universe → 2종목
    monkeypatch.setattr(ffc, "load_universe", lambda conn: ["005930", "000660"])

    captured = {}

    def _fake_fetch(code, max_pages=2):
        captured.setdefault("codes", []).append(code)
        captured.setdefault("pages", []).append(max_pages)
        return pd.DataFrame({
            "date": [date(2026, 6, 12), date(2026, 6, 11)],
            "foreign_net_vol": [100, -50],
        })

    monkeypatch.setattr(ffc, "fetch_foreign_naver", _fake_fetch)
    monkeypatch.setattr(ffc.KisDbConnection, "get_connection", lambda: _CM(_MockConn()))

    out = ffc.collect_foreign_flow("20260612")
    assert out == {"codes": 2, "rows": 4}
    assert captured["codes"] == ["005930", "000660"]
    # EOD 증분: 최근 ~40일 충분 → max_pages=2
    assert all(p == 2 for p in captured["pages"])


def test_collect_foreign_flow_respects_limit(monkeypatch):
    monkeypatch.setattr(ffc, "load_universe", lambda conn: ["005930", "000660", "035420"])
    monkeypatch.setattr(
        ffc, "fetch_foreign_naver",
        lambda code, max_pages=2: pd.DataFrame({"date": [date(2026, 6, 12)], "foreign_net_vol": [1]}),
    )
    monkeypatch.setattr(ffc.KisDbConnection, "get_connection", lambda: _CM(_MockConn()))
    out = ffc.collect_foreign_flow(limit=1)
    assert out == {"codes": 1, "rows": 1}


def test_collect_foreign_flow_skips_empty(monkeypatch):
    monkeypatch.setattr(ffc, "load_universe", lambda conn: ["005930"])
    monkeypatch.setattr(
        ffc, "fetch_foreign_naver",
        lambda code, max_pages=2: pd.DataFrame(columns=["date", "foreign_net_vol"]),
    )
    monkeypatch.setattr(ffc.KisDbConnection, "get_connection", lambda: _CM(_MockConn()))
    out = ffc.collect_foreign_flow()
    assert out == {"codes": 1, "rows": 0}


# ── 레거시 교차비교 제거 가드 (2026-08-17) ────────────────────────────────────
#
# 🔴 삭제된 테스트 8개 — `reconcile_foreign_flow` 와 그 전용 헬퍼 `_prev_trading_day`
#    가 레거시 DB 폐기와 함께 제거됐기 때문이다. 없어진 함수는 시험할 수 없다:
#      overlap_match_pass · legacy_frozen_no_legacy_pass · no_new_data_fail ·
#      no_new_data_fail_even_when_legacy_empty · prev_trading_day_skips_weekend ·
#      checks_prev_trading_day_not_today · logs_check_date_for_self_describing_row ·
#      genuine_prev_day_gap_fails  (+ 오직 이들만 쓰던 _patch_dbs/_DateAware* 헬퍼)
#
# ⚠️ 잃어버린 커버리지 자기신고: 「네이버 차단으로 foreign_flow 가 0행이면 FAIL」
#    가드가 사라진다. 다만 그 판정은 `KIS_DATA_SOURCE=legacy` 게이트 안에서만
#    돌았으므로 라이브에서는 **이미 휴면**이었다(라이브 .env 는 new). 수집 실패는
#    eod_collection._safe 가 {"error": ...} 로 남기고 system_monitor 가 로그에
#    올린다 — 대체 감시 경로는 유지된다.

def test_legacy_reconcile_helpers_are_gone():
    """레거시 대조 심볼 재유입 방지 — 죽은 DB(robotrader_quant)에 직접 붙던 코드다."""
    for nm in ("reconcile_foreign_flow", "reconcile_verdict", "_prev_trading_day"):
        assert not hasattr(ffc, nm), f"제거된 심볼이 되살아났다: {nm}"
