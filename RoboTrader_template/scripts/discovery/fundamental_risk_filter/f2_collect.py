"""F(2) DART as-filed 연간 재무제표 수집 (순차, 체크포인트 재개).

읽기 전용 + 외부 API. DB 쓰기 없음.

🔴 병렬 금지 — 2026-08-06 IP 차단 전례. 이 파일 자체가 시작 시 PID 잠금(`f2_collect.lock`)을
   걸어 같은 프로세스가 이중 실행되는 것도 막는다(재개가 예정돼 있어 이중 시작이 흔한 실수다).
🔴 status=020(한도초과)·010/011/012/100/101/HTTP_FAIL(키·IP·필드 오류) 은 모두 즉시
   중단하고 체크포인트를 보존한다. 000(성공)·013(무자료)·000_EMPTY 만 정상 진행이다.
🔑 원본 응답을 gzip 으로 그대로 남긴다. 수집이 1~2일이라 필드를 골라 버리면
   나중에 계정 하나 때문에 전체 재수집이 된다.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f2_collect.py
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f2_collect.py --limit 300
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f2_collect.py --status
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f2_collect.py --offset 17800 --limit 50

⚠️ --offset 은 분포 표본 추출 전용이다. 청크 분할 실행에 쓰면 항목이 영구히 누락된다:
   --offset 은 체크포인트로 걸러진 나머지(todo)를 인덱싱하므로, 분할 실행 시 마다
   todo 가 줄어든다. --offset 0 --limit 1000 완료 후 --offset 1000 --limit 1000 을
   부르면, todo 는 이미 1000 짧아져 있어 원래 items[1000:2000] 이 아닌 «다른» 1000건을
   건너뛴다. 같은 --offset 으로 재시도해야 하나, 이미 수집된 것은 체크포인트로 걸러진다.
   대신 full run(--limit 0, 모든 항목) 을 권장한다.
"""
import argparse
import gzip
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_client import (  # noqa: E402
    OUT_DIR, REPRT_FY, DartBlocked, DartClient, DartQuotaExceeded,
    DartUnexpectedStatus, eprint, load_dart_key,
)
from f1_worklist import WORKLIST_JSONL  # noqa: E402

RAW_GZ = os.path.join(OUT_DIR, "f2_raw.jsonl.gz")

# 🔴 이 두 값만 "정상적으로 계속 진행 가능"이다. 013(무자료)은 사실이지 오류가
#    아니다. 그 외(010/011/012 키·IP 문제, 100/101 필드 오류, HTTP_FAIL)는
#    개별 호출 결과만으로 판단해 즉시 올린다 — CFS 에서 이미 나왔다면 OFS 를
#    시도해도 같은 키·IP 문제로 같은 값이 나올 뿐이라 계속할 이유가 없다.
_ACCEPTABLE_CALL_STATUSES = ("000", "013")


def collect_one(client, item):
    """CFS 우선, 무자료면 OFS 로 재시도. 둘 다 없으면 013 을 기록한다.

    🔴 000/013 이 아닌 status(010/011/012/100/101/HTTP_FAIL 등)는 여기서
       `DartUnexpectedStatus` 로 즉시 올린다. 조용히 last 에 저장해 최종
       레코드로 기록해 버리면 키·IP 문제 하나가 작업목록 전체를
       「수집 완료, 무자료」로 태우고 체크포인트에 영구히 박힌다.
    """
    last = (None, "")
    for fs_div in ("CFS", "OFS"):
        status, message, rows = client.fnltt_all(
            item["corp_code"], item["bsns_year"], REPRT_FY, fs_div,
        )
        if status == "000" and rows:
            return {
                "stock_code": item["stock_code"],
                "corp_code": item["corp_code"],
                "bsns_year": item["bsns_year"],
                "status": status,
                "fs_div": fs_div,
                "rows": rows,
            }
        if status not in _ACCEPTABLE_CALL_STATUSES:
            raise DartUnexpectedStatus(status, item["stock_code"], item["bsns_year"])
        last = (status, message)
    # 🔴 데이터 없음을 성공으로 기록하지 않는다. 리스크 필터가 조용히 깨끗하다고 답하면 최악이다.
    final_status = last[0]
    if final_status == "000":
        final_status = "000_EMPTY"
    return {
        "stock_code": item["stock_code"],
        "corp_code": item["corp_code"],
        "bsns_year": item["bsns_year"],
        "status": final_status,
        "fs_div": None,
        "rows": [],
    }


def load_done(path):
    """이미 수집한 (stock_code, bsns_year) 집합. 잘린 마지막 줄은 버린다.

    🔴 하드킬·전원차단으로 gzip 종료 마커가 없으면 EOFError 를 낸다.
       «디코딩된 만큼은 살려» 재개를 할 수 있게 한다.
    """
    done = set()
    if not os.path.exists(path):
        return done
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue  # 중단 시점의 잘린 줄 — 그 한 줄만 버린다
                done.add((rec["stock_code"], rec["bsns_year"]))
    except EOFError:
        # gzip 컨테이너가 정상 종료되지 않았으나 읽은 데이터는 유효하다.
        # 앞부분을 살리고 재개한다.
        pass
    return done


def load_worklist():
    items = []
    with open(WORKLIST_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


LOCK_PATH = os.path.join(OUT_DIR, "f2_collect.lock")


def _pid_is_alive(pid):
    """PID 가 살아있는 프로세스를 가리키는지. 신호를 보내지 않고 확인한다.

    🔴 Windows 에서 `os.kill(pid, 0)` 은 신뢰할 수 없다 — 실측(2026-08-08)으로
       확인됨: 자식 프로세스가 종료된 뒤에도 부모가 핸들을 쥐고 있는 동안은
       예외 없이 통과한다. `GetExitCodeProcess` 로 STILL_ACTIVE 여부를 직접
       확인해야 한다. POSIX 는 `os.kill(pid, 0)` 그대로 쓴다.
    """
    if pid is None or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        STILL_ACTIVE = 259
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 존재하지만 신호 권한이 없다 = 살아있다
    else:
        return True


def acquire_lock(path=None):
    """단일 인스턴스 잠금. 살아있는 PID 가 잡고 있으면 거부, 죽은 PID 면 가져간다.

    🔴 이 파이프라인은 ~2.5시간 걸리고 한도(20,200 호출 vs 20,000/일) 때문에
       재개가 최소 1회 예정돼 있다 — 운영자가 재개인지 모르고 두 번째 인스턴스를
       띄우기 쉬운 정확한 상황이다. 두 프로세스가 동시에 돌면 초당 6건이 되고,
       이건 2026-08-06 IP 차단·운영 수집기 동반 마비의 재현 조건이다. gzip 에도
       두 프로세스가 겹쳐 쓰면 스트림이 섞인다.
    """
    path = path or LOCK_PATH
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                old_pid = int(f.read().strip())
        except (OSError, ValueError):
            old_pid = -1  # 손상된 잠금파일 — stale 로 간주
        if _pid_is_alive(old_pid):
            raise RuntimeError(
                f"다른 인스턴스(PID {old_pid})가 이미 실행 중이다 — {path}"
            )
        # stale: 기록된 PID 가 죽어 있다. 잠금을 가져간다.
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    return path


def release_lock(path=None):
    path = path or LOCK_PATH
    try:
        os.remove(path)
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0,
                    help="체크포인트로 걸러진 나머지를 인덱싱. 분포 표본 추출 전용. "
                         "청크 분할에 쓰면 항목이 영구히 누락된다.")
    ap.add_argument("--interval", type=float, default=0.34)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    items = load_worklist()
    done = load_done(RAW_GZ)
    todo = [i for i in items if (i["stock_code"], i["bsns_year"]) not in done]

    print(f"작업 {len(items)} / 완료 {len(done)} / 남음 {len(todo)}")
    if args.status:
        return

    key = load_dart_key()
    if not key:
        eprint("OPENDART_API_KEY 를 찾지 못했다 — 중단")
        sys.exit(1)

    try:
        acquire_lock()
    except RuntimeError as e:
        eprint(f"🔴 {e}")
        sys.exit(7)

    try:
        client = DartClient(key, min_interval=args.interval)
        if args.offset:
            todo = todo[args.offset:]
        if args.limit:
            todo = todo[: args.limit]

        written = 0
        try:
            with gzip.open(RAW_GZ, "at", encoding="utf-8") as out:
                for item in todo:
                    rec = collect_one(client, item)
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
                    written += 1
                    if written % 200 == 0:
                        print(f"  {written}/{len(todo)} · 호출 {client.calls} "
                              f"· status {dict(Counter(client.status_counts))}")
        except DartQuotaExceeded as e:
            eprint(f"🔴 {e} — 체크포인트 {written}건 보존. 자정 이후 재개할 것.")
            sys.exit(2)
        except DartBlocked as e:
            eprint(f"🔴 {e} — 체크포인트 {written}건 보존. 즉시 중단했다.")
            sys.exit(3)
        except DartUnexpectedStatus as e:
            eprint(f"🔴 {e} — 체크포인트 {written}건 보존. status={e.status} 확인 후 재개할 것.")
            sys.exit(5)

        print(f"완료 {written}건 · 호출 {client.calls} · status {dict(client.status_counts)} "
              f"· 연결리셋 {client.conn_resets} · http오류 {client.http_errors}")
    finally:
        release_lock()


if __name__ == "__main__":
    main()
