"""산문 전용 거래 문장 -> 종목명 추출 (v5 편입 1단계).

🔴 결과변수(forward 수익률·성과)는 계산하지 않는다. 이 스크립트는 DB 를 아예 건드리지 않는다.

## 왜 사전을 안 쓰는가

직전 라운드 재사용 규칙: ***`code_map_v4.json` 은 라벨에서 파생된 사전이라 라벨에 없는 종목을
구조적으로 못 찾는다. 이걸로 산문을 검색하면 「없음」과 「못 찾음」이 구분되지 않는다.***
그래서 이 스크립트는 **두 경로**로 이름을 뽑고 서로를 기준으로 회수율을 잰다.

  (A) `READING` — 157문장을 **사람이 읽어** 뽑은 목록. 아래 표가 그 전부다.
  (B) `mech_tokens()` — 문장 구조(조사 경계)만 보는 **기계 추출**. 사전 없음.

(B) 의 토큰 중 (A) 에 없는 것은 `prose_recall_tokens.txt` 로 떨궈
**네이버 정확일치**에 걸리는지 별도 확인한다(= 사람이 놓친 종목 탐지).
어느 쪽도 상대의 후보 생성기가 아니다.

## 역할(role) — 편입 여부를 정하는 축

| role | 뜻 | 편입 |
|---|---|---|
| `entry` | 진입 문장의 거래 종목 | 🟢 |
| `order_placed` | 주문은 넣었고 미체결 (2021-10-25 두산중공업) | 🟢 **관리자 판정 J2** — 라벨 기준은 「그가 골랐는가」이지 「체결됐는가」가 아니다 |
| `notrade` | 「지켜만 봤다」·「패스」·「매수가 미도달」 = 선별 결과가 **부정** | 🔴 |
| `ambiguous` | 거래 여부 불명 (J5) | 🔴 편입하면 편향 방향을 모른다. `prose_ambiguous` 로 흔적만 |
| `reference` | 남의 종목·따라간 대장주 등, 그가 거래한 게 아님 | 🔴 |
| `entry_misclassified` | **거래한 종목인데 문장이 `진입` 이 아닌 부류로 분류됨** | 🔴 (권한 밖) + 결함 보고 |

`entry_misclassified` 는 직전 작업 분류의 결함이다. 이번 편입 대상은 관리자가 「진입 120문장
+ 두산중공업 1」로 못 박았으므로 **여기서 조용히 늘리지 않는다.** 표로만 남긴다.
"""
import argparse
import collections
import csv
import hashlib
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 🔴 `READING` 의 키는 `prose_only_candidates.csv` 의 **행 번호**다. 그 파일은
#    문장 원문을 담고 있어 `.gitignore` 로 커밋이 막혀 있고(타인 저작물), 다시 만들면
#    행 순서가 달라질 수 있다. 순서가 한 칸만 밀려도 **판독이 엉뚱한 문장에 붙는데
#    산출물에는 아무 흔적이 남지 않는다.** 그래서 지문을 박아 두고 시작 전에 막는다.
#    (게이트를 코드 순서로 강제 — 7차에서 가장 효과가 컸던 장치)
SRC_FINGERPRINT = "898759a3f055a7c548feed57769f8e4c8e81f702e138a722a1fe2a75f3450c46"

# ---------------------------------------------------------------------------
# (A) 사람이 읽은 결과. key = prose_only_candidates.csv 의 데이터 행 번호(1-based).
#     값 = [(종목명, role, 비고)]. 이름은 **본문 표기 그대로** 적는다(오타 포함) —
#     교정하면 그 순간 유사매칭이 되고, 7차 교훈(정답 없이 조용히 매칭)을 어긴다.
# ---------------------------------------------------------------------------
READING = {
    2: [("동구바이오제약", "entry_misclassified", "약수익권으로 매매 종료 = 거래함. 문장은 종목불특정으로 분류됨"),
        ("동국S&C", "entry_misclassified", "동상")],
    3: [("신풍제약", "entry", "")],
    4: [("나인테크", "notrade", "매매하려 했으나"), ("에이치엘비", "notrade", "매매하려 했으나"),
        ("신성델타테크", "entry_misclassified", "「확실한 종목 … 를 거래했습니다」 = 거래함"),
        ("제노포커스", "entry_misclassified", "동상")],
    5: [("아난티", "entry", "")],
    6: [("멕스로텍", "entry", "표기 그대로(맥스로텍 오타 추정) — 교정하지 않는다")],
    7: [("파워로직스", "entry", ""), ("컬러레이", "entry", "")],
    8: [("우진", "entry", ""), ("제일약품", "entry", ""), ("케이씨에스", "entry", "")],
    10: [("태경케미칼", "entry", "")],
    11: [("오텍", "entry", "")],
    13: [("현대약품", "entry", ""), ("KPX생명과학", "entry", "")],
    14: [("대원전선", "ambiguous", "「매매할 종목이 있었습니다」"), ("압타바이오", "ambiguous", "동상")],
    15: [("코프라", "entry", ""), ("유니온커뮤니티", "entry", ""), ("삼성에스디에스", "entry", "")],
    16: [("삼화네트웍스", "ambiguous", "판단만 서술, 거래 진술 없음")],
    17: [("금호석유", "entry", "")],
    18: [("두산밥캣", "entry", ""), ("강스템바이오", "entry", "표기 그대로(강스템바이오텍 축약 추정)"),
         ("한양이엔지", "entry", ""), ("태경비케이", "entry", "")],
    19: [("엘컴텍", "entry", "")],
    20: [("레인보우틱스", "entry", "표기 그대로(레인보우로보틱스 오타 추정)"), ("모비스", "entry", "")],
    21: [("한신기계", "entry", "")],
    22: [("대원미디어", "notrade", "떴으나 거래를 못해"),
         ("SM", "entry_misclassified", "「SM으로 두번 수익을 내줬습니다」 = 거래함")],
    23: [("이구산업", "notrade", "못한것이 아쉽네요")],
    25: [("한네트", "entry", ""), ("피비파마", "entry", ""), ("풍산", "entry", ""), ("양지사", "entry", "")],
    26: [("삼화네트웍스", "entry", ""), ("NE능률", "entry", ""), ("서연이화", "entry", ""),
         ("하이스틸", "entry", ""), ("티플렉스", "entry", "")],
    27: [("에코캡", "notrade", "매수가가 오지않았고요")],
    29: [],   # 「이외의 종목들은 …」 — 진입으로 분류됐으나 **종목 불특정**. 결함.
    30: [("DSR 제강", "entry", "공백 포함 표기")],
    31: [("YBM넷", "ambiguous", "「접근할듯말듯 하다가 … 진입을 했었는데」 문장이 끊김")],
    32: [("메디콕스", "notrade", "트레이딩을 하지 못헀습니다")],
    34: [("아즈텍", "entry", "표기 그대로(아즈텍WB 축약 추정)"), ("켐트로스", "entry", "")],
    36: [("영화테크", "ambiguous", "제대로 트레이딩하지 못했습니다"), ("인스코비", "ambiguous", "동상")],
    37: [("바이오니아", "entry", "")],
    38: [("한화투자증권", "entry", "극소액으로 매수")],
    39: [("네오이뮨택", "notrade", "지켜만 보았는데요"), ("삼진엘앤디", "notrade", "동상"),
         ("국보", "notrade", "동상")],
    40: [("두산중공업", "order_placed", "🟢 J2 — 매수를 걸어두었지만 체결되지 않음. 선별은 완료")],
    41: [("위메이드맥스", "notrade", "신중히 했습니다 = 미거래")],
    42: [("경남스틸", "entry", "")],
    43: [("맥스트", "entry", "")],
    44: [("네오크레마", "entry", "")],
    46: [("다날", "entry", "")],
    47: [("아톤", "entry", "")],
    48: [("하이비젼시스템", "entry", "")],
    49: [("넥슨지티", "notrade", "매매대상에 제외")],
    50: [("한화투자증권", "entry", "")],
    52: [("퍼스텍", "entry", "")],
    53: [("로보로보", "entry", ""),
         ("에브리봇", "reference", "「에브리봇을 따라가는 흐름」 — 따라간 대상, 그가 거래한 게 아님")],
    54: [("제주맥주", "entry", "")],
    55: [("SG&G", "entry", "")],
    56: [("네오오토", "ambiguous", "「공략할 종목들이 어느정도 있었네요」"), ("대원전선", "ambiguous", "동상")],
    57: [("금양", "entry", "")],
    58: [("미투온", "entry", "일부만 체결 = 진입"), ("모나미", "entry", "")],
    59: [("일동홀딩스", "entry", ""), ("KG스틸", "entry", "")],
    61: [("메이슨캐피탈", "entry", "")],
    62: [("태경케미칼", "entry", "")],
    63: [("우림피티에스", "entry", "")],
    64: [("HLB", "entry", ""), ("한탑", "entry", "")],
    65: [("성도이엔지", "entry", ""), ("공구우먼", "entry", "")],
    66: [("큐라클", "entry", "")],
    67: [("HK이노엔", "entry", "")],
    68: [("노터스", "entry", "")],
    69: [("수젠텍", "notrade", "패스"), ("포바이포", "notrade", "패스")],
    70: [("켐온", "ambiguous", "「매매할 구간이 나와주었네요」 — 구간 서술")],
    71: [("희림", "entry", "")],
    72: [("멕아이씨에스", "entry", ""), ("매디아나", "entry", "표기 그대로(메디아나 오타 추정)"),
         ("솔본", "entry", "")],
    73: [("청담글로벌", "entry", "")],
    74: [("인포바인", "notrade", "거래를 하지 못했습니다")],
    75: [("그린케미칼", "entry", "")],
    76: [("켐트로스", "entry", "")],
    77: [("아이원", "entry", "")],
    78: [("금강철강", "entry", "")],
    80: [("한일사료", "entry", "")],
    81: [("네오위즈", "entry", "")],
    82: [("금양", "entry", "")],
    83: [("에코플라스틱", "entry", "")],
    84: [("오토앤", "entry", "")],
    85: [("브이씨", "entry", "")],
    86: [("저스템", "entry", "")],
    87: [("디어유", "entry", "")],
    88: [("어보브반도체", "entry", "")],
    89: [("성우하이텍", "entry", "")],
    90: [("가온칩스", "entry", "")],
    91: [("조일알미늄", "entry", "")],
    92: [("한미반도체", "entry", "")],
    93: [("레이크머티리얼", "entry", "표기 그대로(레이크머티리얼즈 축약 추정)")],
    94: [("후성", "entry", "")],
    95: [("제이오", "entry", "")],
    96: [("엔켐", "entry", "")],
    97: [("인탑스", "notrade", "못하였네요")],
    98: [("원준", "entry", "")],
    99: [("주성엔지니어링", "entry", "")],
    100: [("윤성에프엔씨", "entry", "표기 그대로(윤성에프앤씨 오타 추정)")],
    101: [("윤성에프앤씨", "entry", "")],
    102: [("지아이텍", "entry", "")],
    103: [("KBG", "entry", "")],
    104: [("솔루엠", "entry", "")],
    105: [("현대무백스", "notrade", "패스하였습니다. 표기 그대로(현대무벡스 오타 추정)")],
    106: [("코리아에프티", "entry", "")],
    107: [("케이엔제이", "entry", "")],
    108: [("디와이디", "entry", "")],
    109: [("성문전자", "entry", "")],
    110: [("에코바이오", "entry", "")],
    111: [("아비코전자", "entry", "")],
    112: [("대상홀딩스", "entry", "")],
    113: [("넥스트칩", "entry", "")],
    114: [("티로보틱스", "entry", "")],
    115: [("지노믹트리", "entry", "")],
    116: [("TCC스틸", "entry", "")],
    117: [("퓨런티어", "entry", "")],
    118: [("금양", "entry", "")],
    119: [("미래컴퍼니", "entry", "")],
    120: [("솔브레인홀딩스", "entry", "")],
    121: [("포스코DX", "entry", "")],
    122: [("에코바이오", "entry", "")],
    123: [("대동기어", "entry", "")],
    124: [("브이티", "entry", "")],
    125: [("신성델타테크", "entry", "")],
    126: [("엘컴텍", "entry", "")],
    127: [("이글벳", "entry", "")],
    128: [("에스티아이", "entry", "")],
    129: [("멕아이씨", "entry", "표기 그대로(멕아이씨에스 축약 추정)")],
    130: [("위더스제약", "entry", "")],
    131: [("유니온", "entry", "")],
    132: [("한화솔루션", "entry", "")],
    133: [("스톤브릿지", "entry", "표기 그대로(스톤브릿지벤처스 축약 추정)")],
    134: [("씨씨에스", "entry", "")],
    135: [("화천기계", "entry", "")],
    138: [("대한전선", "entry", "")],
    139: [("와이씨", "entry", "")],
    140: [("지투파워", "entry", "")],
    141: [("우양", "entry", ""), ("태성", "entry", "")],
    142: [("코오롱글로벌", "entry", "")],
    143: [("삼천당제약", "entry", "")],
    144: [("대한해운", "entry", "")],
    145: [("제룡전기", "entry", "")],
    146: [("SG글로벌", "entry", "")],
    147: [("에스피시템스", "entry", "표기 그대로(에스피시스템스 오타 추정)")],
    148: [("하이젠알엔엠", "entry", "")],
    149: [("렙지노믹스", "entry", "표기 그대로(랩지노믹스 오타) — v3 ALIAS 에 이유가 기록돼 있다")],
    150: [("그리드위즈", "entry", "")],
    151: [("태성", "entry", ""), ("바이넥스", "entry", "")],
    153: [("원익", "entry", "")],
    157: [("신성이엔지", "entry", "")],
}

# ---------------------------------------------------------------------------
# (B) 기계 추출 — 사전 없음. 조사 경계로만 후보 토큰을 자른다.
# ---------------------------------------------------------------------------
PARTICLE = r"(?:은|는|이|가|을|를|도|와|과|랑|이나|나|에|의|에서|으로|로|만)"
TOKEN = r"[가-힣A-Za-z][가-힣A-Za-z0-9&\.]*"


def mech_tokens(sentence: str):
    """조사가 붙은 명사 토큰을 전부 뽑는다. 종목/비종목을 구분하지 않는다 —
    구분은 **네이버 정확일치**가 한다(사전을 쓰면 「없음」과 「못 찾음」이 섞인다)."""
    out = []
    for chunk in re.split(r"[,\(\)\[\]/·\"'\s]+", sentence):
        if not chunk:
            continue
        m = re.match(r"^(" + TOKEN + r")" + PARTICLE + r"?$", chunk)
        cand = m.group(1) if m else None
        if cand is None:
            m2 = re.match(r"^(" + TOKEN + r")", chunk)
            cand = m2.group(1) if m2 else None
        if cand and len(cand) >= 2:
            out.append(cand)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="prose_only_candidates.csv")
    ap.add_argument("--fingerprint", action="store_true",
                    help="후보 파일의 지문만 출력하고 끝낸다")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.src, encoding="utf-8-sig")))
    fp = hashlib.sha256("\n".join(
        f"{r['post_date']}|{r['logNo']}|{r['class']}|{r['sentence']}" for r in rows
    ).encode("utf-8")).hexdigest()
    if args.fingerprint:
        print("SRC_FINGERPRINT =", fp)
        return 0
    if fp != SRC_FINGERPRINT:
        print("🔴 중단 — 후보 파일이 판독 당시와 다르다.")
        print(f"   기대 {SRC_FINGERPRINT}\n   실제 {fp}")
        print("   READING 의 키는 행 번호다. 행이 밀리면 판독이 남의 문장에 붙는다.")
        print("   파일을 확인하고, 정말 갱신본이면 --fingerprint 로 새 값을 받아 박을 것.")
        return 2
    print(f"후보 문장 {len(rows)}건 · 글 {len({r['logNo'] for r in rows})}건")
    print("부류:", dict(collections.Counter(r["class"] for r in rows)))

    # ---- (A) 사람 판독 -> prose_names.csv ----
    out = []
    for i, r in enumerate(rows, 1):
        for name, role, note in READING.get(i, []):
            out.append({"idx": i, "post_date": r["post_date"], "logNo": r["logNo"],
                        "class": r["class"], "name": name, "role": role, "note": note})
    with open("prose_names.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["idx", "post_date", "logNo", "class",
                                           "name", "role", "note"])
        w.writeheader()
        w.writerows(out)

    print(f"\n=== (A) 사람 판독: (문장,종목) {len(out)}건 · 고유이름 "
          f"{len({o['name'] for o in out})} ===")
    byrole = collections.Counter(o["role"] for o in out)
    for role in ("entry", "order_placed", "notrade", "ambiguous", "reference",
                 "entry_misclassified"):
        print(f"  {role:<20}{byrole.get(role, 0):>4}")

    # 분류 결함: class 와 role 이 어긋나는 문장
    print("\n=== 🔴 직전 분류의 결함 ===")
    ent_sent = {o["idx"] for o in out if o["role"] in ("entry", "order_placed")}
    for i, r in enumerate(rows, 1):
        got = READING.get(i, [])
        if r["class"] == "진입" and not got:
            print(f"  [{i}] {r['post_date']} 진입으로 분류됐으나 **종목 불특정**: "
                  f"{r['sentence'][:60]}")
        if any(o[1] == "entry_misclassified" for o in got):
            names = ",".join(o[0] for o in got if o[1] == "entry_misclassified")
            print(f"  [{i}] {r['post_date']} class={r['class']} 인데 거래한 종목 존재: {names}")

    # ---- (B) 기계 추출 -> 회수 대조용 토큰 ----
    gold = {(o["idx"], re.sub(r"\s+", "", o["name"])) for o in out}
    extra = collections.defaultdict(set)
    for i, r in enumerate(rows, 1):
        for tok in mech_tokens(r["sentence"]):
            if (i, re.sub(r"\s+", "", tok)) not in gold:
                extra[tok].add(i)
    with open("prose_recall_tokens.txt", "w", encoding="utf-8") as fh:
        for tok in sorted(extra):
            fh.write(tok + "\n")
    print(f"\n=== (B) 기계 추출: 사람 판독에 없는 토큰 {len(extra)}종 "
          f"-> prose_recall_tokens.txt (네이버 정확일치로 선별) ===")

    print(f"\n-> prose_names.csv ({len(out)}행) · prose_recall_tokens.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
