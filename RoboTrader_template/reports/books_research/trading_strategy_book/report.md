# Book 19 『트레이딩 전략서』 — 일봉 매수후보 스크리너 (조건식 A~I)

> 생성일: 2026-06-03
> 설계: [../../../docs/superpowers/specs/2026-06-03-trading-strategy-book-screener-design.md](../../../docs/superpowers/specs/2026-06-03-trading-strategy-book-screener-design.md)
> 계획: [../../../docs/superpowers/plans/2026-06-03-trading-strategy-book-screener.md](../../../docs/superpowers/plans/2026-06-03-trading-strategy-book-screener.md)
> 코드: `strategies/books/trading_strategy_book/`(rules.py·strategy.py) · 테스트 `tests/books/test_trading_strategy_book_daily.py`(12 passed)

## 0. 출처·범위

- **이북 부재** → 사장님 정리 노트 기반. 노트의 **HTS 공식 조건검색식 A~I**(200일 신고가 + Envelope 돌파)를 일봉 매수후보 스크리너로 **verbatim 코드화**.
- **분봉(3/5분) 눌림목 실행층 보류**: 이등분선/가격박스/볼린저밴드 진입·청산은 사장님 노트에서도 임계값이 다수 미정("밀집 기준?", "작은 캔들 기준?", "이탈 0.2%?")이고, 18권 내내 **분봉단타 전멸** 전례 + **임계값 재튜닝=과적합** 교훈으로, 임의 임계값 코드화는 함정. → 진입 스크리너만 충실 검증.
- 청산은 정본 멀티버스 드라이버(`book_portfolio_multiverse.py`)의 sl/tp/mh 스윕으로 근사(책 명목 +3%/−3% 포함). 책 진짜 청산(장중 이등분선 트레일링)은 일봉 해상도로 표현 불가 → **진입 충실성에 한정한 결론**.

## 1. 진입 규칙 (조건식 A~I, 평가시점 t=마지막봉, 진입 t+1 시가)

| 조건 | 의미 | 기본값 |
|---|---|---|
| A | 200일 종가 신고가 `close[t] >= max(close[t-199..t])` | high_window=200 |
| B | Envelope 상단 돌파 `close[t] >= SMA(close,10)·1.10` | env_period=10, env_pct=0.10 |
| C | 양봉 `open[t] < close[t]` | — |
| D | 거래량 전일대비 100%+ `vol[t] >= vol[t-1]` | vol_ratio=1.0 |
| E | 종가 > 이등분선 `close[t] > (high+low)/2` | — |
| F | 5일 거래대금 ≥ 50억(금일 제외) | value_window=5, min_value_mil=5000 |
| ¬G | 갭상승 제외 `open[t] >= close[t-1]·1.07` | gap_excl=0.07 |
| ¬H | 직전급등 제외 `close[t-1] >= close[t-2]·1.10` | prior_surge_excl=0.10 |
| I | 당일 시가대비 +3% `close[t] >= open[t]·1.03` | intraday_gain=0.03 |

신호 = A∧B∧C∧D∧E∧F∧¬G∧¬H∧I. 거래대금은 일봉에 별도 컬럼이 없어 `close·volume/1e6`(백만) 근사. no-lookahead·NaN가드 테스트 통과.

**미코드화(범위 외)**: 산문 전용 "한 달 내 +100% 제외"·"장초반 +20% 제외"·"상한가 다음날 제외"(장중·재량), 분봉 실행층 전체.

## 2. 백테스트 결과 (정본 멀티버스, daily, top_volume:50, K∈{3,5,10}, sl/tp/mh 스윕 72조합)

### 2.1 전구간 2021-01-01 ~ 2026-06-02 (정본·동일 유니버스)

| | combo | 거래수 | Sharpe | PnL | MaxDD | Hit |
|---|---|---|---|---|---|---|
| **BEST** | sl=0.05 tp=0.03 mh=3 K=10 | 227 | **0.435** | **−6.1%** | **99.8%** | 53.3% |
| BASELINE | sl=0.03 tp=0.03 mh=1 K=3 | 210 | 0.429 | −67.0% | 99.3% | 42.4% |

- **72조합 전부 PnL 음수**(범위 best −6.1% ~ 최악 −99%, 절반 이상이 −50% 이하), **MaxDD ~99.8%**(사실상 파산). 신호는 **희소하지 않음**(227거래).
- Sharpe 0.435는 **채택바 0.6 미달**이며, 음수 PnL·파국적 MaxDD와 병치하면 **per-trade 변동성만 낮을 뿐 자본경로는 붕괴**(Sharpe 단독 오해 소지).
- ⚠️ **MaxDD 99.8% 정밀도 주의**: sl≤5%·mh≤5봉인데 99.8%까지 빠지는 것은 단순 손실 복리로는 설명이 약함 → 상관된 돌파실패 군집 + 특정 종목 급락(갭 관통)일 가능성. 정확한 기여 분해는 미수행(판정에 불필요). 단 **음수 PnL·Sharpe<0.6은 다조합 강건**이라 판정은 견고.

### 2.2 구간(연도) 분해 — ⚠️ 유니버스가 구간마다 재계산·in-sample best combo (참고용)

| 구간 | 성격 | best 거래수 | best Sharpe | best PnL | baseline Sharpe/PnL |
|---|---|---|---|---|---|
| 2021 | 상승→고점 | 8 | 1.232 | +6.7% (MaxDD 2.6%) | — |
| **2022** | **BEAR(−25%)** | **0** | **—** | **거래 없음** | — |
| 2023–24 | 회복/완만 | — | 0.295 | +6.9% | 0.127 / +1.6% |
| 2025–26 | 강세 | — | 0.856 | +20.0% | 0.660 / **−3.5%** |

- **★구조적 발견: 약세장 자동 무거래.** 조건 A(200일 신고가)가 약세장(2022)엔 충족 종목이 없어 **스크리너가 스스로 꺼진다**(거래 0). 이는 *능동적 방어가 아니라 부재* — 약세장 per-trade 성과 측정 자체가 불가(Elder의 BEAR +3.01% 같은 방어 데이터 없음).
- 연도별 양(+) 구간들은 **in-sample best combo 체리피킹**(2025–26 +20%도 baseline은 −3.5%) → 일반화 근거 약함. 구간마다 유니버스가 달라 전구간(2.1)과 직접 합산 불가.

## 3. 채택 판정 — **CANDIDATE 부적격**

| 기준 | 결과 |
|---|---|
| Sharpe ≳ 0.6 | ✗ 전구간 best 0.435 |
| 양(+) 수익 | ✗ 전구간 음수, 다조합 −50~−88% |
| 하락방어 | ✗ 측정 불가(BEAR 거래 0 = 부재) |
| 강건성 | ✗ 양수 구간은 유니버스·combo 의존 |

**해석**: 진입이 **이미 확장된 돌파**(MA10 대비 +10%↑ Envelope 상단 + 당일 +3% + 200일 신고가)를 t+1에 추격 → 국소 고점 매수 → 되돌림. tp 3%/sl 5% 비대칭까지 겹쳐 음수 기대. **19권째 "한국 일봉은 추세추종 눌림목(Elder/Minervini dryup)만 생존, 확장 돌파 추격은 부적격" 재확인.**

**가상매매 미등록.** 라이브 영향 없음(신규 책 파일만 추가, 기존 5전략·드라이버 무수정).

## 4. 산출물·재현

- 코드: `strategies/books/trading_strategy_book/{rules.py,strategy.py,__init__.py}`, `tests/books/test_trading_strategy_book_daily.py`(12 passed).
- 재현:
  ```
  python scripts/book_portfolio_multiverse.py --book trading_strategy_book --rule envelope_200d_high \
    --granularity daily --start 2021-01-01 --end 2026-06-02 --universe top_volume:50 --K-list 3 5 10 \
    --max-per-stock 3000000 --initial-capital 10000000 \
    --entry-grid '{"high_window":[200]}' --exit-grid '{"sl":[0.03,0.05],"tp":[0.03,0.05,0.10],"mh":[1,2,3,5]}' \
    --workers 4 --out D:\tmp\multiverse\book19_full
  ```
- TSV: `D:\tmp\multiverse\book19_full\book_portfolio_trading_strategy_book_envelope_200d_high.tsv` (구간별 `book19_{2021,2022bear,2023_24,2025_26}`).

> 비고: 본 책은 내부 **Book 19**. index.md 진행표는 현재 1~17까지만 등재(taesso bible2=Book 18은 별도 세션 통합 대기 → 18번 공백). leaderboard.parquet 갱신은 부적격이라 보류(상위권 무변동).

---

## 5. 분봉 실행층 3전략 (2026-06-04)

> 설계: [../../../docs/superpowers/specs/2026-06-04-trading-strategy-book-minute-execution-design.md](../../../docs/superpowers/specs/2026-06-04-trading-strategy-book-minute-execution-design.md) · 계획: [../../../docs/superpowers/plans/2026-06-04-trading-strategy-book-minute-execution.md](../../../docs/superpowers/plans/2026-06-04-trading-strategy-book-minute-execution.md)
> 코드: `strategies/books/trading_strategy_book/rules.py`(3룰 추가) · 테스트 `tests/books/test_trading_strategy_book_minute.py`(26 passed)

### 5.0 범위·골격
- §0에서 보류했던 **분봉(3/5분) 실행층 3전략**(가격박스·볼린저밴드·눌림목)을 사장님 지시로 코드화. 노트의 "?" 임계값은 사장님과 **하나씩 확정**(임의 추측 아님).
- **진입만 충실 코드화, 청산은 드라이버 sl/tp/mh 근사**(일봉 A~I와 동일 철학). 공통 **이등분선 필터**(종가≥이등분선)·**세션 인식**(당일 누적고/저·당일 최다거래량을 datetime으로 당일 봉만).
- **★검증 한계(판정 선반영)**: 분봉 데이터 `minute_candles` = **2025-02~2026-06, 전 구간 강세/횡보, BEAR 부재** → 약세장 강건성 측정 불가(일봉 A~I와 동일). 검증 구간 = `--periods 2025-10,2026-04,2026-05`(3개월).

### 5.1 3전략 진입 규칙 (확정 임계값)
| 전략 | 봉 | 핵심 로직 | 확정 임계값 |
|---|---|---|---|
| `rule_price_box_tma` | 1분 | TMA(30) ± 편차밴드(최근60봉 \|c−TMA\| mean+2std), 하한 지지 OR 중심 상향돌파 + 이등분선 | tma=30·dev=60·k=2·tol0.2% |
| `rule_bollinger_squeeze` | 5분 | BB(20,2) 직전봉 밴드폭≤최근100봉 중앙값(스퀴즈) + 상한돌파 OR 첫 하한지지 + 이등분선 | bb20·k2·sqz100·tol0.2% |
| `rule_pullback_volume_dry` | 5분 | **명시적 4단계: ①상승 leg → ②하락(되돌림 dip) → ③횡보(거래량 급감·캔들 축소) → ④횡보 박스상단 돌파** | leg12·rise2%·dip1%·¼·½ |

- **눌림목 4단계 재설계 경위**: 초기 프록시(`close[t]>close[t-6]`+건조+확대)는 **되돌림 dip을 검출 안 해** 단조 상승 후 확대봉에도 발사되는 충실성 갭이 있었음(사장님 지적). → 상승·하락·횡보·돌파를 **각각 명시 검출**하도록 재구현(국소고점 P_high·되돌림저점 P_low·박스상단 돌파). 회귀테스트 `test_pb4_no_dip_blocks`로 "단조상승 미발사" 보장.

### 5.2 백테스트 결과 (정본 멀티버스, minute, top_volume:50, K∈{3,5}, sl/tp/mh 36조합, 3개월)
| 룰 | 봉 | best mSharpe | best mPnl | 양수기간 | 거래수 | 판정 |
|---|---|---|---|---|---|---|
| price_box_tma | 1분 | 0.322 | **−98.5%** | 0/3 | 8519 | ✗ |
| bollinger_squeeze | 5분 | 0.615 | **−75.4%** | 0/3 | 2340 | ✗ |
| pullback_volume_dry(4단계) | 5분 | 0.402 | **−21.9%** | 0/3 | 474 | ✗ |

- **3전략 전부 3개 구간 모두 PnL 음수(양수기간 0/3)**. best mPnl −21.9%~−98.5%. Sharpe>0.6는 볼린저(0.615)뿐이나 PnL −75%와 병치하면 **per-trade 변동성만 낮고 자본경로 붕괴 = Sharpe 착시**(일봉 §2.1과 동일 함정).
- **★눌림목 4단계의 의미 있는 개선**: 프록시(거래 1960·mPnl −50%) 대비 4단계는 **거래 474로 급감·mPnl −21.9%로 대폭 개선**. 되돌림 dip 명시 요구가 선별성을 크게 높였음(가장 덜 파국적). **하지만 채택바(Sharpe 0.6·양수)에는 여전히 미달.**

### 5.3 채택 판정 — **3전략 전부 CANDIDATE 부적격**
| 기준 | price_box | bollinger | pullback(4단계) |
|---|---|---|---|
| Sharpe ≳ 0.6 | ✗ 0.322 | △ 0.615(착시) | ✗ 0.402 |
| 양(+) 수익 | ✗ −98.5% | ✗ −75.4% | ✗ −21.9% |
| 강건성(양수기간) | ✗ 0/3 | ✗ 0/3 | ✗ 0/3 |
| 약세장 방어 | ✗ 측정불가(BEAR 부재) | ✗ | ✗ |

**해석**: 18·19권 내내 확인된 **"한국 분봉단타 전멸"** 재확인. 분봉 실행층 3전략 모두 강세/횡보장에서조차 한정자본 포트폴리오로는 음수. 눌림목 4단계가 가장 충실·선별적이나 그래도 부적격. **가상매매 미등록·라이브 무영향**(신규/수정 책 파일만, 기존 5전략·드라이버 무수정).

### 5.4 미코드화·한계 (정직)
- **청산 재량**(10분 무반응·상승폭<하락폭·이등분선 트레일링·±3%) → 드라이버 sl/tp/mh 근사. 진입 충실에 한정한 결론.
- **장중 재량 게이트**(+20% 급등 접근금지·상한가 다음날·2마디) 보류.
- "조건부 편차"(가격박스)·TMA(30) 정의는 재현가능 단순화(spec R4·R5).
- **교차세션 caveat**: 눌림목 pre-breakout 윈도우·볼린저 룩백이 전일 봉을 혼입할 수 있음(day_max_vol·이등분선만 세션 한정). 분봉 데이터 BEAR 부재와 함께 구조적 한계.

### 5.5 재현
```
# 가격박스(1분)
python scripts/book_portfolio_multiverse.py --book trading_strategy_book --rule price_box_tma \
  --granularity minute --periods 2025-10,2026-04,2026-05 --minute-resample-freq 1 \
  --universe top_volume:50 --K-list 3 5 --max-per-stock 3000000 --initial-capital 10000000 \
  --entry-grid '{"tma_period":[30]}' --exit-grid '{"sl":[0.02,0.03],"tp":[0.02,0.03,0.05],"mh":[2,4,8]}' \
  --workers 4 --out D:\tmp\multiverse\book19_minute_pricebox
# 볼린저(5분): --rule bollinger_squeeze --minute-resample-freq 5 --entry-grid '{"bb_period":[20]}'
# 눌림목 4단계(5분): --rule pullback_volume_dry --minute-resample-freq 5 --entry-grid '{"leg_window":[12]}'
```
- TSV: `D:\tmp\multiverse\book19_minute_{pricebox,bollinger,pullback4}\book_portfolio_*.tsv`.
