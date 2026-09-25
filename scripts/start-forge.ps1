# start-forge.ps1 — inject .env into the environment, then start router(4010) + core(4020).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\start-forge.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path   # scripts/
$root = Split-Path -Parent $root                          # repo root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "no .venv found - run installers\install.ps1 first" }

$logs = Join-Path $env:TEMP "forge"
New-Item -ItemType Directory -Path $logs -Force | Out-Null

# inject .env values (the apps read os.environ directly; they do not load .env themselves)
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $t = $_.Trim()
        if ($t -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $k = $Matches[1]; $v = $Matches[2].Trim()
            if ($v -ne "") { Set-Item -Path "Env:$k" -Value $v }
        }
    }
}

# clear stale listeners on our ports first
foreach ($port in 4010, 4020) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

$p1 = Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", "forge_router.main:app", "--host", "127.0.0.1", "--port", "4010" -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput "$logs\router.out.log" -RedirectStandardError "$logs\router.err.log" -PassThru
$p2 = Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", "forge_core.main:app", "--host", "127.0.0.1", "--port", "4020" -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput "$logs\core.out.log" -RedirectStandardError "$logs\core.err.log" -PassThru
"$($p1.Id) $($p2.Id)" | Set-Content (Join-Path $logs "pids.txt")

Start-Sleep -Seconds 5
Write-Host "router :4010  pid=$($p1.Id)  (GET /forge/quota)"
Write-Host "core   :4020  pid=$($p2.Id)  (GET /forge/health)"
Write-Host "dashboard       http://127.0.0.1:4010/forge/"
Write-Host "logs            $logs"