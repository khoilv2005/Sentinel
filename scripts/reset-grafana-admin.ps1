param(
  [Parameter(Mandatory = $true)]
  [string]$Password
)

$ErrorActionPreference = 'Stop'

Write-Host 'Resetting the Grafana admin password in the persistent Grafana database...'
docker compose exec -T grafana grafana cli admin reset-admin-password $Password
if ($LASTEXITCODE -ne 0) {
  throw "Grafana password reset failed with exit code $LASTEXITCODE"
}
Write-Host 'Grafana admin password reset completed.'
