# PIT 국면 진입게이트 검증 — 약세장 무방비 전략 구제 테스트

> 작성: 2026-06-02 · 드라이버: `scripts/book_portfolio_multiverse.py --regime-gate`
> 국면판별기: `core/regime/regime_classifier.py` (PIT, `tests/regime/test_regime_no_lookahead.py` 14/14 통과)
> 선행 설계: [_EXPERT_regime_daytrading_2track.md](_EXPERT_regime_daytrading_2track.md)

---

## 0. TL;DR

- **연동 완료**: `--regime-gate {none,exclude_bear,bull_only,(분봉)trend_only,dir_match}` 를 멀티버스 차원으로 추가.
  진입봉 시점의 PIT 국면이 허용집합이 아니면 그 신호를 skip(진입신호 캐시 필터링). `classify_daily/classify_intraday`
  를 **그대로 호출**(재구현 0). 국면 시계열은 시장 레벨 1회 사전계산 후 진입봉 datetime 으로 매핑.
- **★일봉 게이트는 약세장 무방비 전략을 강하게 구제한다.** 약세장(2022) 무방비로 손실난 전략(elder/ma5/daytrading3)에서
  `exclude_bear` 가 BEAR 손실을 줄이거나 흑자전환시키고 MaxDD 를 절반 이하로 낮춘다. `bull_only` 는 전구간 PnL·MaxDD 를
  가장 크게 개선(추세전략 본질=BULL 노출)하나 약세장에선 거래 0(전량 차단). 대가는 **거래수 급감**(2~4배).
- **단, 무방비가 아닌 전략은 게이트가 오히려 손해**(close_betting 는 BEAR 에서 자기완결 흑자라 게이트가 수익 깎음).
  게이트는 "약세장 노출이 곧 손실"인 전략에만 처방.
- **[갱신 2026-06-02] 분봉 게이트는 봉 간격 인지(granularity-aware) 정합화로 완성**: `IntradayRegimeParams` 에
  `bar_interval_min`(자동추론) 추가, 시간 윈도(vwap_slope_lb/vol_window)를 봉 개수로 환산 → 15분봉서 trend 라벨
  **실제 발화**(period별 36/81/94봉, 구버그 0건 해소). pytest 17/17(룩어헤드 5종 포함). **결론(§4-B)**: 게이트가
  분봉 데이트레이딩을 **명확히 구제하진 못함** — surge_fade trend_only 만 강건성·과적합 개선(but PnL 흑자전환 실패),
  bellafiore 는 흑자 파괴(페이드 본령=range 와 상충), aziz(orb) dir_match 는 손실만 줄되 거래 과축소(노출회피).
- **[구버그 기록·이하 §4 는 정합화 전 상태]** 분봉 게이트(surge_fade)는 정합화 전엔 무효였음: 15분 리샘플에서
  `trendiness=trend` 라벨 **0건**(621봉 전부 range), 1분봉 기준 파라미터와 15분봉 부정합이 원인 → §4-B 에서 해소.

---

## 1. 연동 방식 (룩어헤드 안전성)

- **게이트 = 진입신호 캐시 필터**. `_precompute_signals` 가 만든 `{code:[bar_idx]}` 에서 각 bar 의 datetime 에 해당하는
  국면 라벨이 허용집합 밖이면 그 bar 를 제거 → `run_portfolio` 에 게이트된 캐시 전달. exit×K 는 동일 캐시 재사용.
- **PIT 보장**: `classify_daily`/`classify_intraday` 는 각 봉 라벨이 그 봉(≤T/≤t)까지 데이터로만 산출됨이 절단·미래
  불변성 테스트로 증명됨. 따라서 전체 시계열 1회 분류 후 진입일 라벨 조회 = 절단값과 동일(룩어헤드 없음). 함수 재구현 없음.
- **일봉 게이트**: KOSPI 일봉(daily_prices `stock_code='KOSPI'`, SSOT) + 전종목 %above MA120 breadth 패널 → `classify_daily`.
  MA120 워밍업 위해 시작 이전 ~400 달력일 룩백 로드(라벨 PIT 라 안전).
- **분봉 게이트**: 15분 리샘플 패널을 일자별로 `classify_intraday`(bias 갭은 게이트에 불필요 → prev_close 미전달).
- **전략 로직 무수정**: 룰 dataclass·strategy 코드는 손대지 않음. 드라이버+게이트 모듈만 추가.

국면 라벨 분포(2021-01~2026-05, 거래일): sideways 581 / bear 420 / bull 323.
구간: **full**=2021~2026.5(전국면), **BEAR**=2022(bear187/side59, bull 0), **SIDE**=2024(side133/bear83/bull28).

---

## 2. 게이트 on/off 핵심표 (K=5, 대표청산 sl0.05/tp0.10/mh10, top_volume:50)

전략 | 게이트 | full Sharpe | full PnL | BEAR Sharpe | BEAR PnL | BEAR MaxDD | full 거래수 | BEAR 거래수
---|---|---|---|---|---|---|---|---
**elder** | none | 0.433 | **−0.421** | **−1.814** | **−0.406** | 49.3% | 706 | 106
**elder** | exclude_bear | 0.415 | −0.150 | **+0.240** | **+0.022** | **14.0%** | 510 | 39
**elder** | bull_only | 0.401 | **+0.202** | 0(차단) | 0 | — | 206 | 0
**ma5** | none | 0.409 | +0.009 | −0.578 | −0.173 | 30.2% | 800 | 138
**ma5** | exclude_bear | 0.435 | +0.036 | −0.326 | −0.060 | **19.0%** | 528 | 46
**ma5** | bull_only | 0.425 | **+0.907** | 0(차단) | 0 | — | 235 | 0
**ma20** | none | 0.524 | +1.255 | 0.719 | +0.207 | 37.0% | 602 | 109
**ma20** | exclude_bear | 0.548 | +1.336 | 0.444 | +0.079 | **18.2%** | 420 | 39
**ma20** | bull_only | 0.593 | **+1.429** | 0(차단) | 0 | — | 176 | 0
**daytrading3** | none | 0.433 | −0.464 | −0.350 | −0.123 | 29.2% | 530 | 96
**daytrading3** | exclude_bear | 0.436 | −0.519 | −0.567 | −0.099 | **21.7%** | 394 | 39
**daytrading3** | bull_only | 0.412 | **+0.306** | 0(차단) | 0 | — | 188 | 0
**close_betting** | none | 0.276 | +0.079 | **0.859** | **+0.067** | 3.75% | 22 | 9
**close_betting** | exclude_bear | 0.234 | +0.051 | 0.611 | +0.030 | 3.69% | 16 | 4
**close_betting** | bull_only | **0.501** | +0.084 | 0(차단) | 0 | — | 8 | 0

> full PnL 은 5년 누적(레버리지·재투자 단순모델이라 ma20/ma5 의 절대치는 과장; **상대비교용**). MaxDD 가 게이트 효과의
> 핵심 지표. K=3 결과는 TSV(`D:\tmp\multiverse\regime_gate\*`) 참조 — 부호·서열 동일.

### SIDE(2024) 보강 — 횡보장 효과

전략 | none Sharpe/PnL | exclude_bear | bull_only
---|---|---|---
ma20 (K=5) | 0.015 / −0.055 | 0.274 / +0.037 | (K3)**1.509 / +0.230**
ma5 (K=5) | −0.874 / −0.306 | −0.459 / −0.141 | **0.675 / +0.103**
daytrading3 (K=5) | 0.247 / +0.031 | 0.474 / +0.085 | (K3)0.592 / +0.083
elder (K=3) | 0.226 / +0.025 | **0.300 / +0.040** | −0.308 / −0.008

---

## 3. 판정 — 게이트가 약세장을 구제하는가?

### 전략별

- **elder ✅ 강한 구제**: BEAR 에서 무방비 시 Sharpe −1.81/PnL −41%/MaxDD 49% 의 참사 → `exclude_bear` 로
  Sharpe **+0.24**·PnL **+2.2%**·MaxDD **14%** 로 흑자·방어 전환. 전구간 PnL 도 −42%→−15%(exclude)→+20%(bull_only).
  거래 706→510→206. **게이트의 최대 수혜자**(elder 진입룰 자체엔 약세장 차단 장치 부재 → 국면게이트가 그 공백을 메움).
- **ma5 ✅ 구제**: BEAR PnL −17%→−6%, MaxDD 30%→19%. 전구간 PnL 은 bull_only 에서 +0.9 로 급반전(MaxDD 93%→62%).
- **daytrading3(유지윤 돌파) △ 부분구제**: BEAR 손실 −12%→−10%·MaxDD 29%→22%(완화)이나 Sharpe 는 악화(−0.35→−0.57,
  잔존 거래의 변동성↑). 전구간은 bull_only 만 흑자(−46%→+31%). **돌파전략은 bull_only 가 정답**.
- **ma20 ◐ 트레이드오프**: BEAR 무방비가 이미 흑자(Sharpe 0.72)라 exclude_bear 가 Sharpe 를 깎음(0.72→0.44).
  그러나 MaxDD 는 37%→18% 로 절반 → **위험조정·꼬리리스크 관점에선 게이트 이득**. 전구간은 단조개선(bull_only 최상).
- **close_betting ❌ 비구제(역효과)**: 종가매매는 BEAR 에서 자기완결 흑자(Sharpe 0.86)라 게이트가 수익을 깎음.
  단 bull_only 의 full Sharpe(0.50)는 최상 — **이 전략은 게이트 불요, 굳이 쓰면 bull_only 만**.

### 종합

1. **게이트는 "약세장 노출=손실"인 추세추종(elder/ma5/daytrading3)에 처방하면 BEAR 손실·MaxDD 를 확실히 줄인다.**
   특히 elder 처럼 진입룰에 약세장 차단이 없는 전략은 국면게이트가 사실상 필수 방어막.
2. **`exclude_bear` = 균형선**(약세장만 차단, sideways·bull 유지 → 거래·기회 보존하며 꼬리리스크 축소).
   **`bull_only` = 공격적**(전구간 PnL·MaxDD 최대개선이나 BEAR/SIDE 거래 대량차단 → 기회비용·표본급감 큼).
3. **거래수 trade-off 명확**: exclude_bear 전구간 ~20~30%↓, BEAR ~60%↓; bull_only 전구간 ~65%↓, BEAR 100%↓.
   거래 급감은 통계 신뢰도·자금회전을 떨어뜨리므로 "구제폭 vs 표본손실" 저울질 필요.
4. **무차별 적용 금지**: close_betting 처럼 약세장 자기방어가 되는 전략엔 게이트가 순손해.
   → 게이트는 **국면분해에서 BEAR 가 음수인 전략에 한해 선별 적용**.

---

## 4. 분봉 게이트 수행 결과 (surge_fade)

- 실행: `--book surge_fade --rule surge_fade --granularity minute --periods 2025-10,2026-04,2026-05
  --regime-gate none trend_only dir_match` → 정상 완주(연동·PIT 동작 확인).
- **결과: trend_only/dir_match 게이트가 전 거래 차단(0 trades)**. 원인은 전략 부적합이 아니라 **국면 파라미터-해상도 불일치**:
  15분 리샘플 패널에서 `classify_intraday` 의 `trendiness` 라벨이 **621봉 전부 range**(trend 0건). direction 은 변동
  (up177/down65/neutral379) 하나 dir_match 는 trendiness=trend 도 요구 → 0.
- 진단: `IntradayRegimeParams` 기본값(or_minutes=15분=15분봉 1개, vwap_slope_lb=30분≈2개 15분봉)이 **1분봉 설계**라
  15분봉에선 OR돌파+VWAP기울기+breadth극단 동시충족이 사실상 불가 → trend 라벨 미발화.
- **권고**: 분봉 게이트 유효성 검증은 ①1분봉 직접 투입(드라이버가 현재 15분 리샘플) 또는 ②15분봉용 파라미터 재튜닝
  (or_minutes/vwap_slope_lb 를 봉 단위로 재정의, breadth_hi/lo 완화)이 선행돼야 함. **별도 과제**(현 드라이버·게이트
  연동 자체는 정상 — 라벨이 안 나올 뿐). bellafiore/aziz 는 동일 한계가 예상돼 수행 보류.

---

## 4-B. 트랙B 정합화 + 재실행 완성 (2026-06-02 추가)

### 정합 방식 — 봉 간격 인지(granularity-aware)

`core/regime/regime_classifier.py` 의 `IntradayRegimeParams`/`classify_intraday` 를 **봉 간격 인지**로 수정:
- **신규 파라미터** `bar_interval_min: Optional[int]=None`. None 이면 입력 분봉 datetime 의 **중앙 간격**에서
  자동 추론(`_infer_bar_interval_min`). 1분봉→1, 15분봉→15.
- **시간 기반 윈도를 봉 개수로 환산**(`_to_bars(minutes, bar_iv)=round(min/iv), 최소 1`):
  `vwap_slope_lb`(30분) → 15분봉서 **2봉**, `vol_window`(20분) → **1봉→하한 2봉**(std 표본 보장).
  `or_minutes` 는 본래 `pd.Timedelta(minutes=)` 시간 기반이라 간격 무관(수정 불필요).
- **1분봉 하위호환**: 자동추론=1 → `_to_bars` 가 분=봉 그대로 → **기존 동작과 바이트 동일**(테스트로 증명,
  `bar_interval_min=1` 명시본과 `.equals()`). 분류기 임계(dir_thresh/breadth_hi/lo)는 **무변경** — 윈도 환산만.

### pytest 통과 (룩어헤드 포함)

`pytest tests/regime/ -q` → **17 passed**(기존 14 룩어헤드 5종 전부 유지 + 신규 3종):
절단/미래 불변성·trailing·디바운스 forward-only 불변. 신규: ①15분봉 trend 라벨 발화 ②자동추론==명시 하위호환
③15분봉 절단 불변성. **룩어헤드·PIT 불변성 깨짐 없음.**

### 트랙B 게이트 on/off (3국면 2025-10,2026-04,2026-05 · top_volume:50 · K∈{5,10} · gate 차원 스윕)

검증: 15분 리샘플서 **trend 라벨 실제 발화**(period별 trend_bars 36/81/94 — 구버그 0건 → 해소). 표는 게이트별
전 entry×exit×K 조합 평균.

전략 | 게이트 | mSharpe | mPnl | pos/N | 최악국면 평균PnL | 거래수(합) | overfit조합
---|---|---|---|---|---|---|---
**surge_fade** | none | +0.641 | **−0.244** | 1.62/3 | −0.915 | 2034 | 6/16
**surge_fade** | trend_only | **+0.827** | **−0.196** | **2.00/3** | **−0.680** | 528 | **0/16**
**surge_fade** | dir_match | +0.132 | **−0.001** | 0.50/3 | −0.002 | 32 | 8/16
**bellafiore** | none | +0.944 | **+0.457** | 1.00/3 | −0.575 | 3729 | 8/8
**bellafiore** | trend_only | +0.358 | −0.317 | 0.50/3 | −0.705 | 834 | 4/8
**bellafiore** | dir_match | −0.411 | −0.099 | 1.00/3 | −0.297 | 150 | 8/8
**aziz(orb)** | none | +1.124 | **−0.531** | 1.00/3 | −0.984 | 1331 | 2/2
**aziz(orb)** | trend_only | +0.691 | −0.562 | 1.00/3 | −0.999 | 271 | 2/2
**aziz(orb)** | dir_match | +0.476 | **−0.014** | 1.00/3 | −0.038 | 52 | 2/2

> mPnl 은 3구간 평균(레버리지·재투자 단순모델 → 상대비교용). 본 3구간엔 명시적 BEAR 라벨 구간이 없음
> (2022 부재) → "약세장 손실" 은 **최악국면 평균PnL** 로 대리. dir_match 는 거래 극소(노출 최소화)라
> 손실 절댓값만 작아질 뿐 표본부족·pos 붕괴.

### 판정 — 게이트가 분봉 데이트레이딩을 구제하는가?

- **surge_fade(페이드 역추세) △ 부분 구제 — trend_only 가 최선.** mSharpe +0.641→**+0.827**, mPnl −0.244→**−0.196**,
  **pos 1.62→2.00/3**(강건성↑), **overfit 6→0**(과적합 제거), 최악국면 −0.915→−0.680(꼬리 완화). 거래 2034→528(−74%).
  **단 여전히 mPnl 음수** — 게이트는 손실을 줄이지만 흑자 전환은 못 함. dir_match 는 거래 32개로 과축소(pos 0.5, 손실≈0
  이나 표본부족·과적합 8/16) → 처방 부적합.
- **bellafiore(fade_vwap) ❌ 비구제(역효과).** 무게이트가 유일 흑자(mPnl +0.457)인데 trend_only/dir_match 가
  **흑자를 −0.317/−0.099 로 파괴**(mSharpe도 0.94→0.36→−0.41). fade_vwap 은 **range 장(평균회귀)에서 작동**하는데
  trend 게이트가 그 본령(range 봉)을 잘라내 자기모순 → 게이트 금지. (단 none 자체가 pos1/3·overfit8/8 = 단일구간
  거품, 게이트 무관하게 채택부적격.)
- **aziz(orb, 돌파) ◐ dir_match 만 손실 축소.** none/trend_only 는 mPnl −0.53/−0.56 로 대손, **dir_match(trend+up)
  가 −0.014 로 손실 거의 제거**(거래 1331→52). 그러나 거래 52개·pos 1/3·overfit 2/2 = **표본부족 회피일 뿐 알파 아님**.

**종합**: 분봉 데이트레이딩에서 국면게이트는 **일봉처럼 명확히 구제하지 못한다.** ①페이드 계열(surge_fade/bellafiore)은
trend 게이트가 전략 본령(range)과 상충 — surge_fade 만 mSharpe·강건성·과적합은 개선하나 **PnL 흑자전환 실패**,
bellafiore 는 **흑자 파괴**. ②돌파(orb)는 dir_match 로 손실만 줄지만 거래 과축소로 알파가 아닌 **노출회피**. 즉
**게이트는 분봉 단타를 "덜 잃게"는 해도 "돈 벌게"는 못 한다** — 분봉 3책 전멸(MEMORY 정본) 결론과 일치.
**처방 가치는 surge_fade trend_only(강건성·과적합 개선)에 한정**, 나머지는 게이트 불요/금지.

### 미해결

- 본 3구간(2025-10/2026-04/2026-05)에 **명시 BEAR 라벨 구간 부재** → "약세장 손실 개선" 직접 측정은 트랙A(2022 포함)에
  한정. 트랙B 약세장 검증은 분봉 데이터가 2025-09~ 만 존재해(minute_candles 커버리지) 불가 — 최악국면 PnL 로 대리.
- dir_match 의 극소 거래(32~52)는 통계신뢰 부족 → 표 수치는 방향성 참고만.

---

## 5. 룩어헤드 안전성 확인

- `regime_at`/`classify_daily`/`classify_intraday` 를 **그대로 호출**(게이트 모듈에서 국면 재계산·룰 변형 없음).
- 전체 시계열 1회 분류 후 진입일 라벨 조회 → 절단 시계열 라벨과 동일(절단·미래 불변성 테스트 14/14 통과로 증명).
- 진입봉 i 라벨은 그 봉 datetime 으로 조회(i 까지의 누적). breadth/RV/장중누적 모두 trailing.
- `tests/regime/test_regime_no_lookahead.py` 회귀: **14 passed**(분류기 무수정 확인).

---

## 6. 산출물

- 드라이버: `scripts/book_portfolio_multiverse.py` (`--regime-gate` 차원, 게이트 모듈 `_build_daily_regime_map`/
  `_build_minute_regime_maps`/`_filter_cache_*`).
- 결과 TSV: `D:\tmp\multiverse\regime_gate\<strat>_<window>\book_portfolio_*.tsv` (전 조합 gate 열 포함).
- 분봉: `D:\tmp\multiverse\regime_gate\surge_fade\`.
