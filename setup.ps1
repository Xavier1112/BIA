$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pythonCommand) { & py -3.12 -m venv .venv }
    else {
        $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (Test-Path -LiteralPath $bundledPython) { & $bundledPython -m venv .venv }
        else { throw 'Install Python 3.12 from python.org, including the Python launcher, then retry.' }
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python 3.12 environment.' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the network and retry.' }
Write-Host 'Ready. Double-click Launch.cmd to open the desktop app.'
