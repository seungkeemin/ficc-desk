# 스케줄러가 부르는 수집 1회차. 사람이 직접 부를 일은 없다 (직접 돌릴 때는
# .venv\Scripts\python -m ficc.ingest 를 쓴다).
#
#   powershell -File scripts\scheduled_run.ps1
#   powershell -File scripts\scheduled_run.ps1 -WithBackup
#
# 재시도가 없다. 일부러 없다. 한 회차가 실패하면 그냥 실패한 채로 끝나고 다음
# 회차가 몇 시간 뒤에 새 프로세스로 처음부터 다시 한다. 재시도를 넣으면 소스가
# 죽어 있는 동안 실패가 누적되고, "이 시각에 값이 있었나"를 나중에 세는 일이
# 불가능해진다 (아래 커버리지 메모).
#
# 회차별 결과는 파일이 아니라 DB 에 남는다 — ingest_run(started_at, status) 과
# ingest_result(field_key, status, message). 로그 파일을 따로 두지 않는 이유는
# 판단 근거가 두 군데로 갈리면 안 되기 때문이다. 실행 여부를 확인하려면:
#
#   .venv\Scripts\python -c "import ficc.db as d;c=d.connect();print(*c.execute('SELECT id,started_at,status FROM ingest_run ORDER BY id DESC LIMIT 5'),sep='\n')"
#
# ── 시각 커버리지 메모 (2026-08-12) ────────────────────────────────────────────
# 하루 3회(07:30 / 16:30 / 23:30)는 넉넉하게 잡은 값이다. ECOS·KRX 의 실제 게시
# 시각을 아직 확인하지 못했기 때문에 "언제 올라오든 하루 안에 한 번은 잡힌다"를
# 우선했다. 2026-09-02 (3주 뒤) 에 ingest_result 를 시각별로 집계해서 — 각 필드가
# 몇 시 회차에서 처음 ok 가 되는지 — 회차를 줄인다. 07:30 이 매번 전 영업일 값만
# 가져오고 16:30 이 항상 같은 값을 채운다면 그 회차는 없애도 되는 회차다.
# 주말·공휴일에도 그대로 돈다. 휴장일 판정을 코드가 하지 않는다 — 그날은 소스가
# 새 값을 안 주고 ingest 가 'miss' 로 기록하면 그만이고, 그 'miss' 자체가
# "휴장이었다"는 기록이다.

[CmdletBinding()]
param(
    # 백업까지 함께 돈다. 하루 마지막 회차(23:30)에만 붙인다.
    [switch]$WithBackup
)

$root = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $py)) {
    Write-Host "가상환경이 없다: $py"
    exit 1
}

# 작업 스케줄러는 C:\Windows\System32 에서 프로세스를 띄운다. schtasks 로는 시작
# 디렉터리를 지정할 수 없어(그건 XML 등록에만 있다) 여기서 직접 옮긴다. 이게 없으면
# python -m ficc.ingest 가 "No module named 'ficc'" 로 죽는다 — 손으로 돌릴 때는
# 항상 저장소 루트에 있어서 드러나지 않는 실패다.
Set-Location $root

# $ErrorActionPreference 를 Stop 으로 두지 않는다. ingest 가 죽어도 백업은 돌아야
# 한다 — 백업이 지키는 것은 오늘 수집분이 아니라 지금까지 쌓인 시계열 전체다.
& $py -m ficc.ingest
$ingestExit = $LASTEXITCODE

$backupExit = 0
if ($WithBackup) {
    & $py (Join-Path $root 'scripts\backup.py')
    $backupExit = $LASTEXITCODE
}

# 작업 스케줄러의 '마지막 실행 결과' 에 남는 값이다. 0 이 아니면 그 회차가
# 무언가 실패했다는 뜻이고, 무엇이 실패했는지는 DB 를 본다.
if ($ingestExit -ne 0) { exit $ingestExit }
exit $backupExit
