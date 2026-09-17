# 검증 — `strategy_book_envelope_200d.md` (2026-08-24, 검증 직원)

> **역할**: 반박. 대상 보고서의 파일:라인·숫자·SQL·로그 주장을 **독립 재도출**했다. 코드 0줄 · git 쓰기 0 · 라이브 트리 python 0. 판정 = `SUPPORTED` / `REFUTED` / `UNVERIFIABLE`.
> **재현 방법**: SQL 은 scratchpad 의 UTF-8 파일을 `PGCLIENTENCODING=UTF8 psql -h 127.0.0.1 -p 5433 -U robotrader -d kis_template -X -A -F'|' -f <file>` 로 실행(한글 리터럴을 `-c` 로 넘기면 코드페이지 오류). 파일: `scratchpad/v1_sell_reasons.sql`·`v2_entry_rules.sql`·`v3_detail.sql`·`v4_holdings.sql`·`v5~v10_*.sql`.
> **조회 시점**: 2026-08-24 09:10 이후(오늘 09:00 스캔이 이미 돈 뒤). `daily_prices`·`screener_snapshots` 는 살아 있는 표라 보고서(08:15 작성) 와 행 수가 갈리는 곳이 있다 — §9 에 명시.

## §0 총평

**실질 주장 중 REFUTED 는 없다.** 핵심 4건(ENV-1~4)·손계산·진입 50/50·창 A/B 동일성·ENV-9 오기 5건 전부 재현됐다. 정정은 **수치·표현 6건(전부 경미, 판정 불변)** 과 **누락 1건(ENV-5 의 잠복 경로가 하나 더 있다)**. UNVERIFIABLE 2건은 보고서 자신이 §7 한계로 적은 것과 같다(유령 58신호가 체결로 안 이어진 «이유» · 「책 청산 재측정 없음」이라는 부재 주장).

## §1 ENV-1 🔴🔴 청산 경로 — **SUPPORTED**

| 주장 | 재도출 | 판정 |
|---|---|---|
| 매도 45/45 실시간 경로: PM 손절 30 · 익절 6 · 트레일링 4 · 전략룰(PM 분봉경로) 5 | `v1_sell_reasons.sql` reason LIKE 분류: `손절 실행%` **30**(−4,078,960) · `목표 익절 도달%` **6**(+775,960) · `트레일링 스톱%` **4**(+644,200) · `손절 도달%/익절 도달%` **5**(−193,700) · 합 **45 / −2,852,500** · 보유기간/max_hold 0 | SUPPORTED |
| 전략 «일봉» 루프 체결 0 · 유령 신호 58 전부 07-02 `089970` | `grep -c "\[on_tick\] 매도신호"` 전 로그 → 로거 `strategy.BookEnvelope200dStrategy` **58**, 전부 `robotrader_template_20260702_074012.log` `089970`(:6218 11:05:11 → :17301 15:30:11, 5분 간격). 원장에 그 경로 SELL 0(089970 의 SELL 은 07-06 PM `손절 실행 (-8.08%)`) | SUPPORTED |
| 07-02 전일 종가 119,700 vs 체결가 101,500 → +17.9% · 고가 109,400 | `daily_prices` 089970 07-01 close **119,700** · 07-02 open=high **109,400** · 로그 :6207 `매수 체결: 089970 @ 101,500 x 19주` · :6217 `매도 시그널: 089970 @ 119,700 (take_profit) \| 익절 도달 (+17.9%)`. 119,700/101,500−1 = **+17.93%** | SUPPORTED |
| `strategy.py:131` positions 분기가 `:140` timeframe 가드 «앞» | `grep -n`: :131 `if stock_code in self.positions:` → :132 `_check_sell` · :136 max_positions · :140 `if timeframe != "daily": return None` | SUPPORTED(독해) |
| `position_monitor.py:337-364` 가 전략 룰을 분봉 경로로 호출 | :337 `# 전략 매도 시그널 체크` · :360 `generate_signal(stock_code, intraday_data, timeframe='intraday')` · :364 `전략 매도 신호:` INFO. 5건 로그 전부 `core.trading.position_monitor \| <code> 전략 매도 신호: 손절/익절 도달` (06-12 222800·06-15 403870·06-16 330860·08-18 041830·08-19 096530) | SUPPORTED |
| 09:00~09:05 는 전략 룰이 이기는 우연한 창 | :221-223 `is_before_rebalancing = hour==9 and minute<5` · :326 `if not is_before_rebalancing:` 아래에만 PM 손절(:329-330) · :337 전략 신호 체크는 스킵 없음. 실측 08-18 **09:02:37** · 08-19 **09:02:40** 둘 다 창 안. PM 손절 30건 최조 시각 **09:05**(09:05 에 10건·09:06 에 1건 = 「09:05~09:10 11건」 ✓) | SUPPORTED |
| 6월 3건은 범용 tp/sl «동적» 시기라 −8/+10 고정 룰이 먼저 | 매수 원장 `stop_loss_rate/target_profit_rate`: 222800 sl **0.124** · 403870 tp **0.128** · 330860 sl **0.0957** ⇒ 전략 −8%/+10% 가 먼저 닿는다 | SUPPORTED |
| `041830` 08-18 62,200 은 어떤 일봉 종가도 아님 | `daily_prices` 08-14 close **64,400**(= `minute_candles` 08-14 `153000` close 64,400 ✓) · 08-18 close **61,100**. 로그 :215 `DB 복원: 22주 @67,700원` · :847 `매도 시그널: 041830 @ 62,200 (stop_loss)` → 62,200/67,700−1 = **−8.12%** ✓. 원장 체결가 62,000(−8.42%) = PM 이 `current_price` 로 체결 | SUPPORTED |
| `a736065` 가 이 전략 미적용 | `git show --stat a736065` → `book_pullback_ma20`·`book_pullback_ma5`·`rs_leader` 3파일 + 테스트 3파일만 | SUPPORTED |
| 유령 58신호가 체결로 안 이어진 이유 | 07-02 로그에 089970 `매도 거부/매도 스킵` INFO **0건** · `[모호조회] 089970 다중 소유(2)` WARNING 만(:6200,:6203,:6219). `trading_context.py:562,:579` 두 스킵이 `debug` | **UNVERIFIABLE**(보고서 §7-2 와 동일) |

🟠 **수치 정정 2건(경미)**: §3-D 표 「익절 6 평균 **+10.0**」 → 실측 **+9.58%**(089970 06-12 +0.84% 가 끌어내림) · 「전략 룰 5 평균 **−4.5**」 → **−4.42%**(−8.07·+10.47·−8.01·−8.42·−8.09). 손절 30 평균 −8.23 ✓ · 실현 범위 −14.22~−3.04 ✓ · 최대 보유 11달력일 ✓.

## §2 창 A/B 동일성 + D-5 양립 판정 — **SUPPORTED · 양립(서로 다른 양을 잰다)**

**동일성**: `_rule_screener_base.py:195` `get_daily_prices(code, end_date=scan_date, days=self.lookback_days)`(`screener.py:14` 230) 와 `strategy.py:241-242` `get_daily_prices(stock_code, end_date=today, days=self._entry_lookback)`(`config.yaml:35` 230) 가 **같은 메서드** → `quant_daily_reader.py:157-158` `_SELECT_OHLCV`(`volume * COALESCE(adj_factor,1)`) + :176-177 `WHERE stock_code = %s AND date <= %s ORDER BY date DESC LIMIT %s`. 끝날짜: A = `liquidation_handler.py:604` `get_previous_trading_day`, B = `strategy.py:250-252` 오늘 행 마스크 제거 ⇒ 둘 다 D-1(B 는 오늘 행이 있으면 229). SQL `n230`=230 **50/50**. 가드: A `_rule_screener_base.py:177-178`(`sanity_window=None` :94 → 230행 전체), B `base.py:645` 프레임워크 피드(`constants.py:142` 달력 120일). → **SUPPORTED**.

**D-5(변형 횡단 편 `data_transformation_bottom4.md:19,201`) vs 「실측 영향 0/50」(ENV-5)** — 독립 재도출(`v8_snap_ab.sql`·`v9_ab_codes.sql`):
- 유니버스(08-20 `market_cap IS NOT NULL ∧ close×volume×adj ≥ 1e9`, `quant_daily_reader.py` `get_universe_snapshot` 동일 식) = **791** ✓(D-5 와 일치).
- 230행 창에 `pct_change < −0.30`(`utils/data_sanity.py:56-84`, **하락만**) 종목 **24** · 80행 창 **20** · 차집합 **4 = `001510`(절벽 129봉 전, 2026-02-09) · `003350`(83봉, 04-20) · `005930`(150봉, 01-11) · `010120`(88봉, 04-13)** ⇒ D-5 의 「A\B = 4종목」 **재현**.
- 이 4종목의 envelope 원장(BUY/SELL) 레코드 = **0** ⇒ 「실측 영향 0/50」 **재현**.
- ⇒ **양립한다.** D-5 는 「유니버스 안에서 두 가드가 «다르게 판정할» 종목 수」(잠재 노출 4/791), ENV-5 의 0/50 은 「실제 매수 50건 중 그 차이가 발화한 수」(실현). 보고서 §3-1 은 이미 「A 가 상위집합이라 A 통과 → B 통과 성립 · 폴백 유입분만 80봉 가드」라고 같은 구조를 적었고 등급만 🟡 로 뒀다. 두 문서의 숫자는 모순이 아니다.
- 🟠 **누락 1건**: 보고서는 잠복 경로를 `accepts_volume_fallback=True`(`strategy.py:51`) **하나**로 적었는데, `trading_context.py:287-297` `get_selected_stocks()` 는 `owner` 미지정 호출 시 **`strategy_name` 이 비어 있는 «공용» SELECTED 종목도 함께 반환**한다(:296 `if so == target or not so`). 변형 횡단 편 D-7 이 rs_leader 에서 이 통로를 관측했다(자기 후보 밖 12종목 평가). envelope 의 `_check_buy` 는 룰이 참일 때만 로그를 남기므로 「08-21 신호 6종 = 스냅샷 6종」(재현 ✓)은 이 통로가 «닫혀 있다»는 증거가 아니라 «그날 룰 통과가 없었다»는 증거다. ⇒ ENV-5 에 두 번째 잠복 경로를 추가할 것.
- 참고: 08-21 로그의 envelope 스크리너 불가능봉 제외는 **17건**(`[book_envelope_200d] <code>: 불가능봉 …`)이고 오늘 SQL 은 24 — 살아 있는 표(036800 @08-18 등 절벽이 그 뒤 생김/바뀜). 17건 중 80봉 밖 = **4건** 으로 위와 같은 4종목이다.

**등급 제안**: envelope 문서의 ENV-5 는 🟡 유지 가능(실현 0) 이나, 횡단 편 D-5 🔴 와 **같은 결함에 다른 등급**이 붙어 있다. 사장님 결정용으로 「🔴(잠복) · 실현 0/50 · 잠복 경로 2개(폴백·공용 SELECTED)」로 통일 표기를 권고.

## §3 ENV-2 진입 밴드·`001210` — **SUPPORTED(표현 정정 2)**

| 주장 | 재도출 |
|---|---|
| 06-16 이후 41건: +3% 초과 **0** · −2% 미만 **17(41.5%)** · −5% 미만 4 · 최악 −15.20 · 평균 −2.04 | `v3_detail.sql` band split: post **41 / 0 / 17 / 4 / −15.20 / −2.04** · pre 9 / 3 / 4 / 1 / −17.67 / −0.85 ✓ |
| 체결 44/50 이 09:30 이전 | `ts::time < '09:30'` **44/50** ✓ |
| 밴드 코드에만·하한 None·거절 debug | `strategy.py:88-90` ✓ · `config.yaml:41-47` 두 키 부재 ✓ · `trading_decision_engine.py:409-416` 밴드 판정 ✓ · `trading_analyzer.py:92` `logger.debug` ✓ · 08-21 로그 「밴드」 **0회** ✓ |
| `001210` ref 7,460 · 상한 7,684 · 09:00 8,220(+10.2%) · 09:09 8,790 · 09:18 9,350(+25.3%) · 4틱 신호 · 체결 0 | `daily_prices` 08-20 close **7,460**(×1.03 = 7,683.8) · `minute_candles`(`trade_date='20260821'` 문자열 · `time='090000'`) 09:00 **8,220** · 09:09 **8,790** · 09:18 **9,350** ✓ · 로그 `BookEnvelope200dStrategy … 매수신호: 001210` **4회** · `매수 체결` 0 ✓ |
| 나머지 4건 체결 −0.94/−0.19/−1.60/−1.03 | 로그 :821 161890 @136,500×10 · :1045 192820 @260,000×5 · :1253 241710 @135,000×10 · :1404 005180 @86,300×16 ✓ (ref 137,800/260,500/137,200/87,200) · 005180 분봉 09:00 86,800 · 09:09 86,100 · 09:18 86,500 ✓ |
| `189330` 쿨다운 5회 → 09:14:50 rs_leader 선점 | :836/:951/:1057/:1159/:1262 `[진입억제] 189330 매수 스킵 — 쿨다운 59초 남음` · :1328 `RSLeaderStrategy \| 매수 체결: 189330 @ 17,200 x 45주` ✓ · 분봉 17,360/17,220/16,850 ✓ |

🟠 **표현 정정**: §2-1 「`001210` **전일 +26.4%**」 — 08-20 종가/전일종가 = **+29.97%**(5,740→7,460), +26.4% 는 08-20 **시가→종가**(5,900→7,460). 「**시초 +10.2%**」 — 08-21 일봉 시가는 8,000(**+7.24%**), +10.2% 는 **09:00 1분봉 종가**(8,220). 결론(밴드 밖·체결 0)은 두 정의 모두에서 성립하므로 판정 불변, 문구만 「09:00 분봉 종가 기준」으로.

## §4 ENV-3 책 청산 인용 — **SUPPORTED**(부재 주장 1건 UNVERIFIABLE)

- `spec:82` = *「책 진짜 청산 = **장중 이등분선 트레일링 + 매수 대비 +3% 익절 / −3% 손절**. 장중 이등분선은 일봉 해상도로 표현 불가」* ✓ verbatim. `spec:16` 「눌림목… 3% 내외 수익 목표」 ✓ · `:21` 「종가기준 200일 신고가 + 거래대금 최소 50억 이상. 한 달 내 100% 증가 종목 제외」 ✓ · `:37` 「추가 진입 조건(산문): 이등분선 지지 … 분봉에서 상승폭>하락폭」 ✓ · `:41` 「접근 금지: 장중 +20% 급등, 상한가 다음날」 ✓ · `:64` D `vol_ratio=1.0 (전일대비 일봉 프록시, 사장님 확정)` ✓.
- `report.md:12` 「청산은 … sl/tp/mh 스윕으로 근사(책 명목 +3%/−3% 포함). 책 진짜 청산(장중 이등분선 트레일링)은 일봉 해상도로 표현 불가」 ✓ · `:38-41` BEST/BASELINE 표 + `:41` 「**72조합 전부 PnL 음수**」 ✓ · `:30` 미코드화 3건 ✓ · `:78` exit-grid `sl{0.03,0.05} tp{0.03,0.05,0.10} mh{1,2,3,5}` ✓ · `:147` 「책 §0.1 은 … 명시」 ✓.
- `_WALKFORWARD:5` 「고정 config(a priori) … sl0.08/tp0.10/mh10, K=5 … gate=none」 ✓ · `:52` 「paper 관찰 전략(regime_gate=exclude_bear, 격리 1천만)」 ✓. `README.md:17` ✓ · `config.yaml:4,14` ✓ · `PAPER_STRATEGIES.md:141` ✓.
- 「책 청산은 깨끗한 데이터로 재측정된 적 없다」 — 메모리 `remeasure-2026-06-05-book19-quant.md` 존재 확인. 그 재측정이 ±3% 를 «안 돌렸다»는 것은 보고서 진술이고 나는 보고서 전체를 뒤지지 않았다 → **UNVERIFIABLE**(반증 없음).

## §5 ENV-4 K·사이징 — **SUPPORTED(전건)**

`v3/v4`: 동시보유(체결 이벤트 누적) 최대 **9 @ 06-18 10:00:25**(200470 BUY) ✓ · `paper_strategy_equity` 55일, `n_open>5` **2일(06-17·18, 최대 6)** · `=5` **5일** ✓ · 08-21 `n_open=5` equity **7,032,279.23** cash **328,479.23** ✓ · 금액 **15,050(004710 1주 06-18) ~ 6,175,000(069960 06-10)** ✓ · 10만 미만 **2** · 1주 **1** · 300만 초과 **2** ✓ · 당일 최대 **4건**(06-18·06-23·08-07·08-21) < 5 ✓ · 건당 평균 **−4.33%** vs 금액가중 **−3.57%**(`sum(profit_loss)/sum(buy.price×qty)`, `buy_record_id` 조인) ✓ = `docs/포지션사이징_결함_2026-08-23.md:75` 행 ✓ · 로그 :273 `07:40:23 종목당 투자금액 재산정: book_envelope_200d 2,000,000원 → 1,397,056원 (자본 6,985,278/10,000,000 = 0.6985)` ✓ · 08-21 4건 1,300,000~1,380,800 ✓. `virtual_trading_manager.py:329-332`(재산정) · `:577-580` `max_amount = min(per_stock, budget)` ✓ · `strategies/config.py:456-465` 자기 주석 ✓ · `trading_config.json:41-45` `max_capital_pct 0.16`·`KOSPI/none` ✓.

## §6 손계산 `005180` — **SUPPORTED(소수점 일치)**

SQL(신호봉 08-20): close 87,200 · SMA10 **74,460** → ×1.10 = **81,906** · tv5 **23,678.3M** · gain **11.79%** · vol 1.763× · n230 **230**. 로그 :831 `매수 시그널: 005180 @ 87,200 (추천 34주) | envelope_200d_high close=87200 >= env_upper=81906 200d_high vol>=prev value=23678M gain=11.8%` ✓.

## §7 진입 50/50 — **SUPPORTED(표본 20건 열람)**

`v2/v3`(보고서 SQL 그대로, alias 충돌 `C`↔`c` 만 `cA..cI` 로 개명 — 원문 SQL 은 그대로 실행하면 「칼럼 참조 c 가 모호」 오류): all9 **50/50** · n230=230 **50/50** · env 최소 **+10.73**(131290 07-14) 최대 **+49.44** · I 최소 **+4.32** 중앙 **+11.58** · D 최소 **1.096×**(=「1.10」) 중앙 **1.875** · F 최소 **5,273.1M**(041830 08-06) ✓. 직접 열람 12건(06-10~06-16) + 지정 8건(089970×2·004710×2·025560·131290·041830·005180) 전부 9조건 참. 패딩: `pad230>0` **3건**(004710×2 = 16행 **2025-09-04~25 close 5,730 고정** ✓ + 025560 1행 ✓) · 신호봉 직전 6봉 `volume=0` **0/50** ✓ · `af200>0` **2건**(004710) ✓.
🟠 **정정**: §2-6 「004710 … 2025-06~07 행 `adj_factor=5`」 → `adj_factor=5` 행은 **2021-01-12~2025-09-25(1,150행)** 이고 신호봉 200봉 창 안에 든 것은 그 꼬리 **27행/24행(2025-08~09)**. 판정 불변.
🟠 **SQL 주의**: 보고서 §3-A 의 SQL 을 그대로 실행하면 PostgreSQL 이 alias `C` 를 컬럼 `c` 와 혼동해 실패한다 — 재현 가능성 위해 alias 를 바꿔 적어 둘 것.

## §8 ENV-9 문서 오기 5건 — **SUPPORTED(5/5)**

① `strategy.py:15` 「직접 210봉을 조회」 · `:72` `entry_lookback_bars` 기본 **210**(config 230 이 덮음 · 초기화 로그 「진입평가=quant 230봉」) ✓ ② `config.yaml:12` 「D 거래량 전일**+100%**」 vs `rules.py:57` `vol_ratio=1.0` + `:106` `vol_t >= vol_prev*self.vol_ratio` ✓ ③ `screener.py:33` 「조건E(이등분선) today_mask 용 datetime 보강」 · `strategy.py:182-183` 동일 문구 — `_today_mask` 호출은 `rules.py:158,213,291`(다른 룰) 뿐, `rule_envelope_200d_high` 의 E 는 `:110` `(high_t + low_t)/2` 마지막 봉만 ✓ ④ `README.md:7` 「유일 신규 엣지」 vs `:32-33` 「alpha 가 비강세장 한정」 · `_WALKFORWARD:52` ✓ ⑤ `trading_config.json:45` `none`, `reports/books_research/_REtest_regime_gate.md` 에 「envelope」 0회 ✓.
🟠 **미세 정정**: §1-② 「`rules.py:9`」 → D 주석은 **`:10`**(:9 는 C).

## §9 X-5 / §3-F 스냅샷 — **SUPPORTED(시점 주석 필요)**

지금 `screener_snapshots` envelope = **103행/32일**(보고서 101/31). 차이 = `scan_date=2026-08-21` **2행, created_at 2026-08-24 09:00:12** — 보고서(08:15) 이후 생성. 그 시점 기준 101/31 은 맞다. score↔`close×volume×adj`: 1% 이내 **89/103** · 5% 이내 **101/103** · 최대 **6.40%** · close 일치 **0/103**(보고서 87/99/6.4/0 ⇒ 신규 2행이 1% 안) ✓ · 08-20 001210 **65,565,581,920 vs 65,604,858,820** ✓ · 최대 15행 **06-11** ✓ · 06-12 로그 `[E6] book_envelope_200d: screener_snapshots 10건 (D-1=2026-06-11)` ✓ · rank 11~15(064290·160980·219130·025560·040350) 06-12 매수 **0** ✓. 08-20 스냅샷 6종(001210·161890·192820·241710·005180·189330) = 08-21 신호 6종 ✓(ENV-7 「유령 0건」). `screener.py:41-43` `score = last_close * last_vol` ✓ · `constants.py:143` `MAX_CANDIDATES_PER_STRATEGY=20` · `screener_snapshot_collector.py:113-115` 덮어쓰기 ✓.
→ 보고서 §3-F·§2-5 에 「08-24 08:15 조회 기준」 한 줄 추가 권고.

## §10 나머지 (독해·로그)

| 항목 | 판정 | 근거 |
|---|---|---|
| 3-E tp/sl 심김: 06-29 이후 26/26 · 06-10~23 24/0 · 140860 tp 0.336/sl 0.03 · 089970 tp −0.0188 | SUPPORTED | `v3` 원장 `target_profit_rate/stop_loss_rate` ✓ · `position_monitor.py:311-313` 주석 「089970 2026-06-12」 ✓ · 원장 `목표 익절 도달 (0.84% >= -1.88%)` ✓ |
| 트레일링 4건(069960 06-10·004170 06-11·093370 06-15·034730 06-22, +644,200) · `:292 strategy_for_sell is None` 분기 | SUPPORTED | `v1` ✓ · :292 ✓ · :300-301 문구 ✓ |
| ENV-6 쿨다운 `constants.py:290` `ENTRY_COOLDOWN_SECONDS=60` · `trading_context.py:497-508` | SUPPORTED | ✓ |
| ENV-7 매도 루프가 봇 전체 보유를 돈다 | SUPPORTED(독해) | `base.py:691` `for stock in ctx.get_positions()` → `trading_context.py:300-307` owner 필터 없음 → `strategy.py:131` 비소유면 `_check_buy` 로 하강(단 :134/:136 K·일일 게이트가 먼저 None 을 낼 수 있음) |
| ENV-8 max_hold 오프바이원 | SUPPORTED(독해) | PM `:272-276` `count_trading_days_between(last_buy_time, now)` 그대로 `:281 days_held >= max_days` · 전략 `:309` `− 1` |
| ENV-10 `screener.py:24` `p = self.default_params()` 직독 | SUPPORTED | ✓ |
| §3-1 시각열 09:00:32 → 09:00:56(103개) → 09:01:44 | SUPPORTED | :414 `screener_snapshots 저장 … 6건` · :575 `001210 일봉 데이터 수집 완료: 103개` · :576/:601 저장 · :810 매수 시그널 |
| `describe_impossible_drop` 하락만·창 전체 | SUPPORTED | `data_sanity.py:82` `ret < threshold` · `_rule_screener_base.py:94` `sanity_window=None` |
| `base.py:686` `ctx.buy` · `:694-701` exit_timeframe daily 루프 | SUPPORTED | ✓ |
| 창 C-(a) `trading_context.py:143-174` 당일봉 제거 | SUPPORTED | ✓ |

## §11 정정 제안 요약 (보고서 직접 수정 안 함)

| # | 위치 | 현행 | 제안 | 등급 영향 |
|---|---|---|---|---|
| 1 | §3-D 표 | 익절 6 평균 +10.0 / 전략룰 5 평균 −4.5 | **+9.58** / **−4.42** | 없음 |
| 2 | §2-1·§0·§3-C | 「전일 +26.4%」「시초 +10.2%」 | 「08-20 시가→종가 +26.4%(전일 종가 대비 +30.0%)」「09:00 분봉 종가 +10.2%(일봉 시가 +7.2%)」 | 없음 |
| 3 | §2-6 | 004710 「2025-06~07 행 adj_factor=5」 | 「adj_factor=5 는 2021-01~2025-09-25, 200봉 창 안 27/24행」 | 없음 |
| 4 | §1-② | `rules.py:9` | `rules.py:10` | 없음 |
| 5 | §3-F·§2-5 | 101행/31일 | 「08-24 08:15 기준」 주석(09:00 스캔 뒤 103/32) | 없음 |
| 6 | §3-A SQL | alias `C` | `c` 컬럼과 충돌 — 실행 불가, alias 개명 | 없음 |
| 7 | **ENV-5** | 잠복 경로 = 폴백 1개 · 4종목 미인용 | 잠복 경로 **2개**(폴백 + `get_selected_stocks()` 공용 반환 `trading_context.py:296`) · A\B80 = `001510·003350·005930·010120` 명기 · 횡단 편 D-5 🔴 와 등급 표기 통일 | 🟡 유지 또는 「🔴(잠복)·실현 0/50」 — 사장님 결정 |

**등급 변경 제안**: ENV-1 🔴🔴 · ENV-2 🔴 · ENV-3 🔴 · ENV-4 🔴 **유지**(전부 실측 재현). ENV-5 만 횡단 편과 표기 통일 대상. **REFUTED 0건.**
