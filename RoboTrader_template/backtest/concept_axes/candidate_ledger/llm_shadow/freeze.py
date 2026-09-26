"""§5-1 · §5-2 무결성 — 동결 상수는 git «밖» `%LOCALAPPDATA%/kis-llm-shadow/frozen.json`.

🔑 선언된 이탈(관리자 승인): 사전등록은 「코드 커밋 sha 를 런너 상수로」라 했지만, 상수를 커밋에 넣으면
   그 커밋의 sha 가 다시 바뀐다(자기 참조). 그래서 코드 커밋 «뒤» `--freeze` 가 아래 값을 파일로 동결한다.
   {code_sha, exe_sha256, cli_version, prompt_sha256, prompt_sha256_search, batch_timeout_s, frozen_at}
   `--freeze` 는 `git status --porcelain` 이 빈 상태에서만 쓴다 · 덮어쓰기 전 옛 값은 `frozen_history.jsonl` 에 append.
런너 거부 조건: 라이브 트리 경로 · HEAD ≠ code_sha · 더러운 워크트리 · exe sha ≠ 동결 · CLI 버전 ≠ 동결 · 프롬프트 sha ≠ 동결.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from . import prompt_v1 as P
from . import settings as S


class GuardError(RuntimeError):
    """실행 거부(§5-1) — 경보 대상."""


@dataclass(frozen=True)
class Frozen:
    code_sha: str
    exe_sha256: str
    cli_version: str
    prompt_sha256: str
    prompt_sha256_search: str
    batch_timeout_s: int
    frozen_at: str


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cli_version(pkg_json: Optional[Path] = None) -> str:
    p = pkg_json or S.cli_package_json()
    with open(p, encoding="utf-8") as f:
        return str(json.load(f)["version"])


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, shell=False)
    if r.returncode != 0:
        raise GuardError(f"git {' '.join(args)} 실패(rc={r.returncode})")
    return r.stdout


def git_head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()


def git_dirty(repo: Path) -> bool:
    return bool(_git(repo, "status", "--porcelain").strip())


def refuse_live_tree(path: Path) -> None:
    """🔴 라이브 트리에서 실행 금지(§13-5)."""
    p = os.path.normcase(os.path.abspath(str(path))).replace("\\", "/")
    live = os.path.normcase(os.path.abspath(S.LIVE_TREE)).replace("\\", "/")
    if p == live or p.startswith(live.rstrip("/") + "/"):
        raise GuardError(f"라이브 트리({S.LIVE_TREE})에서 실행 금지 — 전용 워크트리에서 실행")


def load_frozen(path: Optional[Path] = None) -> Frozen:
    p = path or S.frozen_path()
    if not Path(p).exists():
        raise GuardError(f"동결 파일 없음({p}) — 코드 커밋 뒤 `--freeze` 먼저")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return Frozen(**{k: d[k] for k in Frozen.__dataclass_fields__})


def write_frozen(repo: Path, batch_timeout_s: int, exe: Optional[Path] = None,
                 pkg_json: Optional[Path] = None, path: Optional[Path] = None) -> Frozen:
    """코드 커밋 «뒤» 1회. 워크트리가 깨끗하지 않으면 거부."""
    refuse_live_tree(repo)
    if git_dirty(repo):
        raise GuardError("워크트리가 깨끗하지 않다(git status --porcelain) — 동결 거부")
    P.verify_against_prereg()
    exe = exe or S.exe_path()
    fr = Frozen(code_sha=git_head(repo), exe_sha256=file_sha256(exe), cli_version=cli_version(pkg_json),
                prompt_sha256=P.PROMPT_SHA256, prompt_sha256_search=P.PROMPT_SHA256_SEARCH,
                batch_timeout_s=int(batch_timeout_s), frozen_at=datetime.now().isoformat(timespec="seconds"))
    p = Path(path or S.frozen_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        with open(p.parent / "frozen_history.jsonl", "a", encoding="utf-8") as f:
            f.write(p.read_text(encoding="utf-8").replace("\n", " ").strip() + "\n")
    tmp = p.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(fr.__dict__, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return fr


def check_runtime(repo: Path, fr: Frozen, exe: Optional[Path] = None,
                  pkg_json: Optional[Path] = None) -> Dict[str, str]:
    """§5-1 실행 조건 전부. 하나라도 어긋나면 GuardError(경보 + 거부)."""
    refuse_live_tree(repo)
    P.verify_against_prereg()
    if P.PROMPT_SHA256 != fr.prompt_sha256 or P.PROMPT_SHA256_SEARCH != fr.prompt_sha256_search:
        raise GuardError("prompt_sha256 ≠ 동결 값 — 실행 거부")
    head = git_head(repo)
    if head != fr.code_sha:
        raise GuardError(f"HEAD {head[:12]} ≠ 동결 code_sha {fr.code_sha[:12]} — 실행 거부")
    if git_dirty(repo):
        raise GuardError("워크트리가 깨끗하지 않다 — 실행 거부")
    check_exe(fr, exe)
    ver = cli_version(pkg_json)
    if ver != fr.cli_version:
        raise GuardError(f"CLI 버전 {ver} ≠ 동결 {fr.cli_version} — 실행 거부")
    return {"code_sha": head, "cli_version": ver}


def check_exe(fr: Frozen, exe: Optional[Path] = None) -> str:
    """호출마다: exe sha256 을 다시 재고 동결 값과 다르면 거부(§5-2)."""
    got = file_sha256(exe or S.exe_path())
    if got != fr.exe_sha256:
        raise GuardError("exe sha256 ≠ 동결 값 — 실행 거부(CLI 가 바뀌었다)")
    return got
