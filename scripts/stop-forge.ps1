# stop-forge.ps1 — stop router(4010) + core(4020) started by start-forge.ps1.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$logs = Join-Path $env:TEMP "forge"
$pidFile = Join-Path $logs "pids.txt"
if (Test-Path $pidFile) {
    Get-Content $pidFile | ForEach-Object {
        if ($_ -match '^\d+$') { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    }
}
foreach ($port in 4010, 4020) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}
Write-Host "forge services stopped"