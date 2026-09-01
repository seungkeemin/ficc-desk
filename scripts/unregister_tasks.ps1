# 수집 스케줄 해제. register_tasks.ps1 이 만든 3개를 지운다.
#
#   powershell -ExecutionPolicy Bypass -File scripts\unregister_tasks.ps1
#
# 등록돼 있지 않은 작업은 조용히 넘어간다 — 이 스크립트를 두 번 돌리는 것과
# 한 번 돌리는 것의 결과가 같아야 한다.
#
# 지우는 것은 작업 등록뿐이다. DB·백업 파일에는 손대지 않는다.

$names = @(
    'ficc-desk ingest 0730',
    'ficc-desk ingest 1630',
    'ficc-desk ingest 2330'
)

foreach ($name in $names) {
    $null = schtasks /Query /TN $name 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "없음: $name"
        continue
    }

    schtasks /Delete /TN $name /F
    if ($LASTEXITCODE -ne 0) {
        Write-Host "해제 실패: $name (schtasks exit $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
}
