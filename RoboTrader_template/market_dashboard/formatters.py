"""대시보드 출력 포맷터

콘솔/로그용 출력 포맷터. 숫자 데이터만 보여주고 시장 판단(상승/횡보/하락)은 하지 않습니다.
"""
from datetime import datetime
from typing import List, Optional

from .models import (
    PremarketBriefing,
    MarketDashboardData,
    InvestorFlow,
    PositionSummary,
    DomesticMarketSnapshot,
    GlobalMarketSnapshot,
)


class ConsoleFormatter:
    """콘솔/로그 출력 포맷터"""

    SEPARATOR = "=" * 60
    THIN_SEP = "-" * 60

    # ------------------------------------------------------------------
    # 숫자 포맷 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _sign(value: float) -> str:
        """양수에 + 부호를 붙여 반환합니다."""
        if value > 0:
            return f"+{value:,.2f}"
        return f"{value:,.2f}"

    @staticmethod
    def _sign_int(value: int) -> str:
        """정수에 + 부호를 붙여 반환합니다."""
        if value > 0:
            return f"+{value:,}"
        return f"{value:,}"

    @staticmethod
    def _sign_rate(value: float) -> str:
        """등락률을 +X.XX% 형태로 반환합니다."""
        if value > 0:
            return f"+{value:.2f}%"
        return f"{value:.2f}%"

    @staticmethod
    def _format_amount(value: float) -> str:
        """거래대금(억원)을 표시합니다. 1조 이상이면 X.X조, 아니면 X,XXX억."""
        if abs(value) >= 10000:
            return f"{value / 10000:.1f}조"
        return f"{value:,.0f}억"

    @staticmethod
    def _format_price(value: float) -> str:
        """가격을 천단위 콤마로 포맷합니다. 정수면 소수점 없이, 아니면 소수점 2자리."""
        if value == int(value):
            return f"{int(value):,}"
        return f"{value:,.2f}"

    @staticmethod
    def _format_volume(value: int) -> str:
        """거래량을 천단위 콤마로 포맷합니다."""
        return f"{value:,}"

    # ------------------------------------------------------------------
    # 장전 브리핑 포맷
    # ------------------------------------------------------------------

    @staticmethod
    def format_premarket_briefing(briefing: PremarketBriefing) -> str:
        """장전 브리핑을 콘솔 출력 문자열로 포맷합니다."""
        fmt = ConsoleFormatter
        lines: List[str] = []

        # 헤더
        briefing_time = briefing.briefing_time or datetime.now()
        lines.append(fmt.SEPARATOR)
        lines.append("  장전 브리핑 (Pre-Market Briefing)")
        lines.append("  {}".format(briefing_time.strftime("%Y-%m-%d %H:%M:%S")))
        lines.append(fmt.SEPARATOR)

        # 해외시장 섹션
        global_mkt: Optional[GlobalMarketSnapshot] = briefing.global_market
        if global_mkt is not None and global_mkt.indices:
            lines.append("")
            lines.append("  [해외시장]")
            lines.append(fmt.THIN_SEP)
            lines.append(
                "  {:<12} {:>12}  {:>10}  {:>8}".format(
                    "지수", "현재가", "등락", "등락률"
                )
            )
            lines.append(fmt.THIN_SEP)
            for idx in global_mkt.indices:
                lines.append(
                    "  {:<12} {:>12}  {:>10}  {:>8}".format(
                        idx.name,
                        fmt._format_price(idx.value),
                        fmt._sign(idx.change),
                        fmt._sign_rate(idx.change_rate),
                    )
                )

        # 환율 섹션
        if global_mkt is not None and global_mkt.exchange_rates:
            lines.append("")
            lines.append("  [환율]")
            lines.append(fmt.THIN_SEP)
            for er in global_mkt.exchange_rates:
                lines.append(
                    "  {:<12} {:>10}     {} ({})".format(
                        er.pair,
                        fmt._format_price(er.rate),
                        fmt._sign(er.change),
                        fmt._sign_rate(er.change_rate),
                    )
                )

        # 전일 국내시장 섹션
        dom: Optional[DomesticMarketSnapshot] = briefing.domestic_prev_close
        if dom is not None and (dom.kospi is not None or dom.kosdaq is not None):
            lines.append("")
            lines.append("  [전일 국내시장]")
            lines.append(fmt.THIN_SEP)
            for index_data in [dom.kospi, dom.kosdaq]:
                if index_data is None:
                    continue
                name_map = {"코스피": "KOSPI", "코스닥": "KOSDAQ"}
                display_name = name_map.get(index_data.name, index_data.name)
                lines.append(
                    "  {:<10} {:>10}    {} ({})".format(
                        display_name,
                        fmt._format_price(index_data.value),
                        fmt._sign(index_data.change),
                        fmt._sign_rate(index_data.change_rate),
                    )
                )

        # 푸터
        lines.append(fmt.SEPARATOR)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 장중 대시보드 포맷
    # ------------------------------------------------------------------

    @staticmethod
    def format_dashboard(data: MarketDashboardData) -> str:
        """장중 대시보드를 콘솔 출력 문자열로 포맷합니다."""
        fmt = ConsoleFormatter
        lines: List[str] = []

        # 헤더
        dashboard_time = data.dashboard_time or datetime.now()
        lines.append(fmt.SEPARATOR)
        lines.append("  시장현황 대시보드")
        lines.append("  {}".format(dashboard_time.strftime("%Y-%m-%d %H:%M:%S")))
        lines.append(fmt.SEPARATOR)

        dom: Optional[DomesticMarketSnapshot] = data.domestic

        # 시장 지수 섹션
        if dom is not None and (dom.kospi is not None or dom.kosdaq is not None):
            lines.append("")
            lines.append("  [시장 지수]")
            lines.append(fmt.THIN_SEP)
            for index_data in [dom.kospi, dom.kosdaq]:
                if index_data is None:
                    continue
                name_map = {"코스피": "KOSPI", "코스닥": "KOSDAQ"}
                display_name = name_map.get(index_data.name, index_data.name)
                amount_str = ""
                if index_data.trade_amount > 0:
                    amount_str = "  거래대금: {}".format(
                        fmt._format_amount(index_data.trade_amount)
                    )
                lines.append(
                    "  {:<10} {:>10}    {} ({}){}".format(
                        display_name,
                        fmt._format_price(index_data.value),
                        fmt._sign(index_data.change),
                        fmt._sign_rate(index_data.change_rate),
                        amount_str,
                    )
                )

        # 투자자별 동향 섹션
        if dom is not None and dom.investor_flow is not None:
            flow = dom.investor_flow
            # 모든 값이 0이면 건너뛰기
            if not (
                flow.foreign_net == 0
                and flow.institution_net == 0
                and flow.individual_net == 0
            ):
                lines.append("")
                lines.append("  [투자자별 동향]")
                lines.append(fmt.THIN_SEP)

                def _flow_str(label, value):
                    sign = "+" if value > 0 else ""
                    return "{}: {}{:,.0f}억".format(label, sign, value)

                lines.append(
                    "  {}  {}  {}".format(
                        _flow_str("외국인", flow.foreign_net),
                        _flow_str("기관", flow.institution_net),
                        _flow_str("개인", flow.individual_net),
                    )
                )

        # 거래량 상위 섹션
        if dom is not None and dom.volume_rank:
            lines.append("")
            lines.append("  [거래량 상위]")
            lines.append(fmt.THIN_SEP)
            lines.append(
                "  {:>3}  {:<14} {:>10}  {:>8}  {:>12}".format(
                    "#", "종목명", "현재가", "등락률", "거래량"
                )
            )
            for stock in dom.volume_rank:
                lines.append(
                    "  {:>3}  {:<14} {:>10}  {:>8}  {:>12}".format(
                        stock.rank,
                        stock.stock_name,
                        fmt._format_price(stock.current_price),
                        fmt._sign_rate(stock.change_rate),
                        fmt._format_volume(stock.volume),
                    )
                )

        # 보유 포지션 섹션
        positions = data.positions or []
        if positions:
            lines.append("")
            lines.append("  [보유 포지션] ({}종목)".format(len(positions)))
            lines.append(fmt.THIN_SEP)
            lines.append(
                "  {:<12} {:>5}  {:>8}  {:>8}  {:>10}  {:>8}".format(
                    "종목명", "수량", "매입가", "현재가", "손익", "손익률"
                )
            )
            for pos in positions:
                lines.append(
                    "  {:<12} {:>5}  {:>8}  {:>8}  {:>10}  {:>8}".format(
                        pos.stock_name,
                        pos.quantity,
                        fmt._format_price(pos.avg_price),
                        fmt._format_price(pos.current_price),
                        fmt._sign_int(int(pos.profit_loss)),
                        fmt._sign_rate(pos.profit_loss_rate),
                    )
                )
            # 합계
            total_pnl = data.total_profit_loss
            total_eval = data.total_eval_amount
            sign = "+" if total_pnl > 0 else ""
            lines.append(
                "  합계: {}{:,}원 (평가액: {:,}원)".format(
                    sign, int(total_pnl), int(total_eval)
                )
            )
        else:
            lines.append("")
            lines.append("  [보유 포지션] 없음")

        # 푸터
        lines.append(fmt.SEPARATOR)
        return "\n".join(lines)
