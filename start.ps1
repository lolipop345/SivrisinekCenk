#!/usr/bin/env pwsh
# start.sh'in Windows PowerShell muadili.
# SpoofDPI'ı (gerekiyorsa) :8080'de başlatır, ardından bot.py'ı foreground'da çalıştırır.
# Override: $env:SPOOFDPI_BIN='C:\path\to\spoofdpi.exe'; $env:SPOOFDPI_PORT='8080'

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

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
