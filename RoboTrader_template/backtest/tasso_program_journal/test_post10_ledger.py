# -*- coding: utf-8 -*-
"""`verify_ledger_post10.py` 의 «가드 시험» — 게이트가 실제로 실패를 내는지 본다.

🔑 계열 규칙: *캡처 장치도 가드다 — 가드를 시험하지 않으면 그것도 장식이다*
(`test_post6_ledger.py` ~ `test_post9_ledger.py` 의 문형을 그대로 승계).
🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「통과했다」만 보이면
게이트가 항상 통과하는 장식일 수 있으므로 **일부러 깨뜨린 사본에서 실패가 나는지**도 본다.

실행: `python test_post10_ledger.py`  또는  `python -m pytest test_post10_ledger.py -q -p no:cacheprovider`
      (라이브 트리 import 0건 · DB 접속 0건)

  P   양성 대조 — 손대지 않은 원장 + 원문 ⇒ 종료코드 0 · 실패 0건
  P2  `~` 무판정 — 원문 우리로 값 줄 끝에 `~` 를 더 붙여도 결과 불변 (PD-10 #2·#3 · 라온 `~` 값 줄 중간)
  N1  G-A   원문의 항목번호를 5 → 7 로 바꿔 결번을 만든다
  N2  G-B   post10 매매행 1개(한컴위드)를 지운다 (원문 12 != trades 11)
  N3  G-C   post10 레그 값 12.78 → 12.79 로 바꾼다
  N4  G-C   근접 값 HT 7.65·7.63·7.62 중 7.63 을 지우고 `n_legs` 를 5 → 4 로 맞춘다 (G-D 는 비껴간다)
  N5  G-D   post10 매매건(성호전자)의 `n_legs` 를 4 → 3 으로 바꾼다
  N6  P6-G-E  `fill_level=first_only` 인 행(성호전자)의 `fill_n` 을 3 으로 바꾼다
  N7  [parse] 선언 기제가 post10 원문에도 걸린다 — 시험 중에만 post10 에 «원문에 없는» 문자열을 선언 ⇒ 「선언 ↔ 원문 불일치」
  N8  [parse] 선언 목록에 없는 «산문» ITEM_MARK 줄을 넣는다 (post10 `NON_ITEM_LINES` = 0건)
  N9  G-C   역방향 — 범한퓨얼셀에 원문에 없는 레그 0.38 을 하나 더 넣고 `n_legs` 2 → 3
  N10 선언 0 이 옳다 — post10 에 `RAW_TYPO_FIX`·`NON_ITEM_LINES`·`EXTRA_PROSE_ITEMS` 선언이 «없다»
  N11 ⑧ 값 줄 밖 `%` — 테마 줄(txt:4·:9 · ITEM_MARK 없음)에 「+99.99%」 를 넣어도 결과 불변 (항목 블록 전체를 긁지 않는다)
  N12 ① 「손실률」 음수 값이 G-C 다중집합에 «들어간다» — 라온 -0.49 → -0.48
  R1  post9 회귀 — `test_post9_ledger` 17건 중 R3 를 뺀 16건이 post10 append «뒤» 원장에서 통과
  R1b post9 R3 는 «구조적으로» 실패한다 — 그 단언(「뒤에 붙은 줄은 전부 post9」 · 91/323)이 post10 append 로 거짓이 되는 것이
        정확한 이유인지 본다(🔴 post9 시험 파일은 고치지 않는다 · 3단계 보정 대상)
  R2  post9 회귀 — `verify_ledger_post9.main` 이 실제 원장(사본 아님)에서 통과
  R3  순수 append — 기존 91/323 데이터 행(+헤더)의 바이트 md5 = post9 판 원장 값 · 뒤에 붙은 줄은 전부 post10 · 103/357
  S   post10 12행/34레그가 `INTAKE_2026-10-04_post10.md` §1 · `LABELS_2026-10-04_post10.md`「원장 플래그」·
      `PREDECISION_2026-10-04_post10.md` PD-17 표와 일치 (게이트가 안 보는 인코딩 칸의 스냅샷)

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
import verify_ledger_post9 as P9
import verify_ledger_post10 as P10
import test_post9_ledger as T9

BASE = Path(__file__).resolve().parent
LOG = "224429747319"
ROW = "%s,2026-10-02,1.0.43," % LOG        # post10 행 머리(post_log_no,post_date,prog_ver,)
RAW_SRC = P10.raw_path(LOG, {})            # 실제 원문(보관소) 경로

# post9 판 원장 — append 뒤에도 앞부분이 이 값이어야 한다
PREFIX = {"ledger_trades.csv": (55299, "c01ea57da6b1bcc32ae7e93d0e025350"),
          "ledger_legs.csv": (18693, "bfa828f869ef5139a2489aaeff61d02b")}


def run_gate(csv_dir: Path, raw_file: Path):
    """게이트를 «사본» 위에서 한 번 돌린다. 반환 = (종료코드, 실패목록, 출력)."""
    old_base, old_failures = V.BASE, list(P10.failures)
    V.BASE = csv_dir
    P10.failures.clear()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = P10.main(["--raw", "%s=%s" % (LOG, raw_file)])
        return rc, list(P10.failures), buf.getvalue()
    finally:
        V.BASE = old_base
        P10.failures.clear()
        P10.failures.extend(old_failures)


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
    drop_line(d / "ledger_legs.csv", ROW + "9,HT로보틱스,4,7.63,0,0")
    edit(d / "ledger_trades.csv", ROW + "9,HT로보틱스,5,1,0,", ROW + "9,HT로보틱스,4,1,0,")


def _n9(d):
    edit(d / "ledger_legs.csv", ROW + "3,범한퓨얼셀,2,0.38,0,0\n",
         ROW + "3,범한퓨얼셀,2,0.38,0,0\n" + ROW + "3,범한퓨얼셀,3,0.38,0,0\n")
    edit(d / "ledger_trades.csv", ROW + "3,범한퓨얼셀,2,0,", ROW + "3,범한퓨얼셀,3,0,")


# (tag, gate, 실패 문구 needle, 사본 깨뜨리기)
NEG = {
    "N1": ("G-A", "결번 [5]", lambda d: edit(d / RAW_SRC.name, "5. 코데즈컴바인 /", "7. 코데즈컴바인 /")),
    "N2": ("G-B", "", lambda d: drop_line(d / "ledger_trades.csv", ROW + "1,한컴위드,")),
    "N3": ("G-C", "원문에만 있는 수치 [12.78]",
           lambda d: edit(d / "ledger_legs.csv", ROW + "2,라온시큐어,1,12.78,0,0", ROW + "2,라온시큐어,1,12.79,0,0")),
    "N4": ("G-C", "원문에만 있는 수치 [7.63]", _n4),
    "N5": ("G-D", "", lambda d: edit(d / "ledger_trades.csv", ROW + "8,성호전자,4,0,", ROW + "8,성호전자,3,0,")),
    "N6": ("P6-G-E", "", lambda d: edit(d / "ledger_trades.csv",
                                         ROW + "8,성호전자,4,0,0,2026-09-14,exact,first_only,1,",
                                         ROW + "8,성호전자,4,0,0,2026-09-14,exact,first_only,3,")),
    "N8": ("parse", "구분자 분해 실패", lambda d: edit(d / RAW_SRC.name, "감사합니다.",
                                                  "선언에 없는 산문 통계기반 자동매매 홍보 줄")),
    "N9": ("G-C", "원장에만 있는 수치 [0.38]", _n9),
    "N12": ("G-C", "원문에만 있는 수치 [-0.49]",
            lambda d: edit(d / "ledger_legs.csv", ROW + "2,라온시큐어,6,-0.49,1,0", ROW + "2,라온시큐어,6,-0.48,1,0")),
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
    assert "2026-10-02 224429747319: 12건(표지 12 + 산문 0) 34레그" in out
    assert "2026-10-02 224429747319: 저자번호 1..12 / 표지행 12 / **결번 0개**" in out


def test_P2_tilde_not_judged(tmp_path):
    d = fresh(tmp_path, "P2")
    edit(d / RAW_SRC.name, "15.44%, 11.58%", "15.44%, 11.58% ~")
    rc, fails, _ = run_gate(d, d / RAW_SRC.name)
    assert rc == 0 and not fails, fails


# ---- 음성 대조 ----------------------------------------------------------------
def test_N1_GA(tmp_path):
    _neg(tmp_path, "N1")


def test_N2_GB(tmp_path):
    _neg(tmp_path, "N2")


def test_N3_GC_value(tmp_path):
    _neg(tmp_path, "N3")


def test_N4_GC_near_values_multiset(tmp_path):
    fails = _neg(tmp_path, "N4")
    assert not [f for f in fails if not f.startswith("[G-C]")], "N4 는 G-C 만 걸려야 한다: %s" % fails


def test_N5_GD(tmp_path):
    _neg(tmp_path, "N5")


def test_N6_P6GE(tmp_path):
    _neg(tmp_path, "N6")


def test_N7_declared_string_must_exist(tmp_path):
    d = fresh(tmp_path, "N7")
    assert LOG not in P10.RAW_TYPO_FIX
    P10.RAW_TYPO_FIX[LOG] = [("선언했지만 원문에 없는 문자열", "x")]
    try:
        rc, fails, _ = run_gate(d, d / RAW_SRC.name)
    finally:
        del P10.RAW_TYPO_FIX[LOG]
    hit = [f for f in fails if f.startswith("[parse] %s: 선언한 오기" % LOG)]
    assert rc == 1 and hit, fails
    _LAST[:] = [hit[0]]


def test_N8_undeclared_item_mark_line(tmp_path):
    _neg(tmp_path, "N8")


def test_N9_GC_ledger_only_value(tmp_path):
    fails = _neg(tmp_path, "N9")
    assert not [f for f in fails if not f.startswith("[G-C]")], "N9 는 G-C 만 걸려야 한다: %s" % fails


def test_N10_no_declaration_needed():
    assert LOG not in P10.RAW_TYPO_FIX and LOG not in P10.NON_ITEM_LINES and LOG not in P10.EXTRA_PROSE_ITEMS
    assert V.PCT_RE.findall("수익률 12.78%, 0.32% ~, 손실률 -0.49%") == ["12.78", "0.32", "-0.49"]


def test_N11_off_line_percent_not_read(tmp_path):
    d = fresh(tmp_path, "N11")
    edit(d / RAW_SRC.name, "크라우드스트라이크(+13.85%) 등 美 사이버보안주 급등 영향",
         "크라우드스트라이크(+13.85%) 등 美 사이버보안주 급등 영향 +99.99%", expect=2)
    rc, fails, _ = run_gate(d, d / RAW_SRC.name)
    assert rc == 0 and not fails, fails


def test_N12_GC_loss_value_enters_multiset(tmp_path):
    _neg(tmp_path, "N12")


# ---- post9 회귀 · 순수 append ---------------------------------------------------
def test_R1_post9_guard_suite_minus_R3(tmp_path):
    ran = []
    for i, (tag, _desc, fn, needs_tmp) in enumerate(T9.CASES):
        if tag.strip() == "R3":
            continue
        if needs_tmp:
            t = tmp_path / ("t9_%02d" % i)
            t.mkdir()
            fn(t)
        else:
            fn()
        ran.append(tag.strip())
    T9._LAST.clear()
    assert len(ran) == len(T9.CASES) - 1 == 16, ran


def test_R1b_post9_R3_fails_only_by_growth():
    try:
        T9.test_R3_pure_append()
    except AssertionError as e:
        assert "뒤에 post9 아닌 줄" in str(e), str(e)
    else:
        raise AssertionError("post9 R3 가 통과했다 — 성장 뒤에도 거짓이 되지 않았다면 이 시험의 전제가 틀렸다")
    for name, (n, md5) in T9.PREFIX.items():          # post8 판 prefix 는 여전히 그대로
        assert hashlib.md5((BASE / name).read_bytes()[:n]).hexdigest() == md5, name
    for name, (n, _md5) in PREFIX.items():            # post8 판 뒤 ~ post9 판 끝 = 전부 post9 줄
        mid = (BASE / name).read_bytes()[T9.PREFIX[name][0]:n].decode("utf-8").splitlines()
        assert mid and all(l.startswith(T9.ROW) for l in mid), name


def test_R2_post9_gate_on_real_ledger():
    old = list(P9.failures)
    P9.failures.clear()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = P9.main([])
        assert rc == 0 and not P9.failures, (P9.failures, buf.getvalue())
    finally:
        P9.failures.clear()
        P9.failures.extend(old)


def test_R3_pure_append():
    for name, (n, md5) in PREFIX.items():
        b = (BASE / name).read_bytes()
        assert hashlib.md5(b[:n]).hexdigest() == md5, "%s: 기존 %d바이트가 바뀌었다" % (name, n)
        assert b"\r" not in b and b.endswith(b"\n")
        tail = b[n:].decode("utf-8").splitlines()
        assert tail and all(l.startswith(ROW) for l in tail), "%s: 뒤에 post10 아닌 줄" % name
    assert len(V.load_csv("ledger_trades.csv")) == 103 and len(V.load_csv("ledger_legs.csv")) == 357


# ---- post10 인코딩 스냅샷 (INTAKE §1 · LABELS 「원장 플래그」 · PD-17) -------------------
#  item: (종목, [레그], open_ended, reg_date, precision, fill_level, fill_n, preset, manual, breakeven, stoploss, 라벨)
H60, QT = "표준형/HDR60", "표준형/사분위수"
EXPECT = {
    1: ("한컴위드", [7.50, 5.48], "1", "", "none", "partial", "2", H60,   # fill_n 2 = 사이클 1 서술(PD-43) · 대안 3 = PD-17 서술 최대 차수
         "0", "0", "0", "TP"),
    2: ("라온시큐어", [12.78, 9.52, 6.40, 2.33, 0.32, -0.49], "0", "2026-09-15", "exact", "partial", "4", H60,
        "0", "1", "0", "MIX"),
    3: ("범한퓨얼셀", [7.79, 0.38], "0", "2026-09-16", "exact", "first_only", "1", H60, "0", "1", "0", "TP"),
    4: ("서산", [3.01, 0.38], "0", "2026-09-09", "exact", "partial", "5", QT, "0", "1", "0", "TP"),
    5: ("코데즈컴바인", [0.12], "0", "", "none", "partial", "2", QT, "0", "1", "0", "TP"),
    6: ("샌즈랩", [5.24, 4.88, 0.29, -0.02], "1", "2026-09-14", "exact", "partial", "3", H60, "0", "1", "0", "MIX"),
    7: ("빛샘전자", [27.52, 25.34], "0", "", "none", "first_only", "1", H60, "0", "0", "0", "TP"),
    8: ("성호전자", [26.39, 17.92, 13.71, 9.28], "0", "2026-09-14", "exact", "first_only", "1", H60,
        "0", "0", "0", "TP"),
    9: ("HT로보틱스", [16.93, 12.36, 7.65, 7.63, 7.62], "1", "2026-09-18", "exact", "partial", "3", H60,
        "0", "0", "0", "TP"),
    10: ("한켐", [10.37], "1", "2026-09-16", "exact", "first_only", "1", H60, "0", "0", "0", "TP"),
    11: ("뷰노", [15.63, 2.18], "0", "2026-09-29", "exact", "first_only", "1", H60, "0", "1", "0", "TP"),
    12: ("우리로", [19.47, 15.44, 11.58], "1", "2026-09-18", "exact", "first_only", "1", H60, "0", "0", "0", "TP"),
}
# 서술 기준 미완결 5행의 마지막 레그 + 라온 `~` 레그(0.32 · 값 줄 중간 · post8 우리로 선례)
LEG_OPEN = {("1", "2"), ("2", "5"), ("6", "4"), ("9", "5"), ("10", "1"), ("12", "3")}
CONT = {"1": "post9#6", "5": "post8#9", "7": "post9#4"}                 # 후속 3건(PD-2)


def test_S_post10_encoding_matches_intake():
    trades = [t for t in V.load_csv("ledger_trades.csv") if t["post_log_no"] == LOG]
    legs = [l for l in V.load_csv("ledger_legs.csv") if l["post_log_no"] == LOG]
    assert len(trades) == 12 and len(legs) == 34
    assert {t["post_date"] for t in trades + legs} == {"2026-10-02"}
    assert {t["prog_ver"] for t in trades + legs} == {"1.0.43"}
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
        if t["item_no"] in CONT:
            assert t["narrative"].startswith("라벨 %s · CONTINUATION %s" % (lab, CONT[t["item_no"]])), t["item_no"]
    assert {(l["item_no"], l["leg_idx"]) for l in legs if l["leg_open_ended"] == "1"} == LEG_OPEN
    assert {(l["item_no"], l["leg_idx"]) for l in legs if l["is_loss"] == "1"} == {("2", "6"), ("6", "4")}
    labels = Counter(t["narrative"].split(" ", 2)[1] for t in trades)
    assert labels == Counter(TP=10, MIX=2), labels                         # LABELS 집계
    assert Counter(t["reg_date_precision"] for t in trades) == Counter(exact=9, none=3)   # 후속 3 = none
    assert sum(1 for t in trades if t["open_ended"] == "1") == 5
    assert sum(1 for t in trades if t["breakeven_exit"] == "1") == 6
    assert sum(1 for t in trades if t["stoploss_plan"] == "1" or t["manual_exit"] == "1") == 0
    # ⑥ 「재등록」 으로 행을 나누지 않는다 — 한컴·샌즈 각 1행
    assert sum(1 for t in trades if t["stock_name"] == "한컴위드") == 1
    assert sum(1 for t in trades if t["stock_name"] == "샌즈랩") == 1


# ---- 스크립트 모드 -------------------------------------------------------------
CASES = [
    ("P ", "양성 대조", test_P_positive, True),
    ("P2", "`~` 무판정(결과 불변)", test_P2_tilde_not_judged, True),
    ("N1", "음성 G-A", test_N1_GA, True),
    ("N2", "음성 G-B", test_N2_GB, True),
    ("N3", "음성 G-C (값)", test_N3_GC_value, True),
    ("N4", "음성 G-C (근접값 다중집합)", test_N4_GC_near_values_multiset, True),
    ("N5", "음성 G-D", test_N5_GD, True),
    ("N6", "음성 P6-G-E", test_N6_P6GE, True),
    ("N7", "음성 [parse] 선언↔원문", test_N7_declared_string_must_exist, True),
    ("N8", "음성 [parse] 미선언 산문줄", test_N8_undeclared_item_mark_line, True),
    ("N9", "음성 G-C (원장에만)", test_N9_GC_ledger_only_value, True),
    ("N10", "선언 0 이 옳다", test_N10_no_declaration_needed, False),
    ("N11", "값 줄 밖 % 불변(⑧)", test_N11_off_line_percent_not_read, True),
    ("N12", "음성 G-C (손실률 음수)", test_N12_GC_loss_value_enters_multiset, True),
    ("R1", "post9 가드 16/17 회귀(R3 제외)", test_R1_post9_guard_suite_minus_R3, True),
    ("R1b", "post9 R3 = 성장 탓 실패만", test_R1b_post9_R3_fails_only_by_growth, False),
    ("R2", "post9 게이트 실원장 회귀", test_R2_post9_gate_on_real_ledger, False),
    ("R3", "순수 append", test_R3_pure_append, False),
    ("S ", "post10 인코딩 스냅샷", test_S_post10_encoding_matches_intake, False),
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
