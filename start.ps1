#!/usr/bin/env pwsh
# start.sh'in Windows PowerShell muadili.
# SpoofDPI'ı (gerekiyorsa) :8080'de başlatır, ardından bot.py'ı foreground'da çalıştırır.
# Override: $env:SPOOFDPI_BIN='C:\path\to\spoofdpi.exe'; $env:SPOOFDPI_PORT='8080'

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Invoke-SetupWizard {
    Write-Host "[setup] .env bulunamadi -- ilk-calistirma wizard'i"
    Write-Host ""

    do {
        $token = Read-Host "Discord bot token"
        if (-not $token) { Write-Host "  Bos olamaz, tekrar gir." }
    } while (-not $token)

    Write-Host ""
    Write-Host "Yerel LLM sunucu adresi:"
    Write-Host "  [1] http://localhost:3131/v1   (llama-server)"
    Write-Host "  [2] http://localhost:1234/v1   (LM Studio)"
    Write-Host "  [3] http://localhost:8000/v1   (vLLM / Ollama)"
    Write-Host "  [4] custom"
    $choice = Read-Host "Secim [1]"
    if (-not $choice) { $choice = "1" }
    switch ($choice) {
        "1"     { $baseUrl = "http://localhost:3131/v1" }
        "2"     { $baseUrl = "http://localhost:1234/v1" }
        "3"     { $baseUrl = "http://localhost:8000/v1" }
        "4"     { $baseUrl = Read-Host "  Custom URL" }
        default { $baseUrl = "http://localhost:3131/v1" }
    }

    Write-Host ""
    $model = Read-Host "Model identifier (tek-modelli sunucularda bos birakilabilir)"

    Write-Host ""
    Write-Host "Slash sync modu:"
    Write-Host "  [1] Dev -- guild ID set, slash aninda gorunur (onerilen)"
    Write-Host "  [2] Prod -- global, propagation ~1 saat"
    $syncChoice = Read-Host "Secim [1]"
    if (-not $syncChoice) { $syncChoice = "1" }
    $guildId = ""
    if ($syncChoice -eq "1") {
        Write-Host ""
        Write-Host "  ID icin: Discord -> Ayarlar -> Gelismis -> Gelistirici Modu;"
        Write-Host "  sunucu adina sag tik -> Sunucu Kimligini Kopyala"
        $guildId = Read-Host "  Discord sunucu ID (bos gecilebilir)"
    }

    Write-Host ""
    $tr = Read-Host "Turkiye'de misin? (Discord SNI engelli, SpoofDPI gerekli) [E/h]"
    if (-not $tr) { $tr = "E" }
    $proxy = ""
    if ($tr -match "^[EeYy]") {
        $proxy = "http://127.0.0.1:8080"
    }

    $envContent = @"
DISCORD_TOKEN=$token
OPENAI_BASE_URL=$baseUrl
OPENAI_API_KEY=not-needed
OPENAI_MODEL=$model
SESSION_TTL_SECONDS=7200
HISTORY_MAX_MESSAGES=100
GUILD_ID=$guildId
DISCORD_PROXY=$proxy

# Persistent memory (default'lar yeterli)
MEMPALACE_PATH=
MEMORY_AUTO_EXTRACT=true
MEMORY_EXTRACT_EVERY_N_MESSAGES=8
MEMORY_RETRIEVAL_K=3
MEMORY_MIN_FACT_LEN=6
"@

    Set-Content -Path ".env" -Value $envContent -Encoding UTF8
    Write-Host ""
    Write-Host "[setup] .env yazildi."
    Write-Host ""
}

if (-not (Test-Path -LiteralPath ".env")) {
    Invoke-SetupWizard
}

$SpoofdpiBin  = if ($env:SPOOFDPI_BIN)  { $env:SPOOFDPI_BIN }  else { Join-Path $env:USERPROFILE "Desktop\spoofdpi.exe" }
$SpoofdpiPort = if ($env:SPOOFDPI_PORT) { [int]$env:SPOOFDPI_PORT } else { 8080 }

$spoofdpiProcess = $null

function Test-PortInUse {
    param([int]$Port)
    try {
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop | Out-Null
        return $true
    } catch {
        return $false
    }
}

try {
    if (Test-PortInUse -Port $SpoofdpiPort) {
        Write-Host "[start] SpoofDPI :$SpoofdpiPort already running, reusing"
    } else {
        if (-not (Test-Path -LiteralPath $SpoofdpiBin)) {
            Write-Host "[start] SpoofDPI not found at $SpoofdpiBin" -ForegroundColor Red
            Write-Host "[start] override with: `$env:SPOOFDPI_BIN='C:\path\to\spoofdpi.exe'; .\start.ps1"
            exit 1
        }
        Write-Host "[start] launching SpoofDPI -window-size 1 on :$SpoofdpiPort (TLS Client Hello fragmentation for Discord DPI bypass)"
        $logOut = Join-Path $env:TEMP "spoofdpi.log"
        $logErr = Join-Path $env:TEMP "spoofdpi.err.log"
        $spoofdpiProcess = Start-Process `
            -FilePath $SpoofdpiBin `
            -ArgumentList @("-window-size", "1", "-port", "$SpoofdpiPort") `
            -RedirectStandardOutput $logOut `
            -RedirectStandardError  $logErr `
            -PassThru `
            -WindowStyle Hidden

        $bound = $false
        for ($i = 1; $i -le 5; $i++) {
            Start-Sleep -Seconds 1
            if (Test-PortInUse -Port $SpoofdpiPort) { $bound = $true; break }
        }
        if (-not $bound) {
            Write-Host "[start] SpoofDPI didn't bind :$SpoofdpiPort, see $logOut" -ForegroundColor Red
            exit 1
        }
    }

    Write-Host "[start] launching bot (preflight checks LLM + Discord reachability)"
    & python -u bot.py
}
finally {
    if ($spoofdpiProcess -and -not $spoofdpiProcess.HasExited) {
        Write-Host ""
        Write-Host "[stop] cleaning up SpoofDPI..."
        Stop-Process -Id $spoofdpiProcess.Id -ErrorAction SilentlyContinue
    }
}
