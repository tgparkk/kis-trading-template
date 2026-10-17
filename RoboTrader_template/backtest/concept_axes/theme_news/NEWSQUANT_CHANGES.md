# TN1 — NewsQuant 가 알려 온 변경 날짜 기록 (부록 A)

> 동결 사전등록 `RoboTrader_template/docs/prereg_2026-10-09_theme_news_rank.md`(동결 `f5059af`) 부록 A 「바뀌면 알려 주실 것(날짜 «삽입»)」 으로 받은 알림을 **받은 순서대로** 적는다. 개봉(§14-7) 때 §9 인쇄 «NewsQuant 가 알려 온 추출기·종목사전·수집 규칙 변경 날짜(부록 A)» 와 §11 한계 표가 이 파일을 읽는다.
> 규칙: 행은 덧붙이기만(고치지 않음 · 정정은 새 행) · 동결 문서는 바꾸지 않는다 · 가상매매 세션이 DB SELECT 로 확인한 값만 «확인» 칸에 적는다.

| # | 받은 때 | NewsQuant 커밋 | 무엇이 바뀌었나 | 라이브 반영 | 금지 ①~⑤ 해당 | TN1 영향 | 가상매매 세션 확인(DB SELECT) |
|---|---|---|---|---|---|---|---|
| 1 | 2026-10-17 11:5x(NEXT_SESSION «삽입» ①) | `475a732`(10-12 12:03 main 머지) | 해외 RSS 중 CNBC·MarketWatch 기사 **본문**을 `news.content` 에 저장(사이클당 상한 20 · 재시도 없음 · 프로세스 첫 사이클 예열 = 요청 0) · `base_crawler` 문자셋 판별 수정(데이터 URI 의 잘못된 charset 건너뜀). Investing.com·Google News 는 대상 아님 | **2026-10-13(화) 07:40** 자동 재시작부터(10-12 프로세스는 구 코드) | 없음(과거 행 소급 0 · 삭제 0 · UPSERT 규칙 불변 · `theme_*` 불변 · `published_at`·`created_at`·`source` 불변) | **0** — TN1 소스는 언론 3개 고정(`naver_finance`·`hankyung`·`mk_news` · §2-4)이고 해외 소스는 종목 연결 0. 영향은 NewsQuant 영어 감성·중요도·한국 영향도(해외 뉴스 한정 · 10-13~ 입력 변화) | ✅ 평균 `length(content)`(created_at 날짜별): CNBC 120·136·138(10-08·09·12) → 1,255·902·1,947·1,261(10-13~16) · MarketWatch 133·105·113 → 331·330·450·279 — 알림과 일치. 하루 200자 이상 행 CNBC 13~28 · MW 3~9(문턱 200자 기준이라 알림의 13~26·2~7 과 조금 다름). 해외 7소스(cnbc·marketwatch·investing_com·google_news_*) 10-01~ `related_stocks` 비어 있지 않은 행 0 · CNBC·MW 의 `news_stock` 행 0 |
| 2 | 2026-10-17 12:4x(NEXT_SESSION «삽입» ⑥) | `b8f085d`(main 머지·push) | **크롤러 소스 추가** — 네이버 증권사 리서치 리포트 → 새 표 `research_reports`(kis_template · robotrader SELECT)에만 씀. 과거 2년 백필 19,131행(2024-10-17~2026-10-16 · `backfilled=TRUE`) | **2026-10-19(월) 07:40** 자동 시작부터(기동 2분 뒤 첫 실행 · 30분 간격) | 없음(`news`·`news_stock`·`related_stocks`·`theme_*` 영향 0) | **0** — `news` 표 밖. 표본 중 새 소스는 넣지 않는다(§2-4) · 개수 인쇄 대상도 아님(`news.source` 가 아님) | ✅ `research_reports` 19,131행 전부 `backfilled=TRUE` · `first_seen_at` 2026-10-17 12:30~12:37(백필 시각 → 시점 분석엔 `backfilled=FALSE` 만) |

## 관련 메모(TN1 판정과 무관 · 참고)

- 2026-10-17 NewsQuant 알림 ③: 공유 DB `daily_prices` 가 매일 09:00 적재 때 과거 빈칸을 채운다(10-12 `143540` 55행 · 10-15 `006405` 18행 · 10-16 `010955` 17행 · 10-16 15:45 전 행 `updated_at` 일괄 갱신). TN1 은 Y(시가→종가)와 S_price(D·D−1 종가)에 `daily_prices` 를 쓰므로, 개봉 때 동결 입력 재현이 필요하면 `theme_rank/run.py` 의 `DB_ASOF`(`93ff99f`) 처럼 `created_at` 컷을 검토할 것 — 동결 문서에 없는 규칙이라 **도입하려면 사장님 확인**.
