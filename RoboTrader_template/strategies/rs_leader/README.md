# rs_leader — 횡보장 RS 리더 (derived 전략, 페이퍼 관찰 전용)

> 활성 페이퍼 전략. 운영 허브 → [docs/PAPER_STRATEGIES.md](../../docs/PAPER_STRATEGIES.md) · 추가 가이드 → [docs/STRATEGY_GUIDE.md](../../docs/STRATEGY_GUIDE.md)
> 임계값의 SSOT는 `config.yaml` + 진입/청산 룰 코드입니다. 이 문서는 *해설*이며, 숫자가 어긋나면 코드가 정본.

## 한 줄
시장이 안 좋을 때 상대적으로 강한(횡단면 RS 상위) 절대상승 종목을 매수. 횡보장에서 강건.

## 출처 / 분류
derived 전략 (Book20 아님) — 상대강도(RS) / 추세.

## 진입 (`RSLeaderRule`)
절대상승추세(`RSLeaderRule(ma_short=20, ma_long=60, abs_lb=60)`: 종가 > MA20 · 종가 > MA60 · MA20 > MA60 ·
60일수익 > 0)를 per-stock 재확인 후 매수. **횡단면 RS 랭킹은 EOD 스크리너가 담당** (절대상승추세 통과 종목의
120일 수익률을 score로 → 정렬 + topK = RS 랭킹).
> 🔧 2026-08-22: 진입에 `종가 > MA20` 추가. 청산 ma_break(무조건 `종가 < MA20`)와 진입 조건이 겹쳐(진입은
> `종가 > MA60`만 요구) 매수 직후 매도되는 결함을 수정 — 상세 → `rule.py` docstring.

## 청산
- 전략 고유 청산: 종가 < MA20 하향이탈 (**무조건**) / max_hold **30거래일**.
- sl **-8%** / tp **+15%** 는 전략이 판정하지 «않는다» — 범용 `core/trading/position_monitor.py` 가
  `config.yaml` `risk_management`(`stop_loss_pct` / `take_profit_pct`) 값을 **라이브 현재가**로 판정한다
  (2026-08-25 `1810cd2`, D-1 종가 익절 환영 결함 → `docs/prereg_2026-08-25_d1close_tp_phantom.md`).

## 매수 배제 가드 — 미조정 기업행위(합병) 의심 (2026-09-10, 기본 `shadow`)

RS 점수의 **입력값이 오염된 종목**을 랭킹에 넣지 않는다. 알파 주장이 아니라 **데이터 위생 가드**다
(`utils/data_sanity.py` 불가능봉 가드와 같은 계열 — 그쪽은 «하락» 절벽, 이쪽은 정지런 뒤의 «상승» 불연속).

- **판정**: 큐 파일(`logs/corp_action_refetch_queue.jsonl`)을 읽지 «않는다». 큐를 생산하는 로직
  `collectors.corp_action_watch.scan_series` 를 **스크리너가 이미 로드한 130봉 프레임에 그대로** 적용한다
  (추가 DB 접근 0 · 새 문턱 상수 0개 · 데이터가 고쳐지면 **자동 해제**).
- **배선**: ① `screener.py::match()` 룰 평가 앞 — 정렬·topK «앞»이라 후보 수가 줄지 않는다(백필)
  ② `strategy.py::_check_buy()` 맨 앞 — 스크리너를 안 거친 종목이 on_tick 으로 들어오는 구멍을 막는다.
- **청산은 불변**: 배제는 매수만 막는다. `_check_sell` · `evaluate_sell_conditions` ·
  `core/trading/position_monitor.py` · 백테스트가 부르는 `evaluate_entry` 는 한 줄도 안 바뀐다.
- **스위치**: `config.constants.RS_LEADER_CORP_ACTION_MODE` = `off` / `shadow`(기본) / `live`
  (env `RS_LEADER_CORP_ACTION_MODE`). 🔴 롤백은 `off` «하나»뿐이고, 이미 체결된 매매를 되돌리지 않는다.
- 🔴 **한계**: on_tick 프레임은 **82봉**이라 그 창 밖 사건은 원리적으로 못 잡는다(실측 003350 유형).
  「on_tick 도 막았다」를 「전부 막았다」로 읽지 말 것 — 스크리너(130봉)가 1차, on_tick 이 2차다.
- 설계 → [`docs/superpowers/specs/2026-09-10-rsleader-corp-action-exclusion-design.md`](../../docs/superpowers/specs/2026-09-10-rsleader-corp-action-exclusion-design.md)

## 유니버스 / regime / 사이징
- 유니버스: 거래대금 ≥ 10억 · 시총 컷 없음 (절대상승추세 통과 → 120일수익률 RS topK)
- regime: index **KOSPI** / gate **exclude_bear** (깊은약세 미입증이라 약세장 매수 차단)
- K = **10** / 종목당 **100만**

## 평판 (백테스트 / OOS)

🔴 **이 숫자는 검증 러너 유니버스(`top_volume:50`)에서 나왔다 — 라이브 유니버스와 다르다.**
라이브 매수의 97%가 그 밖이다(실측). 라이브 기대치로 인용하지 말 것 → [PAPER_STRATEGIES §0.7](../../docs/PAPER_STRATEGIES.md#07--백테스트-평판-숫자와-라이브는-다른-모집단이다-2026-08-15-감사)
검증 조건부 (횡보장 5/5 config 강건 +5~8% · OOS 양수 ✅ / 깊은약세 부호반전 · per-trade Sharpe 0.08~0.19 ❌).
현 백테스트는 강세장 순풍 왜곡 (2026-04/05 +8.5/+6.8%는 KOSPI +30/+28% 덕). 페이퍼 관찰 전용.

## 코드
- 전략: `strategy.py` · 설정: `config.yaml` · EOD 스크리너: `screener.py`
- 매수 배제 가드: `corp_action_guard.py` (판정 로직은 `collectors/corp_action_watch.py` 재사용)
- 진입 룰(SSOT): `strategies/rs_leader/rule.py::RSLeaderRule` (2026-07-02 `scripts/rs_leader/` 에서 승격 — 라이브 엣지 -2)
