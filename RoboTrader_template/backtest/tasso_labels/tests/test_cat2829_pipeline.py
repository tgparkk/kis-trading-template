# -*- coding: utf-8 -*-
"""[28]·[29] 전수 수집 파이프라인 — 단위 테스트.

⚠️ 라이브 트리에서 실행 금지. 워크트리에서 이 파일로 한정해 돌린다:
    pytest backtest/tasso_labels/tests/test_cat2829_pipeline.py -v
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

TASSO = Path(__file__).resolve().parents[1]        # backtest/tasso_labels
HARVEST = TASSO / "harvest"
REPO = TASSO.parents[1]                            # RoboTrader_template (.gitignore 위치)


def _load(name):
    """harvest/ 는 패키지가 아니므로(=__init__.py 없음) 경로로 직접 로드한다."""
    path = HARVEST / (name + ".py")
    spec = importlib.util.spec_from_file_location("_tasso_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ignored(rel):
    """git check-ignore: 무시되면 exit 0, 아니면 1."""
    r = subprocess.run(["git", "check-ignore", "-q", rel], cwd=str(REPO))
    return r.returncode == 0


# ============================ Task 1 ============================

def test_paths_are_absolute_and_cwd_independent(tmp_path, monkeypatch):
    """🔑 지난 수집분 29건이 사라진 원인의 회귀 테스트.

    구 스크립트는 os.makedirs("posts2") 로 **cwd 상대** 경로에 썼다. 다른 cwd 에서
    돌리면 산출물이 엉뚱한 곳에 생기고 저장소에는 흔적이 남지 않는다.
    """
    before = _load("cat2829_common").POSTS_DIR
    monkeypatch.chdir(tmp_path)
    after = _load("cat2829_common").POSTS_DIR
    assert before == after, "cwd 를 바꾸니 출력 경로가 달라졌다"
    assert after.is_absolute()
    assert after.parent == HARVEST


@pytest.mark.parametrize("rel", [
    "backtest/tasso_labels/harvest/posts28/x.html",
    "backtest/tasso_labels/harvest/text28/x.txt",
    "backtest/tasso_labels/harvest/images28/x.png",
    "backtest/tasso_labels/harvest/claims_batches/b01.jsonl",
    "backtest/tasso_labels/harvest/claims_cat2829_quoted.csv",
])
def test_gitignore_blocks_copyrighted_artifacts(rel):
    """타인 저작물(원문 HTML·텍스트·이미지·인용 포함 원장)은 커밋되면 안 된다.

    ⚠️ 2026-08-05 실측: 조치 전에는 **다섯 개 전부 tracked** 였다.
       .gitignore:169 의 `!backtest/tasso_labels/harvest/*.csv` 가 quoted 판까지 되살린다.
    """
    assert _ignored(rel), rel + " 이 커밋 대상이다"


@pytest.mark.parametrize("rel", [
    "backtest/tasso_labels/harvest/claims_cat2829.csv",
    "backtest/tasso_labels/harvest/catlist_28_29.json",
    "backtest/tasso_labels/harvest/postmeta_28_29.json",
    "backtest/tasso_labels/harvest/verify_cat2829.log",
])
def test_gitignore_keeps_derived_evidence(rel):
    """🔑 반대 방향도 고정한다 — 파생 사실·검증 근거는 반드시 추적돼야 한다.

    ⚠️ 2026-08-05 실측: verify_cat2829.log 는 `*.log`(.gitignore:68,138) 에 삼켜져
       **IGNORED** 였다. 범용 패턴이 우리 산출물을 삼키는 6번째 사례다.
    이 방향을 안 고정하면 다음 사람이 "그냥 harvest/ 전체를 차단" 으로 되돌려도 안 잡힌다.
    """
    assert not _ignored(rel), rel + " 이 조용히 무시된다"
