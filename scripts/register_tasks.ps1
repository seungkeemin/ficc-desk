# 수집 스케줄 등록. 하루 3회 + 마지막 회차에 백업.
#
#   powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1 -Force   # 시각 변경 시 재등록
#
# 해제는 scripts\unregister_tasks.ps1.
#
# 이미 등록돼 있으면 건너뛴다. 스크립트를 두 번 돌려도 작업이 6개가 되지 않는다.
# 시각을 바꾸거나 저장소를 옮겼으면 -Force 로 덮어쓴다.
#
# 회차 시각의 근거와 3주 뒤 축소 계획은 scripts\scheduled_run.ps1 머리말에 있다.
# 주말·공휴일에도 그대로 돈다 (ScheduleByDay, DaysInterval 1).
#
# 백업이 23:30 에 붙는 이유: 하루 마지막 회차의 수집까지 담은 스냅샷이어야
# 그날 하루가 통째로 보존된다. (요청서의 '22:00 회차'는 07:30/16:30/23:30 3회차
# 안에 없어서 하루의 마지막 회차로 붙였다. 22:00 을 별도 회차로 두려면 아래
# $tasks 에 한 줄을 추가하고 23:30 의 Backup 을 $false 로 바꾼다.)
#
# ── /TR 이 아니라 /XML 로 등록하는 이유 ──────────────────────────────────────
# schtasks /Create /TR 로 만든 작업은 DisallowStartIfOnBatteries=TRUE 로 굳어지고
# CLI 로는 이 값을 못 바꾼다. 이 기계는 노트북이라 배터리로 도는 동안 작업이
# 실행되지 않고 'Queued' 상태로 쌓이기만 한다 (2026-08-12 등록 후 실제로 이렇게
# 됐다 — /Run 을 걸어도 100초 동안 프로세스가 뜨지 않았다). 배터리로 쓰는 날은
# 수집이 통째로 비므로 반드시 꺼야 하고, 끄려면 XML 등록뿐이다.
# ScheduledTasks 모듈(Register-ScheduledTask)이 아니라 schtasks 를 쓴다.

[CmdletBinding()]
param(
    # 이미 등록된 작업을 지우고 다시 만든다.
    [switch]$Force
)

$root   = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $root 'scripts\scheduled_run.ps1'

if (-not (Test-Path $runner)) {
    Write-Host "실행 스크립트가 없다: $runner"
    exit 1
}

$tasks = @(
    @{ Name = 'ficc-desk ingest 0730'; Time = '07:30'; Backup = $false },
    @{ Name = 'ficc-desk ingest 1630'; Time = '16:30'; Backup = $false },
    @{ Name = 'ficc-desk ingest 2330'; Time = '23:30'; Backup = $true  }
)

$user = "$env:USERDOMAIN\$env:USERNAME"

function New-TaskXml([hashtable]$task) {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File &quot;$runner&quot;"
    if ($task.Backup) { $arguments += ' -WithBackup' }

    $description = "ficc-desk 수집 $($task.Time)"
    if ($task.Backup) { $description += ' + 백업 (하루 마지막 회차)' }

    # StartBoundary 의 날짜는 '이 시각부터 매일' 의 시작점일 뿐이라 과거 날짜여도 된다.
    # 고정 날짜를 박아 두면 등록한 날에 따라 첫 회차가 달라지는 일이 없다.
    #
    # StartWhenAvailable=false: 컴퓨터가 꺼져 있어 놓친 회차를 나중에 몰아서 돌리지
    #   않는다. 07:30 을 놓쳤으면 그냥 놓친 것이고 16:30 이 정시에 처음부터 다시
    #   한다. 밀린 회차를 뒤늦게 돌리면 '그 시각에 값이 있었나' 를 세는 커버리지
    #   집계가 거짓말이 된다.
    # RestartOnFailure 없음: 재시도하지 않는다 (요청 사항).
    # MultipleInstancesPolicy=IgnoreNew: 앞 회차가 아직 돌고 있으면 새 회차를 버린다.
    #   런처 수집과 겹쳐도 DB 를 두 프로세스가 동시에 두드리지 않는다.
    # ExecutionTimeLimit=PT10M: 실측 12~13초짜리 작업이다. 10분을 넘겼으면 매달린
    #   것이므로 죽인다. 매달린 프로세스가 다음 회차까지 살아남지 않게 한다.
    return @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>$description</Description>
    <URI>\$($task.Name)</URI>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T$($task.Time):00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$user</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <AllowHardTerminate>true</AllowHardTerminate>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>$arguments</Arguments>
      <WorkingDirectory>$root</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@
}

foreach ($task in $tasks) {
    $name = $task.Name

    $null = schtasks /Query /TN $name 2>&1
    $exists = ($LASTEXITCODE -eq 0)

    if ($exists -and -not $Force) {
        Write-Host "건너뜀 (이미 등록됨): $name"
        continue
    }

    # schtasks /XML 은 UTF-16 파일을 기대한다. UTF-8 로 쓰면 한글 설명이 깨진다.
    $xmlPath = Join-Path $env:TEMP ("ficc-task-" + $task.Time.Replace(':', '') + ".xml")
    [IO.File]::WriteAllText($xmlPath, (New-TaskXml $task), [Text.Encoding]::Unicode)

    try {
        if ($Force) {
            schtasks /Create /TN $name /XML $xmlPath /F
        } else {
            schtasks /Create /TN $name /XML $xmlPath
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Host "등록 실패: $name (schtasks exit $LASTEXITCODE)"
            exit $LASTEXITCODE
        }
    } finally {
        Remove-Item $xmlPath -ErrorAction SilentlyContinue
    }
}

Write-Host ''
foreach ($task in $tasks) {
    schtasks /Query /TN $task.Name /FO LIST | Select-String 'TaskName|Next Run Time|Status|다음 실행|상태'
}
