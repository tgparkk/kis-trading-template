"""
데이터베이스 설정
"""
import os
from dataclasses import dataclass

@dataclass
class DatabaseConfig:
    host: str = 'localhost'
    port: int = 5432
    database: str = 'robotrader'
    user: str = 'robotrader'
    password: str = 'robotrader_secure_pw_2024'

    @classmethod
    def from_env(cls):
        return cls(
            host=os.getenv('TIMESCALE_HOST', 'localhost'),
            port=int(os.getenv('TIMESCALE_PORT', 5432)),
            database=os.getenv('TIMESCALE_DB', 'robotrader'),
            user=os.getenv('TIMESCALE_USER', 'robotrader'),
            password=os.getenv('TIMESCALE_PASSWORD', 'robotrader_secure_pw_2024')
        )
