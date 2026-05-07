"""Claude CLI agent wrapper for council discussions."""

import asyncio
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

from .config import AgentConfig

logger = logging.getLogger("council")


@dataclass
class AgentResponse:
    """Response from an agent."""
    agent_name: str
    agent_role: str
    content: str
    elapsed_seconds: float
    success: bool
    error: Optional[str] = None


# Global semaphore to limit concurrent claude CLI calls (API rate limit)
_semaphore: Optional[asyncio.Semaphore] = None


def get_semaphore(max_concurrent: int = 1) -> asyncio.Semaphore:
    """Get or create the global concurrency semaphore."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(max_concurrent)
    return _semaphore


class Agent:
    """Wraps a Claude CLI invocation as an agent.

    Pipes the prompt via stdin to avoid Windows command-line length limits.
    """

    MAX_RETRIES = 2
    RETRY_DELAY = 10  # seconds

    def __init__(self, config: AgentConfig, project_dir: str):
        self.config = config
        self.project_dir = project_dir

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def role(self) -> str:
        return self.config.role

    @property
    def is_lead(self) -> bool:
        return self.config.is_lead

    async def think(
        self,
        prompt: str,
        max_budget: Optional[float] = None,
        timeout_seconds: int = 600,
    ) -> AgentResponse:
        """Run the agent with a prompt and return the response.

        Uses a global semaphore to limit concurrent API calls and
        retries on failure with exponential backoff.
        """
        sem = get_semaphore()

        for attempt in range(1, self.MAX_RETRIES + 1):
            async with sem:
                logger.info(
                    f"[{self.config.team}] {self.name} 발언 시작"
                    f"{f' (재시도 {attempt}/{self.MAX_RETRIES})' if attempt > 1 else ''}..."
                )
                start = time.time()

                try:
                    cmd = self._build_command(max_budget)
                    loop = asyncio.get_event_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(
                            None, self._run_sync, cmd, prompt
                        ),
                        timeout=timeout_seconds,
                    )
                    elapsed = time.time() - start

                    if result["returncode"] != 0:
                        error_msg = result["stderr"] or f"exit code {result['returncode']}"
                        logger.error(f"[{self.name}] 에러: {error_msg[:500]}")
                        if attempt < self.MAX_RETRIES:
                            delay = self.RETRY_DELAY * attempt
                            logger.info(f"[{self.name}] {delay}초 후 재시도...")
                            await asyncio.sleep(delay)
                            continue
                        return AgentResponse(
                            agent_name=self.name,
                            agent_role=self.role,
                            content="",
                            elapsed_seconds=elapsed,
                            success=False,
                            error=error_msg,
                        )

                    # Check for empty response (sometimes CLI returns 0 but no output)
                    if not result["stdout"].strip():
                        logger.warning(f"[{self.name}] 빈 응답")
                        if attempt < self.MAX_RETRIES:
                            delay = self.RETRY_DELAY * attempt
                            logger.info(f"[{self.name}] {delay}초 후 재시도...")
                            await asyncio.sleep(delay)
                            continue

                    logger.info(
                        f"[{self.config.team}] {self.name} 발언 완료 ({elapsed:.1f}s)"
                    )
                    return AgentResponse(
                        agent_name=self.name,
                        agent_role=self.role,
                        content=result["stdout"],
                        elapsed_seconds=elapsed,
                        success=True,
                    )

                except asyncio.TimeoutError:
                    elapsed = time.time() - start
                    logger.warning(f"[{self.name}] 타임아웃 ({timeout_seconds}s)")
                    return AgentResponse(
                        agent_name=self.name,
                        agent_role=self.role,
                        content="",
                        elapsed_seconds=elapsed,
                        success=False,
                        error=f"타임아웃 ({timeout_seconds}초)",
                    )

        # Should not reach here, but just in case
        return AgentResponse(
            agent_name=self.name, agent_role=self.role, content="",
            elapsed_seconds=0, success=False, error="최대 재시도 초과",
        )

    def _run_sync(self, cmd: list[str], prompt: str) -> dict:
        """Synchronous subprocess execution (run in executor)."""
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.project_dir,
            shell=(sys.platform == "win32"),  # Windows needs shell for .cmd
        )
        stdout, stderr = proc.communicate(input=prompt.encode("utf-8"))
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace").strip(),
            "stderr": stderr.decode("utf-8", errors="replace").strip(),
        }

    def _build_command(self, max_budget: Optional[float] = None) -> list[str]:
        """Build the claude CLI command (prompt comes via stdin)."""
        cmd = [
            "claude",
            "-p",                          # print mode (stdin → stdout)
            "--system-prompt",
            self.config.system_prompt,
            "--model",
            self.config.model,
            "--output-format", "text",
        ]

        if self.config.tools:
            cmd.extend(["--tools", ",".join(self.config.tools)])

        if max_budget:
            cmd.extend(["--max-budget-usd", str(max_budget)])

        return cmd
