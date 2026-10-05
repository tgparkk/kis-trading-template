"""RoboTrader_template/*.bat 줄바꿈 가드.

cmd.exe 는 LF 만 쓴 UTF-8 배치 파일(한글 주석 포함)을 파싱하지 못한다
(exit 255 · 파이썬 미실행 · 텔레그램 경보 없음). 비ASCII 바이트가 있는 .bat 는 CRLF 라야 한다.
"""
import subprocess
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent.parent


def _tracked_bat_files():
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.bat"],
            cwd=TEMPLATE_DIR, capture_output=True, check=True,
        ).stdout.decode("utf-8")
        files = [TEMPLATE_DIR / p for p in out.split("\0") if p and "/" not in p]
        if files:
            return files
    except (OSError, subprocess.CalledProcessError):
        pass
    return sorted(TEMPLATE_DIR.glob("*.bat"))


def find_bare_lf(data: bytes) -> bool:
    """비ASCII 바이트가 있고 CR 앞에 오지 않은 LF 가 있으면 True."""
    if all(b < 0x80 for b in data):
        return False
    return data.replace(b"\r\n", b"").count(b"\n") > 0


def test_non_ascii_bat_files_have_no_bare_lf():
    for path in _tracked_bat_files():
        assert not find_bare_lf(path.read_bytes()), (
            f"{path.name}: 비ASCII(한글) 주석이 있는데 LF 단독 줄바꿈이 있다. "
            "cmd.exe 는 LF 만 쓴 UTF-8 배치 파일을 파싱하지 못한다 "
            "(exit 255 · 파이썬 미실행 · 텔레그램 경보 없음). CRLF 로 저장할 것."
        )
