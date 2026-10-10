"""🔒 동결 해시 2개 — `PREREG.md` 의 pins 블록이 고정하는 파일 목록에서 «빠지는» 유일한 패키지 파일(순환 해시 회피).

- `PREREG_FROZEN_BLOB` = 동결된 `PREREG.md` 의 git blob(`git hash-object PREREG.md`). PREREG.md 의 ```pins 블록이
  나머지 코드·의존 모듈·`results/backfill_check.json` 의 blob 을 고정하므로, 이 값 하나가 전체를 사슬로 묶는다.
- `PROXY_COEF_MD5` = `results/proxy_coef.json` 의 md5.
둘 다 Task 12 동결 커밋 때 채운다. 비어 있으면 build·seal·open 거부(`run.require_frozen`).
"""
PREREG_FROZEN_BLOB = ""   # Task 12 동결 커밋 뒤 설정 — 비어 있으면 build·seal·open 거부
PROXY_COEF_MD5 = ""        # Task 12 동결 때 PREREG_FROZEN_BLOB 와 함께 설정 — 비어 있으면 build·seal·open 거부
