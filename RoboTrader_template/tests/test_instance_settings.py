from pathlib import Path
from config.settings import (
    resolve_instance_id, resolve_config_dir, real_trading_table_name,
    token_file_name, log_dir_name,
)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

def test_instance_id_default_when_unset():
    assert resolve_instance_id({}) == "default"
    assert resolve_instance_id({"KIS_INSTANCE_DIR": ""}) == "default"

def test_instance_id_from_dir_basename_normalized():
    assert resolve_instance_id({"KIS_INSTANCE_DIR": "instances/rs_leader"}) == "rs_leader"
    assert resolve_instance_id({"KIS_INSTANCE_DIR": "instances/Book-MA5"}) == "book_ma5"

def test_config_dir_default_is_config_folder():
    assert resolve_config_dir({}) == CONFIG_DIR

def test_config_dir_override():
    assert resolve_config_dir({"KIS_INSTANCE_DIR": "instances/rs_leader"}) == Path("instances/rs_leader")

def test_real_table_name():
    assert real_trading_table_name("default") == "real_trading_records"
    assert real_trading_table_name("rs_leader") == "real_trading_rs_leader"


def test_instance_id_rejects_reserved_default():
    import pytest
    with pytest.raises(ValueError):
        resolve_instance_id({"KIS_INSTANCE_DIR": "instances/default"})


def test_instance_id_rejects_empty_normalization():
    import pytest
    with pytest.raises(ValueError):
        resolve_instance_id({"KIS_INSTANCE_DIR": "instances/!!!"})


def test_token_file_name():
    # 기본은 기존과 동일(하위호환), 인스턴스는 분리
    assert token_file_name("default") == "token_info.json"
    assert token_file_name("rs_leader") == "token_info_rs_leader.json"


def test_log_dir_name():
    assert log_dir_name("default") == "logs"
    assert log_dir_name("rs_leader") == "logs/rs_leader"
