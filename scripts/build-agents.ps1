$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Out = Join-Path $Root "dist\agents"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
Push-Location (Join-Path $Root "agents\sentinel-agent")
try {
    go mod tidy
    go mod download all
    go mod verify
    go test ./...
    $env:CGO_ENABLED = "0"
    $env:GOOS = "linux"; $env:GOARCH = "amd64"
    go build -mod=readonly -trimpath -ldflags="-s -w" -o (Join-Path $Out "sentinel-agent-linux-amd64") .
    $env:GOOS = "windows"; $env:GOARCH = "amd64"
    go build -mod=readonly -trimpath -ldflags="-s -w" -o (Join-Path $Out "sentinel-agent-windows-amd64.exe") .
} finally { Pop-Location }
Get-FileHash -Algorithm SHA256 (Join-Path $Out "sentinel-agent-linux-amd64") | ForEach-Object { "$($_.Hash.ToLower())  sentinel-agent-linux-amd64" } | Set-Content (Join-Path $Out "sentinel-agent-linux-amd64.sha256")
Get-FileHash -Algorithm SHA256 (Join-Path $Out "sentinel-agent-windows-amd64.exe") | ForEach-Object { "$($_.Hash.ToLower())  sentinel-agent-windows-amd64.exe" } | Set-Content (Join-Path $Out "sentinel-agent-windows-amd64.exe.sha256")
Write-Host "Built agent artifacts in $Out" -ForegroundColor Green
