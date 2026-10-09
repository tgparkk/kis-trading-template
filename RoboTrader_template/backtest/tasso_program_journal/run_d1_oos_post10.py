# -*- coding: utf-8 -*-
"""10번째 글 `TV`(= `trading_value / market_cap`) 자가보고 재검정 — **자가보고 0건 ⇒ 축 전체 «미룸»**(6글 연속).

`run_d1_oos_post9.py`(→ `run_d1_oos_post8.py` → `run_d1_oos_post7.py`) 승계 · 원본 불변. 정의(`PREREG_D1_OOS.md` §2)·허용오차·문언 부류 규칙은
**한 글자도 바꾸지 않는다** · 판정표 문형(`ITEMS`)·누적(`PRIOR`)·13항목 상태(`STATUS`)는 **import 해 그대로** 쓰고
이번 글 한 줄만 덧붙인다.

동결 준거(계산 «전» 고정): `PREREG_D1_OOS.md` §2~§4 · `PREREG_POST6.md` §1-3(부류 A~F) · §6 · `PREREG_POST10.md` ·
  `PREREG_POST8.md` §0-5-1 · `D-3` · `D-5` · `D-9` · `PREDECISION_2026-10-04_post10.md` **PD-6**(`TV` 0건 ⇒ 13항목 미룸 ·
  연속 두 단위(6글 / 5글) · `P6-W10` 창 규약 용도 없음) · PD-1 · `INTAKE_2026-10-04_post10.md` §5 「`TV-`」 행(`F-3` 대상 아니오 · 판정 0).

🔴 부류 A~F 해당 0 ⇒ `TV-W1`~`W9` · `P6-W10` · `TV-N1`~`N3` **전부 ⛔ 「미룬다」** — ***규칙을 넓혀 열지 않는다.***
🔴 가격을 읽지 않는다 — DB 조회는 `D-9` 박제용 타임스탬프·행수뿐(SELECT). 이 레인은 `PREREG_POST8.md:544` 의 대상 밖이나
   공통 지시에 따라 `D-9` ① 을 `d1_oos_post10/read_stamp.json`(키 `first_read_kst`·`timezone`·`fingerprint` ·
   지문 같으면 다시 쓰지 않는다)로 더 많이 인쇄한다(`P9-스탬프통일` · PD-35).
🔴 누적은 직전 문서의 확정치를 그대로 인쇄 · 새 예측 0 · 등급 이름 0 · 라이브 채택 아님.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import psycopg2

import run_d1_oos_post7 as D7
import run_d1_oos_post8 as D8
import run_d1_oos_post9 as D9
from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
OUT_NAME = "RESULTS_D1_OOS_POST10_NUMBERS.md"
STAMP_DIR = "d1_oos_post10"

DB_UPTO = "2026-10-02"             # PD-1 (이 레인은 창을 만들지 않는다 · 옮겨 적은 값)
WIN = ("2026-08-12", "2026-10-02")  # 창 구간(`D-9` ②④ 기록용 · 브리프 A-1)
DPLUS1_SWEEP = "2026-10-06 15:35"
DEFER_STREAK = 6                   # `TV-W1`·`W2` 미룸 = 5~10번째(PD-6)
ZERO_STREAK = 5                    # 종목 단위 자가보고 0건 = 6~10번째(PD-6 · post8 §6 정오표 ⑨ 셈 단위)
LIVE_BAN = ("*「🔴 **라이브 채택 금지.** 저자가 *\"사람이 할 일은 종목 고르는 것까지\"* 라고 적었다. "
            "후보 선정이 재량이면 규칙을 복원해도 자동화 대상이 아니다. 이 검정의 산출물은 **기록**이지 "
            "전략 후보가 아니다.」*")
WINDOW_LINE = ("창 종료 2026-10-02 = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · "
               "전 축(`WRC-` 포함) · PD-1")

CLASSES = D8.CLASSES               # 부류 A~F 전부 0 (INTAKE §3 표 — post8 과 같은 0 행)
AUX_ZERO = D8.AUX_ZERO             # `TV-W8`·`TV-W9` 대상 0
GREP_WORDS = [("거래대금", 0), ("배", 0), ("시총", 0)]       # `post_224429747319.txt` · PD-6(`probes/p10_textgrep.txt`)
GREP_LINES = []                                              # 「거래대금」 자리 0
TV_W9_BLOCK = ("신규주 자가보고 < 2 ⇒ **이번 0 < 2** (🔴 이번 글 종목 단위 `TV` 진술 자체가 0 · 신규 `exact` 종목의 DB 첫 봉은 "
               "기록만 — 상장일 판정 안 함)")

REQUIRED = (WINDOW_LINE, "실행 시 `max(date)`", LIVE_BAN, "0건 · 미룸", "`D-9` ①", "`D-9` ②", "`D-9` ③", "`D-9` ④", "`D-9` ⑤",
            "`approx` 포함 시 최소 n 이 차는 축:", "`D-5`", "`P9-공통독법`: 답 = 판정 · (나)4 결과 = ", "`P9-행단위`",
            "라이브 채택 대상이 아니다")


def say(s=""):
    print(s)
    OUT.append(s)


def note(s=""):
    print(s)


def assert_duties(lines):
    body = "\n".join(lines)
    miss = [m for m in REQUIRED if m not in body]
    if miss:
        raise AssertionError("🔴 인쇄 의무 누락: %s" % miss)
    return True


def read_stamp(cur, base=None):
    """`D-9` ① — 이 DB 지문을 이 스크립트가 «처음» 읽은 실행의 KST 시각(같은 지문이면 파일을 다시 쓰지 않는다)."""
    cur.execute("SELECT max(date) FROM daily_prices")
    mx = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (mx,))
    mx_rows = int(cur.fetchone()[0])
    cur.execute("SELECT count(*), min(updated_at), max(updated_at) FROM daily_prices WHERE date BETWEEN %s AND %s", WIN)
    w_n, w_min, w_max = cur.fetchone()
    fp = dict(max_date=str(mx), max_rows=mx_rows, win=list(WIN), win_n=int(w_n), win_min_u=str(w_min),
              win_max_u=str(w_max))
    cur.execute("SELECT to_char(now() AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS')")
    now_kst = cur.fetchone()[0]
    d = (base or BASE) / STAMP_DIR
    p = d / "read_stamp.json"
    prev = None
    if p.exists():
        try:
            prev = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev = None
    if prev and prev.get("fingerprint") == fp and prev.get("first_read_kst"):
        return prev["first_read_kst"], now_kst, True, fp
    d.mkdir(exist_ok=True)
    p.write_text(json.dumps(dict(fingerprint=fp, first_read_kst=now_kst, timezone="Asia/Seoul"),
                            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return now_kst, now_kst, False, fp


def status10():
    """13항목 상태 — post9 표(`D9.status9()`)의 이력에 9번째를 붙이고 10번째 칸을 더한다(전부 미룸 · 연속 +1)."""
    return [(lbl, src, first, f"{hist} · 9 {now9}", "미룸", streak + 1)
            for lbl, src, first, hist, now9, streak in D9.status9()]


def main():  # noqa: C901
    t0 = time.time()
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    first_kst, now_kst, reused, fp = read_stamp(cur)
    conn.close()
    if first_kst < DPLUS1_SWEEP:
        raise SystemExit("🔴 착수 조건 미충족 — 10-02 봉은 아직 D 빈티지다(PD-27 (마)).")

    say("# RESULTS_D1_OOS_POST10_NUMBERS — 기계 생성 (수정 금지)\n")
    say("**TV: 0건 · 미룸**(연속 두 단위 — `TV-W1`·`W2` 미룸 6글 연속 · 종목 단위 자가보고 0건 5글 연속)\n")
    say("정의 `PREREG_D1_OOS.md` §2(동결분 그대로) · 문언 부류 "
        "[`PREDECISION_2026-10-04_post10.md`](PREDECISION_2026-10-04_post10.md) **PD-6**(계산 «전» 동결) · "
        "`PREREG_POST10.md`(동결 `522d6dc`) · `PREREG_POST9.md` · `PREREG_POST8.md`(동결 `04cd785`) · 생성 `run_d1_oos_post10.py` "
        "(`run_d1_oos_post9.py`·`run_d1_oos_post8.py`·`run_d1_oos_post7.py` 승계 · 원본 불변)")
    say("")
    say(f"> {LIVE_BAN}")
    say("> (`PREREG_POST10.md:56` · `PREREG.md:15` 문언 그대로) — 🔴 이 분석은 **라이브 채택 대상이 아니다**.")
    say("")
    say("## §0. 실행 환경 · 동결 규약\n")
    say("| 항목 | 값 |")
    say("|---|---|")
    say("| 판정 대상 | 🔴 **0건** — 종목 단위 `TV` 자가보고가 이 글에 «없다»(PD-6) |")
    say("| DB | 🔴 **가격 조회 0회** — `trading_value`·`market_cap`·`high`·`low` 를 읽지 않았다 · 조회는 `D-9` 박제용 "
        "**타임스탬프·행수**뿐(SELECT) |")
    say(f"| 🔴 창 종료 | **{WINDOW_LINE}** — 이 레인은 창을 만들지 않는다(옮겨 적은 값) |")
    say(f"| 🔴 실행 시 스냅샷 | **실행 시 `max(date)` = {fp['max_date']} · 그 날짜 행수 {fp['max_rows']:,} — 기록만(창 아님)** |")
    say(f"| 허용오차 · 시드 · NREP | ±{D7.TOL*100:.0f}%(고치지 않는다) · **{D7.SEED}**(난수 미사용) · 승계 원본에 `NREP` 없음 |")
    say("| 라이브 | 🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST10.md`) |")
    say("")
    say("### 0-1. 공통 인쇄 의무 (`PREREG_POST8.md` · `PREREG_POST9.md`)\n")
    say("| 의무 | 이 산출물 |")
    say("|---|---|")
    say(f"| `D-9` ① 쿼리 실행 시각(KST) | **{first_kst}** — 이 DB 지문(`max(date)`·그 날 행수·창 구간 `[{WIN[0]}, {WIN[1]}]` "
        f"행수·`min/max(updated_at)`)을 이 스크립트가 «처음» 읽은 실행의 DB `now()` · `{STAMP_DIR}/read_stamp.json`"
        "(같은 지문 재실행 = 같은 값) · 🔴 이 레인은 `PREREG_POST8.md:544` 대상 밖 — 공통 지시에 따른 «더 많이 인쇄»"
        "(`P9-스탬프통일` · PD-35) |")
    say(f"| `D-9` ② 창 구간 `max(updated_at)` | `[{WIN[0]}, {WIN[1]}]` **{fp['win_max_u']}** |")
    say("| `D-9` ③ | **10-02 봉은 D+1(10-06) sweep 이후 읽음** — 🔴 이 레인은 그 봉의 가격을 **읽지 않는다** |")
    say(f"| `D-9` ④ (기록 · 통과 조건 아님) | 창 구간 `min(updated_at)` = **{fp['win_min_u']} ≥ {DPLUS1_SWEEP}: "
        f"{'예' if fp['win_min_u'] >= DPLUS1_SWEEP else '아니오'}** |")
    say("| `D-9` ⑤ `P8-혼합빈티지신고` | **걸침 창 없음** — 자가보고 0건 ⇒ 측정 A·B 창 0개 |")
    say("| `D-3` | *「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 0 / `approx` 포함 분모 0」* — `TV` 분모는 "
        "**자가보고 진술**이고 0건이다(등록일 정밀도와 무관) |")
    say("| `P9-공통독법` | `P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`TV` 분모 = 자가보고 진술 · 등록일 정밀도 갈래가 "
        "생기지 않는다 · `F-3` 대상 아니오 · 판정 0 — 더 많이 인쇄) |")
    say("| `D-5` | 갈래 **없음** — 13항목 전부 `(주, 0, 미룸)` 한 쪽뿐 · §2 표 |")
    say("| `D-6`·`D-8`·`P9-행단위`·`D-11` | 해당 없음(`n_up` 미사용 · `prog_ver` 공변량 미사용 = 수준 목록 없음 · `Q1-R2` 미인용) |")
    say("")
    say("🔴 **규칙을 넓히지 않는다.** 부류가 0이면 그 축은 미룬다(`PREREG_POST6.md` §6 · `RESULTS_D1_OOS.md` §5). "
        "🔴 새 예측을 만들지 않는다(`PREREG_POST6.md` §7-B #11) · 등급 이름을 적지 않는다(§6 단계).")
    say("")

    say("## §1. 자가보고 — **0건** (PD-6 · INTAKE §3)\n")
    say("| 부류 (`PREREG_POST6.md` §1-3) | 이름 | 건 |")
    say("|---|---|---|")
    for k, nm, n in CLASSES:
        say(f"| {k} | {nm} | **{n}** |")
    say("")
    say("| 그 밖의 대상 | 건 |")
    say("|---|---|")
    for nm, n in AUX_ZERO:
        say(f"| {nm} | **{n}** |")
    say("")
    say("| grep 실측 낱말 (`post_224429747319.txt`) | 건 |")
    say("|---|---|")
    for w, n in GREP_WORDS:
        say(f"| 「{w}」 | **{n}** |")
    say("")
    say("| 「거래대금」 자리(txt 줄) | 원문(축자) | 성격 |")
    say("|---|---|---|")
    for ln, txt, kind in GREP_LINES:
        say(f"| :{ln} | *「{txt}」* | {kind} |")
    if not GREP_LINES:
        say("| — | (없음 — 「거래대금」 0) | — |")
    say("")
    tot = sum(n for _k, _nm, n in CLASSES) + sum(n for _nm, n in AUX_ZERO)
    say(f"⇒ **합계 {tot}건.** 부류 A~F 는 전부 **「N배」 수치**를 요구한다(`PREREG_POST6.md:168-175`) ⇒ 그 한 자리는 **해당 0**"
        "(post8·post9 PD-6 과 같은 처리).")
    say("")

    say("## §2. 판정 — 「**0건 · 미룸**」 · `TV-W1`~`W9` · `P6-W10` · `TV-N1`~`N3` **13항목 전부 ⛔ 「미룬다」**\n")
    say("| 항목 | 가설(한 줄) | 문턱 (출처 파일) | 최소 n | 이번 해당 건 | **판정** | 대칭/반증 쌍 | "
        "⛔ 경로 · 민감도 · `D-5` `(갈래, n, 답)` |")
    say("|---|---|---|---|---|---|---|---|")
    for lbl, hyp, thr, minn, pair, block in D7.ITEMS:
        blk = TV_W9_BLOCK if lbl == "`TV-W9`" else block
        say(f"| {lbl} | {hyp} | {thr} | {minn} | **0** | ⛔ **미룬다** | {pair} | {blk} · 민감도 = **없음** · "
            "`(주, 0, 미룸)` |")
    say("")
    say(f"⇒ **{len(D7.ITEMS)}개 항목 전부 ⛔ 「미룬다」.** ***0건은 「예측이 틀렸다」가 아니라 「잴 것이 없었다」다.***")
    say("")
    say("### §2-1. `P6-W10` 의 두 용도 — 한 수로 합치지 않는다 (PD-6)\n")
    say("| 용도 | 이번 회차 | 이 산출물의 처리 |")
    say("|---|---|---|")
    say("| (가) `TV` 축 무작위 **창** 귀무 | 구간 건 **0** · C 부류 **0** | ⛔ **미룬다**(위 표) |")
    say("| (나) `PREREG_POST6.md` §1-4 **창 규약**의 귀무 | 🔴 **대상 없음** — `approx` **0**(PD-4)이라 §1-4 창 규약이 발동하지 "
        "않는다(PD-6) | 인쇄할 값 없음(기록) |")
    say("")

    say("## §3. 누적 재현 — **불변** (🔴 탐색적 · 어느 사전등록 문턱에도 걸려 있지 않다)\n")
    say("| 글 | 판정 대상 | 재현 | 비고 |")
    say("|---|---|---|---|")
    for nm, n, hit, memo in D7.PRIOR:
        say(f"| {nm} | {n} | **{hit}** | {memo} |")
    say("| 7번째 글 (`RESULTS_D1_OOS_POST7_NUMBERS.md` §3) | 0 | **—** | 🔴 자가보고 0건 ⇒ 분모 밖 |")
    say("| 8번째 글 (`RESULTS_D1_OOS_POST8_NUMBERS.md` §3) | 0 | **—** | 🔴 자가보고 0건 ⇒ 분모 밖 |")
    say("| 9번째 글 (`RESULTS_D1_OOS_POST9_NUMBERS.md` §3) | 0 | **—** | 🔴 자가보고 0건 ⇒ 분모 밖 |")
    say("| **10번째 글 (이 문서)** | **0** | **—** | 🔴 자가보고 0건 ⇒ 분모에 안 들어간다 |")
    tot_n, tot_hit = D7.PRIOR_TOTAL
    say(f"| **누적** | **{tot_n}** | **{tot_hit}/{tot_n} ({tot_hit/tot_n*100:.1f}%)** | **post5 와 같은 값 — 5글 연속 불변** |")
    say("")
    say(f"⚠️ **세 글의 비교 규칙이 서로 다르다** — ***합산 {tot_hit/tot_n*100:.1f}% 를 검정 통계량으로 쓰지 말 것.*** "
        "🔴 0건을 「0/0 = 실패」로도 「통과」로도 세지 않는다.")
    say("")
    say("### §3-1. 미룸 누적 — 🔴 **두 단위**로 적는다 (PD-6 · post8 §6 정오표 ⑨)\n")
    say(f"- **`TV-W1`·`TV-W2` 미룸 = {DEFER_STREAK}글 연속**(5·6·7·8·9·10번째) · **종목 단위 자가보고 0건 = {ZERO_STREAK}글 연속**"
        "(6·7·8·9·10번째 · 5번째는 자가보고가 있었으나 부류별 3건 미달로 미뤘다).")
    say("")
    say("| 항목 | 동결 자리 | 첫 적용 글 | 이력(4~9번째) | **10번째** | 연속 미룸 |")
    say("|---|---|---|---|---|---|")
    st9 = status10()
    for lbl, src, first, hist, now9, streak in st9:
        extra = (" (🔴 셈 명시: 5번째 「판정 불가(선행 미판정)」를 미룸으로 센 값 · 낱말 그대로면 **4글**)"
                 if lbl == "`TV-W3`" else "")
        say(f"| {lbl} | {src} | {first} | {hist} | ⛔ **{now9}** | **{streak}글**{extra} |")
    say("")
    say(f"⇒ **{len(st9)}항목 전부 이번 글에서 미룸.** 🔴 **미룸 횟수가 는다고 문턱을 낮추지 않는다**(게이트 보고 파라미터 하향 "
        "금지 조항 승계).")
    say("")

    say("## §4. 자기점검 — 규칙을 넓히지 않았다는 증거\n")
    say("| 점검 | 결과 |")
    say("|---|---|")
    say("| 부류 매핑을 이번 글 문장에 맞춰 «새로» 만들었는가 | 🟢 **아니다** — PD-6·INTAKE §3 이 계산 «전»에 「0건」으로 동결 |")
    say("| 「거래대금」 산문 1곳을 `TV` 진술로 승격했는가 | 🟢 **아니다** — 수치가 없는 섹터 서술이다 |")
    say("| 최소 n(3건·2건)을 낮췄는가 · 새 예측을 등록했는가 | 🟢 **둘 다 아니다** |")
    say("")
    say("## §5. 한계 (승계)\n")
    say("- 🔴 **자가보고가 0건인 것 자체는 우리 가설의 증거가 아니다.**")
    say("- 🔴 **`daily_prices.market_cap` 은 여전히 백로그 대상이다**(`PREREG_D1_OOS.md` §5).")
    say("- 🔴 **`TV-W5`~`W9`·`P6-W10`(가) 는 한 번도 판정된 적이 없다** — 「살아 있다」와 「검증됐다」는 다르다.")
    say("- 🔴 **`--rerun` 한계** — 다음 sweep 이 `updated_at` 을 일괄 갱신하면 `D-9` ②④·지문이 바뀌어 이 산출물은 byte 가 바뀐다"
        "(동결 규칙의 귀결).")
    say("- 이 분석은 **라이브 채택 대상이 아니다** (`PREREG.md` §0 2번 · `PREREG_POST10.md`).")

    assert_duties(OUT)
    (BASE / OUT_NAME).write_bytes(("\n".join(OUT) + "\n").encode("utf-8"))
    note("")
    note(f"[D-9 ①] 이번 실행 벽시계 = {now_kst} · 본문 ① = {first_kst} ({'stamp 재사용' if reused else 'stamp 새로 박음'})")
    note(f"[written] {OUT_NAME} · 런타임 {time.time() - t0:.3f}s")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
