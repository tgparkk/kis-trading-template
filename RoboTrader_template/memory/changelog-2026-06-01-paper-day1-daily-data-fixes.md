# 2026-06-01 페이퍼 첫날 운영 + 일봉 데이터 정확성 버그 3건 수정

## 페이퍼 운용 첫날 결과
- 5전략(Elder·Minervini·Ma20·Ma5·DayTrading3Methods) 페이퍼 가동 첫날. 무사고(ERROR/CRITICAL 0), API 성공 99.88%(96,494콜, 속도제한 0.11%).
- **실현손익 +69,730원 (1전 1승)**: Minervini가 332570을 09:00 @12,250×367 매수 → 09:11 @12,440 매도(+1.55%). 미청산 포지션 없음.
- on_tick: Minervini 1,516 / 나머지 4전략 각 ~505회. **5전략 전부 정상 틱**(멈춘 전략 없음). Minervini만 진입조건 충족해 거래.

## 발견·수정한 버그 3건 (전부 커밋·푸시됨)

### 1. 매도기록 전략명 불일치 — 커밋 44b9a8f
- 증상: 같은 라운드트립인데 BUY=`minervini_volume_dryup`(폴더키), SELL=`MinerviniVolumeDryupStrategy`(클래스명).
- 원인: 매도경로(`trading_decision_engine.py:640`)가 `trading_stock.strategy_name`(=클래스명, `models.py:207`이 `owner_strategy_name` 미러)을 넘김. 매수는 폴더키(`ledger_key`) 기록.
- 영향: 재시작 복원(`get_strategy_trade_sums`가 strategy 컬럼 GROUP BY)이 라운드트립을 두 버킷으로 쪼개 전략별 현금 재구성 오류.
- 수정: `virtual_trading_manager.py` `execute_virtual_sell`에서 런타임 원장 owner(`_position_owner`=폴더키)를 single source of truth로 삼아 DB 기록 strategy를 폴더키로 정규화(+5줄). 매도 진입점 단일이라 전 경로 커버, 레거시(원장 미할당)는 전달 strategy 유지=하위호환.
- DB 정정: 기존 id=812 SELL 행을 `minervini_volume_dryup`으로 UPDATE 완료(사장님 승인).
- 테스트 4건 추가, 회귀 277 passed.

### 2. (A) Elder 일봉 40봉 — lookback 깊이 (커밋 a459f7e에 포함)
- 증상: 후보 9종목 전부 일봉 40개만 전달 → Elder(min_len=70) 333회 전부 `일봉 40건 < min_len=70`으로 스킵, 종일 무력화.
- 원인: `trading_context.py:108 get_daily_data(days=60)` 기본값 60(**달력일** → `price.py get_daily_prices`가 `date >= now-days`로 해석 → 영업 ~40봉). base on_tick(`base.py:534`)이 days 없이 호출. **설정 상수 `OHLCV_LOOKBACK_DAYS=120`은 이 경로에 미연결**(전날종가 조회용 `main.py:795`에서만 사용). 즉 "120일로 늘려 70봉 충족"이 실제 로드경로엔 적용 안 돼 있었음.
- 수정: 기본 `days=None`→`OHLCV_LOOKBACK_DAYS`(120) 연결 → 영업 ~79봉, 70봉 충족. days 명시 호출은 하위호환 유지.

### 3. (B) 미완성 당일봉을 일봉룰에 투입 — 신규·중요 (커밋 a459f7e에 포함)
- 증상: 장중 `daily_prices`에 부분 거래량으로 upsert되는 **당일 미확정봉**(거래량=직전일 1~3%)이 룰의 `df.iloc[-1]`로 들어감.
  - Minervini volume_dryup **오발사**: 미완성 봉 저거래량이 recent/base를 0.70 게이트 아래로 끌어내림(010140 raw 0.674 발사 → 확정 0.794 미발사).
  - DayTrading 돌파 **영구 무발사**: 거래량배수 0.01~0.12x로 ×2.0 게이트 불충족(확정봉 0.54~8.45x면 정상 발사).
  - MA5/MA20 양봉/종가 판정 왜곡(034020 음봉 1개로 탈락 등).
- 원인 경로: `data_collector.py:67` `get_ohlcv_data("D",150)` → `_save_daily_to_db` → `price.py save_daily_prices_batch` ON CONFLICT upsert로 장중 당일 부분봉이 DB에 기록 → `get_daily_data`가 그대로 반환.
- 판정: **버그**(모든 룰/전략 주석이 "확정 일봉/no-lookahead/현재봉 제외" 전제, 백테스트는 `df.iloc[:i+1]` 확정봉 사용).
- 수정: `get_daily_data`에 `_drop_unconfirmed_today_bar` 추가 — 마지막 봉 날짜가 KST 오늘이면 1봉 제거(읽기 레이어 single source of truth, 룰/전략 무수정으로 회귀위험 최소). 당일봉만 있으면 None.
- 운영 데이터: 당일 부분봉 row는 장 마감 후 `PostMarketDataSaver.save_daily_data`가 확정봉으로 자동 정정(수동 불필요).
- 테스트 4건 추가. (A)+(B) 합쳐 `test_trading_context.py` 63 passed.

## 회귀 전체
- 전체 스위트 2616 passed / 19 failed. 19건은 수정 전 baseline과 **동일한 사전존재 실패**(실DB 의존 exit_multiverse/phase5/screener, mock 누수 — 격리 실행 시 통과). 이번 수정이 새로 깬 테스트 0건. `test_adjacent_grid.py`는 `import RoboTrader_template.runners` 경로오류로 수집단계 실패(사전존재).

## ★다음 세션 필수 조치
- **봇 재시작 필요**: 3건 모두 코드 수정이라 다음 `run_robotrader.bat` 가동 시 반영됨. 재시작 전까지는 (구코드) 라벨불일치·40봉·미완성봉 문제가 재발.
- **재시작 후 기대 변화**: Elder가 매일 평가 가능(죽지 않음), Minervini 스퓨리어스 신호 감소(거래 빈도 줄 수 있음=정상), 돌파전략 발사 가능, 매도기록 폴더키 일관.
- 며칠 페이퍼 관찰 후 캘리브레이션. 오늘 332570 거래는 확정봉 기준으로도 trigger라 우연히 유효(010140·001440 추가신호가 스퓨리어스였던 것).

## 환경 메모
- 동시 실행 python main.py 5개는 **각각 다른 프로젝트**(rt=RoboTrader, rtquant=RoboTrader_quant, NewsQuant, RoboTrader_quant_mom, kis-template). 우리 봇은 cwd=`...\RoboTrader_template`인 1개뿐. CommandLine만으론 구분 불가 → `psutil.Process(pid).cwd()`로 확인.
- 로그 `logs/trading_YYYYMMDD.log`는 UTF-8. PowerShell/cp949 콘솔에서 깨지면 `python open(encoding='utf-8')` + `sys.stdout.reconfigure(encoding='utf-8')`.
