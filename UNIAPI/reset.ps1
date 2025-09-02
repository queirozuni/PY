# reset-db.ps1 - Reseta o banco SQLite usado pela UniApi
# ⚠️ ATENÇÃO: Este script apaga TODO o banco de dados (data/app.db)

# Forçar UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"

$projPath = Get-Location
$dbPath   = Join-Path $projPath "data\app.db"

Write-Host ""
Write-Host "⚠️  ATENÇÃO: Este procedimento irá APAGAR TODO o banco de dados UniApi." -ForegroundColor Red
Write-Host "⚠️  Isso inclui TODOS os usuários criados e configurações persistidas." -ForegroundColor Red
Write-Host ""
$confirm = Read-Host "Digite 'SIM' para confirmar a exclusão ou qualquer outra coisa para cancelar"

if ($confirm -ne "SIM") {
    Write-Host "❌ Operação cancelada pelo usuário." -ForegroundColor Yellow
    exit 1
}

if (Test-Path $dbPath) {
    Remove-Item $dbPath -Force
    Write-Host "🗑️  Arquivo $dbPath removido." -ForegroundColor Cyan
} else {
    Write-Host "ℹ️  Nenhum banco encontrado em $dbPath." -ForegroundColor Gray
}

$dataFolder = Join-Path $projPath "data"
if (-not (Test-Path $dataFolder)) {
    New-Item -ItemType Directory -Path $dataFolder | Out-Null
    Write-Host "📁 Pasta 'data' criada." -ForegroundColor Green
}

Write-Host ""
Write-Host "✅ Banco resetado." -ForegroundColor Green
Write-Host "➡️  Rode .\\run.ps1 para recriar o banco com ADMIN_USER/ADMIN_PASS do .env" -ForegroundColor Green
