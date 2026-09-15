#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUT="$ROOT/dist/agents"
mkdir -p "$OUT"
cd "$ROOT/agents/sentinel-agent"
go mod tidy
go mod download all
go mod verify
go test ./...
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -mod=readonly -trimpath -ldflags="-s -w" -o "$OUT/sentinel-agent-linux-amd64" .
CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -mod=readonly -trimpath -ldflags="-s -w" -o "$OUT/sentinel-agent-windows-amd64.exe" .
cd "$OUT"
sha256sum sentinel-agent-linux-amd64 > sentinel-agent-linux-amd64.sha256
sha256sum sentinel-agent-windows-amd64.exe > sentinel-agent-windows-amd64.exe.sha256
printf 'Built agent artifacts in %s\n' "$OUT"
