# kis-trading-template

한국투자증권(KIS) Open API 기반 국내 주식 자동매매 봇. 현재 8전략 **페이퍼(가상) 매매**로 매 거래일 운영 중이며, 실전 전환은 보류 상태다.

**코드는 전부 `RoboTrader_template/` 아래에 있다** (디렉토리명은 프레임워크 템플릿 시절의 레거시명).

- 시작점: [RoboTrader_template/README.md](RoboTrader_template/README.md) · 개발 라우터: [RoboTrader_template/CLAUDE.md](RoboTrader_template/CLAUDE.md)
- `pytest` 설정은 이 루트의 `pyproject.toml` 이 가진다(`testpaths = ["RoboTrader_template/tests"]`).

```bat
cd RoboTrader_template
copy config\key.ini.example config\key.ini
run_robotrader.bat
```

`config/key.ini` 의 `[KIS]` 절에 API 키·계좌를 넣는다(`.env` 가 아니다). `run_robotrader.bat` 가 venv 생성 → 의존성 설치 → 기동까지 한 번에 한다.
DB 는 PostgreSQL 16 + TimescaleDB, 포트 **5433**, DB `kis_template` 이 코드 기본값이라 `.env` 없이도 붙는다 → [docs/DATABASE.md](RoboTrader_template/docs/DATABASE.md).

---
⚠️ 교육 및 연구 목적입니다. 실제 투자 손실은 사용자 책임입니다.
