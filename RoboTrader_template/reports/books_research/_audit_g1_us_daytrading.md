# 책 전략 구현 충실도 감사 — G1 미국 데이트레이딩 3권

> 감사일: 2026-06-02
> 대상: aziz_day_trade, bellafiore_playbook, raschke_street_smarts
> 4축: 매수후보(유니버스) · 보유종목수(포트폴리오 모델) · 매수타이밍(진입) · 매도타이밍(청산)
> 판정: ✅일치 / ⚠️부분·근사 / ❌불일치·미모델

---

## 공통 방법론 (출처: aziz report.md §2·부록A, multiverse 정본 changelog 2026-06-02)

- **백테스터**: 단일룰(`results_single_*`) + `book_param_multiverse`. 신호봉 다음봉 시가 체결(no-lookahead), Long-only.
- **보유 모델**: **동시 보유 1종목, 종목별 균등** — 한정자본 K 포트폴리오 모델 아님. 3권 전부 K 미모델.
- **유니버스**: 베이스 `all`(503~581종목) / 정본 복원 `top_volume:50`(일별 거래대금 상위 50). Float·RVOL·촉매 데이터 없음.
- **청산 고정**: 베이스 sl2/tp3/mh60봉, 정본 sl3/tp5/mh120봉, EOD 강제청산. 룰별 R-multiple 청산 미반영.

---

## 1. aziz_day_trade (How to Day Trade for a Living)

8개 셋업 분봉 코드화. 정본 결론: bull_flag만 break-even(신호 극소), 나머지 전멸. CANDIDATE 부적격.

| 축 | 판정 | 근거 |
|---|---|---|
| 매수후보 | ❌ | 책 전제 = "Stocks in Play"(촉매 + RVOL≥2 + Float 소형 갭주, 시장 상위 0.1~1%). 백테스트는 `all`/`top_volume:50` 거래대금 근사. Float·RVOL·촉매 미반영 → report.md §7·한계점에서 직접 자인. top_volume50은 대형주풀로 책의 소형 갭주와 정반대일 수 있음. |
| 보유종목수 | ❌ | 동시 1종목·종목별 균등. 책은 분할진입·복수종목 병렬·R기반 사이징 권장(§한계점 자인). K 포트폴리오 미모델. |
| 매수타이밍 | ⚠️ | 진입 패턴(ABCD·bull_flag·ORB·VWAP반등·red-to-green·s/r·ma_trend)은 책 셋업과 형태상 일치하나 모두 1분봉. 책은 1·5분봉 혼합 + 테이프리딩 전제. top_reversal(sell)·all_AND은 long-only 구조상 0거래(미발동). 개장 09:30(ET)→09:00(KST) 환산만 적용, 변동성 구조 차이 미보정. |
| 매도타이밍 | ❌ | 고정 sl/tp/mh. 책은 셋업별 R-multiple(예: ORB 10R 목표) 권장. 청산 룰이 책 의도와 무관한 백테스터 기본값(§한계점 자인). |
| **종합** | **❌ 근사·미모델 다수** | 핵심 알파(SIP 종목선별·R청산)가 데이터 부재로 미반영. 진입 패턴만 형태 모사. 책 검증이라기보다 "패턴 단독 적용 시 한국 분봉서 무효" 확인. |

---

## 2. bellafiore_playbook (One Good Trade / The PlayBook)

10셋업 중 테이프 의존 4개 제외, 6룰 코드화. 정본 50서 fade_vwap만 2/3 부분강건(니치), 나머지 무너짐.

| 축 | 판정 | 근거 |
|---|---|---|
| 매수후보 | ❌ | 책 전제 = "Stocks In Play"(RVOL≥2·촉매·기관 오더플로우, 촉매 없으면 거래 회피). top_volume:50은 거래대금 근사일 뿐 촉매/RVOL 필터 아님. catalyst_gap 룰이 RVOL을 분봉 누적거래량 proxy로 흉내내나 진짜 촉매·장전갭 데이터 없음(RULES_RESEARCH §주의점 자인). |
| 보유종목수 | ❌ | 동시 1종목·종목별 균등. 책의 PlayBook은 셋업별 사이징·복수 In Play 종목 운용. K 미모델. |
| 매수타이밍 | ⚠️ | 2nd_day_play·bull_flag·range_trade·fade_vwap·opening_consolidation·catalyst_gap 형태 일치. 단 D-1 정보 부재로 second_day_play를 "분봉 첫 30봉=D-1 근사"로 대체(코드 docstring 자인) — 책의 일봉 D-1 ±5%/거래량2배 정의와 다름. fade_vwap만 책 수치(-2%이격·RSI(2)<10) 충실 코드화. 테이프리딩(Opening Drive·Pullback·Trade2Hold) 4셋업은 아예 제외. |
| 매도타이밍 | ❌ | 고정 sl/tp/mh. 책은 "근거 붕괴 시 즉시 손절" + Reasons2Sell(추세이탈·저항도달·비정상매도)·Measured Move(폴크기 목표). 구조적 청산 전혀 미반영. fade_vwap의 책 목표(VWAP 복귀)도 미반영. |
| **종합** | **❌ 부분근사** | fade_vwap 진입만 책 수치에 충실(니치 부분강건). 종목선별(In Play)·청산(Reasons2Sell)은 미모델. second_day_play는 D-1 근사로 의도 이탈. |

---

## 3. raschke_street_smarts (Street Smarts, Connors & Raschke)

10셋업. 분봉 5룰(rules.py) + 일봉 5룰(rules_daily.py) 코드화. 정본 50서 anti 36조합 전부 OVERFIT(mSharpe −1.27), index ⭐ 철회 권고.

| 축 | 판정 | 근거 |
|---|---|---|
| 매수후보 | ⚠️ | 책은 SIP 같은 종목선별 전제가 약함(선물·주가지수·개별주 범용 패턴북). top_volume:50/all 적용이 다른 두 책보다 덜 어긋남 — 책 자체가 "컨텍스트+가격행동" 중심이라 특정 유니버스 강제 없음. 다만 책 원본은 미국 선물·1995년 미세구조 기준. |
| 보유종목수 | ❌ | 동시 1종목·종목별 균등. K 포트폴리오 미모델(다른 2권과 동일). |
| 매수타이밍 | ⚠️ | 분봉룰: holy_grail(ADX>30+20EMA 첫풀백)은 Raschke 추천 셋업 충실. anti(스토캐스틱 훅)·gimmee_bar(BB하단)·momentum_pinball·nr4는 형태 일치하나 **원본이 일봉인 NR4·momentum_pinball을 분봉으로 변형**(docstring 자인 — "원서 일봉을 30분/첫1시간봉으로 변형"). 일봉룰(turtle_soup·80-20·adx_gapper·2period_roc)은 원본 일봉 정의에 충실. 단 숏 셋업은 공매도 제약으로 롱만 코드화(80-20·adx_gapper 한방향). |
| 매도타이밍 | ❌ | 고정 sl/tp/mh. 책은 "신규 스윙저점 손절 + 2~6봉 트레일링"(셋업별 상이). 트레일링·봉수 청산 미반영. |
| **종합** | **⚠️→❌ 진입 일부 충실, 청산·K 미모델** | holy_grail·일봉 셋업은 원본 정의 충실. 그러나 일봉룰을 분봉으로 변형한 셋업이 다수, 청산·포트폴리오 미모델. anti의 index ⭐는 단일기간 소표본 착시(정본서 OVERFIT) → 철회 권고. |

---

## 공통 패턴 (3권 관통)

세 책 모두 **진입 패턴은 형태상 모사했으나, 책의 알파 원천인 ①종목선별(Stocks in Play/RVOL/촉매·Float) ②셋업별 R-multiple·구조적(Reasons2Sell·트레일링) 청산 ③복수종목 K 포트폴리오 사이징이 데이터 부재 또는 백테스터 구조 한계로 전부 미모델**이며, 동시 1종목·종목별 균등·고정 sl/tp/mh로 근사 검증됨 → 결과(전멸/니치)는 책 의도의 충실한 반증이 아니라 "핵심 전제 제거 후 패턴 단독 적용"의 결과. 단 raschke 일봉 셋업·bellafiore fade_vwap·aziz bull_flag 등 일부 진입은 수치 충실도가 높다.
