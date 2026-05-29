# Changelog 2026-05-29 — 펀더멘털 일봉 다년 백필 + 재검증

> 10권 시리즈 완료 후 "다음 단계" = 데이터 백필(사장님 선택). 펀더멘털 책(Greenblatt·O'Shaughnessy)의 6개월 단일국면 한계 해소.

## 배경
- Greenblatt·O'Shaughnessy는 market_cap이 6개월(2025-07~2026-02, 124일)만 있어 단일 BULL 국면만 검증됐음.
- 재무 79종목의 daily_prices도 ~200일(2025-07~)뿐 → 다년 백테스트 불가.

## 스코핑 발견
- pykrx 고수준 fundamental/market_cap 함수 **깨짐**(KRX 컬럼매핑) — OHLCV만 작동.
- **`strategy_analysis.daily_candles`**: 2021-01-12~2026-02-10, 5년, OHLCV 보유 → 토대 소스.
  - ⚠️ daily_candles.market_cap은 **전부 0**(관리자 COUNT 검증이 0을 '존재'로 세어 속음 — 직원이 잡음).
  - 실제 시총 = **`strategy_analysis.yearly_fundamentals.market_cap_won`** (연 1회 값).

## 백필 (사장님 승인 후 --apply)
- 신규 스크립트 `scripts/backfill_daily_prices_fundamental.py` (기존 etl 패턴: dry-run→--apply, INSERT ON CONFLICT DO NOTHING, 멱등, DROP/TRUNCATE/UPDATE 금지)
- OHLCV ← daily_candles, market_cap ← yearly_fundamentals(연도매칭), adj_factor=1.0(기존 행도 1.0, 스케일 정합)
- 결과: daily_prices(재무종목) **15,723 → 158,190행 (+142,467)**, 기간 2021-01-12~2026-05-29, market_cap 94.2%, 기존 행 무변경
- 버그수정: --apply의 `autocommit=False`가 열린 트랜잭션과 충돌 → rollback() 선행

## 0가격 데이터 가드
- 백필된 과거 행에 open=high=low=0 (거래정지/결손) **671건/18종목**(2021 261건 등 초기 집중) → ZeroDivisionError
- greenblatt·oshaughnessy simulate_one_stock에 가드 3종(매수 fill≤0 skip, 청산 fill≤0 defer, forced-close close≤0 skip). zero_price_exits=0 확인

## 🔑 다년 재검증 결과 — Sharpe 붕괴 (핵심)
| 룰 | 6개월(이전) | 5년(백필후) |
|----|-----------|------------|
| Greenblatt magic_formula_top A | 38T +10.04% Sharpe 0.41 (per-trade 84% win) | 308T +18.26% **Sharpe 0.12** (per-trade 50.7% win +7.26%) |
| Greenblatt magic_formula_top B | 197T +7.79% Sharpe 0.36 | 1724T +8.43% **Sharpe 0.05** (per-trade 47.7% +0.75%) |
| O'Shaughnessy low_psr A | 38T +8.26% Sharpe 0.36 | 310T +12.54% **Sharpe 0.11** (per-trade 48.4% +7.47%) |
| O'Shaughnessy low_psr B | 200T +6.67% Sharpe 0.37 | 1721T +3.02% **Sharpe 0.05** (per-trade 46.4% +0.82%) |
| O'Shaughnessy value_composite A | — | 288T +10.92% (per-trade 47.2% +5.58%) |

- **결론: 6개월 숫자는 단일 BULL 거품. 다년·다국면에선 Sharpe 0.4→0.1 붕괴, per-trade 승률 84%→~48%(동전).**
- low_psr이 다년에서도 O'Shaughnessy 베스트 유지("PSR=가치 팩터의 왕" 재확인). magic_formula_top·low_psr 여전히 각 책 1위.
- threshold/high_roc_value(절대임계값)는 다년에도 소표본·음수 — 여전히 부적합.
- **시사점: 강건성 검증(다년)이 백필의 진짜 가치. 펀더멘털 순위는 약한 양 엣지이나 risk-adjusted로는 미미.**

## 검증
- pytest tests/books/: (재실행 영향 없음, 책 룰 단위테스트 무관). leaderboard greenblatt 8 + osullivan 8 = 16행 갱신.
- n_eligible per date: dates=1241 (이전 124) — 다국면 확보.

## 산출물
- scripts/backfill_daily_prices_fundamental.py (신규)
- greenblatt_magic_formula/report.md, osullivan_what_works/report.md 다년 addendum
- index.md 갱신

## 다음 후보
- daily 시총 정밀화(상장주수×일별close) / 분기재무·배당 백필(DART) / 상위 기술적 룰(Elder·Minervini) 동일 다년 walk-forward
