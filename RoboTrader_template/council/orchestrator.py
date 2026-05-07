"""Council orchestrator - manages the multi-agent discussion workflow."""

import asyncio
import io
import logging
import sys
from typing import Optional

from .agent import Agent, AgentResponse
from .config import CouncilConfig, TeamConfig
from .session import Session

logger = logging.getLogger("council")

# Fix Windows cp949 encoding issues with emojis/unicode
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace"
    )


def _safe_print(text: str):
    """Print with encoding error protection."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("utf-8", errors="replace").decode("utf-8"))


def _print_phase(title: str):
    """Print a phase header."""
    bar = "=" * 60
    _safe_print(f"\n{bar}")
    _safe_print(f"  {title}")
    _safe_print(f"{bar}\n")


def _print_speaker(name: str, role: str, team: str):
    """Print who is speaking."""
    _safe_print(f"  [{team}] {name} ({role}) 발언 중...")


def _print_response_preview(response: AgentResponse, max_lines: int = 5):
    """Print a brief preview of the response."""
    if not response.success:
        _safe_print(f"  !! 에러: {response.error}")
        return
    lines = response.content.strip().split("\n")
    preview = "\n".join(lines[:max_lines])
    if len(lines) > max_lines:
        preview += f"\n  ... (+{len(lines) - max_lines}줄)"
    # Indent for readability
    indented = "\n".join(f"    {l}" for l in preview.split("\n"))
    _safe_print(indented)
    _safe_print(f"  ({response.elapsed_seconds:.1f}초)")
    print()


class Council:
    """Orchestrates multi-agent discussions."""

    def __init__(self, config: CouncilConfig):
        self.config = config
        self.leader = Agent(config.leader, config.project_dir)
        self.teams: dict[str, list[Agent]] = {}

        for team_id, team_config in config.teams.items():
            self.teams[team_id] = [
                Agent(member, config.project_dir) for member in team_config.members
            ]

    async def run(self, topic: str, session: Session) -> str:
        """Run the full council workflow."""

        # Phase 1: Leader creates agenda
        _print_phase("Phase 1: 리더 분석 및 과제 할당")
        agenda = await self._leader_analyze(topic, session)
        if not agenda:
            print("리더 분석 실패. 중단합니다.")
            return ""

        # Phase 2: Team discussions (parallel across teams)
        _print_phase("Phase 2: 팀 내부 토론")
        discussions = await self._team_discussions(agenda, session)

        # Phase 3: Team reports
        _print_phase("Phase 3: 팀별 보고서 작성")
        reports = await self._team_reports(agenda, discussions, session)

        # Phase 4: Cross-review
        _print_phase("Phase 4: 교차 검토")
        cross_review = await self._cross_review(reports, session)

        # Phase 5: Leader synthesis
        _print_phase("Phase 5: 리더 최종 종합")
        summary = await self._leader_synthesize(
            topic, agenda, reports, cross_review, session
        )

        _print_phase("Council 완료")
        print(f"세션 저장: {session.dir}")
        print(f"최종 보고서: {session.dir / '04-summary.md'}")

        return summary

    async def _leader_analyze(self, topic: str, session: Session) -> Optional[str]:
        """Phase 1: Leader analyzes the topic and creates team assignments."""
        prompt = f"""사장님이 다음 주제를 지시했습니다:

---
{topic}
---

다음을 수행하세요:
1. 주제를 분석하고 핵심 논점을 정리하세요
2. 각 팀에 구체적인 과제를 할당하세요:
   - 개발팀 (dev): 코드/구현 관점의 분석 과제
   - 검수팀 (qa): 품질/보안 관점의 검증 과제
   - 주식전문가팀 (expert): 도메인/전략 관점의 검토 과제
3. 각 팀이 집중해야 할 핵심 질문을 명시하세요

형식:
# 주제 분석
(분석 내용)

# 개발팀 과제
(과제 및 핵심 질문)

# 검수팀 과제
(과제 및 핵심 질문)

# 주식전문가팀 과제
(과제 및 핵심 질문)

# 주의사항
(팀 간 협력이 필요한 부분, 우선순위 등)"""

        _print_speaker("리더", "개발 총괄", "leadership")
        response = await self.leader.think(prompt)
        _print_response_preview(response)

        if response.success:
            session.save_agenda(response.content)
            return response.content
        return None

    async def _team_discussions(
        self, agenda: str, session: Session
    ) -> dict[str, str]:
        """Phase 2: Each team discusses internally (parallel across teams)."""
        tasks = []
        team_ids = list(self.teams.keys())

        for team_id in team_ids:
            tasks.append(self._single_team_discussion(team_id, agenda, session))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        discussions = {}
        for team_id, result in zip(team_ids, results):
            if isinstance(result, Exception):
                logger.error(f"팀 {team_id} 토론 에러: {result}")
                discussions[team_id] = f"(토론 실패: {result})"
            else:
                discussions[team_id] = result

        return discussions

    async def _single_team_discussion(
        self, team_id: str, agenda: str, session: Session
    ) -> str:
        """Run a single team's internal discussion."""
        team = self.teams[team_id]
        team_config = self.config.teams[team_id]
        discussion_log = f"# {team_config.name} 토론\n\n"

        # Extract team-specific assignment from agenda
        for round_num in range(1, self.config.discussion_rounds + 1):
            discussion_log += f"\n## Round {round_num}\n\n"

            for member in team:
                if round_num == 1 and member.is_lead:
                    # Team lead starts the discussion
                    prompt = f"""다음은 리더가 배정한 전체 과제입니다:

{agenda}

당신은 {team_config.name}의 팀장입니다. 팀 토론을 시작하세요:
1. 우리 팀에 할당된 과제를 분석하세요
2. 필요한 코드/파일을 직접 읽고 분석하세요
3. 초기 분석 결과와 의견을 제시하세요
4. 팀원들에게 세부 검토를 요청하세요

실제 코드를 읽고 구체적인 근거를 들어 의견을 제시하세요."""
                else:
                    # Truncate previous discussion to last 3000 chars to avoid
                    # context bloat in later rounds
                    prev_context = discussion_log
                    if len(prev_context) > 3000:
                        prev_context = "...(이전 토론 생략)...\n\n" + prev_context[-3000:]

                    prompt = f"""다음은 리더가 배정한 전체 과제입니다:

{agenda}

다음은 지금까지의 우리 팀({team_config.name}) 토론 내용입니다:

{prev_context}

당신의 차례입니다. 이전 발언을 참고하여:
1. 동의하는 부분과 다른 의견이 있는 부분을 명시하세요
2. 새로운 관점이나 놓친 부분을 추가하세요
3. 필요한 코드/파일을 직접 읽고 근거를 제시하세요
4. 구체적인 제안을 하세요

단순한 동의가 아닌, 실질적인 기여를 하세요."""

                _print_speaker(member.name, member.role, team_config.name)
                response = await member.think(prompt)
                _print_response_preview(response)

                if response.success:
                    discussion_log += f"### {member.name} ({member.role})\n\n"
                    discussion_log += response.content + "\n\n---\n\n"
                else:
                    discussion_log += f"### {member.name} ({member.role})\n\n"
                    discussion_log += f"(발언 실패: {response.error})\n\n---\n\n"

        session.save_discussion(team_id, discussion_log)
        return discussion_log

    async def _team_reports(
        self,
        agenda: str,
        discussions: dict[str, str],
        session: Session,
    ) -> dict[str, str]:
        """Phase 3: Each team lead writes a report summarizing their discussion."""
        tasks = []
        team_ids = list(self.teams.keys())

        for team_id in team_ids:
            lead = next((m for m in self.teams[team_id] if m.is_lead), self.teams[team_id][0])
            team_config = self.config.teams[team_id]

            prompt = f"""다음은 리더가 배정한 과제입니다:

{agenda}

다음은 우리 팀({team_config.name})의 토론 내용입니다:

{discussions.get(team_id, "(토론 내용 없음)")}

팀장으로서 토론을 종합하여 보고서를 작성하세요:

# {team_config.name} 보고서

## 핵심 발견사항
(가장 중요한 발견/결론)

## 세부 분석
(팀원들의 의견을 종합한 상세 분석)

## 이슈 목록
(심각도 순으로 정리: CRITICAL > HIGH > MEDIUM > LOW)

## 제안사항
(구체적인 개선/실행 제안)

## 다른 팀에 전달할 사항
(교차 검토 시 다른 팀이 확인해야 할 내용)"""

            tasks.append(lead.think(prompt))

        results = await asyncio.gather(*tasks)

        reports = {}
        for team_id, response in zip(team_ids, results):
            team_config = self.config.teams[team_id]
            _print_speaker(
                f"{team_config.name} 팀장", "보고서 작성", team_config.name
            )
            _print_response_preview(response)

            content = response.content if response.success else f"(보고서 작성 실패: {response.error})"
            reports[team_id] = content
            session.save_report(team_id, content)

        return reports

    async def _cross_review(
        self, reports: dict[str, str], session: Session
    ) -> str:
        """Phase 4: Teams cross-review each other's reports."""
        all_reports = "\n\n".join(
            f"---\n## {self.config.teams[tid].name} 보고서\n{content}\n---"
            for tid, content in reports.items()
        )

        # QA reviews dev report, Expert reviews from domain perspective
        tasks = []

        # QA team lead reviews dev team's report
        qa_lead = next((m for m in self.teams["qa"] if m.is_lead), self.teams["qa"][0])
        qa_prompt = f"""다음은 모든 팀의 보고서입니다:

{all_reports}

검수팀장으로서 교차 검토를 수행하세요:
1. 개발팀 보고서의 기술적 제안을 검증하세요
2. 놓친 품질/보안 이슈가 없는지 확인하세요
3. 전문가팀의 도메인 의견과 개발팀의 기술적 의견 사이에 충돌이 없는지 확인하세요
4. 전체적인 실행 가능성을 평가하세요

형식:
# 교차 검토 - 검수팀 관점
## 개발팀 보고서 검토
## 전문가팀 보고서 검토
## 팀 간 의견 충돌/보완 사항
## 최종 검수 의견"""
        tasks.append(qa_lead.think(qa_prompt))

        # Expert team lead reviews from domain perspective
        expert_lead = next(
            (m for m in self.teams["expert"] if m.is_lead), self.teams["expert"][0]
        )
        expert_prompt = f"""다음은 모든 팀의 보고서입니다:

{all_reports}

주식전문가팀장으로서 교차 검토를 수행하세요:
1. 개발팀의 구현 방향이 도메인 관점에서 타당한지 검증하세요
2. 검수팀이 놓친 도메인 특화 리스크가 없는지 확인하세요
3. 실전 트레이딩 관점에서의 우려사항을 제시하세요
4. 전략적 개선 방향을 제안하세요

형식:
# 교차 검토 - 주식전문가팀 관점
## 개발팀 기술 방향 검토
## 검수팀 품질 기준 검토
## 도메인 특화 우려사항
## 전략적 제안"""
        tasks.append(expert_lead.think(expert_prompt))

        results = await asyncio.gather(*tasks)

        cross_review = "# 교차 검토 결과\n\n"
        labels = ["검수팀", "주식전문가팀"]
        for label, response in zip(labels, results):
            _print_speaker(f"{label} 팀장", "교차 검토", label)
            _print_response_preview(response)

            if response.success:
                cross_review += f"\n{response.content}\n\n---\n\n"
            else:
                cross_review += f"\n({label} 교차 검토 실패: {response.error})\n\n---\n\n"

        session.save_cross_review(cross_review)
        return cross_review

    async def _leader_synthesize(
        self,
        topic: str,
        agenda: str,
        reports: dict[str, str],
        cross_review: str,
        session: Session,
    ) -> str:
        """Phase 5: Leader synthesizes everything into a final summary."""
        all_reports = "\n\n".join(
            f"## {self.config.teams[tid].name} 보고서\n{content}"
            for tid, content in reports.items()
        )

        prompt = f"""당신은 Council 리더입니다. 모든 팀의 토론, 보고서, 교차 검토가 완료되었습니다.

원래 주제:
{topic}

팀별 보고서:
{all_reports}

교차 검토 결과:
{cross_review}

최종 종합 보고서를 작성하세요:

# Council 최종 보고서

## 주제
(원래 주제 요약)

## 핵심 결론
(모든 팀의 의견을 종합한 최종 결론)

## 합의된 사항
(팀 간 합의가 이루어진 내용)

## 미해결 논점
(팀 간 의견이 갈린 부분과 리더로서의 최종 판단)

## 실행 계획
(우선순위별 구체적 액션 아이템)
- CRITICAL: 즉시 실행 필요
- HIGH: 이번 주기에 실행
- MEDIUM: 다음 주기에 실행
- LOW: 검토 후 결정

## 각 팀 피드백
(각 팀에 전달할 코멘트)

## 사장님께 보고
(사장님에게 전달할 최종 요약 - 3~5문장)"""

        _print_speaker("리더", "최종 종합", "leadership")
        response = await self.leader.think(prompt)
        _print_response_preview(response, max_lines=10)

        content = response.content if response.success else f"(최종 종합 실패: {response.error})"
        session.save_summary(content)
        return content

    async def implement(
        self, plan: str, session: Session
    ) -> str:
        """Optional Phase 6: Dev team implements changes, QA verifies."""
        _print_phase("Phase 6: 구현")

        # Dev team implements
        dev_lead = next(
            (m for m in self.teams["dev"] if m.is_lead), self.teams["dev"][0]
        )
        # Give dev lead write access for implementation
        original_tools = dev_lead.config.tools
        dev_lead.config.tools = ["Read", "Glob", "Grep", "Edit", "Write", "Bash"]

        impl_prompt = f"""다음 실행 계획에 따라 코드를 수정하세요:

{plan}

지침:
- 계획에 명시된 변경 사항만 구현하세요
- 각 변경 사항에 대해 수정 전/후를 설명하세요
- 테스트도 함께 수정/추가하세요
- 완료 후 변경 목록을 정리하세요"""

        _print_speaker("시니어 개발자", "구현", "개발팀")
        impl_response = await dev_lead.think(impl_prompt, timeout_seconds=600)
        _print_response_preview(impl_response, max_lines=10)

        # Restore original tools
        dev_lead.config.tools = original_tools

        # QA verification
        qa_lead = next(
            (m for m in self.teams["qa"] if m.is_lead), self.teams["qa"][0]
        )
        verify_prompt = f"""개발팀이 다음 구현을 완료했습니다:

{impl_response.content if impl_response.success else "(구현 실패)"}

검증을 수행하세요:
1. 변경된 파일들을 읽고 코드 품질을 확인하세요
2. 테스트를 실행하세요 (Bash 도구로 pytest 실행)
3. 구현이 계획대로 되었는지 확인하세요
4. 문제가 있으면 구체적으로 지적하세요"""

        _print_speaker("QA 리드", "검증", "검수팀")
        verify_response = await qa_lead.think(verify_prompt)
        _print_response_preview(verify_response)

        result = f"# 구현 결과\n\n"
        result += f"## 개발팀 구현\n{impl_response.content if impl_response.success else impl_response.error}\n\n"
        result += f"## QA 검증\n{verify_response.content if verify_response.success else verify_response.error}\n\n"

        session.save_implementation(result)
        return result
