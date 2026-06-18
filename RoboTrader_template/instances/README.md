# 실전 인스턴스 셋업

전략당 1개 실전 인스턴스. 격리 3중: 계좌 / 프로세스 / DB 테이블.

## 새 인스턴스 추가
1. `instances/<strategy>/` 폴더 생성
2. `key.ini.example` → `key.ini` 복사 후 **그 계좌의 실 앱키/시크릿/계좌번호** 입력
3. `trading_config.json.example` → `trading_config.json` 복사, `paper_trading=false`, 활성전략=해당 1개 확인
4. 기동: `run_instance.bat <strategy>` (= `set KIS_INSTANCE_DIR=instances\<strategy>`)
5. 첫 기동 시 `real_trading_<strategy>` 테이블이 자동 생성됨(robotrader DB)

## 보안
- `instances/` 전체가 .gitignore됨 — 실 key.ini는 절대 커밋되지 않음
- 키 백업은 repo 밖 안전한 곳(비밀번호 관리자/암호화 볼륨)

## 검증
- 가동 후 `robotrader_<strategy>.pid` 생성 확인
- KIS 계좌 잔고 = 해당 전략 단독 운용 확인
- `SELECT * FROM real_trading_<strategy>` 로 기록 격리 확인
