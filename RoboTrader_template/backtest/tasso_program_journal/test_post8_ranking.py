# -*- coding: utf-8 -*-
"""`RNK-` 축 post8 검증 모드 회귀 시험 — `test_post7_ranking.py`(R1~R5)·`test_post6_ranking.py` 규약 승계.

🔑 계열 규칙: *캡처 장치도 가드다 — 가드를 시험하지 않으면 그것도 장식이다.* 새 문턱·새 정의 0건.

  R1  `POST8_CODES` 10건 ↔ `INTAKE_2026-09-18_post8.md` §1 표 **축자 일치**
  R2  계열 기존 코드(post1~7)와 **충돌 0**
  R3  🔴 **이중 매핑 대조** — `run_sector.POST8_NEW`(7) ⊂ `POST8_CODES` 이고 코드가 같다 ·
      `run_wrc_post8.CODES8`(10) 과도 전건 일치 (post7 `run_sector.py` `post7_context` 방식)
  R4  `build_codes8()` 이 `POST8_CODES` 를 전부 담고 **post7 이하 매핑을 덮어쓰지 않는다**
  R5  부수 집합(`POST8_REENTRY`·`POST8_REENTRY_ITEM`·`POST8_PRIOR_CYCLE`·`POST8_NONE_NEW`·`POST8_APPROX`)의
      이름이 전부 `POST8_CODES` 안에 있고, `POST8_FOLLOWUP` 은 계열 기존 코드에 있다
  S1  🔴 **스테이지 추가는 «순수 덧붙임»** — `post6_main`·`post7_main` 과 공유 헬퍼 본문 md5 가 `HEAD` 블롭과 같다
      (바뀐 함수는 `main` 하나 · `choices` 에 `post8` 추가 + 분기 1개)
  S2  원장 분모 — post8 `exact` 4(우리로·JW신약·액스비스·우리기술) · `approx` 2 · `none` 4
  S3  `RESULTS_RANKING_POST8_NUMBERS.md` 의무 줄(`D-3`·`D-5`·`D-8`·`D-9` ①~⑤ · 라이브 금지 · 「새 정보 없음」) ·
      등급 이름 0 · D-9 ① = `ranking_post8/read_stamp.json`
  S4  post7 이하 산출물(`RESULTS_RANKING_POST7/POST6/TRAIN_NUMBERS.md`)이 `HEAD` 블롭과 **내용 동일**

실행: `python -m pytest test_post8_ranking.py -q -p no:cacheprovider` (DB 접속 0 · 라이브 import 0)
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

import run_ranking as R

BASE = Path(__file__).resolve().parent
INTAKE = "INTAKE_2026-09-18_post8.md"
NUMBERS = BASE / "RESULTS_RANKING_POST8_NUMBERS.md"
CODE_RE = re.compile(r"[0-9][0-9A-Z]{5}")


def _intake_table() -> dict:
    out = {}
    for ln in (BASE / INTAKE).read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in ln.split("|")]
        if len(c) >= 5 and c[1].isdigit():
            m = CODE_RE.search(c[3] or "")
            if m:
                out[c[2]] = m.group(0)
    return out


def _head(rel: str) -> str:
    r = subprocess.run(["git", "show", f"HEAD:./{rel}"], cwd=str(BASE), capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout.decode("utf-8")


def _bodies(src: str) -> dict:
    t = ast.parse(src)
    return {n.name: hashlib.md5(ast.get_source_segment(src, n).encode("utf-8")).hexdigest()
            for n in t.body if isinstance(n, ast.FunctionDef)}


def test_R1_codes_match_intake_verbatim():
    tbl = _intake_table()
    assert len(R.POST8_CODES) == 10
    assert {k: tbl.get(k) for k in R.POST8_CODES} == R.POST8_CODES


def test_R2_no_clash_with_series_codes():
    prior, _ = R.build_codes7()
    clash = {k: (prior[k], v) for k, v in R.POST8_CODES.items() if k in prior and prior[k] != v}
    assert not clash
    assert R.POST8_CODES["우리기술"] != prior["우리기술투자"]           # 이름이 비슷한 다른 종목


def test_R3_dual_mapping_sector_and_wrc():
    import run_sector as S
    import run_wrc_post8 as W8
    sec = {nm: c for nm, c, _reg in S.POST8_NEW}
    assert len(sec) == 7
    assert {k: R.POST8_CODES.get(k) for k in sec} == sec
    assert W8.CODES8 == R.POST8_CODES


def test_R4_build_codes8_superset_without_overwrite():
    c8, _ = R.build_codes8()
    prior, _ = R.build_codes7()
    assert all(c8.get(k) == v for k, v in R.POST8_CODES.items())
    assert all(c8.get(k) == v for k, v in prior.items())


def test_R5_side_sets_are_named_in_mapping():
    names = set(R.POST8_CODES)
    for s in (R.POST8_REENTRY, R.POST8_REENTRY_ITEM, set(R.POST8_PRIOR_CYCLE), set(R.POST8_NONE_NEW),
              set(R.POST8_APPROX), set(R.POST8_PRIOR_CYCLE_NOTE)):
        assert set(s) <= names, s
    prior, _ = R.build_codes7()
    assert all(n in prior for n in R.POST8_FOLLOWUP)
    assert R.POST8_REENTRY_ITEM == {"우리로"} and not (R.POST8_REENTRY & R.POST8_REENTRY_ITEM)


def test_S1_pure_addition_function_bodies_unchanged():
    old = _bodies(_head("run_ranking.py"))
    new = _bodies((BASE / "run_ranking.py").read_text(encoding="utf-8"))
    changed = sorted(k for k in old if old[k] != new.get(k))
    assert changed == ["main"], changed
    for k in ("post6_main", "post7_main", "build_codes", "build_codes7", "measure", "null_pctl",
              "load", "load_ledger", "exact_items", "approx_items", "a5_calibration"):
        assert old[k] == new[k], k
    added = sorted(k for k in new if k not in old)
    assert "post8_main" in added and "build_codes8" in added
    src = (BASE / "run_ranking.py").read_text(encoding="utf-8")
    assert 'choices=["train", "post6", "post7", "post8"]' in src
    assert 'if a.stage == "post8":' in src


def test_S1b_constants_are_the_intake_values():
    assert R.DB_UPTO_POST8 == "2026-09-18" and R.POST8_LOG_NO == "224416253270"
    assert R.POST8_POST_DATE == "2026-09-18"
    assert R.POST8_NONE_NEW == ("원익",)
    assert R.POST8_APPROX == ("헥토파이낸셜", "코데즈컴바인")
    assert R.POST8_FOLLOWUP == ("빛과전자", "로보티즈", "범한퓨얼셀")
    assert R.POST8_PUB_A1[7]["m"] == 24.5 and R.POST8_PUB_A1[6]["m"] == 15.5


def test_S2_ledger_denominators():
    rows = R.load_ledger("post8")
    codes, _ = R.build_codes8()
    items, post_idx = R.exact_items(rows, codes)
    p8 = post_idx[R.POST8_LOG_NO]
    ex = [it for it in items if it["post"] == p8]
    ap = [it for it in R.approx_items(rows, codes, post_idx) if it["post"] == p8]
    none = [r for r in rows if r["post_log_no"] == R.POST8_LOG_NO and r["reg_date_precision"] == "none"]
    assert sorted(it["name"] for it in ex) == sorted(["우리로", "JW신약", "액스비스", "우리기술"])
    assert sorted(it["name"] for it in ap) == sorted(R.POST8_APPROX) and all(not it["reg"] for it in ap)
    assert sorted(r["stock_name"] for r in none) == sorted(R.POST8_NONE_NEW + R.POST8_FOLLOWUP)


def test_S3_duty_lines_and_no_grade_names():
    t = NUMBERS.read_text(encoding="utf-8")
    for s in ("D-9 ① 쿼리 실행 시각(KST)", "D-9 ② 창 구간 `max(daily_prices.updated_at)`",
              "봉은 D+1(2026-09-21) sweep 이후 읽음", "창 구간 `min(updated_at)` =", "혼합 빈티지」",
              "`approx` 포함 시 최소 n 이 차는 축: **없음**", "| 갈래 | **n** | 최소 n(3) | **답**(`RNK-P1` AND) | 비고 |",
              "| `1.0.42` | 10 | 1 |", "라이브 채택 대상이 아니다", "새 정보 없음 = `REG-M4` 재진술",
              "「우리로 제외」 | 3 |", "인쇄만 — 갈래로 세지 않는다", "이번 회차 재판정", "창 종료 `2026-09-18` = 발행 당일"):
        assert s in t, s
    for g in ("GT-A", "GT-B", "GT-C", "GT-D", "GT-E", "GT-F", "충족·참고용", "낡음(재실행 금지)", "[갈래 의존]"):
        assert g not in t, g


def test_S3b_d9_first_read_matches_stamp():
    st = json.loads((BASE / "ranking_post8" / "read_stamp.json").read_text(encoding="utf-8"))
    m = re.search(r"\| D-9 ① 쿼리 실행 시각\(KST\) \| \*\*([0-9: -]+)\*\*", NUMBERS.read_text(encoding="utf-8"))
    assert m and m.group(1) == st["first_read_kst"]


def test_S3c_mixed_vintage_lines_cover_pd27_table():
    t = NUMBERS.read_text(encoding="utf-8")
    assert t.count("은 제도 경계 2026-09-14 를 걸친다") == len(R.POST8_PD27_CROSS) + 1   # + 적재 창 1줄


def test_S4_prior_outputs_untouched_vs_head():
    for rel in ("RESULTS_RANKING_POST7_NUMBERS.md", "RESULTS_RANKING_POST6_NUMBERS.md",
                "RESULTS_RANKING_TRAIN_NUMBERS.md", "RESULTS_RANKING_POST7.md", "PREREG_RANKING.md",
                "FREEZE_RANKING_2026-08-31.md"):
        wt = (BASE / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
        assert wt == _head(rel).replace("\r\n", "\n"), rel
