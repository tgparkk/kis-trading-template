"""미청산 포지션 소유자(owner) 대조 프로브 — 읽기 전용 연구 스크립트.

목적(2026-08-13 재정의):
    계획서 초안은 "런타임 _position_entries 에 owner=None 이 있는가"를 물었다.
    그러나 add_position 생산자 전수조사 결과 **페이퍼 모드에서 owner=None 은
    구조적으로 0 일 수밖에 없다**:

        bot/state_restorer.py:247          owner 전달 O (복원)
        bot/trading_analyzer.py:197        owner 전달 O (페이퍼 매수)
        core/orders/order_monitor.py:370   owner 전달 X (실주문 체결)
        core/orders/order_timeout.py:294   owner 전달 X (실주문 타임아웃)

    owner 를 빠뜨리는 두 경로는 **둘 다 실주문 경로**이고,
    order_monitor.py:364-365 가 스스로 그렇게 적어놨다 —
    "이 경로는 페이퍼 모드에선 pending_orders 자체가 비어 휴면이라 무해하나".

    => owner 없음 0 을 관측해도 blocker 가 반증되지 않는다. 그래서 이 프로브의
       질문은 "owner=None 찾기"가 아니라 **"엔트리가 DB 기준선과 일치하는가"**다.
       불일치가 나오면 그게 곧 다른 종류의 누수다.

방법:
    1차(정확): buy_record_id 링크 — 대응 SELL 이 없는 BUY 가 미청산.
    2차(교차검증): (stock_code, strategy, timestamp>) 휴리스틱.
    두 결과의 **대칭 차분을 양방향으로** 출력한다.
    단독 단언은 판별력이 없다 — 두 방법이 갈리면 그 자체가 발견이다.

2026-08-13 측정치(종가 후, 두 독립 방법이 대칭 차분 양방향 0 으로 일치):
    엔트리 48 / 고유 종목 47 / owner 없음 0
    전략별:
        elder_ema_pullback           16
        daytrading_3methods_breakout  8
        book_pullback_ma20            6
        minervini_volume_dryup        6
        book_envelope_200d            5
        rs_leader                     4
        book_pullback_ma5             3
    겹침 1건: 003280 = book_pullback_ma5 + minervini_volume_dryup

읽기 전용 — INSERT/UPDATE/DELETE 를 절대 실행하지 않는다.

usage:
  cd RoboTrader_template && python scripts/probe_position_entries.py
"""
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.kis_db_connection import KisDbConnection  # noqa: E402

# --- 2026-08-13 기준선 (코드에 박아둔다: 다르면 눈에 띄어야 한다) ---
BASELINE_DATE = "2026-08-13"
BASELINE_ENTRIES = 48
BASELINE_CODES = 47
BASELINE_NO_OWNER = 0
BASELINE_BY_OWNER = {
    "elder_ema_pullback": 16,
    "daytrading_3methods_breakout": 8,
    "book_pullback_ma20": 6,
    "minervini_volume_dryup": 6,
    "book_envelope_200d": 5,
    "rs_leader": 4,
    "book_pullback_ma5": 3,
}

NO_OWNER_TOKENS = ("(null)", "", None)

# 1차: buy_record_id 정확 링크. SELL.buy_record_id 는 BUY.id 를 가리키는 FK 이고,
# action='SELL' AND buy_record_id IS NOT NULL 에 UNIQUE 인덱스가 걸려 있어
# BUY 1건 : SELL 1건 대응이 보장된다.
SQL_EXACT = """
SELECT b.id, b.stock_code, COALESCE(b.strategy, '(null)')
FROM virtual_trading_records b
WHERE b.action = 'BUY'
  AND NOT EXISTS (
    SELECT 1 FROM virtual_trading_records s
    WHERE s.action = 'SELL' AND s.buy_record_id = b.id)
ORDER BY b.id
"""

# 2차(교차검증): 계획서 초안의 휴리스틱. 같은 종목·전략에 «나중» SELL 이 하나라도
# 있으면 닫힌 것으로 본다 → 분할매수(BUY 2 : SELL 1)에서 1차와 갈릴 수 있다.
SQL_HEURISTIC = """
SELECT b.id, b.stock_code, COALESCE(b.strategy, '(null)')
FROM virtual_trading_records b
WHERE b.action = 'BUY'
  AND NOT EXISTS (
    SELECT 1 FROM virtual_trading_records s
    WHERE s.action = 'SELL' AND s.stock_code = b.stock_code
      AND s.strategy IS NOT DISTINCT FROM b.strategy
      AND s.timestamp > b.timestamp)
ORDER BY b.id
"""

# 1차 방법의 전제 점검: SELL 에 buy_record_id 가 없으면 링크가 깨진다.
SQL_ORPHAN_SELL = """
SELECT COUNT(*) FROM virtual_trading_records
WHERE action = 'SELL' AND buy_record_id IS NULL
"""

SQL_SELL_TOTAL = "SELECT COUNT(*) FROM virtual_trading_records WHERE action = 'SELL'"


def fetch(sql):
    with KisDbConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def fetch_one(sql):
    return fetch(sql)[0][0]


def report(entries, label):
    """entries: [(id, stock_code, owner)] -> (by_owner Counter, codes set)"""
    by_owner = Counter(o for _, _, o in entries)
    codes = {c for _, c, _ in entries}
    nones = sorted(c for _, c, o in entries if o in NO_OWNER_TOKENS)

    print(f"--- {label} ---")
    print(f"엔트리 {len(entries)} / 고유 종목 {len(codes)}")
    for owner, n in by_owner.most_common():
        print(f"  {owner:<32} {n}")
    print(f"owner 없음 {len(nones)}건: {nones}")

    # 같은 종목 다중 소유
    owners_by_code = defaultdict(list)
    for _, code, owner in entries:
        owners_by_code[code].append(owner)
    multi = {c: sorted(o) for c, o in owners_by_code.items() if len(o) > 1}
    if multi:
        pct = 100.0 * len(multi) / len(codes) if codes else 0.0
        print(f"같은 종목 다중소유 {len(multi)}건 ({pct:.1f}%):")
        for code, owners in sorted(multi.items()):
            print(f"  {code}  {' + '.join(owners)}")
    else:
        print("같은 종목 다중소유 0건")
    return by_owner, codes, nones


def compare_baseline(entries, by_owner, codes, nones):
    """기준선과 다르면 눈에 띄게 출력. 같으면 한 줄."""
    diffs = []
    if len(entries) != BASELINE_ENTRIES:
        diffs.append(f"엔트리 {len(entries)} != {BASELINE_ENTRIES}")
    if len(codes) != BASELINE_CODES:
        diffs.append(f"고유 종목 {len(codes)} != {BASELINE_CODES}")
    if len(nones) != BASELINE_NO_OWNER:
        diffs.append(f"owner 없음 {len(nones)} != {BASELINE_NO_OWNER}")

    for owner in sorted(set(BASELINE_BY_OWNER) | set(by_owner)):
        got = by_owner.get(owner, 0)
        want = BASELINE_BY_OWNER.get(owner, 0)
        if got != want:
            diffs.append(f"전략 {owner}: {got} != {want}")

    print()
    if diffs:
        print(f"[!] 기준선({BASELINE_DATE}: "
              f"{BASELINE_ENTRIES}/{BASELINE_CODES}/{BASELINE_NO_OWNER})과 다름 "
              f"— {len(diffs)}항목")
        for d in diffs:
            print(f"    [!] {d}")
        print("    (기준선 이후 매매가 있었다면 정상. 같은 날짜인데 다르면 조사할 것.)")
    else:
        print(f"[OK] 기준선({BASELINE_DATE}: "
              f"{BASELINE_ENTRIES}/{BASELINE_CODES}/{BASELINE_NO_OWNER}) 및 "
              f"전략별 분포 완전 일치")
    return diffs


def symmetric_diff(exact, heuristic):
    """두 방법의 대칭 차분을 양방향으로 출력. 단독 단언은 판별력이 없다."""
    ex = {r[0]: r for r in exact}
    he = {r[0]: r for r in heuristic}
    only_exact = sorted(set(ex) - set(he))
    only_heur = sorted(set(he) - set(ex))

    print()
    print("--- 대칭 차분 (1차 정확링크 vs 2차 휴리스틱) ---")
    print(f"1차에만 있음 {len(only_exact)}건 / 2차에만 있음 {len(only_heur)}건")
    for rid in only_exact:
        print(f"  [1차only] id={rid} {ex[rid][1]} owner={ex[rid][2]}")
    for rid in only_heur:
        print(f"  [2차only] id={rid} {he[rid][1]} owner={he[rid][2]}")
    if not only_exact and not only_heur:
        print("  양방향 0 — 두 방법이 완전히 일치한다.")
    else:
        print("  [!] 두 방법이 갈렸다. 그 자체가 발견이다 — 위 목록을 조사할 것.")
    return only_exact, only_heur


def main():
    sell_total = fetch_one(SQL_SELL_TOTAL)
    orphan_sell = fetch_one(SQL_ORPHAN_SELL)
    print(f"SELL 총 {sell_total}행 / buy_record_id IS NULL {orphan_sell}행")
    if orphan_sell:
        print("  [!] buy_record_id 없는 SELL 이 있다 — 1차(정확 링크) 방법이 깨진다.")
    else:
        print("  [OK] 모든 SELL 이 buy_record_id 를 갖는다 — 정확 링크 성립.")
    print()

    exact = fetch(SQL_EXACT)
    heuristic = fetch(SQL_HEURISTIC)

    by_owner, codes, nones = report(exact, "1차: buy_record_id 정확 링크")
    print()
    report(heuristic, "2차: (stock_code, strategy, timestamp>) 휴리스틱")

    symmetric_diff(exact, heuristic)
    compare_baseline(exact, by_owner, codes, nones)

    print()
    print("주의: 이 프로브는 DB(virtual_trading_records) 기준이다. 런타임")
    print("      fund_manager._position_entries 는 봇 프로세스 안에 있어 여기서 못 읽는다.")
    print("      bot/state_restorer.py 의 [진단] 로그와 위 출력을 대조할 것.")
    print("      owner 없음 0 은 페이퍼 모드에서 정상이며 blocker 의 반증이 아니다")
    print("      (근거: core/orders/order_monitor.py:364-365).")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
