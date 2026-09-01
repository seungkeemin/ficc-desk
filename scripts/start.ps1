# ficc-desk 실행. 바탕화면 아이콘이 start.bat 을 거쳐 이 파일을 부른다.
#
#   1. 서버가 실제로 응답하는지 본다 (포트 점유 여부가 아니다). 떠 있으면 다시 띄우지
#      않으므로 아이콘을 두 번 눌러도 안전하다.
#      단, 리슨조차 안 하고 있으면 소켓을 열지 않고 즉시 '없다' 로 끝낸다.
#   2. 없으면 최소화된 창으로 띄우고 응답할 때까지 기다린다.
#   3. Chrome 앱 모드로 연다 - 탭·주소창을 빼야 세로 940px 예산이 성립한다 (SPEC 4-5a).
#
# 서버를 끄려면 작업표시줄의 'ficc-desk server' 창에서 Ctrl+C.
#
# 로직이 .bat 이 아니라 여기 있는 이유: cmd.exe 는 배치 파일을 바이트 오프셋으로 읽어서,
# chcp 로 코드페이지를 바꾸면 다음 줄을 엉뚱한 위치에서 다시 읽는다. 주석의 한글이
# 쪼개져 명령으로 실행된다 ("'까지' is not recognized..."). cmd 에서 한글을 안전하게
# 담을 방법이 없으므로 start.bat 은 ASCII 껍데기만 남기고 전부 PowerShell 로 옮겼다.

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$port = 8787
# localhost 가 아니라 127.0.0.1 이다. uvicorn 은 IPv4 에만 리슨하는데 Windows 의
# localhost 는 ::1 로 먼저 풀려서, IPv6 을 실패하고 IPv4 로 폴백할 때까지 요청
# 하나가 2초를 통째로 버린다 (127.0.0.1 로 직접 부르면 5ms).
$url  = "http://127.0.0.1:$port/"
$py   = Join-Path $root '.venv\Scripts\python.exe'

# 창이 숨겨져 있어도 실패는 보여야 한다. 콘솔에 찍으면 아무도 못 본다.
function Fail([string]$message) {
    Write-Host $message
    (New-Object -ComObject WScript.Shell).Popup($message, 0, 'ficc-desk', 0x10) | Out-Null
    exit 1
}

# 소켓을 열기 전에 커널의 리슨 목록부터 본다. 닫힌 IPv4 루프백 포트로 connect 하면
# 거절(RST)이 즉시 오지 않고 SYN 이 버려져서 한 번에 2초씩 날아간다. 대기 루프에서
# 이걸 반복하면 서버는 0.8초면 뜨는데 아이콘은 10초 넘게 먹통이다.
function Test-Listening {
    $listeners = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    return [bool]($listeners | Where-Object { $_.Port -eq $port })
}

# 500 도 '떠 있다' 로 친다. 상태 코드를 따지면 오류를 내는 서버 위에 두 번째 서버를
# 띄우려다 포트 충돌로 시간만 버리고 화면은 열리지도 않는다.
#
# 리슨 여부는 빠른 '아니오' 를 위한 예비 검사일 뿐이고, '떠 있다' 는 판정은 여전히
# 실제 응답을 받아야 내린다. 포트만 잡고 응답하지 않는 프로세스에 속지 않는다.
function Test-Server([int]$seconds) {
    $deadline = [datetime]::Now.AddSeconds($seconds)
    while ($true) {
        if (Test-Listening) {
            try {
                $request = [net.webrequest]::Create($url)
                $request.Timeout = 2000
                $request.Proxy = $null   # 로컬이다. 프록시 자동감지를 시키지 않는다
                $request.GetResponse().Close()
                return $true
            } catch {
                if ($_.Exception.Response) { return $true }
            }
        }
        if ([datetime]::Now -ge $deadline) { return $false }
        Start-Sleep -Milliseconds 100
    }
}

if (-not (Test-Path $py)) {
    Fail @"
가상환경을 찾지 못했다.

  $py

만드는 법:
  cd $root
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
"@
}

# 이미 떠 있는지는 이제 한 번에 판정된다. 재시도 여유를 줄 이유가 없다.
if (-not (Test-Server 0)) {
    Start-Process -FilePath $py `
        -ArgumentList '-m', 'uvicorn', 'ficc.app:app', '--port', $port `
        -WorkingDirectory $root `
        -WindowStyle Minimized

    if (-not (Test-Server 25)) {
        Fail @"
서버가 25초 안에 응답하지 않았다.

아래를 직접 실행해 오류를 확인하라.
  cd $root
  .venv\Scripts\python -m uvicorn ficc.app:app --port $port
"@
    }
}

$chrome = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($chrome) {
    Start-Process -FilePath $chrome -ArgumentList `
        "--app=$url", '--window-size=1920,1080', '--window-position=0,0'
} else {
    # 크롬 UI 만큼 세로가 줄어든다. F11 로 전체화면을 만들어야 스크롤이 없다.
    Start-Process $url
}

# 데스크를 열 때도 한 번 수집한다. 작업 스케줄러가 죽어 있거나(등록 해제, 배터리
# 정책, 로그온 안 한 날) 마지막 회차 이후 값이 갱신됐을 때의 백스톱이다.
#
# 반드시 화면을 띄운 뒤에, 반드시 비동기다. ingest 실측 소요가 12~13초라서 동기로
# 붙이면 아이콘을 누르고 13초 동안 아무것도 안 뜬다. 순서를 바꾸지 마라.
#
# 수집 실패가 대시보드 실행을 막지 않는다 — 실패는 ingest_result 에만 남고 런처는
# 이미 할 일을 끝냈다. 그래서 종료 코드도 보지 않고 Fail() 도 부르지 않는다.
# (여기서 뜨는 값은 화면에 자동 반영되지 않는다. 수집이 끝난 뒤 F5.)
try {
    Start-Process -FilePath $py `
        -ArgumentList '-m', 'ficc.ingest' `
        -WorkingDirectory $root `
        -WindowStyle Hidden
} catch {
    Write-Host "런처 수집을 띄우지 못했다: $($_.Exception.Message)"
}
