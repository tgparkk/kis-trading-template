# Step 3c — 시총 플로어·섹터 제외 필터 OOS 백테스트 결과

> 측정 전용(라이브 코드/config 무수정). 영구룰: 숫자 검증·추정 금지 — 아래 수치는
> `scripts/step3c_size_sector_filter.py` 실행 산출(워킹트리). step3·라이브 무수정,
> 신규 스크립트 1개로 한정.

## 목적
2026-06-27 in-sample 반사실 검증(116 페이퍼 SELL: 두 필터 적용 시 실현
−1.12M→+1.17M, 4전략 전부 손실→흑자)을 **다년 PIT 백테스트로 OOS 검증**한다.
- **가설A(시총 플로어)**: 초소형주(시총<300억) 진입 컷 → 갭 손절관통 감소.
- **가설B(섹터 제외)**: 반도체와반도체장비·전자장비와기기 제외.

## 측정 설정
- 기간: **2021-01-12 ~ 2026-06-26**
- scan 빈도(PIT): **monthly** — scan_date 67개 (2021-01-12 .. 2026-06-26)
- 하니스: step3_pit_rebaseline `_run_pit`(build_signals → pit_gate_signal_cache →
  run_portfolio) 재사용. sim·진입룰·청산·비용·사이징·K = multiverse4 SPECS 정본 그대로.
- **유일 차이 = PIT resolver**: baseline 은 step3 U2_PIT(make_scan_eligible_resolver),
  나머지는 통과집합에 시총 플로어/섹터 제외를 곱한 변형(make_filtered_resolver).
- 데이터=전략별 union(warmup 확보), 진입신호만 resolver 게이팅.

## 구성
- `baseline` = step3 U2_PIT (필터 없음).
- `floor300` = scan_date snapshot market_cap ≥ **3e10(300억)**. **PIT-clean**.
- `floor500` = market_cap ≥ **5e10(500억)**. 민감도용. PIT-clean.
- `ex_sector` = 반도체와반도체장비·전자장비와기기 제외. **근사**(아래 한계).
- `floor300_ex_sector` = 둘 다.

## 비교표 (전략 × 구성)

| strategy | config | uni_size | loaded | n_signals | n_trades | sharpe | pnl | maxdd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| daytrading_3methods_breakout | baseline | 2429 | 2414 | 24517 | 984 | +0.283 | +24.70% | 30.60% |
| daytrading_3methods_breakout | floor300 | 2429 | 2414 | 6080 | 479 | -0.259 | -32.58% | 41.56% |
| daytrading_3methods_breakout | floor500 | 2429 | 2414 | 5923 | 479 | -0.247 | -31.51% | 41.56% |
| daytrading_3methods_breakout | ex_sector | 2429 | 2414 | 20775 | 999 | +0.462 | +55.54% | 32.75% |
| daytrading_3methods_breakout | floor300_ex_sector | 2429 | 2414 | 4912 | 476 | +0.158 | +6.65% | 40.35% |
| elder_ema_pullback | baseline | 1795 | 1787 | 93751 | 2270 | +0.473 | +103.57% | 63.13% |
| elder_ema_pullback | floor300 | 1795 | 1787 | 32628 | 1003 | +1.055 | +169.90% | 25.95% |
| elder_ema_pullback | floor500 | 1795 | 1787 | 32628 | 1003 | +1.055 | +169.90% | 25.95% |
| elder_ema_pullback | ex_sector | 1795 | 1787 | 79970 | 2263 | +0.297 | +16.47% | 69.56% |
| elder_ema_pullback | floor300_ex_sector | 1795 | 1787 | 27666 | 1005 | +0.933 | +125.09% | 20.79% |
| book_envelope_200d | baseline | 2447 | 2432 | 5547 | 873 | +0.089 | -36.43% | 78.51% |
| book_envelope_200d | floor300 | 2447 | 2432 | 3497 | 473 | +0.173 | +8.13% | 52.54% |
| book_envelope_200d | floor500 | 2447 | 2432 | 3469 | 473 | +0.181 | +9.08% | 51.64% |
| book_envelope_200d | ex_sector | 2447 | 2432 | 4344 | 883 | +0.196 | -4.60% | 71.90% |
| book_envelope_200d | floor300_ex_sector | 2447 | 2432 | 2671 | 467 | +0.004 | -11.50% | 50.96% |
| rs_leader | baseline | 2447 | 2432 | 278074 | 3347 | +0.492 | +149.11% | 60.97% |
| rs_leader | floor300 | 2447 | 2432 | 141200 | 1509 | +0.790 | +102.48% | 34.35% |
| rs_leader | floor500 | 2447 | 2432 | 139165 | 1509 | +0.790 | +102.48% | 34.35% |
| rs_leader | ex_sector | 2447 | 2432 | 232371 | 3463 | +0.418 | +84.28% | 60.42% |
| rs_leader | floor300_ex_sector | 2447 | 2432 | 117176 | 1606 | +0.447 | +41.92% | 27.33% |


- `uni_size` = union 코드 수, `loaded` = 일봉 30행+ 확보돼 실제 로딩된 종목 수
- `n_signals` = PIT 게이팅 후 진입신호 수, `n_trades` = 청산(sell) 수

## 전략별 baseline 대비 델타

**daytrading_3methods_breakout** (baseline: sharpe +0.28, pnl +24.70%, maxdd 30.60%, trades 984)
  - `floor300`: Δsharpe -0.54, Δpnl -57.28%, Δmaxdd +10.96%, trades 984→479
  - `floor500`: Δsharpe -0.53, Δpnl -56.21%, Δmaxdd +10.96%, trades 984→479
  - `ex_sector`: Δsharpe +0.18, Δpnl +30.84%, Δmaxdd +2.15%, trades 984→999
  - `floor300_ex_sector`: Δsharpe -0.12, Δpnl -18.05%, Δmaxdd +9.75%, trades 984→476

**elder_ema_pullback** (baseline: sharpe +0.47, pnl +103.57%, maxdd 63.13%, trades 2270)
  - `floor300`: Δsharpe +0.58, Δpnl +66.33%, Δmaxdd -37.18%, trades 2270→1003
  - `floor500`: Δsharpe +0.58, Δpnl +66.33%, Δmaxdd -37.18%, trades 2270→1003
  - `ex_sector`: Δsharpe -0.18, Δpnl -87.10%, Δmaxdd +6.43%, trades 2270→2263
  - `floor300_ex_sector`: Δsharpe +0.46, Δpnl +21.52%, Δmaxdd -42.34%, trades 2270→1005

**book_envelope_200d** (baseline: sharpe +0.09, pnl -36.43%, maxdd 78.51%, trades 873)
  - `floor300`: Δsharpe +0.08, Δpnl +44.56%, Δmaxdd -25.97%, trades 873→473
  - `floor500`: Δsharpe +0.09, Δpnl +45.51%, Δmaxdd -26.87%, trades 873→473
  - `ex_sector`: Δsharpe +0.11, Δpnl +31.83%, Δmaxdd -6.61%, trades 873→883
  - `floor300_ex_sector`: Δsharpe -0.08, Δpnl +24.93%, Δmaxdd -27.55%, trades 873→467

**rs_leader** (baseline: sharpe +0.49, pnl +149.11%, maxdd 60.97%, trades 3347)
  - `floor300`: Δsharpe +0.30, Δpnl -46.63%, Δmaxdd -26.62%, trades 3347→1509
  - `floor500`: Δsharpe +0.30, Δpnl -46.63%, Δmaxdd -26.62%, trades 3347→1509
  - `ex_sector`: Δsharpe -0.07, Δpnl -64.83%, Δmaxdd -0.55%, trades 3347→3463
  - `floor300_ex_sector`: Δsharpe -0.04, Δpnl -107.19%, Δmaxdd -33.64%, trades 3347→1606

## 핵심 판정

### 가설A (시총 플로어 floor300, **PIT-clean**) — sharpe↑ AND maxdd↓ 면 YES
- **daytrading_3methods_breakout**: NO — sharpe +0.28→-0.26 (-0.54), maxdd 30.6%→41.6% (+11.0%), pnl +25%→-33%
- **elder_ema_pullback**: YES — sharpe +0.47→+1.05 (+0.58), maxdd 63.1%→25.9% (-37.2%), pnl +104%→+170%
- **book_envelope_200d**: YES — sharpe +0.09→+0.17 (+0.08), maxdd 78.5%→52.5% (-26.0%), pnl -36%→+8%
- **rs_leader**: YES — sharpe +0.49→+0.79 (+0.30), maxdd 61.0%→34.4% (-26.6%), pnl +149%→+102%

### 가설B (섹터 제외 ex_sector, **근사** — 방향만)
- **daytrading_3methods_breakout**: 양(+) — sharpe +0.28→+0.46 (+0.18), maxdd 30.6%→32.8% (+2.2%), pnl +25%→+56%
- **elder_ema_pullback**: 음(-) — sharpe +0.47→+0.30 (-0.18), maxdd 63.1%→69.6% (+6.4%), pnl +104%→+16%
- **book_envelope_200d**: 양(+) — sharpe +0.09→+0.20 (+0.11), maxdd 78.5%→71.9% (-6.6%), pnl -36%→-5%
- **rs_leader**: 음(-) — sharpe +0.49→+0.42 (-0.07), maxdd 61.0%→60.4% (-0.6%), pnl +149%→+84%

## 유니버스/섹터 구성
- 전체시장 snapshot(2026-06-26) = 2486종목.
- **daytrading_3methods_breakout**: union 2429 (전체의 98%)
- **elder_ema_pullback**: union 1795 (전체의 72%)
- **book_envelope_200d**: union 2447 (전체의 98%)
- **rs_leader**: union 2447 (전체의 98%)
- 섹터맵 코드 2447개 중 제외대상(반도체와반도체장비·전자장비와기기) 258개, 미상('?') 31개.

## 한계 (반드시 함께 해석)
- **섹터 근사(가설B)**: 섹터맵은 네이버 종목페이지의 *현재* 업종명을 스크랩한 정적값이다.
  이를 과거 진입봉에 소급적용 = **look-ahead/생존편향**(과거 다른 업종이었거나 상장폐지로
  현재 페이지가 없는 종목은 '?'). 따라서 `ex_sector` 계열은 *방향성 참고*일 뿐 PIT-clean 이
  아니다. (시총 플로어 `floor*` 는 scan_date snapshot market_cap 사용 → PIT-clean.)
- **6월 특수성**: in-sample 신호는 2026-06 반도체 약세 국면 특수성을 반영했을 수 있다.
  OOS(5.5년)는 다양한 국면을 포함하므로 in-sample 흑자전환이 OOS 에서 재현되지 않을 수
  있다(이것이 본 검증의 핵심).
- **PIT 월별 근사**: 라이브 스크리너는 일별이나 본 측정은 monthly scan_date 멤버십으로
  근사. 월 중 신규 진입/이탈 종목의 멤버십 전환 시점에 ±수주 오차 가능.
- **union 데이터 로딩**: 풀기간 union 은 base_filter 가 느슨한 전략에서 전체시장에 근접.
  U2_PIT 게이팅이 이를 우회하나, 데이터 적재 자체는 union 전체(무거움).
