# 5년 144셀 PoC를 1년씩 5분할 직렬 실행
# 각 1년마다 새 python 프로세스 → 메모리 자동 회수
# 5/10 사장님 결재: 32GB로 5년 본 가동 위한 분할 전략

$ErrorActionPreference = "Continue"
$env:PYTHONPATH = "D:\GIT\kis-trading-template;D:\GIT\kis-trading-template\RoboTrader_template"
$env:PYTHONUTF8 = "1"

$jobs = @(
    @{tag="2021"; start="2021-01-12"; end="2021-12-31"},
    @{tag="2022"; start="2022-01-01"; end="2022-12-31"},
    @{tag="2023"; start="2023-01-01"; end="2023-12-31"},
    @{tag="2024"; start="2024-01-01"; end="2024-12-31"},
    @{tag="2025-2026"; start="2025-01-01"; end="2026-04-30"}
)

$masterLog = "D:\GIT\kis-trading-template\RoboTrader_template\logs\multiverse_quant_5y_split_master.log"
"=== 5y split 시작: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File -FilePath $masterLog -Encoding utf8

foreach ($j in $jobs) {
    $outDir = "D:\GIT\kis-trading-template\RoboTrader_template\output\multiverse_quant_split_$($j.tag)"
    $stdout = "D:\GIT\kis-trading-template\RoboTrader_template\logs\multiverse_quant_split_$($j.tag)_stdout.log"
    $stderr = "D:\GIT\kis-trading-template\RoboTrader_template\logs\multiverse_quant_split_$($j.tag)_stderr.log"
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null

    "[$(Get-Date -Format 'HH:mm:ss')] === START $($j.tag): $($j.start) ~ $($j.end) ===" | Out-File -FilePath $masterLog -Encoding utf8 -Append

    $proc = Start-Process -FilePath "python" -ArgumentList "-u", "-m", "RoboTrader_template.scripts.run_multiverse_grid", "--persona", "quant", "--universe", "kospi200_pit", "--start", $j.start, "--end", $j.end, "--mode", "plain", "--n-jobs", "8", "--output", $outDir -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WorkingDirectory "D:\GIT\kis-trading-template" -NoNewWindow -Wait

    "[$(Get-Date -Format 'HH:mm:ss')] === END $($j.tag) exit=$($proc.ExitCode) ===" | Out-File -FilePath $masterLog -Encoding utf8 -Append

    # 메모리 강제 GC + 잠깐 대기 (메모리 회수 시간)
    [System.GC]::Collect()
    Start-Sleep -Seconds 5
}

"=== 5y split 완료: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File -FilePath $masterLog -Encoding utf8 -Append
