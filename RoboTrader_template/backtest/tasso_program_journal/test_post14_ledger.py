# -*- coding: utf-8 -*-
"""`verify_ledger_post14.py` 의 «가드 시험» — 게이트가 실제로 실패를 내는지 본다 (post13 판 승계).

🔑 계열 규칙: *캡처 장치도 가드다 — 가드를 시험하지 않으면 그것도 장식이다* · *단독 단언은 판별력이 없다 → 대칭 단언*.

실행: `python test_post14_ledger.py`  또는  `python -m pytest test_post14_ledger.py -q -p no:cacheprovider`
      (라이브 트리 import 0건 · DB 접속 0건 · 러너 실행 0건)

  P   양성 대조 · P2 `~` 무판정(값 줄 끝 `~` 를 붙여도 결과 불변)
  N1 G-A · N2 G-B · N3 G-C(값) · N4 G-C(부호 뒤집기 — 이번 글은 음수 레그 0 이라 양수 레그의 부호를 뒤집는다)
  N5 G-D · N6 P6-G-E · N7/N8 [parse] · N9 G-C(원장에만)
  N10 선언 0 이 옳다 · N11 값 줄 밖 `%` 불변 · N12 G-C(레그 삭제 — 멜콘 0.28)
  R1  post13 회귀 — `test_post13_ledger` 19건 중 R3 를 뺀 18건이 post14 append «뒤» 원장에서 통과
  R2  post13 게이트 실원장 통과 · R3 순수 append(기존 127/438 행 바이트 md5 불변 · 뒤는 전부 post14 · 129/446)
  S   post14 2행/8레그 인코딩 스냅샷(INTAKE §1 · LABELS · PREDECISION)

🔴 post14 는 «손실률» 음수 레그가 0 이라 post13 N4/N12 의 음수 레그 대응물이 없다 — N4 는 부호 뒤집기, N12 는 양수 레그 삭제로 대체.
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
import verify_ledger_post13 as P13
import verify_ledger_post14 as P14
import test_post12_ledger as T12
import test_post13_ledger as T13

BASE = Path(__file__).resolve().parent
LOG = "224460275556"
ROW = "%s,2026-10-31,," % LOG              # post14 행 머리(prog_ver 빈칸)(post_log_no,post_date,prog_ver,)
RAW_SRC = P14.raw_path(LOG, {})            # 실제 원문(보관소) 경로

# post13 판 원장(`f1c2414` 시점 HEAD · 실측 크기·md5) — append 뒤에도 앞부분이 이 값이어야 한다
PREFIX = {"ledger_trades.csv": (81282, "934043c6ed3ecde240c2788d5fc653a5"),
          "ledger_legs.csv": (25175, "21086509bf48998006d6a6656b35822c")}


def run_gate(csv_dir: Path, raw_file: Path):
    """게이트를 «사본» 위에서 한 번 돌린다. 반환 = (종료코드, 실패목록, 출력)."""
    old_base, old_failures = V.BASE, list(P14.failures)
    V.BASE = csv_dir
    P14.failures.clear()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = P14.main(["--raw", "%s=%s" % (LOG, raw_file)])
        return rc, list(P14.failures), buf.getvalue()
    finally:
        V.BASE = old_base
        P14.failures.clear()
        P14.failures.extend(old_failures)


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
    edit(d / "ledger_legs.csv", ROW + "1,삼기에너지솔루션즈,1,22.33,0,0", ROW + "1,삼기에너지솔루션즈,1,-22.33,0,0")


def _n9(d):
    edit(d / "ledger_legs.csv", ROW + "2,멜콘,4,0.28,0,0\n",
         ROW + "2,멜콘,4,0.28,0,0\n" + ROW + "2,멜콘,5,0.38,0,0\n")
    edit(d / "ledger_trades.csv", ROW + "2,멜콘,4,0,", ROW + "2,멜콘,5,0,")


def _n12(d):
    drop_line(d / "ledger_legs.csv", ROW + "2,멜콘,4,0.28,0,0")
    edit(d / "ledger_trades.csv", ROW + "2,멜콘,4,0,", ROW + "2,멜콘,3,0,")


# (tag, gate, 실패 문구 needle, 사본 깨뜨리기)
NEG = {
    "N1": ("G-A", "결번 [2]", lambda d: edit(d / RAW_SRC.name, "2. 멜콘 /", "11. 멜콘 /")),
    "N2": ("G-B", "", lambda d: drop_line(d / "ledger_trades.csv", ROW + "2,멜콘,")),
    "N3": ("G-C", "원문에만 있는 수치 [22.33]",
           lambda d: edit(d / "ledger_legs.csv", ROW + "1,삼기에너지솔루션즈,1,22.33,0,0",
                          ROW + "1,삼기에너지솔루션즈,1,22.34,0,0")),
    "N4": ("G-C", "원문에만 있는 수치 [22.33]", _n4),
    "N5": ("G-D", "", lambda d: edit(d / "ledger_trades.csv", ROW + "1,삼기에너지솔루션즈,4,0,",
                                     ROW + "1,삼기에너지솔루션즈,5,0,")),
    "N6": ("P6-G-E", "", lambda d: edit(d / "ledger_trades.csv",
                                         ROW + "1,삼기에너지솔루션즈,4,0,0,2026-10-19,exact,first_only,1,",
                                         ROW + "1,삼기에너지솔루션즈,4,0,0,2026-10-19,exact,first_only,4,")),
    "N8": ("parse", "구분자 분해 실패", lambda d: edit(d / RAW_SRC.name, "이번 주 정말 고생 많으셨습니다.",
                                                  "선언에 없는 산문 통계기반 자동매매 홍보 줄 이번 주 정말 고생 많으셨습니다.")),
    "N9": ("G-C", "원장에만 있는 수치 [0.38]", _n9),
    "N12": ("G-C", "원문에만 있는 수치 [0.28]", _n12),
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
    assert "2026-10-31 224460275556: 2건(표지 2 + 산문 0) 8레그" in out
    assert "2026-10-31 224460275556: 저자번호 1..2 / 표지행 2 / **결번 0개**" in out


def test_P2_tilde_not_judged(tmp_path):
    d = fresh(tmp_path, "P2")
    edit(d / RAW_SRC.name, "1.04%, 1.03%, 0.45%, 0.28%", "1.04%, 1.03%, 0.45%, 0.28% ~")
    rc, fails, _ = run_gate(d, d / RAW_SRC.name)
    assert rc == 0 and not fails, fails


# ---- 음성 대조 ----------------------------------------------------------------
def test_N1_GA(tmp_path):
    _neg(tmp_path, "N1")


def test_N2_GB(tmp_path):
    _neg(tmp_path, "N2")


def test_N3_GC_value(tmp_path):
    _neg(tmp_path, "N3")


def test_N4_GC_sign_flip(tmp_path):
    fails = _neg(tmp_path, "N4")
    assert not [f for f in fails if not f.startswith("[G-C]")], "N4 는 G-C 만 걸려야 한다: %s" % fails


def test_N5_GD(tmp_path):
    _neg(tmp_path, "N5")


def test_N6_P6GE(tmp_path):
    _neg(tmp_path, "N6")


def test_N7_declared_string_must_exist(tmp_path):
    d = fresh(tmp_path, "N7")
    assert LOG not in P14.RAW_TYPO_FIX
    P14.RAW_TYPO_FIX[LOG] = [("선언했지만 원문에 없는 문자열", "x")]
    try:
        rc, fails, _ = run_gate(d, d / RAW_SRC.name)
    finally:
        del P14.RAW_TYPO_FIX[LOG]
    hit = [f for f in fails if f.startswith("[parse] %s: 선언한 오기" % LOG)]
    assert rc == 1 and hit, fails
    _LAST[:] = [hit[0]]


def test_N8_undeclared_item_mark_line(tmp_path):
    _neg(tmp_path, "N8")


def test_N9_GC_ledger_only_value(tmp_path):
    fails = _neg(tmp_path, "N9")
    assert not [f for f in fails if not f.startswith("[G-C]")], "N9 는 G-C 만 걸려야 한다: %s" % fails


def test_N10_no_declaration_needed():
    assert LOG not in P14.RAW_TYPO_FIX and LOG not in P14.NON_ITEM_LINES and LOG not in P14.EXTRA_PROSE_ITEMS
    assert V.PCT_RE.findall("수익률 17.60%, 17.60%, 0.32% ~, 손실률 -0.49%") == ["17.60", "17.60", "0.32", "-0.49"]


def test_N11_off_line_percent_not_read(tmp_path):
    d = fresh(tmp_path, "N11")
    edit(d / RAW_SRC.name, "본전 위협에 전량매도", "본전 위협에 전량매도 +99.99%")
    rc, fails, _ = run_gate(d, d / RAW_SRC.name)
    assert rc == 0 and not fails, fails


def test_N12_GC_leg_deleted(tmp_path):
    _neg(tmp_path, "N12")


# ---- post13 회귀 · 순수 append ---------------------------------------------------
def test_R1_post13_guard_suite_minus_R3(tmp_path):
    ran = []
    for i, (tag, _desc, fn, needs_tmp) in enumerate(T13.CASES):
        if tag.strip() == "R3":
            continue
        if needs_tmp:
            t = tmp_path / ("t13_%02d" % i)
            t.mkdir()
            fn(t)
        else:
            fn()
        ran.append(tag.strip())
    T13._LAST.clear()
    assert len(ran) == len(T13.CASES) - 1 == 18, ran


def test_R1b_post13_prefix_unchanged_after_growth():
    # post13 의 R3(`T13.test_R3_pure_append`)는 행 수(127/438)를 단언해 post14 append 뒤 «성장 탓» 으로 실패한다
    # (옛 시험은 이 단계에서 고치지 않는다). 대신 같은 술어를 «post13 상태 prefix 불변 + 뒤는 전부 post14» 로 직접 단언한다.
    for name, (n, md5) in PREFIX.items():
        b = (BASE / name).read_bytes()
        assert hashlib.md5(b[:n]).hexdigest() == md5, name
        n12, md512 = T13.PREFIX[name]
        assert hashlib.md5(b[:n12]).hexdigest() == md512, name
        mid = b[n12:n].decode("utf-8").splitlines()
        assert mid and all(l.startswith(T13.ROW) for l in mid), name


def test_R2_post13_gate_on_real_ledger():
    old = list(P13.failures)
    P13.failures.clear()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = P13.main([])
        assert rc == 0 and not P13.failures, (P13.failures, buf.getvalue())
    finally:
        P13.failures.clear()
        P13.failures.extend(old)


def test_R3_pure_append():
    for name, (n, md5) in PREFIX.items():
        b = (BASE / name).read_bytes()
        assert hashlib.md5(b[:n]).hexdigest() == md5, "%s: 기존 %d바이트가 바뀌었다" % (name, n)
        assert b"\r" not in b and b.endswith(b"\n")
        tail = b[n:].decode("utf-8").splitlines()
        assert tail and all(l.startswith(ROW) for l in tail), "%s: 뒤에 post14 아닌 줄" % name
    assert len(V.load_csv("ledger_trades.csv")) == 129 and len(V.load_csv("ledger_legs.csv")) == 446


# ---- post14 인코딩 스냅샷 (INTAKE §1 · LABELS · PD-5·PD-13) ------------------------
#  item: (종목, [레그], open_ended, reg_date, precision, fill_level, fill_n, preset, manual, breakeven, stoploss, 라벨)
H60 = "표준형/HDR60"
EXPECT = {
    1: ("삼기에너지솔루션즈", [22.33, 18.02, 12.84, 8.33], "0", "2026-10-19", "exact", "first_only", "1", H60,
        "0", "0", "0", "TP"),
    2: ("멜콘", [1.04, 1.03, 0.45, 0.28], "0", "2026-10-28", "exact", "partial", "4", H60, "0", "1", "0", "TP"),
}
# leg_open_ended: 전 레그 0 (LABELS 완결 2/2 · 값 줄 끝 `~` 0)
LEG_OPEN = set()
CONT = {}                                                        # 후속 0건(PD14-2)
REENTRY = {"1"}                                                  # 재진입 exact 1건(PD14-3 · 🔒 #1 A 삼기에너지솔루션즈)
LOSS_LEGS = set()                                                # 「손실률」 레그 0


def test_S_post14_encoding_matches_intake():
    trades = [t for t in V.load_csv("ledger_trades.csv") if t["post_log_no"] == LOG]
    legs = [l for l in V.load_csv("ledger_legs.csv") if l["post_log_no"] == LOG]
    assert len(trades) == 2 and len(legs) == 8
    assert {t["post_date"] for t in trades + legs} == {"2026-10-31"}
    assert {t["prog_ver"] for t in trades + legs} == {""}                      # PD-8 결측 2/2
    for t in trades:
        nm, lg, oe, rd, pr, fl, fn, ps, ma, be, sl, lab = EXPECT[int(t["item_no"])]
        al = "1" if lab == "SL" else "0"
        got = (t["stock_name"], int(t["n_legs"]), t["open_ended"], t["all_loss"], t["reg_date"],
               t["reg_date_precision"], t["fill_level"], t["fill_n"], t["preset"],
               t["manual_exit"], t["breakeven_exit"], t["stoploss_plan"])
        assert got == (nm, len(lg), oe, al, rd, pr, fl, fn, ps, ma, be, sl), (t["item_no"], got)
        assert t["narrative"].startswith("라벨 %s" % lab), (t["item_no"], t["narrative"][:20])
        seq = [float(l["ret_pct"]) for l in legs if l["item_no"] == t["item_no"]]
        idx = [l["leg_idx"] for l in legs if l["item_no"] == t["item_no"]]
        assert seq == lg and idx == [str(i) for i in range(1, len(lg) + 1)], (nm, seq, idx)
        if t["item_no"] in CONT:
            assert " · CONTINUATION %s" % CONT[t["item_no"]] in t["narrative"][:60], t["item_no"]
        else:
            assert "CONTINUATION" not in t["narrative"], t["item_no"]
        assert ("🔂 재진입" in t["narrative"]) == (t["item_no"] in REENTRY), t["item_no"]
    assert {(l["item_no"], l["leg_idx"]) for l in legs if l["leg_open_ended"] == "1"} == LEG_OPEN
    assert {(l["item_no"], l["leg_idx"]) for l in legs if l["is_loss"] == "1"} == LOSS_LEGS
    labels = Counter(t["narrative"].split(" ", 2)[1].split("(")[0] for t in trades)
    assert labels == Counter(TP=2), labels                                     # LABELS 집계
    assert Counter(t["reg_date_precision"] for t in trades) == Counter(exact=2)   # 신규 exact 2 · none 0
    assert sum(1 for t in trades if t["breakeven_exit"] == "1") == 1
    assert sum(1 for t in trades if t["manual_exit"] == "1") == 0
    assert sum(1 for t in trades if t["stoploss_plan"] == "1") == 0
    assert sum(1 for t in trades if t["open_ended"] == "1") == 0               # 완결 2/2
    assert "약한 자리" in [t for t in trades if t["stock_name"] == "삼기에너지솔루션즈"][0]["narrative"]
    assert "약한 자리" not in [t for t in trades if t["stock_name"] == "멜콘"][0]["narrative"]   # 약한 자리 1(F-6)


# ---- 스크립트 모드 -------------------------------------------------------------
CASES = [
    ("P ", "양성 대조", test_P_positive, True),
    ("P2", "`~` 무판정(결과 불변)", test_P2_tilde_not_judged, True),
    ("N1", "음성 G-A", test_N1_GA, True),
    ("N2", "음성 G-B", test_N2_GB, True),
    ("N3", "음성 G-C (값)", test_N3_GC_value, True),
    ("N4", "음성 G-C (부호 뒤집기)", test_N4_GC_sign_flip, True),
    ("N5", "음성 G-D", test_N5_GD, True),
    ("N6", "음성 P6-G-E", test_N6_P6GE, True),
    ("N7", "음성 [parse] 선언↔원문", test_N7_declared_string_must_exist, True),
    ("N8", "음성 [parse] 미선언 산문줄", test_N8_undeclared_item_mark_line, True),
    ("N9", "음성 G-C (원장에만)", test_N9_GC_ledger_only_value, True),
    ("N10", "선언 0 이 옳다", test_N10_no_declaration_needed, False),
    ("N11", "값 줄 밖 % 불변", test_N11_off_line_percent_not_read, True),
    ("N12", "음성 G-C (레그 삭제)", test_N12_GC_leg_deleted, True),
    ("R1", "post13 가드 18/19 회귀(R3 제외)", test_R1_post13_guard_suite_minus_R3, True),
    ("R1b", "post13 prefix 불변(성장 후)", test_R1b_post13_prefix_unchanged_after_growth, False),
    ("R2", "post13 게이트 실원장 회귀", test_R2_post13_gate_on_real_ledger, False),
    ("R3", "순수 append", test_R3_pure_append, False),
    ("S ", "post14 인코딩 스냅샷", test_S_post14_encoding_matches_intake, False),
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
