param([switch]$Test)
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if (-not [Environment]::Is64BitProcess) { throw 'Use 64-bit Python and PowerShell.' }
    if (-not (Test-Path '.venv\Scripts\python.exe')) {
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Install 64-bit Python 3.12 from python.org (including the py launcher).' }
    }
    # windows-capture requires opencv-python. Both OpenCV distributions own cv2;
    # remove the old headless distribution when upgrading the Windows venv.
    & .\.venv\Scripts\python.exe -m pip uninstall -y opencv-python-headless
    if ($LASTEXITCODE -ne 0) { throw 'OpenCV upgrade preparation failed.' }
    & .\.venv\Scripts\python.exe -m pip install -c constraints.txt -e . 'pytest==9.1.1'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & .\.venv\Scripts\python.exe -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }
    if ($Test) {
        & .\.venv\Scripts\python.exe -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    }
} finally { Pop-Location }
