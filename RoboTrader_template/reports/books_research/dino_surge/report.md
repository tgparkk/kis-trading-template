# 디노(백새봄) 『돈이 된다! 급등주 투자법』 — 다년·국면 백테스트 리포트

> Book 16 · 진서원(2022) · 네이버 월재연 카페 베스트셀러 · 핵심 시그니처 **"수익률보다 회전율"**(낚싯대 매매법, +10% 무조건 익절)
> 백테스트 기간: **2021-01-04 ~ 2026-05-29**(daily_prices 전체 가용 기간, 1,304 분류 거래일)
> 유니버스: top_volume:N(일평균 거래대금 상위) · 일봉 스윙 · 수정주가(adj_factor) · no-lookahead(t 신호 -> t+1 시가 체결)
> 거래비용: 수수료 0.015% + 세금 0.18% + 슬리피지 0.1% (elder/haru/문병로와 동일)

---

## 0. 결론 (먼저)

**CANDIDATE 부적격.** 디노 급등주 회전 전략은 **펀더멘털 붕괴군(Sharpe ~0.1)** 에 속한다. 헤드라인 연율 Sharpe 0.08~0.09(베스트 variant B)로 추세추종 생존군(Elder 0.68 / Minervini 0.64 / 강창권 ma20 0.44 / Book15 ma5 0.63)에 한참 못 미친다.

단, **두 가지 의미 있는 부분 발견**:
1. **약세장 진입 방어는 의외로 성립**: variant B(회전 단순)의 **entry-BEAR per-trade +3.59%(n=39)** 로 Elder의 BEAR +3.01%를 표본/수치 모두 상회. "급등 후 눌린 자리"가 약세장에서 저가매수 기회로 작동.
2. **그러나 책의 핵심 주장("+10% 무조건 익절" 회전)은 한국 일봉에서 약하게만 유효**: +10% 익절은 *발동 시* 평균 +14.7%지만 전체 청산의 31%만 도달, 손절(-7.2%, 33%)이 거의 상쇄. **회전 철학 자체가 알파를 만들지 못함**.

또한 **책의 시그니처인 "디노 테스트(재무 4축 점수)"가 알파를 더하지 못함**(재무게이트 켜면 표본만 줄고 Sharpe 개선 없음) — 펀더멘털 책 6권째와 동일한 "재무 스코어 ~= 노이즈" 결론. 한국 일봉에서 살아남는 건 **추세추종 진입(Elder/Minervini)** 뿐이라는 16권째 재확인.

---

## 1. 실행 커맨드 (실제 실행분)

```bash
# 필수 3종 (전체기간, top_volume:50)
python scripts/run_dino_surge.py --variant A --all-modes
python scripts/run_dino_surge.py --variant A --all-modes --no-fin
python scripts/run_dino_surge.py --variant B --all-modes

# 표본 강건성 (top_volume:100)
python scripts/run_dino_surge.py --variant B --mode single --rule pullback_rebound --top-n 100
python scripts/run_dino_surge.py --variant A --mode single --rule dino_test_pullback --no-fin --top-n 100
python scripts/run_dino_surge.py --variant A --mode single --rule dino_test_pullback --top-n 100

# 재무 컷오프 민감도 (디노 재무점수 0~5)
python scripts/run_dino_surge.py --variant A --mode single --rule dino_test_pullback --min-fin-score 1
python scripts/run_dino_surge.py --variant A --mode single --rule dino_test_pullback --min-fin-score 2
# (기본 --min-fin-score 3 은 필수 3종에 포함)

# 국면/연도 분해
python scripts/regime_split_dino_surge.py   # 신규 작성
```

산출 경로:
- per-trade 로그: `reports/books_research/dino_surge/results_variant*_single_*.parquet` (8개)
- 국면/연도 분해표: `reports/books_research/dino_surge/regime_split.parquet`, `regime_split.md`
- 리더보드: `reports/books_research/leaderboard.parquet` (book_id=`dino_surge`, rows 229~237 = 전체기간 canonical)
- 국면 라벨: `reports/books_research/regime_label_5y.parquet` (Elder/Minervini/문병로 공용 재사용)

---

## 2. 전체기간 메트릭 (top_volume:50, 2021~2026)

> headline Sharpe/Calmar/MaxDD/hit/avg_hold = **종목별(50종목, 각 1천만 독립) 메트릭 평균**(다른 책과 동일 집계). pnl = 종목별 수익률 평균.

| variant | rule | mode | n_trades | pnl% | **Sharpe** | Calmar | MaxDD% | hit% | hold(bars) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| **B** | **pullback_rebound** | single | 55 | **3.123** | **0.078** | 0.869 | 4.17 | 27.8 | 4.4 |
| A_nofin | dino_test_pullback | single | 135 | 0.582 | 0.025 | 0.212 | 4.87 | 31.4 | 1.8 |
| A_nofin | all_AND | all_AND | 9 | 0.526 | 0.029 | 0.039 | 0.57 | 11.0 | 0.5 |
| A | dino_test_pullback | single | 8 | 0.102 | -0.003 | -0.002 | 0.30 | 2.3 | 0.1 |
| A | pullback_rebound | single | 56 | 1.164 | -0.001 | 0.380 | 2.86 | 22.1 | 1.6 |
| A | all_AND | all_AND | 0 | — | — | — | — | — | — |
| B | dino_test_pullback | single | 8 | 0.370 | 0.018 | 0.079 | 0.62 | 4.7 | 0.5 |
| B | all_AND | all_AND | 0 | — | — | — | — | — | — |

**관찰**
- **베스트 = variant B / pullback_rebound**(회전 단순, sl5/tp10/mh15, trail 없음): pnl +3.12%, Sharpe **0.078**, Calmar 0.87, hit 27.8%.
- 재무게이트 변형(variant A `dino_test_pullback`, min_fin_score=3): **8거래뿐, hit 2.3%** — 컷오프가 과도하게 빡빡해 사실상 작동 불능.
- `all_AND`(두 룰 동시 충족)는 0~9거래로 표본 소멸 -> 무의미.
- variant A의 MA5 trail이 회전 철학을 무력화(아래 §5).

### 표본 강건성 (top_volume:100)

| variant | rule | n_trades | pnl% | Sharpe | hit% |
|---|---|---:|---:|---:|---:|
| B | pullback_rebound | 105 | 3.519 | **0.092** | 25.3 |
| A_nofin | dino_test_pullback | 291 | -0.115 | -0.010 | 23.7 |
| A | dino_test_pullback (fin) | 25 | -0.198 | -0.024 | 1.9 |

-> variant B 는 유니버스를 2배로 넓혀도(50->100) Sharpe 0.078->0.092, pnl +3.5%로 **부호/크기 유지**(소표본 우연 아님). 반면 variant A는 유니버스 확대 시 **음(-)으로 전환** — dino_test 룰엔 진짜 엣지가 없고, 작은 유니버스의 행운이었음.

### 재무 컷오프 민감도 (variant A dino_test, top50)

| min_fin_score | n_trades | pnl% | Sharpe | hit% |
|---:|---:|---:|---:|---:|
| 1 | 116 | 0.340 | 0.01 | 28.5 |
| 2 | 67 | -0.119 | 0.01 | 25.4 |
| 3 (기본) | 8 | 0.102 | -0.00 | 2.3 |
| no-fin | 135 | 0.582 | 0.03 | 31.4 |

-> **재무 컷오프를 풀수록 표본만 늘고 Sharpe는 0.01~0.03에 정체.** 디노 재무 4축 점수는 알파를 더하지 않는다(오히려 no-fin이 가장 높음). 책 시그니처 "디노 테스트" **부분 반박**.

---

## 3. 국면(BULL/BEAR/SIDEWAYS) 분해

국면 정의: KOSPI 20일 rolling 누적수익률 +-2% 임계(Elder/Minervini/문병로 동일 라벨). 분포: BULL 39.3% / BEAR 29.3% / SIDEWAYS 31.4%. 2022=BEAR 비중 높음.

### ENTRY 기준 per-trade (그 국면에서 *진입*한 거래의 결과)

| rule | 국면 | n | mean% | 승률 | shp_px |
|---|---|---:|---:|---:|---:|
| B pullback_rebound | ALL | 55 | 3.130 | 56.4% | 0.318 |
| B pullback_rebound | **BEAR** | 39 | **3.588** | 61.5% | 0.357 |
| B pullback_rebound | BULL | 7(소표본) | 2.624 | 42.9% | 0.261 |
| B pullback_rebound | SIDEWAYS | 9(소표본) | 1.539 | 44.4% | 0.182 |
| A dino_test (no-fin) | ALL | 135 | 0.527 | 48.1% | 0.099 |
| A dino_test (no-fin) | BULL | 25 | 2.562 | 64.0% | 0.444 |
| A dino_test (no-fin) | **BEAR** | 70 | 0.874 | 54.3% | 0.155 |
| A dino_test (no-fin) | SIDEWAYS | 40 | -1.351 | 27.5% | -0.361 |

> shp_px = pooled per-trade mean/std (연율화 안 함, 헤드라인 Sharpe와 척도 다름). 소표본=n<20.

**핵심 발견 — 약세장(BEAR) 방어**

| rule | entry-BEAR mean% | n | exit-BEAR mean% | n |
|---|---:|---:|---:|---:|
| **B pullback_rebound** | **+3.588** | 39 | +0.648 | 29 |
| A dino_test (fin) | +1.966 | 5(소표본) | -1.033 | 4(소표본) |
| A dino_test (no-fin) | +0.874 | 70 | +0.284 | 71 |
| *비교: Elder ema_pullback A* | *+3.01* | — | — | — |

- **variant B의 entry-BEAR +3.59%(n=39)는 Elder의 +3.01%를 상회** — "급등 후 -20~-40% 눌린" 자리가 약세장에서 저가매수 진입점으로 유효. **약세장 진입 방어는 진짜다.**
- 단 **exit-BEAR는 +0.65%로 약화**(약세장 한복판에 청산되는 거래는 주로 stop_loss). 즉 약세장에 *진입*하면 회복하나, 약세장에 *물려 청산*되면 본전권. Elder처럼 자기완결적 방어(+3%)는 아님.
- A dino_test(no-fin)는 **SIDEWAYS에서 -1.35%** 로 횡보장에 약함(눌림 후 추가 횡보 -> 잦은 트레일 손실).

---

## 4. 연도별 분해 (exit 기준)

| rule | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| B pullback_rebound mean% (n) | 2.15 (10) | 0.85 (17) | 9.52 (8) | 3.24 (16) | -4.02 (3) | 20.1 (1) |
| A dino_test no-fin mean% (n) | 1.13 (18) | 0.74 (30) | -0.31 (15) | 0.20 (35) | -0.19 (30) | 4.54 (7) |

- **연도별 표본이 매우 얕다**(B는 연 1~17거래). 단일 연도 수치(2023 +9.5%, 2026 +20%)는 통계적으로 무의미 — 회전 철학에 비해 신호가 너무 드물게 발생.
- A no-fin는 연 15~35거래로 그나마 표본 확보되나, **연도별 mean이 -0.31~+1.13%로 0 근처 진동**(엣지 없음 재확인).

---

## 5. 회전 철학(+10% 잦은 익절)이 한국 일봉에서 유효한가 — 청산 사유 분해

**variant B (pullback_rebound, sl5/tp10/mh15, trail 없음) — 55거래**

| 청산 사유 | 건수 | 평균 pnl |
|---|---:|---:|
| max_hold(15봉) | 20 | +2.6% |
| stop_loss(-5%) | 18 | -7.2% |
| **take_profit(+10%)** | 17 | **+14.7%** |

**variant A no-fin (dino_test, sl7/tp10/mh20/MA5-trail) — 135거래**

| 청산 사유 | 건수 | 평균 pnl |
|---|---:|---:|
| **trail_ma(MA5 이탈)** | 121 | **-0.5%** |
| take_profit(+10%) | 11 | +14.3% |
| stop_loss(-7%) | 3 | -10.3% |

**판정 — 회전 철학은 한국 일봉에서 약하게만 유효**
- **+10% 익절은 발동만 하면 좋다**(평균 +14.7%, 슬리피지로 목표 초과). 그러나 variant B에서 **전체 청산의 31%(17/55)만 +10%에 도달**. 손절(-7.2%, 33%)이 익절을 거의 상쇄 -> 순 per-trade +3.1%는 사실상 max_hold(+2.6%)의 기여.
- **variant A의 MA5 trail이 회전 철학을 죽인다**: 121/135(90%)가 trail_ma 청산(평균 -0.5%). +10% 도달 전 MA5 이탈로 끊겨 회전의 핵심(+10% 익절)이 11건뿐. 책 충실판(A)이 단순판(B)보다 못한 이유.
- 결국 **"작은 +10%를 빠르게 반복"** 은 한국 일봉에서 **(a) +10% 도달 빈도가 낮고 (b) 도달 전 손절/트레일에 더 자주 걸려** 의도대로 작동하지 않는다.

---

## 6. 비교 위치 — 어느 군에 속하는가

| 전략 | 군 | Sharpe(헤드라인) | BEAR per-trade |
|---|---|---:|---:|
| Elder ema_pullback A | 추세추종 생존 | **0.68** | +3.01% (방어OK) |
| Minervini volume_dryup B | 추세추종 생존 | **0.64** | — |
| Book15 ma5_pullback B | 추세추종(BULL의존) | 0.63 | — |
| 강창권 ma20 눌림 | 중간 | 0.44 | — |
| **dino_surge B pullback_rebound** | **펀더멘털 붕괴** | **0.078~0.092** | **+3.59%(entry)** |
| 문병로 value_composite_kr | 펀더멘털 붕괴 | ~0.1 | — |
| 홍용찬 value4_low | 펀더멘털 붕괴 | ~0.11 | — |

-> **dino_surge는 헤드라인 Sharpe로 명백히 펀더멘털 붕괴군**(문병로/홍용찬과 동일대). 추세추종 생존군과 0.6 vs 0.08의 격차.

-> **단, 약세장 진입 방어(entry-BEAR +3.59%)만큼은 펀더멘털군과 다르게 Elder급**. 이는 "디노 재무점수" 때문이 아니라 **"고점대비 -20~-40% 눌림 + RSI 저점반등"이라는 가격축 진입 발상** 덕분(재무게이트 끄면 더 좋음). 가격축 눌림 발상은 약세장 저가매수로서 가치가 있으나, **회전형 +10% 익절 청산이 그 엣지를 충분히 수확하지 못해** 헤드라인 성과로 연결되지 못한다.

---

## 7. CANDIDATE 적격 판정

**부적격 (NOT CANDIDATE).** 근거:

1. **Sharpe 생존 실패**: 헤드라인 연율 Sharpe 0.078~0.092 — 펀더멘털 붕괴군(~0.1) 수준. CANDIDATE 기준선(추세추종 0.44~0.68)에 미달.
2. **다국면 일관성 부족**: 약세장 진입 방어(entry-BEAR +3.59%)는 우수하나 SIDEWAYS 약세(B +1.5%/A -1.4%), exit-BEAR 약화(+0.65%). 국면 전반의 안정적 양(+)이 아님.
3. **표본 부족**: top50에서 베스트 룰조차 55거래(연 1~17), 50종목 중 23종목만 거래 -> 자본 활용률 극히 낮음(헤드라인 Sharpe가 낮은 직접 원인). 회전 철학(10~20종목 상시 회전)을 데이터가 뒷받침 못 함.
4. **책 시그니처 2개 모두 부분 반박**: (1) "디노 재무테스트"가 알파 무첨가(no-fin이 더 나음), (2) "+10% 회전 익절"이 도달 빈도 부족으로 미작동.

**부분 가치(후속 메모)**: 가격축 눌림 진입(-20~-40% + RSI 반등)의 **약세장 진입 방어 +3.59%** 는 단독 신호로는 Elder급. 향후 **Elder/Minervini의 추세 청산(trend_flip/trailing)과 결합**하면(디노식 +10% 익절 대신) 약세장 방어 진입군을 보강할 여지. 단 이는 디노 책 고유 기여가 아니라 가격눌림 일반의 효과.

---

## 8. 데이터 한계/근사 (명시)

- **이자보상배율(영업이익/이자비용)**: financial_statements에 이자비용 컬럼 없음 -> `debt_ratio>=200% AND 영업적자` 좀비 근사 하드필터로 대체.
- **유보율(>=1000%)**: 직접 컬럼 없음 -> ROE>0 가점으로 근사.
- **재료(축④ 뉴스/공시 촉매)**: 데이터 없음 -> 코드화 생략(카탈로그 §6).
- **봉차트 13패턴**: '바닥반전군'(아래꼬리 장대양봉 / 장대양봉+거래량)만 근사 코드화.
- **관리종목 제외 플래그**: 데이터 없음 -> top_volume 유니버스로 간접 회피.
- **디노점수 컷오프 16=만점 모순**(카탈로그 §6): 보수적으로 min_fin_score=3 기본, 민감도 1~3 스윕으로 보완.
- **연도/일부 국면 셀 표본<20**(소표본 표기): 단일 셀 수치는 참고용. 헤드라인/entry-BEAR(n=39)/전체기간(n=55/135)만 결론 근거로 사용.
- **재무 시계열**: 131종목 중 top_volume 유니버스에 33~57종목만 재무 매칭(LAG_DAYS=105 PIT 조인).

---

## 9. 살베이지 실험 (variant C: 디노진입 + Elder식 추세청산)

§6~7의 부분가치 메모("가격축 눌림 진입의 약세장 방어 +3.59% 는 Elder급인데, +10% 회전 익절이 엣지를 못 수확")를 직접 검증한 실험. **진입은 B(`pullback_rebound`)와 1:1 동일하게 고정하고, 청산만 Elder ema_pullback A 사상으로 교체**했다.

### 9.1 청산 사양 (variant C)
- 디노식 청산 전폐기: +10% 고정익절 / 타이트 손절(5%) / MA5 트레일 → 전부 삭제.
- Elder식 추세청산 모사: **초기손절 8% + EMA13 트레일링 스톱(수익권 진입 후 종가가 EMA13 하회 시) + 추세반전(EMA65 하향 기울기 AND 종가 EMA65 하회 = trend_flip) + max_hold 100거래일 + 고정익절은 tp=0.30 으로 사실상 추세에 맡김**.
- 구현: `scripts/run_dino_surge.py` `VARIANT_PARAMS["C"]`(exit_mode="trend", trail_ema=13, trend_ema=65) + `simulate_one_stock` 의 trend 분기. EMA 는 `ewm(span,adjust=False)` 누적이라 no-lookahead 유지(단위테스트로 가드).

### 9.2 헤드라인 메트릭 (top_volume:50, 2021~2026, `--variant C --all-modes`)

| variant | 진입 | 청산 | n_trades | pnl(평균) | **Sharpe(헤드라인)** | hit | avg_hold |
|---|---|---|---:|---:|---:|---:|---:|
| **B** | pullback_rebound | +10%익절/sl5/mh15 | 55 | **3.13%** | **0.078~0.092** | 56.4% | 14.2d |
| **C** | pullback_rebound | EMA13트레일+trend_flip+sl8/mh100 | 56 | **0.63%** | **-0.02** | 22.7% | **1.7d** |
| A dino_test(no-fin) | dino_test_pullback | +10%/sl7/mh20/MA5 | 135 | 0.53% | 0.099 | 48.1% | 4.1d |
| Elder ema_pullback A | (참고: 추세진입+추세청산) | EMA트레일/trend_flip | — | — | **0.68** | — | — |

- top100 동일 룰: n=112, pnl 0.46%, Sharpe 0.00, hit 20.5% (top50 와 동일 결론, 표본만 확대).

### 9.3 국면 분해 — entry/exit-BEAR (B vs C)

| rule | entry-BEAR mean% | n | exit-BEAR mean% | n |
|---|---:|---:|---:|---:|
| **B pullback_rebound** | **+3.588** | 39 | +0.648 | 29 |
| **C pullback+trend_exit** | **+0.029** | 40 | +0.029 | 40 |

- B 의 약세장 진입 방어(entry-BEAR +3.59%, Elder +3.01% 상회)가 C 에서 **+0.03% 로 소멸**. exit-BEAR 도 개선은커녕 B(+0.65%)보다 더 낮음.

### 9.4 청산 사유 분해 (variant C, top50, 56 sells) — 왜 실패했나

| reason | count | mean pnl% |
|---|---:|---:|
| trend_flip | **53** | **+0.038** |
| ema_trail | 1 | +8.60 |
| take_profit | 1 | +31.25 |
| stop_loss | 1 | -6.40 |

- **청산의 95%(53/56)가 trend_flip 으로, 진입 후 평균 1.7거래일 만에 거의 0% 손익으로 빠져나감.** 트레일(8.6%)·tp(31%)로 추세를 끝까지 탄 케이스는 단 2건.
- 원인: 디노 진입은 **고점대비 -20~-40% 눌림 = 본질적 역추세 저가매수**다. 이 시점의 EMA65 는 거의 항상 하향(기울기<0)이고 종가는 EMA65 아래에 있다. 따라서 진입 다음 봉에 `trend_flip` 조건(EMA65 하향 AND 종가<EMA65)이 즉시 충족되어 **반등이 전개되기도 전에 잘려나간다.** Elder 의 추세청산은 "추세 진입(EMA65 상향에서 산다)"을 전제로 설계된 것이라, **역추세 진입 신호와 구조적으로 양립 불가**.

### 9.5 최종 판정 — **여전히 부적격 (살베이지 실패)**

판정 기준 대비:
- ❌ 헤드라인 Sharpe 0.3+ 상승: **달성 실패** (0.078 → **-0.02**, 오히려 악화). Elder 0.68 과 dino B 0.078 의 두 끝 중 **dino B 보다도 아래로 추락**.
- ❌ entry-BEAR 방어 유지(≥+3%): **소멸** (+3.59% → +0.03%).
- ❌ exit-BEAR 개선(음수 탈출): 애초에 B 가 양수(+0.65%)였고 C 는 그보다 낮음(+0.03%) — 개선 없음.
- ✅ 표본 유지: 56 trades(B 55 와 동등) — 유일하게 충족.

**결론**: "디노식 +10% 익절이 약세장 방어 진입의 엣지를 못 수확한다"는 가설은 맞았으나, **그 대안으로 Elder식 추세청산을 붙이면 더 나빠진다.** 역추세 눌림 진입과 추세추종 청산은 사상이 정반대라 trend_flip 이 진입 직후 발동해 엣지를 완전히 파괴한다. dino_surge 에서 건질 부품(가격축 눌림의 약세장 방어)은 **추세청산이 아니라, 그 방어 구간을 충분히 보유하는 청산(예: 시간기반 N일 보유 / 목표 도달 또는 반등 소진까지 보유)** 과 결합해야 살아날 가능성이 있다. 이번 살베이지(추세청산 결합)는 **부적격 확정**. CANDIDATE 판정(§7)은 변동 없음.

> 실행 커맨드: `python scripts/run_dino_surge.py --variant C --all-modes` · `--variant C --mode single --rule pullback_rebound --top-n 100` · `python scripts/regime_split_dino_surge.py`(variant C 포함). 단위테스트 `tests/books/test_dino_surge_daily.py` 32 passed(기존 27 + variant C 5 신규).
