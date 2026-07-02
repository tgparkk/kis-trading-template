# archive/

무참조 연구 스크립트 보관소 — 라이브 매매/테스트 어디서도 참조되지 않는 것으로 판정된
`scripts/` 하위 코드를 git 이력 보존한 채 이곳으로 이동했습니다.

- 판정 근거: `docs/superpowers/plans/2026-07-02-archive-candidates.md` (grep 0-hit 기준, ops 화이트리스트 제외)
- 복원 방법: `git mv archive/<path> <path>` (역방향 이동)
