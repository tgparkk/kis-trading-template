"""ARCHIVE 후보 판정기 — docs/INVENTORY.md의 UNREFERENCED(scripts/ 계열)를 재검증.

로직(정확히 이 순서):
  1. docs/INVENTORY.md에서 태그 UNREFERENCED & 경로가 scripts/로 시작하는 행만 파싱.
  2. ops 화이트리스트(스펙 Global Constraints 패턴) 매칭 → KEEP(사유 명기).
  3. 나머지 각 파일: stem(확장자 뺀 파일명)을 repo 전체 *.py/*.bat/*.ps1에서 검색
     (자기 자신·__pycache__·archive/·docs/ 제외). 1건이라도 hit → KEEP(hit 위치 1개 예시),
     0-hit → ARCHIVE.
  4. markdown 표 출력 (path | git 최종커밋일 | ARCHIVE/KEEP | 근거).

사용: venv\\Scripts\\python tools/gen_archive_candidates.py > docs/superpowers/plans/2026-07-02-archive-candidates.md
재실행 가능 — INVENTORY.md나 repo 상태가 바뀌면 판정도 바뀐다(일회성 스크립트 아님).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INVENTORY_PATH = os.path.join(ROOT, "docs", "INVENTORY.md")
DEFAULT_OUTPUT_PATH = os.path.join(ROOT, "docs", "superpowers", "plans", "2026-07-02-archive-candidates.md")

# 스펙 Global Constraints의 ops 화이트리스트 패턴 (경로/파일명 매칭).
# 각 항목: (설명 라벨, 매칭 함수(normalized_path, basename) -> bool)
WHITELIST_PATTERNS = [
    ("scripts/kis_db/*", lambda path, base: path.startswith("scripts/kis_db/")),
    ("backfill_*", lambda path, base: base.startswith("backfill_")),
    ("preflight_*", lambda path, base: base.startswith("preflight_")),
    ("seed_*", lambda path, base: base.startswith("seed_")),
    ("schema*", lambda path, base: base.startswith("schema")),
    ("refresh_*", lambda path, base: base.startswith("refresh_")),
    ("reconcile_*", lambda path, base: base.startswith("reconcile_")),
]

# repo 전역 stem 검색 시 순회에서 제외할 디렉터리(경로 컴포넌트 이름 기준).
# self·__pycache__·archive/·docs/는 브리프 명시. venv 계열은 서드파티 라이브러리라
# "repo 전체" 취지(자체 소스) 밖 — 성능·오탐 방지를 위해 gen_inventory.py와 동일하게 제외.
SEARCH_EXCLUDE_DIRS = {"__pycache__", "archive", "docs", "venv", "venv_broken_quantcopy", ".git"}

SEARCH_EXTS = (".py", ".bat", ".ps1")

INVENTORY_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*([A-Z-]+)\s*\|")


def parse_inventory_scripts_unreferenced(inventory_text: str) -> list[str]:
    """UNREFERENCED 태그 & scripts/ 접두 경로만 파싱, 정규화된(슬래시) 경로 리스트 반환."""
    out = []
    for line in inventory_text.splitlines():
        m = INVENTORY_ROW_RE.match(line)
        if not m:
            continue
        raw_path, tag = m.group(1), m.group(2)
        norm_path = raw_path.replace("\\", "/")
        if tag == "UNREFERENCED" and norm_path.startswith("scripts/"):
            out.append(norm_path)
    return out


def whitelist_reason(norm_path: str) -> str | None:
    base = os.path.basename(norm_path)
    for label, matcher in WHITELIST_PATTERNS:
        if matcher(norm_path, base):
            return f"ops 화이트리스트: {label}"
    return None


def build_search_corpus() -> dict[str, str]:
    """repo 전체 *.py/*.bat/*.ps1 파일을 1회 읽어 {normalized_relpath: content} 캐시."""
    corpus: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SEARCH_EXCLUDE_DIRS]
        for fname in filenames:
            if not fname.endswith(SEARCH_EXTS):
                continue
            full = os.path.join(dirpath, fname)
            relpath = os.path.relpath(full, ROOT).replace("\\", "/")
            text = None
            for enc in ("utf-8", "cp949", "latin-1"):
                try:
                    with open(full, encoding=enc) as fh:
                        text = fh.read()
                    break
                except (UnicodeDecodeError, OSError):
                    continue
            if text is not None:
                corpus[relpath] = text
    return corpus


def find_stem_hit(stem: str, self_path: str, corpus: dict[str, str]) -> tuple[str, int] | None:
    """stem을 corpus 전역에서 substring 검색(자기 자신 제외). 첫 hit(경로, 줄번호) 반환."""
    for relpath, text in corpus.items():
        if relpath == self_path:
            continue
        if stem not in text:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if stem in line:
                return relpath, lineno
        # 이론상 도달 불가(위에서 stem in text 확인됨) — 방어적 fallback
        return relpath, 0
    return None


def git_last_commit_date(norm_path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ad", "--date=short", "--", norm_path],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        date = result.stdout.strip()
        return date if date else "-"
    except OSError:
        return "-"


def render_table(rows: list[tuple[str, str, str]]) -> str:
    archive_rows = sorted([r for r in rows if r[1] == "ARCHIVE"], key=lambda r: r[0])
    keep_rows = sorted([r for r in rows if r[1] == "KEEP"], key=lambda r: r[0])
    ordered = archive_rows + keep_rows

    lines = []
    lines.append("# ARCHIVE 후보 판정표 (2026-07-02)")
    lines.append("")
    lines.append("> `tools/gen_archive_candidates.py` 생성. 재실행 가능(일회성 아님) — "
                  "`docs/INVENTORY.md` 재생성 후 이 스크립트를 다시 돌리면 판정이 갱신된다.")
    lines.append(">")
    lines.append("> 판정 로직: docs/INVENTORY.md에서 태그 `UNREFERENCED` & 경로가 `scripts/`인 행만 대상 →")
    lines.append("> ops 화이트리스트(`scripts/kis_db/*`, `backfill_*`, `preflight_*`, `seed_*`, `schema*`, "
                  "`refresh_*`, `reconcile_*`) 매칭 시 KEEP →")
    lines.append("> 나머지는 stem(확장자 뺀 파일명)을 repo 전체 `*.py`/`*.bat`/`*.ps1`에서 "
                  "substring 검색(자기 자신·`__pycache__`·`archive/`·`docs/` 제외) — "
                  "1건이라도 hit면 KEEP(보수적 방향), 0-hit면 ARCHIVE.")
    lines.append("")
    lines.append("| path | git 최종커밋일 | 판정 | 근거 |")
    lines.append("|---|---|---|---|")
    for norm_path, verdict, reason in ordered:
        date = git_last_commit_date(norm_path)
        lines.append(f"| `{norm_path}` | {date} | {verdict} | {reason} |")

    n_archive = len(archive_rows)
    n_keep = len(keep_rows)
    total = n_archive + n_keep
    lines.append("")
    lines.append(f"**ARCHIVE {n_archive}건 / KEEP {n_keep}건 / 합계 {total}**"
                  f"(scripts 계열 UNREFERENCED 전수). "
                  f"참고: docs/INVENTORY.md 전체 UNREFERENCED는 이보다 많을 수 있음"
                  f"(multiverse/ 등 scripts/ 외 계열 포함, 이 판정 범위 밖 — 스펙 §1 불가침).")
    return "\n".join(lines) + "\n"


def main() -> None:
    with open(INVENTORY_PATH, encoding="utf-8") as fh:
        inventory_text = fh.read()

    candidates = parse_inventory_scripts_unreferenced(inventory_text)
    corpus = build_search_corpus()

    rows: list[tuple[str, str, str]] = []
    for norm_path in candidates:
        wl_reason = whitelist_reason(norm_path)
        if wl_reason is not None:
            rows.append((norm_path, "KEEP", wl_reason))
            continue

        stem = os.path.splitext(os.path.basename(norm_path))[0]
        hit = find_stem_hit(stem, norm_path, corpus)
        if hit is not None:
            hit_path, hit_line = hit
            reason = f"stem hit: `{hit_path}:{hit_line}`"
            rows.append((norm_path, "KEEP", reason))
        else:
            rows.append((norm_path, "ARCHIVE", "stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외)"))

    output_text = render_table(rows)

    # Windows 콘솔 cp949로는 em-dash 등 유니코드가 print()에서 깨지므로(stdout 리다이렉트도 동일 위험),
    # 파일에 직접 UTF-8로 기록한다(선호되는 방식) — 인자로 다른 출력 경로를 줄 수도 있음.
    out_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUTPUT_PATH
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(output_text)

    n_archive = sum(1 for r in rows if r[1] == "ARCHIVE")
    n_keep = sum(1 for r in rows if r[1] == "KEEP")
    sys.stdout.write(f"wrote {out_path}: ARCHIVE {n_archive} / KEEP {n_keep} / total {len(rows)}\n")


if __name__ == "__main__":
    main()
