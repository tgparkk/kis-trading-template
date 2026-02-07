# 🤖 KIS Trading Template

> 한국투자증권 API 기반 자동매매 프레임워크 템플릿
>
> 전략만 갈아끼우면 새로운 자동매매 봇이 탄생합니다.

## 구조

```
kis-trading-template/
├── RoboTrader_template/    ← 프레임워크 본체
│   ├── framework/          ← 추상화 레이어 (Broker, Data, Executor)
│   ├── api/                ← KIS API 래퍼
│   ├── strategies/         ← 전략 모듈 (BaseStrategy + 예제)
│   ├── core/               ← 공통 핵심 (주문, 자금, 알림)
│   ├── config/             ← 설정
│   ├── db/                 ← 데이터베이스
│   ├── utils/              ← 유틸리티
│   └── tests/              ← 테스트
└── agents/                 ← AI 개발 에이전트
```

## 사용법

자세한 내용은 **[RoboTrader_template/README.md](RoboTrader_template/README.md)** 를 참고하세요.

```bash
cd RoboTrader_template
pip install -r requirements.txt
cp .env.example .env    # API 키 설정
python main.py
```

## 관련 프로젝트

| 프로젝트 | 전략 | 상태 |
|----------|------|------|
| [RoboTrader](https://github.com/tgparkk/RoboTrader) | Price Position 단타 | 운영 중 |
| RoboTrader_orb | ORB 돌파 단타 | 백테스팅 |
| RoboTrader_quant | 퀀트 팩터 포트폴리오 | 백테스팅 |

---

⚠️ 교육 및 연구 목적입니다. 실제 투자 손실은 사용자 책임입니다.
