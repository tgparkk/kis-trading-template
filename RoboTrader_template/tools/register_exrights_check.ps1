# 실전 보유 종목 기업행위 예고 점검 - 월~금 08:40 작업 등록 (08:30 DART 아침 적재 뒤).
# 실행 내용: venv python tools\exrights_morning_check.py --telegram (읽기 전용 · KIS/DART 호출 0)
#   걸리면(종료 코드 3) [TELEGRAM] (instances\daytrading\key.ini) 로 1건. 출력은 logs\exrights_morning_check.log 에 덧붙인다.
# 사용: .\register_exrights_check.ps1 -DryRun   (정의만 출력, 등록 0)
#       .\register_exrights_check.ps1           (등록 - 읽기 전용 점검이라 Enabled 로 등록)
#       .\register_exrights_check.ps1 -Force    (이미 있으면 덮어쓰기)
# 끄기: .\unregister_exrights_check.ps1  (또는 Disable-ScheduledTask -TaskName KisTemplate_ExrightsCheck)
# 형식은 실전 기동 등록 스크립트(D:\tmp\session_real_start\register_real_daytrading.ps1)를 따른다.
param([switch]$DryRun, [switch]$Force)
$ErrorActionPreference = 'Stop'

$TaskName = 'KisTemplate_ExrightsCheck'
$WorkDir  = 'D:\GIT\kis-trading-template\RoboTrader_template'
$User     = "$env:USERDOMAIN\$env:USERNAME"
$Python   = Join-Path $WorkDir 'venv\Scripts\python.exe'
$Script   = Join-Path $WorkDir 'tools\exrights_morning_check.py'

if (-not (Test-Path $Python)) { Write-Host "거부: python 없음 $Python"; exit 2 }
if (-not (Test-Path $Script)) { Write-Host "거부: 스크립트 없음 $Script (main 에 머지 전?)"; exit 2 }

# cmd /c 로 감싸 출력·종료 코드를 남긴다(작업 «마지막 실행 결과» = 0 걸림없음 / 3 걸림 / 2 데이터 오류).
$cmdArgs   = '/c "set PYTHONIOENCODING=utf-8&& venv\Scripts\python.exe tools\exrights_morning_check.py --telegram >> logs\exrights_morning_check.log 2>&1"'
$action    = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $cmdArgs -WorkingDirectory $WorkDir
$trigger   = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 08:40
$settings  = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$settings.StartWhenAvailable = $false
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited

Write-Host "=== 등록할 작업 정의 ==="
Write-Host "작업명        : $TaskName"
Write-Host "사용자        : $User (Interactive / Limited)"
Write-Host "트리거        : 월~금 08:40 (주간) - 08:30 DART 아침 적재 뒤"
Write-Host "실행          : $($action.Execute) $($action.Arguments)"
Write-Host "작업 폴더     : $WorkDir"
Write-Host "다중 실행     : IgnoreNew · 제한 10분 · StartWhenAvailable=$($settings.StartWhenAvailable) (PC 가 꺼져 있던 날은 건너뜀)"
Write-Host "성격          : 읽기 전용(DB SELECT · KIS/DART 호출 0) - 봇 동작과 무관"

$exists = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($exists) { Write-Host "이미 존재: $TaskName (State=$($exists.State))" }

if ($DryRun) { Write-Host "`n[DryRun] 등록·변경 없음."; return }
if ($exists -and -not $Force) { Write-Host "거부: 이미 있습니다. 덮어쓰려면 -Force."; exit 2 }

try {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
        -Description 'kis-template 실전 보유 종목 기업행위 예고 점검 (tools\exrights_morning_check.py --telegram, 읽기 전용) - 2026-10-10 (d)' -Force:$Force | Out-Null
} catch {
    Write-Host "등록 실패: $($_.Exception.Message)"; exit 3
}

$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $t) { Write-Host "등록 확인 실패: 작업 없음"; exit 3 }
Write-Host "`n등록 완료: $TaskName State=$($t.State)"
Write-Host "수동 시험: Start-ScheduledTask -TaskName $TaskName ; 결과는 $WorkDir\logs\exrights_morning_check.log"
