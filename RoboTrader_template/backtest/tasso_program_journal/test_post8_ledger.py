# -*- coding: utf-8 -*-
"""`verify_ledger_post8.py` 의 «가드 시험» — 게이트가 실제로 실패를 내는지 본다.

🔑 계열 규칙: *캡처 장치도 가드다 — 가드를 시험하지 않으면 그것도 장식이다*
(`test_post6_ledger.py` · `test_post7_ledger.py` 의 문형을 그대로 승계).
🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「통과했다」만 보이면
게이트가 항상 통과하는 장식일 수 있으므로 **일부러 깨뜨린 사본에서 실패가 나는지**도 본다.

실행: `python test_post8_ledger.py`  또는  `python -m pytest test_post8_ledger.py -q -p no:cacheprovider`
      (라이브 트리 import 0건 · DB 접속 0건)
🔑 post7 판 `test_post7_ledger.py` 는 `main()` 만 있고 `test_*` 함수가 없어 pytest 가 0건을 모은다 —
   그래서 post7 회귀는 이 파일의 R1 이 `test_post7_ledger.main()` 을 직접 불러 pytest 에 올린다.

  P   양성 대조 — 손대지 않은 원장 + 원문 ⇒ 종료코드 0 · 실패 0건
  P2  `~` 무판정 — 원문 우리기술 값 줄 끝에 `~` 를 붙여도 결과 불변
        🔑 PD-10 함정 ① (`~` 5개 중 레그 표지 1) — 이 게이트는 `~` 를 세지 않는다는 증거
  N1  G-A   원문의 항목번호를 7 → 9 로 바꿔 결번·중복을 만든다
  N2  G-B   post8 매매행 1개(액스비스)를 지운다 (원문 10 != trades 9)
  N3  G-C   post8 레그 값 17.00 → 17.01 로 바꾼다
        🔑 함정 ② 「17%」 의 선언 정규화가 «면제»가 아니라 **정규화**다
           (면제였다면 17.00 이든 17.01 이든 G-C 분모 밖이라 안 걸린다)
  N4  G-C   동률 레그 20.99 두 행 중 하나를 지우고 `n_legs` 를 3 → 2 로 맞춘다 (G-D 는 비껴간다)
        🔑 동률 레그 다중집합 보존(PD-10 2) — 집합 비교였다면 통과했을 사본이다
  N5  G-D   post8 매매건(코데즈컴바인)의 `n_legs` 를 5 → 4 로 바꾼다
  N6  P6-G-E  `fill_level=first_only` 인 행(액스비스)의 `fill_n` 을 3 으로 바꾼다
  N7  [parse] 선언한 「17%,」 를 원문에서 지운다 ⇒ 「선언 ↔ 원문 불일치」가 큰 소리로 걸려야 한다
  N8  [parse] 선언 목록에 없는 «산문» ITEM_MARK 줄을 넣는다 (post8 `NON_ITEM_LINES` = 0건)
        🔑 선언을 비워 둔 것도 가드다 — 면제 규칙을 넓히지 않았다
  N9  G-C   손실률 인라인 레그 −2.28 → 2.28 (부호) — 함정 ③ 의 값이 부호째 다중집합에 들어간다
  N10 G-C   post8 선언(`RAW_TYPO_FIX` 의 「17%,」)을 «빼고» 돌린다 ⇒ 17.0 이 원장에만 남는다
        🔑 그 선언이 장식이 아니라 «필요한» 선언이다(없으면 게이트가 실제로 떨어진다)
  R1  post7 회귀 — `test_post7_ledger.main()` 이 post8 append «뒤» 원장에서 8/8 통과
  R2  post7 회귀 — `verify_ledger_post7.main` 이 실제 원장(사본 아님)에서 통과
  R3  순수 append — 기존 75/263 데이터 행(+헤더)의 바이트 md5 = post7 판 원장 값 · 뒤에 붙은 줄은 전부 post8
  S   post8 10행/37레그가 `INTAKE_2026-09-18_post8.md` §1 · `LABELS_2026-09-18_post8.md`「원장 플래그」·
      `PREDECISION_2026-09-18_post8.md` PD-17 표와 축자 일치 (게이트가 안 보는 인코딩 칸의 스냅샷)

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
import verify_ledger_post7 as P7
import verify_ledger_post8 as P8
import test_post7_ledger as T7

BASE = Path(__file__).resolve().parent
LOG = "224416253270"
ROW = "%s,2026-09-18,1.0.42," % LOG        # post8 행 머리(post_log_no,post_date,prog_ver,)
RAW_SRC = P8.raw_path(LOG, {})             # 실제 원문(보관소) 경로

# post7 판 원장(`df62b38`)의 바이트 길이·md5 — append 뒤에도 앞부분이 이 값이어야 한다
PREFIX = {"ledger_trades.csv": (29315, "726018feca4a50dc9530130d51758368"),
          "ledger_legs.csv": (15335, "975173c833e79188cedfa96f849efd50")}


def run_gate(csv_dir: Path, raw_file: Path):
    """게이트를 «사본» 위에서 한 번 돌린다. 반환 = (종료코드, 실패목록, 출력)."""
    old_base, old_failures = V.BASE, list(P8.failures)
    V.BASE = csv_dir
    P8.failures.clear()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = P8.main(["--raw", "%s=%s" % (LOG, raw_file)])
        return rc, list(P8.failures), buf.getvalue()
    finally:
        V.BASE = old_base
        P8.failures.clear()
        P8.failures.extend(old_failures)


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
    drop_line(d / "ledger_legs.csv", ROW + "4,범한퓨얼셀,2,20.99,0,0")
    edit(d / "ledger_trades.csv", ROW + "4,범한퓨얼셀,3,0,", ROW + "4,범한퓨얼셀,2,0,")


# (tag, gate, 실패 문구 needle, 사본 깨뜨리기)
NEG = {
    "N1": ("G-A", "", lambda d: edit(d / RAW_SRC.name, "7. 헥토파이낸셜 /", "9. 헥토파이낸셜 /")),
    "N2": ("G-B", "", lambda d: drop_line(d / "ledger_trades.csv", ROW + "8,액스비스,")),
    "N3": ("G-C", "", lambda d: edit(d / "ledger_legs.csv", ROW + "3,우리로,3,17.00,0,0",
                                      ROW + "3,우리로,3,17.01,0,0")),
    "N4": ("G-C", "원문에만 있는 수치 [20.99]", _n4),
    "N5": ("G-D", "", lambda d: edit(d / "ledger_trades.csv", ROW + "9,코데즈컴바인,5,1,0,",
                                      ROW + "9,코데즈컴바인,4,1,0,")),
    "N6": ("P6-G-E", "", lambda d: edit(d / "ledger_trades.csv",
                                         ROW + "8,액스비스,2,0,0,2026-09-11,exact,first_only,1,",
                                         ROW + "8,액스비스,2,0,0,2026-09-11,exact,first_only,3,")),
    "N7": ("parse", "선언한 오기", lambda d: edit(d / RAW_SRC.name, "17%,", "17.00%,")),
    "N8": ("parse", "구분자 분해 실패", lambda d: edit(d / RAW_SRC.name, "읽어주셔서 감사합니다.",
                                                  "선언에 없는 산문 통계기반 자동매매 홍보 줄")),
    "N9": ("G-C", "", lambda d: edit(d / "ledger_legs.csv", ROW + "7,헥토파이낸셜,4,-2.28,1,0",
                                      ROW + "7,헥토파이낸셜,4,2.28,1,0")),
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
    assert "2026-09-18 224416253270: 10건(표지 10 + 산문 0) 37레그" in out
    assert "2026-09-18 224416253270: 저자번호 1..10 / 표지행 10 / **결번 0개**" in out


def test_P2_tilde_not_judged(tmp_path):
    d = fresh(tmp_path, "P2")
    edit(d / RAW_SRC.name, "8.23%, 4.75%", "8.23%, 4.75% ~")
    rc, fails, _ = run_gate(d, d / RAW_SRC.name)
    assert rc == 0 and not fails, fails


# ---- 음성 대조 ----------------------------------------------------------------
def test_N1_GA(tmp_path):
    _neg(tmp_path, "N1")


def test_N2_GB(tmp_path):
    _neg(tmp_path, "N2")


def test_N3_GC_normalized_not_exempt(tmp_path):
    _neg(tmp_path, "N3")


def test_N4_GC_tied_legs_multiset(tmp_path):
    fails = _neg(tmp_path, "N4")
    assert not [f for f in fails if not f.startswith("[G-C]")], "N4 는 G-C 만 걸려야 한다: %s" % fails


def test_N5_GD(tmp_path):
    _neg(tmp_path, "N5")


def test_N6_P6GE(tmp_path):
    _neg(tmp_path, "N6")


def test_N7_declared_string_must_exist(tmp_path):
    _neg(tmp_path, "N7")


def test_N8_undeclared_item_mark_line(tmp_path):
    _neg(tmp_path, "N8")


def test_N9_GC_inline_loss_sign(tmp_path):
    _neg(tmp_path, "N9")


def test_N10_declaration_is_load_bearing(tmp_path):
    d = fresh(tmp_path, "N10")
    keep = P8.RAW_TYPO_FIX.pop(LOG)
    try:
        rc, fails, _ = run_gate(d, d / RAW_SRC.name)
    finally:
        P8.RAW_TYPO_FIX[LOG] = keep
    hit = [f for f in fails if f.startswith("[G-C] %s: 원장에만 있는 수치 [17.0]" % LOG)]
    assert rc == 1 and hit and len(fails) == 1, fails
    _LAST[:] = [hit[0]]


# ---- post7 회귀 · 순수 append ---------------------------------------------------
def test_R1_post7_guard_suite_still_passes():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = T7.main()
    assert rc == 0, buf.getvalue()
    assert "가드 시험 8/8 통과" in buf.getvalue()


def test_R2_post7_gate_on_real_ledger():
    old = list(P7.failures)
    P7.failures.clear()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = P7.main([])
        assert rc == 0 and not P7.failures, (P7.failures, buf.getvalue())
    finally:
        P7.failures.clear()
        P7.failures.extend(old)


def test_R3_pure_append():
    for name, (n, md5) in PREFIX.items():
        b = (BASE / name).read_bytes()
        assert hashlib.md5(b[:n]).hexdigest() == md5, "%s: 기존 %d바이트가 바뀌었다" % (name, n)
        assert b"\r" not in b and b.endswith(b"\n")
        tail = b[n:].decode("utf-8").splitlines()
        assert tail and all(l.startswith(ROW) for l in tail), "%s: 뒤에 post8 아닌 줄" % name
    assert len(V.load_csv("ledger_trades.csv")) == 85 and len(V.load_csv("ledger_legs.csv")) == 300


# ---- post8 인코딩 스냅샷 (INTAKE §1 · LABELS 「원장 플래그」 · PD-17) --------------------
#  item: (종목, [레그], open_ended, reg_date, precision, fill_level, fill_n, preset, manual, breakeven, stoploss, 라벨)
EXPECT = {
    1: ("빛과전자", [23.47, 17.88], "0", "", "none", "first_only", "1", "표준형/HDR60", "0", "0", "0", "TP"),
    2: ("로보티즈", [17.95, 16.74], "0", "", "none", "first_only", "1", "표준형/HDR60", "1", "0", "0", "MANUAL"),
    3: ("우리로", [24.20, 19.94, 17.00, 16.26, 13.32, 12.44, 0.54], "0", "2026-09-11", "exact", "first_only", "1",
        "표준형/HDR60", "0", "1", "0", "TP"),
    4: ("범한퓨얼셀", [20.99, 20.99, 0.43], "0", "", "none", "first_only", "1", "표준형/HDR60", "0", "1", "0", "TP"),
    5: ("원익", [19.49, 17.61, 15.54, 13.14], "0", "", "none", "first_only", "1", "표준형/HDR60", "1", "0", "0",
        "MANUAL"),
    6: ("JW신약", [16.28, 12.68, 11.05, 10.78], "0", "2026-09-01", "exact", "first_only", "1", "표준형/HDR60",
        "1", "0", "0", "MANUAL"),
    7: ("헥토파이낸셜", [5.84, 2.98, 1.39, -2.28], "0", "", "approx", "first_only", "1", "표준형/HDR60",
        "0", "1", "0", "MIX"),
    8: ("액스비스", [11.64, 0.31], "0", "2026-09-11", "exact", "first_only", "1", "표준형/HDR60", "0", "1", "0", "TP"),
    9: ("코데즈컴바인", [13.20, 11.05, 11.03, 8.71, 6.59], "1", "", "approx", "partial", "2", "표준형/사분위수",
        "0", "0", "0", "TP"),
    10: ("우리기술", [8.47, 8.47, 8.23, 4.75], "1", "2026-09-09", "exact", "first_only", "1", "표준형/HDR60",
         "0", "0", "0", "TP"),
}
LEG_OPEN = {("3", "7"), ("9", "5"), ("10", "4")}     # 우리로 0.54(`~` ∧ 완결 · PD-5 1) · 코데즈·우리기술 마지막
LEG_LOSS = {("7", "4")}                              # 헥토 −2.28(「손실률」)


def test_S_post8_encoding_matches_intake():
    trades = [t for t in V.load_csv("ledger_trades.csv") if t["post_log_no"] == LOG]
    legs = [l for l in V.load_csv("ledger_legs.csv") if l["post_log_no"] == LOG]
    assert len(trades) == 10 and len(legs) == 37
    assert {t["post_date"] for t in trades + legs} == {"2026-09-18"}
    assert {t["prog_ver"] for t in trades + legs} == {"1.0.42"}
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
    assert {(l["item_no"], l["leg_idx"]) for l in legs if l["is_loss"] == "1"} == LEG_LOSS
    labels = Counter(t["narrative"].split(" ", 2)[1] for t in trades)
    assert labels == Counter(TP=6, MANUAL=3, MIX=1), labels            # LABELS 집계
    assert sum(len(v[1]) for k, v in EXPECT.items() if k in (1, 2, 4)) == 7   # 후속 3건 7레그
    assert "「17%」" in [t for t in trades if t["item_no"] == "3"][0]["narrative"]   # 원 표기 보존


# ---- 스크립트 모드 -------------------------------------------------------------
CASES = [
    ("P ", "양성 대조", test_P_positive, True),
    ("P2", "`~` 무판정(결과 불변)", test_P2_tilde_not_judged, True),
    ("N1", "음성 G-A", test_N1_GA, True),
    ("N2", "음성 G-B", test_N2_GB, True),
    ("N3", "음성 G-C (17% 정규화)", test_N3_GC_normalized_not_exempt, True),
    ("N4", "음성 G-C (동률 다중집합)", test_N4_GC_tied_legs_multiset, True),
    ("N5", "음성 G-D", test_N5_GD, True),
    ("N6", "음성 P6-G-E", test_N6_P6GE, True),
    ("N7", "음성 [parse] 선언↔원문", test_N7_declared_string_must_exist, True),
    ("N8", "음성 [parse] 미선언 산문줄", test_N8_undeclared_item_mark_line, True),
    ("N9", "음성 G-C (손실률 부호)", test_N9_GC_inline_loss_sign, True),
    ("N10", "음성 G-C (선언 제거)", test_N10_declaration_is_load_bearing, True),
    ("R1", "post7 가드 8/8 회귀", test_R1_post7_guard_suite_still_passes, False),
    ("R2", "post7 게이트 실원장 회귀", test_R2_post7_gate_on_real_ledger, False),
    ("R3", "순수 append", test_R3_pure_append, False),
    ("S ", "post8 인코딩 스냅샷", test_S_post8_encoding_matches_intake, False),
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
