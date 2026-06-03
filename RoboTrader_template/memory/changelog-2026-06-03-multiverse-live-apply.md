# 멀티버스 증거 → 가상매매 라이브 설정 반영 (2026-06-03)

> 사장님 결정: 게이트=증거기반, 튜닝값=Minervini 5→3·유지윤 hw15 둘 다. 워킹트리 변경까지(커밋은 승인 대기). 상세 검증 `reports/books_research/_REtest_bear_multiwindow.md`.

## 적용 내역
### A. 국면 게이트 교정 (신규 변경, 미커밋) — `config/trading_config.json`
- elder_ema_pullback: regime_gate `exclude_bear` → **`none`** (라인 38)
- minervini_volume_dryup: regime_gate `exclude_bear` → **`none`** (라인 45)
- ma20·ma5 = exclude_bear 유지, 유지윤 = none 유지.
- **근거(②일자별 PIT 재측정)**: minervini exclude_bear 역효과(Sharpe0.44→0.30·PnL+0.71→−0.28·MaxDD41→75%), elder 무수혜(소폭 악화). 게이트 진짜 수혜=ma20·ma5 눌림목뿐 → 게이트는 수혜 전략만 ON.

### B·C. 튜닝값 — ★이미 적용돼 있었음 (메모리 stale 정정)
- **Minervini max_positions=3**: `strategies/minervini_volume_dryup/config.yaml:34`에 이미 `max_positions: 3`(커밋 821fb80). strategy.py:83의 5는 폴백 디폴트(미사용). → 메모리 곳곳의 "max_positions 5→3 승인 대기"는 **이미 반영됨으로 정정**.
- **유지윤 high_window=15**: `strategies/daytrading_3methods_breakout/config.yaml:32`에 이미 `high_window: 15`(커밋 32b42ee). 백테스트 rule(rules.py:274) 디폴트 20은 그대로(무관). → "hw15 결정 대기"도 **이미 반영됨으로 정정**.

## 검증 (StrategyLoader 실인스턴스 readback, main.py 동일 경로)
| 전략 | regime_index | regime_gate | max_positions | high_window |
|---|---|---|---|---|
| elder | KOSPI | none | 5 | — |
| minervini | KOSPI | none | **3** | — |
| ma20 | KOSPI | exclude_bear | 5 | — |
| ma5 | KOSPI | exclude_bear | 5 | — |
| 유지윤 | KOSDAQ | none | 5 | **15** |
- JSON 유효성 OK. 변경 관련 pytest **154 passed**. 사전존재 무관 실패(test_adjacent_grid import·minervini VCP 룰개수 드리프트·exit_multiverse DB픽스처)는 stash 재현으로 본 변경과 무관 확인.

## 잔여
- **★봇 재시작 시 반영** — trading_config.json strategies는 시작 시 1회 로드. 현재 가동봇은 재시작해야 elder/minervini gate=none 적용.
- **git 커밋 승인 대기** — trading_config.json 변경 1건(미커밋).
- 동작 보장: 게이트 배선은 완전(config.py:449-452 주입 → trading_context 매수전 check_regime_gate → regime_gate.py classify_daily PIT). 라이브 게이트는 이미 일자별 분류(통짜 라벨 문제는 백테스트 측정 한정).
