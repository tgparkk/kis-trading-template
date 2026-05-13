# RoboTrader_template/scripts/run_bb_reversion_3stage.ps1
# bb_reversion 3단계 심화 멀티버스 — spec-2026-05-13-bb-reversion-3stage-multiverse 참조
# 각 Stage: 별도 python 프로세스 (메모리 회수)

param(
    [string]$Date = $(Get-Date -Format "yyyy-MM-dd"),
    [int]$NJobs = 16,
    [switch]$SkipStage1,
    [switch]$SkipStage2,
    [switch]$SkipStage3
)

$ErrorActionPreference = "Continue"
$env:PYTHONPATH = "D:\GIT\kis-trading-template;D:\GIT\kis-trading-template\RoboTrader_template"
$env:PYTHONUTF8 = "1"

$ROOT = "D:\GIT\kis-trading-template"
$OUT  = "$ROOT\RoboTrader_template\output\multiverse_bb_reversion_$Date"
$LOG  = "$OUT\pipeline.log"

New-Item -ItemType Directory -Force -Path $OUT | Out-Null

function Log-Stamp($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$ts] $msg" | Out-File -FilePath $LOG -Encoding utf8 -Append
    Write-Host "[$ts] $msg"
}

Log-Stamp "=== bb_reversion 3-stage pipeline 시작 (n_jobs=$NJobs) ==="

# KOSPI200 PIT 종목 코드 평면화 (Stage 1 시작일 기준)
Log-Stamp "KOSPI200 PIT universe 로드 (기준일 2024-01-01)"
$codes = python -c "import sys; sys.path.insert(0,'$ROOT'); sys.path.insert(0,'$ROOT/RoboTrader_template'); from datetime import date; from RoboTrader_template.multiverse.data.kospi200_pit import get_kospi200_pit; print(','.join(get_kospi200_pit(date(2024,1,1))))"
if ([string]::IsNullOrWhiteSpace($codes)) {
    Log-Stamp "ERROR: KOSPI200 PIT 종목 0건 — 중단"
    exit 1
}
$codeCount = ($codes -split ",").Count
Log-Stamp "universe size: $codeCount 종목"

# ---------- Stage 1 ----------
if (-not $SkipStage1) {
    $S1_OUT = "$OUT\stage1"
    New-Item -ItemType Directory -Force -Path $S1_OUT | Out-Null
    Log-Stamp ">>> Stage 1: 5,832셀 × IS 2024 × n_jobs=$NJobs"
    $s1Start = Get-Date

    python -m RoboTrader_template.runners.param_optimizer `
        --strategies bb_reversion `
        --stock-codes $codes `
        --screener-grid --max-combinations 6000 `
        --start 2024-01-01 --end 2024-12-31 `
        --mode plain --n-jobs $NJobs `
        --min-trades 5 --top-n 50 `
        2>&1 | Tee-Object -FilePath "$S1_OUT\stage1.log"

    $s1Elapsed = (Get-Date) - $s1Start
    Log-Stamp "<<< Stage 1 완료 (elapsed=$([math]::Round($s1Elapsed.TotalMinutes,1))분)"

    # param_optimizer 출력 디렉토리 → S1_OUT으로 정렬
    Move-Item "$ROOT\RoboTrader_template\output\param_optimizer_bb_reversion_*.md" $S1_OUT -ErrorAction SilentlyContinue
    if (Test-Path "$ROOT\RoboTrader_template\output\param_optimizer_bb_reversion_*.parquet") {
        Move-Item "$ROOT\RoboTrader_template\output\param_optimizer_bb_reversion_*.parquet" "$S1_OUT\results.parquet" -ErrorAction SilentlyContinue
    }

    # stage1_analyze.py로 report.md 보강
    if (Test-Path "$S1_OUT\results.parquet") {
        python -m RoboTrader_template.scripts.stage1_analyze `
            --results "$S1_OUT\results.parquet" `
            --output "$S1_OUT\report.md"
        Log-Stamp "stage1_analyze report.md 생성 완료"
    } else {
        Log-Stamp "WARN: results.parquet 없음 — stage1_analyze 건너뜀"
    }

    [System.GC]::Collect()
    Start-Sleep -Seconds 5
}

# ---------- Stage 2 ----------
if (-not $SkipStage2) {
    $S2_OUT = "$OUT\stage2"
    New-Item -ItemType Directory -Force -Path $S2_OUT | Out-Null
    Log-Stamp ">>> Stage 2: 인접격자 ≤ 2000셀 × IS 2022~2024"

    # Stage 1 top50 → 인접격자 yaml 생성
    python -c "
import sys, pandas as pd, yaml
sys.path.insert(0,'$ROOT'); sys.path.insert(0,'$ROOT/RoboTrader_template')
from RoboTrader_template.runners._adjacent_grid import build_adjacent_grid, export_grid_yaml
top = pd.read_parquet('$OUT/stage1/results.parquet')
top = top[(top['total_trades'] >= 5) & (top['calmar'] >= 0.5)].nlargest(50, 'calmar')
print(f'top50 rows: {len(top)}')
original = yaml.safe_load(open('$ROOT/RoboTrader_template/strategies/bb_reversion/multiverse_grid.yaml', encoding='utf-8'))
grid, info = build_adjacent_grid(top, original, max_cells=2000, sample_n=4)
print(f'adjacent grid cells: {info[""cell_count""]}, frozen: {info[""frozen_axes""]}')
export_grid_yaml(grid, '$S2_OUT/grid_seed.yaml')
import json
open('$S2_OUT/grid_seed_info.json','w',encoding='utf-8').write(json.dumps(info, ensure_ascii=False, indent=2))
" 2>&1 | Tee-Object -FilePath "$S2_OUT\adjacent_grid.log"

    if (-not (Test-Path "$S2_OUT\grid_seed.yaml")) {
        Log-Stamp "ERROR: Stage 2 grid_seed.yaml 생성 실패 — 중단"
        exit 2
    }

    # multiverse_grid.yaml 교체 (Stage 2 실행 동안만)
    $bbGridPath = "$ROOT\RoboTrader_template\strategies\bb_reversion\multiverse_grid.yaml"
    Copy-Item $bbGridPath "$S2_OUT\multiverse_grid_original.yaml.bak"
    Copy-Item "$S2_OUT\grid_seed.yaml" $bbGridPath -Force

    $s2Start = Get-Date
    python -m RoboTrader_template.runners.param_optimizer `
        --strategies bb_reversion `
        --stock-codes $codes `
        --screener-grid --max-combinations 2200 `
        --start 2022-01-01 --end 2024-12-31 `
        --mode plain --n-jobs $NJobs `
        --min-trades 30 --top-n 10 `
        2>&1 | Tee-Object -FilePath "$S2_OUT\stage2.log"

    # 그리드 yaml 원복
    Copy-Item "$S2_OUT\multiverse_grid_original.yaml.bak" $bbGridPath -Force
    Remove-Item "$S2_OUT\multiverse_grid_original.yaml.bak"

    $s2Elapsed = (Get-Date) - $s2Start
    Log-Stamp "<<< Stage 2 완료 (elapsed=$([math]::Round($s2Elapsed.TotalMinutes,1))분)"

    Move-Item "$ROOT\RoboTrader_template\output\param_optimizer_bb_reversion_*.md" $S2_OUT -ErrorAction SilentlyContinue
    if (Test-Path "$ROOT\RoboTrader_template\output\param_optimizer_bb_reversion_*.parquet") {
        Move-Item "$ROOT\RoboTrader_template\output\param_optimizer_bb_reversion_*.parquet" "$S2_OUT\results.parquet" -ErrorAction SilentlyContinue
    }

    [System.GC]::Collect()
    Start-Sleep -Seconds 5
}

# ---------- Stage 3 ----------
if (-not $SkipStage3) {
    $S3_OUT = "$OUT\stage3"
    New-Item -ItemType Directory -Force -Path $S3_OUT | Out-Null
    Log-Stamp ">>> Stage 3: Top 10 × 5y walkforward(252/63 ×6)"

    # Stage 2 top10 → Stage 3용 그리드 yaml (단일값만)
    python -c "
import sys, pandas as pd, yaml
sys.path.insert(0,'$ROOT'); sys.path.insert(0,'$ROOT/RoboTrader_template')
top = pd.read_parquet('$OUT/stage2/results.parquet')
top = top[(top['total_trades'] >= 30) & (top['calmar'] >= 1.0)].nlargest(10, 'calmar')
# 각 행이 한 셀 → grid을 행별 단일값 리스트로 빌드는 비효율
# 대신 stage3에서는 행별 직접 백테스트 호출하거나, top10의 각 파라미터 값 union을 grid로 → 100셀까지
grid = {}
for col in top.columns:
    if col.startswith(('parameters.', 'risk_management.', 'screening.')):
        grid[col] = sorted(top[col].dropna().unique().tolist())
import yaml
open('$S3_OUT/grid_seed.yaml','w',encoding='utf-8').write(yaml.safe_dump(grid, allow_unicode=True, sort_keys=False))
print(f'stage3 grid cells (union): {1 if not grid else __import__(""functools"").reduce(lambda a,b: a*b, [len(v) for v in grid.values()])}')
"

    $bbGridPath = "$ROOT\RoboTrader_template\strategies\bb_reversion\multiverse_grid.yaml"
    Copy-Item $bbGridPath "$S3_OUT\multiverse_grid_original.yaml.bak"
    Copy-Item "$S3_OUT\grid_seed.yaml" $bbGridPath -Force

    $s3Start = Get-Date
    python -m RoboTrader_template.runners.param_optimizer `
        --strategies bb_reversion `
        --stock-codes $codes `
        --screener-grid --max-combinations 500 `
        --start 2021-01-01 --end 2026-04-30 `
        --mode walkforward `
        --is-window 252 --oos-window 63 --n-windows 6 `
        --n-jobs $NJobs `
        --min-trades 30 --top-n 10 `
        2>&1 | Tee-Object -FilePath "$S3_OUT\stage3.log"

    Copy-Item "$S3_OUT\multiverse_grid_original.yaml.bak" $bbGridPath -Force
    Remove-Item "$S3_OUT\multiverse_grid_original.yaml.bak"

    $s3Elapsed = (Get-Date) - $s3Start
    Log-Stamp "<<< Stage 3 완료 (elapsed=$([math]::Round($s3Elapsed.TotalMinutes,1))분)"

    Move-Item "$ROOT\RoboTrader_template\output\param_optimizer_bb_reversion_*.md" $S3_OUT -ErrorAction SilentlyContinue
    if (Test-Path "$ROOT\RoboTrader_template\output\param_optimizer_bb_reversion_*.parquet") {
        Move-Item "$ROOT\RoboTrader_template\output\param_optimizer_bb_reversion_*.parquet" "$S3_OUT\walkforward.parquet" -ErrorAction SilentlyContinue
    }

    # 최종 후보 추출 (wf_pass 컬럼 있을 시 필터)
    python -c "
import pandas as pd
df = pd.read_parquet('$S3_OUT/walkforward.parquet')
if 'wf_pass' in df.columns:
    df = df[df['wf_pass'] == True]
df = df[df['total_trades'] >= 30].nlargest(3, 'calmar')
df.to_parquet('$S3_OUT/final_candidates.parquet')
print(f'final candidates: {len(df)}')
"

    # 라이브 튜닝 권고 생성
    python -m RoboTrader_template.scripts.stage3_recommend `
        --candidates "$S3_OUT\final_candidates.parquet" `
        --current-config "$ROOT\RoboTrader_template\strategies\bb_reversion\config.yaml" `
        --output "$S3_OUT\recommend_diff.md"

    Log-Stamp "stage3_recommend 권고 생성 완료"
}

Log-Stamp "=== bb_reversion 3-stage pipeline 종료 ==="
