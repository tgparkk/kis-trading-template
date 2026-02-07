# Agent 시스템

## 개요
이 프로젝트는 여러 전문화된 Agent가 협력하여 작업을 수행합니다.
감독(Supervisor)이 전체를 총괄하고, 각 Agent는 전문 분야를 담당합니다.

## Agent 목록
| Agent | 파일 | 역할 |
|-------|------|------|
| 감독 | SUPERVISOR.md | 프로젝트 총괄, Agent 조율 |
| 분석 | ANALYZER.md | 코드 분석, 구조 파악 |
| 설계 | DESIGNER.md | 아키텍처 설계, 인터페이스 정의 |
| 개발 | DEVELOPER.md | 코드 구현, 리팩토링 |
| 테스트 | TESTER.md | 테스트 작성, 품질 검증 |
| 문서화 | DOCUMENTER.md | 문서 작성, API 문서화 |

## 협업 흐름
1. 감독이 요청 분석 및 작업 분배
2. 분석 Agent가 현황 파악
3. 설계 Agent가 구조 설계
4. 개발자 Agent가 구현 (병렬)
5. 테스트 Agent가 검증
6. 문서화 Agent가 문서 정리

## 사용 방법
각 Agent의 지침서를 참고하여 작업을 수행합니다.

## 프로그래매틱 사용법

### Python에서 사용
```python
from agents import AgentRunner, developer_prompt

# 방법 1: AgentRunner 클래스 사용
prompt = AgentRunner.create_prompt(
    agent_type="developer",
    task="framework/broker.py 리팩토링",
    context="FundManager 클래스 분리 필요"
)

# 방법 2: 편의 함수 사용
prompt = developer_prompt("framework/broker.py 리팩토링")
```

### 사용 가능한 Agent 확인
```python
from agents import AgentRunner

# 모든 Agent 목록과 지침서 존재 여부 확인
agents = AgentRunner.list_agents()
for name, info in agents.items():
    status = "O" if info["exists"] else "X"
    print(f"[{status}] {name}: {info['file']}")
```

### 감독이 Agent 실행 시
```
Task 도구 호출 시 AgentRunner.create_prompt()로 생성된 prompt 사용
-> 해당 Agent의 지침서가 자동으로 포함됨
```
