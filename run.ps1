param([switch]$Demo)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Create .venv and install requirements.txt first. See README.md.'
}
$previousAppMode = $env:APP_MODE
$previousAuthMode = $env:AUTH_MODE
try {
    if ($Demo) {
        $env:APP_MODE = 'demo'
        $env:AUTH_MODE = 'demo'
        Write-Host 'Starting local SQLite demo at http://127.0.0.1:8501'
    }
    & $projectPython -m streamlit run app.py --server.address 127.0.0.1
} finally {
    $env:APP_MODE = $previousAppMode
    $env:AUTH_MODE = $previousAuthMode
}
