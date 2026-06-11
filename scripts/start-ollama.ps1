#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Starts Ollama for Docker access and launches VIKI.
.DESCRIPTION
    Sets OLLAMA_HOST=0.0.0.0:11434 (required for Docker container access),
    starts Ollama if not running, waits for it to be ready, then runs
    `docker compose run --rm -it viki`.
#>

$OllamaPort = 11434
$HostBinding = "0.0.0.0:$OllamaPort"
$OllamaUrl = "http://127.0.0.1:$OllamaPort"

# Check if Ollama is already running
try {
    $null = Invoke-WebRequest -Uri "$OllamaUrl/api/tags" -Method Get -TimeoutSec 3 -ErrorAction Stop
    Write-Host "Ollama is already running." -ForegroundColor Green
} catch {
    Write-Host "Starting Ollama on $HostBinding ..." -ForegroundColor Yellow
    $env:OLLAMA_HOST = $HostBinding
    $env:OLLAMA_CUDA = "0"
    $proc = Start-Process -FilePath "ollama.exe" -ArgumentList "serve" -WindowStyle Hidden -PassThru

    # Wait for Ollama to become ready
    $maxWait = 15
    $waited = 0
    while ($waited -lt $maxWait) {
        Start-Sleep -Seconds 1
        $waited++
        try {
            $null = Invoke-WebRequest -Uri "$OllamaUrl/api/tags" -Method Get -TimeoutSec 2 -ErrorAction Stop
            Write-Host "Ollama is ready." -ForegroundColor Green
            break
        } catch {
            if ($waited -eq $maxWait) {
                Write-Host "ERROR: Ollama did not start within ${maxWait}s." -ForegroundColor Red
                exit 1
            }
        }
    }
}

# Navigate to project root and launch VIKI
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir/.."
Push-Location $ProjectRoot
try {
    docker compose run --rm -it viki
} finally {
    Pop-Location
}
