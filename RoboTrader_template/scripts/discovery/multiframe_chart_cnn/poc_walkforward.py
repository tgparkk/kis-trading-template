# scripts/discovery/multiframe_chart_cnn/poc_walkforward.py
"""강화 PoC: 확장창 다폴드 워크포워드로 이미지 CNN 선별의 베타초과 lift 판정.

사전등록 게이트(.superpowers/sdd/plan2-preregistration.md, 커밋 8e57d54):
각 테스트 폴드에서 lift = sel_gross(상위 top-pct) - base_gross(전체).
판정: lift>0 폴드 과반 AND 합산(거래가중) lift>+0.10%p AND 합산 sel_net 절대>0.

1폴드 PoC가 국면전환 하나에 휘둘린 문제를 다폴드로 해소한다. CUDA 사용
(연구 venv D:/tmp/venv-cnn). 이미지 전용(스칼라 미포함) — 핵심 가설 우선 검증.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROUND_TRIP_COST = 0.0021
CACHE_DIR = Path(__file__).parent / "_cache"
OUTCOMES = ["tp", "sl", "timeout"]


def _spearman(a, b) -> float:
    ra = pd.Series(a).rank().to_numpy(); rb = pd.Series(b).rank().to_numpy()
    ra = ra - ra.mean(); rb = rb - rb.mean()
    den = np.sqrt((ra*ra).sum() * (rb*rb).sum())
    return float((ra*rb).sum()/den) if den > 0 else 0.0


def _daily_ic(score, ret, dates) -> float:
    df = pd.DataFrame({"s": score, "r": ret, "d": dates})
    df["rdm"] = df["r"] - df.groupby("d")["r"].transform("mean")
    return _spearman(df["s"].to_numpy(), df["rdm"].to_numpy())


def build_model(in_ch=6):
    import torch.nn as nn
    return nn.Sequential(
        nn.Conv2d(in_ch, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d(2),
        nn.Conv2d(16, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d(2),
        nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(), nn.MaxPool2d(2),
        nn.AdaptiveAvgPool2d(1), nn.Flatten(),
        nn.Linear(64, 64), nn.ReLU(), nn.Dropout(0.4),
        nn.Linear(64, 3),
    )


def make_folds(dates, n_folds):
    u = np.array(sorted(pd.unique(dates)))
    return [g for g in np.array_split(u, n_folds)]


def train_one(Xtr, ytr, w, epochs, batch, lr, device, seed):
    import torch, torch.nn as nn
    torch.manual_seed(seed)
    model = build_model(Xtr.shape[1]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    lossf = nn.CrossEntropyLoss(weight=w.to(device))
    n = len(Xtr)
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(n)
        for i in range(0, n, batch):
            idx = perm[i:i+batch]
            opt.zero_grad()
            out = model(Xtr[idx].to(device))
            loss = lossf(out, ytr[idx].to(device))
            loss.backward(); opt.step()
    return model


def scores_of(model, X, batch, device):
    import torch
    model.eval()
    outs = []
    with torch.no_grad():
        for i in range(0, len(X), batch):
            p = torch.softmax(model(X[i:i+batch].to(device)), dim=1)
            outs.append(p.cpu().numpy())
    p = np.concatenate(outs)
    return p[:, 0] - p[:, 1]     # P(tp) - P(sl)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(CACHE_DIR))
    ap.add_argument("--n-folds", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--top-pct", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    np.random.seed(args.seed); torch.manual_seed(args.seed)

    d = Path(args.data_dir)
    images = np.load(d / "images.npy")
    meta = pd.read_parquet(d / "meta.parquet")
    y = meta["outcome"].map({o: i for i, o in enumerate(OUTCOMES)}).to_numpy()
    ret = meta["realized_ret"].to_numpy(dtype=np.float64)
    dates = meta["trade_date"].to_numpy()
    print(f"device={device} n={len(images)} folds={args.n_folds} "
          f"dist={ (y==0).mean():.3f}/{(y==1).mean():.3f}/{(y==2).mean():.3f}", flush=True)

    folds = make_folds(dates, args.n_folds)
    rows = []
    for k in range(1, args.n_folds):
        tr_days = np.concatenate(folds[:k]); te_days = folds[k]
        tr = np.isin(dates, tr_days); te = np.isin(dates, te_days)
        Xtr = torch.from_numpy(images[tr].astype(np.float32)/255.0)
        ytr = torch.from_numpy(y[tr]).long()
        Xte = torch.from_numpy(images[te].astype(np.float32)/255.0)

        cnts = np.bincount(y[tr], minlength=3).astype(np.float64)
        w = torch.from_numpy((cnts.sum()/(3*np.maximum(cnts, 1))).astype(np.float32))
        model = train_one(Xtr, ytr, w, args.epochs, args.batch, args.lr, device, args.seed)
        score = scores_of(model, Xte, args.batch, device)

        r = ret[te]; dts = dates[te]
        base = float(r.mean())
        kk = max(1, int(len(score)*args.top_pct))
        top = np.argsort(-score)[:kk]
        sel = float(r[top].mean())
        ic = _daily_ic(score, r, dts)
        rows.append({
            "fold": k, "test_from": str(te_days[0]), "test_to": str(te_days[-1]),
            "n_test": int(te.sum()), "n_sel": kk,
            "base_gross_pct": round(base*100, 4), "sel_gross_pct": round(sel*100, 4),
            "lift_pp": round((sel-base)*100, 4),
            "sel_net_pct": round((sel-ROUND_TRIP_COST)*100, 4),
            "ic_dm": round(ic, 4),
        })
        print(f"fold {k}: test {te_days[0]}..{te_days[-1]} base={base*100:.3f}% "
              f"sel={sel*100:.3f}% lift={(sel-base)*100:+.4f}pp ic_dm={ic:+.4f}", flush=True)

    df = pd.DataFrame(rows)
    print("\n" + df.to_string(index=False))

    n_pos = int((df["lift_pp"] > 0).sum()); n_eval = len(df)
    wsum = df["n_sel"].sum()
    pooled_lift = float((df["lift_pp"]*df["n_sel"]).sum()/wsum)
    pooled_sel_net = float((df["sel_net_pct"]*df["n_sel"]).sum()/wsum)
    g1 = n_pos > n_eval/2; g2 = pooled_lift > 0.10; g3 = pooled_sel_net > 0
    print("\n=== GATE (prereg 8e57d54) ===")
    print(f"lift>0 folds: {n_pos}/{n_eval} -> {'PASS' if g1 else 'FAIL'} (need majority)")
    print(f"pooled lift : {pooled_lift:+.4f}pp -> {'PASS' if g2 else 'FAIL'} (need >+0.10)")
    print(f"pooled sel_net: {pooled_sel_net:+.4f}% -> {'PASS' if g3 else 'FAIL'} (need >0)")
    print(f"VERDICT: {'PASS -> proceed to full build' if (g1 and g2 and g3) else 'FAIL -> stop before 28GB build'}")
    df.to_csv(d / "poc_walkforward_result.csv", index=False)


if __name__ == "__main__":
    main()
