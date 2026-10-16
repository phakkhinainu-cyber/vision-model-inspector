# Build LPR บ้าน บน Windows 10/11 x64 (Python 3.11/3.12 x64, Node.js 20+, Inno Setup 6)
# Usage (PowerShell, จากโฟลเดอร์ lpr):  powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
param([string]$Python = "py -3.12", [switch]$SkipInstaller)
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
Push-Location frontend; npm ci; npm run build; Pop-Location
Invoke-Expression "$Python -m venv .venv-build"
. .\.venv-build\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements\runtime.txt -r requirements\desktop.txt -r requirements\dev.txt
python tools\fetch_models.py
pip-licenses --from=mixed --format=plain-vertical --with-license-file --no-license-path --with-urls --output-file THIRD_PARTY_NOTICES.txt
pyinstaller --noconfirm --clean packaging\lpr.spec
if (-not (Test-Path packaging\WinSW-x64.exe)) {
  Invoke-WebRequest https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe -OutFile packaging\WinSW-x64.exe
}
if (-not $SkipInstaller) {
  $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
  & $iscc /DAppVersion=1.0.0 packaging\installer.iss
  Write-Host "installer: Output\LPR-Setup-1.0.0.exe"
}
