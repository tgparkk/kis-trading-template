# -*- coding: utf-8 -*-
"""`daily_prices` OHLC 쓰기 «표면» 고정 — 가드 없는 쌍둥이가 되살아나지 않게.

사전등록: docs/prereg_2026-09-03_write_path_rawprice_upsert.md (D-3 · §6-22 · §4-4)

「가드는 살아 있는 호출자가 있는 함수가 아니라, 그 SQL 을 실행하는 «모든» 함수에
건다」 — (E′) 를 `save_daily_prices_batch` 에만 걸면 같은 파일의 `save_daily_price`
(호출자 0건)가 가드 없는 UPSERT 로 남는다. D-3 은 그 죽은 경로 셋을 제거했다:

  W4 `core/post_market_data_saver.save_daily_data`  (수정주가 100봉 — 규약이 반대다)
  W5 `utils/unified_data_loader.sync_file_to_db`
  W8 `db/repositories/price.save_daily_price`       (단건 UPSERT · 쌍둥이)

🔴 이 테스트는 「지금 안 불린다」가 아니라 «존재하지 않는다»를 고정한다.
   되살리려면 이 테스트를 같이 고쳐야 하고, 그때 규약을 다시 논의하게 된다.
🔑 잔재 검사는 «문자열»이 아니라 AST 로 한다 — 주석·docstring 의 기록(무엇을 왜
   지웠는가)까지 잡으면 그 기록을 지우게 되고, 그러면 다음 실행자가 이유를 모른다.
"""
import ast
import inspect
import re
from pathlib import Path

REMOVED_WRITE_PATHS = ("save_daily_price", "sync_file_to_db", "save_daily_data")
LIVE_DIRS = ("core", "bot", "framework", "api", "strategies",
             "collectors", "db", "runners", "signals", "utils", "tools")


def test_price_repository_has_exactly_one_daily_ohlc_write_statement():
    """price.py 안의 `INSERT INTO daily_prices` 는 상수 정의 한 곳뿐이어야 한다."""
    from db.repositories import price

    src = inspect.getsource(price)
    # 문자열 상수 정의(_DAILY_INSERT_HEAD_SQL) 한 곳에서만 나온다.
    assert len(re.findall(r"INSERT INTO daily_prices\n", src)) == 1
    # 덮어쓰는 문장도 한 개(DAILY_UPSERT_SQL)뿐이다.
    assert len(re.findall(r"DO UPDATE SET", src)) == 1


def test_w8_single_row_upsert_is_gone():
    from db.repositories.price import PriceRepository

    assert not hasattr(PriceRepository, "save_daily_price")
    assert hasattr(PriceRepository, "save_daily_prices_batch")


def test_w5_file_cache_sync_write_path_is_gone():
    from utils.unified_data_loader import UnifiedDataLoader

    assert not hasattr(UnifiedDataLoader, "sync_file_to_db")


def test_w4_post_market_daily_write_path_is_gone():
    from core import post_market_data_saver as pmds

    assert not hasattr(pmds.PostMarketDataSaver, "save_daily_data")
    # 분봉 텍스트 덤프와 그 트리거(realtime_updater → save_all_data)는 «살아 있다».
    assert hasattr(pmds.PostMarketDataSaver, "save_all_data")
    assert hasattr(pmds.PostMarketDataSaver, "save_minute_data_to_file")

    # 수정주가 피드도 가격 저장소 핸들도 이 모듈 이름공간에 없다(= 되살릴 재료가 없다).
    assert not hasattr(pmds, "get_inquire_daily_itemchartprice")
    assert not hasattr(pmds, "PriceRepository")


def _offenders(py: Path):
    """그 파일에 제거된 이름의 «정의»나 «호출»이 있으면 (kind, name) 목록으로."""
    try:
        tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:  # pragma: no cover - 운영 트리에 파싱 불가 파일은 없다
        return []

    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in REMOVED_WRITE_PATHS:
                found.append(("def", node.name))
        elif isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name in REMOVED_WRITE_PATHS:
                found.append(("call", name))
    return found


def test_removed_paths_have_no_definition_or_caller_left():
    """운영 디렉토리 전수 — 정의도 호출도 0이어야 한다(잔재 = 런타임 AttributeError)."""
    repo = Path(__file__).resolve().parent.parent

    hits = []
    for d in LIVE_DIRS:
        for py in (repo / d).rglob("*.py"):
            for kind, name in _offenders(py):
                hits.append(f"{py.relative_to(repo)}: {kind} {name}")
    assert hits == [], f"제거된 쓰기 경로의 잔재: {hits}"


def test_the_scan_actually_detects_a_resurrected_path(tmp_path):
    """이빨 확인 — 위 검사가 진짜로 판별하는지 가짜 파일로 증명한다."""
    fake = tmp_path / "resurrected.py"
    fake.write_text(
        "class X:\n"
        "    def save_daily_price(self):\n"
        "        pass\n"
        "\n"
        "def go(repo):\n"
        "    repo.sync_file_to_db('001210', '20260903')\n",
        encoding="utf-8",
    )
    kinds = sorted(_offenders(fake))
    assert kinds == [("call", "sync_file_to_db"), ("def", "save_daily_price")]
