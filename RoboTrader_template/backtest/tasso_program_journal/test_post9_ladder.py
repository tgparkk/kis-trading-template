# -*- coding: utf-8 -*-
"""`run_ladder_tranche_post9.py` 가드 시험 (post8 판 구조 승계 · 짧게).

  P1  동결 상수 불변 · END/발행 09-23 · 분모 5/5
  P2  `ITEMS` = post8 판 32건 + post9 5건 · post9 5건 = 원장(30aed89) `exact` 행의 (종목, 등록일, fill_n) · 후속 1건 부재
  N1  대칭 — 사본 한 칸을 흔들면 P2 비교가 잡는다
  P3  상류 재사용 — 통계 핵·가드·`build_rows`·창 헬퍼가 «그 객체»
  P4  `read_stamp` — 같은 지문 = 재사용 · 파일 byte 불변 / 지문 한 글자 차이 = 새 시각
  P5  의무 인쇄 줄 — 창 종료·`max(date)`·§0-1 라이브 금지 문언(PREREG_POST9 `:39`·`:41` 축자)·D-9 ①~⑤·D-7·D-1·D-3·
      `P9-공통독법`「답 = 판정」· D-5 표 전 행 세 쪽(post8 A-B2 교훈) · 등급 이름 0
  P6  판정값 스냅샷
  R1  상류 파일·post8 산출물이 `30aed89` 블롭과 byte 동일 + 대칭(그 ref 에 post9 스크립트 없음)
  R2  재실행 byte 동일(별 프로세스 · 스탬프는 임시 사본 — 지문이 바뀌면 skip: 다음 sweep 뒤 한계)
  R3  위생 — import 허용 목록 · DB 쓰기 0 · adj_factor 산술 0

실행: `python -m pytest test_post9_ladder.py -q -p no:cacheprovider` (R2 만 DB SELECT · 나머지 DB 0)
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import run_ladder_tranche as LAD
import run_ladder_tranche_post6 as P6
import run_ladder_tranche_post7 as P7
import run_ladder_tranche_post8 as P8
import run_ladder_tranche_post9 as P9

BASE = Path(__file__).resolve().parent
NUMBERS9 = BASE / "RESULTS_LADDER_TRANCHE_POST9_NUMBERS.md"
STAMP9 = BASE / "ladder_post9" / "read_stamp.json"
BASE_REF = "30aed89"
LOG9 = "224421214462"
GRADE_NAMES = ["충족·참고용", "조건 미달", "낡음(재실행 금지)", "GT-A", "GT-B", "GT-C", "GT-D", "GT-E", "GT-F"]


def _t9():
    assert NUMBERS9.exists(), "run_ladder_tranche_post9.py 를 먼저 돌린다"
    return NUMBERS9.read_text(encoding="utf-8")


def test_P1_frozen_constants():
    assert (P9.DELTA, P9.NULL_SEED, P9.NPERM, P9.PAIR_THRESHOLD) == (1.0, 20260815, 200_000, 40)
    assert (P9.DELTA, P9.NULL_SEED, P9.NPERM, P9.PAIR_THRESHOLD) == (LAD.DELTA, LAD.NULL_SEED, LAD.NPERM, LAD.PAIR_THRESHOLD)
    assert (P9.END, P9.PUB9, P9.END8, P9.END7, P9.BOUNDARY) == ("2026-09-23", "2026-09-23", "2026-09-18", "2026-09-11",
                                                                 "2026-09-14")
    assert (P9.GUARD_A_NUM, P9.GUARD_A_DEN, P9.TRUNC5_MIN_BARS) == (1, 3, 5)
    assert (P9.N_NEW_POST9, P9.N_EXACT_POST9) == (5, 5)


def _ledger_exact9():
    with open(BASE / "ledger_trades.csv", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["post_log_no"] == LOG9]
    assert len(rows) == 6
    return rows, [(r["stock_name"], r["reg_date"], int(r["fill_n"])) for r in rows if r["reg_date_precision"] == "exact"]


def _cmp(items, ledger):
    return [(nm, d0, n) for nm, _c, d0, n, *_ in items] == ledger


def test_P2_items_composition():
    assert P9.ITEMS[:32] == P8.ITEMS and P9.ITEMS[:28] == list(P7.ITEMS)
    rows, ex = _ledger_exact9()
    assert len(ex) == 5 and _cmp(P9.ITEMS_POST9_NEW, ex)
    assert all(it[4] == "post9" and it[5] == "2026-09-23" and it[6] is False for it in P9.ITEMS_POST9_NEW)
    none = [r["stock_name"] for r in rows if r["reg_date_precision"] != "exact"]
    assert none == ["우리기술"] and not [it for it in P9.ITEMS_POST9_NEW if it[0] in none], "후속은 등록일 축 밖"


def test_N1_symmetric_mutation():
    _rows, ex = _ledger_exact9()
    bad = [list(x) for x in P9.ITEMS_POST9_NEW]
    bad[3][3] = 1                                   # 첨단 N 4 → 1
    assert not _cmp([tuple(b) for b in bad], ex), "흔든 칸을 잡아야 한다(비교가 장식이 아니다)"


def test_P3_upstream_reuse():
    assert P9.pairset is LAD.pairset and P9.statV is LAD.statV and P9.permute_null is LAD.permute_null
    assert P9.run_axis is LAD.run_axis and P9.verdict_t1 is P6.verdict_t1 and P9.guard_a_fires is P6.guard_a_fires
    assert P9.build_rows is P7.build_rows and P9.cross_counts is P8.cross_counts and P9.window_bounds is P8.window_bounds
    assert P9.APPROX_BRANCHES_POST8 is P8.APPROX_BRANCHES and P9.POST7_TRUNC_ASOF is P8.POST7_TRUNC_ASOF
    assert LAD.OUT is P7.OUT, "import 만으로 post7 판 버퍼 결속을 흔들지 않는다"


def test_P4_read_stamp_reuse_and_symmetry():
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d) / "s"
        fp = {"a": 1}
        assert P9.read_stamp(fp, "2026-01-01 00:00:01", dd) == ("2026-01-01 00:00:01", False)
        b0 = (dd / "read_stamp.json").read_bytes()
        assert P9.read_stamp(fp, "2026-01-01 09:09:09", dd) == ("2026-01-01 00:00:01", True)
        assert (dd / "read_stamp.json").read_bytes() == b0, "같은 지문 ⇒ 파일 재기록 없음"
        assert P9.read_stamp({"a": 2}, "2026-01-02 00:00:00", dd) == ("2026-01-02 00:00:00", False), "🔴 지문이 다르면 새 시각"


def _d5_rows(t):
    sec = t.split("## §7-3.")[1].split("### §7-4.")[0]
    return [ln for ln in sec.splitlines() if ln.startswith("| ") and not ln.startswith("| 갈래 ") and not ln.startswith("|---")]


def test_P5_mandatory_lines():
    t = _t9()
    pre = (BASE / "PREREG_POST9.md").read_text(encoding="utf-8").splitlines()
    assert pre[38] == P9.LIVE_39 and pre[40] == P9.LIVE_41, "§0-1 문언 축자(PREREG_POST9 :39·:41)"
    lines = t.splitlines()
    assert P9.LIVE_39 in lines and P9.LIVE_41 in lines
    assert "**창 종료 2026-09-23 = 발행 당일(수 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1**" in lines
    assert re.search(r"^\*\*실행 시 `max\(date\)` = \d{4}-\d\d-\d\d · 그 날짜 행수 [\d,]+ — 기록만\(창 아님\)\*\*", t, re.M)
    st = json.loads(STAMP9.read_text(encoding="utf-8"))
    assert f"| ① 쿼리 실행 시각(KST) | **{st['first_read_kst']}**" in t
    for k in ("| ② 창 구간", "| ③ 09-23 봉의 빈티지", "| ④ 창 구간 `min(updated_at)`", "| ⑤ 혼합 빈티지"):
        assert k in t, k
    assert "*「주 분모 0/5 · `exact` 분모 0/5 · 문턱 1/3」* — **분모 갈래: 갈리지 않음**" in t
    assert "**post9 = 2회차 · `exact` 갈래 «미도달»**" in t
    assert "| ① 그 글 «단독»(post9 주 표본 5건끼리) | **7** |" in t and "**누적 비교가능 쌍 = 435**" in t
    assert "「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 5 / `approx` 포함 분모 5」" in t
    assert re.search(r"「`P9-공통독법`: 답 = 판정 · \(나\)4 결과 = 대상 없음", t)
    sec02 = [ln for ln in t.split("### §0-2.")[1].split("## §1-0.")[0].splitlines() if ln.startswith("- ")]
    assert sum("은 제도 경계 2026-09-14 를 걸친다 — 경계 전" in ln for ln in sec02) == 6, "PD-27 (바) 걸침 줄"
    assert sum("은 전부 제도 경계 후(전 0 / 후 5)" in ln for ln in sec02) == 3, "「전부 경계 후」 줄"
    rows = _d5_rows(t)
    assert len(rows) == 8
    for ln in rows:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        assert len(cells) == 4 and all(cells) and cells[1] != "—" and cells[2] != "—", f"세 쪽 빈칸 금지: {ln[:80]}"
    assert not [g for g in GRADE_NAMES if g in t], "등급 이름 0"


def test_P6_verdict_snapshot():
    t = _t9()
    assert "| **창5 `[D,D+4]` (주)** | 204 | 435 | 74 | 218.69 | **0.3508** |" in t
    assert "- ⇒ ⛔ **`LAD-T1` 불성립** (`p` = 0.3508 >= 0.05)." in t
    assert "| **정규화축 `DD/sigma20`(같은 쌍 집합)** | 211 | 391 | 65 | 197.33 | **0.6760** |" in t
    assert "| T3 `경과 거래일 E` | 209 | 435 | 77 | 217.62 | **0.4091** |" in t
    assert "**아니오 — 영구 취소 조항 미발동**" in t
    assert "- 주 판정 **불성립** ↔ 재진입 제외 **불성립** ⇒ **판정이 갈리지 않는다**" in t
    assert "주 갈래와 같은 쪽 **49/49**" in t
    assert "중앙값 **19.94%** ⇒ **✅ 구간 안**" in t
    assert "0.3509" not in t.split("## §3.")[1].split("### §3-1")[0], "대칭: 없는 값은 안 잡힌다"


def _blob(rel):
    out = subprocess.run(["git", "show", f"{BASE_REF}:RoboTrader_template/backtest/tasso_program_journal/{rel}"],
                         cwd=BASE, capture_output=True)
    assert out.returncode == 0, rel
    return out.stdout


def test_R1_upstream_untouched():
    for rel in ("run_ladder_tranche.py", "run_ladder_tranche_post6.py", "run_ladder_tranche_post7.py",
                "run_ladder_tranche_post8.py", "RESULTS_LADDER_TRANCHE_POST8_NUMBERS.md", "RESULTS_LADDER_TRANCHE_POST8.md",
                "run_tests.py"):
        assert hashlib.md5((BASE / rel).read_bytes()).hexdigest() == hashlib.md5(_blob(rel)).hexdigest(), rel
    # 원장은 post10 행이 뒤에 append 됐다(`0cc2e5e`) ⇒ 「post9 상태(= 기준 블롭)가 순수 prefix」 로 본다
    assert (BASE / "ledger_trades.csv").read_bytes().startswith(_blob("ledger_trades.csv")), \
        f"ledger_trades.csv: {BASE_REF} 상태가 prefix 가 아니다"
    miss = subprocess.run(["git", "cat-file", "-e",
                           f"{BASE_REF}:RoboTrader_template/backtest/tasso_program_journal/run_ladder_tranche_post9.py"],
                          cwd=BASE, capture_output=True)
    assert miss.returncode != 0, "대칭: 기준 ref 에 post9 스크립트는 없다(ref 가 post9 이전)"


def test_R2_rerun_byte_identical():
    with tempfile.TemporaryDirectory() as d:
        sd = Path(d) / "st"
        sd.mkdir()
        shutil.copy(STAMP9, sd / "read_stamp.json")
        b0 = (sd / "read_stamp.json").read_bytes()
        out = Path(d) / "N.md"
        code = ("import sys; sys.stdout.reconfigure(encoding='utf-8'); from pathlib import Path; "
                "import run_ladder_tranche_post9 as m; m.main(numbers=Path(sys.argv[1]), stamp_dir=Path(sys.argv[2]))")
        r = subprocess.run([sys.executable, "-X", "utf8", "-c", code, str(out), str(sd)], cwd=BASE,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, r.stderr[-2000:]
        if (sd / "read_stamp.json").read_bytes() != b0:
            pytest.skip("DB 지문이 바뀌었다(다음 sweep 뒤) — byte 재현은 같은 스냅샷 안에서만 성립(§9 --rerun 한계)")
        assert out.read_bytes() == NUMBERS9.read_bytes(), "같은 스냅샷 재실행 = byte 동일"


def test_R3_source_hygiene():
    src = (BASE / "run_ladder_tranche_post9.py").read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M)
    allow = {"__future__", "json", "statistics", "sys", "collections", "math", "pathlib", "psycopg2", "run_tests",
             "run_ladder_tranche", "run_ladder_tranche_post6", "run_ladder_tranche_post7", "run_ladder_tranche_post8"}
    assert not [m for m in imports if m.split(".")[0] not in allow]
    assert not re.search("adj_" r"factor\s*[\*/]|[\*/]\s*adj_" r"factor|execute\([^)]*adj_" r"factor", src), "adj_factor 산술·조회 0"
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\b\s", src), "DB 쓰기 0"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
