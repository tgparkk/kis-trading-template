# -*- coding: utf-8 -*-
"""`verify_ledger_post9.py` 의 «가드 시험» — 게이트가 실제로 실패를 내는지 본다.

🔑 계열 규칙: *캡처 장치도 가드다 — 가드를 시험하지 않으면 그것도 장식이다*
(`test_post6_ledger.py` · `test_post7_ledger.py` · `test_post8_ledger.py` 의 문형을 그대로 승계).
🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「통과했다」만 보이면
게이트가 항상 통과하는 장식일 수 있으므로 **일부러 깨뜨린 사본에서 실패가 나는지**도 본다.

실행: `python test_post9_ledger.py`  또는  `python -m pytest test_post9_ledger.py -q -p no:cacheprovider`
      (라이브 트리 import 0건 · DB 접속 0건)

  P   양성 대조 — 손대지 않은 원장 + 원문 ⇒ 종료코드 0 · 실패 0건
  P2  `~` 무판정 — 원문 우리기술 값 줄 끝에 `~` 를 붙여도 결과 불변
        🔑 PD-10 함정 ② (`~` 5개 중 레그 표지 0) — 이 게이트는 `~` 를 세지 않는다는 증거
  N1  G-A   원문의 항목번호를 5 → 7 로 바꿔 결번을 만든다
  N2  G-B   post9 매매행 1개(한컴위드)를 지운다 (원문 6 != trades 5)
  N3  G-C   post9 레그 값 13.59 → 13.60 으로 바꾼다
        🔑 함정 ① 「13.59.%」 의 값이 G-C 다중집합에 «들어간다»(PCT_RE 가 선언 없이 읽는다)
  N4  G-C   동률 레그 3.79 두 행 중 하나를 지우고 `n_legs` 를 3 → 2 로 맞춘다 (G-D 는 비껴간다)
        🔑 함정 ⑤ 동률 다중집합 보존 — 집합 비교였다면 통과했을 사본이다
  N5  G-D   post9 매매건(빛샘전자)의 `n_legs` 를 7 → 6 으로 바꾼다
  N6  P6-G-E  `fill_level=first_only` 인 행(삼미금속)의 `fill_n` 을 3 으로 바꾼다
  N7  [parse] 선언 기제가 post9 원문에도 걸린다 — 시험 중에만 post9 에 선언(「13.59.%」)을 넣고
        원문 사본에서 그 문자열을 지운다 ⇒ 「선언 ↔ 원문 불일치」가 큰 소리로 걸려야 한다
  N8  [parse] 선언 목록에 없는 «산문» ITEM_MARK 줄을 넣는다 (post9 `NON_ITEM_LINES` = 0건)
        🔑 선언을 비워 둔 것도 가드다 — 면제 규칙을 넓히지 않았다
  N9  G-C   역방향 — 한컴위드에 원문에 없는 레그 7.52 를 하나 더 넣고 `n_legs` 2 → 3 (G-D 는 비껴간다)
        ⇒ 「원장에만 있는 수치 [7.52]」 (post8 N9 의 대상 「손실률 인라인」은 post9 에 0건이라 이 자리로 옮겼다)
  N10 선언 0 이 옳다 — post9 에 `RAW_TYPO_FIX` 선언이 «없고», 넣어도 결과가 한 글자도 안 바뀐다
        (= 선언은 장식이 된다) · `PCT_RE` 가 「13.59.%」 에서 13.59 를 읽는다
  R1  post8 회귀 — `test_post8_ledger` 16건 중 R3 를 뺀 15건이 post9 append «뒤» 원장에서 통과
  R1b post8 R3 는 «구조적으로» 실패한다 — 그 단언(「post7 판 뒤에 붙은 줄은 전부 post8」 · 85/300)이
        post9 append 로 거짓이 되는 것이 정확히 그 이유인지 본다(대칭 단언 · 🔴 post8 시험 파일은 고치지 않는다)
  R2  post8 회귀 — `verify_ledger_post8.main` 이 실제 원장(사본 아님)에서 통과
  R3  순수 append — 기존 85/300 데이터 행(+헤더)의 바이트 md5 = post8 판 원장 값 · 뒤에 붙은 줄은 전부 post9
  S   post9 6행/23레그가 `INTAKE_2026-09-24_post9.md` §1 · `LABELS_2026-09-24_post9.md`「원장 플래그」·
      `PREDECISION_2026-09-24_post9.md` PD-17 표와 축자 일치 (게이트가 안 보는 인코딩 칸의 스냅샷)

🔴 원본 파일은 하나도 건드리지 않는다 — 전부 임시 디렉토리 사본에서만 깨뜨린다.
"""
from __future__ import annotations

import hashlib
import io
import shutil
import sys
import tempfile
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

import verify_ledger as V
import verify_ledger_post8 as P8
import verify_ledger_post9 as P9
import test_post8_ledger as T8

BASE = Path(__file__).resolve().parent
LOG = "224421214462"
ROW = "%s,2026-09-23,," % LOG              # post9 행 머리(post_log_no,post_date,prog_ver(빈 칸),)
RAW_SRC = P9.raw_path(LOG, {})             # 실제 원문(보관소) 경로

# post8 판 원장(`b302f7f`)의 바이트 길이·md5 — append 뒤에도 앞부분이 이 값이어야 한다
PREFIX = {"ledger_trades.csv": (45776, "883ad1461887e13ce7a095509bba7aa7"),
          "ledger_legs.csv": (17475, "ebb78814cee4872786815bd42c9ce23b")}

# post9 판 원장(`9d3bbe1`)의 길이·md5 — post10 행이 뒤에 append 돼도(`0cc2e5e`) 이 앞부분은 불변이어야 한다(post9 술어의 post10 이후 판)
POST9_STATE = {"ledger_trades.csv": (55299, "c01ea57da6b1bcc32ae7e93d0e025350"),
               "ledger_legs.csv": (18693, "bfa828f869ef5139a2489aaeff61d02b")}


def run_gate(csv_dir: Path, raw_file: Path):
    """게이트를 «사본» 위에서 한 번 돌린다. 반환 = (종료코드, 실패목록, 출력)."""
    old_base, old_failures = V.BASE, list(P9.failures)
    V.BASE = csv_dir
    P9.failures.clear()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = P9.main(["--raw", "%s=%s" % (LOG, raw_file)])
        return rc, list(P9.failures), buf.getvalue()
    finally:
        V.BASE = old_base
        P9.failures.clear()
        P9.failures.extend(old_failures)


def fresh(tmp: Path, tag: str):
    """원장 2종 + 원문 1종을 사본으로 깐다."""
    d = tmp / tag
    d.mkdir()
    for n in ("ledger_trades.csv", "ledger_legs.csv"):
        shutil.copyfile(BASE / n, d / n)
    shutil.copyfile(RAW_SRC, d / RAW_SRC.name)
    return d


def _write(path: Path, txt: str):
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(txt)


def edit(path: Path, old: str, new: str, expect: int = 1):
    with path.open(encoding="utf-8", newline="") as fh:
        txt = fh.read()
    assert txt.count(old) == expect, "치환 대상 %d건(기대 %d): %r" % (txt.count(old), expect, old)
    _write(path, txt.replace(old, new, expect))


def drop_line(path: Path, needle: str):
    with path.open(encoding="utf-8", newline="") as fh:
        lines = fh.read().splitlines(True)
    keep = [l for l in lines if needle not in l]
    assert len(keep) == len(lines) - 1, "지울 줄이 %d개" % (len(lines) - len(keep))
    _write(path, "".join(keep))


def _n4(d):
    drop_line(d / "ledger_legs.csv", ROW + "5,한국첨단소재,2,3.79,0,0")
    edit(d / "ledger_trades.csv", ROW + "5,한국첨단소재,3,1,0,", ROW + "5,한국첨단소재,2,1,0,")


def _n9(d):
    edit(d / "ledger_legs.csv", ROW + "6,한컴위드,2,7.52,0,1\n",
         ROW + "6,한컴위드,2,7.52,0,0\n" + ROW + "6,한컴위드,3,7.52,0,1\n")
    edit(d / "ledger_trades.csv", ROW + "6,한컴위드,2,1,0,", ROW + "6,한컴위드,3,1,0,")


# (tag, gate, 실패 문구 needle, 사본 깨뜨리기)
NEG = {
    "N1": ("G-A", "결번 [5]", lambda d: edit(d / RAW_SRC.name, "5. 한국첨단소재 /", "7. 한국첨단소재 /")),
    "N2": ("G-B", "", lambda d: drop_line(d / "ledger_trades.csv", ROW + "6,한컴위드,")),
    "N3": ("G-C", "", lambda d: edit(d / "ledger_legs.csv", ROW + "1,우리기술,1,13.59,0,0",
                                      ROW + "1,우리기술,1,13.60,0,0")),
    "N4": ("G-C", "원문에만 있는 수치 [3.79]", _n4),
    "N5": ("G-D", "", lambda d: edit(d / "ledger_trades.csv", ROW + "4,빛샘전자,7,1,0,",
                                      ROW + "4,빛샘전자,6,1,0,")),
    "N6": ("P6-G-E", "", lambda d: edit(d / "ledger_trades.csv",
                                         ROW + "2,삼미금속,4,0,0,2026-09-04,exact,first_only,1,",
                                         ROW + "2,삼미금속,4,0,0,2026-09-04,exact,first_only,3,")),
    "N8": ("parse", "구분자 분해 실패", lambda d: edit(d / RAW_SRC.name, "이 점을 꼭 고려하셔야 합니다.",
                                                  "선언에 없는 산문 통계기반 자동매매 홍보 줄")),
    "N9": ("G-C", "원장에만 있는 수치 [7.52]", _n9),
}


_LAST = []                                 # 스크립트 모드 인쇄용 — 마지막 음성 대조가 낸 실패 줄


def _neg(tmp: Path, tag: str):
    """사본을 깨뜨려 게이트를 돌리고, 지정 게이트·문구의 실패가 났는지 본다. 반환 = 전체 실패목록."""
    gate, needle, mutate = NEG[tag]
    d = fresh(tmp, tag)
    mutate(d)
    rc, fails, _ = run_gate(d, d / RAW_SRC.name)
    hit = [f for f in fails if f.startswith("[%s]" % gate) and needle in f]
    assert rc == 1 and hit, "%s: rc=%d · %s 실패 %d건 · 전체 %s" % (tag, rc, gate, len(hit), fails)
    _LAST[:] = [hit[0]]
    return fails


# ---- 양성 대조 ----------------------------------------------------------------
def test_P_positive(tmp_path):
    d = fresh(tmp_path, "P")
    rc, fails, out = run_gate(d, d / RAW_SRC.name)
    assert rc == 0 and not fails, fails
    assert "2026-09-23 224421214462: 6건(표지 6 + 산문 0) 23레그" in out
    assert "2026-09-23 224421214462: 저자번호 1..6 / 표지행 6 / **결번 0개**" in out


def test_P2_tilde_not_judged(tmp_path):
    d = fresh(tmp_path, "P2")
    edit(d / RAW_SRC.name, "9.71%, 0.21%", "9.71%, 0.21% ~")
    rc, fails, _ = run_gate(d, d / RAW_SRC.name)
    assert rc == 0 and not fails, fails


# ---- 음성 대조 ----------------------------------------------------------------
def test_N1_GA(tmp_path):
    _neg(tmp_path, "N1")


def test_N2_GB(tmp_path):
    _neg(tmp_path, "N2")


def test_N3_GC_typo_value_enters_multiset(tmp_path):
    _neg(tmp_path, "N3")


def test_N4_GC_tied_legs_multiset(tmp_path):
    fails = _neg(tmp_path, "N4")
    assert not [f for f in fails if not f.startswith("[G-C]")], "N4 는 G-C 만 걸려야 한다: %s" % fails


def test_N5_GD(tmp_path):
    _neg(tmp_path, "N5")


def test_N6_P6GE(tmp_path):
    _neg(tmp_path, "N6")


def test_N7_declared_string_must_exist(tmp_path):
    d = fresh(tmp_path, "N7")
    edit(d / RAW_SRC.name, "13.59.%", "13.59%")
    assert LOG not in P9.RAW_TYPO_FIX
    P9.RAW_TYPO_FIX[LOG] = [("13.59.%", "13.59%")]
    try:
        rc, fails, _ = run_gate(d, d / RAW_SRC.name)
    finally:
        del P9.RAW_TYPO_FIX[LOG]
    hit = [f for f in fails if f.startswith("[parse] %s: 선언한 오기" % LOG)]
    assert rc == 1 and hit, fails
    _LAST[:] = [hit[0]]


def test_N8_undeclared_item_mark_line(tmp_path):
    _neg(tmp_path, "N8")


def test_N9_GC_ledger_only_value(tmp_path):
    fails = _neg(tmp_path, "N9")
    assert not [f for f in fails if not f.startswith("[G-C]")], "N9 는 G-C 만 걸려야 한다: %s" % fails


def test_N10_no_declaration_needed(tmp_path):
    assert LOG not in P9.RAW_TYPO_FIX and LOG not in P9.NON_ITEM_LINES and LOG not in P9.EXTRA_PROSE_ITEMS
    assert V.PCT_RE.findall("수익률 13.59.%, 12.34%") == ["13.59", "12.34"]
    d = fresh(tmp_path, "N10")
    rc0, fails0, out0 = run_gate(d, d / RAW_SRC.name)
    P9.RAW_TYPO_FIX[LOG] = [("13.59.%", "13.59%")]
    try:
        rc1, fails1, out1 = run_gate(d, d / RAW_SRC.name)
    finally:
        del P9.RAW_TYPO_FIX[LOG]
    assert rc0 == rc1 == 0 and not fails0 and not fails1, (fails0, fails1)
    strip = [l for l in out1.splitlines() if "[오기 정규화]  %s" % LOG not in l]
    assert strip == out0.splitlines(), "선언이 결과를 바꿨다 — 선언이 «필요»했다는 뜻"


# ---- post8 회귀 · 순수 append ---------------------------------------------------
def test_R1_post8_guard_suite_minus_R3(tmp_path):
    ran = []
    for i, (tag, _desc, fn, needs_tmp) in enumerate(T8.CASES):
        if tag.strip() == "R3":
            continue
        if needs_tmp:
            t = tmp_path / ("t8_%02d" % i)
            t.mkdir()
            fn(t)
        else:
            fn()
        ran.append(tag.strip())
    T8._LAST.clear()
    assert len(ran) == len(T8.CASES) - 1 == 15, ran


def test_R1b_post8_R3_fails_only_by_growth():
    # 🔧 3단계(2026-09-30): post8 R3 술어를 「post8 상태 prefix 불변」으로 보정했다(`test_post8_ledger.py::POST8_STATE`)
    #    ⇒ 이제 post9 행이 붙어도 통과한다(예전엔 「뒤에 post8 아닌 줄」로 실패 — 정상 성장 때문). 통과 = 성장이 순수 append 라는 뜻.
    T8.test_R3_pure_append()
    for name, (n, md5) in T8.PREFIX.items():         # post7 판 prefix 는 여전히 그대로
        assert hashlib.md5((BASE / name).read_bytes()[:n]).hexdigest() == md5, name
    for name, (n, _md5) in PREFIX.items():            # post7 판 뒤 ~ post8 판 끝 = 전부 post8 줄
        mid = (BASE / name).read_bytes()[T8.PREFIX[name][0]:n].decode("utf-8").splitlines()
        assert mid and all(l.startswith(T8.ROW) for l in mid), name


def test_R2_post8_gate_on_real_ledger():
    old = list(P8.failures)
    P8.failures.clear()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = P8.main([])
        assert rc == 0 and not P8.failures, (P8.failures, buf.getvalue())
    finally:
        P8.failures.clear()
        P8.failures.extend(old)


def test_R3_pure_append():
    for name, (n, md5) in PREFIX.items():
        b = (BASE / name).read_bytes()
        assert hashlib.md5(b[:n]).hexdigest() == md5, "%s: 기존 %d바이트가 바뀌었다" % (name, n)
        assert b"\r" not in b and b.endswith(b"\n")
        n9, md59 = POST9_STATE[name]
        assert hashlib.md5(b[:n9]).hexdigest() == md59, "%s: post9 상태 %d바이트가 바뀌었다" % (name, n9)
        tail = b[n:n9].decode("utf-8").splitlines()
        assert tail and all(l.startswith(ROW) for l in tail), "%s: post8 뒤·post9 끝 사이에 post9 아닌 줄" % name
    assert len(V.load_csv("ledger_trades.csv")) >= 91 and len(V.load_csv("ledger_legs.csv")) >= 323


# ---- post9 인코딩 스냅샷 (INTAKE §1 · LABELS 「원장 플래그」 · PD-17) --------------------
#  item: (종목, [레그], open_ended, reg_date, precision, fill_level, fill_n, preset, manual, breakeven, stoploss, 라벨)
EXPECT = {
    1: ("우리기술", [13.59, 12.34, 11.02, 9.71, 0.21], "0", "", "none", "partial", "2", "표준형/HDR60",
        "0", "1", "0", "TP"),
    2: ("삼미금속", [22.09, 17.76, 13.45, 9.23], "0", "2026-09-04", "exact", "first_only", "1", "표준형/HDR60",
        "0", "0", "0", "TP"),
    3: ("에스투더블유", [15.08, 10.64], "0", "2026-09-10", "exact", "first_only", "1", "표준형/HDR60",
        "0", "0", "0", "TP"),
    4: ("빛샘전자", [23.08, 21.05, 18.64, 16.46, 14.20, 12.26, 10.08], "1", "2026-09-14", "exact", "first_only", "1",
        "표준형/HDR60", "0", "0", "0", "TP"),
    5: ("한국첨단소재", [3.80, 3.79, 3.79], "1", "2026-09-15", "exact", "partial", "4", "표준형/HDR60",
        "0", "0", "0", "TP"),
    6: ("한컴위드", [7.55, 7.52], "1", "2026-09-15", "exact", "partial", "2", "표준형/HDR60", "0", "0", "0", "TP"),
}
LEG_OPEN = {("4", "7"), ("5", "3"), ("6", "2")}     # 빛샘 10.08 · 첨단 두 번째 3.79 · 한컴 7.52 (서술 기준 마지막)


def test_S_post9_encoding_matches_intake():
    trades = [t for t in V.load_csv("ledger_trades.csv") if t["post_log_no"] == LOG]
    legs = [l for l in V.load_csv("ledger_legs.csv") if l["post_log_no"] == LOG]
    assert len(trades) == 6 and len(legs) == 23
    assert {t["post_date"] for t in trades + legs} == {"2026-09-23"}
    assert {t["prog_ver"] for t in trades + legs} == {""}                 # missing(PD-8)
    for t in trades:
        nm, lg, oe, rd, pr, fl, fn, ps, ma, be, sl, lab = EXPECT[int(t["item_no"])]
        got = (t["stock_name"], int(t["n_legs"]), t["open_ended"], t["all_loss"], t["reg_date"],
               t["reg_date_precision"], t["fill_level"], t["fill_n"], t["preset"],
               t["manual_exit"], t["breakeven_exit"], t["stoploss_plan"])
        assert got == (nm, len(lg), oe, "0", rd, pr, fl, fn, ps, ma, be, sl), (t["item_no"], got)
        assert t["narrative"].startswith("라벨 %s" % lab), (t["item_no"], t["narrative"][:20])
        seq = [float(l["ret_pct"]) for l in legs if l["item_no"] == t["item_no"]]
        idx = [l["leg_idx"] for l in legs if l["item_no"] == t["item_no"]]
        assert seq == lg and idx == [str(i) for i in range(1, len(lg) + 1)], (nm, seq, idx)
    assert {(l["item_no"], l["leg_idx"]) for l in legs if l["leg_open_ended"] == "1"} == LEG_OPEN
    assert not [l for l in legs if l["is_loss"] == "1"]                   # 「손실률」 0(PD-10 10)
    labels = Counter(t["narrative"].split(" ", 2)[1] for t in trades)
    assert labels == Counter(TP=6), labels                                # LABELS 집계
    assert Counter(t["reg_date_precision"] for t in trades) == Counter(exact=5, none=1)   # PD-4
    one = [t for t in trades if t["item_no"] == "1"][0]["narrative"]
    assert one.startswith("라벨 TP · CONTINUATION post8#10")                # 후속(PD-2)
    assert "「13.59.%」" in one                                             # 원 표기 보존(확인 2)


# ---- 스크립트 모드 -------------------------------------------------------------
CASES = [
    ("P ", "양성 대조", test_P_positive, True),
    ("P2", "`~` 무판정(결과 불변)", test_P2_tilde_not_judged, True),
    ("N1", "음성 G-A", test_N1_GA, True),
    ("N2", "음성 G-B", test_N2_GB, True),
    ("N3", "음성 G-C (13.59 다중집합)", test_N3_GC_typo_value_enters_multiset, True),
    ("N4", "음성 G-C (동률 다중집합)", test_N4_GC_tied_legs_multiset, True),
    ("N5", "음성 G-D", test_N5_GD, True),
    ("N6", "음성 P6-G-E", test_N6_P6GE, True),
    ("N7", "음성 [parse] 선언↔원문", test_N7_declared_string_must_exist, True),
    ("N8", "음성 [parse] 미선언 산문줄", test_N8_undeclared_item_mark_line, True),
    ("N9", "음성 G-C (원장에만)", test_N9_GC_ledger_only_value, True),
    ("N10", "선언 0 이 옳다(결과 불변)", test_N10_no_declaration_needed, True),
    ("R1", "post8 가드 15/16 회귀(R3 제외)", test_R1_post8_guard_suite_minus_R3, True),
    ("R1b", "post8 R3 = 성장 탓 실패만", test_R1b_post8_R3_fails_only_by_growth, False),
    ("R2", "post8 게이트 실원장 회귀", test_R2_post8_gate_on_real_ledger, False),
    ("R3", "순수 append", test_R3_pure_append, False),
    ("S ", "post9 인코딩 스냅샷", test_S_post9_encoding_matches_intake, False),
]


def main() -> int:
    bad = []
    with tempfile.TemporaryDirectory() as td:
        for i, (tag, desc, fn, needs_tmp) in enumerate(CASES):
            try:
                if needs_tmp:
                    t = Path(td) / ("c%02d" % i)
                    t.mkdir()
                    fn(t)
                else:
                    fn()
                ok, why = True, ""
            except AssertionError as e:  # noqa: PERF203
                ok, why = False, str(e)
            print("%-4s %-28s %s" % (tag, desc, "OK" if ok else "🔴 " + why[:300]))
            for f in _LAST:
                print("     └ %s" % f[:160])
            _LAST.clear()
            if not ok:
                bad.append(tag)
    print("")
    if bad:
        print("🔴 가드 시험 실패 %d건: %s" % (len(bad), bad))
        return 1
    print("가드 시험 %d/%d 통과 — 게이트는 통과도 «실패도» 낸다 (장식이 아니다)" % (len(CASES), len(CASES)))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
