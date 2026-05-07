"""Council CLI entry point.

Usage:
    python -m council "주제"
    python -m council "주제" --implement
    python -m council --list
    python -m council --model opus          # all agents use opus
    python -m council --rounds 3            # 3 rounds of discussion
"""

import argparse
import asyncio
import logging
import os
import sys

from .config import build_default_config
from .orchestrator import Council
from .session import Session


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")


def parse_args():
    parser = argparse.ArgumentParser(
        prog="council",
        description="Multi-agent council for kis-template development",
    )
    parser.add_argument("topic", nargs="?", help="Discussion topic")
    parser.add_argument(
        "--implement", action="store_true",
        help="Run implementation phase after discussion",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_sessions",
        help="List past sessions",
    )
    parser.add_argument(
        "--rounds", type=int, default=2,
        help="Number of discussion rounds per team (default: 2)",
    )
    parser.add_argument(
        "--leader-model", default="opus",
        help="Model for the leader agent (default: opus)",
    )
    parser.add_argument(
        "--member-model", default="sonnet",
        help="Model for team members (default: sonnet)",
    )
    parser.add_argument(
        "--budget", type=float, default=None,
        help="Max budget per agent call in USD",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    setup_logging(args.verbose)

    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # If we're inside council/, go up to RoboTrader_template/
    if os.path.basename(project_dir) == "council":
        project_dir = os.path.dirname(project_dir)

    council_dir = os.path.join(project_dir, "council")

    # List sessions
    if args.list_sessions:
        sessions = Session.list_sessions(council_dir)
        if not sessions:
            print("저장된 세션이 없습니다.")
            return
        print("과거 세션 목록:")
        for s in sessions:
            status = "완료" if s["has_summary"] else "진행중"
            print(f"  [{status}] {s['id']}")
        return

    # Topic is required for new discussions
    if not args.topic:
        print("주제를 입력하세요: python -m council \"주제\"")
        sys.exit(1)

    # Build configuration
    config = build_default_config(project_dir)
    config.discussion_rounds = args.rounds
    config.leader_model = args.leader_model
    config.member_model = args.member_model
    config.max_budget_per_call = args.budget

    # Update models in agent configs
    config.leader.model = args.leader_model
    for team in config.teams.values():
        for member in team.members:
            member.model = args.member_model

    # Create session
    session = Session(council_dir, args.topic)

    print(f"""
Council 시작
{'=' * 60}
주제: {args.topic}
리더 모델: {args.leader_model}
팀원 모델: {args.member_model}
토론 라운드: {args.rounds}
세션: {session.session_id}
{'=' * 60}

팀 구성:
  리더: 개발 총괄 리더 ({args.leader_model})
  개발팀: 시니어 개발자, 백엔드 개발자, 테스트 개발자
  검수팀: QA 리드, 코드 리뷰어, 보안 검수자
  주식전문가팀: 퀀트 분석가, 트레이딩 전략가, 리스크 관리자
""")

    # Run council
    council = Council(config)
    summary = await council.run(args.topic, session)

    # Optional implementation phase
    if args.implement and summary:
        confirm = input("\n구현 단계를 진행하시겠습니까? (y/N): ")
        if confirm.lower() in ("y", "yes"):
            await council.implement(summary, session)

    print("\nCouncil 종료.")


def run():
    """Entry point for the council CLI."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
