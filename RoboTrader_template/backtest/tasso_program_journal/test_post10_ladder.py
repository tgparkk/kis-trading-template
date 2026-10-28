# -*- coding: utf-8 -*-
"""`run_ladder_tranche_post10.py` 가드 시험 (post9 판 구조 승계 · 짧게).

  P1  동결 상수 불변 · END/발행 10-02 · 분모 9/9
  P2  `ITEMS` = post9 판 37건 + post10 9건 · post10 9건 = 원장 `exact` 행의 (종목, 등록일, fill_n) · 후속 3건 부재 · 재진입 4 표시
  N1  대칭 — 사본 한 칸을 흔들면 P2 비교가 잡는다
  P3  상류 재사용 — 통계 핵·가드·`build_rows`·창 헬퍼가 «그 객체»
  P4  `read_stamp` — 같은 지문 = 재사용 · 파일 byte 불변 / 지문 한 글자 차이 = 새 시각
  P5  의무 인쇄 줄 — 창 종료·`max(date)`·§0-1 라이브 금지 문언(PREREG_POST10 `:56`·`:58` 축자)·D-9 ①~⑤·D-7·D-3·`P9-공통독법`·
      `F-3` 신고 줄·D-5 표 전 행 세 쪽 · 걸침 1 + 전부 경계 후 8 · 등급 이름 0
  P6  🔴 `F-5` 구조 — `LAD-T1`·`LAD-P2` 「계산 0회」 문형 · `V`·`p` 판정 표 없음 · `LAD-T3` 「귀결 대상 종결」 · 가드-B 문형
  S1  🔴 소스 가드 — `verdict_t1` 호출 0 · `run_axis` 호출은 전부 `T3` 축 · `LAD-T1` 입력(DD 값)에 `statV`/`permute_null` 직접 호출은 `t2_stats` 안뿐
  R1  상류 파일·post9 산출물이 `8e014ca` 블롭과 byte 동일 · 옛 원장 행 불변 + 대칭(그 ref 에 post10 스크립트 없음)
  R2  재실행 byte 동일(별 프로세스 · 스탬프는 임시 사본 — 지문이 바뀌면 skip: 다음 sweep 뒤 한계)
  R3  위생 — import 허용 목록 · DB 쓰기 0 · adj_factor 산술 0

실행: `python -m pytest test_post10_ladder.py -q -p no:cacheprovider` (R2 만 DB SELECT · 나머지 DB 0)
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
import run_ladder_tranche_post10 as P10

BASE = Path(__file__).resolve().parent
NUMBERS10 = BASE / "RESULTS_LADDER_TRANCHE_POST10_NUMBERS.md"
STAMP10 = BASE / "ladder_post10" / "read_stamp.json"
BASE_REF = "8e014ca"
LOG10 = "224429747319"
GRADE_NAMES = ["충족·참고용", "조건 미달", "낡음(재실행 금지)", "GT-A", "GT-B", "GT-C", "GT-D", "GT-E", "GT-F"]


def _t10():
    assert NUMBERS10.exists(), "run_ladder_tranche_post10.py 를 먼저 돌린다"
    return NUMBERS10.read_text(encoding="utf-8")


def test_P1_frozen_constants():
    assert (P10.DELTA, P10.NULL_SEED, P10.NPERM, P10.PAIR_THRESHOLD) == (1.0, 20260815, 200_000, 40)
    assert (P10.DELTA, P10.NULL_SEED, P10.NPERM, P10.PAIR_THRESHOLD) == (LAD.DELTA, LAD.NULL_SEED, LAD.NPERM, LAD.PAIR_THRESHOLD)
    assert (P10.END, P10.PUB10, P10.END9, P10.END7, P10.BOUNDARY) == ("2026-10-02", "2026-10-02", "2026-09-23", "2026-09-11",
                                                                      "2026-09-14")
    assert (P10.GUARD_A_NUM, P10.GUARD_A_DEN, P10.TRUNC5_MIN_BARS) == (1, 3, 5)
    assert (P10.N_NEW_POST10, P10.N_EXACT_POST10) == (9, 9)
    assert P10.LAUNCH_CAP == "2026-10-08 23:59:59"


def _ledger():
    with open(BASE / "ledger_trades.csv", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["post_log_no"] == LOG10]
    assert len(rows) == 12
    return rows, [(r["stock_name"], r["reg_date"], int(r["fill_n"])) for r in rows if r["reg_date_precision"] == "exact"]


def _cmp(items, ledger):
    return [(nm, d0, n) for nm, _c, d0, n, *_ in items] == ledger


def test_P2_items_composition():
    assert P10.ITEMS[:37] == P9.ITEMS and P10.ITEMS[:28] == list(P7.ITEMS) and len(P10.ITEMS) == 46
    rows, ex = _ledger()
    assert len(ex) == 9 and _cmp(P10.ITEMS_POST10_NEW, ex)
    assert all(it[4] == "post10" and it[5] == "2026-10-02" for it in P10.ITEMS_POST10_NEW)
    assert {it[0] for it in P10.ITEMS_POST10_NEW if it[6]} == {"범한퓨얼셀", "서산", "한켐", "우리로"}, "재진입 4 (PD-3)"
    none = [r["stock_name"] for r in rows if r["reg_date_precision"] != "exact"]
    assert none == ["한컴위드", "코데즈컴바인", "빛샘전자"] and not [it for it in P10.ITEMS_POST10_NEW if it[0] in none], \
        "후속 3 은 등록일 축 밖"
    assert [r["stock_name"] for r in rows if r["reg_date_precision"] == "exact" and r["open_ended"] == "1"] == \
        ["샌즈랩", "HT로보틱스", "한켐", "우리로"]


def test_N1_symmetric_mutation():
    _rows, ex = _ledger()
    bad = [list(x) for x in P10.ITEMS_POST10_NEW]
    bad[2][3] = 1                                   # 서산 N 5 → 1
    assert not _cmp([tuple(b) for b in bad], ex), "흔든 칸을 잡아야 한다(비교가 장식이 아니다)"


def test_P3_upstream_reuse():
    assert P10.pairset is LAD.pairset and P10.statV is LAD.statV and P10.permute_null is LAD.permute_null
    assert P10.run_axis is LAD.run_axis and P10.guard_a_fires is P6.guard_a_fires and P10.median is P6.median
    assert P10.build_rows is P7.build_rows and P10.cross_counts is P8.cross_counts and P10.window_bounds is P8.window_bounds
    assert P10.APPROX_BRANCHES_POST8 is P8.APPROX_BRANCHES and P10.POST7_TRUNC_ASOF is P8.POST7_TRUNC_ASOF
    assert LAD.OUT is P7.OUT, "import 만으로 post7 판 버퍼 결속을 흔들지 않는다"


def test_P4_read_stamp_reuse_and_symmetry():
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d) / "s"
        fp = {"a": 1}
        assert P10.read_stamp(fp, "2026-01-01 00:00:01", dd) == ("2026-01-01 00:00:01", False)
        b0 = (dd / "read_stamp.json").read_bytes()
        assert P10.read_stamp(fp, "2026-01-01 09:09:09", dd) == ("2026-01-01 00:00:01", True)
        assert (dd / "read_stamp.json").read_bytes() == b0, "같은 지문 ⇒ 파일 재기록 없음"
        assert P10.read_stamp({"a": 2}, "2026-01-02 00:00:00", dd) == ("2026-01-02 00:00:00", False), "🔴 지문이 다르면 새 시각"
        st = json.loads((dd / "read_stamp.json").read_text(encoding="utf-8"))
        assert set(st) == {"fingerprint", "first_read_kst", "timezone"} and st["timezone"] == "Asia/Seoul"


def _d5_rows(t):
    sec = t.split("## §7-3.")[1].split("### §7-4.")[0]
    return [ln for ln in sec.splitlines() if ln.startswith("| ") and not ln.startswith("| 갈래 ") and not ln.startswith("|---")]


def test_P5_mandatory_lines():
    t = _t10()
    pre = (BASE / "PREREG_POST10.md").read_text(encoding="utf-8").splitlines()
    assert pre[55] == P10.LIVE_39 and pre[57] == P10.LIVE_41, "§0-1 문언 축자(PREREG_POST10 :56·:58)"
    lines = t.splitlines()
    assert P10.LIVE_39 in lines and P10.LIVE_41 in lines
    assert "**창 종료 2026-10-02 = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · `END` · 전 축(`WRC-` 포함) · PD-1**" in lines
    assert re.search(r"^\*\*실행 시 `max\(date\)` = \d{4}-\d\d-\d\d · 그 날짜 행수 [\d,]+ — 기록만\(창 아님\)\*\*", t, re.M)
    st = json.loads(STAMP10.read_text(encoding="utf-8"))
    assert set(st) == {"fingerprint", "first_read_kst", "timezone"}
    assert f"| ① 쿼리 실행 시각(KST) | **{st['first_read_kst']}**" in t
    for k in ("| ② 창 구간", "| ③ 10-02 봉의 빈티지", "| ④ 창 구간 `min(updated_at)`", "| ⑤ 혼합 빈티지"):
        assert k in t, k
    assert "「10-02 봉은 D+1(10-06 · 10-05 개천절 대체공휴일) sweep 이후 읽음」" in t
    assert "*「주 분모 1/9 · `exact` 분모 1/9 · 문턱 1/3」* — **분모 갈래: 갈리지 않음**" in t
    assert "**post10 = 3회차 · `exact` 갈래 «미도달»**" in t
    assert "「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 9 / `approx` 포함 분모 9」" in t
    assert re.search(r"「`P9-공통독법`: 답 = 판정 · \(나\)4 결과 = 대상 없음", t)
    assert "*「`P10-기업행위봉`: 기업행위 건 " in t and "`adj_factor` 산술 0 · 처리 = (나)」*" in t
    assert re.search(r"`P10-approx누적범위`: 범위 = 🔒 \(가\) 누적 `approx` 전건", t)
    sec02 = [ln for ln in t.split("### §0-2.")[1].split("## §1-0.")[0].splitlines() if ln.startswith("- ")]
    assert sum("(post10 · 등록" in ln and "은 제도 경계 2026-09-14 를 걸친다 — 경계 전" in ln for ln in sec02) == 1, "걸침 1(서산)"
    assert sum("(post10 · 등록" in ln and "은 전부 제도 경계 후(전 0 / 후" in ln for ln in sec02) == 8, "「전부 경계 후」 8"
    rows = _d5_rows(t)
    assert len(rows) >= 10
    for ln in rows:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        assert len(cells) == 4 and all(cells) and cells[1] != "—" and cells[2] != "—", f"세 쪽 빈칸 금지: {ln[:80]}"
    assert any(ln.startswith("| 「기업행위 건 제외」") and "답(참고) · 세지 않는다" in ln for ln in rows)
    assert not [g for g in GRADE_NAMES if g in t], "등급 이름 0"
    assert "라이브 채택 대상이 아니다" in t and "nan" not in t


def test_P6_f5_structure():
    t = _t10()
    assert f"- **`LAD-T1`**: {P10.T1_CLOSED}" in t
    assert "해당 없음 — 🔒 종결(2026-10-01 폐기 접수 · `PREREG_ANCHOR_REDESIGN.md:253` · 기록 보존) — 핵심 수: 계산 0회" in t
    assert f"- **`LAD-P2`**(〔LAD-P2〕 조각): {P10.T1_CLOSED}" in t
    assert "**`LAD-T1` 영구 취소**" not in t and "불성립** (`p` =" not in t and "(주)** |" not in t, "T1 판정·표 행이 없어야 한다"
    assert "**귀결 대상 종결(`F-5`)**" in t.split("## §5.")[1].split("## §6.")[0], "LAD-T3 귀결 줄"
    assert "**귀결 대상 종결(`F-5`)**" in t.split("## §6.")[1].split("## §7.")[0], "P6-창5절단가드-B 귀결 줄"
    assert all(not ln.startswith("| 창5 `[D,D+4]`") and not ln.startswith("| **창5 `[D,D+4]`") for ln in t.splitlines())
    assert "최소 n 을 채운 계수 갈래 = **0개**" in t


def _src():
    return (BASE / "run_ladder_tranche_post10.py").read_text(encoding="utf-8")


def test_S1_t1_never_computed():
    src = _src()
    body = src.split("def main(")[1]
    assert not re.search(r"verdict_t1\s*\(", src), "verdict_t1 호출 0 (LAD-T1 종결)"
    calls = re.findall(r'run_axis\(\s*f?"([^"]*)"', body)
    assert calls and all("T3" in c for c in calls), f"run_axis 는 T3 축에만: {calls}"
    # statV / permute_null 직접 호출은 t2_stats(LAD-T2 계속) 안에서만
    t2src = src.split("def t2_stats(")[1].split("def main(")[0]
    assert "statV(" in t2src and "permute_null(" in t2src
    assert not re.search(r"\b(statV|permute_null)\s*\(", body), "main 에서 V·null 직접 계산 0"
    assert "comp_of(" in body and "def comp_of" in src


def _blob(rel):
    out = subprocess.run(["git", "show", f"{BASE_REF}:RoboTrader_template/backtest/tasso_program_journal/{rel}"],
                         cwd=BASE, capture_output=True)
    assert out.returncode == 0, rel
    return out.stdout


def _lf(b):
    return b.replace(bytes([13, 10]), bytes([10]))      # Windows `write_text` 가 CRLF 로 쓴다 — 줄끝 차이는 내용 차이가 아니다


def test_R1_upstream_untouched():
    for rel in ("run_ladder_tranche.py", "run_ladder_tranche_post6.py", "run_ladder_tranche_post7.py",
                "run_ladder_tranche_post8.py", "run_ladder_tranche_post9.py", "RESULTS_LADDER_TRANCHE_POST8_NUMBERS.md",
                "RESULTS_LADDER_TRANCHE_POST9_NUMBERS.md", "RESULTS_LADDER_TRANCHE_POST9.md", "run_tests.py"):
        assert hashlib.md5(_lf((BASE / rel).read_bytes())).hexdigest() == hashlib.md5(_lf(_blob(rel))).hexdigest(), rel
    for rel in ("ledger_trades.csv", "ledger_legs.csv"):          # 옛 원장 행 불변 — 현재 파일이 그 ref 의 접두를 그대로 품는다
        assert _lf((BASE / rel).read_bytes()).startswith(_lf(_blob(rel))), rel
    miss = subprocess.run(["git", "cat-file", "-e",
                           f"{BASE_REF}:RoboTrader_template/backtest/tasso_program_journal/run_ladder_tranche_post10.py"],
                          cwd=BASE, capture_output=True)
    assert miss.returncode != 0, "대칭: 기준 ref 에 post10 스크립트는 없다(ref 가 post10 이전)"


def test_R2_rerun_byte_identical():
    with tempfile.TemporaryDirectory() as d:
        sd = Path(d) / "st"
        sd.mkdir()
        shutil.copy(STAMP10, sd / "read_stamp.json")
        b0 = (sd / "read_stamp.json").read_bytes()
        out = Path(d) / "N.md"
        code = ("import sys; sys.stdout.reconfigure(encoding='utf-8'); from pathlib import Path; "
                "import run_ladder_tranche_post10 as m; m.main(numbers=Path(sys.argv[1]), stamp_dir=Path(sys.argv[2]))")
        r = subprocess.run([sys.executable, "-X", "utf8", "-c", code, str(out), str(sd)], cwd=BASE,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, r.stderr[-2000:]
        if (sd / "read_stamp.json").read_bytes() != b0:
            pytest.skip("DB 지문이 바뀌었다(다음 sweep 뒤) — byte 재현은 같은 스냅샷 안에서만 성립(§9 --rerun 한계)")
        assert out.read_bytes() == NUMBERS10.read_bytes(), "같은 스냅샷 재실행 = byte 동일"


def test_R3_source_hygiene():
    src = _src()
    imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M)
    allow = {"__future__", "json", "statistics", "sys", "collections", "math", "pathlib", "psycopg2", "run_tests",
             "run_ladder_tranche", "run_ladder_tranche_post6", "run_ladder_tranche_post7", "run_ladder_tranche_post8",
             "run_ladder_tranche_post9"}
    assert not [m for m in imports if m.split(".")[0] not in allow]
    assert not re.search("adj_" r"factor\s*[\*/]|[\*/]\s*adj_" r"factor|execute\([^)]*adj_" r"factor", src), "adj_factor 산술·조회 0"
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\b\s", src), "DB 쓰기 0"
    assert not re.search(r"anchor_post10|RESULTS_ANCHOR_POST10", src), "ANC 산출물 경로 0(`F-5` (ㄱ))"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
