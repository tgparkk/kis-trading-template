"""
Agent Runner - 지침서 자동 적용 시스템

사용법:
    from agents.runner import AgentRunner

    # 개발자 Agent 실행용 prompt 생성
    prompt = AgentRunner.create_prompt(
        agent_type="developer",
        task="framework/broker.py 리팩토링"
    )
"""

from pathlib import Path
from typing import Optional, Union
from enum import Enum

class AgentType(Enum):
    SUPERVISOR = "supervisor"
    ANALYZER = "analyzer"
    DESIGNER = "designer"
    DEVELOPER = "developer"
    TESTER = "tester"
    DOCUMENTER = "documenter"

class AgentRunner:
    """Agent 지침서 자동 적용 헬퍼"""

    # 지침서 디렉토리 (이 파일 기준 상대 경로)
    AGENTS_DIR = Path(__file__).parent

    @classmethod
    def get_guidelines(cls, agent_type: Union[AgentType, str]) -> str:
        """Agent 유형에 맞는 지침서 로드"""
        if isinstance(agent_type, str):
            agent_type = AgentType(agent_type.lower())

        guideline_file = cls.AGENTS_DIR / f"{agent_type.value.upper()}.md"

        if not guideline_file.exists():
            raise FileNotFoundError(f"지침서 없음: {guideline_file}")

        return guideline_file.read_text(encoding='utf-8')

    @classmethod
    def create_prompt(
        cls,
        agent_type: Union[AgentType, str],
        task: str,
        context: Optional[str] = None,
        project_path: str = "D:\\GIT\\kis-trading-template\\RoboTrader_quant - 복사본"
    ) -> str:
        """
        지침서가 포함된 Agent 실행용 prompt 생성

        Args:
            agent_type: Agent 유형 (developer, tester 등)
            task: 수행할 작업 설명
            context: 추가 컨텍스트 (선택)
            project_path: 프로젝트 경로

        Returns:
            지침서 + 작업 설명이 포함된 prompt
        """
        guidelines = cls.get_guidelines(agent_type)

        prompt = f"""## Agent 지침서
{guidelines}

---

## 프로젝트 경로
{project_path}

## 작업 요청
{task}
"""

        if context:
            prompt += f"""
## 추가 컨텍스트
{context}
"""

        return prompt

    @classmethod
    def list_agents(cls) -> dict:
        """사용 가능한 Agent 목록 반환"""
        agents = {}
        for agent_type in AgentType:
            guideline_file = cls.AGENTS_DIR / f"{agent_type.value.upper()}.md"
            agents[agent_type.value] = {
                "file": str(guideline_file),
                "exists": guideline_file.exists()
            }
        return agents


# 편의 함수
def developer_prompt(task: str, context: str = None) -> str:
    """개발자 Agent용 prompt 생성"""
    return AgentRunner.create_prompt("developer", task, context)

def tester_prompt(task: str, context: str = None) -> str:
    """테스트 Agent용 prompt 생성"""
    return AgentRunner.create_prompt("tester", task, context)

def analyzer_prompt(task: str, context: str = None) -> str:
    """분석 Agent용 prompt 생성"""
    return AgentRunner.create_prompt("analyzer", task, context)

def designer_prompt(task: str, context: str = None) -> str:
    """설계 Agent용 prompt 생성"""
    return AgentRunner.create_prompt("designer", task, context)

def documenter_prompt(task: str, context: str = None) -> str:
    """문서화 Agent용 prompt 생성"""
    return AgentRunner.create_prompt("documenter", task, context)
