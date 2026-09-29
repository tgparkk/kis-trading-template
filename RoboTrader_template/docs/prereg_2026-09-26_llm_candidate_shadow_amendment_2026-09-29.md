# 개정문(초안) — LLM 전 종목 채점 shadow §3-4 전향 공시 적재 · 운영 결함 수정(채점 로직 무변경) · 2026-09-29

- 대상: `docs/prereg_2026-09-26_llm_candidate_shadow.md`(동결 `64f4d4a`) — **원문은 한 글자도 고치지 않는다.** 앞선 개정문 `…_amendment_2026-09-26.md`(`9bbf15c`)에 이은 두 번째 별도 문서다.
- 성격: 🔒 절의 **내용 변경이 아니다**. §3-4 「① 스크립트 `scripts/dart_disclosure_backfill.py` 를 잠금만 교체해 재사용」의 **구현 결함**(실운영에서 적재가 한 번도 돌지 못함)을 고쳐 원문 동작으로 되돌린다. §13-3 새 가족 사유(프롬프트·스키마·모델·CLI(버전·exe·플래그)·채점 조건·입력 규칙)는 어느 것도 바뀌지 않는다 ⇒ **가족 F1 유지**(사장님 확인 필요).
- 시점: **첫 채점 행 «뒤»**(F1 D=2026-09-23 · T=09-28 · 360행 ok · `code_sha 9bbf15c`). 그래서 이 문서는 「첫 실행 «전» 개정문」(§10 ⑤)이 아니라 **운영 결함 선언 + §11 V2·V6 판정 방식 개정(선언된 이탈)** 이다.

## 1. 증상 [실측 로그 `%LOCALAPPDATA%\kis-llm-shadow\logs\`]

| 실행 | 로그 줄 |
|---|---|
| 09-29 08:30 검색 팔 | `[DART] D=2026-09-28 OpenDART 오늘 0→0회 · 완결=False 적재 중단: AttributeError` → 검색 팔 보류 · `[경보] 발송 ok` |
| 09-29 16:10 본체 | `[DART] D=2026-09-28 적재 시작일=2026-09-24 · OpenDART 오늘 0→0회 · 완결=False 적재 중단: AttributeError` → `[대상] F1 D 목록 ['2026-09-23']`(호출 0 · 원장 해시 09-28 과 동일) · `[경보] 발송 ok` · 종료코드 0 |

- 09-28 실행은 적재 시작일 09-24 > D 09-23 이라 적재 경로를 타지 않았다(`load_forward` 의 `start <= D` 거짓) ⇒ **09-29 가 적재 경로의 실운영 첫 실행**이었다.
- 상태 폴더 `dart_forward\` 는 비어 있다(`progress.json`·`call_log.jsonl`·`raw\` 없음) · `dart_disclosures` 의 `max(rcept_dt)` = 2026-09-23 · 09-24 이후 0행 [실측 SELECT].

## 2. 원인 — 확정 [실경로 재현 · 스케줄러 인터프리터 `…\Shared\Python39_64\python.exe` 3.9.13]

`llm_shadow/dart_load.py::_backfill_module()` 이 `importlib.util.spec_from_file_location` + `exec_module` 로 백필 스크립트를 올리면서 **`sys.modules` 에 등록하지 않았다**. 그 스크립트는 `from __future__ import annotations`(27행) + `@dataclass`(179 `CallBudget` · 194 `Warnings`)를 쓴다 ⇒ Python 3.9 `dataclasses._is_type` 이 문자열 주석을 풀려고 `sys.modules.get(cls.__module__).__dict__` 를 읽다가 `None` 에서 터진다.

```
  File "…\llm_shadow\dart_load.py", line 32, in _backfill_module
    spec.loader.exec_module(mod)
  File "…\scripts\dart_disclosure_backfill.py", line 180, in <module>
    class CallBudget:
  File "…\Python39_64\lib\dataclasses.py", line 714, in _get_field
    and _is_type(f.type, cls, typing, typing.ClassVar,
  File "…\Python39_64\lib\dataclasses.py", line 660, in _is_type
    ns = sys.modules.get(cls.__module__).__dict__
AttributeError: 'NoneType' object has no attribute '__dict__'
```

- 테스트가 못 잡은 이유: `test_dart_load_budget` 는 `runner=` 주입만 써서 `_backfill_module()` 실경로를 한 번도 지나지 않았다.
- 로그에 예외 이름만 남은 이유: `load_forward` 는 키 노출을 막으려고 예외 문자열을 싣지 않는다(설계대로).

## 3. 수정 — `dart_load.py` 한 파일 (+ 테스트 3)

```diff
+import sys
 …
-    spec = importlib.util.spec_from_file_location("dart_disclosure_backfill", str(path))
+    spec = importlib.util.spec_from_file_location("_llm_shadow_dart_disclosure_backfill", str(path))
     mod = importlib.util.module_from_spec(spec)
+    sys.modules[spec.name] = mod
     spec.loader.exec_module(mod)
```

- 모듈 이름은 다른 것과 겹치지 않게 바꿨다(`tests/test_dart_disclosure_backfill.py` 의 `scripts.dart_disclosure_backfill` 과 다르다). 그 밖의 동작은 바뀌지 않는다.
- **무변경**: 백필 스크립트 본문 · 적재 범위·완결 판정·OpenDART 합산 ≤ 60 · 잠금 · 채점(`state`·`schedule`)·입력(`inputs`)·프롬프트(`prompt_v1` · `prompt_sha256` `ca5348ad…0e62` · `prompt_sha256_search` `e1281ce9…a613`)·argv·CLI 2.1.283·exe `9dbe16da…de3a`·묶음 타임아웃 180초·DDL·검정.
- 테스트(`tests/test_llm_shadow.py` · 기존 33 무변경 + 3): ① `_backfill_module()` 실제 적재 ② 실제 백필 모듈 + 가짜 OpenDART·가짜 DB 로 09-24~09-28 완결(013 8회 + 09-28 B 1쪽 · I 2쪽 · 유형 간 중복 1 → 11회 · 재실행 0회) ③ 합산 55회 소진 → 5회 뒤 `CallBudget` 중단(미완결·보류) → 다음 날 이어서 완결. 수정 전에는 3개 다 실패하고(`적재 중단: AttributeError` 그대로 재현) 수정 후에는 전부 통과한다(3.9.13 두 인터프리터).

## 4. 영향

- **본체 F1 D=09-28**: 09-29 에 채점 보류. §2 「누락 보충 = 최근 5거래일 · D 오름차순」(`settings.CATCHUP_TD=5` · 스케줄러 인자 `--catchup`)으로 회복한다. 09-28 이 따라잡기 창에 남는 마지막 D 는 **10-02**, 그 D 를 처리하는 마지막 실행은 **T=10-06**이다(10-05 = 개천절 대체공휴일 · `is_trading_day` 거짓). 실제 `target_days` 로 계산한 값이다.
  - 재배포가 09-30 08:30 전에 끝나면 **T=09-30 16:10 한 번**에 `[09-23(호출 0), 09-28, 09-29]` 를 처리한다. D 단위 상한 ≤ 20호출이라 이 실행은 최대 약 40호출 · 약 7분이다(09-23 실측 19호출 3분 19초). 작업 제한 90분 안에 든다.
  - 늦을수록 한 번에 따라잡는 D 가 늘어난다(10-02 재배포면 5일 · 최대 약 100호출). 구독 한도 사다리(§5-8)에 걸릴 위험도 그만큼 커진다.
- **PIT**: 따라잡는 D 의 컷오프는 실행일이 아니라 `T_D = next_trading_day(D)` 다(`state.compute_schedule` · `day_plan.t_date`). D=09-28 은 `news.created_at < 09-29 08:30` 그대로다. 실행이 늦어서 생기는 차이는 그 사이의 늦은 수정·삭제뿐이며, §11 V3 드리프트율에 들어간다.
- **검색 팔 S1 D=09-28**: **영구 결측**이다(검색 팔에는 따라잡기가 없다 · 판정 밖 · 보조). S1 D=09-29 표본 목록은 T=09-30 08:30 에, 본체가 09-28 을 따라잡기 «전»에 같은 규칙으로 계산된다(`main_codes`). 그래서 09-28 에 처음 들어온 종목·09-28 이월분만큼 본체 09-29 계획과 어긋날 수 있다. (ㄴ) 짝 비교는 교집합으로만 한다(판정 밖).
- **OpenDART**: 09-30 08:30 적재 범위는 09-24~09-29(휴장·주말 4일 × B·I = 013 8회 + 거래일 2일)다. ① 실측(날짜×유형 페이지 합 중앙 4 · 최대 15)으로 추정하면 약 16~38회로 ≤ 60 이다. 넘어도 `CallBudget` 이 멈추고 다음 실행이 이어 받는다(테스트 ③).
- **봉인 데이터 오염**: 없다. 09-29 두 실행은 채점 행을 새로 쓰지 않았다(D=09-23 재처리 호출 0 · 원장 해시 동일).

## 5. 선언된 이탈 — §11 V2·V6 판정 방식

- **V2**: 「`code_sha` 한 값」을 「`code_sha` ∈ {`9bbf15c19dbe…`, 이 수정 커밋}」으로 바꾼다. D=09-23 행은 `9bbf15c`, D ≥ 09-28 행은 수정 커밋이다. verifier 는 두 값의 차이가 `git diff 9bbf15c <수정 커밋> --stat -- RoboTrader_template ':!RoboTrader_template/tests' ':!RoboTrader_template/docs'` 에서 **`llm_shadow/dart_load.py` 한 파일**뿐인지 확인한다. `exe_sha256`·`prompt_sha256`·`argv_sha256`·`cli_version`·가족 안 `model` 은 여전히 한 값이다.
- **V6**: git 순서를 「동결 < 코드 커밋 < 첫 행 < **이 수정 커밋(첫 행 뒤 · 채점 무관 · 이 문서)** < 개봉-1 < 개봉-2」로 읽는다.
- 재동결 이력은 `%LOCALAPPDATA%\kis-llm-shadow\frozen_history.jsonl` 에 `9bbf15c` 동결 줄이 자동으로 append 되는 것으로 남긴다(§5-1 · git 밖 frozen.json 이탈 (a) 그대로).

## 6. 재동결 필요성

- §5-1 은 「HEAD = 동결 `code_sha` ∧ `git status --porcelain` 빈 상태」에서만 실행을 허용한다. 수정 커밋이 배포 워크트리(`D:/tmp/kis-wt-dart-events` · `research/dart-events`)에 들어가면 HEAD ≠ `9bbf15c` 가 되어 런너가 거부한다. 그래서 **`--freeze` 재동결이 필수**다.
- 재동결 뒤 `frozen.json` 에서 바뀌어도 되는 값은 **`code_sha`·`frozen_at` 둘뿐**이다. `exe_sha256`·`cli_version`·`prompt_sha256`·`prompt_sha256_search`·`batch_timeout_s`(180) 중 하나라도 바뀌면 이 개정문 범위를 벗어난 것이므로 중단하고 보고한다.
- 머지와 재동결 사이에 스케줄 실행이 끼면 `GuardError` 거부 + 경보가 난다. 그래서 두 작업을 러너가 돌지 않는 시간(평일 08:30~08:58 · 16:10~17:40 밖)에 연달아 한다.

## 7. 사장님 결정 사항

1. 이 수정을 «새 가족 사유 아님 · F1 유지»로 인정하는가.
2. §5 V2·V6 판정 방식 개정(`code_sha` 두 값)을 승인하는가.
3. 커밋 + `research/dart-events` 머지 + push + 재동결 시점(권고: **09-30 08:30 전** — 그러면 09-30 16:10 한 번에 09-28·09-29 를 회복한다).

> 🔒 **사장님 결정(2026-09-29 17:3x)**: 「세 가지 모두 승인 · 오늘 배포」 — ① F1 유지(새 가족 사유 아님) ② V2·V6 판정 방식 개정(`code_sha` 두 값: D=09-23 → `9bbf15c` · D≥09-28 → 이 개정 커밋) ③ 09-29 저녁 커밋·머지·push·재동결. 리뷰(code-reviewer · 원본 대조 3 failed/65 passed → 수정 68 passed 독립 재현 · T=10-06 재현) APPROVE-WITH-NOTES · 필수 수정 0.

## 🔒 확정 시점

사장님 승인 뒤 이 문서를 **수정 코드와 같은 커밋**으로 넣는다. 앞선 개정문 `9bbf15c`(문서 + 코드 한 커밋)와 같은 방식이다. 그 커밋을 배포 워크트리에 반영한 **직후** 재동결하고, 재동결 전에는 어떤 실행도 새 코드로 돌지 않는다.
