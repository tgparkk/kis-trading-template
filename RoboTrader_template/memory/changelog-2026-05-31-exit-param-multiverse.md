# 선별 4전략 청산 파라미터 멀티버스 워크포워드 최적화 — 구축 + 실행

> 작성: 2026-05-31 · 설계서 `docs/superpowers/specs/2026-05-31-exit-param-multiverse-design.md` · 계획서 `docs/superpowers/plans/2026-05-31-exit-param-multiverse.md`
> 커밋: 설계 6c2589d · 계획 9099134 · 구현 db596bb~9b64777 (전부 main)

## 한 줄 결론

**선별 4전략(elder/minervini/ma20/ma5)의 청산 파라미터를 실전과 동일한 포트폴리오 잣대 + 워크포워드 OOS + 국면최악 Sharpe→DSR 게이트로 그리드 탐색한 결과 — 4전략 전부 "기존값 유지"**. 어떤 청산 조합도 OOS에서 현재 운용값을 유의하게 이기지 못함 = **기존 운용 청산값이 이미 합리적**. 실파라미터 교체 없음(권고안만).

## 무엇을 만들었나 — `scripts/exit_multiverse/` 신규 패키지

기존 책 백테스트 러너(`scripts/run_*.py`)의 진입(`generate_signal_with_extra_ctx`)·청산 로직을 **재사용**하되, 실전과 같은 **포트폴리오 자본 모델**(전략당 1천만 공유·max5·종목당300만)을 신규 시뮬레이터로 구현. 진입 신호는 청산과 무관하므로 그리드 밖에서 1회 사전계산(RAM 활용).

| 모듈 | 역할 |
|---|---|
| `data_loader.py` | 유니버스(top_volume:50)·일봉adj·KOSPI종가·turnover 로드 |
| `exits.py` | 청산 판정 순수함수 2종(elder=trail_ema+trend_flip / 단순MA) — 레거시 1:1 이식 |
| `signals.py` | 진입 신호 사전계산 캐시(그리드 무관) |
| `adapters.py` | 4전략 어댑터(진입메커니즘·청산종류·그리드·ctx). 그리드 중앙=현재 운용값 |
| `portfolio_sim.py` | 포트폴리오 시뮬레이터(자금·슬롯·매수스톱·per-stock 모드) |
| `objective.py` | 국면별 Sharpe→국면최악→DSR |
| `walkforward.py` | 롤링 폴드(train24/test6/step6=7폴드)·평가(train 그리드→OOS) |
| `run.py` / `run_all.py` | 단일/4전략 병렬 CLI + 종합 summary |
| `report.py` | 폴드 테이블·파라미터 안정성·md 리포트 |

구현: 12 task, 전부 TDD + 서브에이전트 2단계/통합 리뷰. 최종 회귀 **31 passed**(slow 동등성 포함).

## 중요 버그 2건 — 검증 게이트가 잡음

1. **동등성 게이트(Task6)가 실거래 버그 적발**: `portfolio_sim` unconstrained 모드에서 `entered_codes`가 첫 청산 후 재진입을 영구 차단(신규 1 sell vs 레거시 4). `entered_codes.discard(code)`로 수정 → new=legacy=4 정확 일치. **`--mode per-stock` 동등성 회귀가 없었으면 못 잡았을 버그.**
2. **elder 병렬 IndexError 근본수정**: `run_all`의 ProcessPoolExecutor에서 elder만 간헐 `IndexError`(단일/순차는 안정). 근본원인 = `load_top_volume_universe`의 `ORDER BY turnover DESC LIMIT 50`에 **tiebreak 부재** → 동률 시 50번째 종목이 worker마다 달라짐 → 짧은 이력 종목이 일부 worker에만 진입 → stop 브랜치 `df.iloc[trigger_high_idx]` OOB. 수정: ①결정적 tiebreak(`, stock_code ASC`) ②`_prior_high_at` OOB 가드(in-bounds는 byte-identical → elder 결과 불변) ③`run_all._worker` traceback 노출(기존엔 `{e!r}`만 남겨 디버깅 불가했음).

## 결과 (워크포워드 OOS, top50, 2021-01~2026-05, 7폴드)

| 전략 | OOS 국면최악 Sharpe(평균) | OOS 평균수익 | max DSR | 판정 |
|---|---|---|---|---|
| elder_ema_pullback | −4.16 | **+1.4%** | ≈0 | 기존값 유지 |
| minervini_volume_dryup | −2.77 | **+4.9%** | ≈0 | 기존값 유지 |
| book_pullback_ma20 | −4.17 | **+11.6%** | ≈0 | 기존값 유지 |
| book_pullback_ma5 | −5.04 | −12.1% | ≈0 | 기존값 유지 |

산출물: `reports/exit_optimization/{전략}_walkforward.md`(폴드별 train베스트/OOS/파라미터 안정성), `{전략}_grid.parquet`, `summary.md`.

## 해석 — 정직한 단서 2가지

- **방법론 가혹성**: OOS 국면최악 Sharpe가 전부 큰 음수인 건 측정 탓이 큼. OOS는 6개월 단일 구간이라 국면별 표본이 적어(`min_obs=1`) Sharpe가 극단으로 튐. **절대수익(OOS 평균)은 ma20 +11.6%·minervini +4.9%·elder +1.4%로 양수** — 전략이 망가진 게 아니라 "국면최악 + 단기 OOS"라는 엄격한 잣대가 청산 미세조정의 우위를 못 드러낸 것.
- **Task10 단일 진단(ma5)**: 포트폴리오 모드에서 BULL Sharpe +1.16(레거시 0.63과 정합)이나 BEAR −1.41/SIDEWAYS −2.02 → 약세장에서 자본 잠식. 책 헤드라인(per-stock 평균·전기간)과 포트폴리오·국면최악 잣대의 간극이 그대로 드러남.

## 결론 / 잔여

- **채택**: 없음. 4전략 모두 기존값 유지(default to no-change). `trading_config.json`/`config.yaml` **미변경**.
- **시사점**: 현재 운용 청산값이 이미 합리적. "청산 미세조정으로 알파를 더한다"는 가설은 이 엄격한 잣대에서 기각.
- **차기 검토 여지**: ①목적함수 재설계(OOS 국면최악 대신 전체기간 Sharpe·절대수익·Calmar 병행 — 단기 OOS 국면 표본부족 완화) ②유니버스 적합성(급등주 눌림 전략 ma5/ma20에 top_volume 대형주풀이 맞는지 — 책도 top_volume:50을 썼으나 포트폴리오 모드에선 재고 여지) ③진입 임계값까지 확장(이번엔 청산만).
