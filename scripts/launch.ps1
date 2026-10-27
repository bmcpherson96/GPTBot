$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Run scripts\setup.ps1 first.' }
    & .\.venv\Scripts\python.exe -m teachdesk.ui
    if ($LASTEXITCODE -ne 0) { throw 'TeachDesk exited with an error.' }
} finally { Pop-Location }
