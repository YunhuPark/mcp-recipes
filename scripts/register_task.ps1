# 매일 정해진 시각에 오늘 날짜의 '검수완료' 글을 올리는 작업 스케줄러 항목을 등록한다.
# **사용자가 직접 실행한다.** (PC 설정을 바꾸는 일이라 Claude는 실행하지 않는다)
#
# 사용:
#   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -DryRun            # 무엇을 등록할지 보기만 (아무것도 바꾸지 않음)
#   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Time 12:00        # 등록 (매일 12:00)
#   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Remove            # 등록 취소
#
# 이 작업이 하는 일: 저장소 폴더에서 `post.py --scheduled --publish --topic "AI Threads"` 를 실행한다.
#   - 오늘 날짜의 '검수완료' 글만 올리고, 없으면 아무것도 하지 않는다.
#   - 하루 1개, 같은 글 두 번 금지, 불확실하면 자동 재시도 금지 등 post.py 의 안전 장치가 그대로 적용된다.
#   - 올리기 직전에 check.py 가 돌아 근거 인용이 사라졌거나 본문이 바뀐 글은 올리지 않는다.
#   - THREADS_LIVE=yes 는 이 작업의 실행 명령 안에서만 설정한다 (평소 환경에는 두지 않는다).
#   - 토큰은 사용자 환경 변수에서 읽는다 (작업 설정에 적지 않는다). 로그인한 상태에서만 실행되도록 등록한다.
#   - 결과는 저장소 폴더의 .post-scheduler.log 에 덧붙인다 (저장소에 올라가지 않는다).
param(
    [string]$Time = "12:00",
    [string]$TaskName = "mcp-recipes-daily-post",
    [switch]$DryRun,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ($Remove) {
    if ($DryRun) { Write-Host "[드라이런] 작업 '$TaskName' 을 지웁니다 (실제로는 지우지 않음)"; exit 0 }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "작업 '$TaskName' 을 지웠습니다."
    exit 0
}

if ($Time -notmatch '^([01]\d|2[0-3]):[0-5]\d$') { throw "-Time 은 HH:MM 형식이어야 합니다 (예: 12:00)" }

$python = (Get-Command python -ErrorAction Stop).Source
$inner = "Set-Location '$root'; `$env:PYTHONUTF8='1'; `$env:THREADS_LIVE='yes'; " +
         "& '$python' scripts\post.py --scheduled --publish --topic 'AI Threads' *>> '.post-scheduler.log'"
$arg = "-NoProfile -ExecutionPolicy Bypass -Command `"$inner`""

Write-Host "작업 이름 : $TaskName"
Write-Host "실행 시각 : 매일 $Time"
Write-Host "실행 폴더 : $root"
Write-Host "실행 명령 : powershell.exe $arg"
Write-Host "설정      : 로그인한 상태에서만 실행, 놓친 실행은 켜진 뒤에 한 번만(오늘 날짜 글만), 최대 10분, 중복 실행 안 함"

if ($DryRun) { Write-Host "`n[드라이런] 등록하지 않았습니다."; exit 0 }

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "`n등록했습니다. 확인: Get-ScheduledTask -TaskName $TaskName"
Write-Host "바로 시험하려면(오늘 날짜의 검수완료 글이 있으면 실제로 올라갑니다): Start-ScheduledTask -TaskName $TaskName"
