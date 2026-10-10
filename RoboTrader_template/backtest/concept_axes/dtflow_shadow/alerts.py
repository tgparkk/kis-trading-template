"""텔레그램 경보 — 태쏘 shadow `alerts.py` 형태. key.ini [TELEGRAM] token·chat_id 를 읽기만 · 한 실행 1통 · 본문 = D·status·건수."""
from __future__ import annotations

import configparser
from datetime import date
from typing import Callable, Optional, Tuple

from . import settings as S

PREFIX = "[kis-dtflow-shadow]"


def body(D: date, status: str, n: Optional[int] = None) -> str:
    return f"D={D.isoformat()} status={status}" + (f" n={n}" if n is not None else "")


def _conf() -> Optional[Tuple[str, str]]:
    try:
        cp = configparser.ConfigParser()
        cp.read(str(S.key_ini_path()), encoding="utf-8")
        tok = cp.get("TELEGRAM", "token", fallback="").strip()
        chat = cp.get("TELEGRAM", "chat_id", fallback="").strip()
        return (tok, chat) if tok and chat else None
    except (configparser.Error, OSError):
        return None


def send(text: str, dry_run: bool = False, poster: Optional[Callable] = None, log: Callable = print) -> bool:
    msg = f"{PREFIX} {text}"[:1000]
    if dry_run:
        log(f"(dry-run 경보) {msg}")
        return True
    conf = _conf()
    if conf is None:
        log("경보 설정 없음 — 로그만")
        return False
    try:
        if poster is None:
            import requests
            poster = requests.post
        r = poster(f"https://api.telegram.org/bot{conf[0]}/sendMessage", data={"chat_id": conf[1], "text": msg}, timeout=10)
        return getattr(r, "status_code", 0) == 200
    except Exception as e:  # noqa: BLE001 — URL 에 토큰이 있으므로 예외 이름만
        log(f"경보 실패: {type(e).__name__}")
        return False
