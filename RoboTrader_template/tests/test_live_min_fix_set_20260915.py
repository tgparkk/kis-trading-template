"""실매매 최소 수정 집합 (2026-09-15) — TDD 회귀 고정.

지시서: `scratchpad/real_trading_audit_20260914/TASK_min_fix_set.md`
근거:   `docs/audit_2026-09-14_real_trading_switch.md` §6

원칙: **페이퍼 8전략 동작 0 변경**. 각 항목은 실전 인스턴스 모드
(`KIS_INSTANCE_DIR` 설정 / `INSTANCE_ID != "default"`)에서만 갈라지거나,
페이퍼가 애초에 도달하지 않는 실브로커 경로만 건드린다.
"""
import importlib
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# 공통 헬퍼
# =============================================================================
def _reload_settings(monkeypatch, instance_dir):
    """`KIS_INSTANCE_DIR` 을 바꾼 뒤 config.settings 를 재로딩해 돌려준다.

    `CONFIG_FILE` 은 import 시점 상수라, 「인스턴스 모드에서 어느 파일을 여는가」는
    재로딩 없이 관찰할 수 없다. 테스트 종료 시 원복은 호출자 책임(fixture 사용).
    """
    import config.settings as settings
    if instance_dir is None:
        monkeypatch.delenv("KIS_INSTANCE_DIR", raising=False)
    else:
        monkeypatch.setenv("KIS_INSTANCE_DIR", str(instance_dir))
    return importlib.reload(settings)


@pytest.fixture
def settings_env(monkeypatch):
    """config.settings 재로딩 테스트용 — 끝나면 env 원복 + 재재로딩."""
    import config.settings as settings
    yield settings
    monkeypatch.delenv("KIS_INSTANCE_DIR", raising=False)
    importlib.reload(settings)


def _capture_config_path(fn):
    """fn() 실행 중 `Path.exists()` 로 조회된 경로 목록을 돌려준다.

    파일을 만들지 않고 경로만 관찰하기 위한 장치다(실제 key.ini 를 워크트리에
    떨구지 않는다). 존재하지 않는다고 답하므로 호출부는 조기 반환한다.
    ⚠️ 패치값은 «함수» 여야 한다 — 클래스 인스턴스를 넣으면 디스크립터가 아니라
    바인딩이 안 되고, 호출부의 try/except 가 그 TypeError 를 삼켜 빈 목록이 된다.
    """
    seen = []

    def fake_exists(path_self):
        seen.append(Path(path_self))
        return False

    with patch.object(Path, "exists", fake_exists):
        fn()
    return seen


# =============================================================================
# A1 — core/telegram_integration.py: key.ini 하드코딩 → settings.CONFIG_FILE
# =============================================================================
class TestA1TelegramConfigPath:
    """P1-1: 실전 인스턴스가 «페이퍼 봇의» key.ini 를 읽어 텔레그램을 잘못 보내던 결함."""

    def _load(self):
        from core.telegram_integration import TelegramIntegration
        ti = TelegramIntegration.__new__(TelegramIntegration)
        ti.logger = MagicMock()
        return _capture_config_path(ti._load_telegram_config)

    def test_instance_mode_opens_instance_key_ini(self, settings_env, monkeypatch, tmp_path):
        inst = tmp_path / "instances" / "x"
        settings = _reload_settings(monkeypatch, inst)
        assert settings.INSTANCE_ID == "x"

        seen = self._load()
        assert seen, "key.ini 존재 검사가 한 번도 일어나지 않았다"
        assert seen[-1] == inst / "key.ini", (
            f"인스턴스 모드인데 {seen[-1]} 를 열었다 (기대: {inst / 'key.ini'})"
        )

    def test_default_mode_opens_repo_config_key_ini(self, settings_env, monkeypatch):
        settings = _reload_settings(monkeypatch, None)
        assert settings.INSTANCE_ID == "default"

        seen = self._load()
        assert seen, "key.ini 존재 검사가 한 번도 일어나지 않았다"
        assert seen[-1] == Path(settings.CONFIG_FILE)
        assert seen[-1].parent.name == "config" and seen[-1].name == "key.ini"


# =============================================================================
# A2 — api/kis_auth.py `_send_failure_telegram`: 동일 하드코딩
# =============================================================================
class TestA2AuthFailureTelegramConfigPath:
    """P1-1: 장애 알림도 같은 경로를 쓴다 — 인스턴스 봇의 경보가 엉뚱한 채팅방으로 갔다."""

    def _send(self):
        import api.kis_auth as kis_auth
        return _capture_config_path(lambda: kis_auth._send_failure_telegram("msg"))

    def test_instance_mode_opens_instance_key_ini(self, settings_env, monkeypatch, tmp_path):
        inst = tmp_path / "instances" / "y"
        _reload_settings(monkeypatch, inst)

        seen = self._send()
        assert seen, "key.ini 존재 검사가 한 번도 일어나지 않았다"
        assert seen[-1] == inst / "key.ini"

    def test_default_mode_opens_repo_config_key_ini(self, settings_env, monkeypatch):
        settings = _reload_settings(monkeypatch, None)

        seen = self._send()
        assert seen, "key.ini 존재 검사가 한 번도 일어나지 않았다"
        assert seen[-1] == Path(settings.CONFIG_FILE)


# =============================================================================
# A3 — bot/candidate_loader.py: 단일 전략 모드 owner 표기를 «폴더키» 로
# =============================================================================
class _FakeTradingManager:
    """add_selected_stock 이 실제로 받은 owner 를 기록하는 최소 대역.

    registry 키가 (code, owner) 라 「owner 표기가 갈리면 조회가 빈다」는 실제
    결함 구조를 그대로 재현한다(get_trading_stock 은 owner 완전일치만 반환).
    """

    def __init__(self):
        self.calls = []
        self._registry = {}

    async def add_selected_stock(self, stock_code, stock_name, selection_reason="",
                                 prev_close=0.0, owner_strategy=""):
        self.calls.append({"stock_code": stock_code, "owner_strategy": owner_strategy})
        ts = MagicMock()
        ts.stock_code = stock_code
        ts.strategy_name = None
        self._registry[(stock_code, owner_strategy)] = ts
        return True

    def get_trading_stock(self, stock_code, strategy=None):
        return self._registry.get((stock_code, strategy or ""))

    def get_stocks_by_state(self, state):
        return list(self._registry.values())


def _single_strategy_bot(folder_key, class_name):
    """단일 전략 봇 대역 — `strategies` dict 키는 폴더명, 인스턴스 `.name` 은 클래스명."""
    from core.candidate_selector import CandidateStock

    strategy_instance = MagicMock()
    strategy_instance.name = class_name

    bot = MagicMock()
    bot._candidates_loaded = False
    bot._candidate_load_retries = 0
    bot.liquidation_handler = None
    bot.config.strategy = None
    bot.strategy = strategy_instance
    bot.strategies = {folder_key: strategy_instance}
    bot.candidate_selector.load_from_screener.return_value = [
        CandidateStock(code="005930", name="삼성전자", market="KRX",
                       score=50.0, reason="테스트", prev_close=70000.0)
    ]
    bot.db_manager = None
    bot.trading_manager = _FakeTradingManager()
    return bot


class TestA3SingleStrategyOwnerKey:
    """P1-2: 단일 전략 모드가 owner 를 «클래스명» 으로 달아, 폴더키로 조회하는
    TradingContext 가 자기 후보를 못 찾아 무거래가 됐다."""

    @pytest.mark.asyncio
    async def test_owner_is_folder_key_not_class_name(self):
        from bot.candidate_loader import CandidateLoader

        bot = _single_strategy_bot("book_pullback_ma20", "BookPullbackMA20Strategy")
        await CandidateLoader(bot)._load_screener_candidates()

        assert bot.trading_manager.calls, "add_selected_stock 이 호출되지 않았다"
        owners = {c["owner_strategy"] for c in bot.trading_manager.calls}
        assert owners == {"book_pullback_ma20"}, (
            f"owner 가 폴더키가 아니다: {owners}"
        )

    @pytest.mark.asyncio
    async def test_context_with_folder_key_sees_the_candidate(self):
        """end-to-end 1건: 폴더키로 만든 TradingContext 가 그 종목을 돌려준다."""
        from bot.candidate_loader import CandidateLoader
        from core.trading_context import TradingContext

        bot = _single_strategy_bot("book_pullback_ma20", "BookPullbackMA20Strategy")
        await CandidateLoader(bot)._load_screener_candidates()

        ctx = TradingContext.__new__(TradingContext)
        ctx.logger = MagicMock()
        ctx._strategy_key = "book_pullback_ma20"
        ctx._trading_manager = bot.trading_manager

        codes = [s.stock_code for s in ctx.get_selected_stocks()]
        assert codes == ["005930"], f"폴더키 컨텍스트가 후보를 못 봤다: {codes}"

    @pytest.mark.asyncio
    async def test_no_strategies_dict_keeps_legacy_fallback(self):
        """`strategies` 가 비면 기존 폴백(클래스명 / "unknown") 유지 — 동작 변화 0."""
        from bot.candidate_loader import CandidateLoader

        bot = _single_strategy_bot("ignored", "BookPullbackMA20Strategy")
        bot.strategies = {}
        await CandidateLoader(bot)._load_screener_candidates()

        owners = {c["owner_strategy"] for c in bot.trading_manager.calls}
        assert owners == {"BookPullbackMA20Strategy"}

    @pytest.mark.asyncio
    async def test_multi_strategy_path_untouched(self):
        """전략 2개 이상이면 기존 다중 전략 경로로 그대로 빠진다(이번 수정 무관)."""
        from bot.candidate_loader import CandidateLoader

        bot = _single_strategy_bot("a", "A")
        bot.strategies = {"a": MagicMock(), "b": MagicMock()}
        loader = CandidateLoader(bot)
        with patch.object(loader, "_load_candidates_multi_strategy") as multi:
            async def _noop(*a, **k):
                return None
            multi.side_effect = _noop
            await loader._load_screener_candidates()
        assert multi.called, "다중 전략 경로가 안 탔다"
        assert not bot.trading_manager.calls


# =============================================================================
# A4 — api/kis_market_api.py: total_value 덮어쓰기 제거 (현금이 사라지던 결함)
# =============================================================================
def _kis_balance_response():
    """실브로커 응답 형태 그대로 — 키 이름은 `get_stock_balance()` 가 실제로 만드는 것.

    총평가 1,000만 · 주식 평가합 400만(= 현금성 600만). 종전 코드는 `total_value`
    를 주식 평가합으로 «덮어써» 600만을 지웠다.
    """
    import pandas as pd

    rows = [
        {"pdno": "005930", "prdt_name": "삼성전자", "hldg_qty": "10",
         "pchs_avg_pric": "70000", "prpr": "250000", "evlu_amt": "2500000",
         "evlu_pfls_amt": "1800000", "evlu_pfls_rt": "257.14"},
        {"pdno": "000660", "prdt_name": "SK하이닉스", "hldg_qty": "5",
         "pchs_avg_pric": "200000", "prpr": "300000", "evlu_amt": "1500000",
         "evlu_pfls_amt": "500000", "evlu_pfls_rt": "50.0"},
    ]
    summary = {
        "dnca_tot_amt": 6_000_000,
        "nxdy_excc_amt": 6_000_000,
        "prvs_rcdl_excc_amt": 6_000_000,
        "tot_evlu_amt": 10_000_000,
        "evlu_pfls_smtl_amt": 2_300_000,
        "pchs_amt_smtl_amt": 1_700_000,
        "evlu_amt_smtl_amt": 4_000_000,
        "raw_summary": {},
    }
    return pd.DataFrame(rows), summary


class TestA4AccountTotalValue:
    """P1-3: `total_value` 가 Σevlu_amt 로 덮여, 실전 총자금 산정이 현금을 통째로
    빠뜨렸다(= 총자금이 주식 평가액으로 축소 → 매수 여력 과소)."""

    def test_total_value_keeps_tot_evlu_amt_and_stock_sum_gets_new_key(self):
        import api.kis_market_api as market_api

        with patch.object(market_api, "get_stock_balance", return_value=_kis_balance_response()):
            result = market_api.get_account_balance()

        assert result is not None
        assert result["total_value"] == 10_000_000, (
            f"total_value 가 총평가액(tot_evlu_amt)이 아니다: {result['total_value']}"
        )
        assert result["stock_eval_value"] == 4_000_000
        assert result["total_stocks"] == 2
        assert result["total_profit_loss"] == 2_300_000

    def test_profit_loss_rate_denominator_is_stock_eval_sum(self):
        """손익률 분모는 «주식 평가합» 이라야 한다 — 총평가로 나누면 현금이 희석한다."""
        import api.kis_market_api as market_api

        with patch.object(market_api, "get_stock_balance", return_value=_kis_balance_response()):
            result = market_api.get_account_balance()

        assert result["total_profit_loss_rate"] == pytest.approx(2_300_000 / 4_000_000 * 100)

    def test_empty_holdings_unchanged(self):
        """보유 0 이면 기존과 동일 — total_value 는 그대로 총평가액."""
        import pandas as pd
        import api.kis_market_api as market_api

        _, summary = _kis_balance_response()
        with patch.object(market_api, "get_stock_balance",
                          return_value=(pd.DataFrame(), summary)):
            result = market_api.get_account_balance()

        assert result["total_value"] == 10_000_000
        assert result["total_stocks"] == 0
        assert result["stocks"] == []
        assert result["stock_eval_value"] == 0

    def test_broker_total_balance_is_total_assets(self):
        """소비자 경로 1건 — `bot/initializer.py` 가 실전 총자금 상한 비교에 쓰는 값."""
        import api.kis_market_api as market_api
        from framework.broker import KISBroker

        broker = KISBroker.__new__(KISBroker)
        broker.logger = MagicMock()
        broker._connected = True
        broker._kis_market_api = market_api

        with patch.object(market_api, "get_stock_balance", return_value=_kis_balance_response()):
            balance = broker.get_account_balance()

        assert balance["total_balance"] == 10_000_000


# =============================================================================
# A5 — api/kis_auth.py `_CB_BYPASS_TR_IDS`: 현금 매도(TTTC0011U) 통과
# =============================================================================
class TestA5CircuitBreakerSellBypass:
    """P1-8 입구: Circuit Breaker 가 OPEN 이면 «매도»까지 막혀 보유분을 못 던진다.
    매수는 계속 막아야 한다(막힌 채로 두는 것이 안전한 방향)."""

    def _fetch(self, tr_id):
        """CB OPEN 상태에서 `_url_fetch` 를 호출하고 (차단여부, 인증시도여부) 반환.

        두 경로 모두 최종 반환값은 None 이라(토큰 없음) 반환값으로는 구분되지 않는다.
        ⇒ CB 의 `record_blocked` 호출 여부와 `auth()` 도달 여부로 대칭 판정한다.
        """
        import api.circuit_breaker as cb_mod
        import api.kis_auth as kis_auth

        cb = MagicMock()
        cb.can_execute.return_value = False   # OPEN

        with patch.object(cb_mod, "get_circuit_breaker", return_value=cb), \
             patch.object(kis_auth, "_TRENV", None), \
             patch.object(kis_auth, "auth", return_value=False) as auth_fn:
            kis_auth._url_fetch("/dummy", tr_id, "", {})
        return cb.record_blocked.called, auth_fn.called

    def test_cash_sell_tr_passes_circuit_breaker(self):
        blocked, reached_auth = self._fetch("TTTC0011U")
        assert not blocked, "현금 매도(TTTC0011U)가 Circuit Breaker 에 막혔다"
        assert reached_auth, "CB 를 통과했는데 그 다음 단계(인증)로 가지 않았다"

    def test_cash_buy_tr_still_blocked(self):
        blocked, reached_auth = self._fetch("TTTC0012U")
        assert blocked, "현금 매수(TTTC0012U)가 Circuit Breaker 를 통과했다 — 금지"
        assert not reached_auth

    def test_existing_bypass_tr_ids_unchanged(self):
        """기존 우회 대상(정정취소)은 그대로 통과 — 회귀 가드."""
        for tr_id in ("TTTC0013U", "TTTC8036R"):
            blocked, reached_auth = self._fetch(tr_id)
            assert not blocked and reached_auth, tr_id


# =============================================================================
# A6 — bot/system_monitor.py `_handle_postmarket_tasks`: 인스턴스는 EOD 후속작업 금지
# =============================================================================
def _postmarket_monitor(monkeypatch, instance_id):
    """EOD 블록의 모든 후속 작업을 대역으로 바꾼 SystemMonitor 를 만든다."""
    from unittest.mock import AsyncMock
    import bot.system_monitor as sm_mod
    import config.settings as settings

    monkeypatch.setattr(settings, "INSTANCE_ID", instance_id, raising=False)
    monkeypatch.setattr(sm_mod, "is_holiday", lambda *_a, **_k: False)
    summary = MagicMock()
    monkeypatch.setattr(sm_mod, "print_today_trading_summary", summary)

    mon = sm_mod.SystemMonitor.__new__(sm_mod.SystemMonitor)
    mon.bot = MagicMock()
    mon.logger = MagicMock()
    mon._last_daily_report_date = None
    mon._last_regime_index_summary_date = None
    mon._last_equity_n_strategies = None
    mon._dashboard = None
    for name in ("_build_current_price_lookup", "_verify_eod_fund_integrity",
                 "_log_regime_index_resolution", "_verify_screener_snapshot",
                 "_run_equity_snapshot", "_run_regime_index_refresh",
                 "_log_eod_benchmark"):
        setattr(mon, name, MagicMock())
    mon._run_data_collection = AsyncMock()
    return mon, summary


class TestA6PostmarketInstanceGate:
    """P1-9: 실전 인스턴스가 EOD 리포트·equity 스냅샷·데이터 수집을 «또» 돌려
    페이퍼 봇의 산출물과 경합(중복 UPSERT·중복 수집)한다. 생성은 페이퍼 봇 몫이다."""

    @pytest.mark.asyncio
    async def test_instance_skips_all_eod_tasks(self, monkeypatch):
        mon, summary = _postmarket_monitor(monkeypatch, "rs_leader")
        await mon._handle_postmarket_tasks(datetime(2026, 9, 15, 15, 36))

        assert not summary.called, "인스턴스가 일일 매매 리포트를 생성했다"
        assert not mon._run_equity_snapshot.called, "인스턴스가 equity 스냅샷을 적재했다"
        assert not mon._run_data_collection.called, "인스턴스가 EOD 데이터 수집을 돌렸다"
        assert not mon._log_eod_benchmark.called
        assert not mon._run_regime_index_refresh.called
        assert not mon._verify_eod_fund_integrity.called

    @pytest.mark.asyncio
    async def test_default_instance_runs_eod_tasks_as_before(self, monkeypatch):
        """대칭: 페이퍼(default)는 종전대로 전부 돈다."""
        mon, summary = _postmarket_monitor(monkeypatch, "default")
        await mon._handle_postmarket_tasks(datetime(2026, 9, 15, 15, 36))

        assert summary.called
        assert mon._run_equity_snapshot.call_count == 2   # 1차 + 재스냅샷
        assert mon._run_data_collection.called
        assert mon._log_eod_benchmark.called

    @pytest.mark.asyncio
    async def test_instance_gate_latches_so_it_logs_once(self, monkeypatch):
        """5초 루프가 15:35~15:59 를 ~300회 재진입하므로 래치가 필요하다."""
        mon, _ = _postmarket_monitor(monkeypatch, "rs_leader")
        t = datetime(2026, 9, 15, 15, 36)
        await mon._handle_postmarket_tasks(t)
        await mon._handle_postmarket_tasks(t)
        assert mon._last_daily_report_date == t.date()
        assert mon.logger.info.call_count == 1
