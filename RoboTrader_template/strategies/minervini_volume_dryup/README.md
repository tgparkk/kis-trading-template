# minervini_volume_dryup — Minervini VCP (Variant B)

> 활성 페이퍼 전략. 운영 허브 → [docs/PAPER_STRATEGIES.md](../../docs/PAPER_STRATEGIES.md) · 추가 가이드 → [docs/STRATEGY_GUIDE.md](../../docs/STRATEGY_GUIDE.md)
> 임계값의 SSOT는 `config.yaml` + 진입/청산 룰 코드입니다. 이 문서는 *해설*이며, 숫자가 어긋나면 코드가 정본.

## 한 줄
변동성 수축(거래량 dry-up) 후 매집 구간을 포착. Minervini의 알파 원천이 VCP가 아닌 dryup임이 확인됨.

## 출처 / 분류
Minervini VCP (Variant B) — 추세/매집.

## 진입 (`rule_volume_dryup`)
최근10봉 평균거래량 ≤ 직전30봉 평균의 **70%** (거래량 dry-up). confidence = 58.

## 청산
sl **-8%** / tp **+12%** / max_hold **20거래일**. **trail 없음, trend_flip 없음** (Variant A와 차이).

## 유니버스 / regime / 사이징
- 유니버스: 시총 ≥ 3천억 · 거래대금 ≥ 30억
- regime: index **KOSPI** / gate **none** (게이트 역효과)
- K = **3** / 종목당 **333만**

## 평판 (백테스트 / OOS)

🔴 **이 숫자는 검증 러너 유니버스(`top_volume:50`)에서 나왔다 — 라이브 유니버스와 다르다.**
라이브 매수의 97%가 그 밖이다(실측). 라이브 기대치로 인용하지 말 것 → [PAPER_STRATEGIES §0.7](../../docs/PAPER_STRATEGIES.md#07--백테스트-평판-숫자와-라이브는-다른-모집단이다-2026-08-15-감사)
정본상 평범 (KOSPI 하회 -7%). K 풀스윕서 **K3만 생존** (K10/20 MaxDD ≈ 100%).

## 코드
- 전략: `strategy.py` · 설정: `config.yaml` · EOD 스크리너: `screener.py`
- 진입 룰(SSOT): `strategies/books/minervini_vcp/rules.py::rule_volume_dryup`

---

## 🎯 Trend Template(TT) 배선 — 2026-08-18, 현재 `shadow`

`backtest/concept_axes/minervini/`(사전등록 판정 `b6d3d89`) 결과:

| Arm | 진입 룰 | 거래당 평균 | 무작위 20회 최대(+1.03%) 대비 |
|---|---|---|---|
| `D` | dryup 만 — **2026-08-18까지의 라이브** | **+0.00%** | ❌ **못 넘음** (p=1.0000) |
| `DT` | dryup ∧ TT | **+1.54%** | ✅ 넘음 (p=0.0476) |
| `T` | TT 만 (dryup 제거) | **+2.38%** | ✅ 넘음 (p=0.0476) |

🔴 ***현행 `D` 는 「그날 적격 집합에서 무작위로 10종목 고르기」와 구별되지 않는다.*** 이 전략
이름에 든 `volume_dryup` 이 곧 **빼는 것이 나은 축**으로 나왔다(`T` > `DT` > `D`).

**사장님 승인(2026-08-18)은 「1단계 = TT 더하기」까지다.** `T`(dryup 제거)는 매매 빈도가
크게 바뀌므로 빈도 실측 후 별도 결정한다.

### 모드 — `screener.py::TT_FILTER_MODE`
| 모드 | 동작 |
|---|---|
| `off` | TT 미평가 (2026-08-18 이전 동작) |
| **`shadow`** (현재) | TT 를 평가해 **기록만** — 후보 선정은 `off` 와 **100% 동일**. `reason` 에 `tt=0/1` 이 찍힌다 |
| `on` | TT 통과 종목만 후보 (= 백테스트 `DT`) |

### 🔴 왜 바로 `on` 이 아닌가
`rule_trend_template` 은 **220봉**과 **`ctx['rs_value']`** 가 둘 다 있어야 한다. 하나라도 없으면
**로그 없이 `False`** 를 반환한다(`rules.py:52`, `:66`). 즉 배관이 틀리면 **후보 0건**이 되는데
아무 경보도 안 뜬다. 그래서 shadow 로 며칠 돌려 배관을 확인한 «뒤에» 올린다.
그 사각지대를 메우려고 `finalize_scan()` 이 스캔마다 `220봉충족 / rs_value 확보 / dryup / TT통과`
를 인쇄하고, 0 이면 **ERROR** 를 낸다.

### TT 승격 체크리스트 (`shadow` → `on`)
전부 충족해야 올린다. 하나라도 미달이면 **원인 규명이 먼저다.**

- [ ] **① 배관** — EOD 로그 `TT게이트` 줄에서 `rs_value 확보` 와 `220봉충족` 이 **연속 5거래일** 0 이 아니다.
- [ ] **② 발화** — 같은 5거래일 누적 `TT통과 / dryup` 이 **5~40%** 구간(백테스트 실측 **16.1%**, 라이브 재현 **16.4%**).
      0% 면 배관 결함, 90%↑ 면 룰이 안 걸린 것이다.
- [ ] **③ 빈도 영향** — `screener_snapshots` 의 `reason` 에서 `tt=1` 비율로 **후보가 몇 건으로 줄어드는지** 산출.
      최종후보가 **평균 3건 미만**이면 K=3 대비 과소 — 올리기 전에 사장님 판단을 받는다.
- [ ] **④ 회귀** — `pytest RoboTrader_template/tests/test_screener_minervini.py` 전건 통과.
- [ ] **⑤ 승인** — 라이브 매매가 바뀌므로 **사장님 승인**. 코드상 한 줄(`TT_FILTER_MODE = "on"`).

🔑 **외부 후보 유입 차단은 이미 돼 있다**(2026-08-18) — `accepts_volume_fallback = False`.
`evaluate_entry()` 는 dryup 만 재검사하고 **TT 는 재검사하지 않으므로**, 스크리너를 거치지 않고
워치리스트에 들어온 종목은 TT 를 한 번도 통과하지 않은 채 매수될 수 있었다. 그러면 그 종목만
`D`(무작위를 못 넘은 arm)로 매매된다. → `tests/test_candidate_foreign_pool_gate.py`

⚠️ **병기 의무**(사전등록 §10-5 항목 12): arm 간 폐기율이 **4.08배** 벌어져 있어 이 비교는
「같은 룰의 두 버전」이 아니라 **「매매 빈도가 다른 두 룰」**에 가깝다. `on` 승격은 성과뿐 아니라
**거래 횟수 자체를 바꾸는 변경**이다.

### 배선 충실도 재확인
`backtest/concept_axes/minervini/verify_live_wiring.py` — 라이브 스크리너 경로로 `DT/D` 비율을
백테스트 창 안 날짜들에 대해 재산출한다. 2026-08-18 실측 **라이브 16.4% vs 백테스트 16.1% (1.02배)**.
