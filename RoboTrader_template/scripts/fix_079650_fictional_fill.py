"""079650(2026-06-15) 허수 체결 1건 보정 — 누적 페이퍼 성과에서 제거.

배경: 페이퍼 매수가 실시간가 미확보 시 직전 확정 일봉 종가(1,690)로 체결을
날조했는데, 079650은 06-15 종일 상한가 락(OHLC 전부 2,195)이라 1,690 매수가
물리적으로 불가능했다. 봇은 1,690 매수 → 2,195 청산으로 +597,415원 허수 이익을
기록했다(누적 실현의 ~28%). 근본 버그는 커밋 9f8fd9e(실시간가 전용+진입밴드)로
수정됐고, 이 스크립트는 그 버그가 남긴 *데이터 잔재*만 제거한다.

대상: virtual_trading_records 의 (stock_code='079650', date=2026-06-15,
      source='kis_template') BUY+SELL 페어 = id 920(BUY) / 923(SELL).

안전장치:
  - 삭제 전 지문 검증(BUY 1183@1690 / SELL 1183@2195 profit_loss=597415).
    불일치 시 중단(엉뚱한 행 삭제 방지).
  - 삭제행 백업을 reports/discovery/fix_079650_deleted_rows.tsv 에 기록.
  - 멱등: 이미 삭제됐으면 no-op.
  - 단일 트랜잭션.

실행 후: `python tools/paper_strategy_equity.py` 재실행으로 전략별 equity 곡선
재산출(멱등 리플레이). paper_trading_state(현금)는 다음 봇 사이클에 자동 재계산.

usage: python scripts/fix_079650_fictional_fill.py        # 보정 실행
       python scripts/fix_079650_fictional_fill.py --dry  # 미실행(조회만)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import DatabaseConnection  # noqa: E402

STOCK = "079650"
TRADE_DATE = "2026-06-15"
SOURCE = "kis_template"
EXPECT = {  # 지문: (action) -> (quantity, price, profit_loss)
    "BUY": (1183, 1690.00, 0.00),
    "SELL": (1183, 2195.00, 597415.00),
}
BACKUP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "discovery", "fix_079650_deleted_rows.tsv")


def _cum(cur):
    cur.execute("SELECT count(*) FILTER (WHERE action='SELL'), "
                "COALESCE(sum(profit_loss),0) FROM virtual_trading_records "
                "WHERE source=%s AND action='SELL'", (SOURCE,))
    return cur.fetchone()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="삭제 없이 조회만")
    args = ap.parse_args(argv)

    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, action, quantity, price, profit_loss FROM virtual_trading_records "
            "WHERE stock_code=%s AND timestamp::date=%s AND source=%s ORDER BY id",
            (STOCK, TRADE_DATE, SOURCE),
        )
        rows = cur.fetchall()
        if not rows:
            print(f"[no-op] {STOCK} {TRADE_DATE} 레코드 없음 — 이미 보정됨")
            return 0

        # 지문 검증
        for rid, action, qty, price, pnl in rows:
            exp = EXPECT.get(action)
            if exp is None or qty != exp[0] or float(price) != exp[1] or float(pnl) != exp[2]:
                print(f"[중단] 예상과 다른 행: id={rid} {action} {qty}@{price} pnl={pnl} "
                      f"(기대 {exp}). 안전을 위해 삭제하지 않음.")
                return 2

        sells, cum_before = _cum(cur)
        print(f"삭제 대상 {len(rows)}행: {[(r[0], r[1]) for r in rows]}")
        print(f"누적(보정 전): SELL {sells}건 / 총손익(수수료전) {float(cum_before):,.0f}원")

        if args.dry:
            print("[dry] 미실행")
            return 0

        # 백업
        os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
        with open(BACKUP, "w", encoding="utf-8") as f:
            f.write("id\taction\tquantity\tprice\tprofit_loss\n")
            for r in rows:
                f.write("\t".join(str(x) for x in r) + "\n")
        print(f"백업 기록: {BACKUP}")

        ids = tuple(r[0] for r in rows)
        cur.execute("DELETE FROM virtual_trading_records WHERE id IN %s", (ids,))
        sells2, cum_after = _cum(cur)
        conn.commit()
        print(f"삭제 완료. 누적(보정 후): SELL {sells2}건 / 총손익(수수료전) {float(cum_after):,.0f}원 "
              f"(Δ {float(cum_after) - float(cum_before):,.0f})")
    print("→ 다음: python tools/paper_strategy_equity.py 로 전략별 equity 재산출")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
