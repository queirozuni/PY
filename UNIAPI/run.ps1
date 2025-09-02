# run.ps1 - iniciar UniApi no VS Code

$ErrorActionPreference = "Stop"

# 1) venv
if (-not (Test-Path ".\.venv")) {
  Write-Host "  Criando ambiente virtual..." -ForegroundColor Yellow
  python -m venv .venv
}
Write-Host " Ativando ambiente virtual..." -ForegroundColor Cyan
. .\.venv\Scripts\Activate.ps1

# 2) deps
Write-Host " Verificando/instalando dependências..." -ForegroundColor Yellow
python -m pip install --upgrade pip
pip install -r requirements.txt

# 3) .env
if (-not (Test-Path ".env")) {
  Write-Host "  .env não encontrado. Copie .env.example para .env e ajuste SECRET_KEY/ADMIN_PASS." -ForegroundColor Red
  exit 1
}

# 4) start
Write-Host " Iniciando em http://127.0.0.1:8000 ..." -ForegroundColor Green
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
