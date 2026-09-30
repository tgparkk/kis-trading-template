# gap_persistence — 「개장 전 재료가 있던 갭」의 갭 뒤 수익 측정 (2026-09-30)

- 사전등록: [`docs/prereg_2026-09-30_gap_persistence.md`](../../docs/prereg_2026-09-30_gap_persistence.md) (측정 전 동결 · sha256 은 두 스크립트가 인쇄)
- 리포트: [`docs/report_2026-09-30_gap_persistence.md`](../../docs/report_2026-09-30_gap_persistence.md)
- 연구 전용. 라이브 코드(`bot/ core/ strategies/ collectors/ config/`) 수정 0줄 · `config.constants` 에서 `SQL_STOCK_ONLY`·`resolve_daily_source_db` 를 import 만 한다.

## 파일

| 파일 | 역할 |
|---|---|
| `build_events.py` | DB(SELECT 만 · 세션 `default_transaction_read_only=on`) → 이벤트·조건·결과 표. 가격·뉴스·DART 3쿼리 + 예시 2쿼리. |
| `analyze.py` | DB 접속 없음. 날짜 고정효과 차이 · 날짜 클러스터 부트스트랩(B=1,000 · `default_rng(20260930)` 비교마다 새로) · MDE · 판정. |
| `dart_tags_copy.py` | `D:/tmp/kis-wt-dart-events` 의 `dart_tags.py`(커밋 `a0c88e2`) **바이트 그대로 사본** · sha256 `77def4a0…a5f37dfa`. 빌드가 원본과 해시 일치를 인쇄한다. 고치지 말 것 — 원본이 바뀌면 다시 복사하고 해시를 갱신. |

## 실행 (워크트리 `RoboTrader_template/` 에서 · 라이브 트리에서 실행 금지)

```
D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe -m backtest.gap_persistence.build_events
D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe -m backtest.gap_persistence.analyze
```

- 출력 폴더 = `D:/research-archive/gap_persistence_20260930/`(환경변수 `GAP_PERSIST_OUT` 로 바꿀 수 있음).
  - `events.parquet`·`events.csv`(gap ≥ +3% 후보 전부 · U4/U5/U6 는 필터가 아니라 **플래그 열** — 분석이 거른다)
  - `coverage_by_day.csv`(창 거래일별 N1·N2b 커버리지) · `example_126340.json`(비나텍 예시 원자료 · 제목·연결만)
  - `build_meta.json`·`analysis_meta.json`(sha256·쿼리·행 수·실행 시간) · `comparisons.csv`(비교 81행)
  - `build_stdout.txt`·`analysis_stdout.txt`(호출 쪽 `tee` 사본)
- 실행 시작 시 `config/key.ini` 가 없다는 경고 2줄이 찍힌다(`config` 패키지 import 부수효과) — KIS 키를 쓰지 않으므로 무해.

## 🔴 알아둘 데이터 함정 (사전등록 §2)

1. **`news.created_at` 은 저장값 `< 2026-03-09 12:00` 구간이 UTC 다**(서버 timezone 은 Asia/Seoul). 소수초가 0 인 행 = UTC 구간과 100% 일치. 이 코드는 `+9시간` 보정한다(`to_kst`). 보정 없이 개장 전 창을 자르면 D 장중·장후 기사가 섞인다.
2. 비-dart 기사의 종목 연결은 2026-01-08~02-09 · 2026-08-18~09-30 에만 살아 있다. 그 밖의 날짜의 「뉴스 없음」은 「못 봄」이다 → 커버리지 규칙(적격 연결 종목 ≥ 20).
3. `news.source='dart'` 는 공시 피드다(뉴스 아님). N1 에서 뺐다.
4. `daily_prices` 2026-01-11(일) 1행 — 거래일에서 제외(행 ≥ 1,000 규칙).
5. `adj_factor` 는 2026-06 부터 대부분 NULL — 분할 필터가 눈이 멀어 ±30% 가격제한폭 위생 필터를 함께 쓴다.
