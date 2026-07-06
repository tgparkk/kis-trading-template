"""pytest 실행 중 공유 파일 핸들러가 프로덕션 로그를 오염시키지 않는지 검증.

버그: `_get_shared_handlers()`가 날짜만으로 `trading_YYYYMMDD.log` 경로를 만들어
pytest 세션(다른 셸/세션 포함)이 프로덕션 `logs/trading_YYYYMMDD.log`에 append 함.

수정 후: pytest 하에서는 `test_trading_YYYYMMDD.log`로 분리되어야 함.
"""
import sys

import utils.logger as logger_mod


def test_shared_file_handler_isolated_under_pytest():
    # 싱글톤 강제 초기화 (신규 생성 유도)
    saved_file_handler = logger_mod._shared_file_handler
    saved_console_handler = logger_mod._shared_console_handler
    saved_file_path = logger_mod._shared_file_path

    logger_mod._shared_file_handler = None
    logger_mod._shared_console_handler = None
    logger_mod._shared_file_path = None

    created_handler = None
    try:
        # pytest 하에서 실행되므로 True 여야 함 (전제 조건)
        assert "pytest" in sys.modules

        file_handler, _console_handler = logger_mod._get_shared_handlers()
        created_handler = file_handler

        path = logger_mod._shared_file_path
        assert path is not None
        filename = path.replace("\\", "/").split("/")[-1]

        # pytest 하에서는 test_trading_*.log 여야 하고, bare trading_*.log 는 금지
        assert filename.startswith("test_trading_"), (
            f"pytest 하에서 공유 로그가 프로덕션 파일을 가리킴: {filename}"
        )
    finally:
        # 다른 테스트가 의존하는 공유 핸들러를 깨지 않도록 원복
        if created_handler is not None:
            try:
                created_handler.close()
            except Exception:
                pass
        logger_mod._shared_file_handler = saved_file_handler
        logger_mod._shared_console_handler = saved_console_handler
        logger_mod._shared_file_path = saved_file_path
