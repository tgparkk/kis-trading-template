# docs/ 색인 — 무엇이 어디에 있나 (2026-09-17)

> 이 폴더의 정본 개발 문서·전략 허브·날짜 문서의 **위치와 이름 규약**. 라우터는 [../CLAUDE.md](../CLAUDE.md). 문서와 코드가 어긋나면 코드가 맞다.
> 재배치 근거·이동 금지 목록 원문 = [audit_2026-09-17_dev_docs_cleanup_plan.md](audit_2026-09-17_dev_docs_cleanup_plan.md) §4.

## 1. 정본 개발 문서 (코드를 설명한다 · 코드가 바뀌면 같이 고친다)

| 문서 | 한 줄 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 레이어 그림(**정본**)·기동 시 조립 관계·패키지 역할·의존성 |
| [TRADING_FLOW.md](TRADING_FLOW.md) | 런타임 흐름 — 기동 → 3초 루프 → 하루 타임라인 → 매수 경로 → 매도 체인 → Task Supervisor |
| [code/MODULES.md](code/MODULES.md) | 모듈별 표(main.py·framework·strategies·api·core·bot·config·db·utils·collectors·signals·tools·runners) + 테스트 구조·실행 규칙 |
| [CODE_MAP.md](CODE_MAP.md) | 운영 vs 연구 디렉토리 경계 · 라이브→연구 엣지(현재 1건) · 드리프트 검증 명령 · 인벤토리 재생성법 |
| [INVENTORY.md](INVENTORY.md) | 연구 파일 참조 태깅(`tools/gen_inventory.py` 출력 · LIVE-DEP/TEST-ONLY/RESEARCH/UNREFERENCED) |
| [CONFIGURATION.md](CONFIGURATION.md) | `config/key.ini`(KIS 키·텔레그램) · `trading_config.json` · `constants.py` · `market_hours.py` · 전략 `config.yaml` |
| [DATABASE.md](DATABASE.md) | 접속(풀 둘) · 환경변수 전수·폐지 env · 서버 DB 목록(은퇴 DB 포함) · 표 인벤토리 · 핵심 표 컬럼 · DDL 위치 |
| [DATA_MANAGEMENT.md](DATA_MANAGEMENT.md) | 하루 시간표 기준 「언제 무엇이 DB 에 들어오고 재기동 때 무엇을 읽나」 |
| [OWNERSHIP_MODEL.md](OWNERSHIP_MODEL.md) | 다전략 소유권 — 폴더키/클래스명 2종 신원 · 실주문 소유권 게이트 · 미청산 수량 판정 |
| [STRATEGY_GUIDE.md](STRATEGY_GUIDE.md) | 새 전략 추가 Step(폴더·config.yaml·strategy.py·screener+어댑터 등록·`strategies[]` 등록) · BaseStrategy 인터페이스 · 테스트 |

## 2. 전략 허브 · 상시 설명 문서

| 문서 | 한 줄 |
|---|---|
| [PAPER_STRATEGIES.md](PAPER_STRATEGIES.md) | 활성 8전략 운영 허브 — SSOT `config/trading_config.json strategies[]` 의 해설 · 한눈표 · 집중 3전략/관측 5전략 · 예정 변경(K 상향·live 발효) |
| `../strategies/<name>/README.md` | 전략별 상세(의도·진입/청산 룰·평판) — 허브에서 링크 |
| [RS리더_쉬운설명.md](RS리더_쉬운설명.md) | `rs_leader` 해설(정본은 `config.yaml` + 룰 코드) |
| [전략진단_쉬운설명.md](전략진단_쉬운설명.md) | 「8전략은 왜 마이너스인가」 쉬운 설명(엄밀본 `backtest/*/RESULTS.md`) — 🔒 이동 금지(§5) |
| [DB통합_쉬운설명.md](DB통합_쉬운설명.md) | 2026-08 `kis_template` 단일화 경위 + 현재 상태 박스 |
| [TODO_2026-08-27.md](TODO_2026-08-27.md) | 통합 TODO(2026-08-27 기준) — 🔒 이동 금지(§5) |
| [N1_수리_로드맵_쉬운설명_2026-09-03.md](N1_수리_로드맵_쉬운설명_2026-09-03.md) | N-1(병합·감자 미조정) 수리 로드맵 한 장 — 🔒 이동 금지(§5) |
| [2026-07_전략고유청산_공백_재해석.md](2026-07_전략고유청산_공백_재해석.md) | 2026-07 전략 고유 청산 공백 기간의 성적 재해석 주의보 — 🔒 이동 금지(§5) |

## 3. 하위 폴더 — 무엇을 어디에 넣나

| 폴더 | 들어가는 것 | 지금 있는 것 |
|---|---|---|
| `code/` | 코드 모듈 표 | [code/MODULES.md](code/MODULES.md) |
| `reports/2026-09/` | 장마감 보고(`report_YYYY-MM-DD_장마감.md`)·기간 성과·전략 요약 — **동결 문서가 인용하지 않는 것만** | [09-07](reports/2026-09/report_2026-09-07_장마감.md) · [09-08](reports/2026-09/report_2026-09-08_장마감.md) · [09-10](reports/2026-09/report_2026-09-10_장마감.md) · [09-11](reports/2026-09/report_2026-09-11_장마감.md) · [09-14](reports/2026-09/report_2026-09-14_장마감.md) · [09-16](reports/2026-09/report_2026-09-16_장마감.md) · [09-11 전략별 8·9월 성과](reports/2026-09/report_2026-09-11_전략별_8월9월_성과.md) · [전략요약 3전략+태쏘 09-16](reports/2026-09/전략요약_3전략_태쏘_2026-09-16.md) |
| `panels/2026-09/` | 전문가 패널·자문 쉬운설명(`<주제>_쉬운설명_YYYY-MM-DD.md`) — 동결 문서가 인용하지 않는 것만 | [뉴스분류 개선 09-16](panels/2026-09/뉴스분류_개선_패널_쉬운설명_2026-09-16.md) · [산업연쇄 예측 09-16](panels/2026-09/산업연쇄_예측_패널_쉬운설명_2026-09-16.md) · [재무뉴스 전문가패널 09-14](panels/2026-09/재무뉴스_전문가패널_쉬운설명_2026-09-14.md) · [재무뉴스 패널2차 09-16](panels/2026-09/재무뉴스_패널2차_쉬운설명_2026-09-16.md) · [재무수집기 머지결정 09-06](panels/2026-09/재무수집기_머지결정_쉬운설명_2026-09-06.md) · [재무수치 적용방법 09-06](panels/2026-09/재무수치_적용방법_쉬운설명_2026-09-06.md) · [태쏘 전략분석 09-05](panels/2026-09/태쏘_전략분석_쉬운설명_2026-09-05.md) |
| `archive/` | 현재 코드를 설명하지 않는 옛 문서(DEPRECATED 배너 + 색인 한 줄 필수) · `archive/reference/` 는 외부 참고 총람 | [archive/README.md](archive/README.md) — 11본(CHANGELOG_2026-02 · SYSTEM_FLOW · DYNAMIC_RISK_MANAGEMENT · PORTFOLIO_SNAPSHOT_GUIDE · 추세기반_적응형_청산_가이드 · quant_strategy_plan · refactoring_2A_report · ANALYSIS_REPORT · TEMPLATE_DESIGN · reference/ 2) |
| `superpowers/specs/` · `superpowers/plans/` | 설계 `YYYY-MM-DD-<topic>-design.md` · 계획서 — **경로 불변**(운영 코드·테스트가 경로를 인용, `tools/gen_archive_candidates.py` 가 출력 경로 하드코딩) | specs 40 · plans 46 |
| `audit_2026-08-23/` · `audit_2026-08-24/` | 8전략 감사 원문(SUMMARY + 전략별·데이터 변환) — 최상위 유지(동결 prereg 가 인용) | 7 + 11 파일 |

`audits/` 하위 폴더는 **아직 없다** — `audit_`·`review_` 문서는 최상위(§6). 만들 때는 동결 문서 인용을 먼저 확인한다.

## 4. 명명 규약

| 접두사 / 형식 | 뜻 | 둘 곳 |
|---|---|---|
| `prereg_YYYY-MM-DD_<topic>.md` | 사전등록 — **동결 = 커밋**. 실행 전에 가설·판정 기준을 고정한다 | 최상위 · 편집·이동 금지 |
| `report_YYYY-MM-DD_장마감.md` | 장 마감 보고(페이퍼 8전략) | `reports/YYYY-MM/` (동결 문서가 인용하는 것은 최상위) |
| `report_YYYY-MM-DD_<topic>.md` | 기타 보고(기간 성과·검증 완료 보고·태쏘 판정) | 위와 같음 · 태쏘 판정 보고는 동결 |
| `plan_` · `design_` | 계획서·개정문 · 설계(계기·로그 등) | 최상위 |
| `audit_` · `review_` · `verdict_` | 감사(읽기 전용) · 고수 검토 · 사전등록 판정문 | 최상위 |
| `<주제>_쉬운설명_YYYY-MM-DD.md` | 사장님용 쉬운 설명판(패널·자문·계획) | `panels/YYYY-MM/` (동결 문서가 인용하는 것은 최상위) |
| `<TOPIC>.md`(대문자 영문) | 정본 개발 문서(§1) | 최상위 |
| `superpowers/specs/YYYY-MM-DD-<topic>-design.md` | 설계 문서 | `superpowers/specs/` |

새 문서는 위 형식으로 만들고, 다른 문서가 인용하는 문서를 옮길 때는 `git mv` + 인용 갱신을 한 커밋에 넣는다.

## 5. 🔴 동결 문서 — 편집·이동 금지

- **`prereg_*.md` 13본 전부** — 동결(커밋 SHA 가 동결 증거). 운영 코드 주석(`config/constants.py` · `db/repositories/price.py` 등)·8전략 `strategy.py` 주석·`backtest/concept_axes/REGISTRY.md` 가 경로를 인용한다.
- **`report_2026-09-15_tasso_post7_verdicts.md`** — `backtest/tasso_program_journal/PREREG_POST8.md`(md5 동결)가 **줄 앵커**(`:318` · `:324` · `:326-339`)로 인용 → 편집은 물론 **리플로도 금지**.
- **`report_2026-09-05_tasso_post6_verdicts.md`** — 같은 폴더의 동결 문서 `PREDECISION_2026-09-15_post7.md`(§6 #4) · `PREREG_ANCHOR_REDESIGN.md`(§4 ③) · `PREREG_GRADE_TIERS.md`(§4 ②)가 **§ 앵커**로 인용 → 편집 금지.
- **`태쏘_분석_현황_2026-08-29.md`** — `backtest/tasso_program_journal/PREREG_RANKING.md` · `PREREG_WEIGHTED_RECON.md` 인용.
- 이동만 금지(내용 갱신은 가능): `TODO_2026-08-27.md`(`backtest/concept_axes/REGISTRY.md` · `prereg_2026-09-14_fund_distress_warning.md`) · `전략진단_쉬운설명.md`(`backtest/stop_path_minute/PREREG.md`) · `N1_수리_로드맵_쉬운설명_2026-09-03.md`(`prereg_2026-09-03`) · `2026-07_전략고유청산_공백_재해석.md`(`prereg_2026-08-25_d1close`) · `PAPER_STRATEGIES.md` · `STRATEGY_GUIDE.md` · `code/MODULES.md` · `superpowers/` 전체 · `backtest/` 아래 전부.
- 동결 문서 안의 깨진 링크는 **기록만** 하고 고치지 않는다(원문 = 감사 계획 §4-4).

## 6. 최상위에 남아 있는 날짜 문서와 이유 (2026-09-17)

| 문서 | 왜 아직 최상위인가 |
|---|---|
| [prereg_*.md](.) 13본 (2026-08-25 ~ 09-16) | §5 동결 |
| [report_2026-09-05_tasso_post6_verdicts.md](report_2026-09-05_tasso_post6_verdicts.md) · [report_2026-09-15_tasso_post7_verdicts.md](report_2026-09-15_tasso_post7_verdicts.md) · [태쏘_분석_현황_2026-08-29.md](태쏘_분석_현황_2026-08-29.md) | §5 동결 |
| [report_2026-09-09_장마감.md](report_2026-09-09_장마감.md) | `verdict_2026-09-10` 이 인용 — 동반 이동 대상 |
| [report_2026-09-15_장마감.md](report_2026-09-15_장마감.md) | `prereg_2026-09-15_focus3_K_raise.md`(동결) · 계획서 개정문이 줄 앵커로 인용 |
| [report_2026-09-04_8strategies_status_and_plan.md](report_2026-09-04_8strategies_status_and_plan.md) · [report_2026-09-05_8strategies_august.md](report_2026-09-05_8strategies_august.md) | 계획서·태쏘 post6 판정(동결)·전략별 성과 보고가 인용 |
| [report_2026-08-30_n1_53a_gate_and_t1_dryrun.md](report_2026-08-30_n1_53a_gate_and_t1_dryrun.md) | `prereg_2026-08-31` · `prereg_2026-09-03`(둘 다 동결) 인용 |
| [plan_2026-09-05_focus3_roadmap.md](plan_2026-09-05_focus3_roadmap.md) · [amendment_2026-09-15](plan_2026-09-05_focus3_roadmap_amendment_2026-09-15.md) | K 상향 prereg(동결)가 둘 다 인용 · 계획서는 `backtest/concept_axes/ma20/PREREG_PULLBACK_DEPTH_DURATION.md` · 3전략 쉬운설명 · 전략 README 등도 인용 |
| [design_2026-09-10_daytrading_band_reject_instrumentation.md](design_2026-09-10_daytrading_band_reject_instrumentation.md) | 인용 0 · §4 규약(`design_` = 최상위) · `plans/` 신설 시 계획서 묶음과 동반 이동(감사 계획 §4-2) |
| [verdict_2026-09-10_eprime_w1_3sessions.md](verdict_2026-09-10_eprime_w1_3sessions.md) | `prereg_2026-09-03`(동결) 인용 |
| [audit_2026-09-14_real_trading_switch.md](audit_2026-09-14_real_trading_switch.md) · [review_2026-09-14_trading_pipeline_senior.md](review_2026-09-14_trading_pipeline_senior.md) | `tests/test_live_min_fix_set_20260915.py` docstring · K 상향 prereg 인용 |
| [3전략_고도화_계획_쉬운설명_2026-09-05.md](3전략_고도화_계획_쉬운설명_2026-09-05.md) · [전문가자문_재무섹터_쉬운설명_2026-09-06.md](전문가자문_재무섹터_쉬운설명_2026-09-06.md) | 3전략 = `backtest/concept_axes/ma20/PREREG_PULLBACK_DEPTH_DURATION.md`·계획서 인용 / 전문가자문 = `backtest/concept_axes/{ma20,daytrading,minervini}/PREREG_FUNDAMENTAL_RANK.md`·`superpowers/specs/2026-09-11-minervini-fundamental-shadow-design.md` 인용 |
| [섹터데이터_쉬운설명_2026-09-06.md](섹터데이터_쉬운설명_2026-09-06.md) | `superpowers/plans/2026-09-06-sector-data.md`(경로 불변)만 이 경로를 인용 |
| [ma20_진입룰_점검_2026-08-23.md](ma20_진입룰_점검_2026-08-23.md) · [daytrade_진입밴드_조사_2026-08-23.md](daytrade_진입밴드_조사_2026-08-23.md) · [포지션사이징_결함_2026-08-23.md](포지션사이징_결함_2026-08-23.md) · [ma20_daytrade_3축_쉬운설명_2026-08-23.md](ma20_daytrade_3축_쉬운설명_2026-08-23.md) · [ma20_daytrade_자문종합_2026-08-23.md](ma20_daytrade_자문종합_2026-08-23.md) | `backtest/concept_axes/` 사전등록·`SHADOW_LOG.md` 와 08-23/24 감사 폴더가 인용 |
| [audit_2026-09-17_dev_docs_cleanup_plan.md](audit_2026-09-17_dev_docs_cleanup_plan.md) | 이번 정리의 근거 문서(§2 결함 목록 · §4 재배치안 · §5 위생) |

---

**마지막 업데이트**: 2026-09-17
