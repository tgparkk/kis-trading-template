# Phase 0-P0-3 No Look-Ahead 잠금 인프라 — 산출물 보고서

**작성일**: 2026-05-24  
**담당**: Executor (Claude)  
**원칙 근거**: 사장님 대원칙 ① No Look-Ahead (PIT 강제) + ② Chronological Walk-Forward

---

## 신설 파일 3개

| 번호 | 경로 | 역할 |
|------|------|------|
| 1 | `RoboTrader_template/lib/__init__.py` | lib 패키지 초기화 |
| 2 | `RoboTrader_template/lib/pit_helpers.py` | PIT 헬퍼 모듈 — `safe_lag` / `pit_quantile` / `forward_return` |
| 3 | `RoboTrader_template/tests/test_no_lookahead.py` | No Look-Ahead 회귀 테스트 (12개) |
| 4 | `RoboTrader_template/scripts/10pct_strategy/check_no_lookahead.py` | Lint 검사기 (CI/pre-commit 통합용) |

---

## 1. PIT 헬퍼 모듈 (`lib/pit_helpers.py`)

### 함수 요약

| 함수 | 역할 | 핵심 제약 |
|------|------|-----------|
| `safe_lag(df, col, n, group_col)` | 종목별 groupby 후 n일 과거 shift | n < 0 → ValueError (forward leak 원천 차단) |
| `pit_quantile(df, value_col, date_col, n_bins)` | 날짜별 cross-section에서만 분위수 계산 | 전 기간 통합 분위수 금지 |
| `forward_return(df, price_col, n_days, group_col)` | n일 선행 수익률 (shift(-n)) | 호출 시 `FutureLeakWarning` 자동 발생 — 평가/레이블링 전용 |

### 핵심 보호 메커니즘

- `safe_lag(n<0)` → `ValueError` 즉시 — 실수로 forward leak 불가
- `forward_return()` → `FutureLeakWarning` 항상 발생 — 시그널 모듈에서 잘못 사용 시 경고 가시화
- `FutureLeakWarning` 커스텀 클래스 — pytest `filterwarnings` 또는 CI에서 특정 경고만 에러 승격 가능

---

## 2. 단위 테스트 결과 (`tests/test_no_lookahead.py`)

```
============================= test session starts =============================
platform win32 -- Python 3.9.13, pytest-8.4.2
collected 12 items

tests\test_no_lookahead.py::TestSafeLag::test_safe_lag_no_leak          PASSED
tests\test_no_lookahead.py::TestSafeLag::test_safe_lag_negative_raises  PASSED
tests\test_no_lookahead.py::TestSafeLag::test_safe_lag_zero             PASSED
tests\test_no_lookahead.py::TestSafeLag::test_safe_lag_multigroup_boundary PASSED
tests\test_no_lookahead.py::TestSafeLag::test_safe_lag_n2               PASSED
tests\test_no_lookahead.py::TestPitQuantile::test_pit_quantile_no_leak  PASSED
tests\test_no_lookahead.py::TestPitQuantile::test_pit_quantile_cross_section_range PASSED
tests\test_no_lookahead.py::TestPitQuantile::test_pit_quantile_no_future_influence PASSED
tests\test_no_lookahead.py::TestForwardReturn::test_forward_return_warning PASSED
tests\test_no_lookahead.py::TestForwardReturn::test_forward_return_correct PASSED
tests\test_no_lookahead.py::TestForwardReturn::test_forward_return_bad_n PASSED
tests\test_no_lookahead.py::TestForwardReturn::test_forward_return_group_boundary PASSED

12 passed in 0.27s
```

**핵심 회귀 테스트 설명**:

- `test_safe_lag_no_leak`: 1,000행 가짜 시계열 → safe_lag(n=1) 적용. 마지막 50행 절단 후 재계산 → 앞 950행 결과 완전 일치 (assert_series_equal)
- `test_pit_quantile_no_leak`: 전체 기간 vs 과거 절반만으로 pit_quantile 계산 → 과거 구간 분위 완전 일치 확인
- `test_forward_return_warning`: 호출 시 `FutureLeakWarning` 발생 여부 강제 검증

---

## 3. 기존 코드베이스 Leak 점검 결과

```
[INFO] Scanning for forward shift(-) leaks under: D:\GIT\kis-trading-template\RoboTrader_template
[INFO] Target subdirs: ['strategies', 'multiverse', 'screener', 'scripts/10pct_strategy']

[PASS] No look-ahead violations found. exit 0
```

**검사 대상**: `strategies/`, `multiverse/`, `screener/`, `scripts/10pct_strategy/` 하위 모든 `.py` 파일  
**위반 건수**: **0건** — 기존 코드베이스에 forward shift leak 없음 확인

### 화이트리스트 (검사 제외)
- `tests/` 하위 파일 (테스트에서는 forward_return 호출 정상)
- `lib/pit_helpers.py` (forward_return 구현체 자체)
- 파일명에 `forward` 포함 모듈
- `check_no_lookahead.py` 자체

---

## 4. 사용 방법

### 시그널/필터 코드에서

```python
from lib.pit_helpers import safe_lag, pit_quantile

# 전일 종가 (PIT 안전)
df["close_lag1"] = safe_lag(df, "close", n=1)

# 날짜별 시총 5분위 (PIT 안전)
df["cap_q"] = pit_quantile(df, "market_cap", "date", n_bins=5)
```

### EDA / 레이블링에서만

```python
from lib.pit_helpers import forward_return

# forward return — 평가 전용, 시그널 입력 절대 금지
df["fwd_5d"] = forward_return(df, "close", n_days=5)
# → FutureLeakWarning 발생 (의도적)
```

### CI / pre-commit 통합

```bash
python RoboTrader_template/scripts/10pct_strategy/check_no_lookahead.py
# exit 0 → 통과, exit 1 → 위반 (file:line 출력)
```

---

## 5. 향후 Phase와의 연결

- **Phase 1** (Forward Return 베이스라인): `forward_return()` 사용, 반드시 EDA 전용 컨텍스트에서만
- **Phase 2** (멀티버스 Stage A/B/C): 모든 시그널 함수는 `safe_lag()` / `pit_quantile()` 경유 의무
- **신규 전략 추가 시**: `check_no_lookahead.py` 를 PR 체크 또는 pre-commit hook으로 실행하여 자동 검증
