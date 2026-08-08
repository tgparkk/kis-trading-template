"""PIT as-of 조인 — 「그날 알 수 있었던 재무」를 고르는 단 하나의 함수.

🔴 이 파일이 틀리면 look-ahead 가 조용히 들어오고 이후 모든 검정이 무효가 된다.
   정렬 키는 «사업연도» 가 아니라 «접수일(rcept_dt)» 이다.

⚠️ 08-07 시총 백필의 교훈(「look-ahead 규약을 과거 사실의 복원에 적용하지 말 것」)과
   방향이 «반대» 다. 여기는 복원이 아니라 예측이고, 재무는 보고서가 접수되기 전엔
   실제로 아무도 몰랐다. 두 규칙은 모순이 아니라 목적이 다르다.
"""
import re


_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _daystr(v):
    """'YYYY-MM-DD' 로 정규화. `datetime.date`·`datetime`·`Timestamp` 도 받는다.

    🔴 이게 필요한 이유: 적재 테이블의 `rcept_dt` 는 DATE 컬럼이라 psycopg2 가
       `datetime.date` 로 돌려준다. 반면 정규화 JSONL 에서 읽으면 문자열이다.
       섞이면 파이썬 3 에서 date 와 str 비교가 **TypeError** 로 죽는다 —
       조용히 틀리지는 않지만, 소비자가 어디서 읽느냐에 따라 터진다.

    🔴 형식을 **검사**하고 어긋나면 예외를 낸다. 비교가 문자열 사전순이라
       `'2023-3-5'`(0 패딩 없음) 같은 값은 **조용히 틀린 답**을 낸다 —
       `'2023-3-5' > '2023-12-01'` 이 참이 된다. 이 모듈이 막으려는 실패 유형이
       바로 그것이므로, 여기서는 «시끄럽게 실패»하는 쪽이 옳다.
    """
    if v is None:
        return None
    s = str(v)[:10]
    if not s:
        return None          # 빈 값은 「모른다」 — 건너뛸 대상이지 오류가 아니다
    if not _DAY_RE.match(s):
        raise ValueError(f"날짜 형식이 'YYYY-MM-DD' 가 아니다: {v!r}")
    return s


def asof_financials(records, as_of):
    """rcept_dt <= as_of 인 것 중 rcept_dt 가 가장 늦은 레코드. 없으면 None.

    동률(같은 날 접수)이면 **사업연도가 큰 쪽**을 고른다 — 정정공시·재제출이
    같은 날짜로 들어올 수 있고, 입력 순서에 따라 답이 바뀌면 안 된다.
    """
    as_of = _daystr(as_of)
    best = None
    best_key = None
    for r in records:
        dt = _daystr(r.get("rcept_dt"))
        if not dt:
            continue  # 언제 공개됐는지 모르는 값은 쓸 수 없다
        if dt > as_of:
            continue
        key = (dt, str(r.get("bsns_year") or ""))
        if best_key is None or key > best_key:
            best, best_key = r, key
    return best
