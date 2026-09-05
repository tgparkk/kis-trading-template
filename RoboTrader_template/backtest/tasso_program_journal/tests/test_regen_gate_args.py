# -*- coding: utf-8 -*-
"""C-23 회귀 테스트 — `--rerun` 이 «동결본을 덮어쓰는» 경로가 다시 열리지 않는지.

## 무엇을 막나 (2026-09-05)

`regen_gate.py` 의 `PAIRS` 값이 «스크립트 파일명 하나»뿐이던 시절 `rerun()` 은
`python <script>` 를 **인자 없이** 불렀다. 그런데 한 파일이 두 산출물을 만드는 스크립트가 둘이다:

  · `run_sector.py`  기본 `--mode both`  ⇒ 동결 `RESULTS_SECTOR_DRYRUN_NUMBERS.md`
    **+ `sector_dryrun/` 23파일**을 같이 덮어쓴다.
  · `run_ranking.py` 기본 `--stage train` ⇒ 동결 `RESULTS_RANKING_TRAIN_NUMBERS.md` 를 덮어쓴다.

`FROZEN_STALE` 의 「건너뛰기」는 **그 키가 스킵될 뿐**이라, 같은 스크립트가 *다른 키*(post6)로
호출되면 그대로 돌았다. 그리고 `rerun()` 의 원상복구는 **`PAIRS` 키 파일 하나만** 되돌린다
⇒ 곁다리로 갈린 디렉토리는 복구되지 않는다.

🔑 ***「동결」을 산출물 «이름»에만 걸면, 그 이름을 곁다리로 쓰는 실행이 동결을 뚫는다.***

DB 없이 도는 테스트만 모았다(`subprocess.run` 을 가짜로 갈아끼운다). 라이브 트리 import 0건.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import regen_gate as RG                # noqa: E402

# 한 파일이 «여러» 산출물을 만드는 스크립트 — 인자를 비우면 기본 모드가 동결본을 친다.
MULTI_OUTPUT_SCRIPTS = {"run_sector.py", "run_ranking.py"}


# ════════════════════════════════════════════════════════════════════════════
# 1. `PAIRS` 인자 파싱
# ════════════════════════════════════════════════════════════════════════════
def test_pairs_values_split_into_script_and_argv():
    """`script_file` 은 파일명만, `script_argv` 는 실행 인자 전부."""
    assert RG.script_file("run_sector.py --mode post6") == "run_sector.py"
    assert RG.script_argv("run_sector.py --mode post6") == ["run_sector.py", "--mode", "post6"]
    assert RG.script_file("run_wrc_post6.py") == "run_wrc_post6.py"
    assert RG.script_argv("run_wrc_post6.py") == ["run_wrc_post6.py"]


def test_every_pair_script_exists_and_deps_resolve():
    """🔴 sha·의존 폐포는 «파일명»으로 계산해야 한다 — 인자를 섞으면 파일을 못 찾아 크래시한다."""
    for out, spec in RG.PAIRS.items():
        f = RG.script_file(spec)
        assert (BASE / f).is_file(), f"{out}: 스크립트 {f} 가 없다"
        deps = RG.local_deps(f)          # 인자가 섞여 있으면 여기서 터진다
        assert f in deps, out


def test_multi_output_scripts_always_carry_an_explicit_mode():
    """🔴 **이 테스트가 C-23 의 본체다** — 인자 없는 `run_sector.py`/`run_ranking.py` 등재 금지."""
    for out, spec in RG.PAIRS.items():
        if RG.script_file(spec) in MULTI_OUTPUT_SCRIPTS:
            assert len(RG.script_argv(spec)) > 1, (
                f"{out}: `{spec}` 에 모드 인자가 없다 — 기본 모드가 동결본을 덮어쓴다")


def test_the_two_sector_and_ranking_modes_are_distinct():
    """같은 스크립트의 두 키가 «서로 다른» 모드여야 한다(같으면 한쪽이 다른쪽을 덮어쓴다)."""
    for script in MULTI_OUTPUT_SCRIPTS:
        specs = [v for v in RG.PAIRS.values() if RG.script_file(v) == script]
        assert len(specs) == len(set(specs)) >= 2, script


# ════════════════════════════════════════════════════════════════════════════
# 2. `rerun()` — 동결 스킵과 실제 argv
# ════════════════════════════════════════════════════════════════════════════
def _fake_rerun(monkeypatch, tmp_path):
    """`subprocess.run` 을 가짜로 갈아끼우고 `rerun()` 을 돌린 뒤 **실행된 argv 목록**을 준다.

    가짜는 파일을 안 건드리므로 byte-diff 는 전부 「일치」로 끝난다 — 여기서 재는 것은
    *「무엇을 실행했는가」*뿐이다(DB 불필요)."""
    calls: list[list[str]] = []

    class _R:
        returncode = 0
        stdout = stderr = ""

    def fake_run(argv, **kw):
        calls.append(list(argv))
        return _R()

    monkeypatch.setattr(RG.subprocess, "run", fake_run)
    # `clear_absorbed()` 가 진짜 매니페스트를 쓰지 않도록 사본으로 돌린다.
    copy = tmp_path / "REGEN_MANIFEST.json"
    copy.write_text(RG.MANIFEST.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(RG, "MANIFEST", copy)
    rc = RG.rerun()
    return rc, calls


def test_rerun_never_executes_a_frozen_artifacts_script(monkeypatch, tmp_path, capsys):
    """🔴 `FROZEN_STALE` 산출물의 스크립트는 **실행되지 않고** 그 사실이 인쇄돼야 한다."""
    rc, calls = _fake_rerun(monkeypatch, tmp_path)
    out = capsys.readouterr().out
    assert rc == 0, out
    executed = {tuple(c[1:]) for c in calls}          # sys.executable 은 뺀다

    for art in RG.FROZEN_STALE:
        spec = RG.PAIRS[art]
        assert tuple(RG.script_argv(spec)) not in executed, \
            f"🔴 동결 {art} 의 명령 `{spec}` 이 실행됐다"
        assert art in out and "건너뜀" in out, art


def test_rerun_never_calls_the_multi_output_scripts_bare(monkeypatch, tmp_path):
    """🔴 「인자 없는 `run_sector.py` 호출이 없다」 — 실제 실행 목록에서 확인한다."""
    _rc, calls = _fake_rerun(monkeypatch, tmp_path)
    for argv in calls:
        assert argv[0] == sys.executable, argv
        if argv[1] in MULTI_OUTPUT_SCRIPTS:
            assert len(argv) > 2, f"🔴 인자 없는 호출: {argv[1:]}"
    bare = [argv[1:] for argv in calls if argv[1:] in ([s] for s in MULTI_OUTPUT_SCRIPTS)]
    assert not bare, bare


def test_rerun_runs_the_post6_pair_with_its_mode(monkeypatch, tmp_path):
    """동결이 아닌 post6 두 키는 «모드를 달고» 실제로 돈다(스킵이 과잉이면 게이트가 죽는다)."""
    _rc, calls = _fake_rerun(monkeypatch, tmp_path)
    executed = {tuple(c[1:]) for c in calls}
    assert ("run_sector.py", "--mode", "post6") in executed
    assert ("run_ranking.py", "--stage", "post6") in executed


def test_rerun_covers_every_non_frozen_pair(monkeypatch, tmp_path):
    """스킵 목록이 조용히 자라면 게이트가 «안 보는» 산출물이 생긴다 — 개수로 못박는다."""
    _rc, calls = _fake_rerun(monkeypatch, tmp_path)
    expected = {k for k in RG.PAIRS if k not in RG.FROZEN_STALE}
    assert len(calls) == len(expected), (len(calls), len(expected))


# ════════════════════════════════════════════════════════════════════════════
# 3. `ART_DIRS` — 디렉토리 산출물 스냅샷·복구
# ════════════════════════════════════════════════════════════════════════════
def test_art_dirs_point_at_real_directories():
    for art, dirs in RG.ART_DIRS.items():
        assert art in RG.PAIRS, art
        for d in dirs:
            assert (BASE / d).is_dir(), f"{art}: {d} 디렉토리가 없다"
            assert any((BASE / d).iterdir()), f"{art}: {d} 가 비었다"


def test_dir_snapshot_and_restore_round_trip(monkeypatch, tmp_path):
    """편집·삭제·신규생성 세 가지를 다 되돌리는지 — 바이트로 확인한다."""
    monkeypatch.setattr(RG, "BASE", tmp_path)
    d = tmp_path / "artdir"
    (d / "sub").mkdir(parents=True)
    (d / "a.json").write_bytes(b'{"a": 1}')
    (d / "sub" / "b.tsv").write_bytes(b"x\ty\n")
    snap = RG._dir_snapshot(("artdir",))
    assert set(snap) == {"artdir/a.json", "artdir/sub/b.tsv"}

    (d / "a.json").write_bytes(b'{"a": 2}')        # 편집
    (d / "sub" / "b.tsv").unlink()                 # 삭제
    (d / "new.json").write_bytes(b"{}")            # 신규
    assert RG._dir_snapshot(("artdir",)) != snap

    RG._dir_restore(snap, ("artdir",))
    assert RG._dir_snapshot(("artdir",)) == snap
    assert not (d / "new.json").exists(), "실행이 «새로» 만든 파일도 지워야 원상복구다"


# ── 🔴 D1-② — 아래 시나리오 테스트는 «실파일»을 건드리지 않는다 ───────────────
#    초판은 진짜 `sector_post6/` 파일을 훼손한 뒤 되돌렸다. 되돌리기가 실패하거나 테스트가
#    중간에 죽으면 **발표된 산출물이 오염된 채 남는다** — 가드를 시험하려다 가드 대상을 깨는
#    자리다. ⇒ `tmp_path` 에 최소 사본을 만들고 `RG.BASE`·`PAIRS`·`ART_DIRS` 를 그리로 돌린다.
#    🔑 ***테스트가 「진짜 산출물」을 쓰기 대상으로 삼으면, 그 테스트 자체가 위험원이다.***
def _sandbox(tmp_path, monkeypatch, frozen=False):
    """rerun() 이 돌 최소 세계를 tmp_path 에 만든다. 반환 = (산출물 경로, 디렉토리 안 파일)."""
    (tmp_path / "art").mkdir()
    victim = tmp_path / "art" / "a.json"
    victim.write_bytes(b'{"a": 1}\n')
    (tmp_path / "art" / "b.tsv").write_bytes(b"x\ty\n")
    out = tmp_path / "OUT.md"
    out.write_bytes(b"measured = 42\n")
    (tmp_path / "s.py").write_bytes(b"x = 1\n")
    monkeypatch.setattr(RG, "BASE", tmp_path)
    monkeypatch.setattr(RG, "PAIRS", {"OUT.md": "s.py --mode post6"})
    monkeypatch.setattr(RG, "ART_DIRS", {"OUT.md": ("art",)})
    monkeypatch.setattr(RG, "FROZEN_STALE", {"OUT.md": "시험용 동결"} if frozen else {})
    monkeypatch.setattr(RG, "PENDING", {})
    man = tmp_path / "REGEN_MANIFEST.json"
    man.write_text(json.dumps({"manual_docs": [], "db_fingerprint": None,
                               "artifacts": {"OUT.md": {"script": "s.py --mode post6",
                                                        "deps": {}, "results_sha256": None}}},
                              ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(RG, "MANIFEST", man)
    return out, victim


class _R0:
    returncode = 0
    stdout = stderr = ""


class _R1:
    returncode = 1
    stdout = ""
    stderr = "boom: 부분 출력 뒤 죽었다"


def test_dir_change_is_a_failure_not_a_silent_pass(monkeypatch, tmp_path, capsys):
    """🔴 디렉토리만 갈린 경우 — 단일 파일 byte-diff 는 통과지만 게이트는 **FAIL** 이어야 한다."""
    out, victim = _sandbox(tmp_path, monkeypatch)
    original = victim.read_bytes()

    def fake_run(argv, **kw):
        victim.write_bytes(original + b"# tampered\n")     # 디렉토리만 갈아치운다
        return _R0()

    monkeypatch.setattr(RG.subprocess, "run", fake_run)
    rc = RG.rerun()
    o = capsys.readouterr().out
    assert rc != 0, "🔴 디렉토리가 갈렸는데 게이트가 통과했다 = 죽은 가드"
    assert "디렉토리 산출물이 달라졌다" in o
    assert victim.read_bytes() == original, "**원상복구했다**고 인쇄했으면 실제로 되돌려야 한다"


def test_failed_run_restores_the_artifact_file(monkeypatch, tmp_path, capsys):
    """🔴 **D1-B1** — `returncode != 0` 경로도 산출물을 되돌리는가.

    초판은 디렉토리만 복구하고 단일 파일은 그대로 두고 `continue` 했다 ⇒ 스크립트가 산출물을
    **쓴 뒤** 죽으면 부분 출력이 남아 「검사 전용」 계약이 실패 경로에서만 깨졌다."""
    out, victim = _sandbox(tmp_path, monkeypatch)
    original, dir_original = out.read_bytes(), victim.read_bytes()

    def fake_run(argv, **kw):
        out.write_bytes(b"HALF-WRITTEN GARBAGE\n")          # 쓰고 나서
        victim.write_bytes(b'{"a": 999}\n')
        return _R1()                                        # 죽는다

    monkeypatch.setattr(RG.subprocess, "run", fake_run)
    rc = RG.rerun()
    o = capsys.readouterr().out
    assert rc != 0, "실행 실패인데 게이트가 통과했다"
    assert "실행 실패" in o and "원상복구했다" in o
    assert out.read_bytes() == original, "🔴 실패 경로가 산출물을 되돌리지 않았다(D1-B1)"
    assert victim.read_bytes() == dir_original, "🔴 실패 경로가 디렉토리를 되돌리지 않았다"


def test_whole_loop_tripwire_catches_a_frozen_dir_touched_sideways(monkeypatch, tmp_path, capsys):
    """🔴 **D1-①** — `FROZEN_STALE` 키는 항목별 스냅샷에 «도달하지 못한다»(먼저 continue).

    루프 «전체» 앞뒤 tripwire 가 없으면 `sector_dryrun/`·`wrc_explore/` 는 무방비다."""
    out, victim = _sandbox(tmp_path, monkeypatch, frozen=True)
    original = victim.read_bytes()

    # 동결 키라 스크립트는 «실행되지 않는다» — 그 사이 무언가가 디렉토리를 건드린 상황을 만든다.
    def fake_run(argv, **kw):                       # pragma: no cover - 불려선 안 된다
        raise AssertionError("🔴 동결 항목의 스크립트가 실행됐다")

    monkeypatch.setattr(RG.subprocess, "run", fake_run)
    real_snapshot = RG._dir_snapshot
    calls = {"n": 0}

    def snap_then_tamper(names):
        calls["n"] += 1
        s = real_snapshot(names)
        if calls["n"] == 1:                          # 루프 «전» 스냅샷 직후에 오염시킨다
            victim.write_bytes(original + b"# sideways\n")
        return s

    monkeypatch.setattr(RG, "_dir_snapshot", snap_then_tamper)
    rc = RG.rerun()
    o = capsys.readouterr().out
    assert rc != 0, "🔴 동결 디렉토리가 곁다리로 갈렸는데 통과했다 = 죽은 가드"
    assert "루프 전체 tripwire" in o
    assert victim.read_bytes() == original, "tripwire 도 원상복구해야 한다"


def test_whole_loop_tripwire_prints_a_clean_line_when_nothing_moved(monkeypatch, tmp_path, capsys):
    """대조군 — 아무것도 안 움직이면 tripwire 는 🟢 한 줄만 낸다(상시 FAIL 이면 아무도 안 본다)."""
    out, victim = _sandbox(tmp_path, monkeypatch)
    monkeypatch.setattr(RG.subprocess, "run", lambda argv, **kw: _R0())
    rc = RG.rerun()
    o = capsys.readouterr().out
    assert rc == 0, o
    assert "루프 전체 tripwire" in o and "불변" in o


# ════════════════════════════════════════════════════════════════════════════
# 3-B. C-24(D1-B3) — sha() 줄끝 정규화
# ════════════════════════════════════════════════════════════════════════════
def _git_blob(rel: str) -> bytes | None:
    r = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=str(BASE.parents[2]),
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


def test_sha_normalizes_line_endings():
    """`sha()` 는 내용이 같으면 줄끝이 달라도 같은 값을 내야 한다."""
    import hashlib
    lf, crlf = BASE / "___lf.tmp", BASE / "___crlf.tmp"
    try:
        lf.write_bytes(b"a\nb\n")
        crlf.write_bytes(b"a\r\nb\r\n")
        assert RG.sha(lf) == RG.sha(crlf), "🔴 줄끝이 지문을 갈랐다"
        assert RG.sha_raw(lf) != RG.sha_raw(crlf), "sha_raw 는 «구식» 이라 갈려야 한다"
        assert RG.sha(lf) == hashlib.sha256(b"a\nb\n").hexdigest()
    finally:
        for p in (lf, crlf):
            if p.exists():
                p.unlink()


def test_normalized_sha_matches_the_committed_blob():
    """🔴 **D1-B3 본체** — 추적 중인 산출물의 정규화 sha == `git show HEAD:<path>` 블롭 sha.

    이게 깨지면 **깨끗한 체크아웃(LF)에서 `check()` 가 「손으로 편집됐다」로 오탐**한다.
    실측 당시 CRLF 인 `PAIRS` 산출물은 14개였고 그중 추적 5개가 raw sha 로는 블롭과 달랐다."""
    import hashlib
    rel_root = BASE.relative_to(BASE.parents[2]).as_posix()
    checked, crlf_seen = 0, 0
    for out in sorted(RG.PAIRS):
        blob = _git_blob(f"{rel_root}/{out}")
        if blob is None:
            continue                                    # 미추적(이번 글 신규) — 대상 아님
        p = BASE / out
        checked += 1
        if p.read_bytes().count(b"\r\n"):
            crlf_seen += 1
        assert RG.sha(p) == hashlib.sha256(blob.replace(b"\r\n", b"\n")).hexdigest(), (
            f"🔴 {out}: 정규화 sha 가 HEAD 블롭과 다르다 — CRLF 외의 «진짜» 편집이 있다")
    assert checked >= 5, f"추적 산출물이 {checked}개뿐이라 이 단언이 판별력을 못 가진다"
    assert crlf_seen >= 1, "🔴 CRLF 산출물이 0개면 이 가드는 상수를 재고 있다(죽은 가드)"


def test_manifest_holds_normalized_shas_not_raw_ones():
    """`--update` 후 매니페스트는 «정규화» 값을 담아야 한다(마이그레이션이 끝났다는 뜻)."""
    man = json.loads(RG.MANIFEST.read_text(encoding="utf-8"))
    off = []
    for out in sorted(RG.PAIRS):
        p = BASE / out
        rec = man["artifacts"].get(out, {}).get("results_sha256")
        if rec is not None and p.exists() and rec != RG.sha(p):
            off.append((out, rec == RG.sha_raw(p)))
    assert not off, f"🔴 정규화되지 않은 지문이 남았다(구식 raw 와 같은가 표시): {off}"


# ════════════════════════════════════════════════════════════════════════════
# 4. post6 등재 (§5-3 이 잡은 「어디에도 등재돼 있지 않다」의 이번 글 판)
# ════════════════════════════════════════════════════════════════════════════
def test_post6_artifacts_are_registered():
    for f in ("RESULTS_SELECTION_POST6_NUMBERS.md", "RESULTS_D1_OOS_POST6_NUMBERS.md",
              "RESULTS_REGDAY_POST6_NUMBERS.md", "RESULTS_EXIT_V2_POST6_NUMBERS.md",
              "RESULTS_LADDER_TRANCHE_POST6_NUMBERS.md", "RESULTS_RECONSTRUCT_POST6_NUMBERS.md",
              "RESULTS_WRC_POST6_NUMBERS.md", "RESULTS_RANKING_POST6_NUMBERS.md",
              "RESULTS_SECTOR_POST6_NUMBERS.md"):
        assert f in RG.PAIRS, f
        assert (BASE / f).is_file(), f
    for d in ("INTAKE_2026-09-04_post6.md", "PREDECISION_2026-09-04_post6.md",
              "LABELS_2026-09-04_post6.md", "RESULTS_SELECTION_POST6.md",
              "RESULTS_D1_OOS_POST6.md", "RESULTS_REGDAY_POST6.md", "RESULTS_EXIT_V2_POST6.md",
              "RESULTS_LADDER_TRANCHE_POST6.md", "RESULTS_RECONSTRUCT_POST6.md",
              "RESULTS_WRC_POST6.md", "RESULTS_RANKING_POST6.md", "RESULTS_SECTOR_POST6.md"):
        assert d in RG.MANUAL_DOCS, d
        assert (BASE / d).is_file(), d


def test_pending_is_empty_now_that_post6_exists():
    """🔴 파일이 «생겼는데» PENDING 에 남아 있으면 그때부터 진짜 죽은 가드다(check() 가 FAIL)."""
    assert RG.PENDING == {}
    assert RG.PENDING_DOCS == {}


def test_the_three_newly_frozen_artifacts_carry_a_reason():
    """동결은 «조용히» 되면 안 된다 — 사유 문구가 있어야 하고 매니페스트에도 박혀야 한다."""
    man = json.loads(RG.MANIFEST.read_text(encoding="utf-8"))
    for art in ("RESULTS_RANKING_TRAIN_NUMBERS.md", "RESULTS_WRC_EXPLORE.md",
                "RESULTS_SECTOR_DRYRUN_NUMBERS.md"):
        assert art in RG.FROZEN_STALE, art
        assert len(RG.FROZEN_STALE[art]) > 40, art
        assert man["artifacts"][art].get("frozen_reason") == RG.FROZEN_STALE[art], art


def test_verify_ledger_post6_follows_the_post5_precedent():
    """`verify_ledger_post5.py` 는 어디에도 등재돼 있지 «않다» — post6 판도 같은 자리(= 미등재)."""
    for name in ("verify_ledger_post5.py", "verify_ledger_post6.py"):
        assert name not in RG.MANUAL_DOCS, name
        assert name not in RG.PAIRS.values(), name
        assert not any(RG.script_file(v) == name for v in RG.PAIRS.values()), name


@pytest.mark.parametrize("art", sorted(RG.ART_DIRS))
def test_frozen_dir_artifacts_are_also_frozen_by_name(art):
    """`sector_dryrun/`·`wrc_explore/` 는 동결본의 «디렉토리 몸통»이다 — 이름 쪽도 동결이어야 한다."""
    frozen_dirs = {"sector_dryrun", "wrc_explore"}
    if set(RG.ART_DIRS[art]) & frozen_dirs:
        assert art in RG.FROZEN_STALE, art
