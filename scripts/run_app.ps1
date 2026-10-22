$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "Virtual environment is missing: $Python"
    exit 1
}
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root "src"
& $Python -m localvideoai @args
exit $LASTEXITCODE
