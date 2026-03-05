"""
일일 매매 판단 현황 및 수익률 요약

장 마감 후(15:30) 실행하여 오늘의 매매 내역과 수익률을 확인합니다.
PostgreSQL(TimescaleDB) 기반.
"""
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from utils.korean_time import now_kst
from db.connection import DatabaseConnection


def print_today_trading_summary():
    """오늘의 매매 현황 요약"""
    today = now_kst().strftime('%Y-%m-%d')

    print("=" * 100)
    print(f"📊 일일 매매 판단 현황 및 수익률 요약")
    print("=" * 100)
    print(f"날짜: {today}")
    print(f"생성 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)
    print()

    with DatabaseConnection.get_connection() as conn:
        cursor = conn.cursor()

        # ==================== 1. 오늘의 매매 내역 ====================
        print("=" * 100)
        print("1️⃣ 오늘의 매매 내역")
        print("=" * 100)
        print()

        # 매수 내역
        cursor.execute('''
            SELECT stock_code, stock_name, quantity, price,
                   (quantity * price) as total_amount,
                   target_profit_rate, stop_loss_rate,
                   timestamp
            FROM virtual_trading_records
            WHERE action = 'BUY'
              AND is_test = false
              AND (timestamp AT TIME ZONE 'Asia/Seoul')::date = %s::date
            ORDER BY timestamp
        ''', (today,))

        buy_records = cursor.fetchall()

        if buy_records:
            print(f"💰 매수 내역 ({len(buy_records)}건)")
            print("-" * 100)
            print(f"{'시간':<10} {'종목코드':<10} {'종목명':<20} {'수량':>8} {'매수가':>12} "
                  f"{'매수금액':>15} {'목표익절':>10} {'손절':>10}")
            print("-" * 100)

            total_buy_amount = 0
            for row in buy_records:
                stock_code, stock_name, qty, buy_price, total_amt, target_profit, stop_loss, ts = row
                time_str = ts.strftime('%H:%M') if hasattr(ts, 'strftime') else str(ts)[:5]

                tp_str = f"{float(target_profit)*100:.1f}%" if target_profit else "N/A"
                sl_str = f"{float(stop_loss)*100:.1f}%" if stop_loss else "N/A"

                print(f"{time_str:<10} {stock_code:<10} {stock_name:<20} {int(qty):>8,} {float(buy_price):>12,.0f} "
                      f"{float(total_amt):>15,.0f} {tp_str:>10} {sl_str:>10}")

                total_buy_amount += float(total_amt)

            print("-" * 100)
            print(f"{'총 매수 금액:':<70} {total_buy_amount:>15,.0f}원")
            print()
        else:
            print("💰 매수 내역: 없음")
            print()

        # 매도 내역
        cursor.execute('''
            SELECT stock_code, stock_name, quantity, price,
                   (quantity * price) as total_amount,
                   profit_loss, profit_rate,
                   timestamp
            FROM virtual_trading_records
            WHERE action = 'SELL'
              AND is_test = false
              AND (timestamp AT TIME ZONE 'Asia/Seoul')::date = %s::date
            ORDER BY timestamp
        ''', (today,))

        sell_records = cursor.fetchall()

        if sell_records:
            print(f"💸 매도 내역 ({len(sell_records)}건)")
            print("-" * 100)
            print(f"{'시간':<10} {'종목코드':<10} {'종목명':<20} {'수량':>8} {'매도가':>12} "
                  f"{'매도금액':>15} {'손익':>15} {'수익률':>10}")
            print("-" * 100)

            total_sell_amount = 0
            total_profit_loss = 0
            profit_count = 0
            loss_count = 0

            for row in sell_records:
                stock_code, stock_name, qty, sell_price, total_amt, pl, pl_rate, ts = row
                time_str = ts.strftime('%H:%M') if hasattr(ts, 'strftime') else str(ts)[:5]
                pl = float(pl or 0)
                pl_rate = float(pl_rate or 0)

                pl_sign = "+" if pl >= 0 else ""
                pl_color = "🟢" if pl >= 0 else "🔴"

                print(f"{time_str:<10} {stock_code:<10} {stock_name:<20} {int(qty):>8,} {float(sell_price):>12,.0f} "
                      f"{float(total_amt):>15,.0f} {pl_color}{pl:>14,.0f} {pl_sign}{pl_rate*100:>9.1f}%")

                total_sell_amount += float(total_amt)
                total_profit_loss += pl

                if pl >= 0:
                    profit_count += 1
                else:
                    loss_count += 1

            print("-" * 100)
            print(f"{'총 매도 금액:':<70} {total_sell_amount:>15,.0f}원")
            print(f"{'총 손익:':<70} {total_profit_loss:>15,.0f}원")
            print(f"{'승률:':<70} {profit_count}/{len(sell_records)} ({profit_count/len(sell_records)*100:.1f}%)")
            print()
        else:
            print("💸 매도 내역: 없음")
            print()

        # ==================== 2. 현재 보유 종목 및 평가 ====================
        print("=" * 100)
        print("2️⃣ 현재 보유 종목 및 평가")
        print("=" * 100)
        print()

        cursor.execute('''
            SELECT
                b.stock_code,
                b.stock_name,
                b.quantity,
                b.price as avg_buy_price,
                b.target_profit_rate,
                b.stop_loss_rate
            FROM virtual_trading_records b
            WHERE b.action = 'BUY'
              AND b.is_test = false
              AND NOT EXISTS (
                SELECT 1 FROM virtual_trading_records s
                WHERE s.buy_record_id = b.id
                  AND s.action = 'SELL'
              )
            ORDER BY b.stock_name
        ''')

        holdings = cursor.fetchall()

        total_unrealized_pl = 0
        if holdings:
            print(f"📦 보유 종목 ({len(holdings)}개)")
            print("-" * 120)
            print(f"{'종목코드':<10} {'종목명':<20} {'수량':>8} {'평균매수가':>12} {'매수금액':>15} "
                  f"{'현재가':>12} {'평가금액':>15} {'평가손익':>15} {'수익률':>10}")
            print("-" * 120)

            total_buy_value = 0
            total_current_value = 0

            for stock_code, stock_name, qty, avg_buy, target_profit, stop_loss in holdings:
                qty = int(qty)
                avg_buy = float(avg_buy)
                # 최신 종가 조회
                cursor.execute('''
                    SELECT close
                    FROM daily_prices
                    WHERE stock_code = %s
                    ORDER BY date DESC
                    LIMIT 1
                ''', (stock_code,))

                price_row = cursor.fetchone()
                current_price = float(price_row[0]) if price_row else avg_buy

                buy_value = qty * avg_buy
                current_value = qty * current_price
                unrealized_pl = current_value - buy_value
                unrealized_pl_rate = (unrealized_pl / buy_value) if buy_value > 0 else 0

                pl_sign = "+" if unrealized_pl >= 0 else ""
                pl_color = "🟢" if unrealized_pl >= 0 else "🔴"

                print(f"{stock_code:<10} {stock_name:<20} {qty:>8,} {avg_buy:>12,.0f} {buy_value:>15,.0f} "
                      f"{current_price:>12,.0f} {current_value:>15,.0f} "
                      f"{pl_color}{unrealized_pl:>14,.0f} {pl_sign}{unrealized_pl_rate*100:>9.1f}%")

                total_buy_value += buy_value
                total_current_value += current_value
                total_unrealized_pl += unrealized_pl

            print("-" * 120)
            if total_buy_value > 0:
                print(f"{'합계:':<50} {total_buy_value:>15,.0f} {'':<12} {total_current_value:>15,.0f} "
                      f"{total_unrealized_pl:>15,.0f} {total_unrealized_pl/total_buy_value*100:>9.1f}%")
            print()
        else:
            print("📦 보유 종목: 없음")
            print()

        # ==================== 3. 누적 수익률 ====================
        print("=" * 100)
        print("3️⃣ 누적 수익률 (전체 기간)")
        print("=" * 100)
        print()

        # 전체 매매 손익
        cursor.execute('''
            SELECT
                COALESCE(SUM(CASE WHEN action = 'SELL' THEN profit_loss ELSE 0 END), 0) as total_realized_pl,
                COUNT(CASE WHEN action = 'SELL' AND profit_loss > 0 THEN 1 END) as win_count,
                COUNT(CASE WHEN action = 'SELL' AND profit_loss < 0 THEN 1 END) as loss_count,
                COUNT(CASE WHEN action = 'SELL' THEN 1 END) as total_trades
            FROM virtual_trading_records
            WHERE is_test = false
        ''')

        pl_row = cursor.fetchone()
        total_realized_pl = float(pl_row[0] or 0)
        win_count = pl_row[1] or 0
        loss_count = pl_row[2] or 0
        total_trades = pl_row[3] or 0

        total_pl = total_realized_pl + total_unrealized_pl
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

        print(f"실현 손익: {total_realized_pl:>15,.0f}원")
        print(f"미실현 손익: {total_unrealized_pl:>15,.0f}원")
        print(f"총 손익: {total_pl:>15,.0f}원")
        print()
        print(f"총 매매 횟수: {total_trades}회")
        print(f"승: {win_count}회, 패: {loss_count}회")
        print(f"승률: {win_rate:.1f}%")
        print()

        # ==================== 4. 오늘의 데이터 수집 현황 ====================
        print("=" * 100)
        print("4️⃣ 오늘의 데이터 수집 현황")
        print("=" * 100)
        print()

        # 일봉 데이터
        cursor.execute('''
            SELECT COUNT(DISTINCT stock_code)
            FROM daily_prices
            WHERE date = %s::date
        ''', (today,))
        daily_count = cursor.fetchone()[0] or 0

        print(f"일봉 데이터 수집: {daily_count:,}개 종목 ({today})")
        print()

    print("=" * 100)
    print("✅ 요약 완료!")
    print("=" * 100)
    print()


def main():
    try:
        print_today_trading_summary()
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
