"""
데이터베이스 설정

2026-08-17: 기본 DB 를 'robotrader' → 'kis_template' 으로 전환.
  'robotrader' 는 2026-07-10 동결된 «레거시» DB 다(형제봇 중단). 라이브는 .env 에
  TIMESCALE_DB=kis_template 이 있어 무해했지만, .env 가 없는 환경(워크트리·CI·
  clean checkout)에서는 죽은 DB 를 조용히 가리켰다. 비활성 코드가 아니라
  «환경 의존»이라 더 위험하다. TIMESCALE_DB 로 여전히 덮어쓸 수 있다.
  주의: 'robotrader' 는 DB명이자 롤명이기도 하다 — user 기본값은 롤명이므로 그대로 둔다.
"""
import os
from dataclasses import dataclass

@dataclass
class DatabaseConfig:
    host: str = 'localhost'
    port: int = 5432
    database: str = 'kis_template'
    user: str = 'robotrader'          # ← 롤명(DB명 아님). 변경 대상 아님.
    password: str = '1234'

    @classmethod
    def from_env(cls):
        return cls(
            host=os.getenv('TIMESCALE_HOST', 'localhost'),
            port=int(os.getenv('TIMESCALE_PORT', 5432)),
            database=os.getenv('TIMESCALE_DB', 'kis_template'),
            user=os.getenv('TIMESCALE_USER', 'robotrader'),
            password=os.getenv('TIMESCALE_PASSWORD', '1234')
        )
