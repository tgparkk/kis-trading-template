# dtflow shadow 작업 2개 등록 — 🔴 사장님 확인 뒤에만 실행. 실행 워크트리 = 동결 커밋 detached.
$py = "D:\GIT\kis-trading-template\RoboTrader_template\venv\Scripts\python.exe"
$wt = "D:\tmp\kis-wt-dtflow-run"
$script = "RoboTrader_template\scripts\dtflow_shadow_recorder.py"
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$pr = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
$t1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 07:52
$a1 = New-ScheduledTaskAction -Execute $py -Argument "$script --record" -WorkingDirectory $wt
Register-ScheduledTask -TaskName "kis-dtflow-shadow-record" -Trigger $t1 -Action $a1 -Settings $set -Principal $pr
$t2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 09:05
$a2 = New-ScheduledTaskAction -Execute $py -Argument "$script --check-snapshot" -WorkingDirectory $wt
Register-ScheduledTask -TaskName "kis-dtflow-shadow-snapshot" -Trigger $t2 -Action $a2 -Settings $set -Principal $pr
