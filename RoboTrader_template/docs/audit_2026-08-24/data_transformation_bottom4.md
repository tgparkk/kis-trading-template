# 데이터 → 전략 도달·변형 경로 검수 — 하위 4전략 편 (2026-08-24)

> 대상 4전략: `rs_leader` · `book_pullback_ma20` · `book_envelope_200d` · `deep_mr_dev20`
> 방법: 코드 독해 + `kis_template` SQL + 라이브 로그(8/18·19·20·21) grep. **코드 수정 0줄 · 라이브 트리 python 실행 0회 · git 쓰기 0회.**
> 기준일: 2026-08-24 작성. 라이브 실측은 **2026-08-21 세션** 기준(8/24 로그는 블록 버퍼링으로 미완성).
> 정본(방법·표 형식) = `docs/audit_2026-08-23/data_transformation_4strategies.md`(이하 «08-23 편»). 08-23 편의 결함 번호는 `D1`~`D9`(붙여쓰기), 이 문서의 신규 결함은 `D-1`~(하이픈)으로 구분한다.
> 표기: 「독해」= 코드 독해만 · 「SQL」= DB 재현 · 「로그」= 라이브 로그 실측. 자기 확신 표현은 쓰지 않는다.

---

## §0 한줄 결론

> 🔎 **독립 검증(2026-08-24, 별도 verifier — `_verify_data_transformation_bottom4.md`)**: 검증 항목 **9**(세부 40+) · REFUTED **2**(D-3 「≤0.1%·방향 확정」 · `001210` 시그널 6회) · PARTIAL **2**(D-1 원인 · 라인 번호) · 나머지 전건 SUPPORTED(손계산 4/4 · 가드 16/14/17/4 · D-2·D-4·D-5 · reason 분류 전건). 정정 반영: **D-1 원인을 「미조정 감자/액면병합(adj_factor 미기입 · `corp_events` 감자 유형 부재, 8종목 중 7 미수록)」으로 교체**(«정지 패딩 뒤 재개»는 동반 현상으로 강등, 영향 범위를 130봉 이상 창을 쓰는 모든 룰로 확장, `data_sanity.py:29-31` 이 이미 명시한 예외임을 병기) · **D-3 을 「score 사후 재현 불가(≤0.94%, 0.1% 초과 4/20) · 스캔 뒤 기록자 둘(09:00:54 로더 · 15:45:04 EOD)」로 교체**(「창 A/B 가 다른 volume 을 본다」는 가설로 강등, §5-2 와의 자기모순 해소) · `001210` 6회→**4회** · 라인 ma20 `:133` · rs_leader `:91` · 부록 `sed`→`grep`, 로그 라인 `:535-790`. **등급 변경 없음.**

**4전략의 룰 산술은 두 창에서 «불변»이다 — 하지만 rs_leader 의 후보 «순위»와 «진입 조건»은 데이터 아티팩트(미조정 감자/액면병합 — adj_factor 미기입)가 만든다.**

1. **룰은 창에 둔감하다** (08-23 편 D1 의 EMA 문제는 이 4전략에 «없다»): rs_leader 는 SMA20/60 + 61봉 전 종가, ma20 은 SMA20 + 31봉, envelope 는 자체 230봉 조회, deep_mr 은 룰이 스스로 **34봉으로 절단**(`rule.py:35,38`)한다. 손계산 4/4 가 창 A·B 어느 쪽 봉 수로 계산해도 같은 값을 낸다.
2. **rs_leader 의 RS 랭킹은 «미조정 감자/액면병합» 랭킹이다** (🔴🔴 D-1): 08-20 스냅샷 top-10 중 **8종목**이 130봉 창 안에 하루 **+258% ~ +942%** 점프를 갖고, 1위 `049080` 의 score 16.94 = 8,200/457 − 1 이 그 점프다. 🔎 검증 실측: 점프는 실제 주가 상승도 정지 패딩 자체도 아니다 — **매매정지 «중»에 `daily_prices.market_cap` 이 ÷5/÷10 으로 줄고 재개 시가가 정확히 ×5/×10**(002680 ×5.00 · 090150 ×10.00) = 감자·액면병합의 전형인데 130봉 전 구간 `adj_factor` 가 1/NULL(미기입)이고 `corp_events` 에는 8종목 중 **1건**(090150)만 있다(«감자» 유형 자체가 없다). «정지 패딩 11~18행 뒤 재개»는 병합 변경상장 정지 기간의 **동반 현상**이다. 진입 3조건(종가>MA60·MA20>MA60·60일 수익>0)은 점프 뒤 «자동으로» 참이 되고, 위생 가드는 하락만 본다 — `utils/data_sanity.py:29-31` 이 「미조정 액면병합 = 상승 방향 제외 사유」로 **이미 명시**한 예외다. 8/21 rs_leader 매수 4건 중 **3건**(`049080`·`011090`·`227950`)이 이 종목군. 영향은 rs_leader 만이 아니라 **130봉 이상 창을 쓰는 모든 룰**(envelope 230 · minervini 260 · elder 160)에 같은 종목이 상승 아티팩트로 들어간다. 08-23 편 D9(`001510` adj_factor 경계)의 «상승 방향» 형태.
3. **`screener_snapshots` 의 volume 기반 score 는 사후 SQL 로 재현되지 않는다** (🟡 D-3): ma20 18/20 불일치 · envelope 5/6, 상대 드리프트 **≤0.94%**(0.1% 초과 4/20) — 종가 기반 score(rs_leader·deep_mr)는 소수점까지 일치. 스캔(09:00:28~44) «뒤»에 volume 을 덮어쓰는 기록자가 **둘** 있다: 후보 로더의 종목당 103봉 재수집(09:00:54~09:01:08)과 15:45:04 EOD 배치(현재 행의 `updated_at` 은 전부 후자). 어느 쪽이 드리프트를 만들었는지는 현재 DB 로 구분 불가 ⇒ 「창 A 와 창 B 가 같은 날 다른 volume 을 본다」는 **가설**(09:01 시점 값이 남아 있지 않다).
4. **청산 가드 순서**: `a736065` 가 고친 3전략 중 rs_leader·ma20 가 이 편에 속하고, deep_mr 는 06-12 에 이미 «앞»이다. **envelope 만 «뒤»**(🔴 D-4) — envelope 의 고유 청산 5건은 **5/5 전부** `position_monitor` 의 분봉(폴링) 경로로 나갔고, 그중 2건은 `position_monitor` 자체의 09:00~09:05 손절 유예를 우회했다(08-18 09:02:37 · 08-19 09:02:40).
5. **envelope 의 위생 가드가 룰의 창을 못 덮는다** (🔴 D-5): 룰은 자체 230봉을 보는데 가드는 프레임워크 80봉에만 걸린다. A\B = 4종목(스크리너는 뺐는데 진입은 통과).

---

## §1 4전략 × 창 표

### 1-1. 창 A / 창 B 의 봉 수·창 정의 (독해 + 로그)

| 전략 | 룰 최소 봉 수 (파일:라인) | 룰이 «실제 쓰는» 봉 | 창 A 행 수 | 창 B 봉 수 | A 위생가드 창 | B 위생가드 창 | 룰의 창 의존 |
|---|---|---|---|---|---|---|---|
| `rs_leader` | **61** (`rule.py:26` `len < ma_long+1` · `<= abs_lb`) + 라이브 게이트 `min_daily_bars=65`(`config.yaml:17`) | MA20·MA60·61봉 전 종가 → **61봉**. score 용 `rs_lb=120` 은 **121봉**(스크리너 전용, `screener.py:52-54`) | **130행** (`screener.py:19`) | **78~84봉** (8/21 실측 80) | 130행 (sanity_window=None) | 80봉 | **불변**(61봉 ≤ 78). 단 score(121봉)는 **창 B 에서 원리적으로 계산 불가** — 08-23 편 D4 와 같은 구조 |
| `book_pullback_ma20` | **32** (`haru_silijeon/rules_daily.py:98` `max(20,30)+2`) + 게이트 35(`config.yaml:25`) | SMA20 + 직전 30봉 고저 → **31봉** | **90행** (`screener.py:14`) | **78~84봉** | 90행 | 80봉 | **불변** |
| `book_envelope_200d` | **202** (`trading_strategy_book/rules.py:65`) — on_tick 게이트는 **5**(`min_gate_bars`, `strategy.py:57-63`) | 200봉 최고 종가 + SMA10 + 직전 5봉 거래대금 → **200봉** | **230행** (`screener.py:14`, end=D-1) | **자체 조회 230행**(`strategy.py:241-242` `QuantDailyReader.get_daily_prices(end_date=오늘, days=230)` → 오늘 행 드롭 `:250-252` ⇒ 실효 **229**) + 프레임워크 80봉(게이트·가드·청산용) | 230행 | **80봉** — 가드는 `base.py:645` 의 프레임워크 데이터에만 걸리고 룰이 보는 229봉엔 «안 걸린다» | **불변**(룰 입력 자체가 두 창 모두 QuantDailyReader). ⇒ 4전략 중 유일하게 「같은 SQL·같은 봉 수」. 대신 가드가 어긋난다(D-5) |
| `deep_mr_dev20` | **34** (`rule.py:35` `max(20,14)+10`) + 게이트 35(`config.yaml:36`) | `close.iloc[-34:]` 로 **스스로 절단**(`rule.py:38`) → MA20·RSI14 모두 34봉 | **45행** (`screener.py:20`) | **78~84봉** | 45행 | 80봉 | **불변**(설계에 의해). 🔎 RSI 는 `ewm(alpha=1/14, adjust=True)` 이라 원리상 창 길이에 민감한데 절단이 그것을 «고정»한다 — §2-④ 에서 34봉 26.2 vs 45봉 28.0 |

- 창 B 의 「80봉」 실측: 8/21 로그 `일봉 80건` **1,194회** · `일봉 36건` **36회**(전부 `475040`, 신규상장 37행·ma20 후보 rank 5) · 그 외 0회 (`grep -o "일봉 [0-9]*건" logs/robotrader_template_20260821_074007.log | sort | uniq -c`).
- `475040`: DB 전체 **37행**(2026-06-30~), 창 A(90행 LIMIT) 도 37행, 창 B 36봉(당일 드롭) ⇒ 룰 32·게이트 35 통과 → 8/21 09:08:31 ma20 매수 시그널 발화(로그). **두 창이 같은 37봉을 본 사례**(결손형이 아니라 신규상장형).
- 창 A 유니버스 크기(SQL, 2026-08-20 `market_cap IS NOT NULL` 2,763종목에 base_filter 적용): rs_leader **791**(tv≥10억) · ma20 **635**(tv≥10억 ∧ 시총≤3조) · envelope **791**(tv≥10억) · deep_mr **267**(tv≥100억). 로그엔 minervini 만 유니버스 수를 찍는다(`screener.py:187`); 이 4전략은 `finalize_scan` 미구현이라 **로그 대조 불가**(독해+SQL 뿐).

### 1-2. 부족하면 룰이 어떻게 반응하나 (독해)

| 전략 | 봉 부족 시 | 파일:라인 | 로그 |
|---|---|---|---|
| 공통(창 B) | len(data) < min_len → 스킵 | `strategies/base.py:615` | `[신호없음] … 일봉 N건 < min_len=M` (10분 throttle) — 8/21 4전략 **0건**(전부 80봉) |
| rs_leader | `len < 61` 또는 `<= 60` → 조용히 None · `evaluate_entry` 는 `len < 65` → False | `rule.py:26` · `strategy.py:123` | **없음** |
| rs_leader(score) | `len(close) <= 120` → None (스크리너에서 후보 탈락) | `screener.py:52-53` | **없음** — 121행 미만 종목은 «룰 통과해도» 후보가 안 된다(신규상장 ~6개월) |
| ma20 | `len < 32` → False · `_ma` NaN/≤0 → False | `rules_daily.py:98-102` | **없음** |
| envelope | `len < 202` → False · 스칼라 NaN → False | `rules.py:65-67, 87-89` · `strategy.py:262` | **없음** — 자체 조회 실패는 `warning`(`strategy.py:244`) |
| deep_mr | `len < 34` → None · MA NaN/≤0 → None · RSI NaN → None | `rule.py:36, 41, 48` | **없음** |

### 1-3. 당일 미확정봉 (독해 + SQL)

| | 창 A | 창 B(프레임워크) | 창 B(envelope 자체 조회) |
|---|---|---|---|
| 마지막 봉 | D-1 확정봉 — `scan_date=D-1` + SQL `date <= scan_date` (`quant_daily_reader.py:177`) + `_prepare_frame` 재컷(`_rule_screener_base.py:169`) | D-1 확정봉 — SQL 상한 없음 → `_drop_unconfirmed_today_bar` 1행 제거(`core/trading_context.py:143-174`) | D-1 확정봉 — `end_date=오늘` 로 LIMIT 230 뒤 `date==오늘` 마스크 제거(`strategy.py:250-252`) ⇒ 오늘 행이 있으면 **229봉** |

⇒ 세 경로 모두 같은 「마지막 봉」(08-23 편 §1-3 과 동일). envelope 의 자체 조회는 드롭 «전»에 LIMIT 을 걸어 오늘 행이 1행을 «먹는다» — 룰이 200봉만 쓰므로 무해(독해).

### 1-4 / 1-5. volume·가격 조정 — 08-23 편과 동일 (양 경로 `volume×COALESCE(adj_factor,1)`, 가격 무조정)

- 창 A: `quant_daily_reader.py:157-159` · 창 B: `db/repositories/price.py:128-133` · envelope 자체 조회: 창 A 와 **같은 함수**.
- 손계산 4건(§2)의 창 안 adj_factor 는 전부 1 또는 NULL ⇒ 수치로는 판별 못 함(08-23 편 §5-1 과 같은 한계).

### 1-6. NaN / 결손 / 패딩 (SQL)

| 항목 | 창 A | 창 B | 이 4전략 실측 |
|---|---|---|---|
| 정지 패딩(OHLC 고정·volume 0) | 통과(가드는 하락만) | 통과 | 08-20 스냅샷 top-10 기준 창 B(04-23~08-20) 패딩 보유: **rs_leader 9/10**(13·16·11·18·16·0·16·15·2·15행) · **envelope 1/6**(`001210` 11행) · **ma20 0/10** · **deep_mr 0/1**(`214150`) |
| 결손 | LIMIT n → 더 과거까지 | 달력일 → 봉 감소 | rs_leader `rs_lb=120` 은 결손이 있으면 «더 오래된 종가»를 기준가로 삼는다(창 A 만) |
| 일봉 결손 로그 | 없음 | min_len 미달 때만 | 8/21 0건 |

### 1-7. 위생 가드 창 — 제외 집합 (SQL, 2026-08-20 유니버스 2,763종목)

| 가드 창 | 제외 종목 수 | 누구의 창인가 |
|---|---|---|
| 45행 | **13** | deep_mr 창 A |
| 80봉(달력 120일, 04-23~) | **36** | 전 전략 창 B (08-23 편 36 과 일치) |
| 90행 | **38** | ma20 창 A (08-23 편 38 과 일치) |
| 130행 | **40** | rs_leader 창 A |
| 230행 | **41** | envelope 창 A |

base_filter 적용 후 «집합 차»(A\B = 스크리너는 뺐는데 진입은 통과 · B\A = 후보는 되는데 진입에서 막힘):

| 전략 | base_filter 통과 | \|A\| | \|B\| | **A\B** | **B\A** | 8/21 로그 A 발화 |
|---|---|---|---|---|---|---|
| rs_leader (A=130) | 791 | 16 | 13 | **3** | 0 | **16** ✅ 일치 |
| ma20 (A=90) | 635 | 14 | 13 | **1** | 0 | **14** ✅ 일치 |
| envelope (A=230) | 791 | 17 | 13 | **4** | 0 | **17** ✅ 일치 |
| deep_mr (A=45) | 267 | 4 | 5 | 0 | **1** | **4** ✅ 일치 |

- 🔑 SQL 이 8/21 로그의 전략별 가드 발화 수(16/14/17/4, `grep "미조정 기업행위 의심, 후보 제외"`)를 **4/4 정확히 재현**했다 — 창 A 가드의 창 정의(행 수)가 코드대로 돈다는 실측.
- 방향: rs_leader·ma20·envelope 는 **A 가 더 엄격**(08-23 편의 elder·minervini 형), deep_mr 만 **B 가 더 엄격**(daytrading·ma5 형). deep_mr 의 B\A 1종목은 45행 밖(≈04-23~06-10 구간)에 절벽이 있는 종목이다.
- 창 B 가드 발화: 8/21 `진입 제외` **0건**(08-23 편과 동일).

### 1-8. `screener_snapshots` 의 score 정체 (독해 + SQL)

| 전략 | score 정의 (파일:라인) | 08-20 스냅샷 값 범위 | SQL 재현 | 판정 |
|---|---|---|---|---|
| rs_leader | `last/close[-121] − 1` = 120봉 수익률 (`screener.py:54-62`) | 0.84 ~ **16.94** | `049080` 16.943107221006564 **소수점 일치** | 정의는 문서대로. 그러나 상위 8/10 이 스케일 점프 아티팩트(§3 D-1) |
| ma20 | 최근 20봉 평균 volume (`screener.py:43`) — 패딩 0 포함 | 244,568 ~ 14,130,942 | **18/20 불일치**(Δ 1.5 ~ 11,351) | D-3 |
| envelope | 당일 `close×volume` (`screener.py:41-43`) | 13.9억 ~ 655.7억 | **5/6 불일치**(Δ 3~5,265주) | D-3 |
| deep_mr | \|(close−MA20)/MA20\| (`screener.py:50-54`) | 0.2099 (08-19 1건) | `214150` 0.20993494973388527 **소수점 일치** | 정의대로 |

- elder 식 `close` 폴백(08-23 편 D6)은 **4전략 모두 없다**(독해: 삼항식·`"trading_value" in df` 검사 없음).
- 종가 기반 score 2종은 정확 재현, volume 기반 2종은 전건 불일치 ⇒ 불일치의 원인은 «volume 컬럼의 사후 변경»이다(§3 D-3).

### 1-9. 청산 — timeframe 가드 위치와 실측 (독해 + SQL + 로그)

| 전략 | 가드 위치 | 결과 | `a736065`(06-24) 포함 여부 | 고유 청산 비율(전기간, `virtual_trading_records` SELL reason 분류) | 08-14~ |
|---|---|---|---|---|---|
| `rs_leader` | `strategy.py:86-90` — positions 분기(`:91`) **앞** | 분봉 차단 | **포함** | 11/114 (9.6%) — 그중 06-12 `040350 손절 (-9.3%)` 1건은 수정 «전» 분봉 경로 | 3/11 |
| `book_pullback_ma20` | `strategy.py:133-134` — positions 분기(`:137`) **앞** | 차단 | **포함** | 7/97 (7.2%) | 0/6 |
| `book_envelope_200d` | `strategy.py:140-141` — positions 분기(`:131`) **뒤** | **열림** | 미포함 | 5/45 (11.1%) — **5/5 전부 `position_monitor` 경유**(§3 D-4) | 2/6 |
| `deep_mr_dev20` | `strategy.py:89-93` — positions 분기(`:94`) **앞** | 차단 | 미포함(06-12 수정분, 커밋 메시지 명시) | 3/46 (6.5%) — 3건 전부 06-12 09:06~09:13 «수정 전» 분봉 경로(`MA20×0.9 회복`) | 0/0 |

- reason 분류 규칙: `손절 실행`/`목표 익절`/`보유기간`/`장기보유`/`트레일링 스톱` = `position_monitor` 범용 · `MA…`/`손절 (`/`익절 (`/`손절 도달`/`익절 도달`/`최대 보유일` = 전략 고유. `other` 0건.
- 창 C-1(일봉 청산)은 `base.py:694-695` 가 `ctx.get_daily_data()` 를 다시 부르므로 **창 B 와 같은 프레임**(D-1 종가). rs_leader 의 `ma_break` 는 그 프레임의 `close.iloc[-20:].mean()` — 진입 룰의 MA20 과 **같은 값**(§2-①).

### 1-10. 진입 밴드·K (독해, X-2·X-3 대응 — 이 편은 표만)

| 전략 | `entry_band_up_pct` | `entry_band_down_pct` | 파일:라인 | `max_positions` | 폴백 수용 |
|---|---|---|---|---|---|
| rs_leader | 0.03 | **없음** | `strategy.py:58-60` | 10 | True |
| ma20 | 0.01 | = sl 0.08 | `strategy.py:91-93` | 5 | True |
| envelope | 0.03 | **없음** | `strategy.py:88-90` | 5 | True |
| deep_mr | 0.01 | = sl 0.07 | `strategy.py:60-62` | 5 | **False** |

밴드 거절은 `core/trading_decision_engine.py:412,415` 가 사유를 «반환»만 하고 `bot/trading_analyzer.py:92` 가 `debug` 로 찍는다 — 8/21 INFO 로그에 `밴드` **0건**(08-23 편 X-2 와 동일). 예: 8/21 envelope `001210` 매수 시그널 **4회**(09:01:44·09:06:41·09:11:40·09:16:45 — 🔎 초안 «6회»는 rs_leader 4회와 합산한 오독, 정정) 발화·원장 매수 0건 — 기준가 7,460 vs 8/21 시가 8,000(+7.2%) 이라 밴드 초과로 «추정»되나 **로그로 확인 불가**.

---

## §2 손계산 대조 (전략당 1건) — **4/4 일치**

기준: `virtual_trading_records`(is_test=true) 의 reason 또는 로그 `매수 시그널` 문자열 = 창 B 코드 출력. SQL 은 매수 시점의 마지막 «확정» 봉(D-1)까지로 맞췄다. `adj_factor` 는 4건 모두 1/NULL.

### ① rs_leader — `049080` (2026-08-21 09:04:49 시그널 → 원장 BUY 2147 @7,780 · **1초 뒤** SELL 2148 @7,760)

| 값 | 코드 출력 | SQL 재계산(≤08-20, 80봉) | 판정 |
|---|---|---|---|
| close | 8,200 | 8200 | ✅ |
| MA20 | 8345 (원장 매도 reason) | 8345.0 | ✅ |
| MA60 | — | 5325.38 | 종가 > MA60 ✅ · MA20 > MA60 ✅ |
| 61봉 전 종가 / 60일 수익 | — | 1458 / **+462.4%** | > 0 ✅ |
| 매도: `cur_close < MA20` | `MA20 이탈 (종가 8200 < MA 8345)` | 8200 < 8345 | ✅ — **매수·매도 동시 참**(기존 단서 SQL 재현) |
| 스크리너 score | 16.943107221006564 | 8200/457 − 1 = 16.9431… (`ref120` = 2026-02-24 종가 457) | ✅ 소수점 일치 |

🔎 이 종목의 60일 수익 +462% 와 score 1,694% 의 정체: 2026-06-10~06-26 **993원 고정·volume 0 패딩 13행**(매매정지) 중 06-19 에 `market_cap` 84.3B → **8.43B(÷10)** → 06-29 시가 9,500(×9.57)·종가 **7,770원(+682%)** 재개(`daily_prices` 실측, 🔎검증) = **미조정 10:1 병합/감자**, `adj_factor` 130봉 전 구간 1/NULL. MA60(5,325) 은 병합 이전 ~1,000원대와 이후 5,000~11,000원대의 평균이라 «종가 > MA60» 이 재개 뒤 자동으로 참이 된다. → §3 D-1.

### ② book_pullback_ma20 — `006340` (2026-08-21 09:08:30 시그널 → 원장 BUY 2152 @13,800)

| 조건 | 코드 출력 | SQL 재계산(≤08-20) | 판정 |
|---|---|---|---|
| MA20 | 13926.00 | 13926.0 | ✅ |
| last low | 13940.00 | 13940 | ✅ |
| last close | 14530.00 | 14530 | ✅ |
| ① surge 30봉(마지막 제외) 저→고 ≥ 25% | — | (16370 − 9210)/9210 = **77.7%** | ✅ |
| ② touch: \|low − MA20\|/MA20 ≤ 2% | — | 0.10% | ✅ |
| ③ above: close ≥ MA20×0.98 | — | 14530 ≥ 13647.5 | ✅ |
| ④ 양봉 | — | open 14280 < close 14530 | ✅ |
| 스크리너 score(20봉 평균 volume) | **14,130,942.25** | **14,136,889.2** (Δ +5,946.95 ⇒ 20봉 합 +118,939주) | ❌ → §3 D-3 |

원장 문자열: `daily_ma20_pull ma20=13926.00 low=13940.00 close=14530.00`. 룰 산술 7/7 일치, score 만 불일치.

### ③ book_envelope_200d — `161890` (2026-08-21 09:01:44 시그널 → 원장 BUY 2144 @136,500)

| 조건 | 코드 출력 | SQL 재계산(≤08-20, LIMIT 230 = 230행) | 판정 |
|---|---|---|---|
| A 200봉 최고 종가 | — | max200 = 137800 = close_t | ✅ |
| B env_upper = SMA10×1.10 | 134981 | 122710 × 1.1 = 134981.0 | ✅ |
| C 양봉 | — | 126600 < 137800 | ✅ |
| D vol ≥ vol_prev | — | 411,216 ≥ 295,464 | ✅ |
| E close > (H+L)/2 | — | 137800 > 132550 | ✅ |
| F 직전 5봉 거래대금 평균 ≥ 5,000M | 137937M | 137,937.28M | ✅ |
| G 갭 < 7% | — | open 126600 < 127800×1.07 | ✅ |
| H 전일 급등 < 10% | — | 127800 < 129700×1.10 | ✅ |
| I 시가 대비 +3% | gain=8.8% | 8.85% | ✅ |
| 스크리너 score(close×volume) | 56,665,013,600 | 56,665,564,800 (Δ = **4주**) | ❌ → §3 D-3 |

원장 문자열: `envelope_200d_high close=137800 >= env_upper=134981 200d_high vol>=prev value=137937M gain=8.8%`.

### ④ deep_mr_dev20 — `214150` (2026-08-20 09:14:25 → 원장 BUY 2133 @33,550, 08-19 스냅샷 rank 1)

| 값 | 코드 출력 | 재계산(≤08-19) | 판정 |
|---|---|---|---|
| close / MA20 | — | 33400 / 42275 | — |
| (close−MA20)/MA20 | `MA20 이탈 -21.0%` | **−20.99%** ≤ −20 | ✅ |
| RSI14 — 룰의 34봉 절단(`rule.py:35,38`), `ewm(alpha=1/14, adjust=True, min_periods=14)` 순수 python 재현 | (미출력) | **26.22** < 30 | ✅ |
| 같은 RSI 를 45봉(창 A)으로 | — | 27.98 | 절단이 없었다면 창에 따라 값이 다르다 — 절단이 그것을 «고정» |
| 스크리너 score | 0.20993494973388527 | 0.20993494973388525 | ✅ (부동소수 마지막 자리) |

🔎 RSI 의 pandas `ewm(adjust=True)` 는 가중치를 정규화하므로 창 길이에 따라 값이 움직인다(34봉 26.2 → 45봉 28.0). 룰이 34봉으로 스스로 절단하기 때문에 창 A(45)·창 B(80)·백테스트가 **같은 값**을 낸다. 「RSI14」 라는 이름과 달리 **«34봉 창 RSI»** 이다 — 결함이 아니라 정합의 «원인»이다(독해 + 순수 python).

---

## §3 결함 후보 (결정은 사장님 몫)

| ID | 등급 | 내용 | 영향 | 근거(파일:라인 · SQL · 로그) |
|---|---|---|---|---|
| **D-1** | 🔴🔴 | **rs_leader 의 후보 순위와 진입 3조건을 «미조정 감자/액면병합 점프»가 만든다 — adj_factor 미기입 + `corp_events` 감자 유형 부재(8종목 중 7 미수록).** 08-20 top-10 중 **8종목**이 130봉 창 안에 하루 +258%~+942% 점프를 갖는다: `049080` 06-29 +682% · `226340` 05-27 +310% · `001210` 07-31 +360% · `090150` 08-18 +942% · `011090` 05-20 +325% · `227950` 05-28 +299% · `002680` 07-10 +329% · `014990` 06-26 +258%. 정상은 `189330`(+30%)·`079650`(+30%) 둘뿐. score 1위 16.94 = 8200/457−1. 🔎 원인(검증 실측 `v_series.sql`): 가격이 고정된 정지 기간 «안에서» `market_cap` 이 정수배로 준다(049080 84.3B→8.43B ÷10 · 090150 20.9B→2.09B ÷10 · 001210 55.3B→11.06B ÷5 · 002680 12.1B→2.42B ÷5 · 011090 ÷5.08 · 014990 ÷5; 226340·227950 은 mcap 미반영·×4.6 추정) 뒤 재개 시가가 배율만큼 뛴다(002680 **×5.00** · 090150 **×10.00**) = 상장주식수 감소가 먼저 반영되는 **감자·액면병합의 전형**. 130봉 전 구간 `adj_factor` 는 1/NULL ⇒ 과거 구간에 ×5·×10 을 곱했어야 할 보정이 비어 있다. `corp_events` 는 `090150` `split/merge 2026-08-14 주권매매거래정지해제(액면병합 주권 변경상장)` **1건뿐**, event_type 4종(rights_issue·split·bonus_issue·administrative)에 «감자» 유형이 없다. «정지 패딩 11~18행 뒤 재개»는 변경상장 매매정지의 **동반 현상**이지 원인이 아니다(08-23 편 D3 「정지 패딩 분모」와는 **다른 결함**). 점프 뒤에는 종가>MA60·MA20>MA60·60일 수익>0 이 **자동으로** 참이다(MA 가 점프 전후 평균). 가드는 «하락»만 보며 `utils/data_sanity.py:29-31` 이 「상승 쪽 초과(신규상장, **미조정 액면병합** 등)는 오탐 위험으로 제외」라고 **이미 명시** ⇒ 신규 관측이 아니라 문서화된 예외의 **정량화**(rs_leader 상위가 그 예외로 통째로 채워진다). 8/21 rs_leader 매수 4건 중 **3건**(049080·011090·227950)이 이 군. 같은 메커니즘이 envelope 의 「200일 신고가」도 만든다: `001210` 은 07-31 점프 «이전» 197봉 최고 종가가 **1,389** 라 재개 뒤 어떤 종가도 신고가다(8/21 시그널 4회). **영향 범위 = 130봉 이상 창을 쓰는 모든 룰**(rs_leader 130 · elder 160 · envelope 230 · minervini 260) · **수정 위치 = 전략이 아니라 데이터 계층**(adj_factor 기입 / corp_events 감자 유형) — 08-23 편 D9 계열의 상승 방향형. | rs_leader 최우선 · envelope · 130봉+ 창 전 룰 | SQL(`q_rs.sql`·`q_jump.sql`, 부록 · 검증 `v_series.sql`) · `daily_prices` `049080` 06-10~06-29(`market_cap` 06-19 ÷10) · `001210` 07-23(÷5)~07-31 · `corp_events` `090150` · `data_sanity.py:29-31` · 로그 8/21 `매수 시그널` · 원장 2147·2154·2161 |
| **D-2** | 🔴 | **rs_leader 매수·매도 동시 참 — SQL 재현.** 창 B 와 창 C-1 이 같은 프레임(`base.py:614`·`:695` 둘 다 `get_daily_data`)이라 진입의 MA20(=8345)과 청산 `ma_break` 의 MA20 이 같은 값이고, `cur_close < MA20` 이면 매수 직후 매도. 08-20·08-21 `049080` 1초 왕복(원장 2121→2122 · 2147→2148). MA20~MA60 사이 종가는 매수 3조건 + 매도 조건 동시 성립. | rs_leader | `strategy.py:145-147` · 원장 · §2-① |
| **D-3** | 🟡 | **`screener_snapshots` 의 volume 기반 score 는 사후 재현이 안 된다 — 스캔 «뒤»에 volume 을 덮어쓰는 기록자가 둘이다.** 실측: ma20 score **18/20 불일치**(Δ 1.5~11,351 /봉평균, 최대 20봉 합 +227k주) · envelope **5/6 불일치**(Δ 3~5,265주) · 종가 기반(rs_leader·deep_mr) 은 소수점 일치. 상대 드리프트 **≤0.94%**(462860 0.940% · 00680K 0.153% · 003280 0.109% · 001200 0.102% — 0.1% 초과 **4/20**, 🔎 초안 «≤0.1%» 정정), 순위 변화 0(08-20 기준). 기록자 ①: 스캔 09:00:28~09:00:44(`screener_snapshots 저장` 7줄, 로그 :394-486) 뒤 후보 로더가 종목당 103봉을 재수집·`ON CONFLICT DO UPDATE`(`price.py:95-98`) 저장 09:00:54~09:01:08(`일봉 데이터 DB 저장 완료`, 로그 :535-790). 기록자 ②: 15:45:04 EOD 배치 — 현재 행의 `updated_at` 은 006340·161890·462860 전부 `2026-08-21 15:45:04.905`(🔎 검증). ⇒ 「스냅샷 ≠ 현재 DB」의 원인이 ①인지 ②인지 **현재 DB 로는 구분 불가**하고, 창 B(09:01 읽기)가 창 A 와 «다른 volume 을 봤다»는 것은 09:01 시점 값이 남아 있지 않아 **가설**이다(초안의 「방향 확정」 철회 — §5-2 와 정합). 확정된 것은 (a) 두 기록자가 코드·로그상 실재한다 (b) `screener_snapshots.score` 는 volume 룰에서 사후 재현 불가 (c) 08-23 편 §3 손계산의 「창 안 volume 이 같다」 전제는 «어느 시점의 표를 읽느냐»에 따라 봉 단위로 어긋날 수 있다. 원인 후보(시간외 거래량 반영 차이)는 미검증. | 8전략 공통(volume 룰) | 로그 8/21 :394-486(스캔) / :535-790(저장) · `price.py:95-98` · SQL(`q_score.sql` · 검증 `v_d3.sql` `updated_at`) · 메모리 「09:00 103봉 덮어쓰기」·「`updated_at` 매일 재도장」 |
| **D-4** | 🔴 | **envelope 청산 timeframe 가드가 positions 분기 «뒤»** (`strategy.py:131` 매도 → `:140` 가드) ⇒ `position_monitor.py:359` 의 분봉(≈13초 폴링) 경로가 열려 있고, `generate_signal` 에 min_len 검사도 없다. 실측: envelope 고유 청산 **5/5** 가 `position_monitor` 「전략 매도 신호」 로 나갔다(06-12 `222800` · 06-15 `403870` · 06-16 `330860` · **08-18 09:02:37 `041830`** · **08-19 09:02:40 `096530`**, 원장 타임스탬프와 초 단위 일치). 뒤 2건은 `position_monitor.py:219-224,326` 의 **09:00~09:05 손절 유예를 우회**했다(전략 경로 `:339` 에는 유예가 없다). `a736065` 는 rs_leader·ma20·ma5 만 고쳤고 deep_mr 는 06-12 에 이미 앞이었다 — **4전략 중 envelope 만 남았다.** | envelope | `strategy.py:130-141` · `position_monitor.py:200-368` · 로그 `grep "전략 매도 신호"` · 원장 |
| **D-5** | 🔴 | **envelope 위생 가드가 룰의 창을 못 덮는다.** 룰 입력 = 자체 조회 229봉(`strategy.py:241`), 가드 = 프레임워크 80봉(`base.py:645`) ⇒ 81~229봉 구간의 절벽은 창 A 에선 제외되고 창 B 에선 통과. 실측 A\B = **4종목**(791 유니버스). `accepts_volume_fallback=True` 라 폴백 유입분은 이 80봉 가드가 유일하다. | envelope | `strategy.py:241-252` · `base.py:645` · §1-7 |
| **D-6** | 🟡 | **rs_leader score(`rs_lb=120`)는 창 B 에서 원리적으로 계산 불가**(121봉 필요, B 78~84) — 08-23 편 D4(minervini TT)와 같은 구조. 지금은 무해(라이브는 score 를 안 씀) 이나 「스크리너 전용 게이트 + 창 B 재검사 불가」 계열 2번째. 또 `len(close) <= 120 → None`(`screener.py:52-53`)이라 상장 ~6개월 미만은 룰 통과해도 «조용히» 후보 탈락. | rs_leader | `screener.py:52-54` |
| **D-7** | 🟡 | **rs_leader 창 B 평가 대상이 자기 후보 밖이다.** 8/21 rs_leader 매수 시그널 **18종목** 중 자기 08-20 top-10 은 **6종목**(049080·001210·011090·189330·227950·079650); 나머지 12(257720·475150·010950·214450·005830·051900·066590·004370·050120·161890·192820·241710) 는 07:40 복원 보유·타전략 후보 코드와 일치. 실제 매수 4건은 자기 목록 안. `get_selected_stocks()` 의 «공용(소유자 없음)» 반환(`trading_context.py:296`)이 통로로 추정 — **경로 확정은 rs_leader 개별 검수로 이관**. | rs_leader(관측) | 로그 8/21 `RSLeaderStrategy … 매수 시그널` · `screener_snapshots` |
| D-8 | 🟡 | 4전략 창 A 어댑터에 `finalize_scan` 진단이 없어 유니버스→평가→매칭 수가 **로그에 안 남는다**(minervini 만 있음). §1-1 유니버스 수는 SQL 추정. | 4전략(관측성) | `_rule_screener_base.py:102-103` · 각 `screener.py` |

---

## §4 08-23 편 D1~D9 재적용 판정

| 08-23 | 내용 | 이 4전략 판정 | 실측 |
|---|---|---|---|
| D1 | 창 B 가 EMA 워밍업에 못 미침 | **해당없음** | 4전략 모두 SMA/rolling 또는 자체 절단(§1-1 「창 의존」 열). 손계산 4/4 가 창 길이에 불변 |
| D2 | 가드 창이 A·B 에서 달라 제외 집합이 갈림 | **성립** | A\B/B\A = rs 3/0 · ma20 1/0 · env 4/0 · deep_mr 0/1. \|A\| 16/14/17/4 = 8/21 로그 발화 수 정확 일치 |
| D3 | 정지 패딩이 거래량 룰 분모를 채움 | **패딩 노출은 성립 · 매매 발화 메커니즘은 «다른 결함»** | rs_leader top-10 **9/10** 이 창 B 에 패딩 보유(envelope 1/6 `001210` · ma20 0/10 · deep_mr 0/1). 그러나 rs_leader 의 순위·진입을 만든 것은 패딩(분모)이 아니라 **미조정 병합이 «분자»(수익률·MA 위치)를 만든 것**(D-1)이고 패딩은 그 정지 기간의 표식이다 — 08-23 편 D3 와 분리해서 볼 것. ma20 의 `_recent_surge`(30봉 고저)·envelope 의 `vol ≥ vol_prev`(prev=0) 는 패딩·점프에 «구조적으로» 취약(독해, 8/21 실측 사례 없음) |
| D4 | TT 는 창 B 에서 평가 불가 | **유사 성립** | rs_leader score 121봉 요구(D-6). envelope 는 자체 230봉 조회로 «회피» — 설계상의 정답 사례이나 가드가 어긋남(D-5) |
| D5 | 청산 timeframe 가드 순서 | **envelope 열림 / 3전략 차단** | envelope 고유 청산 5/5 분봉 경로(D-4). rs_leader·ma20 = `a736065`, deep_mr = 06-12 수정 |
| D6 | 스크리너 score 가 close 폴백 | **불성립(폴백 없음)** · 대신 rs_leader score 가 아티팩트에 지배(D-1) | §1-8 |
| D7 | 행 수 vs 달력일 — 결손 시 창이 반대로 | **성립(구조 동일)** | `475040` 37행/36봉(신규상장형) — 두 창이 같은 봉을 본 사례. rs_leader 창 A 는 결손 시 `ref120` 이 «더 오래된» 종가가 된다 |
| D8 | 005930 일요일 행 | **envelope 만 해당** | 8/21 로그 envelope `005930 불가능봉 @2026-01-11` 제외(230행 창 안). rs_leader 130행·ma20 90행 창엔 안 들어간다(로그에 없음) |
| D9 | adj_factor 경계 어긋남(`001510`) | **rs_leader·envelope 해당** | 8/21 로그 둘 다 `001510 @2026-02-09 −47.3%` 제외. ma20(90행) 은 창 밖 |
| 신규 | — | **D-3** score 사후 재현 불가(기록자 둘) · **D-1** 미조정 감자/액면병합 | D-1 은 08-23 편에 «없던» 관측이 아니라 `data_sanity.py:29-31` 이 명시한 예외(미조정 액면병합)와 08-23 편 D9(adj_factor 경계) 계열의 **정량화·상승 방향형**이다. 새 것은 「rs_leader 상위가 그 예외로 통째로 채워진다(8/10)」는 수치. D-3 의 «창 A/B 상이»는 가설 |

---

## §5 한계

1. **D-1 의 원인 판정은 🔎 검증이 `daily_prices.market_cap`(정지 중 ÷5/÷10)·재개 시가 배율(×5.00/×10.00)·`corp_events`(1/8) 로 실측한 것**이며, 이 문서의 초안은 데이터 모양(패딩 뒤 점프)만 보고 «정지 해제 점프»라 불렀다 — 정정됨. 「정상 시세로 만들어질 수 없다」(KRX ±30%) 논거는 유지. 226340·227950 두 종목은 `market_cap` 이 정지 중 불변이라 배율(×4.6)로만 «5:1 추정». 공시 원문 대조는 하지 않았다.
2. **D-3 에서 확정된 것은 「스냅샷 score ≠ 현재 DB」와 「기록자 둘의 실재」뿐이다.** 09:00:54 로더와 15:45:04 EOD 중 어느 쪽이 값을 바꿨는지, 창 B 가 09:01 에 실제로 다른 volume 을 읽었는지는 덮어쓰기 «전» 값이 남아 있지 않아(`updated_at` 전표 재도장) **판별 불가** — §0-3·§3 D-3 의 「가설」 표기와 정합. 어느 봉이 얼마나 바뀌었는지는 20봉 합계로만 안다. 순위 불변은 08-20 하루의 관측. 시간외 거래량 가설은 미검증.
3. **envelope 001210 미체결 원인(밴드 추정)은 로그로 확인 불가**(`debug`). 08-23 편 X-2 와 같은 관측 불가 영역.
4. **D-7 의 통로(공용 반환)는 독해 추정** — `TradingStockManager` 의 07:40 복원 상태와 owner 바인딩을 이 편에서 추적하지 않았다. rs_leader 개별 검수의 몫.
5. 창 B 가드 발화 0건은 throttle 이 있어도 첫 발화는 항상 로그되므로 신뢰할 수 있다(08-23 편과 같은 논거). 단 가드가 «상승»을 안 보는 것은 설계 의도(`data_sanity.py:29-31`)이고, D-1 은 그 의도를 뒤집자는 주장이 아니라 **그 결과 rs_leader 의 상위가 통째로 가드 밖에 있다**는 관측이다.
6. RSI 손계산은 pandas `ewm(adjust=True, ignore_na=False)` 의 가중 정규화를 순수 python 으로 옮긴 것이다(첫 diff NaN 은 관측에서 제외). 라이브 코드 실행 재현은 아니다. −20.99% 와 score 는 SQL 정확 일치.
7. 손계산 4건 모두 창 안 `adj_factor` 가 1/NULL ⇒ 「읽기 계층이 volume 에 곱한다」는 SQL 문자열 대조로만 확인(08-23 편 §5-1 과 동일).
8. 8/22·8/24 로그 부재/미완성. 실측은 8/18~8/21.
9. 유니버스 수(791/635/791/267)는 SQL 로 base_filter 를 재현한 값이며 로그에 없다(D-8). minervini 의 371 과 다른 것은 시총 필터 차이.

---

## 부록 — 재현 명령

로그(bash, cwd `D:/GIT/kis-trading-template`):

```
L=RoboTrader_template/logs/robotrader_template_20260821_074007.log
grep -o "일봉 [0-9]*건" $L | sort | uniq -c                                   # 80건 1194 · 36건 36
grep "미조정 기업행위 의심, 후보 제외" $L | sed -E 's/.*\[([a-z0-9_]+)\].*/\1/' | sort | uniq -c   # rs 16 · ma20 14 · env 17 · deep 4
grep -n "screener_snapshots 저장\|일봉 데이터 DB 저장 완료" $L | grep "09:0[01]:"   # 스캔 09:00:28~44(:394-486) → 저장 09:00:54~09:01:08(:535-790). 07:40 복원 줄은 제외
grep -h "전략 매도 신호" RoboTrader_template/logs/robotrader_template_*.log       # envelope 5건 = position_monitor 경유
grep "RSLeaderStrategy | INFO | 🧾 \[PAPER\] 매수 시그널" $L | sed -E 's/.*시그널: ([0-9A-Z]+) @.*/\1/' | sort -u | wc -l   # 18
grep -c "BookEnvelope200dStrategy | INFO | 🧾 \[PAPER\] 매수 시그널: 001210" $L                                           # 4 (rs_leader 4회와 합치면 8)
```

SQL (`PGPASSWORD=1234 PGCLIENTENCODING=UTF8 psql -h 127.0.0.1 -p 5433 -U robotrader -d kis_template -X -A -F'|'` — 한글 포함 쿼리는 `-f 파일` 로):

```sql
-- ① rs_leader 049080 (창 B)  → 8200 | 8345 | 5325.38 | 1458 | 4.624 | 457 | 16.9431
WITH w AS (SELECT date, close::double precision c, row_number() OVER (ORDER BY date DESC) rn
           FROM daily_prices WHERE stock_code='049080' AND date<='2026-08-20')
SELECT (SELECT c FROM w WHERE rn=1), (SELECT avg(c) FROM w WHERE rn<=20), (SELECT avg(c) FROM w WHERE rn<=60),
       (SELECT c FROM w WHERE rn=61), (SELECT c FROM w WHERE rn=1)/(SELECT c FROM w WHERE rn=61)-1,
       (SELECT c FROM w WHERE rn=121), (SELECT c FROM w WHERE rn=1)/(SELECT c FROM w WHERE rn=121)-1;

-- ② ma20 006340  → 14530 | 14280 | 13940 | 13926 | 9210 | 16370 | 0.777 | 0.0010 | 14136889.2
WITH w AS (SELECT open::double precision o, high::double precision h, low::double precision l, close::double precision c,
           (volume*COALESCE(adj_factor,1))::double precision v, row_number() OVER (ORDER BY date DESC) rn
           FROM daily_prices WHERE stock_code='006340' AND date<='2026-08-20')
SELECT (SELECT c FROM w WHERE rn=1),(SELECT o FROM w WHERE rn=1),(SELECT l FROM w WHERE rn=1),(SELECT avg(c) FROM w WHERE rn<=20),
       (SELECT min(l) FROM w WHERE rn BETWEEN 2 AND 31),(SELECT max(h) FROM w WHERE rn BETWEEN 2 AND 31),
       (SELECT max(h) FROM w WHERE rn BETWEEN 2 AND 31)/(SELECT min(l) FROM w WHERE rn BETWEEN 2 AND 31)-1,
       abs((SELECT l FROM w WHERE rn=1)-(SELECT avg(c) FROM w WHERE rn<=20))/(SELECT avg(c) FROM w WHERE rn<=20),
       (SELECT avg(v) FROM w WHERE rn<=20);

-- ③ envelope 161890 (LIMIT 230)  → 137800 | 137800 | 122710 | 134981 | 411216 | 295464 | 137937.28 | 0.0885
WITH w AS (SELECT open::double precision o, high::double precision h, low::double precision l, close::double precision c,
           (volume*COALESCE(adj_factor,1))::double precision v, row_number() OVER (ORDER BY date DESC) rn
           FROM daily_prices WHERE stock_code='161890' AND date<='2026-08-20' ORDER BY date DESC LIMIT 230)
SELECT (SELECT c FROM w WHERE rn=1),(SELECT max(c) FROM w WHERE rn<=200),(SELECT avg(c) FROM w WHERE rn<=10),
       (SELECT avg(c) FROM w WHERE rn<=10)*1.1,(SELECT v FROM w WHERE rn=1),(SELECT v FROM w WHERE rn=2),
       (SELECT avg(c*v) FROM w WHERE rn BETWEEN 2 AND 6)/1e6,(SELECT c FROM w WHERE rn=1)/(SELECT o FROM w WHERE rn=1)-1;

-- ④ deep_mr 214150 (≤08-19)  → 33400 | 42275 | -20.9935   (RSI 는 순수 python: 34봉 절단 ewm adjust=True → 26.22)
WITH w AS (SELECT close::double precision c, row_number() OVER (ORDER BY date DESC) rn
           FROM daily_prices WHERE stock_code='214150' AND date<='2026-08-19')
SELECT (SELECT c FROM w WHERE rn=1),(SELECT avg(c) FROM w WHERE rn<=20),
       ((SELECT c FROM w WHERE rn=1)-(SELECT avg(c) FROM w WHERE rn<=20))/(SELECT avg(c) FROM w WHERE rn<=20)*100;

-- D-1: rs_leader 08-20 top-10 의 130행 창 최대 1일 상승·패딩
WITH snap AS (SELECT stock_code, rank_in_snapshot FROM screener_snapshots WHERE strategy='rs_leader' AND scan_date='2026-08-20' AND rank_in_snapshot<=10),
w AS (SELECT s.stock_code, s.rank_in_snapshot, d.date, d.close::double precision c, d.volume, d.open, d.high, d.low,
        row_number() OVER (PARTITION BY s.stock_code ORDER BY d.date DESC) rn
      FROM snap s JOIN daily_prices d ON d.stock_code=s.stock_code AND d.date<='2026-08-20'),
chg AS (SELECT stock_code, rank_in_snapshot, date, c/NULLIF(lag(c) OVER (PARTITION BY stock_code ORDER BY date),0)-1 r,
        volume, open, high, low, c FROM w WHERE rn<=130)
SELECT rank_in_snapshot, stock_code, round(max(r)::numeric,3) max_up,
       count(*) FILTER (WHERE volume=0 AND open=high AND high=low AND low=c AND date>='2026-04-23') padB
FROM chg GROUP BY 1,2 ORDER BY 1;
--  → 1 049080 6.825 13 · 2 226340 3.096 16 · 3 001210 3.603 11 · 4 090150 9.421 18 · 5 011090 3.252 16
--    6 189330 0.300 0 · 7 227950 2.986 16 · 8 002680 3.291 15 · 9 079650 0.300 2 · 10 014990 2.583 15

-- D-3: 스냅샷 score vs 현재 DB 재계산 (ma20 20봉 평균 volume)  → 18/20 불일치, 최대 Δ 11351 (003280), 상대 최대 0.94% (462860)
--      마지막 기록자 확인: SELECT stock_code, date, updated_at FROM daily_prices WHERE stock_code IN ('006340','161890','462860') AND date>='2026-08-19'  → 전부 2026-08-21 15:45:04
WITH snap AS (SELECT stock_code, rank_in_snapshot, score FROM screener_snapshots WHERE strategy='book_pullback_ma20' AND scan_date='2026-08-20'),
w AS (SELECT s.stock_code, s.rank_in_snapshot, s.score, (d.volume*COALESCE(d.adj_factor,1))::double precision v,
        row_number() OVER (PARTITION BY s.stock_code ORDER BY d.date DESC) rn
      FROM snap s JOIN daily_prices d ON d.stock_code=s.stock_code AND d.date<='2026-08-20')
SELECT stock_code, score, avg(v), round((avg(v)-score)::numeric,2) FROM w WHERE rn<=20 GROUP BY 1,2 ORDER BY 2 DESC;

-- §1-7: 가드 창별 제외 집합 (2026-08-20 유니버스)  → ALL 13/38/40/41/36 · 전략별 A\B 3/1/4/0 · B\A 0/0/0/1
WITH uni AS (SELECT stock_code, market_cap::double precision mcap, (close*(volume*COALESCE(adj_factor,1)))::double precision tv
             FROM daily_prices WHERE date='2026-08-20' AND market_cap IS NOT NULL),
bars AS (SELECT d.stock_code, d.date, d.close::double precision c, row_number() OVER (PARTITION BY d.stock_code ORDER BY d.date DESC) rn
         FROM daily_prices d JOIN uni u USING (stock_code) WHERE d.date<='2026-08-20'),
ret AS (SELECT stock_code, date, rn, CASE WHEN c>0 AND lag(c) OVER (PARTITION BY stock_code ORDER BY date)>0
             THEN c/lag(c) OVER (PARTITION BY stock_code ORDER BY date)-1 END r FROM bars WHERE rn<=231),
flags AS (SELECT stock_code, bool_or(r<-0.35 AND rn<=45) a45, bool_or(r<-0.35 AND rn<=90) a90, bool_or(r<-0.35 AND rn<=130) a130,
          bool_or(r<-0.35 AND rn<=230) a230, bool_or(r<-0.35 AND date>='2026-04-23') bB FROM ret GROUP BY 1)
SELECT 'rs_leader', count(*) FILTER (WHERE a130 AND NOT bB) a_not_b, count(*) FILTER (WHERE bB AND NOT a130) b_not_a, count(*) FILTER (WHERE a130) a
FROM flags JOIN uni USING (stock_code) WHERE tv>=1e9
UNION ALL SELECT 'ma20', count(*) FILTER (WHERE a90 AND NOT bB), count(*) FILTER (WHERE bB AND NOT a90), count(*) FILTER (WHERE a90)
FROM flags JOIN uni USING (stock_code) WHERE tv>=1e9 AND mcap>0 AND mcap<=3e12
UNION ALL SELECT 'envelope', count(*) FILTER (WHERE a230 AND NOT bB), count(*) FILTER (WHERE bB AND NOT a230), count(*) FILTER (WHERE a230)
FROM flags JOIN uni USING (stock_code) WHERE tv>=1e9
UNION ALL SELECT 'deep_mr', count(*) FILTER (WHERE a45 AND NOT bB), count(*) FILTER (WHERE bB AND NOT a45), count(*) FILTER (WHERE a45)
FROM flags JOIN uni USING (stock_code) WHERE tv>=1e10;

-- §1-9: 매도 reason 분류 (한글 LIKE 라 -f 파일로)
-- pm:* = position_monitor 범용 · strategy = 전략 고유 → env 30/6/4/5 · ma20 51/36/3/7 · deep 33/7/3/3 · rs 71/25/7/11
```

순수 python(RSI, 프로젝트 모듈 import 없음): 34봉 종가열에 대해 `diff → gain/loss → ewm(alpha=1/14, adjust=True, min_periods=14)` 를 `num = x + (1-α)·num, den = 1 + (1-α)·den, y = num/den` 으로 재현 → 26.2156. 45봉이면 27.9791.
