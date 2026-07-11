# scripts/discovery/multiframe_chart_cnn/poc_train.py
"""PoC: 차트 이미지 CNN이 무조건 진입 기저율을 이기는가(인샘플/1폴드 워크포워드).

사전등록 게이트(.superpowers/sdd/plan2-preregistration.md, 커밋 8e57d54): CNN의
가치 = **베타 초과 lift**(선별 subset net − 그 구간 무조건 net), 워크포워드에서.
이 PoC는 소규모·이미지전용·시간순 1폴드 분할로 "인샘플에서 lift>0 이 나오긴 하나"만
확인한다. 안 나오면 전체 28GB 빌드/CUDA 착수 안 함.

score = P(tp) − P(sl). 상위 --top-pct 를 매수로 보고 sel_net 계산.
lift = sel_gross − base_gross (비용 상쇄). 안전장치: sel_gross > 0.0021(절대 net>0).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROUND_TRIP_COST = 0.0021
CACHE_DIR = Path(__file__).parent / "_cache"
OUTCOMES = ["tp", "sl", "timeout"]


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    denom = np.sqrt((ra * ra).sum() * (rb * rb).sum())
    return float((ra * rb).sum() / denom) if denom > 0 else 0.0


def _daily_demeaned_ic(score: np.ndarray, ret: np.ndarray, dates: np.ndarray) -> float:
    """일단위 시장평균 제거 후 스피어만 (횡단면 IC 근사)."""
    df = pd.DataFrame({"s": score, "r": ret, "d": dates})
    df["r_dm"] = df["r"] - df.groupby("d")["r"].transform("mean")
    return _spearman(df["s"].to_numpy(), df["r_dm"].to_numpy())


def build_model(in_ch: int = 6):
    import torch.nn as nn
    return nn.Sequential(
        nn.Conv2d(in_ch, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),   # 32
        nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),      # 16
        nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),      # 8
        nn.AdaptiveAvgPool2d(1), nn.Flatten(),
        nn.Linear(64, 64), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(64, 3),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(CACHE_DIR))
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--top-pct", type=float, default=0.2)
    ap.add_argument("--train-frac", type=float, default=0.7)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    import torch
    import torch.nn as nn
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    d = Path(args.data_dir)
    images = np.load(d / "images.npy")            # (N,6,64,64) uint8
    meta = pd.read_parquet(d / "meta.parquet")
    assert len(images) == len(meta), (len(images), len(meta))
    print(f"loaded {len(images)} samples, image {images.shape[1:]}, "
          f"dist tp/sl/to = "
          f"{(meta['outcome']=='tp').mean():.3f}/{(meta['outcome']=='sl').mean():.3f}/"
          f"{(meta['outcome']=='timeout').mean():.3f}")

    # 시간순 1폴드 분할 (날짜 단위, 누수 없음).
    dates = np.sort(meta["trade_date"].unique())
    cut = dates[int(len(dates) * args.train_frac)]
    tr_mask = (meta["trade_date"] < cut).to_numpy()
    te_mask = ~tr_mask
    print(f"train dates <{cut}: {tr_mask.sum()} | test >={cut}: {te_mask.sum()}")

    y = meta["outcome"].map({o: i for i, o in enumerate(OUTCOMES)}).to_numpy()
    ret = meta["realized_ret"].to_numpy(dtype=np.float64)

    Xtr = torch.from_numpy(images[tr_mask].astype(np.float32) / 255.0)
    ytr = torch.from_numpy(y[tr_mask]).long()
    Xte = torch.from_numpy(images[te_mask].astype(np.float32) / 255.0)

    # 클래스 불균형 가중.
    counts = np.bincount(y[tr_mask], minlength=3).astype(np.float64)
    w = torch.from_numpy((counts.sum() / (3 * np.maximum(counts, 1))).astype(np.float32))
    model = build_model(images.shape[1])
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    lossf = nn.CrossEntropyLoss(weight=w)

    n = len(Xtr)
    for ep in range(args.epochs):
        model.train()
        perm = torch.randperm(n)
        tot = 0.0
        for i in range(0, n, args.batch):
            idx = perm[i:i + args.batch]
            opt.zero_grad()
            out = model(Xtr[idx])
            loss = lossf(out, ytr[idx])
            loss.backward()
            opt.step()
            tot += loss.item() * len(idx)
        print(f"epoch {ep+1}/{args.epochs} train_loss={tot/n:.4f}", flush=True)

    # 평가 (train/test 둘 다 — "신호없음" vs "과적합" 구분).
    def _scores(X):
        out = []
        for i in range(0, len(X), args.batch):
            out.append(model(X[i:i + args.batch]))
        return torch.softmax(torch.cat(out), dim=1).numpy()

    model.eval()
    with torch.no_grad():
        prob_te = _scores(Xte)
        prob_tr = _scores(Xtr)

    def _report(tag, prob, mask):
        score = prob[:, 0] - prob[:, 1]          # P(tp) - P(sl)
        r = ret[mask]
        dts = meta["trade_date"].to_numpy()[mask]
        base = float(r.mean())
        k = max(1, int(len(score) * args.top_pct))
        top = np.argsort(-score)[:k]
        sel = float(r[top].mean())
        lift = sel - base
        ic = _spearman(score, r)
        ic_dm = _daily_demeaned_ic(score, r, dts)
        print(f"\n=== {tag} (image-only) ===")
        print(f"base_gross={base*100:.4f}%  base_net={(base-ROUND_TRIP_COST)*100:.4f}%")
        print(f"sel(top{args.top_pct:.0%}) n={k}  sel_gross={sel*100:.4f}%  "
              f"sel_net={(sel-ROUND_TRIP_COST)*100:.4f}%")
        print(f"LIFT = sel_gross - base_gross = {lift*100:.4f}%p")
        print(f"IC(raw)={ic:.4f}  IC(daily-demeaned)={ic_dm:.4f}")
        print(f"safeguard sel_net>0 : {'PASS' if sel>ROUND_TRIP_COST else 'FAIL'}  "
              f"lift>0 : {'PASS' if lift>0 else 'FAIL'}")

    _report("TEST fold", prob_te, te_mask)
    _report("TRAIN fold (fit sanity)", prob_tr, tr_mask)


if __name__ == "__main__":
    main()
