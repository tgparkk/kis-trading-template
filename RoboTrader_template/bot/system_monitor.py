"""
시스템 모니터링 모듈
시스템 상태 모니터링 및 주기적 작업을 담당합니다.
"""
import asyncio
from typing import TYPE_CHECKING

from utils.logger import setup_logger
from utils.korean_time import now_kst, is_market_open
from utils.korean_holidays import is_holiday, get_holiday_name
from config.market_hours import MarketHours
from tools.daily_trading_summary import print_today_trading_summary
from collectors.eod_collection import run_data_collection

if TYPE_CHECKING:
    from main import DayTradingBot


# 장전 regime 지수 갱신 throttle 상수 (2026-06-29 폭격 루프 수정)
# 연속 실패 시 재시도 최소 간격(분). 직전 시도 후 [n번째 실패] 인덱스로 참조하며
# 상한(마지막 값)에 캡된다. 1→2→5→15분.
_REGIME_REFRESH_BACKOFF_MINUTES = (1, 2, 5, 15)
# 거래일당 최대 시도 횟수. 초과 시 그날은 재시도 중단(다음 거래일 리셋).
_REGIME_REFRESH_MAX_ATTEMPTS_PER_DAY = 12
# DB 멱등 스킵 판정 대상 지수 코드(daily_prices stock_code).
INDEX_CODES_FOR_SKIP = ("KOSPI", "KOSDAQ")


class SystemMonitor:
    """시스템 모니터링 클래스"""

    def __init__(self, bot: 'DayTradingBot') -> None:
        self.bot = bot
        self.logger = setup_logger(__name__)
        self._last_daily_report_date = None
        # 주입 가능한 시계(테스트 결정론). 기본 실제 KST 시계.
        self._clock = now_kst

        # 대시보드 초기화
        self._init_dashboard()

    def _init_dashboard(self):
        """시장현황 대시보드 초기화"""
        self._dashboard = None
        try:
            from market_dashboard.dashboard import MarketDashboard
            from market_dashboard.global_market import GlobalMarketCollector
            from market_dashboard.domestic_market import DomesticMarketCollector
            from config.constants import GLOBAL_MARKET_CACHE_TTL, DOMESTIC_MARKET_CACHE_TTL

            self._dashboard = MarketDashboard(
                domestic_collector=DomesticMarketCollector.from_kis_api(
                    cache_ttl_seconds=DOMESTIC_MARKET_CACHE_TTL
                ),
                global_collector=GlobalMarketCollector(
                    cache_ttl_seconds=GLOBAL_MARKET_CACHE_TTL
                ),
            )
            self.logger.info("시장현황 대시보드 초기화 완료")
        except Exception as e:
            self.logger.warning(f"시장현황 대시보드 초기화 실패 (무시): {e}")

    async def run_system_monitoring_task(self) -> None:
        """시스템 모니터링 태스크"""
        try:
            self.logger.info("시스템 모니터링 태스크 시작")

            last_api_refresh = now_kst()
            last_market_check = now_kst()
            last_portfolio_snapshot = now_kst()

            while self.bot.is_running:
                current_time = now_kst()

                # API 24시간마다 재초기화
                if (current_time - last_api_refresh).total_seconds() >= 86400:  # 24시간
                    await self._refresh_api()
                    last_api_refresh = current_time

                # 08:30 전일 데이터 수집 및 08:55 퀀트 스크리닝 실행 (장 시작 전)
                await self._handle_premarket_tasks(current_time)

                # 15:35 장 마감 후 일일 매매 리포트 생성
                await self._handle_postmarket_tasks(current_time)

                # 30분마다 포트폴리오 스냅샷 저장 (장중에만)
                if (current_time - last_portfolio_snapshot).total_seconds() >= 30 * 60:
                    if is_market_open():
                        await self._save_portfolio_snapshot(current_time)
                    last_portfolio_snapshot = current_time

                # 시스템 모니터링 루프 대기 (5초 주기)
                await asyncio.sleep(5)

                # 30분마다 시스템 상태 로깅
                if (current_time - last_market_check).total_seconds() >= 30 * 60:
                    await self._log_system_status()
                    last_market_check = current_time

        except Exception as e:
            self.logger.error(f"시스템 모니터링 태스크 오류: {e}")
            await self.bot.telegram.notify_error("SystemMonitoring", e)

    async def _handle_premarket_tasks(self, current_time) -> None:
        """장 시작 전 태스크 처리"""
        # 전략의 get_target_stocks()를 통한 후보 종목 자동 등록
        await self._register_strategy_target_stocks()

        # 장전 regime 지수 자동 갱신 (EOD 15:48 FDR 일시실패로 SSOT 동결 보정,
        # 하루 1회·성공 시에만 가드 설정 → 실패 시 다음 루프 재시도, 2026-06-26)
        await self._run_premarket_regime_index_refresh()

        # 장전 브리핑 (하루 1회)
        await self._run_premarket_briefing()

    def _resolve_strategy_key(self, strategy) -> str:
        """전략 인스턴스의 폴더키(self.bot.strategies 의 dict 키)를 역조회한다.

        SELECTED 소유자 표기는 **폴더키**여야 한다. SELECTED 소비자인
        TradingContext.get_selected_stocks 가 owner 미지정 시 _strategy_key
        (= 폴더키, main.py:447-449·464 가 dict 키를 넘긴다)와 비교하기 때문이다
        (core/trading_context.py:285-297). 클래스명(strategy.name)으로 등록하면
        어느 전략에게도 안 보이는 유령 슬롯이 된다(65bf870 유형의 매칭 0).

        인자 표기를 믿지 않고 **객체 동일성(is)** 으로 키를 얻으므로 표기-불변이다
        (01d336e·6f63b60 관례). 키를 못 찾으면 ""(무기명=공용)로 폴백해 기존 동작을
        보존한다 — 표기를 추측해 넣으면 유령 슬롯이 되므로 추측하지 않는다.
        """
        strategies = getattr(self.bot, 'strategies', None)
        if isinstance(strategies, dict):
            for key, instance in strategies.items():
                if instance is strategy:
                    return key
        return ""

    async def _register_strategy_target_stocks(self) -> None:
        """전략의 get_target_stocks()에서 후보 종목을 가져와 등록"""
        try:
            # 이미 등록했으면 스킵 (하루에 1회)
            if hasattr(self, '_strategy_stocks_registered_date'):
                today = now_kst().date()
                if self._strategy_stocks_registered_date == today:
                    return
            
            strategy = getattr(self.bot, 'strategy', None)
            if not strategy or not hasattr(strategy, 'get_target_stocks'):
                return

            target_stocks = strategy.get_target_stocks()
            if not target_stocks:
                return

            trading_manager = getattr(self.bot, 'trading_manager', None)
            if not trading_manager or not hasattr(trading_manager, 'add_selected_stock'):
                return

            owner_key = self._resolve_strategy_key(strategy)

            self.logger.info(f"전략 후보 종목 {len(target_stocks)}개 등록 시작")
            registered = 0
            for stock_code in target_stocks:
                try:
                    # 종목명 조회: broker.get_stock_name 우선, 실패 시 stock_code 그대로
                    stock_name = stock_code
                    try:
                        broker = getattr(self.bot, 'broker', None)
                        if broker and hasattr(broker, 'get_stock_name'):
                            fetched = broker.get_stock_name(stock_code)
                            if fetched:
                                stock_name = fetched
                    except Exception:
                        pass
                    # 소유자를 등록 시점에 바인딩한다(add_selected_stock 내부에서
                    # TradingStock(owner_strategy_name=...) 으로 생성 —
                    # order_execution.py:119). 등록 후 재조회해서 라벨을 덮어쓰던
                    # 기존 코드는 두 가지 결함이 있었다(2026-07-24):
                    #  ① get_trading_stock(stock_code) 무한정 조회는 다중소유 종목에서
                    #     삽입순 첫 소유자(= 다른 전략)의 슬롯을 반환한다.
                    #  ② TradingStock.strategy_name 은 owner_strategy_name 의 별칭
                    #     프로퍼티라(core/models.py:206-213) 그 대입이 '표시용 이름'이
                    #     아니라 소유권 자체를 덮어쓴다 → 남의 슬롯 오귀속.
                    # 등록 시 바인딩하면 재조회 자체가 불필요하다(owner 지정 조회로
                    # 매칭된 슬롯이든 신규 생성 슬롯이든 owner 는 이미 owner_key).
                    success = await trading_manager.add_selected_stock(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        selection_reason=f"{strategy.name} get_target_stocks()",
                        owner_strategy=owner_key,
                    )
                    if success:
                        registered += 1
                except Exception as e:
                    self.logger.warning(f"전략 후보 종목 등록 실패 ({stock_code}): {e}")

            self._strategy_stocks_registered_date = now_kst().date()
            self.logger.info(f"전략 후보 종목 등록 완료: {registered}/{len(target_stocks)}개")

        except Exception as e:
            self.logger.error(f"전략 후보 종목 등록 오류: {e}")

    async def _run_premarket_briefing(self) -> None:
        """장전 브리핑 실행 (하루 1회)"""
        if self._dashboard is None:
            return
        if self._dashboard.is_briefing_done_today():
            return
        try:
            import asyncio
            await asyncio.to_thread(self._dashboard.generate_premarket_briefing)
            self.logger.info("장전 브리핑 출력 완료")
        except Exception as e:
            self.logger.warning(f"장전 브리핑 오류 (무시): {e}")

    async def _handle_postmarket_tasks(self, current_time) -> None:
        """장 마감 후 태스크 처리 (거래일에만 — 휴장일은 전체 스킵)"""
        if current_time.hour == 15 and current_time.minute >= 35:
            if self._last_daily_report_date != current_time.date():
                # 휴장일(주말·공휴일) 게이트 — 이 블록은 '거래일 마감' 후속처리라
                # 휴장일엔 전 항목이 무의미하거나 유해하다(2026-07-17 제헌절, 컷오버
                # 후 첫 평일 공휴일 대비). 항목별 근거:
                #   - 데이터수집: KIS 가 휴장일 요청에 직전 거래일(T-1) 봉을 반환 →
                #     replace_minute_day 가 T-1 분봉을 DELETE 후 재적재. 부분 재fetch 면
                #     조용히 절단된다(최대 위험).
                #   - equity 스냅샷: _resave_paper_trading_state 가 오늘 날짜로
                #     paper_trading_state 를 UPSERT → _load_calendar 가 휴장일을 거래일로
                #     주워 paper_strategy_equity 에 유령 행 생성(자산곡선 오염).
                #   - regime 지수 갱신: 휴장일엔 신규 일봉이 없어 0행 → "stale 우려"
                #     WARNING 오탐 + FDR 불필요 호출.
                #   - 스크리너 스냅샷 검증: 장이 없어 훅 자체가 안 도므로 "훅 미실행"
                #     WARNING 오탐.
                #   - 매매 리포트/자금 정합성: 체결이 없어 빈 리포트·전일과 동일한
                #     검증 재출력(노이즈).
                # 게이트는 is_holiday(주말 OR 공휴일)만 사용한다. is_market_open() 은
                # 15:35 가 장마감 후라 거래일에도 False → 매일 수집이 죽으므로 금지.
                # _last_daily_report_date 래치를 재사용해 5초 루프마다 재로깅하지 않는다.
                if is_holiday(current_time):
                    self._last_daily_report_date = current_time.date()
                    # 이름 없는 휴장일 = holidays 라이브러리엔 없고 KIS chk-holiday
                    # 캐시에만 있는 날(예: 제헌절 — 2008 년부터 법정공휴일 아님).
                    # 판정 출처를 남겨 다음날 EOD 점검이 즉시 추적 가능하게 한다.
                    reason = get_holiday_name(current_time) or "KIS 지정 휴장일"
                    self.logger.info(
                        f"휴장일({current_time.strftime('%Y-%m-%d')} {reason}) — "
                        f"EOD 후속 작업 전체 스킵 (데이터수집·equity·regime·리포트)"
                    )
                    return

                self.logger.info(f"15:35+ 장 마감 후 일일 매매 리포트 생성 ({current_time.strftime('%H:%M:%S')})")
                try:
                    print_today_trading_summary()
                    self._last_daily_report_date = current_time.date()
                    self.logger.info("일일 매매 리포트 생성 완료")
                except Exception as report_err:
                    self.logger.error(f"일일 매매 리포트 생성 오류: {report_err}")

                # EOD 자금 정합성 검증 (장마감 청산 후)
                try:
                    self._verify_eod_fund_integrity()
                except Exception as verify_err:
                    self.logger.error(f"EOD 자금 정합성 검증 오류: {verify_err}")

                # EOD 스크리너 스냅샷 저장 여부 검증 (D6)
                try:
                    self._verify_screener_snapshot()
                except Exception as snap_err:
                    self.logger.error(f"EOD 스크리너 스냅샷 검증 오류: {snap_err}")

                # EOD 전략별 equity 스냅샷 적재 (paper_strategy_equity, 멱등)
                try:
                    self._run_equity_snapshot()
                except Exception as eq_err:
                    self.logger.error(f"EOD equity 스냅샷 적재 오류: {eq_err}")

                # EOD regime 지수(KOSPI/KOSDAQ) 일봉 갱신 → 게이트 SSOT(daily_prices)
                # 자동 신선화. 수동 backfill 미실행 시 게이트 stale/fail-open 방지(2026-06-24).
                try:
                    import asyncio
                    await asyncio.to_thread(self._run_regime_index_refresh)
                except Exception as ri_err:
                    self.logger.error(f"EOD regime 지수 갱신 오류: {ri_err}")

                # EOD 데이터 수집(일봉·분봉·지수 → kis_template) + grace 교차비교
                try:
                    await self._run_data_collection(current_time)
                except Exception as dc_err:
                    self.logger.error(f"EOD 데이터 수집 오류: {dc_err}")

                # EOD equity 재스냅샷: step6 가 당일(T) 공식종가를 kis_template 으로
                # 수집한 뒤 다시 평가해 15:35 1차 스냅샷의 stale 보유평가(당일종가 미적재
                # 시 전일종가 폴백, 2026-06-25 버그)를 T-close 로 덮어쓴다. 멱등(전구간
                # UPSERT)이라 재호출이 최종 권위가 된다. 예외는 EOD 흐름을 막지 않는다.
                try:
                    self._run_equity_snapshot()
                except Exception as eq2_err:
                    self.logger.error(f"EOD equity 재스냅샷 적재 오류: {eq2_err}")

    def _run_equity_snapshot(self) -> None:
        """EOD 전략별 일별 equity 를 paper_strategy_equity 에 적재 (하루 1회).

        현금식은 라이브 누적 재구성(restore_strategy_ledger_from_records)과 동일.
        멱등(전 구간 UPSERT)이라 실패해도 다음 거래일 재계산되며, 예외는
        EOD 흐름을 막지 않도록 호출측에서 흡수한다. cash_match=False 면 라이브
        SSOT(paper_trading_state)와 현금 불일치이므로 WARNING.
        """
        from db.connection import DatabaseConnection
        from tools.paper_strategy_equity import run_daily_equity_snapshot

        # 0) post-EOD 체결 반영: paper_trading_state 재저장.
        #    save_paper_trading_state는 15:00 EOD청산 훅에서 1회 저장되나, 그 후
        #    15:00~15:30 position_monitor 손절이 virtual_balance를 갱신해도 재저장되지
        #    않아 stale → equity 리플레이와 현금 불일치(2026-06-23 033780 손절 +344,726).
        #    스냅샷 직전 재저장으로 paper_trading_state를 최종 잔고에 일치시킨다.
        self._resave_paper_trading_state()

        with DatabaseConnection.get_connection() as conn:
            result = run_daily_equity_snapshot(conn)
        if not result.get("ok"):
            self.logger.warning(f"EOD equity 스냅샷 스킵: {result.get('reason')}")
            return
        if result.get("cash_match"):
            self.logger.info(
                f"EOD equity 스냅샷 적재 완료: {result['trade_date']} "
                f"{result['n_strategies']}전략, 현금합 {result['total_cash']:,.0f}원 "
                f"= paper_trading_state ✅"
            )
        else:
            self.logger.warning(
                f"EOD equity 스냅샷 적재 완료(현금 불일치 ⚠️): {result['trade_date']} "
                f"리플레이 현금합 {result['total_cash']:,.0f} vs "
                f"paper_trading_state {result.get('eod_balance')}"
            )

    async def _run_premarket_regime_index_refresh(self) -> None:
        """장전 regime 지수(KOSPI/KOSDAQ) 자동 갱신 (하루 1회, 성공 시에만 가드).

        EOD 15:48 _run_regime_index_refresh 가 FDR 일시실패로 {KOSPI:0,KOSDAQ:0}
        을 반환하면 게이트 SSOT(daily_prices)가 동결(stale)돼 exclude_bear 전략을
        잘못 게이팅한다(2026-06-26 진단). 장전에 한 번 더 갱신해 보정한다.

        과거(2026-06-26~28 도입판)에는 실패 시 가드 미설정 → "다음 루프 재시도"라
        모니터 루프(~9초)마다 무제한 FDR 재호출이 발생했고, 이 폭격이 FDR 제공자
        세션 차단(LOGOUT)을 자기강화시켜 하루 종일 빠져나오지 못했다(2026-06-29 실측
        23,908회 실패). 이를 막기 위해 다음 throttle 을 적용한다:
          1) DB 멱등 스킵: 오늘자 KOSPI/KOSDAQ 일봉이 이미 있으면 FDR 미호출·성공처리.
          2) 쿨다운/지수 백오프: 직전 시도 후 _REGIME_REFRESH_BACKOFF_MINUTES(1→2→5→15분,
             상한 캡) 경과 전엔 재호출 금지.
          3) 일일 시도 캡: 거래일당 _REGIME_REFRESH_MAX_ATTEMPTS_PER_DAY 회 초과 시 중단.
          4) 성공 게이트: 그날 성공하면 더 호출 안 함.
        거래일이 바뀌면 카운터/백오프가 리셋된다. 예외는 정상흐름을 막지 않도록 흡수.
        """
        try:
            clock = getattr(self, '_clock', None) or now_kst
            nowdt = clock()
            today = nowdt.date()

            # 4) 성공 게이트: 오늘 이미 갱신 성공
            if getattr(self, '_regime_index_refreshed_date', None) == today:
                return

            # 거래일 전환 시 throttle 상태 리셋
            if getattr(self, '_regime_refresh_state_date', None) != today:
                self._regime_refresh_state_date = today
                self._regime_refresh_attempts = 0
                self._regime_refresh_last_attempt_at = None

            # 1) DB 멱등 스킵: 이미 백필돼 있으면 FDR 두들기지 않음
            if self._regime_indices_present_for(today):
                self._regime_index_refreshed_date = today
                self.logger.info("장전 regime 지수 이미 최신(DB 존재) — FDR 호출 스킵")
                return

            # 3) 일일 시도 캡
            if self._regime_refresh_attempts >= _REGIME_REFRESH_MAX_ATTEMPTS_PER_DAY:
                return

            # 2) 쿨다운/지수 백오프
            last = getattr(self, '_regime_refresh_last_attempt_at', None)
            if last is not None:
                idx = min(self._regime_refresh_attempts - 1,
                          len(_REGIME_REFRESH_BACKOFF_MINUTES) - 1)
                wait_sec = _REGIME_REFRESH_BACKOFF_MINUTES[max(idx, 0)] * 60
                if (nowdt - last).total_seconds() < wait_sec:
                    return

            # 시도 기록 후 실제 갱신
            self._regime_refresh_attempts += 1
            self._regime_refresh_last_attempt_at = nowdt
            res = await asyncio.to_thread(self._run_regime_index_refresh)
            if isinstance(res, dict) and res and min(res.values()) > 0:
                self._regime_index_refreshed_date = today
                self.logger.info(f"장전 regime 지수 갱신 완료: {res}")
            else:
                # 가드 미설정 → 쿨다운/백오프 경과 후 재시도(폭격 방지)
                self.logger.warning(
                    f"장전 regime 지수 갱신 실패/0행 — 재시도 대기"
                    f"(시도 {self._regime_refresh_attempts}/"
                    f"{_REGIME_REFRESH_MAX_ATTEMPTS_PER_DAY}): {res}"
                )
        except Exception as e:
            self.logger.warning(f"장전 regime 지수 갱신 오류 (무시): {e}")

    def _regime_indices_present_for(self, trade_date) -> bool:
        """robotrader.daily_prices 에 trade_date 자 KOSPI·KOSDAQ 일봉이 모두 있으면 True.

        이미 백필돼 있으면 FDR 를 호출하지 않기 위한 멱등 스킵 게이트.
        참조 불가/예외 시 False(스킵 안 함 → 기존 동작 유지).
        """
        try:
            repo = getattr(getattr(self.bot, 'db_manager', None), 'price_repo', None)
            if repo is None:
                from db.repositories.price import PriceRepository
                repo = PriceRepository()
            for name in INDEX_CODES_FOR_SKIP:
                latest = repo.get_latest_daily_price(name)
                if not latest:
                    return False
                d = latest.get('date')
                if hasattr(d, 'date'):
                    d = d.date()
                if d != trade_date:
                    return False
            return True
        except Exception as e:
            self.logger.warning(f"regime 지수 DB 존재 확인 오류 (무시): {e}")
            return False

    def _run_regime_index_refresh(self) -> dict:
        """regime 게이트 SSOT(daily_prices KOSPI/KOSDAQ)를 FDR로 최신화(멱등).

        게이트는 robotrader.daily_prices 의 KOSPI/KOSDAQ 일봉을 읽는데, 이를 채우던
        scripts/backfill_kospi_index.py 가 수동·미스케줄이라 동결되면 게이트가
        stale/fail-open 된다(2026-06-24 진단). 매 EOD FDR 로 자동 갱신해 방지한다.
        예외는 EOD 흐름을 막지 않도록 흡수한다.

        Returns:
            refresh_regime_indices 결과 dict({"KOSPI": n, "KOSDAQ": n}). 예외 시 빈 dict.
            (EOD 경로는 반환값을 안 쓰므로 호환 유지; 장전 가드 판단용으로 사용.)
        """
        try:
            from core.regime.index_refresh import refresh_regime_indices
            repo = getattr(getattr(self.bot, 'db_manager', None), 'price_repo', None)
            if repo is None:
                from db.repositories.price import PriceRepository
                repo = PriceRepository()
            res = refresh_regime_indices(repo)
            # 어떤 지수든 0행이면 stale 우려 → WARNING. 전부 >0 이면 INFO.
            if isinstance(res, dict) and res and min(res.values()) > 0:
                self.logger.info(f"regime 지수 갱신 완료: {res}")
            else:
                self.logger.warning(f"regime 지수 갱신 결과 0행 — stale 우려: {res}")
            return res
        except Exception as e:
            self.logger.warning(f"regime 지수 갱신 오류 (무시): {e}")
            return {}

    def _resave_paper_trading_state(self) -> None:
        """가상모드면 현재 virtual_balance를 paper_trading_state에 재저장.

        15:00 EOD청산 이후(15:00~15:30) position_monitor 손절 등 post-EOD 체결이
        virtual_balance를 갱신하므로, equity 스냅샷 직전 최종 잔고로 동기화한다.
        실전모드/참조불가/예외는 EOD 흐름을 막지 않도록 흡수한다.
        """
        try:
            de = getattr(self.bot, 'decision_engine', None)
            if not getattr(de, 'is_virtual_mode', False):
                return
            vm = getattr(de, 'virtual_trading', None)
            if vm is None:
                self.logger.warning("paper_trading_state 재저장 생략: virtual_trading 참조 불가")
                return
            vm.save_paper_trading_state()
        except Exception as e:
            self.logger.warning(f"paper_trading_state 재저장 오류 (무시): {e}")

    async def _run_data_collection(self, current_time) -> None:
        """EOD 데이터 수집(비차단). ~수분 루프라 to_thread로 모니터 태스크 비차단."""
        import asyncio
        trade_date = current_time.strftime("%Y%m%d")
        result = await asyncio.to_thread(run_data_collection, trade_date)
        daily = result.get("daily", {})
        minute = result.get("minute", {})
        index = result.get("index", {})
        foreign = result.get("foreign_flow", {})
        rec = result.get("reconcile", {})
        self.logger.info(
            f"EOD 데이터 수집 완료: 일봉 {daily} · 분봉 {minute} · 지수 {index} · 외국인수급 {foreign}"
            + (f" · 교차비교 {rec}" if rec else " · (전환완료 비교생략)")
        )
        for ds, r in (rec or {}).items():
            if isinstance(r, dict) and r.get("verdict") not in ("PASS", "EMPTY", None):
                self.logger.warning(f"EOD 교차비교 {ds} 불일치: {r}")

    def _verify_screener_snapshot(self) -> None:
        """EOD 스크리너 스냅샷 실행 여부 검증 (D6)

        run_screener_snapshot_hook()이 오늘 실행됐는지를 1차 확인한다.
        실행됐으면 DB 행 수와 무관하게 정상 (후보 0건은 정상 결과).
        실행 기록이 없으면 WARNING.
        """
        from config.constants import SCREENER_SNAPSHOT_ENABLED
        if not SCREENER_SNAPSHOT_ENABLED:
            return

        today = now_kst().date()

        # 1차: 훅 실행 여부 확인 (DB 없이 판단 가능)
        lh = getattr(self.bot, 'liquidation_handler', None)
        snapshot_done_date = getattr(lh, '_snapshot_done_date', None) if lh else None
        if snapshot_done_date == today:
            # 훅이 오늘 실행됨 — DB 행 수도 참고로 로깅
            try:
                from db.connection import DatabaseConnection
                with DatabaseConnection.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT COUNT(*) FROM screener_snapshots WHERE scan_date = CURRENT_DATE"
                        )
                        row = cur.fetchone()
                        count = row[0] if row else 0
                self.logger.info(f"EOD 스크리너 스냅샷 실행 완료 (DB 저장 {count}건, 0건은 후보 없음)")
            except Exception as e:
                self.logger.info(f"EOD 스크리너 스냅샷 실행 완료 (DB 조회 오류: {e})")
            return

        # 2차: 훅 미실행 → WARNING
        self.logger.warning("EOD 스크리너 스냅샷 훅이 오늘 실행되지 않음 (_snapshot_done_date 미설정)")

    def _verify_eod_fund_integrity(self) -> None:
        """EOD 자금 정합성 검증 (FundManager 내부 등식 확인)"""
        fund_manager = getattr(self.bot, 'fund_manager', None)
        if fund_manager is None:
            return

        integrity = fund_manager.verify_fund_integrity()
        if not integrity['is_valid']:
            self.logger.critical(
                f"EOD 자금 정합성 검증 실패: "
                f"차이={integrity['discrepancy']:,.0f}원, "
                f"total={integrity['total_funds']:,.0f}, "
                f"available={integrity['available_funds']:,.0f}, "
                f"reserved={integrity['reserved_funds']:,.0f}, "
                f"invested={integrity['invested_funds']:,.0f}"
            )
        else:
            self.logger.info(
                f"EOD 자금 정합성 검증 통과: "
                f"total={integrity['total_funds']:,.0f}원, "
                f"available={integrity['available_funds']:,.0f}, "
                f"reserved={integrity['reserved_funds']:,.0f}, "
                f"invested={integrity['invested_funds']:,.0f}, "
                f"보유종목={integrity['position_count']}개"
            )

    async def _save_portfolio_snapshot(self, current_time) -> None:
        """포트폴리오 스냅샷 저장 -- 미구현"""
        self.logger.debug("포트폴리오 스냅샷 저장 기능 미구현 (스킵)")

    async def _log_system_status(self) -> None:
        """시스템 상태 로깅"""
        try:
            current_time = now_kst()
            from utils.korean_time import get_market_status
            market_status = get_market_status()

            # 주문 요약
            order_summary = self.bot.order_manager.get_order_summary()

            # 데이터 수집 상태
            candidate_stocks = self.bot.data_collector.get_candidate_stocks()
            data_counts = {stock.code: len(stock.ohlcv_data) for stock in candidate_stocks}

            # API 통계 수집
            from api import kis_auth
            api_stats = kis_auth.get_api_statistics()

            # API 매니저 통계
            api_manager_stats = (
                self.bot.broker.get_api_statistics()
                if hasattr(self.bot.broker, 'get_api_statistics')
                else {}
            )

            # 후보 선정 통계
            selection_stats = {}

            status_lines = [
                f"시스템 상태 [{current_time.strftime('%H:%M:%S')}]",
                f"  - 시장 상태: {market_status}",
                f"  - 미체결 주문: {order_summary['pending_count']}건",
                f"  - 완료 주문: {order_summary['completed_count']}건",
                f"  - 데이터 수집: {data_counts}",
                f"  - API 통계: 총 {api_stats['total_calls']}회 호출, "
                f"성공률 {api_stats['success_rate']}%, "
                f"속도제한 {api_stats['rate_limit_errors']}회 ({api_stats['rate_limit_rate']}%)"
            ]

            # 후보 선정 통계 추가
            if selection_stats and selection_stats.get('total_analyzed', 0) > 0:
                status_lines.append(
                    f"  - 후보 선정: 전체 {selection_stats['total_analyzed']}개 분석, "
                    f"1차 통과 {selection_stats['passed_basic_filter']}개 "
                    f"({selection_stats.get('basic_filter_rate', 0)}%), "
                    f"최종 선정 {selection_stats['final_selected']}개 "
                    f"({selection_stats.get('final_selection_rate', 0)}%)"
                )

            self.logger.info("\n".join(status_lines))

            # 시장현황 대시보드 출력
            await self._run_market_dashboard()

        except Exception as e:
            self.logger.error(f"시스템 상태 로깅 오류: {e}")

    async def _run_market_dashboard(self) -> None:
        """시장현황 대시보드 출력"""
        if self._dashboard is None:
            return
        if not is_market_open():
            return  # 장 마감 후 불필요 갱신 방지
        try:
            import asyncio
            await asyncio.to_thread(self._dashboard.generate_dashboard)
        except Exception as e:
            self.logger.warning(f"시장현황 대시보드 오류 (무시): {e}")

    async def _refresh_api(self) -> None:
        """API 재초기화"""
        try:
            self.logger.info("API 24시간 주기 재초기화 시작")

            # API 매니저 재초기화
            if not await self.bot.broker.connect():
                self.logger.error("API 재초기화 실패")
                await self.bot.telegram.notify_error("API Refresh", "API 재초기화 실패")
                return False

            self.logger.info("API 재초기화 완료")
            await self.bot.telegram.notify_system_status("API 재초기화 완료")
            return True

        except Exception as e:
            self.logger.error(f"API 재초기화 오류: {e}")
            await self.bot.telegram.notify_error("API Refresh", e)
            return False

    def get_last_daily_report_date(self) -> None:
        """마지막 리포트 날짜 반환"""
        return self._last_daily_report_date

    def set_last_daily_report_date(self, date) -> None:
        """마지막 리포트 날짜 설정"""
        self._last_daily_report_date = date
