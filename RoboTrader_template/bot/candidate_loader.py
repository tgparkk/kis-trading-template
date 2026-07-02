"""
후보 종목 로딩 모듈
스크리너 기반 후보 종목 로딩 및 거래량 순위 폴백 로직을 담당합니다.
"""
import logging
from typing import Dict, Optional, TYPE_CHECKING

from utils.logger import setup_logger
from config.constants import MAX_CANDIDATES_PER_STRATEGY

if TYPE_CHECKING:
    from main import DayTradingBot


class CandidateLoader:
    """후보 종목 로딩 담당 클래스"""

    def __init__(self, bot: 'DayTradingBot') -> None:
        self._bot = bot
        self.logger = setup_logger(__name__)

    async def reload_candidates(self) -> None:
        """후보 종목 강제 재로드 (장중 스크리너 파일 갱신 시 사용)

        _candidates_loaded 플래그와 재시도 카운터를 리셋한 뒤
        즉시 _load_screener_candidates()를 호출합니다.

        # TODO: 텔레그램 /reload 명령어에서 이 메서드를 호출하도록 연결
        #        (core/telegram_integration.py 의 커맨드 핸들러 추가 필요)
        """
        self.logger.info("후보 종목 재로드 요청")
        self._bot._candidates_loaded = False
        self._bot._candidate_load_retries = 0
        await self._load_screener_candidates()

    async def _load_screener_candidates(self):
        """후보 종목 로드: 스크리너 우선, 없으면 거래량 순위 자동 수집.

        다중 전략(self.strategies dict)이 있으면 전략별 독립 후보 풀을 구성합니다.
        단일/없음 전략이면 기존 단일 풀 동작을 유지합니다(backward compat).
        """
        if self._bot._candidates_loaded:
            return

        # 후보 소비 전에 당일 스크리너 스냅샷을 직전 거래일 기준으로 생성(없으면).
        # 직전 거래일 일봉은 야간 적재 완료라 항상 채워지며, 소비자(이 메서드)와 같은 날 정렬된다.
        # run_screener_snapshot_hook 내부 _snapshot_done_date 가드로 하루 1회만 실제 실행.
        try:
            if getattr(self._bot, 'liquidation_handler', None) is not None:
                await self._bot.liquidation_handler.run_screener_snapshot_hook()
        except Exception as e:
            self.logger.warning(f"스크리너 스냅샷 생성 스킵(무시): {e}")

        try:
            max_candidates = MAX_CANDIDATES_PER_STRATEGY
            strategy_config = getattr(self._bot.config, 'strategy', None)
            if isinstance(strategy_config, dict):
                max_candidates = strategy_config.get('parameters', {}).get('max_candidates', MAX_CANDIDATES_PER_STRATEGY)
            elif hasattr(strategy_config, 'parameters'):
                max_candidates = strategy_config.parameters.get('max_candidates', MAX_CANDIDATES_PER_STRATEGY)

            # ── 다중 전략 모드 ────────────────────────────────────────────────
            if len(self._bot.strategies) > 1:
                await self._load_candidates_multi_strategy(max_candidates)
                return

            # ── 단일/없음 전략 모드 (backward compat) ────────────────────────
            # 1순위: 스크리너 JSON에서 로드
            candidates = self._bot.candidate_selector.load_from_screener(
                max_candidates=max_candidates
            )

            # 2순위: 스크리너 없으면 거래량 순위 API 자동 수집
            if not candidates:
                self.logger.info("스크리너 파일 없음 → 거래량 순위 기반 자동 수집 시작")
                candidates = await self._bot.candidate_selector.select_daily_candidates(
                    max_candidates=max_candidates
                )

            if not candidates:
                self.logger.warning("후보 종목 없음 — 스크리너/자동수집 모두 실패")
                self._bot._candidates_loaded = True
                return

            # DB 저장 (자동 수집된 후보)
            try:
                if self._bot.db_manager and hasattr(self._bot.db_manager, 'candidate_repo'):
                    self._bot.db_manager.candidate_repo.save_candidate_stocks(candidates)
                    self.logger.info(f"후보 종목 {len(candidates)}건 DB 저장 완료")
            except Exception as e:
                self.logger.warning(f"후보 종목 DB 저장 실패 (무시): {e}")

            # TradingStockManager에 등록
            registered = 0
            strategy_name = self._bot.strategy.name if self._bot.strategy else "unknown"
            for c in candidates:
                success = await self._bot.trading_manager.add_selected_stock(
                    stock_code=c.code,
                    stock_name=c.name,
                    selection_reason=c.reason,
                    prev_close=c.prev_close,
                    owner_strategy=strategy_name,
                )
                if success:
                    # 순수 전략 이름 설정 (DB strategy 컬럼용)
                    ts = self._bot.trading_manager.get_trading_stock(c.code, strategy=strategy_name)
                    if ts:
                        ts.strategy_name = strategy_name
                    registered += 1

            self._bot._candidates_loaded = True
            self.logger.info(f"후보 종목 {registered}/{len(candidates)}개 등록 완료")

            # 텔레그램 알림
            try:
                msg = (f"후보 종목 등록: {registered}종목\n"
                       + "\n".join(f"  - {c.code}({c.name})" for c in candidates[:registered]))
                await self._bot.telegram.notify_system_status(msg)
            except Exception:
                pass

        except Exception as e:
            self.logger.error(f"후보 종목 로드 오류: {e}")
            self._bot._candidate_load_retries = getattr(self._bot, '_candidate_load_retries', 0) + 1
            if self._bot._candidate_load_retries >= 3:
                self._bot._candidates_loaded = True  # 3회 실패 후 포기
                self.logger.error("후보 종목 로딩 3회 실패 - 금일 매수 불가")
            else:
                self.logger.warning(f"후보 종목 로딩 실패 ({self._bot._candidate_load_retries}/3) - 재시도 예정")

    async def _load_candidates_multi_strategy(self, max_per_strategy: int = 10) -> None:
        """다중 전략 모드: 전략별 독립 후보 풀을 로드하고 TradingStockManager에 등록.

        - select_candidates_per_strategy()로 전략별 후보를 중복 없이 분리합니다.
        - 같은 종목이 두 전략에 등장하면 선행 전략만 등록하고 INFO 로그를 남깁니다.
        - 후보가 전혀 없는 전략은 거래량 순위 API fallback을 시도합니다.
        """
        pool_by_strategy = self._bot.candidate_selector.select_candidates_per_strategy(
            self._bot.strategies, max_per_strategy=max_per_strategy
        )

        # 전 전략 후보 0건일 때만 거래량 순위 안전망 폴백(전략별 무조건 폴백 제거)
        if should_use_volume_fallback(pool_by_strategy):
            self.logger.info("[E6] 전 전략 후보 0건 → 거래량 순위 폴백(안전망)")
            try:
                fallback = await self._bot.candidate_selector.select_daily_candidates(
                    max_candidates=max_per_strategy
                )
                registered_codes = {
                    ts.stock_code for ts in self._bot.trading_manager.trading_stocks.values()
                }
                fallback = [c for c in fallback if c.code not in registered_codes]
                # 첫 번째 전략(fallback 수용 전략)에 배정
                for strategy_name in pool_by_strategy:
                    strategy_instance = self._bot.strategies.get(strategy_name)
                    accepts_fallback = getattr(strategy_instance, "accepts_volume_fallback", True)
                    if accepts_fallback:
                        # 폴백 풀에도 수용 전략의 스크리너 base_filter 적용
                        # (거래대금·시총 컷) → 유니버스 누수 차단(감사 2026-06-25 E).
                        filtered_fallback = apply_volume_fallback_with_filter(
                            strategy_name,
                            fallback,
                            broker=getattr(self._bot, "broker", None),
                            db_manager=getattr(self._bot, "db_manager", None),
                            config=getattr(self._bot, "config", None),
                        )
                        pool_by_strategy[strategy_name] = filtered_fallback
                        self.logger.info(
                            f"[E6] 거래량 폴백 배정 → {strategy_name} "
                            f"({len(filtered_fallback)}/{len(fallback)}종목, base_filter 적용)"
                        )
                        break
            except Exception as e:
                self.logger.warning(f"[E6] 거래량 순위 폴백 실패: {e}")

        total_registered = 0
        for strategy_name, candidates in pool_by_strategy.items():
            for c in candidates:
                # 전략별 자본 독립: 같은 종목을 여러 전략이 각자 보유 가능.
                # 동일 전략(owner)의 중복 등록만 add_selected_stock 내부에서 거부된다.
                success = await self._bot.trading_manager.add_selected_stock(
                    stock_code=c.code,
                    stock_name=c.name,
                    selection_reason=c.reason,
                    prev_close=c.prev_close,
                    owner_strategy=strategy_name,
                )
                if success:
                    ts = self._bot.trading_manager.get_trading_stock(c.code, strategy=strategy_name)
                    if ts:
                        ts.strategy_name = strategy_name
                    total_registered += 1

        self._bot._candidates_loaded = True
        self.logger.info(
            f"[E6] 다중 전략 후보 등록 완료: {total_registered}종목 "
            f"({len(self._bot.strategies)}전략)"
        )

        # 텔레그램 알림
        try:
            lines = []
            for s_name, cands in pool_by_strategy.items():
                if cands:
                    lines.append(
                        f"  [{s_name}] "
                        + ", ".join(f"{c.code}({c.name})" for c in cands)
                    )
            msg = f"후보 종목 등록: {total_registered}종목\n" + "\n".join(lines)
            await self._bot.telegram.notify_system_status(msg)
        except Exception:
            pass


def should_use_volume_fallback(per_strategy_candidates: dict) -> bool:
    """전략별 후보 dict 기준 거래량순위 폴백 사용 여부.

    하나라도 후보가 있으면 폴백 안 함(전략별 격리 유지). 전부 비었을 때만 안전망 폴백.
    """
    if not per_strategy_candidates:
        return True
    return all(not v for v in per_strategy_candidates.values())


def apply_volume_fallback_with_filter(
    strategy_name: str,
    fallback: list,
    *,
    broker=None,
    db_manager=None,
    config=None,
    universe_lookup: Optional[Dict[str, Dict]] = None,
    scan_date=None,
):
    """거래량 순위 폴백 풀(CandidateStock 리스트)에 수용 전략의 스크리너
    base_filter(거래대금≥10억·시총<5천억 등)를 적용해 유니버스 위반 종목을 제거한다.

    폴백 풀은 원래 스크리너 base_filter를 거치지 않아 daytrading 유니버스를 위반했다
    (감사 2026-06-25 E). 여기서 수용 전략의 어댑터를 얻어 base_filter로 거른다.

    - 어댑터가 없거나(미지원 전략) base_filter가 없으면, 또는 유니버스 스냅샷 조회가
      실패하면 컨셉 필터를 적용할 수 없으므로 빈 풀을 반환한다(fail-closed, 2026-06-27 M1).
      무필터 폴백을 반환하면 대형주 거래량 폴백이 소형/중소형 컨셉 전략에 누수된다.
    - CandidateStock은 market_cap/trading_value를 들지 않으므로 quant 유니버스 스냅샷
      (스크리너와 동일 SSOT)에서 code→{market_cap, trading_value}를 조회해 dict로 변환 후
      base_filter에 통과시킨다. 스냅샷에 없는 종목은 base_filter가 trading_value 미상(0)을
      컷으로 처리해 자연히 제외된다.
    """
    if not fallback:
        return fallback

    from runners._adapter_factory import build_adapter

    adapter = build_adapter(
        strategy_name, broker=broker, db_manager=db_manager, config=config
    )
    base_filter = getattr(adapter, "base_filter", None) if adapter is not None else None
    if base_filter is None:
        # 어댑터 미존재/필터 미지원 → 컨셉 필터를 못 거므로 폴백 종목을 넣지 않는다
        # (fail-closed). 무필터 폴백을 반환하면 대형주 거래량 폴백이 소형/중소형
        # 컨셉 전략(daytrading<5천억·ma5/ma20≤3조)에 누수된다(2026-06-27 M1).
        logging.getLogger(__name__).warning(
            f"[E6] {strategy_name} base_filter 없음 → 폴백 풀 fail-closed(빈 풀)"
        )
        return []

    # code → {market_cap, trading_value} 조회 (주입 또는 quant 스냅샷)
    if universe_lookup is None:
        universe_lookup = {}
        try:
            from db.quant_daily_reader import QuantDailyReader
            from utils.korean_time import now_kst
            sd = scan_date or now_kst().date()
            for it in QuantDailyReader().get_universe_snapshot(sd):
                universe_lookup[str(it["stock_code"])] = {
                    "market_cap": it.get("market_cap", 0),
                    "trading_value": it.get("trading_value", 0),
                }
        except Exception as e:
            # 스냅샷 조회 실패 → base_filter를 적용할 수 없으므로 폴백 종목을 넣지
            # 않는다(fail-closed). 무필터 폴백 반환은 유니버스 위반 누수를 만든다(M1).
            logging.getLogger(__name__).warning(
                f"[E6] 폴백 base_filter용 유니버스 스냅샷 조회 실패 → 폴백 풀 fail-closed(빈 풀): {e}"
            )
            return []

    # CandidateStock → base_filter용 dict (market_cap/trading_value 보강)
    dict_universe = []
    by_code = {}
    for c in fallback:
        info = universe_lookup.get(c.code, {})
        u = {
            "code": c.code,
            "name": getattr(c, "name", c.code),
            "market": getattr(c, "market", "KRX"),
            "market_cap": info.get("market_cap", 0),
            "trading_value": info.get("trading_value", 0),
        }
        dict_universe.append(u)
        by_code[c.code] = c

    passed_codes = {u["code"] for u in base_filter(dict_universe)}
    return [by_code[code] for code in passed_codes if code in by_code]
