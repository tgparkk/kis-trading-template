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

# virtual_trading_records.source — robotrader DB는 형제 프로젝트(RoboTrader)와
# 테이블을 공유하므로, 이 프로젝트(kis-template) 데이터만 집계하도록 필터링한다.
SOURCE_KIS_TEMPLATE = 'kis_template'

# 보유 종목 표에서 현재가를 해석하지 못했을 때 쓰는 표기.
# 🔴 avg_buy(평균매수가) 대체 금지 — 그러면 평가손익이 «정확히 0» 으로 찍혀
#    「데이터 없음」이 「정상값 0」으로 둔갑한다(경보로 안 잡히는 형태).
UNRESOLVED_PRICE_MARK = '-'


def _resolve_current_price(cursor, stock_code, today, price_lookup):
    """보유 종목의 현재가를 3단계로 해석한다. 해결 불가 시 None.

    1) ``price_lookup`` — 봇 프로세스 안에서 실행될 때 주입되는 in-memory
       현재가 조회자(sync). ⚠️ **None 또는 <= 0 은 실패로 간주하고 2단계로
       내려간다** — 거래정지 종목은 0 을 주며(2026-08-12 15:36~15:42 에
       13종목이 api/kis_market_api.py:814 "현재가 정보 없음 (값: 0)" ERROR),
       그 0 을 그대로 곱하면 평가금액 0 이라는 더 나쁜 오보가 된다.
       조회자가 예외를 던져도 리포트를 죽이지 않고 2단계로 내려간다.

    2) daily_prices 의 **당일** 종가. 날짜 조건이 필수다 — 없으면
       ``ORDER BY date DESC LIMIT 1`` 이 구조적으로 **항상 전일 종가**를 준다.
       이 리포트는 bot/system_monitor.py 가 15:35 에 부르는데 당일 일봉은
       16:01 EOD 수집에서 들어오기 때문이다(2026-08-12 실측: 보유 60종목 중
       당일 종가와 일치한 건 1건뿐, 최대 괴리 6.46%).
       ⚠️ daily_prices.date 는 text('YYYY-MM-DD')라 ``%s::date`` 캐스팅을
       붙이면 "연산자 없음: text = date" 로 죽는다(§4 주석 참조). today 는
       이미 같은 형식의 문자열이므로 그대로 비교한다.

    3) 둘 다 실패 → None. 호출측이 "-" 로 표기하고 합계에서 제외한다.
    """
    if price_lookup is not None:
        try:
            value = price_lookup(stock_code)
        except Exception:
            value = None
        if value is not None:
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = None
            if value is not None and value > 0:
                return value

    cursor.execute('''
        SELECT close
        FROM daily_prices
        WHERE stock_code = %s
          AND date = %s
        LIMIT 1
    ''', (stock_code, today))

    row = cursor.fetchone()
    if row and row[0] is not None:
        try:
            close = float(row[0])
        except (TypeError, ValueError):
            return None
        if close > 0:
            return close
    return None


def print_today_trading_summary(price_lookup=None):
    """오늘의 매매 현황 요약

    Args:
        price_lookup: ``f(stock_code) -> price|None`` 형태의 **선택적** sync
            현재가 조회자. 봇 프로세스 안에서 호출될 때만 주입된다
            (bot/system_monitor.py). 생략하면(=CLI 단독 실행) 당일 일봉
            → 미해결 순으로 내려간다. 상세는 _resolve_current_price 참조.
    """
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
              -- is_test 필터 제거(2026-08-11): virtual_trading_records 는
              -- 페이퍼(가상) 매매 테이블이라 전 이력이 is_test=true 이고
              -- false 행은 0건이다(운영 규칙: "페이퍼 매매는 is_test=true
              -- 가 정상이며 필터로 거르지 말 것"). 형제 프로젝트 분리는
              -- 이미 source 필터가 담당하므로 is_test 는 중복이자
              -- 리포트가 항상 "매매 없음"을 출력하는 오작동 원인이었다.
              AND source = %s
              AND (timestamp AT TIME ZONE 'Asia/Seoul')::date = %s::date
            ORDER BY timestamp
        ''', (SOURCE_KIS_TEMPLATE, today))

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
              -- is_test 필터 제거(2026-08-11): 위 매수 쿼리와 동일한 사유
              -- (source 필터가 형제 프로젝트 분리를 이미 담당).
              AND source = %s
              AND (timestamp AT TIME ZONE 'Asia/Seoul')::date = %s::date
            ORDER BY timestamp
        ''', (SOURCE_KIS_TEMPLATE, today))

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
              -- is_test 필터 제거(2026-08-11): 위 매수 쿼리와 동일한 사유
              -- (source 필터가 형제 프로젝트 분리를 이미 담당).
              AND b.source = %s
              AND NOT EXISTS (
                SELECT 1 FROM virtual_trading_records s
                WHERE s.buy_record_id = b.id
                  AND s.action = 'SELL'
              )
            ORDER BY b.stock_name
        ''', (SOURCE_KIS_TEMPLATE,))

        holdings = cursor.fetchall()

        total_unrealized_pl = 0
        unresolved_codes = []
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
                buy_value = qty * avg_buy

                current_price = _resolve_current_price(
                    cursor, stock_code, today, price_lookup
                )

                if current_price is None:
                    # 현재가 미해결 — 합계 전체(매수금액 포함)에서 뺀다.
                    # 매수금액만 남기면 합계 행이 «평가금액 < 매수금액» 이 돼
                    # 있지도 않은 손실로 읽힌다(합계 행의 내부 정합성 우선).
                    unresolved_codes.append(stock_code)
                    print(f"{stock_code:<10} {stock_name:<20} {qty:>8,} {avg_buy:>12,.0f} {buy_value:>15,.0f} "
                          f"{UNRESOLVED_PRICE_MARK:>12} {UNRESOLVED_PRICE_MARK:>15} "
                          f"{UNRESOLVED_PRICE_MARK:>15} {UNRESOLVED_PRICE_MARK:>10}")
                    continue

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
            if unresolved_codes:
                print(f"⚠️ 현재가 미해결 {len(unresolved_codes)}종목(합계에서 제외): "
                      f"{', '.join(unresolved_codes)}")
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
            -- is_test 필터 제거(2026-08-11): 위 매수 쿼리와 동일한 사유
            -- (source 필터가 형제 프로젝트 분리를 이미 담당).
            WHERE source = %s
        ''', (SOURCE_KIS_TEMPLATE,))

        pl_row = cursor.fetchone()
        total_realized_pl = float(pl_row[0] or 0)
        win_count = pl_row[1] or 0
        loss_count = pl_row[2] or 0
        total_trades = pl_row[3] or 0

        total_pl = total_realized_pl + total_unrealized_pl
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

        # 미해결 종목은 §2 합계에서 빠졌으므로 여기 미실현/총 손익도 그만큼
        # 불완전하다. 꼬리표 없이 찍으면 "완전한 수"로 읽혀 §2 의 경고가 무력화된다.
        unresolved_note = (
            f"  (⚠️ 현재가 미해결 {len(unresolved_codes)}종목 제외)"
            if unresolved_codes else ""
        )
        print(f"실현 손익: {total_realized_pl:>15,.0f}원")
        print(f"미실현 손익: {total_unrealized_pl:>15,.0f}원{unresolved_note}")
        print(f"총 손익: {total_pl:>15,.0f}원{unresolved_note}")
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
        # daily_prices.date 는 kis_template 에서 text('YYYY-MM-DD') 컬럼이므로
        # ::date 캐스팅 없이 문자열 그대로 비교한다(캐스팅 시 "연산자 없음: text
        # = date"로 실패, 2026-07-10 라이브 로그). today 는 이미 'YYYY-MM-DD'
        # 문자열(위 now_kst().strftime 결과)이라 별도 정규화가 필요 없다.
        cursor.execute('''
            SELECT COUNT(DISTINCT stock_code)
            FROM daily_prices
            WHERE date = %s
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
