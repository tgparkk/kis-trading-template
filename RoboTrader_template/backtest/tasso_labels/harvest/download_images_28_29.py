# -*- coding: utf-8 -*-
"""[28]·[29] 이미지 2차 판독(④) — 대상 글의 **본문 그림**을 내려받는다.

🔴 이 스크립트는 **대상을 스스로 정하지 않는다.** `--targets`/`--stems` 로 받은
   것만 받는다. 무엇을 받을지는 사람이 정하고, 줄였으면 줄였다는 사실이 출력에 남는다
   (계획서 Task 11 의 「무단으로 줄이지 않는다」).

🔴 계획서 초안(2026-08-05-tasso-cat28-29-harvest.md:1777-1794)의 결함 3건을 고쳤다.
   셋 다 「조용히 잘못된 상태로 굳는」 계열이다:
     ① **curl 종료코드를 안 봤다** + `if not out.exists()` 로만 스킵을 판정했다
        ⇒ 실패해도 0바이트 파일이 남고 재실행이 **영구히 스킵**한다.
        실제로 `images28/x.png` 가 0바이트로 남아 있었다.
        → 종료코드 확인 · 매직바이트로 진짜 이미지인지 확인 · **실패하면 파일을
          만들지 않는다**(응답을 메모리에서 검사한 뒤에만 쓴다).
     ② **sleep 이 없었다** ⇒ 수백 연속 요청. `harvest_cat28_29_full.BODY_SLEEP` 승계.
     ③ 페이지 전체에서 `<img src=>` 를 긁었다 ⇒ 프로필 썸네일이 **글당 4장** 섞이고,
        SE2 의 그림 1,986장은 `<span thumburl>` 이라 **한 장도 안 잡힌다**.
        → `cat2829_common.body_images()` 가 유일한 추출 경로다.

⚠️ `images28/` 는 타인 저작물이라 .gitignore:178 로 차단돼 있다(커밋되지 않는다).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
import json
import subprocess
import time

import cat2829_common as C
import harvest_cat28_29_full as H

IMAGE_SLEEP = H.BODY_SLEEP        # 본문 수집과 같은 간격(1.0초)을 쓴다
IMAGE_TIMEOUT = 40                # C._curl(fetch_html) 의 40초를 승계
DEFAULT_KINDS = ("photo",)

# 받은 바이트가 **진짜 이미지인가**. 확장자는 여기서 정한다 —
# ⚠️ 원본이 png/jpg 가 섞여 있어(실측 `.PNG`·`.png`·`.jpg`) `.jpg` 하드코딩은 거짓말이 된다.
#    URL 의 확장자도 못 믿는다: 썸네일 서버는 `?type=w966` 로 형식을 바꿔 줄 수 있고,
#    링크카드 URL(`?src=…`)에는 경로 확장자가 아예 없다(104건 실측).
MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
)


def image_ext(blob):
    """이미지면 확장자, 아니면 **None**. None 이 곧 「받은 게 이미지가 아니다」다."""
    if not blob:
        return None
    for sig, ext in MAGIC:
        if blob.startswith(sig):
            return ext
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "webp"
    return None


def image_path(stem, index, ext):
    """`{stem}_{NNN}.{ext}` — stem 은 `harvest_cat28_29_full._stem()` 과 같은 규칙이라
    `posts28/` 파일명과 짝이 맞는다."""
    return C.IMAGES_DIR / ("%s_%03d.%s" % (stem, index, ext))


def existing_image(stem, index, purge=True):
    """이미 받아 둔 **유효한** 파일. 없으면 None.

    🔑 「존재」가 아니라 「유효」로 판정한다. 0바이트·HTML 오류응답은 존재하지만
       이미지가 아니므로 재시도 대상이고, 그대로 두면 다음 실행이 영구히 스킵한다.
    ⚠️ 확장자를 모른 채 찾아야 하므로(형식은 응답이 정한다) glob 으로 훑는다.
    """
    for path in sorted(C.IMAGES_DIR.glob("%s_%03d.*" % (stem, index))):
        try:
            head = path.read_bytes()[:16]
        except OSError:
            continue
        if image_ext(head):
            return path
        if purge:
            # 무효한 잔해를 남기면 「존재=스킵」으로 되돌렸을 때 다시 영구 스킵이 된다.
            path.unlink()
    return None


def fetch_image(url, timeout=IMAGE_TIMEOUT):
    """(blob, ext, error). 실패면 blob·ext 가 None 이고 error 에 사유가 있다.

    🔑 응답을 **메모리로** 받는다. `-o` 로 파일에 직접 쓰면 실패해도 파일이 생겨
       재실행이 스킵한다 — 이 스크립트가 고치는 결함이 바로 그것이다.
    `-f` 는 HTTP 4xx/5xx 를 종료코드 22 로 만든다(본문 대신 오류 페이지를 저장하는
    사고를 curl 단계에서 끊는다). `-L` 은 리다이렉트를 따라간다.
    """
    r = subprocess.run(
        ["curl", "-s", "-f", "-L", "-m", str(timeout), "-A", C.UA,
         "-H", "Referer: https://m.blog.naver.com/" + C.BLOG, url],
        capture_output=True)
    if r.returncode != 0:
        return None, None, "CURL_EXIT:" + str(r.returncode)
    if not r.stdout:
        return None, None, "EMPTY_RESPONSE"
    ext = image_ext(r.stdout)
    if ext is None:
        return None, None, ("NOT_AN_IMAGE bytes=" + str(len(r.stdout))
                            + " head=" + repr(r.stdout[:12]))
    return r.stdout, ext, None


def plan_jobs(stems, kinds=DEFAULT_KINDS, read=None):
    """대상 글들의 내려받을 목록. **(jobs, skipped_by_kind, missing_stems)**.

    🔴 번호(index)는 **필터를 통과한 순서**로 **내려받기 전에** 매긴다. 성공한 것만
       세면 한 장이 실패했을 때 뒤 번호가 전부 밀려 「몇 번째 그림」이 어긋난다.
       판독 에이전트에게 번호는 맥락이므로 밀리면 조용히 틀린 판독이 된다.
    """
    read = read or (lambda stem: (C.POSTS_DIR / (stem + ".html")).read_text(encoding="utf-8"))
    jobs, skipped, missing = [], {}, []
    for stem in stems:
        try:
            src = read(stem)
        except OSError:
            missing.append(stem)
            continue
        index = 0
        for item in C.body_images(src):
            if item["kind"] not in kinds:
                skipped[item["kind"]] = skipped.get(item["kind"], 0) + 1
                continue
            jobs.append({"stem": stem, "index": index,
                         "url": item["url"], "kind": item["kind"]})
            index += 1
    return jobs, skipped, missing


def download(jobs, fetch=None, sleep=None):
    """실제로 받는다. **(받음, 스킵, 실패목록)**.

    🔑 재개 가능: 유효한 파일이 이미 있으면 요청하지 않는다. 그리고 **요청한 뒤에만**
       쉰다 — 스킵에도 쉬면 재개 실행이 아무 일도 안 하면서 몇 분씩 걸린다.
    🔑 글 하나가 실패해도 끝까지 돈다(harvest_bodies 방식 승계). 대신 실패를 모아
       파일·반환값·종료코드에 전부 드러낸다.
    """
    fetch = fetch or fetch_image
    sleep = sleep if sleep is not None else time.sleep
    C.ensure_dirs()
    got, skipped, failures = 0, 0, []
    for job in jobs:
        if existing_image(job["stem"], job["index"]):
            skipped += 1
            continue
        blob, ext, error = fetch(job["url"])
        if blob is None:
            failures.append({"stem": job["stem"], "index": job["index"],
                             "kind": job["kind"], "url": job["url"], "error": error})
        else:
            image_path(job["stem"], job["index"], ext).write_bytes(blob)
            got += 1
        sleep(IMAGE_SLEEP)
    C.IMAGE_FAIL_JSON.write_text(json.dumps(failures, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
    return got, skipped, failures


def load_targets(args):
    """대상 stem 목록. 🔑 **기본값이 「전부」가 아니다** — 안 주면 아무것도 안 받는다."""
    stems = list(args.stems or [])
    if args.targets:
        stems.extend(json.loads(open(args.targets, encoding="utf-8").read()))
    seen, out = set(), []
    for s in stems:                      # 순서 보존 중복 제거
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="대상 글의 본문 그림을 내려받는다")
    ap.add_argument("--targets", help="stem 목록 JSON 파일 (Task 11 Step 1 산출물)")
    ap.add_argument("--stems", nargs="*", help="stem 을 직접 지정")
    ap.add_argument("--kinds", default=",".join(DEFAULT_KINDS),
                    help="내려받을 정체(쉼표 구분). 가능: " + ",".join(C.IMAGE_KINDS))
    ap.add_argument("--limit", type=int, default=0, help="0 이면 제한 없음")
    ap.add_argument("--dry-run", action="store_true", help="요청 없이 목록만 낸다")
    args = ap.parse_args(argv)

    kinds = tuple(k.strip() for k in args.kinds.split(",") if k.strip())
    # 🔑 오타를 「해당 없음 0장」으로 통과시키지 않는다. 2026-08-04 급락게이트에서
    #    독립검증이 잡은 결정적 결함이 정확히 이 형태였다(`"Auto"` 를 정상으로 보고).
    unknown = [k for k in kinds if k not in C.IMAGE_KINDS]
    if unknown or not kinds:
        print("🔴 알 수 없는 --kinds:", unknown or "(비었음)",
              "· 가능:", ",".join(C.IMAGE_KINDS))
        return 2

    stems = load_targets(args)
    if not stems:
        print("🔴 대상이 없다 — --targets 또는 --stems 를 줘야 한다. "
              "이 스크립트는 대상을 스스로 정하지 않는다.")
        return 2

    jobs, skipped_kind, missing = plan_jobs(stems, kinds)
    print("대상", len(stems), "글 · 내려받을", len(jobs), "장 · 정체", ",".join(kinds))
    if skipped_kind:
        print("   제외한 슬롯", repr(dict(sorted(skipped_kind.items()))))
    if missing:
        print("🔴 저장된 HTML 이 없는 stem", len(missing), "건:", missing[:10])
    if args.limit and len(jobs) > args.limit:
        # 줄였으면 줄였다는 사실이 남아야 한다(계획서 Task 11 Step 1 의 규칙).
        print("⚠️ --limit", args.limit, "로 줄인다 —", len(jobs) - args.limit, "장을 안 받는다")
        jobs = jobs[:args.limit]
    if args.dry_run:
        for job in jobs[:20]:
            print("   ", job["stem"], "%03d" % job["index"], job["kind"], job["url"][:90])
        print("(dry-run — 요청 0회)")
        return 1 if missing else 0

    got, skipped, failures = download(jobs)
    print("받음", got, "장 · 이미 있어 건너뜀", skipped, "장 · 실패", len(failures), "장")
    if failures:
        print("🔴 실패 — 「전수」를 주장할 수 없다:")
        for f in failures[:20]:
            print("   ", f["stem"], "%03d" % f["index"], f["error"])
        print("->", C.IMAGE_FAIL_JSON)
    return 1 if (failures or missing) else 0


if __name__ == "__main__":
    raise SystemExit(main())
