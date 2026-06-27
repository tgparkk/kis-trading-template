# 2026-06-27 — 스크리너 시총 가드 fail-closed 수정 + 2024–26 깨끗창 재측정

> 측정 전용·라이브 로직 행동 보존(채워진 시총엔 무변화). 영구룰: 숫자 날조 금지 —
> 아래 수치는 모두 `scripts/step3c_size_sector_filter.py` 실제 실행 산출(워킹트리).
> 원시 출력: `scratchpad/step3c_core_2024clean.md`, `scratchpad/step3c_core.log`.
> **커밋 안 함** — diff 만 워킹트리에 남김.

---

## 배경 — 확정된 버그 (fail-open 시총 가드)

5개 스크리너 어댑터의 `base_filter` 가 시총 결측을 *fail-open* 으로 통과시켰다:

```python
mcap = u.get("market_cap", 0)
if mcap > 0 and mcap < p["min_market_cap"]: continue   # 하한형(elder, minervini)
if mcap > 0 and mcap >= p["max_market_cap"]: continue  # 상한형(daytrading, ma5, ma20)
```

`mcap > 0 and …` 가드 때문에 시총이 결측(quant `COALESCE(market_cap,0)` → 0)이면
시총 컷을 **조용히 우회**한다. quant `daily_prices.market_cap` 채움률:
2021=0% / 2022=0% / 2023=0.3% / 2024=84.8% / 2025=99.6% / 2026=99.8%.
→ 2021–23 백테스트는 모든 시총컷이 무력화되어 전략이 자기 *컨셉 유니버스*가 아닌
전체 union 을 매매한 것으로 측정됐다. 라이브(2025–26)는 시총이 채워져 정상.

### 비대칭 함정 (반드시 양쪽 모두 fix)
`mcap > 0` 만 삭제하면 **하한형만 고쳐지고 상한형은 안 고쳐진다**:
- 하한형 `if mcap < min`: 결측(0) < min → 제외 ✅
- 상한형 `if mcap >= max`: 결측(0) >= max → False → **여전히 통과** ❌

올바른 규칙 = **"시총 확인 불가(결측/0/None)면 무조건 제외"** 를 하한·상한 공통 적용.

---

## Phase A — fail-closed 수정 (중앙화 + TDD)

### 전수 점검 결과 (시총 가드를 쓰는 전 스크리너)
`strategies/**/screener.py` grep → 시총 가드 보유 어댑터는 정확히 **5개**:

| 전략 | 가드 종류 | 컨셉 |
|---|---|---|
| `elder_ema_pullback` | 하한 `min 5천억` | 대형 |
| `minervini_volume_dryup` | 하한 `min 3천억` | 중형+ |
| `daytrading_3methods_breakout` | 상한 `max 5천억` **미만(>=)** | 중소형 |
| `book_pullback_ma5` | 상한 `max 3조` **이하(>)** | 중소형 |
| `book_pullback_ma20` | 상한 `max 3조` **이하(>)** | 중소형 |

`book_envelope_200d`·`rs_leader` 는 시총컷 없음(거래대금만) → **무수정**.
`sample`·`bb_reversion`·`deep_mr_dev20` 등 나머지 어댑터도 시총 가드 없음 → 무수정.
(`strategies/books/*/rules.py` 의 close_betting 등은 라이브 어댑터가 아닌 책-조사 룰로,
자체 `market_cap_checked` 로직을 별도 보유 → 범위 외, 무수정.)

### 중앙화 헬퍼
`strategies/_rule_screener_base.py` (RuleScreenerBase) 에 공통 헬퍼 추가:

```python
@staticmethod
def _passes_market_cap(mcap, *, min_cap=None, max_cap=None, max_inclusive=False) -> bool:
    if mcap is None or mcap <= 0:        # 결측 → 컨셉 검증 불가 → 제외(fail-closed)
        return False
    if min_cap is not None and mcap < min_cap:
        return False
    if max_cap is not None:
        if max_inclusive:
            if mcap > max_cap:           # '이하' 컨셉(ma5/ma20)
                return False
        elif mcap >= max_cap:            # '미만' 컨셉(daytrading, 기본)
            return False
    return True
```

5개 어댑터의 `base_filter` 가 이 헬퍼를 호출하도록 중복 제거.
`max_inclusive` 플래그로 daytrading(`>=` '미만')과 ma5/ma20(`>` '이하')의
**경계 의미를 정확히 보존**(라이브 동등성). `.get("market_cap", 0)` 기본값 fallback 도
제거(결측을 0 으로 위장하지 않음) — `backtest/screener_universe.py::_snapshot_to_universe`
포함.

### TDD 테스트 (먼저 RED → 구현 → GREEN)
신규/수정 케이스:
- `tests/test_rule_screener_base.py`:
  `test_passes_market_cap_excludes_missing_both_sides`(결측 None/0/음수 → 하한·상한 모두 제외),
  `test_passes_market_cap_min_cap_boundary`,
  `test_passes_market_cap_max_cap_exclusive_boundary`(`>=` 경계 제외),
  `test_passes_market_cap_max_cap_inclusive_boundary`(`>` 경계 통과).
- 각 어댑터 테스트(elder/minervini/daytrading/ma5/ma20):
  `test_base_filter_excludes_when_market_cap_unknown`(결측 전수 제외, 키 자체 결측 포함),
  `*_boundary_*_live_equivalence`(**채워진 시총엔 기존과 동일** = 경계값 정확 검증으로
  라이브 동등성 입증).
- `tests/test_screener_universe.py`: 기존 "UNK(시총0) 통과" 단언을 fail-closed 제외로 갱신.

기존에 *버그 동작*(결측 soft-pass)을 단언하던 테스트 3종(elder tier·daytrading/minervini/
ma5/ma20 의 `passes_when_market_cap_unknown`, universe 의 UNK 통과)을 의도된 새 동작으로
플립. 이는 테스트 해킹이 아니라 **의도된 행동 변경의 명세 갱신**이다.

### 결과 (실측)
- 표적 스크리너 스위트(7파일) + PIT 게이팅: **41 passed**.
- 데이터완전성(Phase B): **6 passed**.
- 전체 스위트(scipy 미설치 `tests/exit_multiverse` 제외): **3279 passed, 15 failed, 3 skipped**.
  - 15 failed 는 전부 **본 변경과 무관한 기존/환경 실패**: 시장 휴장 캘린더
    (`test_market_hours_holidays` NYSE/TSE, `test_market_boundaries`), 분봉/인트라데이
    캐시(`test_minute_loader`, `test_intraday_universe`), `test_discovery::bb_reversion`.
    grep 확인 — 이 파일들은 `market_cap`/`base_filter`/`_rule_screener_base`/
    `screener_universe`/`data_completeness` 를 일절 참조하지 않음. 대표 실패(NYSE 크리스마스)는
    휴장일 판정 버그로 본 작업과 무관.
  - `tests/exit_multiverse` 4건은 `scipy` 미설치 수집오류(환경) — 본 변경과 무관.

### 라이브 동등성 입증
- 라이브 경로 `QuantDailyReader.get_universe_snapshot` 는 `COALESCE(market_cap,0)` →
  결측이 0.0 으로 들어온다. 2025=99.6% / 2026=99.8% 채워짐이므로 **라이브에서 제외되는
  종목은 시총 결측(0)인 극소수**뿐.
- 경계값 테스트(`*_live_equivalence`)가 채워진 시총의 통과/제외가 기존과 1:1 동일함을
  보장(min 경계 통과, daytrading max 경계 `>=` 제외, ma5/ma20 max 경계 `>` 통과).
- 유일한 행동 변화 = **결측(0) 종목이 이제 제외됨**(의도된 변경).

---

## Phase B — 백테스트 데이터완전성 가드 (TDD)

신규 `backtest/data_completeness.py`:
- `market_cap_coverage(reader, scan_dates, min_coverage=0.8) -> CoverageReport`:
  측정 구간 snapshot 의 `market_cap > 0` 채움률 집계(날짜별 + 전체).
- `assert_market_cap_coverage(..., strict=False)`: 임계 미만이면 strict 시 예외
  (`DataCompletenessError`), 아니면 경고 로그. 합격 시 조용히 통과.
- `scripts/step3c_size_sector_filter.py` 진입부에 배선 + `--min-cap-coverage`/
  `--strict-coverage` 플래그. 오염 구간(2021–23)을 모르고 측정하는 **사일런트 재발 방지**.

테스트 `tests/test_data_completeness.py` (6 passed): 정상 채움률 OK, 저채움 NOT-OK,
빈 snapshot NOT-OK, strict 예외, warn-only 무예외, 합격 시 무경고.

**실측 가드 작동**: 2024–26 월별 31 scan_date 채움률 = **91.8%**(67948/74049) → OK.
(2021–23 을 포함했다면 임계 미만으로 경고/실패했을 것.)

---

## Phase C — 2024–26 깨끗창 재측정 (수정 코드로)

`scripts/step3c_size_sector_filter.py --start 2024-01-01 --end 2026-06-26
--strategies <7전략> --configs baseline floor300 floor500` (월별 PIT, max_per_stock=100만,
multiverse4 SPECS 정본 sim/청산/비용). 데이터완전성 가드 통과(91.8%).

### 수정된 base_filter 가 컨셉 유니버스를 올바로 binding 하는가?
union 크기(전체시장 2486 대비) — **시총컷 전략이 자기 컨셉으로 좁혀짐을 확인**:

| 전략 | union | 시장대비 | 해석 |
|---|---|---|---|
| elder_ema_pullback | 618 | 25% | 대형(5천억+)으로 좁혀짐 — fail-open 시절 결측 누수 제거 |
| minervini_volume_dryup | 904 | 36% | 중형(3천억+) |
| daytrading_3methods_breakout | 1862 | 75% | 중소형(5천억 미만) — 시장 대부분이 소형 |
| book_pullback_ma5 / ma20 | 2109 | 85% | 중소형(3조 이하) |
| book_envelope_200d / rs_leader | 2271 | 91% | 시총컷 없음(거래대금만) |

→ elder 25%·minervini 36% 는 컨셉 유니버스가 올바로 bind 됨을 보인다(과거 오염
구간에선 결측 누수로 더 넓었을 것).

### 비교표 (전략 × 구성, 실측)

| strategy | config | n_sig | n_trades | sharpe | pnl | maxdd |
|---|---|---|---|---|---|---|
| daytrading_3methods_breakout | baseline | 6126 | 503 | +0.364 | +15.60% | 34.07% |
| daytrading_3methods_breakout | floor300 | 6073 | 502 | +0.384 | +17.01% | 34.07% |
| daytrading_3methods_breakout | floor500 | 5916 | 503 | +0.419 | +19.33% | 34.07% |
| elder_ema_pullback | baseline | 31891 | 1026 | +1.964 | +235.63% | 31.26% |
| elder_ema_pullback | floor300 | 31891 | 1026 | +1.964 | +235.63% | 31.26% |
| elder_ema_pullback | floor500 | 31891 | 1026 | +1.964 | +235.63% | 31.26% |
| book_envelope_200d | baseline | 3012 | 356 | +0.702 | +33.99% | 35.08% |
| book_envelope_200d | floor300 | 2991 | 354 | +0.828 | +39.81% | 29.43% |
| book_envelope_200d | floor500 | 2963 | 354 | +0.843 | +40.48% | 28.77% |
| rs_leader | baseline | 125227 | 1286 | +1.247 | +109.24% | 25.22% |
| rs_leader | floor300 | 124317 | 1286 | +1.247 | +109.24% | 25.22% |
| rs_leader | floor500 | 122339 | 1286 | +1.247 | +109.24% | 25.22% |
| minervini_volume_dryup | baseline | 65013 | 160 | +1.797 | +47.98% | 6.94% |
| minervini_volume_dryup | floor300 | 65013 | 160 | +1.797 | +47.98% | 6.94% |
| minervini_volume_dryup | floor500 | 65013 | 160 | +1.797 | +47.98% | 6.94% |
| book_pullback_ma5 | baseline | 50338 | 992 | +0.506 | +24.03% | 23.42% |
| book_pullback_ma5 | floor300 | 50000 | 992 | +0.506 | +24.03% | 23.42% |
| book_pullback_ma5 | floor500 | 48872 | 992 | +0.506 | +24.03% | 23.42% |
| book_pullback_ma20 | baseline | 20772 | 666 | +0.187 | +3.82% | 36.14% |
| book_pullback_ma20 | floor300 | 20625 | 664 | +0.215 | +5.58% | 35.75% |
| book_pullback_ma20 | floor500 | 20114 | 663 | +0.150 | +1.35% | 39.64% |

### 핵심 판정 — "시총 플로어가 성과 개선" 결론은 생존하는가?

**대체로 생존하지 못한다(= 광범위 개선 주장은 데이터 오염 아티팩트로 판정).**
깨끗한 2024–26 + 수정 코드에서 floor300/500 의 한계효과는 전략별로 갈린다:

- **null (효과 없음) — 4/7 전략**: `elder`·`minervini`·`rs_leader`·`ma5` 는 floor300/500 이
  baseline 과 **수치 완전 동일**(sharpe/pnl/maxdd). 이유:
  - elder(min 5천억)·minervini(min 3천억) 는 자체 하한이 floor(300/500억)보다 훨씬 높아
    floor 가 **완전 포섭**(잉여).
  - rs_leader·ma5 는 floor 가 신호 일부를 줄이나(예: rs 125227→122339) **거래(top-K 체결)는
    불변** → floor 가 거른 극소형주는 애초에 포지션으로 체결되지 않았음.
- **robust YES — 1/7 전략**: `book_envelope_200d` 만 sharpe↑ **AND** maxdd↓ 가 단조
  (floor500: sharpe +0.70→+0.84, maxdd 35.1%→28.8%). 시총컷이 없는 전략이라 floor 가
  유일한 사이즈 게이트로 실효. **가설A(갭 손절관통 감소)가 성립하는 유일 케이스**.
- **약한/모호 — daytrading**: sharpe·pnl 은 단조 개선(+0.36→+0.42, +15.6%→+19.3%)이나
  **maxdd 는 34.07% 로 완전 불변** → 가설A 의 기제(드로다운 감소)는 깨끗창에서 미성립.
  꼬리(체결 안 되는 극소형) 정리로 평균은 소폭 좋아지나 손절관통 보호 효과는 없음.
- **noisy/비단조 — ma20**: floor300 은 소폭 개선(sharpe +0.187→+0.215, maxdd 소폭↓)이나
  floor500 은 **악화**(sharpe +0.150, maxdd 36.1%→39.6%). 표본잡음 수준.

**결론**: 오염된 5.5년에서 "시총 플로어가 폭넓게 성과 개선"으로 읽힌 것은 상당 부분
**fail-open baseline 의 오염 아티팩트**다(오염 baseline 이 체결도 안 되는 결측-극소형으로
부풀려져, 별도 floor 를 덧대면 무엇이든 좋아 보였음). 수정 후 baseline 이 이미 각 전략
컨셉으로 올바로 bind 되자, 추가 floor 는 **시총컷이 없는 envelope 에서만 robust** 하고
나머지는 잉여/무효/잡음이다. 운영 함의: **일괄 시총 플로어 도입은 근거 약함.** envelope 에
한해 사이즈 게이트(예: 300–500억 하한) 추가를 별도 검토할 가치가 있다.

### 한계 (반드시 함께 해석)
- **표본 길이**: 2024–26 은 ~2.5년(월별 PIT 31 scan_date)으로 5.5년 대비 짧다. 단일
  강세국면 비중이 커 sharpe 절대수준(elder +1.96 등)은 낙관 편향 가능 — 본 측정의 목적은
  *절대 성과가 아니라 floor 한계효과의 방향/생존성* 판별이다.
- **floor 적용 지점**: step3c 는 base_filter 통과집합 위에 PIT snapshot market_cap 플로어를
  곱한다(PIT-clean). 시총컷 보유 전략은 my-fix 로 baseline 이 이미 좁아졌고, 2024–26 은
  결측이 드물어(91.8% 채움) fix 자체의 baseline 변화도 작다.
- **ex_sector(가설B) 미실행**: 섹터 제외는 스크립트 자체가 *현재 섹터 소급 = look-ahead/
  생존편향*(PIT-clean 아님)으로 명시. 오염된 결론을 표에 섞지 않기 위해 본 패스에서는
  PIT-clean 인 floor 구성만 측정. 필요 시 `--configs ex_sector` 로 별도 방향성 참고만 가능.

---

## 변경 파일 요약 (커밋 안 함 — 워킹트리 diff)

수정:
- `strategies/_rule_screener_base.py` — `_passes_market_cap` 헬퍼 추가(중앙화).
- `strategies/{elder_ema_pullback,minervini_volume_dryup,daytrading_3methods_breakout,
  book_pullback_ma5,book_pullback_ma20}/screener.py` — base_filter 가 헬퍼 사용, fallback 제거.
- `backtest/screener_universe.py` — `_snapshot_to_universe` 의 `market_cap` fallback(0) 제거.
- `scripts/step3c_size_sector_filter.py` — 데이터완전성 가드 배선 + 플래그.
- 테스트 6파일 갱신(버그-동작 단언 → fail-closed + 경계 라이브동등성).

신규:
- `backtest/data_completeness.py` — 채움률 가드.
- `tests/test_data_completeness.py` — 가드 테스트(6).

산출물(워킹트리, 비커밋): `scratchpad/step3c_core_2024clean.md`(자동리포트),
`scratchpad/step3c_core.log`(원시 로그).
