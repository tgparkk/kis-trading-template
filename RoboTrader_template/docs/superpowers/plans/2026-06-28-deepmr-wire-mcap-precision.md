# 2026-06-28 — deep_mr 멀티버스 배선 + 시총 백필 정밀화 + 8전략 5.5년 재측정

> 측정 전용·라이브/SSOT 무수정. 영구룰: 숫자 날조 금지 — 아래 수치는
> `scripts/step3d_backfill_5p5yr.py --shares-mode implied2024` (8전략, 2021-01-12~2026-06-26,
> 월별 PIT 67 scan) 실제 실행 산출. 원시: `scratchpad/step3d_deepmr_5p5yr.md`.
> **quant daily_prices 무변형**(메모리 override). 직전 executor가 토큰 한도로 측정 직전 끊겨,
> 측정·본 리포트·커밋은 관리자가 직접 마무리.

## 0. 한 줄 요약
① **deep_mr_dev20을 multiverse4 SPECS에 배선해 처음으로 5.5년 측정** → baseline Sharpe **+0.13 /
pnl −21% / MaxDD 64%** = 약체(envelope·daytrading·ma 계열과 동급, 5.5년 손실). ② **시총 백필을
"2024-내재주식수"로 정밀화**(FDR 현재주식수보다 역사값에 근접, 삼성 검증오차 0.85% vs 2.1%) →
cap-filter 전략 수치가 더 정직해짐(특히 **elder Sharpe 0.556→0.476, DD 62%→72%**). ③ 무-시총컷
전략(envelope·rs)은 정밀화에 **정확히 불변**(정합성 입증). ④ **시총 플로어 무효 결론은 또 재확인**.

## 1. deep_mr 배선 (Task 1)
- **진입**(`_sig_deep_mr`): 라이브 screener와 **동일 SSOT** `MeanReversionMA20Rule(ma20, entry_dev=-20%,
  rsi14, oversold30)`. config.yaml 값 무수정. (multiverse4_returns_export.py:146-152)
- **청산**(`MAReversionExitAdapter(ma=20, recovery_ratio=0.9)`, params sl=0.07/tp=0.12/max_hold=7):
  라이브 `evaluate_sell_conditions`(strategy.py:136-158)와 **우선순위·임계 1:1**
  (stop_loss 7% → take_profit 12% → ma_recovery(종가≥MA20×0.9) → max_hold 7거래일). 라이브 코드
  자체가 "백테스트 MAReversionExitAdapter 정합"이라 명시 = 설계상 정렬.
- **정직한 단순화(날조 아님)**: ① 사이징 max_per_stock=100만(타 7전략 동일 harness 정본; 라이브
  종목당 200만과 다름) ② top_n=300(거래대금 100억 컷 게이트 근사) ③ **K분할 진입 미모델링**
  (라이브는 균등 K분할; harness는 신호봉 전량 진입) — 엣지 방향 판별엔 영향 작으나 체결평균/
  타이밍 미세차 있음.
- 검증: `tests/test_multiverse4.py` **17 passed**, 기존 7전략 수치 회귀 없음.

## 2. 시총 백필 정밀화 (Task 2)
- **진짜 역사 주식수(KRX/pykrx)는 이 환경에서 차단**(`get_market_cap_by_ticker` KeyError 확인).
- 3단 우선순위(`--shares-mode`): **dart**(OPENDART 키 있을 때 진짜 역사값) → **implied2024**(기본:
  quant에 market_cap 실재하는 2024 첫 시점 `market_cap÷close`=내재주식수) → **fdr**(2026 현재주식수).
- **정밀도 검증**(삼성전자 발행주식수): 2024-내재 5.92e9 vs DART 보통주 5.97e9 = **오차 0.85%**,
  FDR현재 5.85e9 = 오차 2.1% → **2024-내재가 역사값에 더 근접**. 본 측정은 implied2024 사용
  (소스분포: implied2024 2405종목 / fdr 폴백 475).
- 채움률: raw 48.5% → **backfill 99.7%**(가드 OK).

## 3. 8전략 5.5년 최종표 (implied2024, baseline / floor300 / floor500)

| strategy | baseline Sharpe/pnl/MaxDD | floor300 | floor500 |
|---|---|---|---|
| minervini_volume_dryup | **+0.567 / +45.1% / 17.2%** | =baseline(null) | =baseline |
| rs_leader | +0.492 / +149.1% / 61.0% | =baseline(null) | =baseline |
| elder_ema_pullback | +0.476 / +132.6% / 71.9% | =baseline(null) | =baseline |
| daytrading_3methods_breakout | +0.144 / **−9.1%** / 53.9% | +0.151/−7.7% | +0.156/−6.6% |
| deep_mr_dev20 (NEW) | +0.129 / **−21.4%** / 64.4% | +0.166/−13.1% | +0.159/−13.2% |
| book_pullback_ma20 | +0.019 / **−30.1%** / 55.7% | +0.028/−28.7% | +0.001/−33.0% |
| book_envelope_200d | +0.089 / **−36.4%** / 78.5% | +0.102/−30.8% | +0.105/−30.2% |
| book_pullback_ma5 | **−0.107** / −41.0% / 61.3% | =baseline | =baseline |

union(시장 2486 대비): elder 36%·minervini 52%·daytrading 86%·deep_mr 76%·envelope/rs 98%·ma 95%.

## 4. 판정
### deep_mr_dev20 (최초 측정)
**약체 — 5.5년 손실(−21%), Sharpe 0.13, DD 64%.** floor300이 −21→−13%로 개선(무-시총컷이라 floor가
유일 사이즈게이트, envelope과 동형)이나 여전히 음수 pnl. "폭락 저격"은 발생 빈도가 낮아(2735 신호/
607 거래) 표본도 얇음. **폐기 검토군(daytrading·ma20·envelope·ma5)에 deep_mr 합류**. 단 폭락국면
한정 전략이라 5.5년 평균이 컨셉 평가에 불리할 수 있음(regime 특화 역할은 별도 고려).

### 시총 플로어 (재확인·최종)
**무효 결론 또 재확인.** cap-filter 전략(elder·minervini·rs·ma5)은 floor300/500이 baseline과 동일(null).
무-시총컷 전략(envelope·deep_mr·daytrading·ma20)에서만 약하게 +이나 pnl은 여전히 음수권. → 일괄
시총 플로어 도입 근거 없음(3회 독립 측정 일관).

### 정밀화 효과(implied2024 vs FDR현재 — 직전 step3d 대비)
- **무-시총컷(envelope·rs)**: 완전 동일(정밀화가 시총 게이트 전략만 건드림 = 정합성 입증).
- **cap-filter**: 변동. **elder 가장 큼**(Sharpe 0.556→0.476, pnl +177%→+133%, DD 61.6%→71.9%)
  = 더 정직(elder는 5천억 경계 근방이라 주식수 정확도가 유니버스 멤버십에 민감). daytrading·ma5도
  소폭 하향. minervini 불변(3천억 하한이 주식수 오차 무관 영역). → **정밀화는 cap-filter 전략을 더
  보수적으로(정직하게) 보정**, 결론(플로어 무효·전략 등급)은 불변.

## 5. 8전략 최종 그림 (정직본 5.5년)
- **pnl 양(+) = 3종**: minervini(+45%·DD17%, 유일 리스크 합리적)·rs(+149%·DD61%)·elder(+133%·DD72%).
- **pnl 음(−) = 5종**: daytrading(−9%)·deep_mr(−21%)·ma20(−30%)·envelope(−36%)·ma5(−41%·음 Sharpe).
- 컬링 결정은 「유지·모니터」(2026-06-27 사장님) 유지 — regime 게이트 실효·라이브 DD 관찰 후 재검.

## 6. 한계
- **역사 주식수**: implied2024는 근사(2024 주식수로 2021–23 역산; 증자/자사주 변동 잔존). 진짜
  역사값은 KRX/pykrx 차단·DART는 키 필요. DART 키 확보 시 `--shares-mode dart`로 정밀 재측정 가능.
- **deep_mr K분할 미모델링**·max_per_stock/top_n harness 통일(§1). 폭락국면 한정이라 표본 얇음.
- 2.5년(2024창)이 아닌 5.5년이라 강세편향은 보정됐으나, MaxDD 절대수준은 전략별 독립포폴 기준
  (실제 8전략 합성·regime 게이트와 다름).
