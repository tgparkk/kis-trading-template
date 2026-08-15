# -*- coding: utf-8 -*-
"""재현 게이트 — 커밋된 `RESULTS_*.md` 가 커밋된 스크립트의 출력인지 검사한다.

## 왜 있나 (2026-08-15)

`RESULTS_COMMON_BAND.md` 가 `solve_common_band.py` 보다 **한 판 뒤처져 있었다.**
커밋 메시지·메모리는 `b₁ ≈ 12.0% · 귀무 0.5%` 라고 적었는데 저장소의 파일은
`b₁ ≈ 1.1% · 귀무 0.6%` 였다. 그 0.6% 는 changelog 가 *「내 귀무의 결함이었다」* 고
**이미 철회한 값**이다.

🔑 ***결과 파일이 스크립트보다 한 판 뒤처지면, 이미 철회한 숫자가 저장소에 남는다.***
   자기보고(커밋 메시지)와 산출물이 갈릴 때 **산출물이 옛것일 수 있다** — 자기보고를
   게이트로 쓰지 말라는 규칙의 산출물 쪽 대응물이다.

## 무엇을 검사하나

각 `RESULTS_*.md` 에 대해 **생성 스크립트 + 그 스크립트가 import 하는 로컬 모듈 전부**의
sha256 을 매니페스트와 대조한다. 의존 폐포까지 보는 이유는 `run_hdr.py` 가
`reconstruct_prices.py` 를 import 하기 때문이다 — 후자만 고치면 전자의 산출물도 낡는다.

이 게이트가 통과한다고 **숫자가 옳다**는 뜻은 아니다. *「그 스크립트로 만든 게 맞다」* 뿐이다.
숫자 자체는 `--rerun` 으로 실제 재실행해 byte-diff 해야 확인된다.

## 실행

    python regen_gate.py            # 빠른 검사 (해시 대조만, DB 불필요)
    python regen_gate.py --rerun    # 실제 재실행 + byte-diff (DB 필요, 느림)
    python regen_gate.py --update   # 산출물을 재생성한 «뒤» 매니페스트 갱신

재현 가능성 전제: 모든 산출 스크립트가 결정적이거나 시드가 고정돼 있다
(`run_selection.py` 는 `np.random.default_rng(20260815)`, `solve_common_band.py` ·
`run_hdr.py` 는 `random.Random(20260815)`). 시드를 바꾸면 이 게이트가 깨진다 — 그게 의도다.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
MANIFEST = BASE / "REGEN_MANIFEST.json"

# 산출물 → 생성 스크립트
PAIRS = {
    "RESULTS_RECONSTRUCT.md": "reconstruct_prices.py",
    "RESULTS_COMMON_BAND.md": "solve_common_band.py",
    "RESULTS_HDR.md": "run_hdr.py",
    "RESULTS_Q1_V2.md": "run_q1_v2.py",
    "RESULTS_SELECTION.md": "run_selection.py",
    "RESULTS_raw.md": "run_tests.py",
}

# 스크립트가 만들지 않는 문서 — 사람이 쓴 것. 게이트 대상 아님을 명시해 둔다.
MANUAL_DOCS = [
    "README.md", "RESULTS.md",
    "PREREG.md", "PREREG_Q1_V2.md", "PREREG_SELECTION.md", "PREREG_HDR.md",
    "PREREG_BUYLADDER.md", "PREREG_EXIT_V2.md", "FINDING_THEME_AXIS.md", "PREREG_SELLTIMING.md",
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def local_deps(script: str, seen: set[str] | None = None) -> set[str]:
    """스크립트가 import 하는 **로컬 모듈**의 폐포 (자기 자신 포함)."""
    seen = seen if seen is not None else set()
    if script in seen:
        return seen
    seen.add(script)
    tree = ast.parse((BASE / script).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        for n in names:
            cand = f"{n.split('.')[0]}.py"
            if (BASE / cand).exists():
                local_deps(cand, seen)
    return seen


def build() -> dict:
    entries = {}
    for out, script in sorted(PAIRS.items()):
        deps = sorted(local_deps(script))
        entries[out] = {
            "script": script,
            "deps": {d: sha(BASE / d) for d in deps},
            "results_sha256": sha(BASE / out) if (BASE / out).exists() else None,
        }
    return {"manual_docs": MANUAL_DOCS, "artifacts": entries}


def check() -> int:
    if not MANIFEST.exists():
        print("🔴 REGEN_MANIFEST.json 이 없다 — `--update` 로 먼저 만들 것.")
        return 2
    old = json.loads(MANIFEST.read_text(encoding="utf-8"))["artifacts"]
    new = build()["artifacts"]
    fails = []
    for out in sorted(PAIRS):
        o, n = old.get(out), new[out]
        if o is None:
            fails.append(f"{out}: 매니페스트에 없음")
            continue
        if not (BASE / out).exists():
            fails.append(f"{out}: 산출물이 없다")
            continue
        stale = [d for d, h in n["deps"].items() if o["deps"].get(d) != h]
        if stale:
            fails.append(
                f"{out}: 🔴 **산출물이 스크립트보다 뒤처졌다** — 바뀐 모듈 {stale} "
                f"⇒ `python {n['script']}` 로 재생성한 뒤 `--update`")
        elif o["results_sha256"] != n["results_sha256"]:
            fails.append(
                f"{out}: 🔴 산출물이 손으로 편집됐다(스크립트는 그대로) "
                f"⇒ 편집분을 스크립트에 넣고 재생성할 것")
        else:
            print(f"  ✅ {out}  ({n['script']} + deps {len(n['deps'])}개)")
    if fails:
        print("\n".join("  " + f for f in fails))
        print(f"\n🔴 재현 게이트 FAIL — {len(fails)}건")
        return 1
    print("\n🟢 재현 게이트 PASS — 모든 산출물이 현재 스크립트 판본과 일치한다.")
    print("⚠️ 단 이건 「그 스크립트로 만들었다」일 뿐 「숫자가 옳다」가 아니다. "
          "숫자 확인은 `--rerun`.")
    return 0


def rerun() -> int:
    """실제 재실행 + byte-diff. 결정적/시드고정이므로 동일해야 한다."""
    fails = []
    for out, script in sorted(PAIRS.items()):
        before = (BASE / out).read_bytes() if (BASE / out).exists() else None
        r = subprocess.run([sys.executable, script], cwd=BASE,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if r.returncode != 0:
            fails.append(f"{out}: 실행 실패 ({script})\n{r.stderr[-800:]}")
            continue
        after = (BASE / out).read_bytes()
        if before is None:
            fails.append(f"{out}: 산출물이 없었다 — 새로 생성됨")
        elif before != after:
            fails.append(f"{out}: 🔴 재실행 결과가 다르다 — 커밋된 값이 낡았거나 비결정적")
        else:
            print(f"  ✅ {out}  재현 일치")
    if fails:
        print("\n".join("  " + f for f in fails))
        print(f"\n🔴 재현(--rerun) FAIL — {len(fails)}건")
        return 1
    print("\n🟢 재현(--rerun) PASS — 재실행 결과가 커밋본과 byte 단위로 같다.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="매니페스트 갱신")
    ap.add_argument("--rerun", action="store_true", help="실제 재실행 + byte-diff (DB 필요)")
    a = ap.parse_args()
    if a.update:
        MANIFEST.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        print(f"[written] {MANIFEST.name}")
        return 0
    if a.rerun:
        return rerun()
    return check()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
