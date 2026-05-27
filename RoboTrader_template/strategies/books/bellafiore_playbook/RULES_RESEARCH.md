# Mike Bellafiore — One Good Trade / The PlayBook: 매매 셋업 조사

> 조사일: 2026-05-28
> 출처: 아래 "출처 URL 목록" 참조

## 요약

Mike Bellafiore는 뉴욕 prop trading firm SMB Capital의 공동창업자로, *One Good Trade*(2010)와 *The PlayBook*(2013) 두 권을 저술했다. 전자는 "한 번에 하나의 좋은 거래"라는 프로세스 중심 철학을 담고, 후자는 각 트레이더가 자신만의 "PlayBook"(최강 셋업 모음집)을 직접 구축하는 방법론을 제시한다. 핵심 차별점은 단순 차트 패턴보다 **다섯 가지 의사결정 레이어(Big Picture · Intraday Fundamentals · Technicals · Tape Reading · Intuition)를 복합 적용**하고, 반드시 "Stocks In Play"(기관 오더플로우가 유입되는 촉매 보유 종목)만 거래한다는 점이다. Bellafiore는 모든 트레이더에게 범용 신호를 제공하는 대신, 자신의 강점에 맞는 셋업 4~5개를 발굴·반복·정밀화하도록 권고한다. 손절은 "근거가 무너지면 즉시"를 원칙으로 하며, 익절 기준은 *Reasons2Sell* 프레임워크(추세 이탈·저항 도달·비정상 매도 포착 등)로 구조화한다.

---

## 다섯 가지 의사결정 레이어 (모든 셋업에 공통 적용)

| 레이어 | 내용 |
|---|---|
| **Big Picture** | S&P500·KOSPI 지수 방향, 80% 이상 종목이 지수를 따르므로 지수 역행 시 포지션 규모 축소 |
| **Intraday Fundamentals** | 신선한 촉매(실적·뉴스·공시) 보유 여부 — Stocks In Play 여부 판별의 핵심 |
| **Technicals** | 주요 지지·저항·VWAP·이동평균 위치, 패턴(flag·consolidation 등) |
| **Tape Reading** | Level 2 호가창 / 체결 테이프 — 매수·매도세 우위, 비정상 호가 잔량, 체결속도 모니터링 |
| **Intuition** | 반복 경험으로 축적된 체감 — 초보자는 상위 4개 레이어만으로 충분 |

---

## Stocks In Play 선별 기준 (모든 셋업 전제조건)

- **RVOL(Relative Volume) ≥ 2**: In Play 최소 기준. RVOL ≥ 3이면 포지션 확대 신호. RVOL ≥ 5이면 강력 In Play
- **장전 갭 ±3% + 장전 거래량 증가**: "Super Stocks In Play" 판별 지름길
- **전일 대비 일중 변동폭 × 2 이상** + **거래량 평소 2배 이상**: 2nd Day Play 후보 필수 조건
- 장전 8:00~9:30 추세·패턴 분석으로 개장 방향 편향(bias) 사전 수립

---

## 셋업 목록

### 셋업 1: 오프닝 드라이브 (Opening Drive)

**책 챕터/페이지**: One Good Trade 및 The PlayBook 반복 언급; smbtraining.com 다수 포스트

**진입 조건** (수치로):
- 조건 1: 개장(9:30) 즉시 또는 첫 1~5분 내 강한 일방향 모멘텀 발생
- 조건 2: Stocks In Play(촉매 + RVOL ≥ 2) 종목에서만 적용
- 조건 3: 5분봉 기준 VWAP 위 유지 + 브레이크아웃 레벨 위에서 이상 거래량 지속
- 조건 4: 장전 고점 돌파 후 거래량 동반 확인 (보수적 진입은 레벨 위 유지 확인 후)
- 조건 5: 드라이브가 보통 5~6분 지연 없이 "즉시" 시작되어야 함 (지연 발생 시 셋업 약화)

**손절 룰**: 매수 후 최초 약세 신호 출현 즉시 청산 ("With any weakness we exit"). 고정 % 손절 아님 — 모멘텀 소멸이 트리거

**익절 룰**: 모멘텀 지속 시 보유, 거래량 감소·역전 봉 출현 시 분할 청산. 개장 후 30분은 가격 발견 구간이므로 전체 추세 기대는 제한적

**최대 보유 시간**: 첫 15~30분 (30분 초과 시 가격발견 구간 종료로 역전 위험 증가)

**사용 시간대**: 개장 직후 9:30~9:45 (핵심 윈도우)

**사용 데이터**: 1분봉·5분봉, VWAP, 장전 고/저점 레벨, Level 2 (선택)

**책의 핵심 가정**: 기관 오더플로우가 개장 즉시 방향을 결정하며, In Play 종목에서 이 힘은 알고리즘보다 강하다. 방향이 확인되면 빠른 수익 실현이 가능하다.

**검증되지 않은 점**: 진입 후 정확한 손절 틱 수 / 목표 R배수는 공개 자료에서 확인되지 않음. Tape Reading 의존도가 높아 순수 분봉 코드화 시 신호 품질 저하 가능

---

### 셋업 2: 2일차 플레이 (Second Day Play)

**책 챕터/페이지**: The PlayBook 핵심 챕터; SlideShare 웨비나 "edu-2nd-day-play-presentation"에서 상세화

**진입 조건** (수치로):
- 조건 1: D-1에 종가 기준 ±5% 이상 이동하며 당일 극단(고가 또는 저가)에 근접 마감
- 조건 2: D-1 거래량 평소 대비 2배 이상 (예: 평소 200만 주 → D-1 3,000만 주 이상)
- 조건 3: D-1에 형성된 주요 가격 레벨(고가·저가·최대 거래량 구간) 사전 식별
- 조건 4: D+1 또는 그 이후 통합(consolidation) 후 해당 레벨 재접근 시 진입
- 조건 5: 레벨 위(long) 또는 아래(short) 유지 확인 후 진입 — "보수적 접근"

**손절 룰**: 진입 레벨 반대편으로 복귀 시 청산. 거래량 스파이크(finishing print) 이후 추가 하락 소진 신호 관찰

**익절 룰**: 거래량 스파이크 출현 시 부분 청산, 핵심 지지·저항 레벨 접근 시 추가 청산. Reasons2Sell 프레임워크 적용

**최대 보유 시간**: 미정 (레벨 유지 기간에 따라 당일 또는 수일 연장 가능 — Trade2Hold 로 전환 가능)

**사용 시간대**: 개장 직후 오프닝 드라이브 시점 또는 주요 레벨 재접근 시

**사용 데이터**: 5분봉, D-1 주요 레벨, 일봉, RVOL

**책의 핵심 가정**: D-1 촉매로 유입된 기관 오더플로우가 완전히 소화되지 않아 D+1에도 추세가 지속될 수 있다. 가장 명확한 지지·저항을 제공하므로 "신규 트레이더에게 가장 쉬운 셋업"으로 권장

**검증되지 않은 점**: D-1 "5% + 극단 마감" 기준은 SlideShare 웨비나 기반이며 책 본문 페이지 번호 미확인. Consolidation 기간 정의(일 수, 변동폭)가 수치화되지 않음

---

### 셋업 3: 불리시 플래그 / 불&베어 플래그 (Bull Flag / Bear Flag)

**책 챕터/페이지**: The PlayBook 반복 언급; smbtraining.com "bull-flag-pattern" 상세 포스트

**진입 조건** (수치로):
- 조건 1: Stocks In Play 종목에서만 적용 (In Play 아닌 종목의 플래그는 승률 현저히 낮음)
- 조건 2: 강한 초기 상승(폴: pole) — 예: 1~2% 이상 단봉 급등, 이상 거래량 동반
- 조건 3: 플래그 구간: 거래량 감소 + 좁은 가격 범위 횡보 (예: QCOM 사례 $93.60~$94.00)
- 조건 4: 플래그 고점($94.00) 돌파 + 돌파 봉 거래량 급증으로 진입
- 조건 5: VWAP 위 유지 + 섹터 동반 강세 확인 (선택적)

**손절 룰**: 플래그 저점 하단 배치 (QCOM 예: 약 $93.60~$93.70 / 리스크 약 30센트)

**익절 룰**: Measured Move = 폴 크기(예: $1) + 돌파 레벨(예: $94) = 목표 $95. R:R 최소 2:1 이상 (QCOM 예시: 30센트 손절 / $1 목표 = 3:1)

**최대 보유 시간**: 목표가 도달 또는 구조 붕괴 시까지 (명시적 시간 기준 없음)

**사용 시간대**: 장 전반 또는 장중 — 개장 이후 첫 1~2시간 선호

**사용 데이터**: 5분봉 (패턴 식별), 1분봉 (진입 타이밍), RVOL, VWAP

**책의 핵심 가정**: 폴 단계의 기관 매수세가 소화 구간(플래그) 이후 재점화된다. In Play 종목에서는 기관 오더플로우가 일반 패턴보다 신뢰도를 크게 높인다.

**검증되지 않은 점**: "플래그 구간 최대 봉 수" 또는 "최대 되돌림 비율" 기준이 공개 자료에 명시되지 않음. Tape Reading 없이 순수 패턴만으로 적용 시 승률 검증 필요

---

### 셋업 4: 풀백 트레이드 (Pullback Trade)

**책 챕터/페이지**: The PlayBook 다수 챕터; "Traders Ask: Pullback or Reversal?" 블로그 포스트

**진입 조건** (수치로):
- 조건 1: 상승 추세 중 얕은 되돌림(shallow pullback) — Adam Grimes 기준 30~60% 되돌림 권장, 이보다 얕으면 2레그 풀백으로 발전 가능
- 조건 2: 종목이 브레이크아웃한 레벨로 되돌아오는 풀백 ("pullbacks to areas where the stock broke out from")
- 조건 3: 추세선 또는 주요 레벨 접근 시 테이프에서 매수세 강화 확인
- 조건 4: 지수(Big Picture)가 동시에 강화되는 시점 선호 — 지수 급락 중 풀백 진입은 회피
- 조건 5: VWAP 위 종목에서의 풀백(long) 또는 VWAP 아래 종목에서의 풀백(short)

**손절 룰**: 중요 레벨(추세선·VWAP·브레이크아웃 구간) 이탈 시 청산. 기계적 % 손절보다 "구조 이탈" 기준 선호

**익절 룰**: 다음 저항 레벨 또는 이전 고점 도달 시 부분 청산. Reasons2Sell 적용 (추세 이탈, 비정상 매도 출현 등)

**최대 보유 시간**: Trade2Hold 전환 시 수 시간 ~ 당일 내. Move2Move 기준 시 수십 분

**사용 시간대**: 장중 전 시간대 (개장 초반 오프닝 드라이브 이후 첫 1시간 내외 선호)

**사용 데이터**: 5분봉·3분봉, VWAP, 추세선, Level 2 (테이프 강화 확인)

**책의 핵심 가정**: 모멘텀이 살아 있는 추세에서 기관은 풀백을 매수 기회로 활용한다. 풀백 깊이가 작을수록 매수세가 강하다는 신호다.

**검증되지 않은 점**: "얕은 풀백" vs "되돌림" 경계 수치는 Bellafiore가 아닌 Adam Grimes 인용. 30~60% 피보나치 되돌림은 SMB 공식 기준이 아닐 수 있음. 풀백과 반전의 경계는 "절대적 기계 규칙 없음"이라고 Bellafiore 직접 명시

---

### 셋업 5: 레인지 트레이드 (Range Trade)

**책 챕터/페이지**: The PlayBook; smbtraining.com "Playing the Range" 포스트

**진입 조건** (수치로):
- 조건 1: 명확히 정의된 지지·저항 구간(range) 식별 — 예: IBM $116~$120, JPM $41~$43
- 조건 2: 레인지 하단(지지) 접근 시 매수 / 상단(저항) 접근 시 매도(short)
- 조건 3: 첫 15분이 당일 레인지 전체를 형성하는 날 오후 세션에서 선호 (오전 레인지 재확인)
- 조건 4: 섹터 동종 종목들도 동일 레인지 패턴 확인 (선택적)
- 조건 5: 테이프에서 레벨 접근 시 매도세(short 진입) 또는 매수세(long 진입) 약화 확인

**손절 룰**: 레인지 이탈 시 즉시 청산 ("When the range breaks the range play is now void"). 레인지 외 고정 버퍼는 제시되지 않음

**익절 룰**: 레인지 반대편 도달 시 청산. 부분 청산 후 잔여 보유 가능

**최대 보유 시간**: 레인지 지속 기간 내 (오후 세션 기준 수 시간, 장 마감까지도 가능)

**사용 시간대**: 주로 오후 세션(13:00~15:30 ET) — 오전 레인지 형성 확인 후 적용. 오전 장중도 가능

**사용 데이터**: 5분봉 또는 15분봉, 지지·저항 레벨, 섹터 비교

**책의 핵심 가정**: 레인지는 명확한 진입·청산 레벨을 제공하므로 "저위험·명확 정의 셋업"이다. 레인지 상단 가짜 돌파(false breakout) 후 레인지 재진입이 오후 세션의 가장 선호되는 패턴이다.

**검증되지 않은 점**: 최소 레인지 폭 기준(예: 몇 % 이상) 미공개. 레인지 유효성 판단을 위한 최소 터치 횟수(예: 2회 이상) 기준 미확인

---

### 셋업 6: 페이드 트레이드 / VWAP 평균회귀 (Fade Trade / VWAP Reversion)

**책 챕터/페이지**: The PlayBook (Fade Trade 항목); smbtraining.com "Finding the Setups Best for Your Trading Personality" 목록에 명시

**진입 조건** (수치로):
- 조건 1: Stocks In Play 종목이 VWAP에서 **+2% 이상** (short) 또는 **-2% 이하** (long) 이격
- 조건 2: RSI(2) > 90 (short) 또는 RSI(2) < 10 (long) — SMB Capital 관련 자료에서 확인된 수치
- 조건 3: 5분봉 기준 긴 위꼬리(shooting star) 또는 아래꼬리 봉 출현으로 모멘텀 소진 확인
- 조건 4: 이격 국면 거래량 높음 → 소진 봉 구간 거래량 감소 (러버밴드 수렴 신호)
- 조건 5: RVOL > 2배 (In Play 종목에서만 유효)

**손절 룰**: 소진 봉 고점(short) 또는 저점(long) 위에 배치. 또는 고정 0.5% 손절 (공개 자료 기준)

**익절 룰**: 1차 목표: VWAP 복귀. 2차 목표: 장전 고/저점 또는 주요 지지 레벨. VWAP 도달 시 트레일링 스톱 전환

**최대 보유 시간**: 수분~30분 (단기 스캘프 성격)

**사용 시간대**: 장중 전 시간대 — 개장 직후 30분은 변동성 과대로 회피 권장

**사용 데이터**: 1분봉·5분봉, VWAP, RSI(2 또는 5), RVOL

**책의 핵심 가정**: 주가는 VWAP에 묶인 고무줄처럼 과도한 이격 후 평균으로 회귀한다. In Play 종목에서 이격이 클수록 기관 역매매 유입 가능성이 높다.

**검증되지 않은 점**: "+2% 이격 / RSI(2) > 90" 수치는 forex.in.rs의 "SMB Capital inspired" 자료에서 인용된 것으로, Bellafiore 저서 원문에 동일 수치가 명기되었는지 확인되지 않음. 미국 대형주 기준으로 한국 시장 직접 적용 시 임계값 재보정 필요

---

### 셋업 7: 2일차 오프닝 통합 브레이크아웃 (Opening Consolidation Breakout)

**책 챕터/페이지**: The PlayBook (Consolidation 항목); ATAS 블로그 7-step Playbook 요약에서 "Opening Consolidation"으로 명시

**진입 조건** (수치로):
- 조건 1: 갭업 또는 갭다운 종목이 개장 후 거래량 감소하며 갭을 채우지 않고 통합(consolidation) 형성
- 조건 2: 통합 구간 상단(long) 또는 하단(short) 브레이크아웃 발생
- 조건 3: 브레이크아웃 봉 거래량 증가로 확인
- 조건 4: VWAP 위(long) 또는 아래(short) 유지
- 조건 5: 지수(Big Picture) 방향 일치

**손절 룰**: 통합 구간 하단(long) 또는 상단(short) 이탈 시 청산

**익절 룰**: Measured Move(통합 구간 폭 × 1) 또는 다음 주요 저항·지지 레벨 도달 시 청산

**최대 보유 시간**: 브레이크아웃 후 모멘텀 지속 시 최대 당일 내. 통합 기간은 통상 개장 후 30분~1시간

**사용 시간대**: 개장 직후(9:30~10:30 ET)

**사용 데이터**: 5분봉, VWAP, 일봉(갭 크기 확인), RVOL

**책의 핵심 가정**: 갭이 채워지지 않고 통합을 거치면 매수·매도세 모두 "방향 합의"에 도달한 것이며, 브레이크아웃 시 기관 오더플로우가 방향을 강화한다.

**검증되지 않은 점**: 통합 구간 최소 지속 시간(분 수) 및 최소 봉 수 기준 미공개. 갭 최소 크기(% 기준) 미명시

---

### 셋업 8: 인트라데이 상대강도 시장 플레이 (Intraday Relative Strength / Market Play)

**책 챕터/페이지**: The PlayBook (Relative Strength, Market Trades 항목); smbtraining.com "Intraday Relative Strength" 포스트

**진입 조건** (수치로):
- 조건 1: 지수(KOSPI) 상승 중 섹터 내 동종 주도 종목 식별
- 조건 2: 지수 대비 상대강도 확인 — 지수가 신고가를 기록할 때 대상 종목도 동반 신고가 (강한 RS 신호)
- 조건 3: VWAP 위에서 장중 풀백이 얕고 빠르게 반등 (시장 대비 상대강도 유지)
- 조건 4: 장전 갭업 후 VWAP 위 유지 & 종가 고점 근처 형성
- 조건 5: 소형주(러셀 2000 또는 코스닥 중소형) 동반 신고가 → 시장 전체 강도 확인. 소형주 미동반 시 강도 약화 경고

**손절 룰**: VWAP 이탈 또는 지수 급락 시 청산. 상대강도가 지수에 수렴(리드 소실) 시 청산

**익절 룰**: 지수 또는 섹터 상승 모멘텀 소진 시 부분 청산. Reasons2Sell 적용

**최대 보유 시간**: 지수 상승 추세 지속 시 Trade2Hold 전환. 최소 수십 분 이상

**사용 시간대**: 장 전반 — 특히 지수 추세가 명확한 날

**사용 데이터**: 5분봉, VWAP, 지수(KOSPI/KOSDAQ) 동기화, 섹터 종목 비교

**책의 핵심 가정**: 시장 상승 시 가장 강한 종목이 가장 큰 이익을 낸다. 소형주와 대형주의 동반 상승은 기관 참여 확인 신호이며, 리드가 끊어지는 순간이 추세 전환의 조기 경고다.

**검증되지 않은 점**: "상대강도" 정량화 기준(예: 지수 대비 몇 % 아웃퍼폼) 미공개. 한국 시장에서는 KOSPI vs KOSDAQ 리더십 관계로 재해석 필요

---

### 셋업 9: Trade2Hold (추세 지속 스윙)

**책 챕터/페이지**: The PlayBook; smbtraining.com "Trade2Hold-Important-Intraday-Level" 포스트

**진입 조건** (수치로):
- 조건 1: 강한 촉매 보유 In Play 종목에서 주요 인트라데이 레벨 돌파
- 조건 2: 레벨에서 매도세가 지속적으로 흡수됨을 테이프에서 확인 ("Sellers tested this level and the buyer would not drop")
- 조건 3: 종목이 VWAP 위(long) 및 오프닝 레인지 위 유지
- 조건 4: 5분봉에서 인트라데이 추세선 유지 확인

**손절 룰**: 5분봉 인트라데이 추세선 이탈 시 청산 (예: 83.75 레벨 돌파 시 short 청산). 기계적 틱 손절 아님 — 구조적 이탈 기준

**익절 룰**: "Reason2Sell 발생까지 보유" — 추세 이탈·저항 도달·비정상 매도 출현·뉴스 변화 중 하나 발생 시. Move2Move(단기 회전)가 아닌 점진적 익절

**최대 보유 시간**: 당일 내 수 시간 (인트라데이 스윙). 드물게 오버나이트 가능

**사용 시간대**: 장중 전 시간대 — 오프닝 드라이브 이후 추세 확립 후

**사용 데이터**: 5분봉, VWAP, 인트라데이 추세선, Level 2 (레벨 흡수 확인)

**책의 핵심 가정**: 강한 촉매와 기관 오더플로우가 있는 날에는 단순 스캘프보다 큰 인트라데이 이동이 발생한다. 추세가 유효한 동안은 보유가 청산보다 유리하다.

**검증되지 않은 점**: Move2Move와 Trade2Hold 전환 결정 기준이 재량적(discretionary)이며 수치화 미제공. Tape Reading 없이 구현 시 신호 품질 저하

---

### 셋업 10: 촉매 갭업 트레이드 (Catalyst / Earnings Gap Trade)

**책 챕터/페이지**: One Good Trade (Stocks In Play 챕터); The PlayBook 전반; RVOL 포스트

**진입 조건** (수치로):
- 조건 1: 실적·뉴스 발표 후 장전 갭 ±3% 이상 + 장전 RVOL 증가
- 조건 2: 개장 시 RVOL ≥ 3 확인 (강한 In Play 신호)
- 조건 3: 개장 후 갭이 채워지지 않고 VWAP 위(갭업) 유지
- 조건 4: 9EMA 또는 21EMA 위 유지 + VWAP 위 체류 시간이 길수록 강도 높음
- 조건 5: 장전 고점(premarket high) 돌파 후 거래량 동반 진입 (가장 보수적이고 신뢰도 높은 진입)

**손절 룰**: 장전 고점 돌파 실패 또는 VWAP 이탈 시 청산. 갭 채움(gap fill) 개시 시 즉시 청산

**익절 룰**: ATR × 1~2 목표, 또는 다음 주요 저항(이전 고점·정수 레벨) 도달 시 부분 청산

**최대 보유 시간**: 첫 1~2시간 (갭 모멘텀 지속 구간). 촉매 강도에 따라 Trade2Hold 전환 가능

**사용 시간대**: 개장 직후 9:30~11:00 ET

**사용 데이터**: 5분봉, VWAP, 9/21 EMA, 장전 고/저점 레벨, RVOL

**책의 핵심 가정**: 실적·뉴스 촉매는 "진짜 오더플로우"를 만들어 알고리즘도 추세에 합류하게 한다. RVOL ≥ 3은 기관 참여가 충분히 활성화되었음을 의미한다.

**검증되지 않은 점**: "9EMA / 21EMA" 기준은 SMB Capital 관련 자료에서 나타나지만 Bellafiore 저서 원문 인용 확인 불가. 갭 최소 크기 ±3%는 "장전 슈퍼 In Play" 판별 기준이며 모든 촉매 트레이드에 엄격히 적용되는지 미확인

---

## 한국 시장 적용 시 주의점

### Level 2 호가창 / Tape Reading — 한국 데이터 가용성

- Bellafiore 셋업의 핵심 알파는 **Level 2 호가창 + 실시간 체결 테이프**에서 나온다. 한국 KIS API는 실시간 호가(10단계)를 제공하지만, 미국의 "bid absorption"·"tape speed" 수준의 정밀 분석은 어렵다.
- **코드화 권장 셋업**: 2일차 플레이, 불리시 플래그, 레인지 트레이드, Opening Consolidation Breakout — 분봉 + VWAP + RVOL만으로 조건 정의 가능
- **코드화 어려운 셋업**: Opening Drive (테이프 의존 강함), Trade2Hold (재량적 추세선 판단), Fade Trade (소진 봉 판단 주관적)

### 종목 선택 "In Play" — Andrew Aziz와의 비교

| 항목 | Bellafiore (SMB Capital) | Andrew Aziz (Bear Bull Traders) |
|---|---|---|
| 핵심 판별 기준 | RVOL + 촉매(뉴스·실적) + 기관 오더플로우 | Float + 갭% + 거래량 급증 |
| RVOL 임계값 | ≥ 2 (In Play), ≥ 3 (고신뢰), ≥ 5 (강력) | 명시적 임계값 대신 "상위 스캐너" 필터 |
| 촉매 강조 | 매우 강조 — 촉매 없으면 거래 자체를 회피 | 강조하나 소형주 기술적 갭도 유효 |
| 종목 특성 | 대형·중형주(뉴욕 prop firm 특성) | 소형주·저가주 갭 플레이 병행 |
| 공통점 | 둘 다 "당일 가장 움직이는 종목 집중" 원칙 동일 | |

- 한국 시장 적용 시: **일일 상한가 종목 + 공시/실적 발표 종목**이 "In Play" 후보. RVOL은 `현재까지 누적 거래량 / (평균일거래량 × 경과시간비율)` 로 계산

### 거래 시간대 변환 (한국 시장)

| Bellafiore 기준 (ET) | 한국 시장 환산 (KST) | 비고 |
|---|---|---|
| 9:30~9:45 개장 드라이브 | 09:00~09:15 (개장 직후) | 한국 개장은 09:00 |
| 9:30~10:30 오프닝 셋업 전반 | 09:00~10:00 | 첫 1시간 |
| 오후 레인지 세션 | 13:30~15:00 | 점심 이후 ~ 마감 30분 전 |
| 장전 8:00~9:30 분석 | 08:00~09:00 (장전 호가·공시 확인) | |

---

## 출처 URL 목록

1. https://www.smbtraining.com/blog/the-playbook-by-mike-bellafiore — SMB Capital 공식 PlayBook 소개 페이지
2. https://www.smbtraining.com/blog/tag/opening-drive — Opening Drive 관련 SMB 블로그 아카이브
3. https://www.smbtraining.com/blog/the-opening-drive-play-ua — Opening Drive Play (UA 종목) 상세 포스트
4. https://www.smbtraining.com/blog/players-ask-pullback-or-reversal — Pullback vs Reversal 구분 (Bellafiore 직접 답변)
5. https://www.smbtraining.com/blog/playing-the-range — Range Trade 상세 포스트
6. https://www.smbtraining.com/blog/do-not-miss-2nd-day-plays — 2nd Day Play 개요 포스트
7. https://www.smbtraining.com/blog/trade2hold-important-intraday-level-breaks-uptrend — Trade2Hold 포스트
8. https://www.smbtraining.com/blog/relative-volume-rvol-defined-and-how-we-use-it — RVOL 정의 및 임계값 (RVOL < 1 / > 2 / > 3 / > 5 기준 출처)
9. https://www.smbtraining.com/blog/the-pre-market-tell — 장전 분석 방법론
10. https://www.smbtraining.com/blog/bull-flag-pattern-how-to-effectively-use-this-classic-pattern-to-profit — Bull Flag 상세 (손절·목표가 수치 포함)
11. https://www.smbtraining.com/blog/intraday-relative-strength-a-clue-to-market-sentiment-and-direction — Intraday Relative Strength 포스트
12. https://www.slideshare.net/smbcapital/edu-2nd-day-play-presentation — 2nd Day Play 웨비나 슬라이드 (SlideShare)
13. https://atas.net/trading-preparation/organisation-of-a-trading-process/playbook/ — PlayBook 7단계 요약 + 셋업 목록 (Second Day Play, Trend Trade, Bullish Flag, Fade, Trade2Hold, Pullback, Opening Consolidation)
14. https://www.forex.in.rs/smb-capital-strategy1/ — "SMB Capital Inspired" Overextended Pullback to VWAP (Fade Trade 수치 기준 +2% / RSI(2)>90 출처)
15. https://pdfcoffee.com/download/smbu-how-to-find-and-trade-stocks-in-play-pdf-pdf-free.html — SMBU "How to Find and Trade Stocks in Play" 원문 자료
16. https://www.smbtraining.com/blog/finding-the-setups-best-for-your-trading-personality — SMB 공식 셋업 20종 목록 (Fade, Opening Drive, Pullback 등)
17. https://cdn.bookey.app/files/pdf/book/en/the-playbook-by-mike-bellafiore.pdf — The PlayBook Bookey 요약 PDF (Support Play, 2nd Day, Bounce/Fade, Bull-Bear Flag 등 셋업 목록 확인)
18. https://www.goodreads.com/book/show/13661656-the-playbook — The PlayBook Goodreads (출판 정보 확인)
