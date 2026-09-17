# CLAUDE.md — kis-trading-template (레포 루트)

- 코드는 전부 `RoboTrader_template/` 아래. 상세 라우터 = [RoboTrader_template/CLAUDE.md](RoboTrader_template/CLAUDE.md) · 문서 색인 = [RoboTrader_template/docs/README.md](RoboTrader_template/docs/README.md).
- pytest 설정은 이 루트 `pyproject.toml`(`[tool.pytest.ini_options]` · `testpaths=RoboTrader_template/tests` · `asyncio_mode=auto` · 마커 `slow`·`db`). ruff 설정은 `RoboTrader_template/pyproject.toml`. CI = `.github/workflows/test.yml`(Python 3.9/3.11/3.12).
- 🔴 봇은 **월~금 07:40 Windows 작업 스케줄러가 자동 기동**한다(라이브 트리 = `D:/GIT/kis-trading-template`, 항상 `main`). **라이브 트리에서 테스트·스모크 실행 금지 · 장중 브랜치 전환 금지.** 작업은 `git worktree add D:/tmp/kis-wt-<topic> -b <type>/<topic>` 로 만든 워크트리에서.
- KIS API 키·텔레그램 = `RoboTrader_template/config/key.ini`(`key.ini.example` 복사) — **`.env` 가 아니다**. `.env` 는 선택(DB 기본값 port 5433 / `kis_template` 은 `db/connection.py` 코드에 있음).
- 루트 `agents/`·`cache/`·`logs/`·`scratchpad/` 는 잔재 디렉토리(미추적·라이브 봇과 무관). 루트 `scripts/`(3파일 = `corp_events` 수동 백필(pykrx) 본체+워커 2 · 멀티버스 스모크 CLI 1)·`docs/superpowers/`(specs 6 · plans 5)는 연구·일회성이며 라이브 봇 코드가 아니다(운영 디렉토리 import 0).
- 세션 메모리·changelog 는 레포 밖 Claude Code 프로젝트 메모리에 있다(git 에 없음).
- 커밋·푸시·추적 파일 삭제는 사장님 확인 후. 커밋 메시지 = `type(scope): 한국어 요약`.

**마지막 업데이트**: 2026-09-17
