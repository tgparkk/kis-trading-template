# 급락 게이트의 판정 축을 종목 소속 시장에 맞춘다 — 설계

- 작성일: 2026-08-03
- 상태: 설계 합의 완료 (구현 계획 대기)
- 발견 경위: 2026-08-03 EOD 점검 — 급락필터 발동 중 매수 3건 체결을 추적하다 드러남
- 관련 메모리: `changelog-2026-08-03-eod-monitoring`
- 관련 커밋: `044a20e`(2026-06-02, 전략별 KOSPI/KOSDAQ 지수 + PIT 국면게이트 라이브 적용)

> **범위 주의**: 이 설계는 **시장 방향성 필터(`check_market_direction`)**만 다룬다.
> **PIT 일봉 국면 게이트(`check_regime_gate`)는 §5에서 명시적으로 범위 밖**으로 분리했다.
> 국면게이트까지 같이 옮기면 3전략의 BEAR 차단이 KOSDAQ 종목에서 조용히 풀릴 수 있다(§5).

## 1. 배경

`044a20e`(2026-06-02)로 급락 게이트가 전략별 지수 판정이 됐다. 전략 config의 `regime_index`("KOSPI"/"KOSDAQ"/"both"/"none")로 검사할 지수를 정한다.

**그러나 게이트의 판정 축(지수)과 대상 집합(후보 유니버스)의 범위가 일치하지 않는다.**

유니버스는 시장 무필터인데, 게이트는 특정 지수 하나로 판정한다. 두 지수가 갈라진 날 이 불일치가 실현된다.

### 확인된 사실 (2026-08-03, 코드·DB·로그 직접 확인)

| 항목 | 확인 내용 | 근거 |
|---|---|---|
| 유니버스가 시장 무필터 | `SELECT stock_code, COALESCE(market_cap,0), ... FROM daily_prices WHERE date = %s` — 시장 조건 없음 | `db/repositories/price.py:257-259` |
| 활성 8전략 전부 스크리너에 시장 라벨 필터 없음 | `daytrading:30` "시장 라벨 게이트 없음" · `book_pullback_ma5:24`·`ma20:24` "KOSPI+KOSDAQ 모두 허용" · 나머지는 시총만 | 각 `strategies/*/screener.py` |
| ma5/ma20의 시장 무관은 **의도된 컨셉** | 주석 "눌림목은 시장 무관" | `book_pullback_ma5/screener.py:24` |
| 게이트는 전략 단위 (종목코드를 안 받음) | `check_market_direction(self, regime_index: str = "both")` | `core/trading_decision_engine.py:136` |
| 검사 지수는 `regime_index` 하나로 결정 | `if idx in ("both","KOSPI"): checks.append(("KOSPI","0001",...))` / `("both","KOSDAQ")` → `("KOSDAQ","1001",...)` | `trading_decision_engine.py:165-168` |
| 임계값 | KOSPI **-2.5%** / KOSDAQ **-3.0%** | `config/constants.py:155-156` |
| 게이트 캐시 키 = `regime_index` 문자열 (TTL 60초) | `self._market_direction_cache[idx]` | `trading_decision_engine.py:156-161, 170-173` |
| 급락필터의 예외 정책 = fail-open | API 실패 시 "매수 허용" | `trading_decision_engine.py:194-197` |
| 호출부가 이미 `stock_code`를 보유 | `buy(stock_code, ...)` 인자, 게이트 호출은 같은 함수 내 | `core/trading_context.py:320, 338-346` |
| 라이브 유일 평가 지점 | 차단 로그 2,909건 **전부** 로거가 `trading_context`, `__main__` 0건. `main.py:524`는 `elif not self.strategies:` 분기라 8전략 로드 시 도달 불가 | 2026-08-03 로그 + `main.py:476-480` |

### 8전략 regime 설정 실측 (`config/trading_config.json`)

| 전략 | `regime_index` | `regime_gate` |
|---|---|---|
| elder_ema_pullback | KOSPI | none |
| book_envelope_200d | KOSPI | none |
| **daytrading_3methods_breakout** | **KOSDAQ** | none |
| minervini_volume_dryup | KOSPI | none |
| book_pullback_ma20 | KOSPI | **exclude_bear** |
| book_pullback_ma5 | KOSPI | **exclude_bear** |
| rs_leader | KOSPI | **exclude_bear** |
| deep_mr_dev20 | KOSPI | none |

### 결함의 두 방향

혼합 유니버스 + 단일 지수 게이트의 조합이므로 결함은 **8전략 전부**에 있고, 방향만 다르다.

| | 게이트 축 | 유니버스에 섞인 종목 | 결과 |
|---|---|---|---|
| daytrading (1개) | KOSDAQ | KOSPI 종목 | **보호 없음** — 급락 시 무방비 |
| 나머지 7개 | KOSPI | KOSDAQ 종목 | **엉뚱한 지수로 차단** — 기회 손실 |

### 2026-08-03 실측 — 조건이 실현된 날

| 지수 | 07-31 | 08-03 | 변화 |
|---|---|---|---|
| KOSPI | 6,595.45 | 6,246.63 | **-5.29%** |
| KOSDAQ | 719.76 | 737.36 | **+2.45%** |

- 급락필터 차단 **2,909건**(09:01:17 KOSPI -3.29% → 마감 -5.36%), 전략별 분포는 정확히 **KOSPI 7전략**, daytrading **0건**
- **자연실험**: 09:08:09 같은 초·같은 종목 `309930` 에 대해 `BookPullbackMa20`은 `매수 판단 스킵: 시장급락 (KOSPI -4.49%)`, daytrading은 통과 → 게이트 기전 자체는 설계대로 동작함을 실증
- daytrading 매수 3건 체결(`340810`·`475400`·`309930`), 마지막 건은 필터 최초 발동 10분 34초 뒤

### ⚠️ 미확인으로 남는 것 (개연성을 증거로 쓰지 말 것)

- **매수 3종목의 소속 시장**: 시스템 어디에도 market/exchange 라벨이 없어 **판정 불가**. 시총 438억·2,355억·181억으로 초소형이라 코스닥 개연성이 높으나, *"이번엔 다행히 전부 코스닥이었다"고 말해서는 안 된다.*
- **2,909건 중 KOSDAQ 종목 비율**: 같은 이유로 **셀 수 없다**. 과잉 차단의 규모는 미측정.
- 두 결함 방향 모두 **구조적으로 존재함은 확정**이나, **2026-08-03에 실현됐는지는 미확정**이다.

## 2. 목표 / 비목표

### 목표
- 급락 게이트의 판정 지수를 **매수 대상 종목의 소속 시장**으로 정한다.
- 8전략 전부에 적용한다(보호 누락·과잉 차단 양방향 해소).
- 기존 `regime_index` 값의 의미를 바꾸지 않는다 — **코드 배포 없이 config만으로 롤백 가능**해야 한다.

### 비목표
- 전략의 유니버스 컨셉 변경 (ma5/ma20의 "시장 무관"은 의도된 설계다 — §4.4)
- PIT 일봉 국면 게이트 (§5에서 범위 밖으로 분리)
- `market_cap` 등 유니버스 다른 축의 결측 문제
- 실시간 지수 조회 경로(`get_index_data`) 자체의 변경

## 3. 핵심 제약

| 제약 | 이유 |
|---|---|
| **`daily_prices`에 컬럼 추가 금지** | 별도 세션이 이 테이블에 DELETE 동반 전 이력 교체(FAIL 471종목)를 대기 중 (`6c4cffc` 후속) |
| **`check_market_direction` 캐시 키에 종목코드를 넣지 말 것** | 키가 `regime_index` 문자열(TTL 60초)이라 종목별 값이 섞이면 조용한 오염 |
| **`stock_list.json`·`stock_sector`의 `market` 필드를 쓰지 말 것** | 오염 확인됨 (§4.3) |

## 4. 설계

### 4.1 해석 레이어 — 공용 함수 시그니처를 바꾸지 않는다

게이트 호출 **전에** 종목 시장을 해석해 기존 함수에 넘긴다.

```
resolve_regime_index(configured: str, stock_code: str) -> str
    configured != "auto"  →  configured 그대로        # 기존 동작 100% 보존
    configured == "auto"  →  매핑 조회 → "KOSPI" | "KOSDAQ"
                             매핑 없음 → "both"       # §4.5
```

호출부는 이미 `stock_code`를 보유한다(`trading_context.py:320` 인자).

```python
# core/trading_context.py:338-343 (변경 후 개념)
regime_index, regime_gate = self._get_strategy_regime_settings()
resolved = resolve_regime_index(regime_index, stock_code)          # 신규
is_crashing, crash_reason = self._decision_engine.check_market_direction(
    regime_index=resolved                                          # 시그니처 무변경
)
```

**이 구조의 효과**:
- `check_market_direction` **시그니처·본문 무변경** → 8전략 매수 경로의 회귀 표면이 최소
- 캐시 키가 여전히 실제 지수("KOSPI"/"KOSDAQ"/"both") → **오염이 구조적으로 불가능**
- 해석 로직이 한 함수에 격리 → 단위 테스트 가능

### 4.2 설정 — `"auto"` 추가, 기존 값 보존

`regime_index`에 `"auto"` 값을 추가하고 8전략을 `"auto"`로 변경한다. 기존 `"KOSPI"`/`"KOSDAQ"`/`"both"`/`"none"`은 **그대로 유효**하게 남긴다.

- 롤백 = `trading_config.json`을 원래 값으로 되돌림. **코드 배포 불필요.**
- 명시적 오버라이드가 필요한 전략·테스트는 기존 값을 계속 쓸 수 있다.

### 4.3 데이터 — 별도 매핑 테이블

**신규 테이블** (`kis_template`):

```sql
stock_market (
    stock_code   varchar PRIMARY KEY,
    market       varchar NOT NULL,      -- 'KOSPI' | 'KOSDAQ'
    updated_at   timestamptz DEFAULT now()
)
```

- **수집**: `FinanceDataReader.StockListing('KOSPI')` / `('KOSDAQ')`. 이미 `requirements.txt`에 `finance-datareader>=0.9.202`로 선언돼 있고 `collectors/index_collector.py:29`에서 프로덕션 실사용 중이다. **KIS 토큰과 무관**하므로 봇 가동 중에도 안전하다.
- **갱신**: EOD 1회 (신규 상장 반영).
- **`daily_prices` 미변경** (§3 제약).

#### ⚠️ 기존 `market` 필드는 오염돼 있다 — 재사용 금지

| 소스 | 실측 | 판정 |
|---|---|---|
| `stock_list.json` | 962종목 **전부 `"KOSPI"`** (분포 실측) | 사용 불가 |
| `stock_sector` 테이블 | `kis_template`에 **존재하지 않음** | 사용 불가 |

코드에 이미 경고가 있다:

```
strategies/sample/screener.py:483-484
  # stock_sector 테이블의 market 컬럼이 전부 "KOSPI"로 부정확하므로
  # realtime 경로는 이를 쓰지 않는다.
```

**"이미 있는 것처럼 보이는 오염된 필드"가 존재한다는 점이 이 항목의 위험**이다. 새 테이블이 유일한 소스가 되도록 하고, 구현 시 오염된 필드로 폴백하지 않도록 한다.

### 4.4 스크리너는 건드리지 않는다

`book_pullback_ma5/ma20`의 "KOSPI+KOSDAQ 모두 허용"은 주석에 *"눌림목은 시장 무관"*이라 명시된 **의도된 컨셉**이다. 유니버스를 시장으로 제한하면 전략 정의 자체를 바꾸게 된다.

게이트만 종목 단위로 내리면 8전략이 **컨셉 변경 없이** 해결된다.

### 4.5 결측 정책 — `"both"` 폴백

매핑이 없을 때(신규 상장·수집 실패·배포 직후 빈 테이블) `"both"`로 떨어진다.

| 후보 | 채택 | 이유 |
|---|---|---|
| **`"both"` 폴백** | ✅ | 기존 코드가 이미 지원하는 경로(`:165-168`)라 새 분기가 안 늘고, **결측이 보호 과잉 쪽으로만 실패**한다(아래). 보수적이지만 매매는 계속된다. |

**빈 테이블일 때 무슨 일이 일어나는가** — 전 종목이 `"both"`가 되어 `KOSPI -2.5% OR KOSDAQ -3.0%` 를 검사한다. 이는 현재 동작(전략별 단일 지수)과 **같지 않고, 양방향 모두 더 보수적**이다:

| | 현재 | 빈 테이블 + `"auto"` | 차이 |
|---|---|---|---|
| KOSPI 7전략 | KOSPI만 검사 | KOSPI + KOSDAQ | KOSDAQ 급락 시에도 차단 |
| daytrading | KOSDAQ만 검사 | KOSPI + KOSDAQ | KOSPI 급락 시에도 차단 |

즉 **결측은 "보호 상실"이 아니라 "보호 과잉" 쪽으로만 실패한다.** 배포 직후·수집 실패 어느 쪽이든 무방비 구간이 생기지 않는다는 것이 이 폴백을 택한 결정적 이유다.
| fail-open (게이트 통과) | ❌ | 배포 직후 빈 테이블 = 급락 보호가 통째로 꺼짐. 2026-08-03 같은 날 2,909건이 전부 통과했을 것. |
| fail-closed (매수 차단) | ❌ | FDR 수집 1회 실패로 당일 매매 전면 중단. 운영 리스크가 결함 리스크보다 클 수 있다. |

부작용: 신규 상장 종목은 매핑 전까지 약간 과잉 차단된다. 허용한다.

## 5. 명시적 범위 밖 — PIT 일봉 국면 게이트

`check_regime_gate`에는 **resolved를 넘기지 않고 기존 config 값을 유지**한다.

3전략(`book_pullback_ma20`·`book_pullback_ma5`·`rs_leader`)이 `regime_gate="exclude_bear"`를 쓴다. 그런데:

```
trading_decision_engine.py:225-226
  # "both"/"none" 은 일봉 게이트에선 KOSPI 로 판정(KOSDAQ 지수 일봉 SSOT 없을 수 있음).
  index_name = regime_index if regime_index in ("KOSPI", "KOSDAQ") else "KOSPI"
```

**KOSDAQ 일봉 국면 데이터의 존재 여부가 확인되지 않았다.** 여기에 resolved를 넘기면 KOSDAQ 종목에 대해 `current_regime("KOSDAQ")`이 `None`을 반환하고, `:234-236`의 fail-open으로 **3전략의 BEAR 차단이 조용히 풀린다.**

> 🔑 보호가 조용히 약해지는 것은 이번 결함과 **같은 클래스**다. 알려진 비대칭에 대한 "기록"은 완화가 아니다 — 차단이거나 교정이어야 한다.

따라서 국면게이트는 KOSDAQ 일봉 국면 SSOT를 **먼저 확인한 뒤 별건**으로 다룬다. 이 설계에서는 손대지 않는다.

## 6. 실패 모드와 대응

| 실패 모드 | 대응 |
|---|---|
| FDR 수집 실패 | 기존 매핑 유지(테이블을 비우지 않는다). 신규 상장만 `"both"` 폴백. |
| 매핑 테이블이 빔(최초 배포) | 전 종목 `"both"` = 양방향 모두 보호 과잉 쪽(§4.5 표). 무방비 구간 없음. |
| FDR이 시장을 잘못 라벨링 | 게이트가 엉뚱한 지수로 판정 = **현재 결함과 동일 수준**. 악화는 아니나, 수집 시 KOSPI∩KOSDAQ 교집합이 비어있는지 검증한다. |
| `"auto"` 도입 후 예상 밖 동작 | `trading_config.json`을 이전 값으로 되돌림(코드 배포 불필요). |
| 캐시 오염 | 구조적으로 불가(§4.1). 회귀 테스트로 고정(§7). |

## 7. 테스트

| 대상 | 검증 내용 |
|---|---|
| `resolve_regime_index` 단위 | ① `configured != "auto"`면 매핑을 조회하지 않고 그대로 반환(기존 동작 보존) ② `"auto"` + 매핑 있음 → 해당 시장 ③ `"auto"` + 매핑 없음 → `"both"` ④ `"none"`은 `"auto"`보다 우선(면제 유지) |
| **캐시 오염 회귀** | KOSPI 종목과 KOSDAQ 종목을 60초 TTL 안에 연속 조회해도 **각자의 지수로 판정**되는지. 캐시 키가 실제 지수임을 고정. |
| 게이트 통합 | KOSPI -5.29% / KOSDAQ +2.45% 상황을 고정값으로 주입해 ① KOSPI 종목 차단 ② KOSDAQ 종목 통과 를 동시에 단언 (**대칭 단언** — 한쪽만 보면 판별력이 없다) |
| 8전략 보존 회귀 | config를 기존 값으로 두면 변경 전과 동일하게 동작 |
| 매핑 수집기 | KOSPI∩KOSDAQ 교집합 0건 · 수집 실패 시 기존 테이블 미파괴 |

⚠️ 테스트는 **라이브 트리에서 실행하지 않는다**(프로젝트 영구 규칙).

## 8. 롤백

1. `config/trading_config.json`의 8전략 `regime_index`를 원래 값(`"KOSPI"` 7개 / `"KOSDAQ"` 1개)으로 되돌린다.
2. `resolve_regime_index`는 비-`"auto"` 입력을 그대로 통과시키므로 **코드를 되돌리지 않아도 변경 전 동작이 복원**된다.
3. `stock_market` 테이블은 남겨도 무해하다(아무도 읽지 않게 된다).

## 9. 미해결 / 후속

| 항목 | 상태 |
|---|---|
| 2026-08-03 매수 3종목의 실제 소속 시장 | **판정 불가** → 매핑 적재 후 사후 확인 가능 |
| 2,909건 차단 중 과잉 차단 규모 | **미측정** → 매핑 적재 후 사후 산출 가능 |
| PIT 국면게이트의 시장 정합 | **별건** (§5) — KOSDAQ 일봉 국면 SSOT 확인이 선행 |
| ETF·우선주·리츠 등 비보통주 처리 | 이 설계 범위 밖. 현행 유니버스가 이미 포함/배제하는 대로 둔다. |
