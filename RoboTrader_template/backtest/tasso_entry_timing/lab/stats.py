"""판정 통계량. 사전등록된 규칙 외로 PASS 를 만들지 않는다."""
from __future__ import annotations

import numpy as np
from scipy import stats as sps


def delta_t(strategy: np.ndarray, control: np.ndarray) -> tuple[float, float]:
    """거래당 초과수익과 Welch t."""
    d = float(np.mean(strategy) - np.mean(control))
    t = float(sps.ttest_ind(strategy, control, equal_var=False).statistic)
    return d, t


def white_reality_check(df: pd.DataFrame, b: int = 1000, seed: int = 20260801) -> float:
    """max-t **종목코드 블록** 부트스트랩.

    입력 df 컬럼: `cell`, `code`, `d`(= 전략 수익률 − 대조군 수익률).
    귀무: 모든 셀의 기대 초과수익 = 0.

    ⚠️ 행 단위 독립 리샘플링을 쓰지 말 것. 같은 종목·같은 시기의 거래가
       셀 간에 겹치므로 유효표본은 거래 수가 아니라 **종목 수**다.
       1~3차도 종목코드 블록을 썼다 — 방법론이 달라지면 계열 비교가 깨진다.
       (참고: 상관 있는 귀무 구성 6회에서 두 방식 모두 거짓양성 0이었다.
        블록을 채택하는 근거는 거짓양성 실측이 아니라 계열 일관성이다.)

    부트스트랩 1회 = 종목코드를 복원추출로 뽑아 **모든 셀에 같은 코드 집합을
    적용**한다. 이래야 셀 간 의존구조가 보존된다.
    """
    rng = np.random.default_rng(seed)
    codes = df["code"].unique()
    cells = list(df["cell"].unique())
    # 셀 → 종목코드 → d 배열 (부트스트랩 루프에서 재계산하지 않도록 미리 접는다)
    per = {c: {k: g["d"].to_numpy() for k, g in df[df["cell"] == c].groupby("code")}
           for c in cells}
    full = {c: np.concatenate(list(per[c].values())) for c in cells}

    def _t(x: np.ndarray) -> float:
        if len(x) < 2:
            return 0.0
        se = np.std(x, ddof=1) / np.sqrt(len(x))
        return float(np.mean(x) / se) if se > 0 else 0.0

    obs_max = max(_t(full[c]) for c in cells)

    boot_max = np.empty(b)
    for j in range(b):
        pick = rng.choice(codes, size=len(codes), replace=True)   # 셀 전체에 같은 코드 집합
        stat = []
        for c in cells:
            parts = [per[c][k] for k in pick if k in per[c]]
            if not parts:
                stat.append(0.0)
                continue
            s = np.concatenate(parts)
            se = np.std(s, ddof=1) / np.sqrt(len(s)) if len(s) > 1 else 0.0
            stat.append((np.mean(s) - np.mean(full[c])) / se if se > 0 else 0.0)
        boot_max[j] = max(stat)
    return float((np.sum(boot_max >= obs_max) + 1) / (b + 1))


def mde(n: int, sd: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """양측 alpha·주어진 power 에서 탐지 가능한 최소 평균차."""
    z_a = sps.norm.ppf(1 - alpha / 2)
    z_b = sps.norm.ppf(power)
    return float((z_a + z_b) * sd * np.sqrt(2.0 / n))
