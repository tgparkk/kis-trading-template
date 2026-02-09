"""
P3-4: 성과 리포트 자동 생성

일일 성과 리포트: 매매내역, 승률, 손익, 보유종목 현황
포맷: 마크다운 + 텔레그램 전송 가능한 텍스트
"""
from datetime import datetime
from typing import Any, Dict, List, Optional


def generate_daily_report(
    trades: List[Dict[str, Any]],
    positions: List[Dict[str, Any]],
    fund_status: Dict[str, Any],
    date: Optional[datetime] = None,
) -> str:
    """
    일일 성과 리포트 생성

    Args:
        trades: 체결 내역 리스트
            각 항목: {order_id, stock_code, side, quantity, price, amount, timestamp}
        positions: 보유종목 현황
            각 항목: {stock_code, stock_name, quantity, avg_price, current_price,
                      profit_loss, profit_loss_rate}
        fund_status: 자금 현황
            {total_funds, available_funds, reserved_funds, invested_funds,
             utilization_rate, position_count}
        date: 리포트 날짜 (None이면 오늘)

    Returns:
        str: 마크다운 형식 리포트 텍스트
    """
    if date is None:
        date = datetime.now()

    lines: List[str] = []
    lines.append(f"📊 **일일 매매 리포트** ({date.strftime('%Y-%m-%d')})")
    lines.append("")

    # ── 매매 요약 ──
    buy_trades = [t for t in trades if t.get('side') == 'buy']
    sell_trades = [t for t in trades if t.get('side') == 'sell']
    total_buy_amount = sum(t.get('amount', 0) for t in buy_trades)
    total_sell_amount = sum(t.get('amount', 0) for t in sell_trades)

    lines.append("**📈 매매 요약**")
    lines.append(f"• 총 거래: {len(trades)}건 (매수 {len(buy_trades)} / 매도 {len(sell_trades)})")
    lines.append(f"• 매수 금액: {total_buy_amount:,.0f}원")
    lines.append(f"• 매도 금액: {total_sell_amount:,.0f}원")
    lines.append("")

    # ── 승률/손익 ──
    pnl_stats = _calc_pnl_stats(trades)
    lines.append("**💰 손익 현황**")
    lines.append(f"• 실현 손익: {pnl_stats['realized_pnl']:+,.0f}원")
    lines.append(f"• 승률: {pnl_stats['win_rate']:.1f}% ({pnl_stats['wins']}승 {pnl_stats['losses']}패)")
    if pnl_stats['avg_profit'] > 0:
        lines.append(f"• 평균 수익: +{pnl_stats['avg_profit']:,.0f}원 / 평균 손실: {pnl_stats['avg_loss']:,.0f}원")
    lines.append("")

    # ── 매매 내역 ──
    if trades:
        lines.append("**📋 매매 내역**")
        for t in trades:
            side_emoji = "🔴" if t.get('side') == 'buy' else "🔵"
            side_text = "매수" if t.get('side') == 'buy' else "매도"
            code = t.get('stock_code', '?')
            qty = t.get('quantity', 0)
            price = t.get('price', 0)
            amount = t.get('amount', qty * price)
            ts = t.get('timestamp')
            time_str = ts.strftime('%H:%M') if isinstance(ts, datetime) else ''
            lines.append(
                f"{side_emoji} {code} {side_text} {qty}주 @{price:,.0f} "
                f"({amount:,.0f}원) {time_str}"
            )
        lines.append("")

    # ── 보유종목 현황 ──
    lines.append("**🏦 보유종목 현황**")
    if positions:
        total_eval = 0
        total_pnl = 0
        for p in positions:
            code = p.get('stock_code', '?')
            name = p.get('stock_name', code)
            qty = p.get('quantity', 0)
            avg = p.get('avg_price', 0)
            cur = p.get('current_price', 0)
            pnl = p.get('profit_loss', (cur - avg) * qty)
            pnl_rate = p.get('profit_loss_rate', (cur - avg) / avg if avg else 0)
            eval_amt = cur * qty

            total_eval += eval_amt
            total_pnl += pnl

            emoji = "📈" if pnl >= 0 else "📉"
            lines.append(
                f"{emoji} {name}({code}) {qty}주 "
                f"평단 {avg:,.0f} → 현재 {cur:,.0f} "
                f"({pnl_rate:+.2%}, {pnl:+,.0f}원)"
            )
        lines.append(f"• 평가 합계: {total_eval:,.0f}원 (평가손익 {total_pnl:+,.0f}원)")
    else:
        lines.append("• 보유종목 없음")
    lines.append("")

    # ── 자금 현황 ──
    lines.append("**💵 자금 현황**")
    total = fund_status.get('total_funds', 0)
    available = fund_status.get('available_funds', 0)
    reserved = fund_status.get('reserved_funds', 0)
    invested = fund_status.get('invested_funds', 0)
    util = fund_status.get('utilization_rate', 0)
    pos_count = fund_status.get('position_count', 0)

    lines.append(f"• 총 자산: {total:,.0f}원")
    lines.append(f"• 가용 현금: {available:,.0f}원")
    if reserved > 0:
        lines.append(f"• 예약 중: {reserved:,.0f}원")
    lines.append(f"• 투자 중: {invested:,.0f}원")
    lines.append(f"• 가동률: {util:.1%}")
    lines.append(f"• 보유 종목: {pos_count}개")
    lines.append("")

    lines.append(f"_생성: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_")

    return "\n".join(lines)


def _calc_pnl_stats(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    매매 내역에서 실현 손익 통계 계산

    매수→매도 쌍을 매칭하여 손익을 계산합니다.
    단순 FIFO 기준.
    """
    # 종목별 매수 내역 추적 (FIFO)
    buy_queue: Dict[str, List[Dict]] = {}
    realized_pnl = 0.0
    wins = 0
    losses = 0
    profit_amounts: List[float] = []
    loss_amounts: List[float] = []

    for t in trades:
        code = t.get('stock_code', '')
        side = t.get('side', '')
        qty = t.get('quantity', 0)
        price = t.get('price', 0)

        if side == 'buy':
            if code not in buy_queue:
                buy_queue[code] = []
            buy_queue[code].append({'quantity': qty, 'price': price})
        elif side == 'sell' and code in buy_queue:
            sell_qty = qty
            sell_price = price
            while sell_qty > 0 and buy_queue[code]:
                buy = buy_queue[code][0]
                match_qty = min(sell_qty, buy['quantity'])
                pnl = (sell_price - buy['price']) * match_qty

                realized_pnl += pnl
                if pnl >= 0:
                    wins += 1
                    profit_amounts.append(pnl)
                else:
                    losses += 1
                    loss_amounts.append(pnl)

                buy['quantity'] -= match_qty
                sell_qty -= match_qty
                if buy['quantity'] <= 0:
                    buy_queue[code].pop(0)

    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0.0
    avg_profit = sum(profit_amounts) / len(profit_amounts) if profit_amounts else 0.0
    avg_loss = sum(loss_amounts) / len(loss_amounts) if loss_amounts else 0.0

    return {
        'realized_pnl': realized_pnl,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'avg_profit': avg_profit,
        'avg_loss': avg_loss,
    }


def generate_telegram_report(
    trades: List[Dict[str, Any]],
    positions: List[Dict[str, Any]],
    fund_status: Dict[str, Any],
    date: Optional[datetime] = None,
) -> str:
    """
    텔레그램 전송용 간략 리포트

    마크다운 리포트의 축약 버전. 텔레그램 메시지 길이 제한(4096자) 고려.
    """
    if date is None:
        date = datetime.now()

    buy_trades = [t for t in trades if t.get('side') == 'buy']
    sell_trades = [t for t in trades if t.get('side') == 'sell']
    pnl = _calc_pnl_stats(trades)

    lines = [
        f"📊 {date.strftime('%m/%d')} 매매 리포트",
        f"거래 {len(trades)}건 (매수{len(buy_trades)}/매도{len(sell_trades)})",
        f"실현손익 {pnl['realized_pnl']:+,.0f}원",
        f"승률 {pnl['win_rate']:.0f}%",
    ]

    if positions:
        total_unrealized = sum(p.get('profit_loss', 0) for p in positions)
        lines.append(f"보유 {len(positions)}종목 (평가손익 {total_unrealized:+,.0f}원)")

    total = fund_status.get('total_funds', 0)
    util = fund_status.get('utilization_rate', 0)
    lines.append(f"총자산 {total:,.0f}원 (가동률 {util:.0%})")

    return "\n".join(lines)
