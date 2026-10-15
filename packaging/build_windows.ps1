# Build Vision Model Inspector (CPU) on Windows 10/11 x64.
# Requirements: Python 3.12 x64, internet access during the build, Inno Setup 6 (for the installer).
# Usage (PowerShell, from the repository root):
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
param(
  [string]$Python = "py -3.12",
  [switch]$SkipInstaller
)
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

Invoke-Expression "$Python -m venv .venv-build"
. .\.venv-build\Scripts\Activate.ps1
python -m pip install --upgrade pip
if (Test-Path requirements\lock-windows-cpu.txt) {
  # exact versions that were tested by CI
  pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements\lock-windows-cpu.txt
} else {
  pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.3,<2.9" "torchvision>=0.18,<0.24"
  pip install -r requirements\runtime.in -r requirements\dev.in
}
python tools\fetch_fonts.py
python tools\make_icon.py
pip-licenses --from=mixed --format=plain-vertical --with-license-file --no-license-path --with-urls --output-file THIRD_PARTY_NOTICES.txt
pyinstaller --noconfirm --clean packaging\vmi.spec
Write-Host "onedir build: dist\VisionModelInspector\VisionModelInspector.exe"

if (-not $SkipInstaller) {
  $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
  if (-not (Test-Path $iscc)) { throw "Inno Setup 6 not found: install from https://jrsoftware.org/isdl.php" }
  & $iscc /DAppVersion=0.1.0 packaging\installer.iss
  Write-Host "installer: Output\VisionModelInspector-0.1.0-cpu-setup.exe"
}
