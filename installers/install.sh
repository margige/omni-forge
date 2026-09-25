#!/usr/bin/env bash
# omni-forge installer (Linux / macOS / WSL)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== omni-forge installer =="

command -v python3 || { echo "python3 3.11+ required"; exit 1; }
command -v bun || echo "warning: bun not found - CLI/MCP will not be built"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
./.venv/bin/python -m pip install -q --upgrade pip
./.venv/bin/python -m pip install -q -e "apps/router[dev]" -e "apps/core[dev]"

if [ ! -f apps/router/providers.yaml ]; then
  cp apps/router/providers.example.yaml apps/router/providers.yaml
  echo "created apps/router/providers.yaml"
fi
if [ ! -f .env ]; then
  cp .env.example .env
  echo "created .env - add your free API keys there"
fi

if command -v bun >/dev/null 2>&1; then
  (cd apps/mcp && bun install && bun run build)
fi

echo ""
echo "Done. Next:"
echo "  1. edit .env with the free keys you have"
echo "  2. ./.venv/bin/python -m uvicorn forge_router.main:app --port 4010"
echo "  3. ./.venv/bin/python -m uvicorn forge_core.main:app --port 4020"
echo "  4. open http://127.0.0.1:4010/forge/  (or use 'forge up' with pm2/docker)"