# -*- coding: utf-8 -*-
"""정독 에이전트에게 줄 배치를 **결정적으로** 나눈다.

정렬 키가 (category, post_date, log_no) 이므로 입력 순서와 무관하게 같은 결과가 나온다.
"""
from __future__ import annotations


def make_batches(metas, target_chars=60000):
    """누적 텍스트 길이가 target_chars 를 넘기 직전에 배치를 끊는다.

    한 글이 혼자 target 을 넘으면 그 글만 담은 배치를 만든다(쪼개지 않는다).
    """
    ordered = sorted(metas, key=lambda m: (m["category"], m["post_date"], m["log_no"]))
    batches = []
    cur = []
    cur_len = 0
    for m in ordered:
        n = int(m.get("text_len") or 0)
        if cur and cur_len + n > target_chars:
            batches.append(cur)
            cur, cur_len = [], 0
        cur.append(m)
        cur_len += n
        if cur_len >= target_chars:
            batches.append(cur)
            cur, cur_len = [], 0
    if cur:
        batches.append(cur)
    return batches
