"""Session management for council discussions."""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional


class Session:
    """Manages a council discussion session's files."""

    def __init__(self, base_dir: str, topic: str, session_id: Optional[str] = None):
        self.topic = topic
        self.session_id = session_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        # Sanitize topic for directory name
        safe_topic = "".join(
            c if c.isalnum() or c in "-_ " else "" for c in topic[:40]
        ).strip().replace(" ", "-")
        self.dir = Path(base_dir) / "sessions" / f"{self.session_id}-{safe_topic}"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "teams").mkdir(exist_ok=True)
        (self.dir / "reports").mkdir(exist_ok=True)

    def save_agenda(self, content: str) -> Path:
        """Save the leader's agenda."""
        path = self.dir / "00-agenda.md"
        path.write_text(content, encoding="utf-8")
        return path

    def save_discussion(self, team_id: str, content: str) -> Path:
        """Save a team's discussion."""
        path = self.dir / "teams" / f"{team_id}-discussion.md"
        path.write_text(content, encoding="utf-8")
        return path

    def save_report(self, team_id: str, content: str) -> Path:
        """Save a team's report."""
        path = self.dir / "reports" / f"{team_id}-report.md"
        path.write_text(content, encoding="utf-8")
        return path

    def save_cross_review(self, content: str) -> Path:
        """Save cross-review results."""
        path = self.dir / "03-cross-review.md"
        path.write_text(content, encoding="utf-8")
        return path

    def save_summary(self, content: str) -> Path:
        """Save the leader's final summary."""
        path = self.dir / "04-summary.md"
        path.write_text(content, encoding="utf-8")
        return path

    def save_implementation(self, content: str) -> Path:
        """Save implementation results."""
        path = self.dir / "05-implementation.md"
        path.write_text(content, encoding="utf-8")
        return path

    def read_file(self, filename: str) -> Optional[str]:
        """Read a session file."""
        path = self.dir / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def get_all_reports(self) -> dict[str, str]:
        """Read all team reports."""
        reports = {}
        report_dir = self.dir / "reports"
        if report_dir.exists():
            for f in report_dir.glob("*-report.md"):
                team_id = f.stem.replace("-report", "")
                reports[team_id] = f.read_text(encoding="utf-8")
        return reports

    @staticmethod
    def list_sessions(base_dir: str) -> list[dict]:
        """List all past sessions."""
        sessions_dir = Path(base_dir) / "sessions"
        if not sessions_dir.exists():
            return []
        result = []
        for d in sorted(sessions_dir.iterdir(), reverse=True):
            if d.is_dir():
                agenda = d / "00-agenda.md"
                summary = d / "04-summary.md"
                result.append({
                    "id": d.name,
                    "path": str(d),
                    "has_agenda": agenda.exists(),
                    "has_summary": summary.exists(),
                })
        return result
