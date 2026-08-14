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

# 🔴 이 리포트가 찍는 손익은 «전부 gross» 다.
# virtual_trading_records.profit_loss = (매도가-매수가)×수량 이며 위탁수수료
# (매수·매도 각 0.015%)도 증권거래세(매도 0.18%)도 빠져 있다. 2026-08-14 실측:
# 리포트 284,104원 vs 실제 net 270,335원(core.fund_manager "매매 손익 반영"
# 합) → 5.1% 과대. 누적으로는 손실이 1,685,761원 과소 표기된다.
#
# ⚠️ 그래서 «여기서 수수료를 다시 계산하지 않는다». 이미 적용 시점이 달라
# 서로 어긋나는 현금 원장이 둘 있고, 리포트에 세 번째 계산식을 심으면 두
# 번째 틀린 숫자가 될 뿐이다. 그리고 net 실현손익은 DB 어디에도 없다:
#   · virtual_trading_records  — profit_loss/profit_rate 뿐, 수수료 컬럼 없음
#   · paper_strategy_equity.realized_pnl_cum — 같은 gross 컬럼의 SUM
#   · paper_trading_state.eod_balance — «현금 잔고»이지 실현손익이 아니다
#   · trading_decision_engine 의 pnl_with_fees(=net) — FundManager 메모리와
#     로그에만 남고 어느 테이블에도 적재되지 않는다
# ⇒ 값은 그대로 두고 라벨이 스스로 gross 임을 밝히게 한다(값을 고치는 것이
#    아니라 «거짓말을 멈추는» 수정).
GROSS_LABEL_SUFFIX = '(gross·수수료/거래세 미반영)'

# 🔴 gross 에서 «파생된 판정»(승/패·승률)도 같은 꼬리표를 받아야 한다.
# 금액은 읽는 사람이 보정할 수 있지만 승/패는 이미 내려진 결론이라 더 나쁘다.
# 리뷰 구성 사례: 매수 100주 @10,000 / 매도 100주 @10,010 → gross +1,000,
# 수수료·거래세 2,101.95 → net −1,102. 돈을 잃은 거래가 「승률 100%」로 찍힌다.
#
# ⚠️ 그래도 «net 승률을 계산하지 않는다» — 금액과 같은 이유다(세 번째 수수료
# 계산식 금지). 대신 산술이 필요 없는 사실 하나만 덧붙인다: 수수료·세금은 항상
# 양수라 모든 거래에서 net ≤ gross 이므로 {net 승} ⊆ {gross 승},
# 즉 **gross 승률은 net 승률의 «상한»**이다. 부등호지 수식이 아니다.
#
# 🔴 그리고 «상한»에서 멈춰야 한다. 부분집합(⊆)은 진부분집합(⊊)이 아니므로
# 「일부는 실제로 net 패다」·「상한이지 net 승률이 아니다」는 이 부등식이
# 허락하지 않는 단언이다(전 거래가 손익분기를 크게 넘으면 두 승률은 «같다»).
# 🔑 게다가 「실제로 일부가 손익분기 아래에 있다」를 세우는 일 자체가 위에서
# 거절한 손익분기 계산이다 — 산술을 피하려고 쓴 문장이 산술을 했어야만 참이
# 되는 문장이면, 그건 이 파일이 없애려던 「표시 ≠ 실제」를 하나 더 만드는 것이다.
# ⇒ 단언이 아니라 «가능성»으로 적는다.
#
# 승/패 관례는 §3 SQL 쪽(> 0 승 / < 0 패, 0원은 어느 쪽도 아님)으로 통일한다.
# 0원 거래는 수수료·거래세만큼 «확정» net 손실이라 승으로 셀 근거가 없고,
# 한 리포트 안에 서로 다른 승률이 둘 있는 것 자체가 결함이었다.
GROSS_DISCLAIMER = (
    "⚠️ 위 손익과 승/패·승률은 모두 gross 기준이다 — 위탁수수료(매수·매도 각 "
    "0.015%)와 증권거래세(매도 0.18%)가 빠져 있어 이익은 과대·손실은 과소로 "
    "나온다. 수수료·세금은 항상 양수라 net ≤ gross 이므로 gross 승 중 일부는 "
    "실제로는 net 패일 수 있다 — 즉 위 승률은 net 승률의 «상한»이다. "
    "net 실현손익은 DB 어느 테이블에도 적재돼 있지 않다(실제 net 은 "
    "로그의 'fund_manager 매매 손익 반영' 라인이 기준)."
)

# §2 보유 종목 표의 평가손익·수익률·합계도 같은 이유로 gross 다(매도 시
# 발생할 수수료·거래세 미반영). 표가 고정폭이라 컬럼 머리마다 꼬리표를 달면
# 정렬이 깨지므로 표 위에 한 줄로 고지한다.
# ⚠️ 「청산하면 수수료·거래세만큼 줄어든다」로만 쓰면 «매도 다리»만 말하게 돼
# 빠진 비용을 한 다리 적게 알린다 — 매수 때 이미 낸 위탁수수료도 평가손익에
# 안 들어 있다.
GROSS_HOLDINGS_NOTE = (
    f"※ 아래 표의 평가손익·수익률·합계{GROSS_LABEL_SUFFIX} — "
    "매수 때 이미 낸 위탁수수료도, 청산 시 낼 매도 수수료·거래세도 빠져 있다."
)

# 승/패/보합 색·부호 관례(§1 매도 행·§2 보유 행 공용).
# 0원은 승도 패도 아니다 — 집계 술어(profit_loss > 0 / < 0)와 «같은» 관례를
# 써야 한다. 예전엔 집계만 > 0 이고 행 렌더링은 >= 0 이라, 0원 거래가 초록으로
# 찍히면서 승률은 50% 였다(이 파일이 없애려던 「한 리포트 두 판정」의 축소판).
PL_MARK_WIN = '🟢'
PL_MARK_LOSS = '🔴'
PL_MARK_FLAT = '⚪'


def _pl_marks(value):
    """(색, 부호 접두사) — 0원은 보합(⚪·부호 없음)."""
    if value > 0:
        return PL_MARK_WIN, "+"
    if value < 0:
        return PL_MARK_LOSS, ""
    return PL_MARK_FLAT, ""


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

            for row in sell_records:
                stock_code, stock_name, qty, sell_price, total_amt, pl, pl_rate, ts = row
                time_str = ts.strftime('%H:%M') if hasattr(ts, 'strftime') else str(ts)[:5]
                pl = float(pl or 0)
                pl_rate = float(pl_rate or 0)

                pl_color, pl_sign = _pl_marks(pl)

                print(f"{time_str:<10} {stock_code:<10} {stock_name:<20} {int(qty):>8,} {float(sell_price):>12,.0f} "
                      f"{float(total_amt):>15,.0f} {pl_color}{pl:>14,.0f} {pl_sign}{pl_rate*100:>9.1f}%")

                total_sell_amount += float(total_amt)
                total_profit_loss += pl

                # 관례는 §3 누적 집계 SQL(profit_loss > 0 승 / < 0 패)과 동일하다.
                # 예전엔 여기만 `pl >= 0` 이라 0원 거래가 «승»이 돼, 같은 리포트
                # 안의 두 승률이 갈렸다(§1 2/2 100% vs §3 50%). 0원은 수수료·
                # 거래세만큼 확정 net 손실이라 승이 아니다. 분모는 양쪽 모두
                # 전체 매도 건수(§3 의 total_trades)로 맞춘다.
                if pl > 0:
                    profit_count += 1

            print("-" * 100)
            print(f"{'총 매도 금액:':<70} {total_sell_amount:>15,.0f}원")
            print(f"{'총 손익' + GROSS_LABEL_SUFFIX + ':':<70} {total_profit_loss:>15,.0f}원")
            print(f"{'승률' + GROSS_LABEL_SUFFIX + ':':<70} {profit_count}/{len(sell_records)} ({profit_count/len(sell_records)*100:.1f}%)")
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
            print(GROSS_HOLDINGS_NOTE)
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

                pl_color, pl_sign = _pl_marks(unrealized_pl)

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

        # 전체 매매 손익 — profit_loss 는 gross 다(파일 상단 GROSS_* 주석 참조).
        # 별칭도 gross 임을 밝힌다: 「realized」라고만 부르면 코드 안에서도
        # net 으로 오해된다.
        cursor.execute('''
            SELECT
                COALESCE(SUM(CASE WHEN action = 'SELL' THEN profit_loss ELSE 0 END), 0) as total_realized_pl_gross,
                COUNT(CASE WHEN action = 'SELL' AND profit_loss > 0 THEN 1 END) as win_count,
                COUNT(CASE WHEN action = 'SELL' AND profit_loss < 0 THEN 1 END) as loss_count,
                COUNT(CASE WHEN action = 'SELL' THEN 1 END) as total_trades
            FROM virtual_trading_records
            -- is_test 필터 제거(2026-08-11): 위 매수 쿼리와 동일한 사유
            -- (source 필터가 형제 프로젝트 분리를 이미 담당).
            WHERE source = %s
        ''', (SOURCE_KIS_TEMPLATE,))

        pl_row = cursor.fetchone()
        total_realized_pl_gross = float(pl_row[0] or 0)
        win_count = pl_row[1] or 0
        loss_count = pl_row[2] or 0
        total_trades = pl_row[3] or 0

        total_pl_gross = total_realized_pl_gross + total_unrealized_pl
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

        # 미해결 종목은 §2 합계에서 빠졌으므로 여기 미실현/총 손익도 그만큼
        # 불완전하다. 꼬리표 없이 찍으면 "완전한 수"로 읽혀 §2 의 경고가 무력화된다.
        unresolved_note = (
            f"  (⚠️ 현재가 미해결 {len(unresolved_codes)}종목 제외)"
            if unresolved_codes else ""
        )
        print(f"실현 손익{GROSS_LABEL_SUFFIX}: {total_realized_pl_gross:>15,.0f}원")
        print(f"미실현 손익{GROSS_LABEL_SUFFIX}: {total_unrealized_pl:>15,.0f}원{unresolved_note}")
        print(f"총 손익{GROSS_LABEL_SUFFIX}: {total_pl_gross:>15,.0f}원{unresolved_note}")
        print()
        print(f"총 매매 횟수: {total_trades}회")
        # 승/패는 profit_loss > 0 / < 0 이므로 0원 거래는 어느 쪽도 아니다
        # (총 매매 횟수에는 남는다) — §1 승률도 같은 관례를 쓴다.
        # ⚠️ 그래서 승+패 < 총 이 될 수 있다. 그 이유는 «주석»에만 있고 리포트
        # 독자는 못 보므로, 보합 건수를 함께 찍어 삼항이 더해지게 한다
        # (「1승 0패」를 순진하게 읽으면 100% 로 보인다). 건수 뺄셈이지
        # 수수료 모델이 아니다 — 새 원장이 생기지 않는다.
        flat_count = total_trades - win_count - loss_count
        print(f"승/패/보합{GROSS_LABEL_SUFFIX}: "
              f"{win_count}회 / {loss_count}회 / {flat_count}회")
        print(f"승률{GROSS_LABEL_SUFFIX}: {win_rate:.1f}%")
        # 🔴 고지문은 손익 «과» 승/패·승률 «아래»에 둔다. c1b9dc3 에서는 손익
        # 줄 바로 뒤(=판정 위)에 있었고 문구도 「위 손익은」이라, 정작 더 위험한
        # 판정(승률)을 덮지 못했다.
        print(GROSS_DISCLAIMER)
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
