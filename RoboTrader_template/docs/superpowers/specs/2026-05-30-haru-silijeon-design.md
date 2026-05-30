# 강창권 『하루 만에 수익 내는 실전 주식투자』 — 백테스트 설계서 (Book 14, 한국 저자 3호)

> 조사: WebSearch 기반(아래 §A 참고). **책 실물 미보유 → 공개 자료/서평/서점 소개/저자 후속작 목차 재구성.**
> 작성: 2026-05-30 · 한국 시장 특화 **인트라데이 단타(데이트레이딩)** — 분봉 셋업.
> 분봉 책 인프라(아지즈 Book 1 / Bellafiore Book 2 / Raschke Book 3) 재사용. book_id=`kang_haru_silijeon`.
> **결정사항(사장님)**: §9 "사장님 결정 필요" 미해결 — 코드화 전 결재 요망(특히 종목풀 선별 기준·전일종가 백필·셋업 우선순위).

---

## A. 책 조사 요약 (Book 14)

### A.1 저자·대표작 확정
- **저자**: **강창권**(姜昌權). 1999년 주식 입문, 전업투자자. **2002년 한국투자증권 실전투자대회 우승**을 시작으로 **총 6회 실전투자대회 수상**. 25년차 트레이더(2025 기준).
- **대표작 확정**: **『하루 만에 수익 내는 실전 주식투자』**(길벗, ISBN 미확정 — 종이책/전자책 동시). 저자의 **15년 실전 매매 노하우**를 실제 매매기록과 함께 공개.
- **저자 후속작(방법론 보강 출처)**: 『수익 내는 주식 매매 타이밍』(길벗), **『주식투자 단기 트레이딩의 정석』(2024~2025, "25년 투자 고수가 전하는 매일 수익 내는 단타 매매의 기술")** — 후속작 목차가 본작 방법론을 더 정량적으로 드러내므로 셋업 재구성의 핵심 보조 출처로 사용.

### A.2 핵심 방법론 (정량 룰로 환원)
서점 소개·후속작 목차·서평을 종합하면 강창권의 골격은 **"당일 강한 거래대금 + 재료가 들어온 종목을, 차트의 핵심(거래량·호가)만 보고, 눌림목/돌파/종가에서 짧게 잡아 당일 또는 1~2일 내 청산"**이다.

**판별 결론**: 이 책은 **(a) 분봉 기반 인트라데이 단타**가 핵심이다(일부 셋업은 1~2일 스윙으로 넘어가는 종가 베팅 포함). 펀더멘털 선별·일봉 장기 스윙이 아니다.

공개 자료에서 반복 확인되는 **시그니처 셋업**(정량화 후보):

1. **거래대금·재료 종목 선별("아직 오르지 않은 급등주")**: "최근 이슈·강한 재료가 있는 종목은 당일 강한 거래대금이 들어오며 장대 양봉을 만든다." → **당일/직전 거래대금 상위** + **장초반 강세**로 종목 압축. (정량화: 거래대금 순위 + 시초가 갭/등락률.)
2. **눌림목 매수(상승추세의 작은 눌림)**: "모든 주식은 상승하다 한번 내려갔다 올라간다(눌림목)." → 장중 단기 급등 후 **얕은 되돌림에서 양봉 반등 시 진입**. 후속작에는 **"급등 이후 20일선 눌림목"**, **"점심시간(11:30~13:00) 눌림목 대응"**이 명시됨.
3. **돌파 매매(신고가/전일고가 돌파)**: "전일 고가를 돌파한 종목 공략, 09:40 부근 고점 매도." → **장초반 전일고가/당일 신고가 돌파 시 진입 → 09:40 전후 빠른 익절**.
4. **정배열 전환·장기선 돌파(분봉 240/480선)**: 후속작에 **"정배열 전환 후 240분·480분 이동평균선 돌파 매매"**, **"240일·480일선 장기추세 파악"** 명시. (분봉 240/480 MA = 대략 분봉 4시간/8시간선, 며칠 추세선.)
5. **종가 베팅(종가매매)**: "종가 베팅의 기술" — **장 막판(14:30~15:20) 강세 지속 종목을 종가 근처 매수해 익일 갭상승 노림** → 익일 시초/장초 청산(1일 스윙).
6. **수급 추종(기관·외국인)**: "기관·외국인 수급 따라가기" — 외인/기관 순매수 종목 가중. (정량화: **분봉 데이터만으로는 직접 불가**, 수급 데이터 부재 → §7 백필/제외.)

**손절 철학**: "지체 없이 손절." 본인이 정한 손절라인 이탈 시 즉시 손절. 목표 수익은 **1~5%(초보 1~2%)** 단타형 — 짧은 익절·짧은 손절.

**정량화 가능 부분**: 셋업 1~5는 분봉 OHLCV + 거래대금(amount)으로 환원 가능. 셋업 6(수급)은 데이터 부재로 제외 또는 백필 종속.
**정성적 부분**: "재료/이슈 판단", "호가창 읽기"는 정성적·데이터 부재 → 코드화 불가(거래대금/등락률로 근사).

### A.3 다른 분봉 책(아지즈/Bellafiore/Raschke)과의 차별점 & 백테스트 가치
| 책 | 핵심 축 | 강창권과의 차이 |
|----|---------|------------------|
| 아지즈(Book 1) | 미국식 ABCD/Bull Flag/ORB/VWAP, "Stocks in Play"=촉매+RVOL | 강창권도 **거래대금 집중 종목 + 돌파/눌림목**으로 골격 유사. 단 **한국 시장에서 직접 검증·체화**된 룰(09:40 익절, 점심 눌림목, 종가베팅)이라 한국 미세구조 반영. |
| Bellafiore(Book 2) | RVOL 정량 + fade_vwap(평균회귀) | Bellafiore fade_vwap이 한국 분봉 베스트(+1.74%, Sharpe 0.37). 강창권 눌림목 = **추세 내 얕은 되돌림 매수**로 fade_vwap과 사촌 관계 → A/B 가치. |
| Raschke(Book 3) | Anti(임펄스 후 훅), 변동성 극단 | Raschke anti가 절대 PnL 최강(+10.24%)이나 Sharpe -2.27. 강창권 돌파/눌림목과 진입 타이밍 비교 가치. |

**핵심 차별점 = "한국 토착 분봉 단타"**: 아지즈/Bellafiore/Raschke는 미국 저자(미국 미세구조 가정). 강창권은 **한국 KRX 분봉에서 직접 6회 수상한 실전 룰**이다. 미국식 인트라데이가 한국에서 대부분 부진(아지즈 -4~-30%)했던 것과 달리, **한국 토착 룰이 한국 분봉에서 우위를 보이는지**가 본 백테스트의 1급 질문이다.

**백테스트 가치**: **높음**. (a) 한국 저자 분봉 룰 vs 미국 저자 분봉 룰 직접 A/B(동일 universe·청산·기간). (b) "거래대금 상위 + 돌파/눌림목" 조합이 아지즈 abcd/orb 복원 실험(top_volume:50에서만 양전환)을 **명시적 종목선별로 재현·개선**하는지. (c) 09:40 익절·점심 눌림목·종가베팅 같은 **시각(time-of-day) 룰**이 한국 분봉에서 엣지인지 — 기존 3책은 시각 룰이 거의 없었음(ORB만 장초반).

---

## 0. 설계 원칙

1. **분봉 인트라데이 셋업 N종 + 한국 토착 시각 룰** — 아지즈/Bellafiore `rules.py`(Rule/RuleResult) 구조 그대로. `BookStrategy`(intraday) 상속. **신규 인프라 불필요(95% 재사용).**
2. **강창권 핵심 명제 검증**: "한국 거래대금 상위 종목에서 돌파/눌림목/종가베팅이 당일 단타 엣지"를 `minute_candles` 다기간으로 검증/반박. 아지즈·Bellafiore·Raschke와 **동일 universe(top_volume:50)·청산·기간(2025-10/2026-04/2026-05)**으로 직접 A/B.
3. **종목풀 = 거래대금 상위**(강창권 셋업 1의 핵심). 기본 `--universe top_volume:50`(아지즈 복원·Bellafiore·Raschke와 동일 → 비교성). 강창권은 종목선별이 룰의 전제이므로 `all` 풀은 보조로만.
4. **시각(time-of-day) 룰 명시화**: 분봉 `time` 컬럼으로 장초반(09:00~09:40)/점심(11:30~13:00)/종가(14:30~15:20) 구간 게이트. 기존 책 인프라에 없던 요소 → ctx에 `time`/`bar_idx`/`bars_per_day` 주입(아지즈 red_to_green의 prev_close 주입 패턴 확장).
5. **전일종가(prev_close)** = red_to_green·갭/등락률·종가베팅에 필요. 아지즈는 `ctx.get("prev_close")` 패턴 존재하나 run 스크립트가 미주입(fallback 추정값 사용). 강창권은 갭/등락률이 핵심이므로 **prev_close 정식 주입 필요**(§7, minute_candles 전일 종가에서 산출 가능 — 백필 불요).
6. 청산: 강창권 단타 = 짧은 익절(1~5%)·즉시 손절·당일 청산. **Variant 다종 측정**(§4). EOD 강제청산 지배(intraday). 종가베팅 셋업만 익일 청산 허용(별도 처리, §4 주석).
7. no-lookahead(t+1 시가 체결), 거래비용 왕복 ~0.21%(분봉 책 공통, 세금 0.18%+수수료), 슬리피지 0.1% 단방향. 롱 전용.

---

## Phase 0. 데이터 선행작업 — (조건부) 경미

분봉 코어는 **백필 불필요**. `minute_candles`에 OHLCV + **`amount`(거래대금) 컬럼 fully populated(NULL 0건)** 확인됨. 다만:

| 항목 | 현황 | 백필 필요? | 비고 |
|------|------|-----------|------|
| 분봉 OHLCV | `minute_candles` 1,373종목 · 2025-02-24~2026-05-29 · 5,219만행 · ~389봉/일(09:00~15:28) | 불필요 | 코어 데이터 |
| **거래대금(amount)** | `minute_candles.amount` 직접 · **NULL 0건** | 불필요 | 거래대금 선별·종가베팅 강도 측정에 직접 사용 |
| **전일종가(prev_close)** | minute_candles 전일 마지막 봉 close에서 산출 가능 | **불필요(재구성)** | run 스크립트에서 종목별 전일 종가 dict 빌드 후 ctx 주입 |
| **시각(time)** | `minute_candles.time`(HHMMSS 문자열) 직접 | 불필요 | 시각 게이트(점심/종가/장초반) |
| **외인·기관 수급** | 분봉 수급 데이터 **부재** | **백필필요(or 제외)** | 셋업 6(수급추종) 종속. **권장=v1 제외**(KIS 투자자별 분봉 수급 별도 수집 부담). |
| 호가(매수/매도 잔량) | **부재** | 백필필요(or 제외) | "호가창 읽기" 정성 영역 → 코드화 제외 |

> 결론: **거래대금·돌파·눌림목·종가베팅·시각 룰 코어는 Phase 0 없이 즉시 코드화 가능**(prev_close는 재구성). 수급·호가 셋업만 데이터 부재로 v1 제외.

---

## 1. 종목풀 (universe)

- 기본: **`top_volume:50`** (기간 거래대금 `SUM(close*volume)` 상위 50). 강창권 "당일 강한 거래대금" 선별의 근사 + **아지즈 복원/Bellafiore/Raschke와 동일 → 직접 A/B**.
- 변형: `top_volume:20`(더 집중), `top_volume:100`(완화), `all`(전체, 비교용).
- (개선 후보) 일별 거래대금 상위 동적 리밸런싱 — 현재 인프라는 기간 합계 정적 선별. v1은 정적, §9 결정 시 동적 확장.

---

## 2. ctx 주입 확장 (run 스크립트)

아지즈/Bellafiore는 `generate_signal(stock_code, window, "intraday")`만 호출(ctx extra 미사용). 강창권은 시각·전일종가가 룰의 전제이므로 `generate_signal_with_extra_ctx` 경로 사용:

```python
ctx_extra = {
    "prev_close": prev_close_by_code[code],   # 전일 마지막 봉 close
    "time": str(bar_now["time"]),             # 현재 봉 HHMMSS
    "bar_idx": i,                             # 당일 봉 인덱스(0=09:00)
    "session_open": float(day_first_open),    # 당일 시초가
}
```

> **주의**: BookBacktester는 현재 `generate_signal`(extra 미전달)만 호출(book_backtester.py:140). 강창권 시각/전일종가 룰을 쓰려면 **백테스터에 extra_ctx 주입 경로 추가**(아래 두 옵션 중 §9 결정):
> - (A) BookBacktester에 옵션 콜백 `ctx_builder(df, i, code)` 추가 → `generate_signal_with_extra_ctx` 호출(범용, 타 책 영향 없음).
> - (B) 룰이 df에서 자력 계산(time은 `df["time"].iloc[-1]`, 전일종가는 df 첫봉 open 근사) → 백테스터 무수정. **prev_close 정확도 손실**(red_to_green과 동일 한계).
> 권장 = **(A)** (강창권 갭/종가베팅 정확도 위해). minute_candles에 `time` 컬럼이 이미 있어 시각은 df 자력 가능, 전일종가만 주입 필요.

---

## 3. 룰 N종 (확정 후보)

> 입력 df = 당일 분봉 OHLCV(+time). t = df 마지막 행. t+1 접근 금지.

### rule_breakout_prev_high (돌파, conf 70)
```
시각 ∈ [09:00, 09:40] AND last_close > prev_high(전일고가 또는 당일 첫 N봉 고가)
AND 거래량 직전 평균 대비 증가
```
> 강창권 "전일 고가 돌파 + 09:40 고점 매도". 아지즈 orb의 한국 시각판. 빠른 익절(§4 B/C).

### rule_pullback_uptrend (눌림목, 시그니처, conf 73)
```
당일 단기 급등(직전 M봉 +X%) 후 얕은 되돌림(고점 대비 -p%~-2p%)
AND last_close > last_open(양봉 반등) AND last_close > 단기 MA(예: 분봉 20)
```
> 강창권 "상승추세 작은 눌림". Bellafiore fade_vwap·아지즈 bull_flag와 A/B. 가장 자주 언급되는 시그니처.

### rule_lunch_pullback (점심 눌림목, conf 68)
```
시각 ∈ [11:30, 13:00] AND 오전 강세(시초 대비 +Y%) 종목의 눌림 후 양봉 반등
```
> 후속작 "점심시간 눌림목 대응" 명시. 시각 특화 변형 — 기존 책에 없던 한국 토착 룰.

### rule_close_betting (종가 베팅, conf 66, 익일청산)
```
시각 ∈ [14:30, 15:20] AND 당일 강세 지속(종가권 신고가 근처)
AND 거래대금 상위 + 장대양봉 → 종가 매수
```
> 강창권 "종가 베팅의 기술". **익일 청산(1일 스윙)** — EOD 강제청산 예외 처리 필요(§4). v1은 **익일 시초 청산 근사** 또는 EOD 청산으로 단순화(§9 결정).

### rule_ma_long_breakout (분봉 장기선 돌파, conf 64)
```
분봉 정배열 전환 AND last_close > 분봉 240 MA (가능하면 480 MA)
```
> 후속작 "240분·480분선 돌파". **240봉 ≈ 당일+전일 누적 필요**(389봉/일) → 멀티데이 분봉 연결 필요(§9). v1은 분봉 120 MA로 축소 가능.

```
ALL_RULES = [rule_breakout_prev_high, rule_pullback_uptrend, rule_lunch_pullback,
             rule_close_betting, rule_ma_long_breakout]
```
> (수급추종 rule_flow_follow는 데이터 부재로 v1 제외 — §7/§9.)

---

## 4. 청산 Variant

강창권 단타 = 짧은 익절(1~5%)·즉시 손절·당일 청산. 분봉 책 공통 baseline + 강창권형 추가:

| Variant | sl | tp | max_hold(봉) | EOD | 비고 |
|---------|-----|-----|------|-----|------|
| **K** (강창권형) | 0.02 | 0.03 | 40 | 강제 | 짧은 익절·손절·당일. 9:40 류 빠른 청산 근사 |
| S (스캘프) | 0.01 | 0.015 | 15 | 강제 | 초보 1~2% 목표(저자 권장 초단타) |
| W (완화) | 0.03 | 0.05 | 120 | 강제 | 아지즈/Bellafiore 복원 실험과 동일 → 직접 비교 |
| **C** (종가베팅) | 0.03 | 0.05 | — | **익일 청산** | rule_close_betting 전용. 익일 시초 또는 익일 장초 청산 |

- 기본 K. W는 기존 3책 복원조건과 동일 청산 → 직접 A/B 보장.
- **종가베팅 익일청산**: BookBacktester는 EOD 강제청산(eod_liquidate=True) 구조. 익일 보유는 (a) eod_liquidate=False + 멀티데이 분봉 연결 또는 (b) v1은 "당일 종가 매수 → EOD 청산 불가"이므로 **종가베팅은 별도 실행(eod off)**. §9 결정.
- forced_close 지배 명시. warmup 20봉.

---

## 5. 코드 산출물

```
strategies/books/kang_haru_silijeon/
├── __init__.py
├── rules.py      # Rule 5종(breakout_prev_high/pullback_uptrend/lunch_pullback/close_betting/ma_long_breakout) + ALL_RULES
└── strategy.py   # KangHaruStrategy(BookStrategy, holding_period="intraday") + BOOK_META + build_strategy
scripts/run_kang_haru.py   # run_books_research 또는 아지즈 run 패턴 복제 + prev_close 빌드 + ctx_extra 주입(옵션 A 시 BookBacktester 확장)
```

- strategy.py: `BOOK_META` id="kang_haru_silijeon", name="강창권 하루 만에 수익 내는 실전 주식투자", category="intraday_kr", data_granularity="minute". holding_period="intraday".
- run 스크립트: `scripts/run_books_research.py` 재사용 가능(`--book kang_haru_silijeon`). 단 **시각/전일종가 룰 정확 구현 시 BookBacktester ctx_builder 확장(옵션 A) 필요** → 전용 `run_kang_haru.py` 권장.
  - `_build_prev_close(data)`: 종목별 `trade_date` 그룹의 직전일 마지막 봉 close → `{code: {trade_date: prev_close}}`.
  - leaderboard book_id="kang_haru_silijeon", universe=f"top_volume:{N}"(기존 3책과 동일), period in {2025-10, 2026-04, 2026-05}, reports-dir "reports/books_research/kang_haru_silijeon".
- **실행 RoboTrader_template/ cwd**.

---

## 6. 백테스트 실행

```
python scripts/run_kang_haru.py --period 2025-10 --all-modes --universe top_volume:50 --variant K
python scripts/run_kang_haru.py --period 2026-04 --all-modes --universe top_volume:50 --variant K
python scripts/run_kang_haru.py --period 2026-05 --all-modes --universe top_volume:50 --variant K
# 변형
... --variant W   # 아지즈/Bellafiore 복원조건 직접 비교
... --variant S   # 초단타 스캘프
... --universe top_volume:20 / all   # 종목풀 민감도
# 종가베팅(익일청산, eod off) 별도
python scripts/run_kang_haru.py --period 2025-10 --mode single --rule close_betting --variant C --eod-off
```

> 기존 책과 동일하게 3기간 × (5 single + all_AND) 매트릭스. universe·청산 통일로 아지즈/Bellafiore/Raschke와 leaderboard 직접 비교.

---

## 7. 데이터 가용성 분류 (있음 / 재구성 / 백필필요)

| 지표 | DB 상태 | 분류 | 비고 |
|------|---------|------|------|
| 분봉 OHLCV | `minute_candles` open/high/low/close/volume | **있음** | ~389봉/일, 09:00~15:28 |
| **거래대금** | `minute_candles.amount` | **있음** | NULL 0건. 종목선별·종가베팅 강도 |
| 시각(time) | `minute_candles.time` (HHMMSS str) | **있음** | 점심/종가/장초반 게이트 |
| **전일종가** | 전일 마지막 봉 close | **재구성** | run 스크립트에서 빌드(백필 불요) |
| 시초가/당일 등락률 | 당일 첫봉 open + 전일종가 | **재구성** | 갭/강세 판정 |
| 분봉 240/480 MA | 멀티데이 분봉 연결 | **재구성(주의)** | 당일 389봉 < 240×2 → 전일 분봉 누적 필요 |
| **외인·기관 수급** | **부재** | **백필필요** | KIS 투자자별 분봉/일별 수급 별도 수집 → **v1 제외 권장** |
| 호가(잔량) | **부재** | **백필필요(or 제외)** | "호가창" 정성 영역 → 코드화 제외 |
| 재료/이슈/뉴스 | **부재** | 제외 | 정성 판단 — 거래대금/등락률로 근사만 |

---

## 8. 검증

- pytest tests/books/ 통과(아지즈/Bellafiore 테스트 패턴 복제). no-lookahead: t+1 시가 체결, 룰은 df[..t]만.
- **책간 A/B 핵심**(동일 universe top_volume:50·동일 청산 W·동일 3기간):
  - 강창권 `pullback_uptrend` vs Bellafiore `fade_vwap`(한국 분봉 베스트) vs 아지즈 `bull_flag` → 눌림목 류 직접 대결.
  - 강창권 `breakout_prev_high` vs 아지즈 `orb`/복원 abcd → 돌파 류 대결(한국 토착 vs 미국식).
  - 강창권 시각 룰(`lunch_pullback`/`close_betting`)이 시각 게이트 없는 룰 대비 엣지 추가하는지 — **한국 분봉 시각 효과 1급 질문**.
- 3기간 시계열 + (가능 시) Raschke처럼 2025-10 단일 강세장 의존성 점검.
- 거래수·Hit Rate·Sharpe·Calmar·MaxDD를 기존 13권 leaderboard에 append.

## 9. 사장님 결정 필요 (코드화 전 결재)

1. **BookBacktester ctx 확장 방식** — 시각/전일종가 룰의 정확 구현. **(A) BookBacktester에 `ctx_builder` 콜백 추가**(prev_close/time 정식 주입, 타 책 무영향, 권장) vs **(B) 룰이 df 자력 계산**(전일종가 근사 손실, 백테스터 무수정). → **권장 (A)**.
2. **종가베팅 익일청산 처리** — rule_close_betting은 본질상 1일 스윙. **(a) eod off + 멀티데이 분봉 연결로 익일 시초 청산**(정확, 구현 부담) / **(b) v1은 당일 EOD 청산으로 단순화**(저자 의도 일부 손실) / **(c) v1에서 close_betting 제외**. → **권장 (b)로 시작, 효과 보이면 (a)**.
3. **수급추종 셋업 포함 여부** — 외인/기관 수급 데이터 **부재**. **(a) v1 제외**(권장, 분봉 코어만) / **(b) KIS 투자자별 수급 백필 후 포함**(수집 부담). → **권장 (a)**.
4. **분봉 240/480 장기선** — 당일 389봉으로 240봉 부족 → 멀티데이 분봉 연결 필요. **(a) 멀티데이 연결 구현**(정확) / **(b) v1은 분봉 120 MA로 축소** / **(c) ma_long_breakout v1 제외**. → **권장 (b)**.
5. **종목풀 기본값** — `top_volume:50`(기존 3책 비교성, 권장) vs `top_volume:20`(강창권 "강한 거래대금 집중"에 더 충실). → **권장 top_volume:50 기본 + 20/100 sweep**.
6. **셋업 우선순위(표본 부족 대비)** — 5셋업 전부 vs 시그니처 2~3개(pullback_uptrend·breakout_prev_high·close_betting) 집중. → **권장 전부 코드화 후 표본 충분한 것 위주 해석**.

---

## 10. 한계 (전면)

- **책 실물 미보유 — 공개 자료 재구성**: 저자·출판사(강창권/길벗)·"분봉 단타·거래대금·돌파/눌림목/종가베팅·09:40 익절·점심 눌림목" 골격은 서점 소개·후속작 목차·서평 다수에서 일치 확인. 그러나 **각 셋업의 정확한 진입 임계(되돌림 %, 거래량 배수, MA 기간, 익절 폭)는 실물 미확인 → 본 설계의 수치는 합리적 추정**이며 실물 확인 시 재조정 필요. 일부 셋업(점심 눌림목·240분선)은 **후속작 『단기 트레이딩의 정석』 목차 기반**으로, 본작에 동일 형태로 있는지는 미확정.
- **정성 영역 코드화 불가**: "재료/이슈 판단", "호가창 읽기", "수급 감각"은 데이터 부재 → 거래대금/등락률 근사로만 대체. 저자 엣지의 상당 부분이 정성적일 수 있어 백테스트가 저자 실적을 재현하지 못할 위험.
- **분봉 책 공통 한계(아지즈 리포트 §8과 동일)**: 종목풀 생존편향(기간 7일 내 데이터 종목만), 거래비용 왕복 0.21% 가정, 단일 매수·동시보유 1종목, 청산 룰 고정 영향, 1분봉 노이즈(손절 -2% 잦은 발동).
- **데이터 기간 편향**: minute_candles 2025-02~2026-05 — 2025.6~2026 **실제 대폭등장** 포함(MEMORY 확인). 단일 강세장 의존성(Raschke anti가 2025-10에만 +59%였던 것처럼) 주의. 3기간만으로 국면 강건성 단정 불가.
- **종가베팅·익일청산·240분선**은 현 BookBacktester(EOD 강제청산·당일 분봉) 구조와 충돌 → §9 결정 전까지 단순화 불가피(저자 의도 부분 손실).
- **수급 셋업 제외**로 강창권 방법론의 한 축(기관/외인 추종)이 v1에서 미검증.

---

## 부록: 조사 출처(WebSearch)
- 알라딘/교보문고/교보ebook/Apple Books — 『하루 만에 수익 내는 실전 주식투자』(강창권, 길벗) 서지·소개
- 교보문고/알라딘/국립중앙도서관/밀리의서재 — 『주식투자 단기 트레이딩의 정석』(강창권, 2024~2025) 목차(20일선 눌림목·240/480분선 돌파·점심 눌림목·종가베팅·수급 추종)
- 나무위키 「주식투자/단타매매 기법」, 내비에셋 데이트레이딩 정리 — 한국 단타 일반론(09:40 익절·거래대금·시초가 돌파·1~5% 목표·즉시 손절)
> ⚠️ 모든 셋업 수치는 위 공개자료 재구성 + 본 인프라(아지즈/Bellafiore) 관행 기반 추정. 실물 확인 시 §3/§4 수치 보정 요망.
