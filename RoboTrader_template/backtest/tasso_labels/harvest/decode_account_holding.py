"""계좌 화면 `대출일` 의 의미를 확정하고 실제 보유 «영업일» 을 복원한다.

━━ 무엇을 확정했나 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  `대출일` = 매수 체결일의 **T+2 영업일 결제일**
  `일자`   = 매도 체결일

  ⇒ 매수 체결일 = 대출일에서 영업일 2일 되돌린 날
  ⇒ 보유 영업일 = (매수 체결일 ~ 일자) 영업일 차

  이로써 `METHOD.md` §A.5.3 / §A.5.6 5조의 미해소 항목
  **「제일모직형 `대출일 < 일자`」** 가 해소된다 — 이상현상이 아니라
  **2영업일 이상 보유한 정상 거래**다. 🔑 그리고 2015~16 일봉 백필 없이 풀렸다
  (§A.5.3 이 적어둔 「매입가가 어느 날 저가~고가에 드는가」 판정 경로는 불필요해졌다).

━━ 어떻게 검증했나 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ① **요일 검정 (결정적)** — 원시 델타(일자 − 대출일)의 봉우리 두 개(−4, −1)는
     트랙이 아니라 «주말 결제 아티팩트» 였다. 델타별 「일자」 요일 분포가 결제일
     가설의 예측과 정확히 맞는다(아래 `report_weekday_evidence` 가 매 실행 시 재출력).
     대출일 요일에 **토·일 0건** — 결제일성 컬럼만 가질 수 있는 성질이다.

  ② **대칭 검증 2개 (이 스크립트의 자기검증)** — 매 실행 시 스스로 출력한다.
       (a) 디코딩 후 «보유일 음수» 건수      → 0 이어야 한다
       (b) 대출일이 «비영업일» 인 행 건수    → 0 이어야 한다
     🔑 둘 다 0 이어야 디코딩이 성립한다. 하나라도 0 이 아니면 «디코딩이 틀린 것»이지
        데이터가 이상한 것이 아니다. 단독 수치는 판별력이 없으므로 **항상 함께** 보고한다.

━━ 입력과 값 공개 정책 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  🔴 입력 `READINGS_DIR` 은 **비공개 원장**이다(METHOD.md §A.5.6 6조).
     코드만 리포에 들어가고 데이터는 들어가지 않는다 — 없으면 친절히 실패한다.
  🔴 출력은 **집계 분포뿐**이다. 개별 판독값·종목명·손익을 절대 찍지 않는다.

  결과 문서: `account_holding_result.md`
"""

import csv
import datetime as dt
import sys
from collections import Counter, defaultdict
from pathlib import Path

# `utils.korean_holidays` 를 «이 파일이 속한 워크트리» 에서 잡는다.
# (라이브 트리 D:\GIT\kis-trading-template 를 하드코딩하면 워크트리 검증이 라이브 코드를 읽는다.)
TEMPLATE_ROOT = Path(__file__).resolve().parents[3]  # .../RoboTrader_template
sys.path.insert(0, str(TEMPLATE_ROOT))

from utils.korean_holidays import is_holiday  # noqa: E402

# Windows 콘솔 기본 코드페이지(cp949)에서 출력이 UnicodeEncodeError 로 죽는 것을 막는다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover - 리다이렉트 등
    pass

# 🔴 비공개 원장 — 리포에 커밋되지 않는다.
READINGS_DIR = Path(r"D:\archive\tasso-account-images-20260809\readings")

SETTLEMENT_BIZ_DAYS = 2  # 대출일 = 매수 체결일 + 2영업일
WEEKDAY_KR = "월화수목금토일"


def load_rows(readings_dir: Path):
    """판독 원장 `*_rows.csv` 를 전부 읽는다. 없으면 친절히 실패한다."""
    if not readings_dir.is_dir():
        sys.exit(
            "🔴 판독 원장 디렉토리가 없다: %s\n"
            "   이 입력은 «비공개 원장» 이라 리포에 커밋되지 않는다(METHOD.md §A.5.6 6조).\n"
            "   보관소 `D:\\archive\\tasso-account-images-20260809\\` 를 연결한 뒤 다시 실행하거나,\n"
            "   다른 위치라면 이 파일의 READINGS_DIR 상수를 고쳐라." % readings_dir
        )
    paths = sorted(readings_dir.glob("*_rows.csv"))
    if not paths:
        sys.exit(
            "🔴 %s 안에 `*_rows.csv` 가 한 개도 없다.\n"
            "   판독 원장이 맞는 디렉토리인지 확인하라." % readings_dir
        )
    rows = []
    for p in paths:
        with open(p, encoding="utf-8-sig", newline="") as f:
            rows.extend(list(csv.DictReader(f)))
    return rows, paths


def load_screen_types(readings_dir: Path):
    """`*_screens.csv` 에서 파일명 → 화면유형 매핑. 없으면 빈 dict(집계만 생략)."""
    types = {}
    for p in sorted(readings_dir.glob("*_screens.csv")):
        with open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                types[r.get("file", "")] = (r.get("screen_type") or "").strip()
    return types


def parse_date(s):
    s = (s or "").strip().replace("/", "-").replace(".", "-")
    for fmt in ("%Y-%m-%d", "%y-%m-%d", "%Y%m%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def is_business_day(d: dt.date) -> bool:
    return not is_holiday(dt.datetime(d.year, d.month, d.day))


def back_business_days(d: dt.date, n: int) -> dt.date:
    """영업일 n 일 되돌리기."""
    k = 0
    while k < n:
        d -= dt.timedelta(days=1)
        if is_business_day(d):
            k += 1
    return d


def business_days_between(a: dt.date, b: dt.date) -> int:
    """a(포함) ~ b(포함) 경과 영업일. b < a 이면 -1(= 디코딩 실패 신호)."""
    if b < a:
        return -1
    n, cur = 0, a
    while cur < b:
        cur += dt.timedelta(days=1)
        if is_business_day(cur):
            n += 1
    return n


def decode(rows):
    """(보유 영업일 리스트, 음수 건수, 대출일 비영업일 건수, 대상 파일명 집합)"""
    holdings, negative, nonbiz_loan, files = [], 0, 0, set()
    for r in rows:
        sell, loan = parse_date(r.get("일자")), parse_date(r.get("대출일"))
        if not (sell and loan):
            continue
        files.add(r.get("file", ""))
        if not is_business_day(loan):
            nonbiz_loan += 1
        buy = back_business_days(loan, SETTLEMENT_BIZ_DAYS)
        held = business_days_between(buy, sell)
        if held < 0:
            negative += 1
        else:
            holdings.append(held)
    return holdings, negative, nonbiz_loan, files


def report_weekday_evidence(rows):
    """근거 ① — 원시 델타(일자 − 대출일)별 「일자」 요일 분포와 대출일 요일 분포."""
    by_delta = defaultdict(Counter)
    loan_weekday = Counter()
    for r in rows:
        sell, loan = parse_date(r.get("일자")), parse_date(r.get("대출일"))
        if not (sell and loan):
            continue
        by_delta[(sell - loan).days][WEEKDAY_KR[sell.weekday()]] += 1
        loan_weekday[WEEKDAY_KR[loan.weekday()]] += 1

    print("=== 근거 ① 요일 검정 — 원시 델타(일자 − 대출일)별 「일자」 요일 ===")
    for delta in sorted(by_delta, key=lambda d: -sum(by_delta[d].values()))[:6]:
        c = by_delta[delta]
        tot = sum(c.values())
        parts = " ".join("%s %d" % (w, n) for w, n in c.most_common())
        print("  델타 %+3d  n=%4d   %s" % (delta, tot, parts))
    print("  대출일 요일 분포: %s"
          % " ".join("%s %d" % (w, loan_weekday[w]) for w in WEEKDAY_KR if loan_weekday[w]))
    print("  → 대출일 «토·일» = %d건 (결제일 가설이 맞으면 0)"
          % (loan_weekday["토"] + loan_weekday["일"]))
    print()


def report_symmetric_checks(n_target, negative, nonbiz_loan):
    """🔑 이 스크립트의 자기검증 — 두 수치를 «항상 함께» 낸다. 둘 다 0 이어야 성립."""
    print("=== 🔑 대칭 검증 (둘 다 0 이어야 디코딩이 성립한다) ===")
    print("  디코딩 대상            %d행" % n_target)
    print("  (a) 보유일 «음수»      %d행   (디코딩이 맞으면 0)" % negative)
    print("  (b) 대출일 «비영업일»  %d행   (결제일 가설이 맞으면 0)" % nonbiz_loan)
    print("  판정: %s" % ("🟢 성립" if negative == 0 and nonbiz_loan == 0
                          else "🔴 불성립 — 디코딩이 틀린 것이지 데이터가 이상한 게 아니다"))
    print()


def report_screen_types(files, screen_types):
    if not screen_types:
        return
    c = Counter(screen_types.get(f, "<unknown>") for f in files if f)
    print("=== 디코딩 대상 행이 실린 화면 유형 ===")
    for t, n in c.most_common():
        print("  %-10s %d장" % (t, n))
    print()


def report_distribution(holdings):
    total = len(holdings)
    if total == 0:
        sys.exit("🔴 디코딩된 행이 0 이다 — 입력을 확인하라.")
    c = Counter(holdings)
    peak = max(c.values())

    print("=== 복원된 실제 보유 영업일 분포 (체결 %d건) ===" % total)
    cum = 0
    for h in sorted(c):
        if h > 12:
            continue
        n = c[h]
        cum += n
        print("  %2d영업일  %4d  %5.1f%%  누적 %5.1f%%  %s"
              % (h, n, 100.0 * n / total, 100.0 * cum / total, "#" * int(70.0 * n / peak)))
    tail = sum(n for h, n in c.items() if h > 12)
    print("  13일 이상 %4d  %5.1f%%   (최대 %d영업일)" % (tail, 100.0 * tail / total, max(c)))
    print()

    s = sorted(holdings)
    print("중앙 %d영업일 · 평균 %.2f · p75 %d · p90 %d · p95 %d · max %d"
          % (s[total // 2], sum(s) / total, s[int(.75 * total)],
             s[int(.90 * total)], s[int(.95 * total)], s[-1]))
    print("0~2영업일 비중 %.1f%% · 5영업일(1주) 초과 %.1f%%"
          % (100.0 * sum(1 for x in s if x <= 2) / total,
             100.0 * sum(1 for x in s if x > 5) / total))


def main():
    rows, paths = load_rows(READINGS_DIR)
    print("판독 원장 %d파일 · 원시 %d행" % (len(paths), len(rows)))
    print()

    report_weekday_evidence(rows)
    holdings, negative, nonbiz_loan, files = decode(rows)
    report_symmetric_checks(len(holdings) + negative, negative, nonbiz_loan)
    report_screen_types(files, load_screen_types(READINGS_DIR))
    report_distribution(holdings)


if __name__ == "__main__":
    main()
