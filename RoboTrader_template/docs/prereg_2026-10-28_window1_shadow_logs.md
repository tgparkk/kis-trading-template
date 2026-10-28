# 사전등록 — 10-29 창구 묶음 A 그림자 로그 4종 (2026-10-28 밤 작성 · 동결 = 커밋)

- 목적: 규칙을 바꾸기 «전에» 건수를 잰다(🔒 「그림자 N주 먼저」). **매매 판단·주문·체결 동작 변화 0** — 로그 줄만 늘어난다.
- 측정 기간: **2026-10-30(목) ~ 2026-11-12(목) · 2주(10거래일)**. 자료 = `logs/robotrader_template_*.log`(페이퍼) · `logs/<instance>/`(실전).
- 볼 날: **11-13 회의** — 건수와 비율만 본다. 이 메모에는 판정 언어(통과·기각·문턱)를 두지 않는다.

## 로그 정의
1. `[재매수-shadow] {code} {strategy} 직전매도={전략}/{종류}/{YYYY-MM-DD HH:MM} 거래일차={n} 같은전략={Y|N} 매수가비={+x.xx%|-}`
   - 자리: `bot/trading_analyzer.py` 매수 판단, 엔진 호출 직전. 직전 매도 = 같은 종목의 가장 최근 SELL(어떤 전략이든) · 오늘 이전 KOSPI 거래일 5개 창 안(페이퍼 `virtual_trading_records` · 실전 = 인스턴스 표).
   - 종류 = 사유 문자열 분류(익절/손절/MA20 이탈/EMA 이탈/기타). 매수가비 = 캐시 현재가(없으면 신호 참조가) ÷ 직전 매도가 − 1.
   - 🔒 SR1: 손절 뒤(또는 사유를 모르는 손실 매도 뒤 — 실전 표 reason 은 `실전매매` 뿐) 매수가비 칸 «-».
   - 같은 (종목, 전략, 직전 매도)는 1회만 · 조회 캐시 (종목, 오늘) TTL 10분.
2. `[자투리-shadow] would_skip=1 {code} amount={금액} target={종목당 예산} ratio={x.xx}`
   - 자리: `core/trading_decision_engine.py` 수량 산정 뒤. 조건 amount < target × 0.5(`SCRAP_BUY_SHADOW_RATIO`). 주문은 그대로 나간다.
   - target: 실전 = `total_funds × max_position_ratio(0.09)` · 가상 = 전략 원장 종목당 금액(per_stock, 상한 cap 반영 · 현금 잔여 항 제외).
3. `[ma20-왕복-shadow] {code} held_sec={n|-} would_block={1|0}` — `book_pullback_ma20` MA20 trailing 이탈 매도 신호마다. would_block = 보유 60초 미만. 매도 신호는 그대로.
4. `[주문가-괴리] {code} 신호가={} 주문가={} {+x.xx%}` — 엔진 수량 산정 뒤(주문이 나가는 건만). 신호가 = `signal.price` → `metadata['close']` → 사유의 `close=`. 없으면 줄 없음.

## 11-13 에 볼 것(숫자만)
- 로그별 건수(전략별 · 페이퍼/실전 분리) · `would_skip=1` 건수 · `would_block=1` 비율 · 재매수 «종류 × 같은전략» 교차표 · 괴리 분포(중앙값·하위 10%).

## 롤백
- 전체 = 커밋 revert(+ 재기동). 재매수 로그만 끄기 = `.env` 에 `REBUY_SHADOW=off`(`0`·`false` 동일) + 재기동.
