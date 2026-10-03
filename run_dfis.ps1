$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "DFIS virtual environment not found at $python"
}

if (-not (Test-Path (Join-Path $PSScriptRoot ".env"))) {
    Copy-Item (Join-Path $PSScriptRoot ".env.example") (Join-Path $PSScriptRoot ".env")
}

$toolBin = Join-Path $env:USERPROFILE ".local\bin"
if (Test-Path $toolBin) {
    $env:Path = "$toolBin;$env:Path"
}

if ((Get-Command ollama -ErrorAction SilentlyContinue) -and -not (Test-NetConnection 127.0.0.1 -Port 11434 -InformationLevel Quiet)) {
    Write-Host "Starting Ollama..."
    Start-Process -FilePath (Get-Command ollama).Source -ArgumentList "serve" -WindowStyle Minimized | Out-Null
    $ready = $false
    1..20 | ForEach-Object {
        if (-not $ready) {
            Start-Sleep -Milliseconds 500
            $ready = Test-NetConnection 127.0.0.1 -Port 11434 -InformationLevel Quiet
        }
    }
    if (-not $ready) {
        Write-Warning "Ollama did not become available; DFIS will use rule-based analysis."
    }
}

Write-Host "Starting DFIS. All selected OSINT tools run concurrently during each scan."
Write-Host "Open http://127.0.0.1:8000"
Write-Host "Press Ctrl+C to stop."
Set-Location (Join-Path $PSScriptRoot "backend")
& $python -m uvicorn main:app --host 127.0.0.1 --port 8000
