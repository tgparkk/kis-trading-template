"""`daily_prices` 유니버스 술어 — **지수 행을 종목으로 세지 않기 위한 공용 필터**. (연구 전용)

🔴 왜 필요한가 — `kis_template.daily_prices` 에는 종목이 아닌 행이 섞여 있다:

    stock_code   범위                     성격
    ----------   ----------------------   ------------------------------------------
    KOSPI        2021-01-04 ~ (1,367행)   close·volume 이 거대, market_cap/trading_value NULL
    KS11 / KQ11  2024-01-02 ~ 2026-07-08  동상 (601행씩)
    KOSDAQ       2026-06-01 ~ (43행)      동상

작성 주체는 `core/regime/index_refresh.py` -> `db/repositories/price.py` (라이브 국면 판정용).
지수 라인 자체는 정당한 데이터다. 문제는 **소비자가 이 행을 종목으로 취급**하는 것이다.

실측(2026-08-03, kis_template 전 구간):
    SUM(close*volume) 상위 50 안에 **KOSPI 1위 · KS11 5위 · KQ11 6위** 가 들어간다.
    즉 「거래대금 상위 N 유니버스」 백테스트는 top-50 중 3자리를 지수에 내주고 있었고,
    거래대금 랭크를 진입 우선순위로 쓰는 코드에서는 **지수가 항상 1순위**였다.

🔑 하드코딩 이름 목록(`NOT IN ('KOSPI','KS11',...)`)으로 막지 말 것.
   지수가 하나 더 추가되면 같은 결함이 그대로 재발한다. 실제로 재발했다 —
   `KOSPI` 만 거르던 코드는 2024년 `KS11`/`KQ11` 추가와 2026-06 `KOSDAQ` 추가에
   전부 뚫렸고, `KS11`/`KQ11` 만 거르던 코드는 `KOSPI`·`KOSDAQ` 에 뚫렸다.
   그래서 여기서는 **KRX 종목코드의 형식**이라는 구조적 술어로 막는다.

--------------------------------------------------------------------------------
어느 술어를 쓸 것인가
--------------------------------------------------------------------------------
`STOCK_CODE_RE` — KRX 단축코드 형식 = **숫자 5자리 + 영숫자 1자리**.
    포함: `005930`(보통주) · `00088K`·`37550L`(신형우선주) 등 실제 상장 종목 전부.
    제외: `KOSPI`(5자) · `KOSDAQ`(6자지만 앞 5자가 문자) · `KS11`·`KQ11`(4자).
    -> **기본값**. 「거래 가능한 종목이면 다 넣는다」는 의도의 호출부에 쓴다.

`COMMON_STOCK_CODE_RE` — 숫자 6자리만. 우선주·변형코드까지 뺀다.
    -> 「보통주만」을 명시적으로 원하는 호출부에만 쓴다
       (예: `scripts/book_param_multiverse.py:_DAILY_CODE_RE`).

⚠️ 우선주 코드 주의: `daily_prices` 의 비-6자리-숫자 종목코드 10종
   (`00088K` `00104K` `00279K` `00680K` `02826K` `03473K` `28513K` `33626K`
    `37550K` `37550L`)은 **진짜 상장 종목**이며, 마지막 행이 전부 2024-02-29 다.
   이는 상장폐지가 아니라 **과거 백필(strategy_analysis 유래) 종료 경계**다.
   따라서 「종목이 아니다」라고 판단해 버리면 안 된다 -> 기본값이 `STOCK_CODE_RE` 인 이유.

--------------------------------------------------------------------------------
🔴 배치 규칙
--------------------------------------------------------------------------------
이 모듈은 `lib/` = **연구/테스트 지원** 패키지에 둔다 (CLAUDE.md 라우팅 §운영 vs 연구).
라이브 디렉토리(`core/` `bot/` `framework/` `api/` `strategies/` `collectors/`
`db/` `runners/` `signals/` `utils/` `tools/`)에서 **import 하지 말 것.**
라이브 쪽 동종 결함(`db/repositories/price.py:get_universe_snapshot`)은
장 마감 후 라이브 경로 안에서 별도로 처리한다.
"""
from __future__ import annotations

import re
from typing import Iterable, List

# KRX 단축코드: 숫자 5자리 + 영숫자 1자리 (보통주 `005930`, 신형우선주 `00088K` 포함)
STOCK_CODE_RE = r"^[0-9]{5}[0-9A-Z]$"

# 보통주만: 숫자 6자리
COMMON_STOCK_CODE_RE = r"^[0-9]{6}$"

# SQL(POSIX regex) 조각. WHERE 절에 그대로 붙여 쓴다.
#   cur.execute(f"SELECT ... FROM daily_prices WHERE {SQL_STOCK_ONLY} AND ...")
# ⚠️ `%` 를 포함하지 않으므로 psycopg2 파라미터 바인딩과 함께 써도 이스케이프가 필요 없다.
# ⚠️ 반대로 이 상수를 f-string/`.format()` **템플릿 리터럴 안에** 직접 적지 말 것 —
#    `{5}` 가 치환 필드로 해석된다. 변수로 끼워넣는 것은 안전하다.
SQL_STOCK_ONLY = "stock_code ~ '^[0-9]{5}[0-9A-Z]$'"
SQL_COMMON_STOCK_ONLY = "stock_code ~ '^[0-9]{6}$'"

_STOCK = re.compile(STOCK_CODE_RE)
_COMMON = re.compile(COMMON_STOCK_CODE_RE)


def sql_stock_only(column: str = "stock_code") -> str:
    """컬럼명이 `stock_code` 가 아니거나 별칭이 붙은 쿼리용 SQL 조각."""
    return f"{column} ~ '{STOCK_CODE_RE}'"


def is_stock(code: str) -> bool:
    """KRX 종목코드 형식인가 (지수 행 배제). 우선주 포함."""
    return bool(code) and _STOCK.match(code) is not None


def is_common_stock(code: str) -> bool:
    """숫자 6자리 보통주인가. 우선주·변형코드도 제외한다."""
    return bool(code) and _COMMON.match(code) is not None


def filter_stock_codes(codes: Iterable[str]) -> List[str]:
    """코드 시퀀스에서 지수 행을 제거한다 (순서 보존)."""
    return [c for c in codes if is_stock(c)]
