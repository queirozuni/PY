
#--COMO RODAR LOCALMENTE (Windows PowerShell)--

# 1) Ir até a pasta do projeto
cd C:\caminho\para\uniapi

# 2) Criar e ativar ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3) Atualizar pip e instalar dependências
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4) Criar .env e ajustar SECRET_KEY / ADMIN_PASS
copy .env.example .env
notepad .env

# 5) Rodar em desenvolvimento
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
# acessar: http://127.0.0.1:8000/login

# --Produção como serviço Windows (NSSM)
# Baixe o NSSM (x64) e garanta que nssm.exe está no PATH
# Instalar o serviço:
nssm install UniApi "C:\caminho\uniapi\.venv\Scripts\uvicorn.exe" "app.main:app"
nssm set UniApiLogin AppParameters "app.main:app --host 127.0.0.1 --port 8000 --workers 2"
nssm set UniApiLogin Start SERVICE_AUTO_START
nssm set UniApiLogin AppStdout "C:\caminho\uniapi\logs\uniapi.out.log"
nssm set UniApiLogin AppStderr "C:\caminho\uniapi\logs\uniapi.err.log"
nssm start UniApiLogin
