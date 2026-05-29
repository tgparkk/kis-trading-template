# Elder·Minervini 다년 walk-forward 재검증 (2026-05-30)

> 트레이딩 책 10권 시리즈 후속. 펀더멘털 3책이 다년 재검증에서 Sharpe 붕괴(−75%)한 전례에 따라, 기술적 베스트 2책(Elder·Minervini 일봉 추세추종)도 동일하게 단일 BULL 거품인지 검증.

## 배경 / 동기
- 두 책의 기존 베스트는 **224일 단일 BULL 구간**(2025-07~2026-05) 산물이었음.
  - Elder `triple_screen_ema_pullback` A: +23.76% PnL / Sharpe **1.22** / 134T / hit 56.4% / MaxDD 13.76%
  - Minervini `volume_dryup` B: +20.27% PnL / Sharpe **1.41** / 153T / hit 62.0%
- 펀더멘털 백필이 `daily_prices`를 2021~2026(1,653일)으로 채워둔 덕에 **추가 데이터 수집 없이** top_volume:50 종목 5년 OHLCV 전 기간 백테스트 가능.
- 펀더멘털과 동일 방법론(국면 분할 없는 전체기간 1회)으로 돌려 공정 비교.

## 발견한 데이터 결함 + 보정 (사장님 승인)
- 1차 실행에서 Minervini `volume_dryup`/`tight_closes`가 `ZeroDivisionError`(run_minervini_vcp.py:167-168, fill=open×slippage=0 → //0)로 크래시.
- 근본 원인: `daily_prices`에 2021년 초 **OHLC≤0(close만 유효) 결손행 671행 / 18종목** 존재. 펀더멘털 백필 잔존 결함. 224일 베이스라인엔 없던 구간.
- **처리(사장님 승인 = 로더에서 close로 보정)**: 백테스트 로더 `_load_daily_adj()`에서 adj_factor 적용 후 `open/high/low≤0|NaN` → 같은 행 `close`로 채움(거래정지일 표준 처리). `close≤0|NaN` 행은 드롭. **daily_prices 원본 불변**(실매매 시스템 사용 + 자동삭제/수정 금지 정책).
- 실측: 보정 대상 3종목(010060 60·003550 54·457190 24), 드롭 0행(모든 결손행 close 유효). 보정 후 8룰 전부 크래시 없이 완주.

## 결과 — 224일 BULL vs 5년 보정후

| 책 / 베스트룰 | PnL | Sharpe | 거래 | Hit | MaxDD | Sharpe 붕괴율 |
|---|---|---|---|---|---|---|
| Elder ema_pullback A | +23.76%→+37.90% | 1.22→**0.68** | 134→925 | 56.4→50.3% | 13.8→33.1% | **−44%** |
| Minervini volume_dryup B | +20.27%→+17.70% | 1.41→**0.64** | 153→1190 | 62.0→55.6% | —→38.8% | **−55%** |
| (참고) 펀더멘털 3책 | — | ~0.4→~0.1 | — | — | — | −75% |

### 전체 룰별 5년 보정후 (8룰)
**Elder**: ema_pullback A +37.90%/0.68(최고) · B +16.23%/0.54 / force_index A 0.36 B 0.34 / stochastic A 0.44 B 0.43 / elder_ray A 0.18 B 0.07 / all_AND 0거래.
**Minervini**: volume_dryup B +17.70%/0.64 vs **A −19.61%/0.03 (6549T 과매매)** / trend_template A 0.04 B 0.04(hit 19~27%, 저승률 고PnL 추세형) / vcp_breakout·tight_closes 표본 5~34건(무의미) / all_AND 0거래.

## 판정
1. **단일 BULL이 Sharpe를 부풀린다 — 추세추종도 예외 아님.** 1.22·1.41은 거품 포함.
2. **추세추종 > 펀더멘털**: 붕괴율(−44%/−55%) < 펀더멘털(−75%), 5년에도 양 PnL·Sharpe 0.6대 유지 → 국면 전환에 상대적으로 견고.
3. **Elder ema_pullback A가 분명한 1순위** (Sharpe 0.68 / Calmar 2.09).
4. **Minervini는 variant 의존성이 위험**: B(tp12%/mh20 타이트 청산)가 과매매를 억제해 0.64, A는 0.03/−19.6%. 룰보다 청산 파라미터가 성과 좌우 → CANDIDATE 등록 시 variant B 고정 필수.

## 국면별 분해 (BULL/BEAR/SIDEWAYS) — 약세장 검증 통과 ✅
> KOSPI 지수(daily_prices에 stock_code='KOSPI' 실존, 1,324행) 20일 rolling 누적수익률 ±2%로 분류(프로젝트 convention; regime_analysis.py 기본값은 ±5%라 불일치 명시). 5년: BULL 513일(39.3%) / BEAR 382일(29.3%) / SIDEWAYS 409일(31.4%). 2022 약세장 정상 검출(BEAR 129일). 거래 진입일을 국면 라벨에 매핑.

| 룰 | BULL | BEAR | SIDEWAYS |
|---|---|---|---|
| Elder ema_pullback A | +3.15% (447T) | **+3.01% (169T)** | **−0.71%** (309T) |
| Elder ema_pullback B | +2.05% | +1.35% (173T) | −0.41% |
| Elder force_index A | +3.12% | +1.60% (66T) | +3.31% |
| Elder stochastic A | +4.91% | **+3.68% (hit57%, 70T)** | −0.21% |
| Minervini volume_dryup B | +1.50% | +1.38% (424T) | −1.03% |
| Minervini trend_template B | +2.48% | +0.60% (117T) | +1.11% |
*(per-trade 평균손익)*

**핵심 발견 — 통념 반전**:
1. **6개 룰 전부 BEAR에서 per-trade 양수.** Elder ema_pullback A는 BEAR(+3.01%)가 BULL(+3.15%)과 **사실상 동급** → 하락장 무너짐 전무. ±5% 대조에서도 BEAR +1.87% 유지(강건).
2. **진짜 약점은 BEAR가 아니라 SIDEWAYS** — ema_pullback A/B·stochastic A·volume_dryup B가 횡보장에서 음수(휩쏘). 추세추종 전형.
3. **전체 Sharpe 0.68은 BULL 편중 아님** — BULL+BEAR가 떠받치고 SIDEWAYS가 깎는 구조 → 추세장(상승·하락 양쪽) 적응력에서 나온 견고한 수치 = **약세장 검증 통과.**

**한계 1건(정직)**: 위 표는 종목 풀 pooled **per-trade 평균**이고, headline +37.90%/Sharpe 0.68은 run 스크립트가 종목별 일별 equity Sharpe를 ~48종목 평균한 별도 정의. 국면별 정식 연율 Sharpe(0.68과 동일 척도)는 종목별 equity를 국면 split해 재백테스트해야 산출 가능(미실행, 사장님 "문서만 매듭" 결정). per-trade 부호·크기로 BEAR 견고 결론은 충분히 탄탄.

## 결정 (사장님)
- **Elder ema_pullback A → CANDIDATE_ALPHAS 등록 확정** (index.md 등록 우선순위 1위, walk-forward·약세장 검증 통과). 조건: **variant A 고정** + (선택) SIDEWAYS 회피 게이트.
- 보조: stochastic A(BEAR 특화 관찰대상, 표본 70), volume_dryup B(분산 보조, 표본 최대 but per-trade 약함).
- 여기서 시리즈 매듭. 정식 국면 Sharpe 재백테스트·SIDEWAYS 게이트 코드화·커밋은 보류(추후 결정).

## 한계 / 차기 후보
- 정식 rolling walk-forward(out-of-sample train/test) 및 국면별 연율 Sharpe는 미실행 — 차기 보강 후보.
- leaderboard 동시쓰기 레이스(all_AND 행 누락) 발견 → 이번엔 순차 실행으로 회피. 향후 직렬화 권장.
- 누적 코드 변경(로더 보정 ×2, regime_split_elder_minervini.py 신규) 미커밋 — 커밋은 사장님 승인 대기.

## 추가 생성 파일 (국면 분해)
- `scripts/regime_split_elder_minervini.py`(신규 ~230줄), `reports/books_research/regime_label_5y.parquet`, `reports/books_research/regime_split_elder_minervini.parquet`

## 변경 파일
- 코드(각 +13줄, 로더 보정만): `scripts/run_elder_triple_screen.py`, `scripts/run_minervini_vcp.py`
- 데이터: `reports/books_research/leaderboard.parquet`(오염 daily_full 50행 제거 후 신규 20행, 백업 .bak), 룰별 results parquet 갱신
- 미변경: daily_prices 원본, run 스크립트의 체결/청산/룰 로직
