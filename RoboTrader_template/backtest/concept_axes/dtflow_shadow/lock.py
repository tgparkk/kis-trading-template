"""§3-4 · §5-2 잠금 — OS 잠금 파일(`msvcrt.locking`) + 파일에 PID·생성 시각.

- 잠금은 «프로세스가 쥐고 있는 동안만» 유효하다(OS 가 핸들 닫힘·프로세스 종료 때 푼다).
- 파일은 남아도 된다: 다음 실행이 OS 잠금을 얻으면 옛 PID 는 stale 로 보고 덮어쓴다(자동 해제).
- 본체·검색 팔·DART 적재가 같은 파일을 쓴다 ⇒ 두 번째 프로세스는 즉시 `LockBusy`.
- 잠금 바이트는 내용 뒤(오프셋 `_LOCK_OFFSET`)에 건다 — 다른 프로세스도 PID 줄은 읽을 수 있게.
- Windows 가 아니면(CI) `fcntl.flock` 으로 같은 의미를 낸다.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

_LOCK_OFFSET = 1_000_000

try:  # pragma: no cover - 플랫폼 분기
    import msvcrt

    def _try_lock(fh) -> bool:
        fh.seek(_LOCK_OFFSET)
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fh) -> None:
        fh.seek(_LOCK_OFFSET)
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
except ImportError:  # pragma: no cover
    import fcntl

    def _try_lock(fh) -> bool:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(fh) -> None:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass


class LockBusy(RuntimeError):
    """다른 «살아 있는» 프로세스가 잠금을 쥐고 있다."""


def read_holder(path: Path) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.readline().strip()
    except OSError:
        return "?"


class RunnerLock:
    """`with RunnerLock(path, owner="main") as lk:` — 못 얻으면 LockBusy. `lk.stale_from` = 덮어쓴 옛 줄."""

    def __init__(self, path: Path, owner: str = "") -> None:
        self.path = Path(path)
        self.owner = owner
        self.fh = None
        self.stale_from: Optional[str] = None

    def acquire(self) -> "RunnerLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+", encoding="utf-8")
        if not _try_lock(fh):
            fh.close()
            raise LockBusy(f"잠금 사용 중({read_holder(self.path)}) — 두 번째 프로세스는 즉시 종료")
        fh.seek(0)
        prev = fh.readline().strip()
        self.stale_from = prev or None           # OS 잠금을 얻었다 = 옛 소유자는 죽었다(stale)
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid={os.getpid()} owner={self.owner} created_at={datetime.now().isoformat(timespec='seconds')}\n")
        fh.flush()
        self.fh = fh
        return self

    def release(self) -> None:
        if self.fh is None:
            return
        _unlock(self.fh)
        self.fh.close()
        self.fh = None

    def __enter__(self) -> "RunnerLock":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()
