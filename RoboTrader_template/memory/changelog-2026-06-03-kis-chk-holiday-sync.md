# 2026-06-03 KIS chk-holiday 휴장일 동기화 — 4개 프로젝트 적용

## 배경
6/3(수)은 제9회 전국동시지방선거 휴장일. 사장님이 4개 트레이딩 봇의 휴장일 인식을 점검 요청.
- **RoboTrader / RoboTrader_quant / RoboTrader_quant_mom**: 휴장일을 **하드코딩 리스트**로 관리 →
  2026-06-03이 셋 다 누락(가동 중 평일로 오판). quant/quant_mom은 대체공휴일 자동계산도 없어
  8/17(광복절대체)·10/5(개천절대체)도 누락. 3개 봇 모두 실전매매(paper_trading=False) 또는 가동 중.
  → 우선 정적 리스트에 2026-06-03(+8/17·10/5) 추가로 응급 보완. 사장님이 봇 정지.
- **kis-template(RoboTrader_template)**: `holidays` 라이브러리(holidays.KR) 사용으로 6/3·8/17·10/5는
  이미 정확 인식(로그상 "시장 상태: holiday" 확인, 매매 0건). 단 **KRX 연말휴장(12/31)은 미인식**
  (라이브러리가 거래소 자체 휴장일은 모름).

→ 근본 해결: KIS 공식 API **`chk-holiday`(국내휴장일조회, CTCA0903R)** 를 권위 소스로 도입.

## API 계약 (라이브 검증 완료)
- `GET /uapi/domestic-stock/v1/quotations/chk-holiday`, tr_id=`CTCA0903R`
- params: `{BASS_DT(YYYYMMDD), CTX_AREA_NK:"", CTX_AREA_FK:""}`
- 응답 `output`: BASS_DT부터 **연속 24 캘린더일** 리스트. 각 행:
  `bass_dt, wday_dvsn_cd, bzdy_yn(영업일), tr_day_yn(거래일), opnd_yn(개장일 Y/N), sttl_day_yn(결제일)`
- **판정: `opnd_yn=='N'` ⇒ 휴장**(주말·공휴일·KRX연말휴장 포함). 검증값 20260603=N, 20261231=N, 20260604=Y.

## 설계 (4개 공통, 스펙 D:\tmp\holiday_kis_spec.md)
1. **라이브 전용 보정**: API 발견 휴장일을 "런타임 휴일셋"에만 추가. 과거 날짜 조회(백테스트·거래일계산)는
   기존 캘린더 그대로 → **백테스트 무손상**.
2. **하루 1회 동기화 + 연중 적재**: BASS_DT를 24일씩 전진시켜 기본 16페이지(~1년)를 1회 sync에 수집.
   캐시파일 `holiday_kis_cache.json`에 `synced_date` 기록 → 같은 날 재호출/재시작 시 API 미호출.
3. **fail-open**: API/네트워크 실패 시 예외 삼키고 기존 캐시 유지 + 기존 캘린더로 폴백(가동 차단 안 함).

## 변경 파일 (프로젝트별)
공통: `api/kis_market_api.py`에 `get_chk_holiday()` 추가(get_inquire_price 스타일 미러),
신규 `utils/holiday_kis_sync.py`(sync_today 페이지네이션·캐시·is_kis_closed_day),
`main.py` 기동 시 auth 완료 직후 `sync_today()` 1회(try/except), `.gitignore`에 캐시파일 추가.
게이트 배선:
- **kis-template / quant / quant_mom**: `utils/korean_holidays.py:is_special_holiday`에 런타임셋 OR 추가
  (lazy import, try/except) → `is_holiday`·`trading_calendar.is_trading_day`·`market_hours._is_holiday` 전파.
- **RoboTrader**: `config/market_hours.py:is_trading_day`의 KRX 분기에서 `KOREAN_HOLIDAYS` 멤버십 체크
  직후 런타임셋 검사 추가(set 기반이라 dict 패턴과 다름).

## 테스트 (TDD, 전부 mock — 네트워크 무호출)
신규 `tests/test_holiday_kis_sync.py`(RoboTrader는 tests/unit/): 파싱·sync·하루1회가드(2번째=0회 호출)·
페이지네이션(2페이지 BASS_DT 전진, 양 페이지 휴장 누적)·fallback(None/[]/예외)·게이트통합(런타임 12/31 주입).
- 신규: kis-template 19, RoboTrader 17, quant 15, quant_mom 20 — **전부 통과**.
- 회귀: kis-template 126·RoboTrader 46·quant/quant_mom 캘린더 스위트 — **신규 실패 0**
  (quant 계열의 test_fix2_simple.py exit(1) INTERNALERROR는 사전존재·무관).

## 라이브 e2e 검증 (4개 전부, 각자 자격증명으로 실제 API 호출)
sync=True, 연중 125일 적재. 게이트 결과 4개 동일:
- 2026-06-03(지방선거)=휴장, **2026-07-17(제헌절)=휴장**, **2026-12-31(연말휴장)=휴장**, 2026-06-04=거래일.
- **★핵심 성과**: 제헌절(2026 공휴일 재지정)·연말휴장은 holidays 라이브러리·수동리스트 **모두 누락** →
  KIS 공식 API만 잡아냄. API 방식 채택의 결정적 근거.

## 잔여 / 주의
- **git 커밋 미실시(사장님 승인 대기)** — 4개 레포 각각 커밋 필요.
- **봇 재시작 시 반영**: 다음 거래일(6/4) 재가동 시 신 코드 로드 + 기동 sync 실행.
  (오늘 force=True 검증으로 각 레포에 synced_date=2026-06-03 캐시 생성됨 → 오늘 재시작해도 API 재호출 없이 사용.)
- 정적 리스트 응급 보완분(quant/quant_mom의 6/3·8/17·10/5, RoboTrader 6/3)은 그대로 둠(이중 안전).
- 페이지 16회 순차호출 중 간헐 HTTP500/속도제한은 kis_auth 재시도로 흡수(검증 중 1회 관측, 정상 완료).
