from pathlib import Path
from config.settings import (
    resolve_instance_id, resolve_config_dir, real_trading_table_name,
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
