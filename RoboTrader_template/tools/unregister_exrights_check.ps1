# 실전 보유 종목 기업행위 예고 점검 작업(KisTemplate_ExrightsCheck) 삭제.
# 사용: .\unregister_exrights_check.ps1 [-DryRun]
# 스크립트 없이: Unregister-ScheduledTask -TaskName KisTemplate_ExrightsCheck -Confirm:$false
#   (잠시 끄기만: Disable-ScheduledTask -TaskName KisTemplate_ExrightsCheck)
param([switch]$DryRun)
$TaskName = 'KisTemplate_ExrightsCheck'
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $t) { Write-Host "작업 $TaskName 없음 - 할 일 없음."; exit 0 }
Write-Host "현재 State=$($t.State)"
if ($DryRun) { Write-Host "[DryRun] 삭제 안 함."; return }
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
} catch {
    Write-Host "Unregister 실패: $($_.Exception.Message) - schtasks 로 재시도"
    & schtasks.exe /Delete /TN $TaskName /F 2>&1 | Out-Null
}
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { Write-Host "경고: 작업이 아직 있습니다!"; exit 1 }
Write-Host "삭제 완료: $TaskName"
