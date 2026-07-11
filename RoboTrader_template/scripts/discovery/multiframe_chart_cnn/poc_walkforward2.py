# scripts/discovery/multiframe_chart_cnn/poc_walkforward2.py
"""등록 스펙 워크포워드: 이미지(6ch)+변동성 스칼라(2) 2입력 CNN, 폴드별 TP/SL.

poc_walkforward.py(이미지 전용, 고정 3x3)의 구조를 확장한다. 사전등록
(.superpowers/sdd/plan2-preregistration.md) 스펙:
  - 입력 = 6채널 이미지 + 표준화된 변동성 스칼라 2개(마지막 FC 직전 concat).
  - TP/SL 은 폴드 학습창 내부에서만 {3x3, 3x5} 중 선택(테스트 누출 없음):
    학습창의 마지막 ~20% 거래일을 내부검증(val')으로 떼어 두 옵션을 학습·평가,
    val' lift 최대 옵션을 고른 뒤 학습창 전체로 재학습해 테스트 폴드에서 1회 평가.
  - 스칼라 표준화 통계(mean/std)는 학습창에서만 계산해 학습·테스트에 적용.

게이트(고정 임계, 변경 금지): lift>0 폴드 과반 AND 합산(거래가중) lift>+0.10%p
AND 합산 sel_net 절대>0. lift = sel_gross(top-pct) - base_gross(전체).

이미지 캐시(28GB)는 mmap 으로 열고 폴드 슬라이스만 float32 로 복사한다.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROUND_TRIP_COST = 0.0021
CACHE_DIR = Path(__file__).parent / "_cache"
OUTCOMES = ["tp", "sl", "timeout"]
GRID_LABELS = ["3x3", "3x5"]


def _spearman(a, b) -> float:
    ra = pd.Series(a).rank().to_numpy(); rb = pd.Series(b).rank().to_numpy()
    ra = ra - ra.mean(); rb = rb - rb.mean()
    den = np.sqrt((ra * ra).sum() * (rb * rb).sum())
    return float((ra * rb).sum() / den) if den > 0 else 0.0


def _daily_ic(score, ret, dates) -> float:
    df = pd.DataFrame({"s": score, "r": ret, "d": dates})
    df["rdm"] = df["r"] - df.groupby("d")["r"].transform("mean")
    return _spearman(df["s"].to_numpy(), df["rdm"].to_numpy())


def build_model2(in_ch=6, n_scalar=2):
    """이미지 특징(64d) + 표준화 스칼라(n_scalar)를 concat 후 분류하는 2입력 CNN.

    conv 스택은 poc_walkforward.build_model 과 동일(Flatten→64d)하되, 최종
    분류기 직전에서 스칼라를 결합한다.
    """
    import torch
    import torch.nn as nn

    class TwoInputCNN(nn.Module):
        def __init__(self, in_ch: int, n_scalar: int):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv2d(in_ch, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(16, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(), nn.MaxPool2d(2),
                nn.AdaptiveAvgPool2d(1), nn.Flatten(),
            )
            self.head = nn.Sequential(
                nn.Linear(64 + n_scalar, 64), nn.ReLU(), nn.Dropout(0.4),
                nn.Linear(64, 3),
            )

        def forward(self, x_img, x_scal):
            feat = self.conv(x_img)
            return self.head(torch.cat([feat, x_scal], dim=1))

    return TwoInputCNN(in_ch, n_scalar)


def make_folds(dates, n_folds):
    u = np.array(sorted(pd.unique(dates)))
    return [g for g in np.array_split(u, n_folds)]


def standardize(train_scal, *others):
    """학습창 스칼라 통계로 표준화(std>0 가드). 학습·검증·테스트 동일 통계 적용."""
    mean = train_scal.mean(axis=0)
    std = train_scal.std(axis=0)
    std = np.where(std > 0, std, 1.0)
    out = [((train_scal - mean) / std).astype(np.float32)]
    for x in others:
        out.append(((x - mean) / std).astype(np.float32))
    return out


def train_one(Ximg, Xscal, y, w, epochs, batch, lr, device, seed):
    import torch
    import torch.nn as nn
    torch.manual_seed(seed)
    model = build_model2(Ximg.shape[1], Xscal.shape[1]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    lossf = nn.CrossEntropyLoss(weight=w.to(device))
    n = len(Ximg)
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(n)
        for i in range(0, n, batch):
            idx = perm[i:i + batch]
            opt.zero_grad()
            out = model(Ximg[idx].to(device).float().div_(255.0), Xscal[idx].to(device))
            loss = lossf(out, y[idx].to(device))
            loss.backward(); opt.step()
    return model


def scores_of(model, Ximg, Xscal, batch, device):
    import torch
    model.eval()
    outs = []
    with torch.no_grad():
        for i in range(0, len(Ximg), batch):
            p = torch.softmax(model(Ximg[i:i + batch].to(device).float().div_(255.0),
                                    Xscal[i:i + batch].to(device)), dim=1)
            outs.append(p.cpu().numpy())
    p = np.concatenate(outs)
    return p[:, 0] - p[:, 1]     # P(tp) - P(sl)


def _class_weights(y, device):
    import torch
    cnts = np.bincount(y, minlength=3).astype(np.float64)
    return torch.from_numpy((cnts.sum() / (3 * np.maximum(cnts, 1))).astype(np.float32))


def _lift(score, realized, top_pct):
    base = float(realized.mean())
    kk = max(1, int(len(score) * top_pct))
    top = np.argsort(-score)[:kk]
    sel = float(realized[top].mean())
    return sel - base, base, sel, kk


def _map_y(meta, lab):
    m = {o: i for i, o in enumerate(OUTCOMES)}
    return meta[f"outcome_{lab}"].map(m).to_numpy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(CACHE_DIR))
    ap.add_argument("--n-folds", type=int, default=8)
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--top-pct", type=float, default=0.2)
    ap.add_argument("--val-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    np.random.seed(args.seed); torch.manual_seed(args.seed)

    d = Path(args.data_dir)
    images = np.load(d / "images.npy", mmap_mode="r")   # (N,6,64,64) uint8, 미실체화
    scalars = np.load(d / "scalars.npy")                # (N,2) float32
    meta = pd.read_parquet(d / "meta.parquet")
    labels = pd.read_parquet(d / "labels_grid.parquet")
    dates = meta["trade_date"].to_numpy()
    assert len(images) == len(scalars) == len(meta) == len(labels), "행 수 불일치"

    ymap = {lab: _map_y(labels, lab) for lab in GRID_LABELS}
    rmap = {lab: labels[f"realized_{lab}"].to_numpy(dtype=np.float64) for lab in GRID_LABELS}
    print(f"device={device} n={len(images)} folds={args.n_folds} "
          f"scalars={scalars.shape}", flush=True)

    def load_imgs(mask):
        # uint8 유지(호스트 RAM 절약): float/255 변환은 GPU에서 배치마다 수행.
        return torch.from_numpy(np.ascontiguousarray(images[mask]))

    folds = make_folds(dates, args.n_folds)
    rows = []
    for k in range(1, args.n_folds):
        tr_days = np.concatenate(folds[:k]); te_days = folds[k]
        tr = np.isin(dates, tr_days); te = np.isin(dates, te_days)

        # 학습창 내부 val' 분할: 마지막 val_frac 거래일(테스트 누출 없음).
        tr_days_sorted = np.array(sorted(pd.unique(dates[tr])))
        vcut = max(1, int(round(len(tr_days_sorted) * args.val_frac)))
        vcut = min(vcut, len(tr_days_sorted) - 1)   # trp' 최소 1일 확보
        val_days = tr_days_sorted[-vcut:]; trp_days = tr_days_sorted[:-vcut]
        trp = np.isin(dates, trp_days); valp = np.isin(dates, val_days)

        Ximg_trp = load_imgs(trp); Ximg_val = load_imgs(valp)
        scal_trp_s, scal_val_s = standardize(scalars[trp], scalars[valp])
        Xs_trp = torch.from_numpy(scal_trp_s); Xs_val = torch.from_numpy(scal_val_s)

        # 각 (tp,sl) 옵션을 trp' 로 학습 → val' lift 로 선택.
        val_lifts = {}
        for lab in GRID_LABELS:
            ytrp = torch.from_numpy(ymap[lab][trp]).long()
            w = _class_weights(ymap[lab][trp], device)
            m = train_one(Ximg_trp, Xs_trp, ytrp, w, args.epochs, args.batch,
                          args.lr, device, args.seed)
            sc = scores_of(m, Ximg_val, Xs_val, args.batch, device)
            lift_v, _, _, _ = _lift(sc, rmap[lab][valp], args.top_pct)
            val_lifts[lab] = lift_v
            print(f"  fold {k} sel-eval {lab}: val_lift={lift_v*100:+.4f}pp", flush=True)
        del Ximg_trp, Ximg_val
        chosen = max(GRID_LABELS, key=lambda L: val_lifts[L])

        # 선택된 (tp,sl) 로 학습창 전체 재학습 → 테스트 폴드 1회 평가.
        Ximg_tr = load_imgs(tr); Ximg_te = load_imgs(te)
        scal_tr_s, scal_te_s = standardize(scalars[tr], scalars[te])
        Xs_tr = torch.from_numpy(scal_tr_s); Xs_te = torch.from_numpy(scal_te_s)
        ytr = torch.from_numpy(ymap[chosen][tr]).long()
        w = _class_weights(ymap[chosen][tr], device)
        model = train_one(Ximg_tr, Xs_tr, ytr, w, args.epochs, args.batch,
                          args.lr, device, args.seed)
        score = scores_of(model, Ximg_te, Xs_te, args.batch, device)
        del Ximg_tr, Ximg_te

        r = rmap[chosen][te]; dts = dates[te]
        lift, base, sel, kk = _lift(score, r, args.top_pct)
        ic = _daily_ic(score, r, dts)
        rows.append({
            "fold": k, "test_from": str(te_days[0]), "test_to": str(te_days[-1]),
            "chosen_tpsl": chosen, "n_test": int(te.sum()), "n_sel": kk,
            "base_gross_pct": round(base * 100, 4), "sel_gross_pct": round(sel * 100, 4),
            "lift_pp": round(lift * 100, 4),
            "sel_net_pct": round((sel - ROUND_TRIP_COST) * 100, 4),
            "ic_dm": round(ic, 4),
        })
        print(f"fold {k}: test {te_days[0]}..{te_days[-1]} chosen={chosen} "
              f"base={base*100:.3f}% sel={sel*100:.3f}% lift={lift*100:+.4f}pp "
              f"ic_dm={ic:+.4f}", flush=True)

    df = pd.DataFrame(rows)
    print("\n" + df.to_string(index=False))

    n_pos = int((df["lift_pp"] > 0).sum()); n_eval = len(df)
    wsum = df["n_sel"].sum()
    pooled_lift = float((df["lift_pp"] * df["n_sel"]).sum() / wsum)
    pooled_sel_net = float((df["sel_net_pct"] * df["n_sel"]).sum() / wsum)
    # g1: ≥5/7 (prereg 2026-07-12 해석확정, 엄격)
    g1 = n_pos / n_eval >= 5 / 7; g2 = pooled_lift > 0.10; g3 = pooled_sel_net > 0
    print("\n=== GATE (prereg) ===")
    print(f"lift>0 folds: {n_pos}/{n_eval} -> {'PASS' if g1 else 'FAIL'} (need >=5/7)")
    print(f"pooled lift : {pooled_lift:+.4f}pp -> {'PASS' if g2 else 'FAIL'} (need >+0.10)")
    print(f"pooled sel_net: {pooled_sel_net:+.4f}% -> {'PASS' if g3 else 'FAIL'} (need >0)")
    print(f"VERDICT: {'PASS' if (g1 and g2 and g3) else 'FAIL'}")
    df.to_csv(d / "poc_wf2_result.csv", index=False)


if __name__ == "__main__":
    main()
