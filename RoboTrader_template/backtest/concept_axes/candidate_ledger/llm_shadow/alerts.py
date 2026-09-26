"""§3-4 경보 🔒 — 텔레그램 1통(런너가 직접 · 봇 프로세스 무관).

- 대상: 적재 실패 · 그날 채점 0행 · `model_mismatch` · exe 해시 불일치(·실행 거부).
- 토큰·chat_id = 라이브 트리 `config/key.ini` `[TELEGRAM]` 읽기만(출력·로그 금지).
- 🔒 본문에 점수·태그·모델 출력 금지 — 고정 문구 + 날짜 + 건수만.
"""
from __future__ import annotations

import configparser
from typing import Callable, Optional

from . import settings as S

PREFIX = "[kis-llm-shadow]"


def _telegram_conf() -> Optional[tuple]:
    cp = configparser.ConfigParser()
    try:
        cp.read(S.key_ini_path(), encoding="utf-8")
        tok, chat = cp.get("TELEGRAM", "token", fallback=""), cp.get("TELEGRAM", "chat_id", fallback="")
    except (configparser.Error, OSError):
        return None
    return (tok, chat) if tok and chat else None


def send_alert(text: str, dry_run: bool = False, poster: Optional[Callable] = None,
               log: Callable[[str], None] = print) -> bool:
    body = f"{PREFIX} {text}"[:1000]
    if dry_run:
        log(f"[경보·dry-run 미발송] {body}")
        return False
    conf = _telegram_conf()
    if conf is None:
        log("[경보] 텔레그램 설정 없음 — 발송 못 함")
        return False
    tok, chat = conf
    try:
        if poster is None:
            import requests
            poster = requests.post
        r = poster(f"https://api.telegram.org/bot{tok}/sendMessage", data={"chat_id": chat, "text": body}, timeout=10)
        ok = getattr(r, "status_code", 0) == 200
    except Exception as e:                   # 예외 문자열은 URL(토큰)을 담을 수 있어 싣지 않는다
        log(f"[경보] 발송 실패 {type(e).__name__}")
        return False
    log(f"[경보] 발송 {'ok' if ok else 'fail'}")
    return ok
