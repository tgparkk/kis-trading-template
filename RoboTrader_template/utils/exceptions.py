"""프로젝트 공용 예외.

LiveStartupAbort: 실전 기동을 «중단»해야 하는 상태(잔고 조회 실패·계좌-DB
불일치·미체결 취소 실패 등). 2026-08-14 P0 스펙 결정 5·6 — 실전 기동
경로에는 「경고 후 계속」이 존재하지 않는다. 페이퍼 경로에서는 raise 금지.
"""


class LiveStartupAbort(Exception):
    def __init__(self, reason: str, details: str = ""):
        self.reason = reason
        self.details = details
        super().__init__(f"{reason} | {details}" if details else reason)
