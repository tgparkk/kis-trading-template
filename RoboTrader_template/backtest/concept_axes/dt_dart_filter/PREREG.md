# 사전등록 — daytrading 거르기 층 A: 공시 재료 다음날 추격 금지(lag0) 확인 검정

상태: 초안(동결 전)

- 작성 2026-10-10(토) · Task 12 Step 1(초안) · 코드 기준 = 브랜치 `research/dt-dart-filter` HEAD `fc92bb5`
- 다음 순서: critic 1패스 → 🔒 사장님 동결(B 사전등록과 한 번에 · 스펙 §6) → 동결 커밋 → `frozen_consts.py` 두 값 커밋 → REGISTRY `DF1` 등재
- 규범 순서: 사장님 결정(§0) > 스펙 `docs/superpowers/specs/2026-10-10-daytrading-filter-layer-design.md`(main `75326bc`) > 이 문서 > 코드
  - 이 문서의 값은 코드(`settings.py` 등)에서 옮겨 적었다.
  - 스펙과 코드가 다른 곳은 §2-6 에 모두 적었고, 이 문서는 **코드(= §11 이 고정하는 값)** 를 따른다.
- 출처 표기
  - `(settings.py: NAME)` = 동결 상수
  - `(spec §x)` = 스펙 절
  - `(Ruling: …)` = SDD 원장 `progress.md` 의 판정 줄
  - `(plan 다른 점 n)` = 구현 계획 «스펙과 다른 점» n번
  - `(code: 파일:함수)` = 상수가 아닌 코드 규칙
- 🔴 라이브 봇 코드 0줄 · DB 는 SELECT 전용(백필 스크립트만 예외 · 끝남) · 실제 표식×수익 결합은 `run.py --stage open` 1회뿐

---

## §0. 사장님 결정 (말 그대로, 2026-10-10 · spec §0)

| 질문 | 답 |
|---|---|
| (발단) | 「daytrading 에 대해 이야기하죠. 퀀트와 뉴스데이터 활용이 필요하다고 생각합니다.」 |
| 어디에 쓰나 | 「거르기 — 나쁜 후보 빼기」 |
| 근거 수준 | 「과거 검정 통과 후 적용」 |
| 재료 | 「공시 악재 — 과거 확인 검정」 + 「수급·언론 뉴스 — 오늘부터 기록」 → 뒤에 「B 는 수급 4종만」(뉴스는 기존 LLM shadow·TN1·테마 층에 맡김) |
| 검정 구간 | 「뭐가 좋을지 모르겠음」 → 쉬운 설명 뒤 「① 으로 진행」(아무도 안 본 2021~2024-03) |
| 기록 방식 | 「DB 봉인 이 어떤 의미인가요?」 → 「뭐가 더 확실히 조사할수 있는건가요?」 → 「② DB 봉인으로」 |
| 과거 시총 없음 | 「ⓐ 시총 조건 빼고 안 본 구간 검정」 |
| 설계 §1·§2 | 「좋아요 — 다음 절로」 |
| (중간) | 「근데 아마 문서로 다음에 할일들을 적어놓은게 있는데 문서한번보고 진행해줘요」 → `NEXT_SESSION.md`·10-17 안건 확인 |
| 09-24 결정과 충돌 | 「그렇게 진행」 = 09-24 「후보 층 재시도 안 함 · 더 찾지 않음」을 **이 건에 한해 면제** · B 는 수급 4종만 |
| 설계 §3·§4 | 「고수랑 논의하고 작성하세요」 → 전문가 패널 3인(spec §8) |
| A 수정안 | 「수정안으로」(돌파일 당일 공시 · 경영권분쟁 제외 · 도구 교체 · 시총 대리 · 정지 처리) |
| B 시작 시점 | 「늦출 필요 없다고 생각하는데 , 의견좀요」 → 관리자 권고 변경 → 「그렇게 진행」(지금 준비 · 점검 통과 뒤 봉인 ≈10-26~28) |
| 범위 밖 | 「10-19 전에 점검」 = 보유 중 권리락 «가짜 손절» 조사(spec §9) |

**면제 문장(spec §5)**: 09-24 「후보 층 재시도 안 함 · 현행 유지 · 더 찾지 않음」을 **daytrading A·B 에 한해** 면제한다(사장님 10-10 「그렇게 진행」). 테마 층 면제 선례대로 `backtest/concept_axes/REGISTRY.md` 에 등재한다.

- 등재 가족: A 주 검정 **1개**(이 문서) · B 주 검정 4개(별도 사전등록).
- 🔴 총계 충돌: SR1·TN1·테마 층·B(DF2)와 겹친다. 나중에 머지되는 쪽이 총계를 다시 센다(REGISTRY 규칙 3).
- 09-24 결정 「검정 도구 교정을 먼저」는 지킨다. 교정에서 떨어진 「종목 묶음 순열」은 쓰지 않는다(spec §3-5).

---

## §1. 가설

**검정 문장**: 「돌파일(스캔일) 당일에 3태그 원공시(유상증자 · 최대주주변경 · 소송·횡령(경영권분쟁 제외))가 난 daytrading 후보(대리 소형)는, 같은 날 다른 후보보다 다음날 매수 → 청산까지의 net 수익이 낮다.」

- δ = 날짜 고정효과 회귀에서 표식 계수(같은 날 다른 후보 대비 %p)(spec §3-5)
- H0: δ ≥ 0 · H1: δ < 0 · **단측** · α = 0.05 `(settings.py: ALPHA)`
- 주 검정 1개(가족 m = 1)다. 태그별·창별·크기별 결과는 모두 인쇄만 하고 라벨을 바꾸지 않는다(§7-2).
- 왜 lag0 인가: 2024-03~(오염 구간)에서 돌파일 당일 공시(lag0)에 효과가 몰려 있었다(n82 −2.49% vs 1~4일 전 공시 n137 +0.57% · spec §2-2). 이 선택은 오염 구간을 보고 정했다. 새 창(2021-02~2024-03)은 보지 않았으므로 «학습 → 확인» 순서다(spec §5). 본 것의 전체 목록은 §10 에 있다.
- 이 검정은 «필터를 켤지»를 정하지 않는다. 통과는 §8 L-1~L-4 의 출발 조건일 뿐이다.

---

## §2. 표본

### 2-0. 동결 값 한눈에 (전부 `settings.py`)

| 항목 | 값 | 출처 |
|---|---|---|
| 스캔 창 | 2021-02-01 ~ 2024-03-12 | `(settings.py: SCAN_START, SCAN_END)` · spec §3-2 |
| 가격 창 | 2021-01-04 ~ 2024-04-30 | `(settings.py: PX_START, PATH_END)` |
| 공시 창 | 2021-01-01 ~ 2024-03-12 | `(settings.py: FILING_START)` · `SCAN_END` |
| 백필·완결 판정 유형 | A · B · I | `(settings.py: BACKFILL_TYPES)` · plan 다른 점 4 |
| 대리 적합 창 | 2024-03-13 ~ 2026-09-23(가격은 2023-12-01 부터) | `(settings.py: FIT_START, FIT_END, FIT_PX_START)` |
| 태그 | 유상증자 · 최대주주변경 · 소송·횡령(U+00B7) | `(settings.py: TAGS_LAG0, MGMT_TAG)` |
| 거래대금 하한 | 10억 원 | `(settings.py: MIN_TV)` |
| 대형 기준 | 시총 ≥ 5,000억 원 | `(settings.py: LARGE_CAP)` |
| 대리 소형 | p_L < 0.5(엄격) | `(settings.py: PL_CUT)` |
| 대리 거래대금 평균 | 20행 | `(settings.py: TV_AVG_BARS)` |
| 체결 상한 | 스캔일 종가 × 1.03 | `(settings.py: BAND_UP)` |
| 비용 | 0.25%p / 로트 | `(settings.py: COST_PCT)` |
| 판정 | 단측 α 0.05 · δ̂ ≤ −0.4%p · n₁ ≥ 100 | `(settings.py: ALPHA, DELTA_MAX, N1_MIN)` |
| 2원 클러스터 블록 | 20거래일 | `(settings.py: BLOCK_TD)` |
| 시드 | 20261010 | `(settings.py: SEED)` |
| 가짜 게이트 | 400개 · 양측 p < 0.10 · 거부율 [0.07, 0.13] · 유효 복제 ≥ 95%(=380) | `(settings.py: N_FAKE, FAKE_P, FAKE_LO, FAKE_HI, FAKE_VALID_FRAC)` |
| MDE 승수 | z.95 + z.80 = 1.6448536… + 0.8416212… = 2.48647 | `(settings.py: Z_ALPHA, Z_POWER)` |
| 꼬리 손실 인쇄 | ret ≤ −15% | `(settings.py: TAIL_LOSS)` |
| 룰 값(라이브 어댑터와 같아야 함) | 고가 15봉 · 거래량 20봉 평균 × 2.0 · lookback 60봉 | `(settings.py: HIGH_WINDOW, VOL_LOOKBACK, VOL_MULT, LOOKBACK_BARS)` |

### 2-1. 창과 달력

- 스캔일 = 돌파일 D. 2021-02-01 은 20봉 거래량 평균이 온전한 첫날이다(spec §3-2).
- 거래일 달력 = `daily_prices` 의 의사티커 `KOSPI` 행(`replayer.loader.load_trading_calendar`) · 2021-01-04 ~ 2024-04-30.
- 가격 창 끝 2024-04-30 은 2024-03-12 스캔 후보의 10거래일 보유를 덮기 위한 것이다. 이 구간은 청산 경로로만 쓴다.

### 2-2. 후보 규칙 — 라이브 룰에서 시총 조건만 뺀다

- 라이브 어댑터 `Daytrading3MethodsBreakoutScreenerAdapter` 의 룰을 그대로 쓰고, `base_filter` 의 시총 조건만 뺀다(`universe.NoCapDaytradingAdapter` · spec §3-2 · 사장님 「ⓐ」).
  - 거래대금 ≥ 10억 `(settings.py: MIN_TV)`. 거래대금 = 종가 × 조정 거래량이다(`replayer.loader` · 라이브 `quant_daily_reader` 와 같은 계산).
  - 종가 ≥ 직전 15봉 고가 최대 `(settings.py: HIGH_WINDOW)`
  - 거래량 ≥ 직전 20봉 평균 × 2.0 `(settings.py: VOL_LOOKBACK, VOL_MULT)`
  - 양봉
  - 불가능봉 가드(`strategies/_rule_screener_base.py::_prepare_frame` · `utils/data_sanity.py`)
  - 점수 = 거래량 배수 · lookback 60봉 `(settings.py: LOOKBACK_BARS)`
- 유니버스는 시총이 결측인 행도 담는다. 2021~2023 은 시총이 거의 전부 결측이다(spec §2-3).
- 유니버스 날짜는 `max(date ≤ 스캔일)` 폴백이다(`replayer.scan.eligible_for_dates`).
- 🔒 **라이브 어댑터의 `default_params()` 값이 위 settings 값과 다르면 실행을 거부한다**(`universe.check_adapter_params` · `require_frozen` 과 `scan_window` 가 부른다 · Ruling: Final I4).
- **순위 절단은 없다.** 룰을 통과한 후보 전부가 원장에 들어간다(`max_candidates=None`). 라이브의 자리 K=10 · 하루 5건은 이 검정에 없다. 그 효과는 L-1(§8)이 본다.
- 거래량은 읽기 계층이 조정한 값이다. 가격(OHLC)은 `daily_prices` 에 저장된 값을 그대로 쓴다(한계 §9).

### 2-3. 시총 대리 p_L — 🔒 계수 동결

- 목적: 2021~2023 시총 결측 때문에 대형주가 대조군에 섞이는 교락을 막는다(spec §3-2 · 퀀트 2).
- 특징(`proxy.add_proxy_features`)
  - x1 = log(스캔일 D 를 포함한 직전 20**행** 평균(종가 × 조정 거래량)) `(settings.py: TV_AVG_BARS)`. 행 기준이다. 정지 행(거래량 0)도 한 행으로 센다.
  - x2 = log(D 종가)
- 모형: p_L = 1 / (1 + exp(−(b0 + b1·x1 + b2·x2))). 선형 예측값은 ±35 에서 자른다.
- 적합: 이미 본 구간 2024-03-13 ~ 2026-09-23 에서 시총 > 0 ∧ x1·x2 유한인 같은 규칙 후보를 쓴다. y = 1{시총 ≥ 5,000억}. 수익은 쓰지 않는다.
  - 방법은 numpy IRLS 다. 입력에 비유한값이 있으면 ValueError, 100회 안에 수렴하지 못하거나 계수가 비유한이면 RuntimeError 로 멈춘다(Ruling: Task 4).
- 🔒 **동결 계수**(`results/proxy_coef.json` · md5 `a1032ffd1cf7092715387ea0502a4c54`)

  | 항목 | 값 |
  |---|---|
  | (b0, b1, b2) | (−30.0351489998722, 0.6827447089973862, 1.4550171146265396) |
  | n · 대형 | 26,129 · 7,902 |
  | AUC(전체) | 0.9198 |
  | 연도별 AUC | 2024 0.9077 · 2025 0.9172 · 2026 0.9332 |
  | p ≥ 0.5 정확도 | 0.8647 |
  | 적합 커밋 | `793e984`(코드) → 결과 커밋 `ae766ce` |

- 동결 뒤에는 대리를 다시 적합하지 않는다. `proxy` 단계는 `PREREG_FROZEN_BLOB` 이 채워져 있으면 거부한다. `build`·`seal`·`open` 은 `PROXY_COEF_MD5` 가 비어 있거나 md5 가 다르면 거부한다(Ruling: Task 9 I3).
- **주 표본 = p_L < 0.5**(엄격 부등호) `(settings.py: PL_CUT)`. p_L 이 NaN 인 행(특징 비유한)은 주 표본에서 빠진다.
- 시총이 없는 해의 대리 분류가 안정적인지는 봉인 보고서의 «연도별 p_L<0.5 비율 · NaN 수»로 확인한다(§6). 이 비율은 수익과 무관하다.

### 2-4. 원장 상태(로트 1개 = 후보-일 1개)

`lots.simulate_candidate` 가 후보마다 상태 1개를 준다.

| status | 뜻 |
|---|---|
| `no_scan_bar` | 스캔일 봉 없음 |
| `no_next_day` | 달력에 다음 거래일 없음 |
| `halt_entry` | 진입일(D+1) 정지 = «진입 불가». 표본에서 빠지고 팔별로 따로 센다(spec §3-4 · §7-2) |
| `no_bar` | 진입일 봉 없음 · 원본 시가 NULL/≤0(`load_bad_open`) · 시가 ≤ 0 |
| `no_fill` | 밴드 미체결(§4-1) |
| `filled` | 체결 — 분석 대상 |

### 2-5. 분석 표본 조립(순서 고정 · `sample.analysis_frame`)

1. `status == filled`(시가 체결 ∪ 상한 체결 · plan 다른 점 1)
2. p_L < 0.5 · NaN 제외
3. 종목 → 거래일 순번으로 정렬한 뒤 **에피소드 첫 행**만 남긴다.
   - 1·2 로 거른 **뒤** 다시 계산한다(plan 다른 점 2 · `run_calib.episodes`).
   - 같은 종목의 직전 남은 행과 거래일 순번 차가 1 을 넘으면 새 에피소드다.
4. x = 1{(종목, 스캔일) ∈ lag0 표식}(§3)
5. y_sl = ret_sl − 0.25 · y_tp = ret_tp − 0.25(%p · `(settings.py: COST_PCT)`)
6. day = 2021-01-04 를 0 으로 하는 거래일 순번 · block = day // 20 `(settings.py: BLOCK_TD)`
7. quint = 이 표본 **전체**의 p_L 5분위(`rank(method="first")` → `qcut` 5 · plan 다른 점 5). 가짜 게이트에만 쓴다.

회귀는 여기서 한 번 더 거른다(§5-1): y 가 유한한 행 중에서, 그날 표식 ≥ 1 ∧ 대조 ≥ 1 인 날만 쓴다.

### 2-6. 스펙과 코드가 다른 점(이 문서는 코드를 따른다)

| # | 스펙 문구 | 코드(= 이 문서) | 근거 |
|---|---|---|---|
| 1 | «체결 가능(band_ok)만»(§3-2) | band_ok = §3-4 체결 규칙(시가 체결 ∪ 상한 체결). 원장 `band_ok`(시가만)가 아니다 | plan 다른 점 1 |
| 2 | «에피소드 첫 행 정의 그대로»(§3-2) | 체결 ∧ 대리 소형으로 거른 **뒤** 다시 계산 | plan 다른 점 2 |
| 3 | 10거래일 만기 | 보유일 탐침(SellProbe) 없이 KOSPI 달력 `open_phase` 만 | plan 다른 점 3 |
| 4 | 백필 유형(§3-1) | A(정기공시)를 더한 A·B·I. 생존자 (ii) 계산용 | plan 다른 점 4 |
| 5 | «같은 날 같은 대리 크기 5분위»(§3-5) | 5분위는 표본 전체 p_L 기준(날짜 안 아님). 같은 날 · 같은 분위 풀에서 뽑는다 | plan 다른 점 5 |
| 6 | «log 20일 평균 거래대금»(§3-2) | 20**행** 평균(종가 × 조정 거래량). 정지 행 포함 | `proxy.add_proxy_features` |
| 7 | 생존자 (i) «원공시 중» · (ii) «상장사 중»(§3-6) | (i) 공시 단위 · (ii) 회사 단위 · 코넥스·상장 전 공시 제외 · (ii) 는 회사 공시 하나라도 누락이면 누락 | Ruling: Final I1 |
| 8 | 라벨 δ̂ ≤ −0.4 · 두 규칙 p < 0.05(§3-7) | δ̂ 문턱은 **손절 우선 판에만** 건다. p 는 두 판 모두 | `run.label` · 사장님 질문 Q2 |
| 9 | 「역방향」 · 그 밖(n₁<100 포함) = 판별 보류(§3-7) | n₁ < 100 검사가 「역방향」보다 **먼저**다. n₁ < 100 이면 역방향도 판별 보류 | `run.label` · 사장님 질문 Q3 |
| 10 | 태그별 3개 인쇄(§3-8) | **코드가 계산하지 않는다.** 이 문서 §5-6 절차를 개봉 뒤 verifier 가 계산(plan Task 13 Step 5) | 코드 결함 · 사장님 질문 Q4 |
| 11 | 연도별(2021/22/23)(§3-8) | 표본에 있는 해 전부(2024-01-01 ~ 03-12 포함 4개) | `run.stage_open` |
| 12 | 봉인 «표식 비율»(§3-6) | 따로 찍지 않는다. n₁ · n₀(원시·유효)로 계산할 수 있다 | `run.seal_report_lines` |
| 13 | 생존자 공시 창 | 스캔 창(2021-02-01 ~ 2024-03-12)의 공시만. 공시 창 시작(2021-01-01)이 아님 | `run._survivorship` |

---

## §3. 표식(주 검정)

### 3-1. lag0 정의

- **lag0** = 스캔일 D 의 `rcept_dt` 에 그 종목의 3태그 원공시가 1건 이상 있다(spec §3-3 · `tags.window_marks(back=0)`).
- 판정 기준일은 스캔일까지다. D 장 마감 뒤 공시도 D+1 아침 매수 전에 볼 수 있으므로 미래 참조가 아니다. 접수 «시각»은 없다(spec §2-3).
- 🔴 **주말·공휴일 접수 공시는 lag0 이 아니다.** 스캔일은 거래일이므로 비거래일 `rcept_dt` 는 어떤 스캔일과도 같지 않다. 이런 공시는 W5·W20 에는 들어간다.
- 표식 출처: `dart_disclosures`(stock_code 있는 행) · `rcept_dt` 2021-01-01 ~ 2024-03-12 · DB 에 있는 모든 유형(백필 = A·B·I).
- build 가 표식 파일 `marks_lag0.csv` · `marks_w5.csv` · `marks_w20.csv` 를 수익 원장과 **따로** 쓴다. 표식 파일은 3태그 합집합이다.

### 3-2. 태그 — 09-26 동결 `dart_tags.tag_of` 그대로(blob `ca3ff3d` · §11)

- 정규화: 공백 제거 → 가운뎃점 6종을 `·`(U+00B7)로 → 앞머리 `[…]` 를 접두로 떼어 냄.
- 정정 제외: 접두에 `기재정정`·`첨부정정`·`첨부추가`·`정정` 이 있으면 원공시가 아니다(`is_corr` → 표식 안 됨).
- 정정 외 접두가 있으면 → 기타. 본문에 `(자회사의주요경영사항)`·`(종속회사의주요경영사항)` 이 있으면 → 기타.
- 정규식(태그 표 순서대로 대조 · 본문 앞머리 · 첫 일치가 태그):
  - 유상증자: `^(주요사항보고서\()?유(무)?상증자결정` — 🔴 **유무상증자결정도 포함**
  - 최대주주변경: `^(최대주주변경(\(|$)|최대주주변경을수반하는주식양수도계약체결|최대주주등소유주식변동신고서\(최대주주변경시\)|경영권변경등에관한계약체결)`
  - 소송·횡령: `^((주요사항보고서\()?소송등의제기|횡령·배임(혐의발생|사실확인))`

- **경영권분쟁 제외**: 소송·횡령 중 본문에 `경영권분쟁` 이 든 공시(`flags["mgmt_dispute"]`)는 표식하지 않는다(spec §3-3 · `tags.is_lag0_tag`).
- 다른 4태그(CB/BW/EB · 자기주식취득 · 공급계약 · 잠정실적)는 표식이 아니다. 그 공시가 난 후보는 대조군에 남는다.

### 3-3. 보조 창(인쇄만)

- W5 = `back=4` · W20 = `back=19`(`tags.window_marks`). 스캔일 cal[i] 에 대해 `rcept_dt` ∈ [cal[i−back], cal[i]] 이다. 이 범위는 달력일이라 사이 주말·공휴일 공시도 들어간다.

### 3-4. 공시 데이터 완결(🔒 build 전제)

- 백필 2021-01-01 ~ 2024-03-12 · 유형 A·B·I(spec §3-1 · Task 11 완료 · `results/backfill_check.json` · §10-3).
- 완결 판정 = 하루 × 유형 칸마다 지름길 없이 판정한다(`daycheck` · Ruling: Task 3). 칸이 완결이려면 둘 중 하나여야 한다.
  - (a) raw 전 페이지 status 000 ∧ 항목 수 = total_count ∧ rcept_no 중복 없음 ∧ DB 소속 수 + 다른 유형 중복 = total_count ∧ 같은 날·같은 유형 DB 여분 행 0
  - (b) 013(무자료) 증거 ∧ 그날 그 유형 DB 행 0
- 결과: 칸 3,501 · 미완결 0 · `complete: true`.
- build 는 아래 셋 중 하나라도 어긋나면 거부한다(`run.check_backfill_report` · Ruling: Final 동결 전 수정 묶음).
  - `backfill_check.json` 이 커밋돼 있고 바뀌지 않았다.
  - `complete == true`
  - 창 = [2021-01-01, 2024-03-12] · 유형 = A·B·I

---

## §4. 결과(daytrading 매매 흉내 · spec §3-4)

### 4-1. 체결(진입일 = 스캔일 다음 거래일 D+1)

- 상한 hi = D 종가 × 1.03 `(settings.py: BAND_UP)`(`theme_rank.bandfill.band_fill`)
  - D+1 시가 ≤ hi → **시가 체결**(basis D_open)
  - 시가 > hi ∧ 저가 ≤ hi → **상한 체결**(가격 hi · basis upper)
  - 그 밖 → 미체결(`no_fill`)

### 4-2. 청산(`ledger8.exitsim8` daytrading 규칙 · ExitRules(tp 0.10, sl 0.10, max_hold 10))

- 수익률 비교는 (가격 − 진입가) / 진입가 다. 익절 ≥ +10% · 손절 ≤ −10% 다(라이브 `position_monitor` 와 같은 식).
- **진입일(k=0)**
  - 시가 체결: 진입일 봉의 고가·저가 터치를 본다.
  - 상한 체결: 체결 시각을 모르므로 진입일 터치를 보지 않는다(`entry_day_touch_skipped` 표시).
- **k ≥ 1, 09:00(시가 단계)**
  - k ≥ 10 → 만기 청산(그날 시가)
  - 시가 ≥ +10% → 갭 익절(시가)
- **k ≥ 1, 시가 뒤**
  - 시가 ≤ −10% → 갭 손절(시가)
  - 저가 ≤ −10% → 손절(진입가 × 0.9)
  - 고가 ≥ +10% → 익절(진입가 × 1.1)
- 봉이 없는 날(가격 행 자체가 없음 · 정지 아님)은 건너뛴다. 그사이 만기에 닿으면 다음 봉 시가에 청산한다.
- 경로는 k ≥ 10 인 첫 봉에서 끝난다(`candidate_ledger.run.build_path`). 보유일 탐침은 쓰지 않는다(plan 다른 점 3).

### 4-3. 동시 터치 — 두 규칙(spec §3-4)

- 같은 봉에서 손절가·익절가에 둘 다 닿으면(`sl_tp_same_bar` 표시):
  - **손절 우선 판** ret_sl = −10%
  - **익절 우선 판** ret_tp = +10.0%
- 동시 터치가 아닌 로트는 ret_tp = ret_sl 이다.

### 4-4. 거래정지(spec §3-4 · `lots`)

- 정지일 = 가격 행이 있고 거래량 ≤ 0 또는 결측인 날(`lots.halt_dates`).
- 진입일 정지 → `halt_entry` = «진입 불가». 분석 표본에서 빠지고 개봉 때 팔별로 따로 센다(§7-2).
- **보유 중 정지** → 보유 중 첫 정지일 «전»까지 평소 규칙으로 돌린다. 그때까지 안 닫혔으면 정지 뒤 첫 봉의 **시가로 무조건 청산**한다(`halt_resume` · 밴드 안 재개여도 계속 보유하지 않음 · Ruling: Final I2).
- 창 끝(2024-04-30)까지 재개 봉이 없으면 → 마지막 값(종가) + «미해소».
- `halted_in_path` = 진입일 다음날부터 청산일까지(미해소면 경로 마지막 날까지) 정지일이 하루라도 있으면 참(Ruling: Task 6). 인쇄용이며 판정과 무관하다.

### 4-5. 미해소 · 비용

- 미해소(경로 안에서 안 닫힘) = 마지막 종가로 평가하고 «미해소»로 표시한다. 수익은 유한하므로 표본에 남는다.
- 비용: 로트마다 0.25%p 를 한 번 뺀다 `(settings.py: COST_PCT)`. 모든 행에 같으므로 δ 는 변하지 않는다. net 은 절대 손익 인쇄용이다(spec §3-4).

---

## §5. 통계

### 5-1. 날짜 고정효과 회귀(`stats.fe_regression`)

- 쓰는 행 = y 유한 ∧ 그날 표식 ≥ 1 ∧ 대조 ≥ 1 인 날(`stats.both_arm_days_mask`)
- x̃ · ỹ = 날짜 안 평균을 뺀 값. β = Σx̃ỹ / Σx̃². δ̂ = β(%p)
- 영향 함수 ψ_i = x̃_i(ỹ_i − βx̃_i) / Σx̃²

### 5-2. 표준오차

**종목 CR1**(Ruling: Task 7 · Cameron–Miller / Stata `areg` 관례)

- V_CR1 = c · Σ_g(Σ_{i∈g} ψ_i)²
- c = G/(G−1) · (N−1)/(N−K)
  - G = 종목 수
  - N = 쓰는 행 수(날 거른 뒤)
  - **K = 1 + 날짜 수**: x 계수에 흡수된 날짜 고정효과를 더해 센다.
- N−K ≤ 0 이거나 G < 2 면 SE = NaN 이다.
- 참조 분포는 정규다. 단측 p1 = Φ(β/SE) · 양측 p2 = 2(1 − Φ(|β/SE|))

**2원 클러스터**(종목 × 20거래일 블록)

- V_2w = V_종목 + V_블록 − V_종목×블록
- 각 성분은 자기 G(종목 수 · 블록 수 · 비어 있지 않은 종목×블록 칸 수)와 같은 (N−1)/(N−K) 를 쓴다.
- V_2w ≤ 0 이면 max(V_종목, V_블록) 을 쓴다.
- 참조 분포는 t(G_블록 − 1) 이다(09-26 `stats_binary` 선례).
- 블록 = (2021-01-04 를 0 으로 한 거래일 순번) // 20

본 분석에는 무작위가 없다. 같은 원장이면 같은 결과다.

### 5-3. 도구 게이트 — 가짜 표식 400개(개봉 «전» · seal 단계 · `gate.fake_gate`)

**블라인드**: 실제 표식 행(x=1)은 [day, quint, stock] 만 남기고 수익을 읽지 않는다. 회귀는 대조 행(x=0)만 쓴다.

**풀 만들기**

- 풀 = 대조 행 중 실제 표식이 하나라도 있었던 종목을 **전부 뺀** 행.
- 인덱스 세 가지: (day, quint) · day · (stock, day)

**복제 i (i = 0…399)**

- 난수 = `numpy.random.default_rng([20261010, 7, i])` `(settings.py: SEED)`. 솔트 7 은 «새 시드» 요구(spec §3-5)를 채운다.
- 실제 표식 행을 표본 순서(종목코드 → 거래일)대로 돈다. 각 행 r 에서:
  1. 같은 복제 안에서 r 의 실제 종목이 이미 가짜 종목 h 에 대응돼 있고, (h, r.day) 행이 풀에 있으며 아직 안 뽑혔으면 → 그 행을 쓴다.
  2. 아니면 → 같은 (day, quint) 풀에서 안 뽑힌 행 중 균등하게 1개를 뽑는다.
  3. 그 풀이 비면 → 같은 day 의 아무 분위에서 뽑는다.
  4. 그래도 없으면 → 그 표식은 건너뛴다(셈은 남긴다).
  - 2·3 에서 새로 뽑으면 r 의 종목 → 뽑힌 종목으로 대응을 고친다.
- 한 복제 안에서는 **비복원**이다. 이미 뽑힌 행은 다시 안 뽑는다(Ruling: Final I3).
- 가짜 x 로 대조 표본에 §5-1·5-2 를 그대로 돌린다. 결과 변수는 **y_sl 만** 쓴다.

**유효 복제 규칙**(Ruling: Final I3 · 관리자 판단 · 사장님 질문 Q1)

- 도구별 유효 복제 = β 와 그 도구의 양측 p 가 둘 다 유한한 복제.
- 거부율 = 유효 복제 중 양측 p < 0.10 인 수 / 그 도구의 유효 복제 수 `(settings.py: FAKE_P)`. NaN p 를 «비거부»로 세지 않는다.
- 문턱 = ceil(0.95 × 400) = **380** `(settings.py: FAKE_VALID_FRAC)`

**도구 선택 순서**(spec §3-5)

| 순서 | 조건 | 결과 |
|---|---|---|
| 1 | CR1 유효 < 380 | 도구 `fail` · 사유 `degenerate`(2원이 괜찮아도) |
| 2 | CR1 거부율 ∈ [0.07, 0.13](양끝 포함) | 도구 **CR1** |
| 3 | 2원 유효 ≥ 380 ∧ 2원 거부율 ∈ [0.07, 0.13] | 도구 **2원** |
| 4 | 2원 유효 < 380 | 도구 `fail` · 사유 `degenerate` |
| 5 | 그 밖 | 도구 `fail` · 사유 `out_of_band` → 라벨 「판정 불가(도구)」 |

**함께 내는 값**(CR1 유효 복제만으로)

- SD_null = 가짜 β 의 표준편차(ddof 1)
- 평균 SE_CR1
- 하측 거부율(단측 p1 < 0.05)
- 평균 가짜 n₁
- 건너뛴 수

### 5-4. MDE

- MDE_null = 2.48647 × SD_null · MDE_SE = 2.48647 × 평균 SE_CR1(`stats.mde`)

### 5-5. 날짜 거르기와 n₁(Ruling: Task 9 I1)

- **n₁(유효)** = 회귀가 실제로 쓰는 표식 행 수다. y_sl 이 유한하고 그날 대조도 있는 날의 표식 행만 센다(`run.effective_n1`).
  - 봉인 보고서와 라벨이 같은 정의를 쓴다. 라벨의 n₁ 은 개봉 때의 `fe_sl.n1` 이다.
- 원시 개수(날 거르기 전)는 따로 «원시»로 표시한다.
- 봉인 때 표식 행의 y_sl 유한 여부를 읽는다. y_sl 이 NaN 인 경우는 봉 없음 · 경로 없음뿐이고, 원장 상태와 같은 정보다. 수익 값 자체는 아니다.

### 5-6. 태그별 3개 + Holm m=3(보조 · 라벨 불변 · spec §3-8)

🔴 현재 코드(`run.stage_open`)는 이 계산을 하지 않는다. 「있음(−)」일 때 자리표시 한 줄만 찍는다. 아래 절차는 이 초안의 **제안**이며 사장님 질문 Q4 로 확정한다.

1. 태그 t ∈ (유상증자 → 최대주주변경 → 소송·횡령(경영권분쟁 제외)) 마다 표식_t 를 만든다. 표식_t = §3 과 같은 규칙에서 태그를 t 하나로 한정한 lag0 표식이다.
2. 표본은 §2-5 와 같다.
   - x_t = 1{표식_t}
   - 다른 태그로만 lag0 표식이 붙은 행은 그 태그 회귀에서 뺀다. 대조 = 3태그 lag0 표식이 전혀 없는 행이다.
   - 두 태그 이상이 붙은 행은 해당 태그마다 표식으로 센다.
3. §5-1·5-2 를 **봉인 때 고른 도구**로 돌린다. 손절 우선 판 단측 p_t 를 얻는다.
4. Holm m = 3: `stats.holm([p_유상증자, p_최대주주변경, p_소송·횡령])`.
   - 동점이면 위 고정 순서를 따른다(안정 정렬).
   - 조정 p < 0.05 인 태그를 「그 태그 기여 있음」으로 **해석**한다.
   - **해석은 주 라벨이 「있음(−)」일 때만** 한다. 그 밖이면 숫자만 인쇄하고 「해석 안 함」으로 적는다.

---

## §6. 봉인 보고서(개봉 전 커밋 · 표식×수익 결합 0 · spec §3-6)

`run.stage_seal` 이 `seal.json` 과 `sealed_report.md` 를 쓴다. 보고서는 아래를 이 순서로 담는다.

1. n₁(유효) · 대조(유효) n₀
2. 원시 개수: 표식 원시 · 대조 원시 · n₁ 원시 연도별
3. 연도별 후보 중 p_L < 0.5 비율 + NaN 수. 원장 전체 · 체결 무관 · 수익 무관
4. SD(대조 행 net · 손절 우선 / 익절 우선). 대조 행만 쓴다.
5. 가짜 게이트
   - CR1 거부율 · 2원 거부율 → 도구 · 사유
   - 유효 n_valid / 400(문턱 380) · 2원 유효 · 건너뜀
   - 하측 거부율 · 평균 가짜 n₁
6. SD_null → MDE_null(%p) · MDE_SE(%p)
7. **생존자 누락률**(`surv.py` · Ruling: Final I1)
   - (i) 3태그 원공시, **공시 단위**
   - (ii) 정기공시(유형 A · 제목에 «정정» 없음)를 낸 회사, **회사 단위**
   - 분류별 내역(있음 / 그날만 없음 / 끝내 없음 / 나중 상장 제외 / 코넥스 제외 / 달력 밖 제외)
8. `- seal.json md5 \`<32hex>\`` 줄 정확히 1개. open 이 이 값으로 seal.json 을 대조한다(Ruling: Final I5).

**생존자 분류 정의**: 공시마다 접수일 이후 첫 거래일 d 를 잡고 아래 순서로 분류한다.

| 분류 | 조건 | 처리 |
|---|---|---|
| `konex` | corp_cls = N | 두 비율 모두에서 제외 |
| `out_of_cal` | d 가 가격 달력 밖 | 제외 |
| `present` | (종목, d) 가 `daily_prices` 에 있음 | 있음 |
| `never_present` | `daily_prices` 에 끝내 없음 | 누락 |
| `later_listed` | 종목이 d «뒤»에야 처음 나타남(상장 전 공시) | 제외 |
| `absent_day` | d 이전에 나타났지만 그날 행이 없음 | 누락 |

- 누락률 = (그날만 없음 + 끝내 없음) / (있음 + 누락)
- (ii) 회사 판정: 회사의 남은(제외 안 된) 정기공시 중 **하나라도 누락이면 그 회사 = 누락**이다. 보수적인 방향이다. (ii) 를 키워 라벨 조건 (i) ≥ (ii) 를 어렵게 만든다.
  - 남은 공시가 없는 회사는 제외 칸에 센다(우선순위 konex > later_listed > out_of_cal).
- 생존자 공시 창 = 스캔 창(§2-6 #13).
- 한계: corp_cls 는 DART **현재** 값이다(§9).

**seal.json 에 더 남기는 것**: build 산출물 md5 전부 + `build_meta.json` md5(`build_md5`) · 실제 표식 수 · 평균 SE · git sha · 봉인 시각. open 이 이것을 대조한다(Ruling: Task 9 I2).

**봉인 뒤 확인**(plan Task 13 Step 2)

- n₁ ≥ 100 인지 확인하고 도구와 MDE 를 기록한다.
- 도구가 `fail` 이면 개봉해도 라벨은 「판정 불가(도구)」로 정해져 있다. 사장님께 보고하고 개봉 여부를 묻는다(사장님 질문 Q6).

---

## §7. 라벨과 보조 인쇄

### 7-1. 주 라벨(spec §3-7 · `run.label` · 검사 순서 고정)

| 순서 | 조건 | 라벨 |
|---|---|---|
| 1 | 봉인 도구 = `fail` | **「판정 불가(도구)」**(spec §3-5) |
| 2 | n₁(유효 · `fe_sl.n1`) < 100 `(settings.py: N1_MIN)` | **「판별 보류(n₁<100)」** |
| 3 | 손절 우선 판 양측 p < 0.05 ∧ δ̂_sl > 0 | **「역방향」** → 필터 기각 확정. 0.05 는 `run.label` 의 상수다 |
| 4 | 손절 우선 단측 p < 0.05 ∧ 익절 우선 단측 p < 0.05 ∧ δ̂_sl ≤ −0.4%p ∧ 누락률 (i) ≥ (ii) | **「있음(−)」** `(settings.py: ALPHA, DELTA_MAX)` |
| 5 | 그 밖 | **「판별 보류」** |

- p 는 봉인 때 고른 도구(CR1 또는 2원)의 값이다.
- p · δ̂ · 누락률 중 하나라도 NaN 이면 그 비교는 거짓이다(닫힌 쪽 실패).
- 「없음」 은 이 설계로 **선언할 수 없다**. CI 반폭이 0.4 보다 크기 때문이다(MDE ≈ 2.0~2.3%p · spec §3-7). 코드에도 「없음」 경로가 없다.
- 「판별 보류」는 「쓸모없음」이 아니다. 보험 규모 효과는 이 표본으로 못 잡을 수 있다(spec §3-7).
- 검정력(퀀트 · spec §3-7)
  - 가정: lag0 대리 소형 n₁ ≈ 100~130 · MDE ≈ 2.0~2.3%p
  - 오염 창 효과 −2.5 를 승자의 저주만큼 줄여 보면 검정력 ≈ 0.4~0.6 이다.
- 문장 예(라벨 → 보고 첫 줄)
  - 「있음(−)」: «돌파일 당일 3태그 공시 후보는 같은 날 다른 후보보다 net δ̂ %p 덜 벌었다(두 동시 터치 규칙 모두 유의 · 생존자 누락이 표식 쪽에 더 많아 방향 보수적). L-1 비열등 검정으로 넘어갈 자격이 생겼다.»
  - 「역방향」: «표식 후보가 오히려 더 벌었다. 이 필터는 기각한다.»
  - 「판별 보류」: «이 표본으로는 있다·없다를 가를 수 없다. 필터는 켜지 않는다.»
  - 「판정 불가(도구)」: «검정 도구가 가짜 표식 교정을 통과하지 못했다. 결과를 판정에 쓰지 않는다.»

### 7-2. 보조 인쇄(라벨 불변 · spec §3-8 · `run.stage_open`)

| 항목 | 계산 |
|---|---|
| W5 · W20 | 같은 표본 · 표식만 W 창. δ̂ · n₁ · CR1 단측 p(도구와 무관하게 CR1) |
| 대형 포함 전체 | p_L 거르기 없이 체결 전부. FE = 날짜 × p_L 3분위(표본 전체 기준 · NaN p_L 은 날짜별 따로 한 칸) · δ̂ · n₁ · CR1 단측 p |
| 연도별 | 표본에 있는 해마다 δ̂ · n₁ |
| 거래대금 3분위별 | 표본 전체 거래대금 3분위마다 δ̂ · n₁ |
| 팔별(표식 / 대조) | 정지 낀 비율(`halted_in_path`) · ret ≤ −15% 비율(gross ret_sl · `(settings.py: TAIL_LOSS)`) · 동시 터치율 |
| 진입 불가 | 대리 소형 원장 행(체결 + 진입 불가) 중 `halt_entry` 수 / n · 팔별(spec :84 «따로 셈») |
| 태그별 3개 + Holm | §5-6(verifier · 사장님 질문 Q4) |

- 주 결과와 부호가 다른 보조가 있으면 「크기/국면 의존 가능」을 함께 적는다(spec §3-8).
- 동시 터치율은 개봉 때만 본다.
- 산출물: `results/RESULTS_<개봉일>.md` · `results/open.json`(라벨 · fe_sl · fe_tp · 보조 · 시각 · git sha).
- verifier(opus)가 같은 원장으로 δ̂ · SE · 라벨을 독립 재계산한다. 손계산 로트 10개도 대조한다. 결과는 RESULTS 부록으로 붙인다(plan Task 13 Step 5).

---

## §8. 통과했을 때(L-1 ~ L-4 · spec §3-9)

이것은 이 사전등록의 판정이 아니다. 「있음(−)」 뒤 **각각 별도 결정**으로 넘어가는 조건이다.

- **L-1 비열등**
  - 경로 시뮬: 점수순 · 1~20위 → 10 · K=10 · 하루 5건 · 밴드 · ±10% · 10일 · 비용 0.25%
  - 조건: 필터 팔 − 무필터 팔 순손익의 월 블록 부트스트랩 90% 하한 > −0.5%(자본 대비)
- **L-2 페이퍼 그림자 20거래일**: 계산만 하고 적용하지 않는다. 조건은 셋이다.
  - 08:30 DART 자료 도착률 ≥ 95%
  - 차단률이 검정 표본의 0.5~2배
  - 정의 일치 100%
- **L-3 안전장치**
  - 독립 DART 아침 적재 작업(07:50~08:25)을 둔다. LLM shadow 실행 가드(CLI sha 고정)에 묶인 현 적재에 기대지 않는다(데이터 X6).
  - 피드 나이 판정: W 창 각 날짜 `count>0 ∧ min(fetched_at) ≥ d+1일 00:00`. 0 이면 켠다. ≥1 이면 끄고 매수는 계속하며 경보한다(fail-open).
  - 하루 차단률 > 5% 면 자동으로 끄고 보고한다.
- **L-4 실전**
  - 페이퍼 적용 60거래일 뒤 별도로 결정한다.
  - 실전 첫 4주(10-19~)에는 넣지 않는다.
  - theme_rank · TN1 과 같은 날 바꾸지 않는다.
  - 적용일 전후 성적 구간을 나눈다.

---

## §9. 한계

**스펙 §7 에서 온 것**

- 효과가 진짜여도 «보험» 크기다. 연 10건 안팎 차단 · 실전 cap 기준 연 수만 원 규모다(spec §1).
- 검정력 ≈ 0.4~0.6 이다. 「판별 보류」가 나올 공산이 작지 않다.
- 시총은 대리로 근사한다. 2021~2023 에서 대리의 정확도는 직접 확인할 수 없다(시총 없음). 봉인 보고서의 연도별 p_L<0.5 비율로 안정성만 본다.
- 상폐 종목 가격이 없다. 누락률 (i)·(ii)로 방향만 확인한다.
- 접수 시각이 없다. 스캔일까지의 공시를 쓴다.
- lag0 선택은 오염 구간을 보고 정했다(§1 · §10).

**구현 쪽 추가**

- **생존자 corp_cls**: DART 의 **현재** 값이다. 과거 코넥스에서 이전상장한 종목 소수가 `konex` 로 잘못 빠질 수 있다(Ruling: Final I1).
- **생존자 later_listed**: `daily_prices` 첫 등장일 기준이다. 가격 이력이 늦게 시작한 상장주는 누락이 아니라 제외로 셀 수 있다(최종 리뷰 잔여).
- **권리락 가격 절벽**
  - 가격(OHLC)은 `daily_prices` 저장값 그대로다. 거래량만 adj_factor 를 곱한다.
  - FD1 사전등록 §3-4-b 는 이 표에서 권리락 절벽(adj_factor 계단)을 실측했다. 유상증자 표식(유무상증자 포함)의 보유 10거래일 안에 권리락이 끼면, 가짜 손절이 **표식 쪽에 몰려 가설 방향으로** 치우칠 수 있다.
  - 지금 코드에는 이 가드도, 인쇄도 없다(사장님 질문 Q5).
- **일봉 근사**: 라이브는 실시간 ±10% 다. 여기서는 일봉 고가·저가와 두 동시 터치 규칙으로 근사한다. 상한 체결은 진입일 터치를 보지 않는다.
- **후보 ≠ 실제 매수**: 순위 절단 · 자리 K · 하루 5건이 없다. 경로 효과는 L-1 이 본다.
- **고정 범위**: §11 pins 는 직접 의존 모듈까지만 고정한다. 추이 폐포가 아니다.
  - 빠지는 것: 상위 패키지 `__init__` · bootstrap · 간접 utils · 파이썬 라이브러리 버전
  - 기록용 버전: Python 3.9.13 · numpy 2.0.2 · pandas 2.3.3 · scipy 1.13.1 · psycopg2 2.9.12. 강제하지 않는다.
- **DB 지문 범위**: build ↔ seal ↔ open 사이 DB 지문은 `daily_prices`(2021-01-04 ~ 2024-04-30)만 덮는다.
  - 표식은 build 때 파일로 커밋되므로 그 뒤 `dart_disclosures` 변화는 표식에 영향이 없다.
  - 생존자 누락률은 seal 때 `dart_disclosures` 를 다시 읽는다.
- **LLM shadow 부작용**(spec §3-1 예고): 2021-01 ~ 2024-03 백필로 LLM shadow 이름 폴백 영향 종목이 **0 → 213** 이 됐다.
  - 2024-03 뒤 공시가 없던 종목은 `inputs.py` `stock_ctx` 가 옛 공시의 `corp_name` 을 잡는다. 상호를 바꾼 종목이면 옛 이름이다.
  - 이 검정과는 무관하다. 사장님 보고 항목이다.

---

## §10. 동결 전 본 것(오염 고지)

### 10-1. 스펙 §5 목록(설계 때 이미 본 것)

1. 2024-03~ daytrading 원장 × DART 태그 결합 전부: `cells_a.csv` W1/W5/W20 · 트레이더 lag0 재집계 · 하위 유형 분포(spec §2-2)
2. `feature_study/RESULTS_2026-09-24.md:428-435` daytrading 기관·외국인 itd5 인쇄. B 쪽 특징이며 A 와는 무관하다.
3. 전문가 패널 3파일 · BRIEF 의 숫자 전부(레포 밖 scratchpad `dt_filter_panel/`)
4. 2021-01 ~ 2024-03 창은 후보 수 · 크기 대리 적합 · 건수만 봤다(수익 결합 0). 스펙 §2-3 의 숫자다.
   - 시총 조건만 뺀 후보 34,735 후보-일 · 하루 45.1 · 에피소드 첫 행 29,176 · 대형 섞임 ≈30%
   - 퀀트 대리 AUC 0.927 · 창 밖 0.895
   - 시총 결측 연도 분포 · 2021 상장 2,120 중 사라진 것 1

lag0 을 주 검정으로 고른 것은 1 을 보고 정했다. 새 창은 보지 않았으므로 «학습 → 확인» 순서다(spec §5).

### 10-2. Task 10 — 대리 적합(이미 본 구간 · 가격·시총만 · 수익 0)

- `run --stage proxy` 1회 실행(코드 `793e984` · 결과 커밋 `ae766ce`).
  - 창 2024-03-13 ~ 2026-09-23
  - n 26,129(스캔 행 26,276 중 시총 > 0 ∧ 특징 유한 · 단계별 탈락 수는 기록 안 됨) · 대형 7,902
  - AUC 0.9198 · 연도별 0.9077 / 0.9172 / 0.9332
  - 계수 (−30.035, +0.6827, +1.4550) · 부호는 기대대로
- 리뷰(haiku)가 수치 · md5 · 창을 대조했다.

### 10-3. Task 11 — DART 백필(쓰기 · 이 창의 «공시 목록»만 · 수익 결합 0)

- 실행: 2026-10-10 11:44 ~ 12:43(금지 시간대 밖) · 연도별 4회 · `--limit-calls 5000 --resume`
- 호출 5,076: 2021 1,587 · 2022 1,582 · 2023 1,584 · 2024-01 ~ 03-12 323
- 적재 226,475행: 2021 71,176 · 2022 70,095 · 2023 70,573 · 2024 14,631
  - `dart_disclosures` 167,508 → 393,983행 · 최소 rcept_dt 2021-01-04
  - 경고 0 · 네트워크 예외 0 · 수리 0
- check-backfill: 칸 3,501 · 미완결 0 · exit 0 · `backfill_check.json` 커밋 `fc92bb5`
- LLM shadow 이름 폴백 영향(전후 SELECT): 0 → 213(§9)
- 리뷰(haiku) 재확인
  - 폴백 SELECT 재실행 213
  - 이번 적재 226,475행 전부 창 안(2024-03-13 이후 0)
  - call_log 5,076줄(000 3,871 · 013 1,205)
- 원자료: `D:/research-archive/dt_dart_backfill_2021_2024`(레포 밖)
- 🔴 **3태그 · lag0 · W 창 표식 건수는 이 창에서 아무도 세지 않았다**(원장 기준). 이 초안 작성자도 세지 않았다.

### 10-4. 그 밖의 읽기 전용 SELECT(구현 중 · 원장 기준)

- **최종 리뷰(opus · c859e91..ae766ce)**: 코드 가정을 확인하려고 달력 · 정지 행 · bad_open · 상폐 종목 stock_code 를 SELECT 했다.
  - 2024-06 시점 코넥스(corp_cls N) 73종목 중 `daily_prices` 에 있는 것 0 · corp_cls E 118 중 25(오염 구간).
  - 그 밖의 창 · 숫자는 원장에 남지 않았다. 리뷰 보고상 수익 결합은 없다.
- **관리자 SELECT(백필 진행 중)**: `dart_disclosures` 에 corp_cls 열이 있다. 연도별 행: 2021 71,176 · 2022 70,095(진행 중) · 2023 3,794(진행 중) · 2024 47,263.
- **테스트**: 105개 모두 합성 데이터 · 가짜 커서다. DB 접속은 없다.
- **이 초안 작성**: DB 접속 0.
  - `git hash-object`(pins) 실행
  - 패키지 테스트 105 passed(합성)
  - 합성 프레임으로 `analysis_frame(small_only=False)` 의 NaN p_L 처리 1회 확인

### 10-5. 보지 않은 것(동결 시점에 참이어야 함)

- build 미실행이다. 새 창의 후보 수익 원장 · 표식 파일이 아직 없다.
- seal · open 미실행이다.
- 새 창에서 표식 × 수익 결합은 0이다(에이전트 · 임시 계산 포함 · 계획 Global Constraints).

---

## §11. 입력 고정 · 실행 순서

### 11-1. 고정 값

| 대상 | 값 | 강제 장치 |
|---|---|---|
| `results/proxy_coef.json` | md5 `a1032ffd1cf7092715387ea0502a4c54` | `frozen_consts.PROXY_COEF_MD5`(동결 때 채움) · `require_frozen` |
| `results/backfill_check.json` | md5 `2a35eb74d3c579191005d6e0f399c7d4` · git blob `393f5d29107a66994cf8937027c7e18dae73d618` | 아래 pins 블록(blob) · build 의 커밋·내용 가드 |
| `PREREG.md`(이 문서) | 동결 커밋의 git blob | `frozen_consts.PREREG_FROZEN_BLOB`(동결 때 채움) |
| 코드 · 의존 모듈 27개 + `backfill_check.json`(28줄) | 아래 pins 블록 | `run.require_frozen` → `parse_pins` · `verify_pins` |
| 코드 커밋 | 초안 기준 `fc92bb5` · 동결 커밋 SHA 는 동결 때 REGISTRY 에 적음 | — |

- `frozen_consts.py` 는 pins 에서 **빠지는 유일한 패키지 파일**이다. 이 문서의 blob 을 담으므로 순환을 피하려고 뺐다(Ruling: Final I4). 이 문서는 `PREREG_FROZEN_BLOB` 으로 사슬에 묶인다.
- pins 대상(`run.required_pins`) = 이 패키지 최상위 `*.py`(frozen_consts.py · tests/ 제외) + `run.PIN_DEPS`.
  - glob 이 실행 때 돈다. 동결 뒤 새 모듈이 생기면 pins 에 없으므로 거부된다.
- 🔴 **이 블록은 초안 시점(`fc92bb5`) 값이다.** 동결 커밋 전에 고정 대상 파일이 하나라도 바뀌면(critic 반영 등), 동결 커밋에서 아래 명령으로 **다시 만든다.** `RoboTrader_template` 에서 실행한다.

```bash
PY=D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe
$PY -c "from backtest.concept_axes.dt_dart_filter import run as R; r=R.repo_root(); print('\n'.join(f'{p} {R.blob(r / p)}' for p in R.required_pins(r)))"
```

```pins
# 레포 루트 기준 POSIX 경로 · git blob sha1(git hash-object) — 초안 시점 fc92bb5 · 28줄
RoboTrader_template/backtest/concept_axes/dt_dart_filter/__init__.py 7f86ec3a21772ec16788834bf1c60de72e1a3de8
RoboTrader_template/backtest/concept_axes/dt_dart_filter/daycheck.py 18081cc52fff28699886a89f293d7c0903a55132
RoboTrader_template/backtest/concept_axes/dt_dart_filter/gate.py a2b58e1e375e0443e2c74e1f73c5418cbcb4c318
RoboTrader_template/backtest/concept_axes/dt_dart_filter/lots.py d1ac72b58c80b7706c4fc1f13682e9d9633f3376
RoboTrader_template/backtest/concept_axes/dt_dart_filter/proxy.py cbdf0da6d9cc2ed550cc2871f160b0e24892757b
RoboTrader_template/backtest/concept_axes/dt_dart_filter/run.py 5e83b415748a4b662d4a576cefa55783fae31e34
RoboTrader_template/backtest/concept_axes/dt_dart_filter/sample.py 860afa105b9ecfeff744b29c1afb7f39204d5b3c
RoboTrader_template/backtest/concept_axes/dt_dart_filter/settings.py 46e649afc79736227346a3390bbf938d7d5a500a
RoboTrader_template/backtest/concept_axes/dt_dart_filter/stats.py 495c7810d976c7a2aec7134a56752850ab0bb0aa
RoboTrader_template/backtest/concept_axes/dt_dart_filter/surv.py 02d53d7bea8fda0a9599c897884c97dddd1bc96f
RoboTrader_template/backtest/concept_axes/dt_dart_filter/tags.py ee091feb59b840f2538bcf3bb9d512958d3bf97c
RoboTrader_template/backtest/concept_axes/dt_dart_filter/universe.py 6f002e17adbb7f21b3d1b3ac4c13de80c3e36ae2
RoboTrader_template/strategies/daytrading_3methods_breakout/screener.py 8007ea2942ad4a0a8f1a0170425746498d7d66fc
RoboTrader_template/strategies/books/daytrading_3methods/rules.py b99cd9028687d9a30b18c4f3fe3f8eac7db255d4
RoboTrader_template/strategies/books/_base_book_strategy.py c4b714aad2999658ad4b7fe98b863d55fbac67f9
RoboTrader_template/strategies/_rule_screener_base.py ed5a188d6af7685f366de3bfca54a7d05154f9bd
RoboTrader_template/utils/data_sanity.py 823a5c4398aba9bb7002abfdf06c0aae205e7aeb
RoboTrader_template/backtest/concept_axes/replayer/scan.py 1a32a3f877c74d0267d9639a59a6fe0cf1b6fb2d
RoboTrader_template/backtest/concept_axes/replayer/loader.py 41b7c8f94423011281aba8009264d4e30c1bbc16
RoboTrader_template/backtest/concept_axes/candidate_ledger/run.py c0a49569f1d4a9d7df8fb4ae5295b8dffda79b69
RoboTrader_template/backtest/concept_axes/candidate_ledger/tool_calibration/run_calib.py b705722358a3204b577c98dfb0391f4fcb972a83
RoboTrader_template/backtest/concept_axes/ledger8/exitsim8.py b9678b1f43c2241f0806d709e320b4e02a2246c1
RoboTrader_template/backtest/concept_axes/ledger8/sizing.py 4399784ddcbb568a9679b691b151e7f4693e97a7
RoboTrader_template/backtest/concept_axes/ledger8/sources8.py add2062bac600a4bb30b1a94e8e6566410b42b5d
RoboTrader_template/backtest/concept_axes/minervini/cap_skip_ledger/sim.py 9ab121ca43f8bce02dd94423609a527a156f3ee1
RoboTrader_template/backtest/concept_axes/theme_rank/bandfill.py 8ac7d21747a6f0afc1ae2c4a9726b89764e42845
RoboTrader_template/backtest/concept_axes/candidate_ledger/dart_events/dart_tags.py ca3ff3d369b809875f807160618b02db14d6d1b0
RoboTrader_template/backtest/concept_axes/dt_dart_filter/results/backfill_check.json 393f5d29107a66994cf8937027c7e18dae73d618
```

### 11-2. 실행 가드(코드가 강제)

**`require_frozen`**(build · seal · open 공통 · 이 순서)

1. `PREREG_FROZEN_BLOB` 이 비어 있지 않다.
2. 이 문서의 blob 이 그 값과 같다.
3. `PROXY_COEF_MD5` 가 비어 있지 않고 proxy_coef.json md5 와 같다.
4. 패키지에 커밋 안 된 변경이 없다. 미추적 파일도 «변경»이다.
5. pins 블록을 파싱하고 대조한다. 블록은 정확히 1개여야 한다. 필수 경로가 빠지거나 파일이 없거나 blob 이 다르면 거부한다.
6. 라이브 어댑터 룰 값이 settings 와 같다.

**단계별 추가 가드**

| 단계 | 가드 |
|---|---|
| build | seal.json · open.started · open.json 이 있으면 거부 · `backfill_check.json` 커밋·불변 · 완결 · 창·유형 일치 |
| seal | seal.json · open.started · open.json 이 있으면 거부(재봉인 금지 · DB 사용 전) · build 산출물 md5 · DB 지문(`daily_prices`) 일치 |
| open | open.json · open.started 가 있으면 거부 · `sealed_report.md` 커밋·불변 · 보고서의 seal.json md5 줄 1개 = 지금 seal.json · seal.json 의 build md5 = 지금 산출물 · DB 지문 일치 → **그 뒤** `open.started` 를 쓰고 → 그 뒤에만 데이터를 읽는다 |

### 11-3. 런북(Task 13 · Ruling: Final I6)

`RoboTrader_template` 에서 `$PY -X utf8 -m backtest.concept_axes.dt_dart_filter.run --stage <단계>` 로 실행한다. 라이브 트리에서는 실행하지 않는다. 커밋 메시지는 파일로 쓴다(`git commit -F`).

1. **동결**
   1. 사장님 승인 뒤 이 문서를 커밋한다. 상태 줄은 «동결»로 바꾸고, 필요하면 pins 를 다시 만든다.
   2. `git hash-object PREREG.md` 값을 `frozen_consts.PREREG_FROZEN_BLOB` 에 넣는다. `PROXY_COEF_MD5 = "a1032ffd1cf7092715387ea0502a4c54"` 도 넣는다.
   3. `frozen_consts.py` 만 커밋한다.
   4. REGISTRY `DF1` 행을 등재한다.
2. **build** → `ledger_A.csv` · `marks_{lag0,w5,w20}.csv` · `build_meta.json`
   - 원장 행 수가 2만 미만이거나 5만 초과면 멈추고 보고한다(퀀트 추정 34,735 근처 기대).
   - → `results/` 를 **커밋**한다. 커밋하지 않으면 패키지가 더러워 seal 이 거부된다.
3. **seal** → `seal.json` · `sealed_report.md`
   - n₁ · 도구 · MDE 를 확인한다(§6).
   - → 둘 다 **커밋**한다(`research(dt-dart-filter): 봉인 — …(표식×수익 결합 0)`).
4. **open**(1회) → `open.started` → `RESULTS_<날짜>.md` · `open.json` → 셋 다 **커밋**한다.
5. **verifier**(opus): 독립 재계산 · §5-6 태그별 · 로트 10개 → RESULTS 부록 → 커밋. push · main 머지는 사장님 별도 확인이다.

**복구 경로**(전부 사장님 승인 뒤 · 사유를 커밋 메시지에 남긴다)

- **seal 이 seal.json 과 sealed_report.md 사이에서 죽음**
  - 커밋 안 된 seal.json 을 손으로 지우고 seal 을 다시 돌린다. 표식×수익 결합이 없는 단계라 결과 오염은 없다.
- **seal 단계 DB 지문 불일치**(build 뒤 `daily_prices` 소급 수정)
  - seal.json 이 아직 없으므로 build 부터 다시 돌린다(build_meta 덮어씀) → 커밋 → seal.
  - 바뀐 종목은 build_meta 에 종목별 지문이 없어 바로 좁힐 수 없다. 두 번의 지문 sha 를 커밋 메시지에 적는다.
- **open 단계 DB 지문 불일치**
  - `open.started` 를 쓰기 «전»에 멈춘다. 결과를 하나도 보지 않았으므로 1회 개봉을 소모하지 않는다(spec §6 · theme_rank 선례).
  - 복구: seal.json · sealed_report.md 를 `git rm` 하는 커밋(기록 보존 · 사유 명시) → build → 커밋 → seal → 커밋 → open.
  - 다시 봉인하면 블라인드 안전 숫자(게이트 · SD · 누락률)를 한 번 더 본다. 표식×수익 결합은 여전히 0이다. 옛 봉인 보고서는 git 이력에 남는다.
- **open 이 `open.started` 뒤에 죽음**
  - 설계상 영구 잠금이다. 두 번째 open 은 거부된다.
  - 수동 복구:
    1. 죽은 실행의 출력은 판정에 쓰지 않는다. 미커밋 RESULTS · open.json 이 있으면 내용을 보지 말고 지운다.
    2. `open.started` 와 traceback 요약을 커밋한다.
    3. 원인이 코드면 고친다. 이것은 pins 가 바뀌는 사전등록 개정이다. 개정 절을 덧붙이고, 사장님 재동결과 `PREREG_FROZEN_BLOB` 갱신이 필요하다.
    4. `open.started` 를 `open.started.crashed-<n>` 으로 `git mv` 해 커밋한 뒤 open 을 다시 돈다.
  - 본 분석은 결정적이다. 같은 원장이면 다시 돌려도 같은 수치다.

---

## 부록 A. Ruling 대응표(행동을 바꾼 판정 → 이 문서 위치)

| Ruling | 내용 | 위치 |
|---|---|---|
| Task 3 | 백필 완결 = 소속 확인 + 여분 행 0(지름길 없음) | §3-4 |
| Task 4 | 로지스틱 적합 닫힌 쪽 실패(ValueError · RuntimeError) | §2-3 |
| Task 6 | `halted_in_path` = 진입 다음날 ~ 청산일(미해소면 경로 끝) | §4-4 |
| Task 7 | 표준 CR1 c = G/(G−1)·(N−1)/(N−K) · K = 1 + 날짜 수 · 2원 각 성분 자기 G | §5-2 |
| Task 8 | 테스트 픽스처만(행동 변화 없음) | — |
| Task 9 I1 | n₁ = 날 거른 뒤 유효 표식 행(봉인 · 라벨 공통) | §5-5 · §6 · §7-1 |
| Task 9 I2 | seal ↔ build 해시 연결 · 봉인 뒤 build 거부 | §6 · §11-2 |
| Task 9 I3 | PROXY_COEF_MD5 동결 · 동결 뒤 proxy 거부 | §2-3 · §11 |
| Final I1 | 생존자: 코넥스 · 상장 전 제외 · (i) 공시 단위 · (ii) 회사 단위(하나라도 누락 = 누락) · 내역 인쇄 | §6 · §9 |
| Final I2 | 보유 중 정지 → 재개 시가 무조건 청산 | §4-4 |
| Final I3 | 게이트 유효 복제(380 문턱 · degenerate) · 복제 안 비복원 · 하측 거부율 · 평균 가짜 n₁ | §5-3 |
| Final I4 | pins 블록 · frozen_consts.py 분리 · 어댑터 룰 값 단언 | §2-2 · §11 |
| Final I5 | 재봉인 거부 · seal.json md5 대조 · open.started 표식 | §6 · §11-2 |
| Final I6 | 런북 · 지문 불일치 복구 · open.started 수동 복구 | §11-3 |
| Final 동결 전 묶음 | 백필 보고 창·유형 가드 · 진입 불가 팔별 · 연도별 p_L 비율 · 원시 라벨 | §3-4 · §6 · §7-2 |
| Task 11 note | LLM shadow 이름 폴백 0 → 213 | §9 · §10-3 |

## 부록 B. 사장님 확인 질문(동결 전)

- **Q1.** 관리자 판단으로 넣은 두 규칙을 그대로 동결할까요?
  - 가짜 게이트 유효 복제 문턱 380/400(95%)
  - 생존자 (ii) «회사 공시 하나라도 누락이면 누락»
- **Q2.** 「있음(−)」의 δ̂ ≤ −0.4%p 를 손절 우선 판에만 걸까요(현 코드), 익절 우선 판에도 걸까요?
- **Q3.** n₁ < 100 이면 「역방향」도 판정하지 않고 「판별 보류」로 둘까요(현 코드 순서)?
- **Q4.** 태그별 3개는 코드에 없습니다. 둘 중 하나를 골라 주세요.
  - (a) 동결 전 코드를 추가해 항상 인쇄
  - (b) §5-6 절차로 verifier 가 계산
  - 함께 확인할 것: 대조 정의(다른 태그 표식 행 제외)와 «고정 순서» = 동점 순서 해석이 맞는지.
- **Q5.** 권리락 가격 절벽이 유상증자 표식 쪽으로 치우칠 위험이 있습니다. 둘 중 하나를 골라 주세요.
  - (a) 한계로만 적기(현 초안)
  - (b) 동결 전 코드 추가: 보유 경로 안 adj_factor 변화 로트 수를 팔별로 인쇄하고, 그 로트를 뺀 민감도도 인쇄
- **Q6.** 봉인 도구가 `fail` 이면 개봉할까요? 미리 정해 둘까요(개봉 안 함 / 보조 인쇄만 보려고 개봉)?
- **Q7.** §11-3 복구 경로(지문 불일치 = build 부터 다시 · open.started 수동 복구 = 개정 절 + 재동결)를 승인하시나요?
