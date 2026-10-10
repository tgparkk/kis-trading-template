"""실행 가드 — 라이브 트리 거부 · HEAD=동결 · clean · detached · 원본 7파일 sha(LF 정규화) · 홈 분리."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from . import settings as S


class GuardError(RuntimeError):
    """가드 거부. `reason` = 로그·경보에 쓰는 짧은 고정 코드(러너는 예외 메시지를 출력하지 않는다)."""

    def __init__(self, msg: str = "", reason: str = "guard") -> None:
        super().__init__(msg)
        self.reason = reason


def _norm(p) -> str:
    return os.path.normcase(os.path.abspath(str(p))).replace("\\", "/").rstrip("/")


def refuse_live_tree(path) -> None:
    live = _norm(S.LIVE_TREE)
    p = _norm(path)
    if p == live or p.startswith(live + "/"):
        raise GuardError(f"라이브 트리에서 실행 거부: {path}", "live_tree")


def check_home(home: Optional[Path] = None) -> Path:
    h = Path(home or S.home_dir())
    for o in S.other_homes():
        if _norm(h) == _norm(o):
            raise GuardError(f"홈 충돌: {h} = 다른 shadow 홈", "home_collision")
    return h


def _git(repo, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, shell=False)
    if r.returncode != 0:
        raise GuardError(f"git {' '.join(args)} 실패: {r.stderr.strip()[:200]}", "git_failed")
    return r.stdout.strip()


def git_head(repo) -> str:
    return _git(repo, "rev-parse", "HEAD")


def git_dirty(repo) -> bool:
    return _git(repo, "status", "--porcelain") != ""


def git_detached(repo) -> bool:
    r = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], cwd=str(repo), capture_output=True, text=True)
    if r.returncode == 0:
        return False
    if r.returncode == 1:
        return True
    raise GuardError(f"git symbolic-ref 실패: {r.stderr.strip()[:200]}", "git_failed")


def source_sha(rel: str, root: str = S.LIVE_RT) -> str:
    try:
        data = (Path(root) / rel).read_bytes()
    except OSError as e:                             # 라이브 원본 이름 바뀜·삭제·잠김 → 조용한 traceback 대신 가드 거부
        raise GuardError(f"라이브 원본 읽기 실패: {rel} ({type(e).__name__})", "source_unreadable") from None
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _sources() -> Dict[str, str]:
    return {rel: source_sha(rel) for rel in S.LIVE_SOURCES}


@dataclass(frozen=True)
class Frozen:
    code_sha: str
    rule_v: str
    frozen_at: str
    sources: Dict[str, str] = field(default_factory=dict)
    credit_lag_k: Optional[int] = None


def _valid_frozen(d) -> bool:
    if not isinstance(d, dict) or not all(isinstance(d.get(k), str) for k in ("code_sha", "rule_v", "frozen_at")):
        return False
    src = d.get("sources", {})
    if not isinstance(src, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in src.items()):
        return False
    k = d.get("credit_lag_k")
    return k is None or (isinstance(k, int) and not isinstance(k, bool))


def load_frozen(path: Optional[Path] = None) -> Frozen:
    p = Path(path or S.frozen_path())
    if not p.exists():
        raise GuardError("frozen.json 없음 — `--freeze` 먼저", "frozen_missing")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if not _valid_frozen(d):
            raise TypeError("frozen.json 필드 형식")
        return Frozen(**d)
    except (OSError, ValueError, TypeError) as e:     # 깨진 JSON·인코딩·필드 누락/초과/형식 → 가드 거부
        raise GuardError(f"frozen.json 읽기 실패({type(e).__name__}) — 다시 동결", "frozen_corrupt") from None


def write_frozen(repo, path: Optional[Path] = None) -> Frozen:
    refuse_live_tree(repo)
    check_home()
    if git_dirty(repo):
        raise GuardError("작업 트리가 깨끗하지 않다 — 동결 거부", "dirty")
    fr = Frozen(git_head(repo), S.RULE_V, datetime.now().isoformat(timespec="seconds"), _sources(), S.CREDIT_LAG_K)
    p = Path(path or S.frozen_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        with open(p.parent / "frozen_history.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(json.loads(p.read_text(encoding="utf-8")), ensure_ascii=False) + "\n")
    tmp = p.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(asdict(fr), ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return fr


def check_runtime(repo, fr: Frozen) -> str:
    refuse_live_tree(repo)
    check_home()
    if fr.rule_v != S.RULE_V:
        raise GuardError(f"rule_v 불일치 {fr.rule_v} ≠ {S.RULE_V}", "rule_v")
    if fr.credit_lag_k != S.CREDIT_LAG_K:
        raise GuardError("credit_lag_k 불일치 — 다시 동결", "credit_lag_k")
    head = git_head(repo)
    if head != fr.code_sha:
        raise GuardError(f"HEAD {head[:10]} ≠ 동결 code_sha {fr.code_sha[:10]}", "head_mismatch")
    if git_dirty(repo):
        raise GuardError("작업 트리가 깨끗하지 않다", "dirty")
    if not git_detached(repo):
        raise GuardError("브랜치 위에서 실행 거부 — detached 워크트리만", "not_detached")
    missing = sorted(set(S.LIVE_SOURCES) - set(fr.sources))
    extra = sorted(set(fr.sources) - set(S.LIVE_SOURCES))
    if missing or extra:
        raise GuardError(f"동결 원본 목록 불일치 — 누락 {missing} · 초과 {extra} — 다시 동결", "source_list")
    now = _sources()
    bad = [k for k, v in fr.sources.items() if now.get(k) != v]
    if bad:
        raise GuardError(f"라이브 원본 sha 불일치: {', '.join(bad)} — 다시 검토·동결", "source_sha")
    return head
