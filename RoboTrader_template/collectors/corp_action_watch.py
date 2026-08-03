# collectors/corp_action_watch.py
"""기업행위 후 '미조정 이력' 탐지 → 재수집 대상 큐 적재 (실행은 하지 않는다).

배경 (2026-08-03 실측)
─────────────────────
`daily_prices` 에는 **과거 OHLC 를 다시 쓰는 코드가 없다**. 수집은 증분이고
`daily_collector.collect_one(lookback_days=7)` 이 최근 7봉만 갱신하는데, 기업행위
매매정지는 실측 중앙값 15봉(최소 9, 최대 41)이라 7봉 창은 정지 구간을 **원리적으로**
넘지 못한다. 지금까지 역사적 교정은 사람이 수동 대량 재수집할 때만 일어났고, 그
스크립트가 2026-05-04 삭제된 뒤로 교정이 멈췄다.

그 결과가 데이터에 그대로 남아 있다 — corp_events 의 정답지 105건을 이벤트 연도별로
분해하면 2021~2025 는 사실상 전부 조정 완료(49건)인데 **2026 은 30건이 미조정**이다.

왜 corp_events 로 라우팅하면 안 되는가
────────────────────────────────────
갭 스캔이 찾은 기업행위 대비 corp_events 가 알고 있던 건 극히 일부였다. 게다가
운영 수집기는 pblntf_ty="B" 만 보고 있어서 분할·병합 공시(pblntf_ty="I")를 한 건도
잡은 적이 없다(corp_events_collector 주석 참조). 그래서 **탐지는 corp_events 가 아니라
가격 그 자체**로 한다. 공시가 없어도, 공시를 놓쳐도 가격 불연속은 남는다.

무엇을 하지 않는가
─────────────────
재수집을 **실행하지 않는다**. 대상 목록만 남긴다. 대량 재수집은 KIS 토큰을 쓰고
사장님 승인 사항이다. 또한 큐 항목은 `eligible_after` 이전에는 확정하지 않는다 —
권리락 직후 재수집은 실패한 관측이 있다(아래 _REFETCH_DELAY_DAYS 주석).
"""
import json
import os
from datetime import date, timedelta

from utils.logger import setup_logger

logger = setup_logger(__name__)

# 정지 해제 판정: 직전에 거래정지(거래량 0) 봉이 최소 몇 개 있어야 하는가.
# 실측 — 정답지 105건의 정지런: 미조정 32건은 최소 9봉, 이미 조정된 64건은 최소 3봉.
# 3 이면 실제 기업행위를 하나도 배제하지 않는다.
_HALT_MIN_BARS = 3

# '정상 등락'으로 볼 수 있는 종가비 밴드. KRX 일일 가격제한은 ±30% 라 정상 하루
# 변동은 [0.70, 1.30] 안이다. 정지 해제일은 기준가가 재설정되며 시가단일가 밴드가
# 더 넓을 수 있어 상단을 1.45 까지 열어 둔다(하단은 0.69).
# 실측 — 이미 조정된 64건은 전부 이 밴드 안, 미조정 32건은 전부 밖이다.
_NORMAL_BAND_LO = 0.69
_NORMAL_BAND_HI = 1.45

# 재수집을 곧바로 확정하지 않고 두는 지연(캘린더 일).
# 🟡 근거가 약하다(n=3): 권리락 +6~9일 뒤 재수집은 성공(003350·058430), +2일은
# 재수집했는데도 깨진 관측이 있다(001510). 원인 미규명 — 공급측이 조정 이력을 늦게
# 반영하는 것으로 보이나 확인되지 않았다. 그래서 fire-and-forget 하지 않고
# eligible_after 를 두고, 재수집 뒤에는 반드시 재검증(verify_resolved)을 거친다.
_REFETCH_DELAY_DAYS = 7

_SCAN_LOOKBACK_DAYS = 120

_QUEUE_FILENAME = "corp_action_refetch_queue.jsonl"


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def queue_path() -> str:
    """큐 파일 경로. ⚠️ cwd 에 의존하지 않는다 — utils/holiday_kis_sync.py 의
    `os.getcwd()` 기반 캐시 경로가 다른 cwd 로 기동하면 통째로 실패하던 전례가 있다."""
    override = (os.getenv("CORP_ACTION_QUEUE_PATH") or "").strip()
    if override:
        return override
    return os.path.join(_project_root(), "logs", _QUEUE_FILENAME)


# ── 순수 탐지 로직 (DB 없이 단위 테스트 가능) ────────────────────────────────

def scan_series(stock_code: str, bars: list) -> list:
    """한 종목의 [(date_iso, close, volume)] 오름차순 → 기업행위 의심 지점 목록.

    판정: 직전 _HALT_MIN_BARS 개 이상이 거래량 0(거래정지)이고, 그 다음 봉의 종가비가
    정상 밴드를 벗어나면 '미조정 이력' 후보다.

    거래량 0 봉의 종가는 정지 직전 종가로 동결돼 있고(실측), 그 동결가와 다음 봉
    종가의 비가 곧 미반영된 기업행위 배수다. 배수 자체는 신뢰하지 않는다 —
    해제봉은 기준가에서 자유롭게 움직이므로 비율은 참고값(`ratio`)으로만 남긴다.

    ⚠️ 불연속 봉에 거래량이 있을 것을 요구하지 않는다. 실측 380540(2026-05-22,
    1:2 병합)은 **정지가 안 풀린 채 기준가만 갱신**됐다(4,225 → 8,450, 거래량 0).
    "거래량 > 0 인 해제봉"만 보던 초판은 이 건을 놓쳤다 — 정지 중 기준가 갱신도
    똑같이 미조정 이력을 남긴다.
    """
    out = []
    halt_run = 0
    for i, (d, close, volume) in enumerate(bars):
        # halt_run == 직전까지 연속된 거래량 0 봉 수 (현재 봉은 아직 포함 안 함)
        if i > 0 and halt_run >= _HALT_MIN_BARS:
            prev_d, prev_close, _ = bars[i - 1]
            if close > 0 and prev_close > 0:
                ratio = close / prev_close
                if ratio > _NORMAL_BAND_HI or ratio < _NORMAL_BAND_LO:
                    out.append({
                        "stock_code": stock_code,
                        "resumption_date": d,
                        "halt_last_date": prev_d,
                        "halt_bars": halt_run,
                        "prev_close": prev_close,
                        "resume_close": close,
                        "ratio": round(ratio, 6),
                        "direction": "merge" if ratio > 1 else "split",
                    })
        halt_run = halt_run + 1 if volume == 0 else 0
    return out


def eligible_after(resumption_date_iso: str) -> str:
    return (date.fromisoformat(resumption_date_iso)
            + timedelta(days=_REFETCH_DELAY_DAYS)).isoformat()


# ── DB 로딩 + 큐 적재 ────────────────────────────────────────────────────────

def _load_bars(conn, since_iso: str) -> dict:
    """[(stock_code → [(date, close, volume)])] — date 는 TEXT 'YYYY-MM-DD'.

    ⚠️ daily_prices.date 는 text 다. 캐스팅하면 인덱스를 못 쓰므로 text 로 비교한다.
    """
    series = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT stock_code, date, close, volume FROM daily_prices "
            "WHERE date >= %s AND stock_code ~ '^[0-9]{6}$' "
            "ORDER BY stock_code, date",
            (since_iso,),
        )
        for sc, d, close, volume in cur.fetchall():
            series.setdefault(sc, []).append(
                (d, float(close or 0), int(volume or 0)))
    return series


def _read_existing(path: str) -> set:
    """이미 큐에 있는 (stock_code, resumption_date) — 재적재 방지(멱등)."""
    seen = set()
    if not os.path.exists(path):
        return seen
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            seen.add((rec.get("stock_code"), rec.get("resumption_date")))
    return seen


def record_candidates(candidates: list, path: str = None) -> int:
    """후보를 JSONL 로 append. 이미 있는 (종목,재개일)은 건너뛴다. 반환: 신규 건수."""
    path = path or queue_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    seen = _read_existing(path)
    new = [c for c in candidates
           if (c["stock_code"], c["resumption_date"]) not in seen]
    if not new:
        return 0
    detected_on = date.today().isoformat()
    with open(path, "a", encoding="utf-8") as f:
        for c in new:
            rec = dict(c)
            rec["detected_on"] = detected_on
            rec["eligible_after"] = eligible_after(c["resumption_date"])
            rec["status"] = "pending"
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(new)


def scan_and_queue(conn, lookback_days: int = _SCAN_LOOKBACK_DAYS,
                   path: str = None) -> dict:
    """수집 파이프라인 훅 — 최근 구간을 스캔해 재수집 대상만 큐에 남긴다.

    재수집은 하지 않는다. 반환 {"candidates": n, "queued": m}.
    """
    since = (date.today() - timedelta(days=lookback_days)).isoformat()
    series = _load_bars(conn, since)
    candidates = []
    for sc, bars in series.items():
        candidates.extend(scan_series(sc, bars))
    queued = record_candidates(candidates, path=path)
    if candidates:
        logger.warning(
            "[corp_action] 미조정 의심 %d건 탐지(신규 %d건 큐 적재) — 재수집은 "
            "수동 승인 사항. 큐: %s", len(candidates), queued, path or queue_path())
    return {"candidates": len(candidates), "queued": queued}


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, _project_root())
    from db.kis_db_connection import KisDbConnection

    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback", type=int, default=_SCAN_LOOKBACK_DAYS)
    ap.add_argument("--dry-run", action="store_true",
                    help="큐에 쓰지 않고 후보만 출력")
    args = ap.parse_args()

    with KisDbConnection.get_connection() as _conn:
        if args.dry_run:
            _since = (date.today() - timedelta(days=args.lookback)).isoformat()
            _cands = []
            for _sc, _bars in _load_bars(_conn, _since).items():
                _cands.extend(scan_series(_sc, _bars))
            for _c in sorted(_cands, key=lambda x: x["resumption_date"]):
                print(_c)
            print(f"total={len(_cands)}")
        else:
            print(scan_and_queue(_conn, args.lookback))
