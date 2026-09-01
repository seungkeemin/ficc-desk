# 바탕화면에 실행 아이콘을 만든다.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1
#
# .lnk 은 바탕화면(저장소 밖)에 생기므로 저장소에는 이 생성기만 남는다.
# 저장소를 다른 곳으로 옮겼거나 아이콘을 지웠으면 이걸 다시 돌리면 된다.

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$bat  = Join-Path $root 'scripts\start.bat'
$icon = Join-Path $root 'scripts\ficc.ico'

if (-not (Test-Path $bat))  { throw "실행 스크립트가 없다: $bat" }
if (-not (Test-Path $icon)) { throw "아이콘이 없다: $icon  (python scripts\make_icon.py 로 만든다)" }

$link = Join-Path ([Environment]::GetFolderPath('Desktop')) 'FICC 데스크.lnk'

$shell    = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath       = $bat
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation     = "$icon,0"
$shortcut.Description      = 'FICC 데스크 대시보드 — 서버를 띄우고 Chrome 앱 모드로 연다'
$shortcut.WindowStyle      = 7   # 최소화. 런처 콘솔이 번쩍이지 않게 한다
$shortcut.Save()

Write-Host "만들었다: $link"
