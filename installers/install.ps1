# omni-forge installer (Windows / PowerShell 5.1+)
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "== omni-forge installer =="

# 1. prerequisites
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "python 3.11+ is required" }
if (-not (Get-Command bun -ErrorAction SilentlyContinue)) { Write-Warning "bun not found - CLI/MCP will not be built" }

# 2. python venv + core services
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -e "apps/router[dev]" -e "apps/core[dev]"

# 3. config files (never overwrite existing)
if (-not (Test-Path "apps\router\providers.yaml")) {
    Copy-Item "apps\router\providers.example.yaml" "apps\router\providers.yaml"
    Write-Host "created apps\router\providers.yaml"
}
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "created .env - add your free API keys there"
}

# 4. typescript pieces
if (Get-Command bun -ErrorAction SilentlyContinue) {
    Push-Location "apps\mcp"; bun install; bun run build; Pop-Location
}

Write-Host ""
Write-Host "Done. Next:"
Write-Host "  1. edit .env with the free keys you have"
Write-Host "  2. .\.venv\Scripts\python -m uvicorn forge_router.main:app --port 4010"
Write-Host "  3. .\.venv\Scripts\python -m uvicorn forge_core.main:app --port 4020"
Write-Host "  4. open http://127.0.0.1:4010/forge/  (or use 'forge up' with pm2/docker)"