$ErrorActionPreference = "Stop"
if (!(Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example." -ForegroundColor Yellow
    Write-Host "Before non-lab use, change SentinelView admin/API/session/database/Grafana secrets." -ForegroundColor Yellow
}
docker compose up -d --build
docker compose ps
Write-Host "SentinelView UI: http://localhost:3001" -ForegroundColor Green
Write-Host "Control API: http://localhost:8080/docs" -ForegroundColor DarkGray
Write-Host "Grafana advanced analytics: http://localhost:3000" -ForegroundColor DarkGray
Write-Host "Prometheus: http://localhost:9090" -ForegroundColor DarkGray
