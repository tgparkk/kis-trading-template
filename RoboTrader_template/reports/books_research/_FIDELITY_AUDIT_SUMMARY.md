# 책 전략 구현 충실도 감사 — 종합 (2026-06-02)

16개 기구현 책 전략을 4축(매수후보·보유종목수·매수타이밍·매도타이밍)으로 원문 대비 검증. 상세: `_audit_g{1..6}_*.md`.

## ★체계적 발견 2건 (전체 프로그램 차원)

### 발견 1 — 보유종목수(K)·한정자본 포트폴리오 거의 전부 미모델 ❌
`backtest/book_backtester.py:run_universe`가 `run_single`을 **종목별 독립 호출(각자 1천만 단일계좌) → 결과 균등평균**. 즉 보고된 PnL/Sharpe는 **"상위 종목들을 따로따로 단타한 평균"**이지 **한정자본·최대보유 K·자본경합·동시청산을 굴린 진짜 포트폴리오가 아님**.
- **K 미모델 (14/16)**: aziz, bellafiore, raschke, 유지윤, dino, 강창권(haru), greenblatt, oshaughnessy, lynch, hongyongchan, moonbyungro, oneil, weinstein, trading_legends.
- **K 모델됨 (2)**: **Elder**(`portfolio_sim_elder.py` K=5/10/20 풀스윕 ✅), **systrader79**(`allocation_backtester` 연속비중 ✅).
- **K 얕음 (1)**: Minervini(K=10 단일점만 ⚠️).

### 발견 2 — 매수후보(유니버스)·매도타이밍 다수 불일치 ⚠️/❌
- **급등주/단타 책**(aziz·bellafiore·dino·유지윤·trading_legends): 책은 In-Play/RVOL/촉매·세력급등주·동전주 모집단인데 **top_volume:50 대형주풀**로 대체 → 매수후보 ❌. 청산도 책의 R-multiple·구조적 손절 대신 고정 sl/tp ❌.
- **가치/퀀트 책**(greenblatt·oshaughnessy·lynch·hong·moon): 랭킹/스크리닝(팩터 상위)은 **충실 ✅**(top_volume 안 쓴 게 옳음). 그러나 **N종목 균등분산·정기 리밸런싱·1년 보유 청산이 전부 미구현** → per-stock sl/tp/mh 단타로 변질(avg_hold 3봉 등). 책의 본질(분산 포트폴리오·장기보유)과 정반대 ❌.

## 4축 매트릭스 (요약)
| 책 | 매수후보 | 보유K | 매수타이밍 | 매도타이밍 | 비고 |
|---|:--:|:--:|:--:|:--:|---|
| **elder** (채택) | ⚠️ | ✅ | ⚠️ | ✅ | 가장 충실. 단 report touch_band 1.01 stale(코드 1.02) |
| **minervini** (채택) | ⚠️ | ⚠️ | ❌→⚠️ | ⚠️ | 채택룰=dry-up 단독, VCP 피벗돌파 핵심 미구현 |
| **systrader79** | ⚠️ | ✅ | ✅ | ✅ | 연속비중 자산배분 충실(다자산→단일 축소만) |
| greenblatt | ⚠️ | ❌ | ⚠️ | ❌ | 랭킹 충실, 포트폴리오·1년보유 미구현 |
| oshaughnessy | ⚠️ | ❌ | ⚠️ | ❌ | 〃 |
| lynch | ⚠️ | ❌ | ⚠️ | ❌ | 〃 |
| hongyongchan | ✅ | ❌ | ⚠️ | ⚠️ | 스크리닝 충실, 20종목 분기리밸 미모델 |
| moonbyungro | ✅ | ❌ | ⚠️ | ⚠️ | 〃 |
| dino | ⚠️ | ❌ | ✅ | ⚠️ | 10~20종목 분산·회전 미모델 |
| 유지윤(daytrading_3methods) | ❌ | ⚠️ | ⚠️ | ⚠️ | 세력급등주→대형주풀, 분봉→일봉환원 |
| 강창권(haru) | ⚠️ | ⚠️ | ✅ | ✅ | 일봉 7룰 충실 |
| aziz | ❌ | ❌ | ⚠️ | ❌ | In-Play/RVOL/R-multiple 미모델 |
| bellafiore | ❌ | ❌ | ⚠️ | ❌ | fade_vwap 진입만 충실 |
| raschke | ⚠️ | ❌ | ⚠️ | ❌ | 진입 일부 충실, 청산·K 미모델. anti ⭐ 철회권고 |
| oneil | ⚠️ | ❌ | ⚠️ | ⚠️ | 라이브 미구현, N/S/I 누락 |
| weinstein | ⚠️ | ❌ | ⚠️ | ⚠️ | 주봉 정본 거래0 미평가, 채택값 일봉근사 |
| trading_legends | ⚠️ | ❌ | ✅ | ⚠️ | 분봉 8인 생략, 종가매매 일봉실패 |

## 결론별 신뢰도 — 어떤 판정이 견고/재검 필요한가
- **견고 (재검 불필요)**: Elder(채택, K풀스윕) · systrader79(충실). 분봉단타 전멸군(aziz·bellafiore·raschke·투매폭·trading_legends 분봉)도 K·유니버스 보정해도 결론 안 바뀔 가능성 높음(분봉단타 본질 약세, taesso 재검에서 확인됨).
- **★재검 가치 높음 (포트폴리오 미모델이 결론 왜곡 가능)**: **가치/퀀트 5책(greenblatt·oshaughnessy·lynch·hongyongchan·moonbyungro)** — 이들의 알파 원천은 "N종목 분산 + 정기 리밸런싱 + 장기보유"인데 per-stock 단타로 테스트됨. **`book_portfolio_multiverse.py`(신규, max-K·한정자본·리밸런싱)로 재검증해야 공정**. dino(10~20종목 분산 회전)도 해당.
- **데이터/구현 한계로 보류**: oneil(라이브 미구현·N/S/I 누락), weinstein(주봉 데이터 부족), Minervini(VCP 핵심 미구현 → 채택은 dry-up 보조신호 단독임을 인지).

## 권고 (우선순위)
1. **가치/퀀트 5책 + dino를 `book_portfolio_multiverse.py`로 재검증**(N종목 분산·정기 리밸런싱·max-K). 이게 충실도 갭의 최대 영향 영역.
2. **Minervini K=5/10/20 풀스윕**(Elder 수준으로) + VCP 피벗돌파 핵심 구현 재검토.
3. **문서 정정**: Elder report.md touch_band 1.01→1.02, raschke anti ⭐ 철회.
4. 분봉단타·미국 데이트레이딩 책: 핵심전제(RVOL/촉매/R-multiple) 데이터 부재로 충실 재현 난망 — 현 결론(전멸) 유지하되 "패턴 단독 적용 결과"임을 명시.

## 재검증 결과 (A·B, 2026-06-02) — 갭은 실재했으나 판정은 불변
상세: `_REtest_value_portfolio.md`·`_REtest_minervini_Ksweep.md`·`_REtest_minervini_VCP.md`. 신규 `scripts/book_rebalance_multiverse.py`(정기 리밸런싱·N종목·한정자본).

**A. 가치/퀀트 5책 + dino — 정기 리밸런싱 포트폴리오 모델 재검 (best freq/K → 전구간 Sharpe·CAGR | BULL/SIDE/BEAR Sharpe)**:
- greenblatt 분기/K30 → **0.37**/+5.8% | 1.49/0.69/**−1.88** (최대 개선)
- oshaughnessy 연/K20 → 0.26/+3.1% | 1.84/0.71/−2.10
- moonbyungro 분기/K20 → 0.25/+3.1% | 1.87/0.70/−2.17
- lynch 분기/K20 → 0.15/+0.7% | 0.32/1.45/−1.65 (MaxDD 최저10%)
- hongyongchan 분기/K10 → 0.10/−0.2% | 신호희소(53거래) 개선 안 됨
- dino K{5,10,20} → 0.09 (max_concurrent 5~6, **K 비결속**, 신호희소로 회전효과 미발현)
- **결론: 포트폴리오 모델링이 Sharpe를 per-stock 붕괴군 ~0.1 → 0.25~0.37로 끌어올림(분산효과 실재 = per-stock 테스트는 실제로 불공정했음). 그러나 채택바(0.6)엔 전부 미달 + 6책 전부 BEAR Sharpe 음수(−1.65~−2.38, 하락방어 전무, Elder의 BEAR +3.01%와 정반대). → 6책 전부 CANDIDATE 부적격 불변(이제 공정하게 확정). 분기>연 일관.**

**B1. Minervini K 풀스윕 — ★Elder와 정반대**: 채택청산(sl8/tp12/mh20)에서 **K=3만 전구간 양PnL·MaxDD억제로 생존**, K=10/20은 MaxDD≈100% 자본전소(Sharpe 비슷해 보이는 건 일변동성 함정, PnL/MaxDD가 진실). volume_dryup은 capacity 작아 **고집중 저-K(K=3)서만 유효**. BEAR 전 K 음수(진입게이트 별도 과제). **→ ★라이브 `max_positions=5`는 BULL서도 PnL음전 → K=3 하향 권고(승인 필요).**

**B2. Minervini VCP 핵심 재구현 — 비유효 확정**: 책 시그니처 VCP(수축레그+피벗돌파+RVOL) 제대로 구현(테스트10통과)했으나 top_volume:50 일봉서 **flat~음수(Sharpe~0.1), 엄격사양은 5년 1거래(2거래 붕괴 재발)**. 채택 dryup B(Sharpe1.41/+20%/153T)와 비교불가. **→ Minervini의 알파는 VCP가 아니라 dryup 신호. 현 채택(dryup 단독) 근거 재확인.**

## 핵심 시사
백테스트 결과(특히 PnL 절대값)는 **포트폴리오가 아닌 종목별 독립거래 평균**이라는 점을 모든 리포트가 명시해야 함. 추세추종(Elder)·자산배분(systrader79)만 진짜 포트폴리오로 검증됐고, 나머지는 "신호 품질"은 봤어도 "포트폴리오 성과"는 미검증.
