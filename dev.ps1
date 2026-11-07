# Starts the Klypsy backend (FastAPI :8000) and frontend (Next.js :3000) for development.
# Every cache / temp folder points inside this project on D: so nothing is written to C:.
$root = $PSScriptRoot
$env:TEMP = "$root\.tmp"; $env:TMP = "$root\.tmp"
$env:UV_CACHE_DIR = "$root\.uv-cache"
$env:UV_PYTHON_INSTALL_DIR = "$root\.uv-python"
$env:npm_config_cache = "$root\.npm-cache"
$env:NEXT_TELEMETRY_DISABLED = "1"
New-Item -ItemType Directory -Force "$root\.tmp" | Out-Null

Push-Location "$root\backend"; uv sync; Pop-Location
if (-not (Test-Path "$root\web\node_modules")) { Push-Location "$root\web"; npm install; Pop-Location }

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; `$env:TEMP='$root\.tmp'; `$env:TMP='$root\.tmp'; uv run uvicorn app.main:app --reload --reload-dir app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\web'; `$env:TEMP='$root\.tmp'; `$env:TMP='$root\.tmp'; `$env:NEXT_TELEMETRY_DISABLED='1'; npm run dev"
Write-Host "Backend: http://localhost:8000/docs   Frontend: http://localhost:3000"
