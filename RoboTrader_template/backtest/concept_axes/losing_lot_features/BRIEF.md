# 연구 브리프 — 「패배 로트의 특징」 (2026-10-30 밤 · 설계 = 관리자 · 실행 = executor opus · 검증 = verifier opus · 읽기 전용 연구)

> 질문(사장님 10-30 밤): 「아직은 패배하는 종목의 특징 못 찾나요?」 → 지금까지는 조각(4분해 «선택 −21%p» · 대형주 Q5 중앙값 −25% · 갭다운 아침 손절 몰림 · 익절 뒤 재매수 1승 7패 · dt 괴리)만 있고 **진입 시각에 알 수 있던 값으로 패배 로트를 구별할 수 있나**를 한 표로 본 적이 없다. 이 연구가 그 표를 만든다. **관측·기술 통계만 · 판정·권고 언어 없음 · 룰 변경 0(동결 11-13)** · 발견은 「다음 그림자 측정 대상 후보」일 뿐이다.

## 0. 제한(위반 = 중단)
- 라이브 트리 `D:/GIT/kis-trading-template` 는 **읽기만**(로그 참고) · 코드·테스트 실행 금지. 작업은 이 워크트리 `D:/tmp/kis-wt-losers`(브랜치 `research/losing-lot-features` · base main `8ac2870`) 안 `RoboTrader_template/backtest/concept_axes/losing_lot_features/` 에만 쓴다. 봇 운영 코드(`core/ bot/ strategies/ main.py …`) 수정 0.
- DB `kis_template`(psycopg2 · 127.0.0.1:5433 · robotrader/1234) **SELECT 만** · DB명 하드코딩 대신 `config/constants.py` resolver 가 있으면 그걸 import(`resolve_daily_source_db()` 등 · 셋 다 "kis_template") — import 가 번거로우면 상수 "kis_template" 를 쓰되 파일 머리에 「resolver 와 같은 값」 1줄.
- 파이썬 = `D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe -X utf8` · 실행 위치 = `D:/tmp/kis-wt-losers/RoboTrader_template` · `PYTHONPATH=$PWD:$PWD/..`. pandas/numpy 는 venv 에 있을 것 · statsmodels 없으면 **설치 금지** · 날짜 블록 부트스트랩으로 대신.
- KIS API 호출 0 · 커밋·push 0(관리자가 뒤에) · 🔴 **미래 정보 누출 금지**: 모든 특징은 **진입 BUY 의 timestamp(KST) 이전에 존재한 값만**(D-1 일봉 · 당일 시가 · 진입 시각 전 분봉). 당일 종가·당일 returns_1d·매도 뒤 가격은 특징으로 쓰지 말 것. 🔴 SR1: 표본은 **청산된 로트만**(미청산 보유 로트 제외 · 평가손익 없음).
- `adj_factor` 는 가격에 곱하지 말 것(이미 조정됨) · volume 은 읽기 계층이 곱하므로 raw 를 다시 곱하지 말 것(CLAUDE.md).
- 숫자는 산출 파일에서 직접 · 비율은 분모 병기 · 금액 원 정수 · 보고 200줄 이내.

## 1. 표본
- `virtual_trading_records`(is_test=true) **SELL 1,273건(06-01 09:11 ~ 10-30 15:11 · 전부 buy_record_id 있음 · 승 444)** ↔ BUY(rid) 1:1 → 로트 1,273(8전략). 로트 열: 전략 · 종목 · 매수 시각(KST) · 매수가 · 수량 · 매도 시각 · 매도가 · 매도 사유(reason: 손절/익절/MA 이탈/EMA/trailing/기타 — 문자열 앞부분으로 분류) · gross profit_loss · gross %(= profit_loss ÷ (매수가×수량)) · 보유 시간(h) · 보유 거래일 수.
- 결과 변수 3개: ① 패배 = profit_loss < 0 ② 손절 청산(reason `손절%`) ③ **초과 수익 = 로트 gross % − 같은 기간(매수일 → 매도일) 전 종목 중앙값 수익률**(`daily_prices` volume>0 양끝 · 의사티커 6 제외 · `eq_median.py` 와 같은 규칙 · 매수일 close→매도일 close 기준 근사 · 당일 왕복은 그날 returns_1d 중앙값). ③이 「날 효과」를 뺀 값이다.

## 2. 특징(전부 진입 시각 이전 값 · D-1 = 매수일 직전 거래일)
| # | 특징 | 출처 | 비고 |
|---|---|---|---|
| F1 | 전략 | vtr.strategy | 8 |
| F2 | 후보 순위 · 분모 | `screener_snapshots` scan_date=D-1 · strategy · stock_code → rank_in_snapshot / 그날 그 전략 후보 수 | 없으면 «순위 없음» 범주(09-18 K 상향 전후 분리 표시) |
| F3 | 시총 5분위 | `daily_prices.market_cap` D-1 · 그날 전 종목 분위(market_cap>0) | Q1 소형 ~ Q5 대형 |
| F4 | 전일 등락 returns_1d · 5d · 20d(D-1) | daily_prices D-1 | 각 5분위(전 종목 기준) |
| F5 | 20일 변동성 volatility_20d(D-1) | daily_prices | 5분위 |
| F6 | 당일 시가 갭 = open(d0)/close(D-1) − 1 | daily_prices d0 open | 매수 시각이 09:00 이후면 시가는 알려진 값 · 구간(≤−3 / −3~−1 / −1~+1 / +1~+3 / >+3 %) |
| F7 | 매수 체결가 vs D-1 종가 괴리 % | vtr.price / close(D-1) − 1 | 구간(≤−5 / −5~−2 / −2~0 / 0~+2 / >+2) |
| F8 | 진입 시각 구간 | vtr.timestamp KST | 09:00~09:10 / 09:10~10:00 / 10~12 / 12~15:20 |
| F9 | 진입 때 지수 상태 | ① 지수 시가 갭(KOSPI·KOSDAQ 의사티커 d0 open/D-1 close) ② 가능하면 `minute_candles` 에 지수 의사티커가 있는지 확인해 진입 직전 1분봉 close 로 당일 등락률 — 없으면 ① 만 | 종목 시장(KOSPI/KOSDAQ)에 맞는 지수 |
| F10 | 거래대금 5분위 trading_value(D-1) | daily_prices | |
| F11 | 시장 · 섹터 | `stock_info.market` · `.sector`(스냅샷 · 시점 주의 1줄) | 섹터는 상위 10 + 기타 |
| F12 | 재매수 여부 | 같은 종목 SELL(어떤 전략이든)이 매수 전 5거래일 안에 있나 · 직전 종류(익절/손절/이탈) · 같은/다른 전략 | 보고서 6장 정의 그대로 |
| F13 | 다른 전략 동시 보유 | 매수 시각에 같은 종목 미청산 BUY 가 다른 전략에 있나 | |
| F14 | 그날 그 전략 몇 번째 매수 | 당일 같은 전략 BUY 순번(1~5+) | 하루 한도 효과 |
| F15 | 요일 · 월 | 매수일 | 보조 |

## 3. 분석(기술 통계 · 판정 없음)
1. **특징별 1차원 표**(F1~F15 각각): 범주/분위별 n · 패배율 · 손절률 · 평균 gross % · 중앙값 gross % · **평균 초과 수익(③)** · 중앙값 초과. 분모 n<30 범주는 «표본 작음» 표식.
2. **날 효과 분리**: 같은 매수일 로트 묶음 안에서 특징이 결과를 가르나 — 각 특징에 대해 「매수일 고정 효과」를 뺀 초과 수익(로트 ③ − 그 매수일 로트 평균 ③) 평균을 함께. 매수일별 로트 수 분포 1줄 · 급락일(10-13·10-15·10-23·10-27·10-30 등 KOSPI |등락| ≥3%) 로트가 전체의 몇 % 인지.
3. **전략 × 특징 2차원 표**: F3(시총) · F6(갭) · F7(괴리) · F8(시각) · F12(재매수) 다섯 개만 × 8전략(n 작은 칸 표식).
4. **다변량 1개(참고)**: 패배(①) 로지스틱 — 특징 F3·F4(1d)·F6·F7·F8·F9①·F12·F1 더미 · **매수일 블록 부트스트랩 1,000회**로 계수 구간(statsmodels 없으면 numpy 로 직접 · 로지스틱은 sklearn 있으면 쓰고 없으면 선형확률모형으로 대신 · 어느 쪽인지 적기). 계수 부호·구간이 0 을 걸치는지만.
5. **반전 검사**: 「패배 로트 특징」 상위 3개를 **승리 로트**에서도 같은 비율로 보나(특징이 패배를 가르는지 전체 분포인지).
6. 한계 고정 줄: 표본 1,273 이나 매수일 ≈100 · 급락일 몇 개가 지배 · 06-01~10-30 하락장 한 국면 · 사후 탐색(다중 비교 · 발견은 가설) · 미청산 제외 편향 · 09-18 K 상향·10-08 한도 «매수만» 등 룰 변화 구간 섞임 · 섹터 스냅샷 시점.

## 4. 산출(이 폴더)
- `build_features.py`(DB → `lots_features.csv` 1,273행 · 열 사전 `FEATURES.md`) · `analyze.py`(csv → 표 → `RESULTS.md`) · `run_log.txt`(rc · 초 · 행수 · 누출 자가검사 = 모든 특징 시각 < 매수 시각 assert).
- **`RESULTS.md`(200줄 이내)**: §0 결론 5줄(사실만 · 「특징 X 범주 Y 는 패배율 a%(n) vs 전체 b%」 꼴) · §1 표본·결과 변수 분포 · §2 특징별 1차원 표 15개(한 특징 한 표 · 작게) · §3 날 효과 분리 · §4 전략×특징 5표 · §5 다변량(참고) · §6 반전 검사 · §7 한계 · §8 「모른다」 · §9 **검증 레인이 재현할 핵심 수치 10개**(값 + SQL/열 이름).
- 끝나면 §0 결론 + 가장 큰 차이를 보인 특징 3개(n·패배율·초과 수익) + 「날 효과 뺀 뒤에도 남는 것」을 12줄 이내로 보고.
