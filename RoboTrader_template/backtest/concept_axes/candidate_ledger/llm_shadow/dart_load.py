"""§3-4 전향 공시 적재 🔒 — ① `scripts/dart_disclosure_backfill.py` 를 «잠금만 교체해» 재사용.

- 범위 = 마지막 적재일 다음 날 ~ D(달력일 · B → I · `--resume` · `last_reprt_at=N`) · 출력 폴더 = git 밖
  `%LOCALAPPDATA%/kis-llm-shadow/dart_forward/`(raw 캐시·progress·call_log 를 본체·검색 팔이 공유).
- 잠금 = 바깥 공유 OS 잠금(`lock.RunnerLock`) · 백필 내부 `.lock` 자리엔 no-op(`run(args, lock_fns=…)` 주입).
- OpenDART 상한 = 두 프로세스 합산 ≤ 60회/일 — `call_log.jsonl` 의 오늘 줄 수로 남은 예산을 `--limit-calls` 로 준다.
- 완결 판정 = ① 문서 §2(날짜 × 유형): status 013(증거 = call_log 줄) 또는 1…total_page 전 페이지 000 ∧
  raw 항목 수 = total_count ∧ DB 행수(rcept_dt·pblntf_ty) + 중복 수(다른 유형으로 이미 저장) = total_count.
  `FIRST_VERIFIED_END`(① 백필 끝 · §2 전수 완결 판정 끝난 날) 이하는 완결로 본다.
- 키(`.env OPENDART_API_KEY`)는 백필 스크립트가 읽기만 한다 — 여기서 출력·로그 금지.
"""
from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, List, Optional

from . import settings as S

FIRST_VERIFIED_END = date(2026, 9, 23)
TYPES = ("B", "I")
CHECK_BACK_DAYS = 14


def _backfill_module():
    path = S.RT_ROOT / "scripts" / "dart_disclosure_backfill.py"
    spec = importlib.util.spec_from_file_location("dart_disclosure_backfill", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # type: ignore[union-attr]
    return mod


def calls_today(call_log: Path, today: date) -> int:
    if not call_log.exists():
        return 0
    n, key = 0, today.isoformat()
    with open(call_log, encoding="utf-8") as f:
        for line in f:
            try:
                if str(json.loads(line).get("ts", "")).startswith(key):
                    n += 1
            except ValueError:
                continue
    return n


def last_loaded_day(out_dir: Path) -> date:
    """progress.json 에서 FIRST_VERIFIED_END 다음 날부터 B·I 모두 done 인 «연속» 마지막 날."""
    p = out_dir / "progress.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    d = FIRST_VERIFIED_END
    while True:
        nxt = d + timedelta(days=1)
        ds = nxt.strftime("%Y%m%d")
        if all((data.get(f"{t}:{ds}") or {}).get("done") for t in TYPES):
            d = nxt
        else:
            return d


def _has_013(call_log: Path, ds: str, ty: str) -> bool:
    if not call_log.exists():
        return False
    with open(call_log, encoding="utf-8") as f:
        for line in f:
            try:
                j = json.loads(line)
            except ValueError:
                continue
            url = str(j.get("url", ""))
            if j.get("status") == "013" and f"bgn_de={ds}" in url and f"pblntf_ty={ty}" in url:
                return True
    return False


def day_complete(query: Callable[[str, tuple], int], out_dir: Path, ty: str, day: date) -> bool:
    """① §2 완결 판정 1칸. query(sql, params) → 정수 1개."""
    if day <= FIRST_VERIFIED_END:
        return True
    ds = day.strftime("%Y%m%d")
    raw = out_dir / "raw"
    p1 = raw / f"{ds}_{ty}_p1.json"
    if not p1.exists():
        return _has_013(out_dir / "call_log.jsonl", ds, ty)
    d1 = json.loads(p1.read_text(encoding="utf-8"))
    tc, tp = int(d1.get("total_count") or 0), int(d1.get("total_page") or 1)
    items: List[dict] = []
    for pg in range(1, tp + 1):
        f = raw / f"{ds}_{ty}_p{pg}.json"
        if not f.exists():
            return False
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("status") != "000":
            return False
        items.extend(d.get("list") or [])
    if len(items) != tc:
        return False
    rcepts = [str(it.get("rcept_no") or "") for it in items]
    n_db = query("SELECT count(*) FROM dart_disclosures WHERE rcept_dt = %s AND pblntf_ty = %s", (day, ty))
    dup = query("SELECT count(*) FROM dart_disclosures WHERE rcept_no = ANY(%s) AND pblntf_ty <> %s", (rcepts, ty))
    return n_db + dup == tc


@dataclass
class LoadResult:
    ok: bool
    first_incomplete: Optional[date]
    calls_before: int
    calls_after: int
    loaded_from: Optional[date]
    message: str = ""


def load_forward(conn, D: date, today: date, out_dir: Optional[Path] = None,
                 runner: Optional[Callable] = None) -> LoadResult:
    """공유 잠금은 호출자가 이미 쥐고 있어야 한다. 미완결이면 ok=False(그 D 채점 보류)."""
    out_dir = Path(out_dir or S.dart_forward_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    call_log = out_dir / "call_log.jsonl"
    before = calls_today(call_log, today)
    start = last_loaded_day(out_dir) + timedelta(days=1)
    msg = ""
    if start <= D:
        budget = S.OPENDART_DAILY_MAX - before
        if budget <= 0:
            msg = f"OpenDART 오늘 {before}회 ≥ {S.OPENDART_DAILY_MAX} — 적재 보류"
        else:
            try:
                if runner is None:
                    bf = _backfill_module()
                    bf.LIVE_ENV = str(S.dotenv_path())
                    args = bf.parse_args(["--bgn", start.isoformat(), "--end", D.isoformat(), "--types", "B,I",
                                          "--resume", "--limit-calls", str(budget), "--last-reprt-at", "N",
                                          "--out", str(out_dir)])
                    bf.run(args, lock_fns=(lambda _d: None, lambda _h: None))
                else:
                    runner(start, D, budget, out_dir)
            except (Exception, SystemExit) as e:
                msg = f"적재 중단: {type(e).__name__}"      # 예외 문자열은 키를 담을 수 있어 싣지 않는다
    after = calls_today(call_log, today)

    def q(sql: str, params: tuple) -> int:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            v = int(cur.fetchone()[0])
        conn.commit()
        return v

    first_bad = None
    d = max(FIRST_VERIFIED_END + timedelta(days=1), D - timedelta(days=CHECK_BACK_DAYS))
    while d <= D:
        if not all(day_complete(q, out_dir, t, d) for t in TYPES):
            first_bad = d
            break
        d += timedelta(days=1)
    return LoadResult(ok=first_bad is None, first_incomplete=first_bad, calls_before=before, calls_after=after,
                      loaded_from=start if start <= D else None, message=msg)

