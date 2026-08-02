"""본문 기반 라벨 추출 (2017~2026 전수).

v1 의 회수 결함(`^\\d+[.,]` **번호 접두를 요구**해 번호 없는 헤더를 통째로 놓침)을 반복하지 않는다.
전수로 넓히며 추가로 확인된 항목 형식:

    1. 흥국에프엔비 / 10일 이동평균선 반등 / 수익률 3.89%, 3.60%      (2021, 번호 O)
    모나리자 / 신고가 돌파 / 시가베팅(종베관점), 급등주 투매폭 / 수익률 13.38%   (2017, 번호 X · 필드 4개)
    가온칩스 / 통계기반 자동매매 / 수익률 25.10%                      (2026, 번호 X)

=> (a) 번호 접두는 **선택**, (b) 종목명과 「수익률/손실률」 사이의 `/` 필드 수는 **가변**,
   (c) 불릿(`-`,`·`,`※`,`▶`)으로 시작하는 줄은 설명이므로 헤더가 아니다.

⚠️ 산문에 등장하는 종목명(*"검색기에 태양금속도 포착되었는데요"*)은 **거래가 아니므로 넣지 않는다.**
   그런 누락은 제목 라벨과의 합집합으로 메운다(제목은 실제 매매 종목만 적힌다).

🔴 v4 초판의 결함: `preset` 이 **모드 수식어를 버렸다.**
   저자는 캡션에 「사분위수(Q1~Q3) 하이브리드」·「HDR 60 하이브리드」처럼 **깊이 분포를 어느 모드로
   계산했는지**를 함께 적는데, 후보를 기저 토큰(하이브리드/안정형/…)으로만 두면 그 수식어가
   조용히 사라진다. 이건 표기 흔들림이 아니라 **정보 손실**이다 — `ANCHOR_STRATEGY.md` §3 이
   앵커 식별 구조가설의 증거로 바로 이 모드 표기를 쓰고, 층화(Q: 낙폭 분위수 / HDR-60)의 키가 된다.
   ⇒ `preset` 은 **캡션 원문 그대로**, 파생은 `preset_base`·`preset_mode` 로 **분리**해서 낸다.

출력: body_labels.csv
   (post_date, logNo, stock_name, method, preset, preset_base, preset_mode, preset_mode_src, n_items)
   preset          캡션 원문 전체 (예: `사분위수(Q1~Q3) 하이브리드`) — 복원 기준
   preset_base     하이브리드 / 안정형 / 표준형 / 공격형 / 방어형 / (빈)
   preset_mode     사분위 / HDR / HDR50 / HDR60 / HDR80 / 미표기
   preset_mode_src caption(캡션에서) / body(산문에서) / (빈=미표기)
"""
import argparse
import collections
import csv
import datetime
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 헤더: [번호.] 종목명 / (가변 필드) / 수익률|손실률
ITEM = re.compile(
    r"^[ \t]*(?:\d{1,2}\s*[.,)]\s*)?"          # 번호는 선택
    r"(?![-–—·•※▶◆★*])"                        # 불릿으로 시작하면 설명 줄
    r"([^/\n]{2,24}?)\s*/"                     # 종목명 (첫 슬래시 앞)
    r"((?:[^/\n]{0,60}/){0,3})"                # 방법 등 가변 필드 0~3개
    # 키워드 사이 공백 허용 — 저자가 「수」/「익률」을 다른 색으로 칠해 스팬이 갈리는 경우가 있다
    r"[^/\n]{0,20}?(?:수\s*익\s*률|손\s*실\s*률|손\s*절\s*률)",
    re.M)
LEAD_NUM = re.compile(r"^\d+\s*[.,)]?\s*")
# 종목명 자리에 올 수 없는 것들 (설명 문장이 잘려 들어오는 경우)
BAD_NAME = re.compile(r"(매수|매도|수익|손실|종목|오늘|어제|시장|거래|보유|진입|청산|이렇게|합니다|했습니다)")

PRESETS = ("하이브리드", "안정형", "공격형", "표준형", "방어형")

# 캡션: 「▲ 통계기반 계산기(Ver 1.4) - 사분위수(Q1~Q3) 하이브리드 *중요한 수치는 가렸습니다.」
# 구분자는 캡션형 대시만 받는다. 화살표(→)는 산문 서술이라 문장이 통째로 딸려온다
# (*"계산기(Ver 1.4) → HDR 하이브리브, 1차 구간 지지확인"* — 오타 「하이브리브」까지 들어온다).
CAPTION = re.compile(r"계산기\s*\(?\s*Ver\s*[\d.]+\s*\)?\s*[-–—]\s*([^\n*]+)")
# 모드 수식어. 「4분위수 Q1」처럼 아라비아 숫자 표기도 저자가 같은 글에서 섞어 쓴다.
QUARTILE = re.compile(r"(?:사|4)\s*분위")
HDR_N = re.compile(r"HDR\s*(\d{1,3})")
# 산문에 모드만 적힌 경우(캡션엔 없음). **그 항목의 매매 서술**일 때만 받는다 —
# 글 말미의 총평(*"조정장이 오면 HDR 범위를 변경하고…"* · *"대장주는 하락폭 HDR 60% 끝단이상…"*)은
# 항목 블록 안에 들어와도 그 거래의 설정값이 아니다.
ACTION = re.compile(r"매수|진입|체결|타점")


def norm(name: str) -> str:
    return re.sub(r"\s+", "", name)


def base_of(s: str) -> str:
    hits = [(s.find(p), p) for p in PRESETS if p in s]
    return min(hits)[1] if hits else ""


def mode_of(s: str) -> str:
    if QUARTILE.search(s):
        return "사분위"
    m = HDR_N.search(s)
    if m:
        return "HDR" + m.group(1)
    if "HDR" in s:
        return "HDR"
    return ""


def preset_in(block: str):
    """(preset 원문, preset_base, preset_mode, preset_mode_src) 반환.

    🔴 v3 는 (a) 블록 시작을 「제목의 종목명 등장 위치」로 잡고 (b) 후보를 **목록 순서**로 훑었다.
       두 결함이 겹치면 다른 종목의 프리셋이 넘어온다 — 2026-03-13 와이제이링크는 본문에
       *"통계기반 계산기(Ver 1.3) - **안정형**"* 이라고 명시돼 있는데, 블록이 제목에서 시작해
       다음 종목(코데즈컴바인·하이브리드)까지 삼켰고 목록 순서상 「하이브리드」가 먼저 검사돼
       **하이브리드로 잘못 붙었다.** 정답이 본문에 있는데도 조용히 다른 값이 붙는 유형이다.
    ⇒ 블록은 **그 항목 헤더 ~ 다음 항목 헤더**로 자르고, 선택은 **위치가 가장 앞선 것**으로 한다.

    🔴 v4 초판은 여기서 한 번 더 잃었다. 후보를 기저 토큰 5개로만 두면 캡션의
       「사분위수(Q1~Q3) / HDR 60」이 잘려나간다. ⇒ **캡션 원문을 먼저** 집고,
       기저 토큰 스캔은 캡션이 없을 때의 폴백으로만 남긴다.
       캡션이 여러 장인 블록이 있으므로(*"- 반등폭"* = 분할매도 표) **기저 프리셋을 포함한
       첫 캡션**을 고른다.
    """
    raw = ""
    for m in CAPTION.finditer(block):
        expr = m.group(1).strip().strip("*").strip()
        if base_of(expr):
            raw = expr
            break
    if not raw:  # 캡션 없음 -> 종전 폴백: 위치가 가장 앞선 기저 토큰
        raw = base_of(block)

    mode, src = mode_of(raw), ""
    if mode:
        src = "caption"
    else:
        for line in block.split("\n"):
            if HDR_N.search(line) and ACTION.search(line):
                mode, src = "HDR" + HDR_N.search(line).group(1), "body"
                break
    return raw, base_of(raw), mode or "미표기", src


def parse_body(txt: str):
    """[(name, method, preset, base, mode, mode_src)] 반환. 같은 글 안 중복은 첫 등장만."""
    ms = list(ITEM.finditer(txt))
    out, seen = [], set()
    for i, m in enumerate(ms):
        name = LEAD_NUM.sub("", m.group(1).strip()).strip()
        name = re.sub(r"\s+", " ", name).strip(" .,·-")
        if len(norm(name)) < 2 or BAD_NAME.search(name):
            continue
        method = re.sub(r"\s+", " ", m.group(2).strip(" /")).strip()
        k = norm(name)
        if k in seen:
            continue
        seen.add(k)
        # 블록 = 이 항목 헤더 ~ 다음 항목 헤더(없으면 +600자 상한)
        end = ms[i + 1].start() if i + 1 < len(ms) else min(len(txt), m.start() + 600)
        out.append((name, method) + preset_in(txt[m.start():end]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="body_labels.csv")
    args = ap.parse_args()

    posts = {str(p["logNo"]): p for p in
             json.load(open("tasso_postlist.json", encoding="utf-8"))}

    rows, per_year, per_year_posts, zero = [], collections.Counter(), collections.Counter(), []
    import glob
    for f in sorted(glob.glob("text/*.txt")):
        base = os.path.basename(f).replace(".txt", "")
        date_s, log_no = base.split("_")
        dt = datetime.datetime.strptime(date_s, "%Y%m%d")
        txt = open(f, encoding="utf-8").read()
        items = parse_body(txt)
        per_year_posts[dt.year] += 1
        if not items:
            zero.append((f"{dt:%Y-%m-%d}", log_no, len(txt)))
        for name, method, preset, base, mode, msrc in items:
            rows.append({"post_date": f"{dt:%Y-%m-%d}", "logNo": log_no,
                         "stock_name": name, "method": method,
                         "preset": preset, "preset_base": base,
                         "preset_mode": mode, "preset_mode_src": msrc,
                         "n_items": len(items)})
            per_year[dt.year] += 1

    with open(args.out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["post_date", "logNo", "stock_name",
                                           "method", "preset", "preset_base",
                                           "preset_mode", "preset_mode_src", "n_items"])
        w.writeheader()
        w.writerows(rows)

    print(f"본문라벨 {len(rows)} · 고유종목 {len({norm(r['stock_name']) for r in rows})}")
    print(f"항목 0건인 글 {len(zero)}건")
    print(f"\n{'연도':<6}{'본문파일':>9}{'본문라벨':>9}{'라벨0글':>9}")
    zc = collections.Counter(d[:4] for d, _, _ in zero)
    for y in sorted(per_year_posts):
        print(f"{y:<6}{per_year_posts[y]:>9}{per_year[y]:>9}{zc[str(y)]:>9}")
    print(f"-> {args.out}")
    if zero:
        print("\n=== 항목 0건 글 (앞 40) ===")
        for d, ln, n in zero[:40]:
            print(f"   {d} {ln} 본문{n}자")

    # ---- 모드 표기 전수 감사 ----
    # ⚠️ 「캡션에서 뽑았다」만 보고하면 **버린 것이 산출물에 흔적을 안 남긴다.** 코퍼스 전체에서
    #    모드 토큰이 나오는 줄을 전부 세어, 라벨에 실린 수와 대조한다(회수·기각 양쪽 다 보이게).
    print("\n=== 모드 표기 전수 감사 (코퍼스 858글 전체) ===")
    got = {(r["post_date"], norm(r["stock_name"])): r["preset_mode"]
           for r in rows if r["preset_mode"] != "미표기"}
    hits = 0
    for f in sorted(glob.glob("text/*.txt")):
        d = os.path.basename(f)[:8]
        for i, line in enumerate(open(f, encoding="utf-8").read().split("\n"), 1):
            if not (QUARTILE.search(line) or "HDR" in line):
                continue
            hits += 1
            cap = bool(CAPTION.search(line))
            why = ("캡션" if cap else
                   ("산문·매매서술" if HDR_N.search(line) and ACTION.search(line)
                    else "미채택(같은 항목 중복 서술 또는 글 말미 총평)"))
            print(f"   {d[:4]}-{d[4:6]}-{d[6:]} L{i:<3} [{why}] {line.strip()[:78]}")
    print(f"   총 {hits}줄 · 라벨에 모드가 실린 (날짜,종목) {len(got)}건")
    for k, v in sorted(got.items()):
        print(f"      {k[0]} {k[1]:<16} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
