#!/usr/bin/env sh
set -eu
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example."
  echo "Before non-lab use, change SentinelView admin/API/session/database/Grafana secrets."
fi
docker compose up -d --build
docker compose ps
printf '\nSentinelView UI: http://localhost:3001\nControl API: http://localhost:8080/docs\nGrafana advanced analytics: http://localhost:3000\nPrometheus: http://localhost:9090\n'
