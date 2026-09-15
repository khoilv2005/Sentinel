# Build distributable SentinelView Agent binaries as part of the server image.
FROM golang:1.25-alpine AS agent-build
WORKDIR /src
COPY agents/sentinel-agent/go.mod ./
COPY agents/sentinel-agent/*.go ./
RUN go mod tidy \
    && go mod download all \
    && go mod verify \
    && go test ./...
RUN mkdir -p /out \
    && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -mod=readonly -trimpath -ldflags="-s -w" -o /out/sentinel-agent-linux-amd64 . \
    && CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -mod=readonly -trimpath -ldflags="-s -w" -o /out/sentinel-agent-windows-amd64.exe . \
    && cd /out \
    && sha256sum sentinel-agent-linux-amd64 > sentinel-agent-linux-amd64.sha256 \
    && sha256sum sentinel-agent-windows-amd64.exe > sentinel-agent-windows-amd64.exe.sha256

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping iproute2 \
    && rm -rf /var/lib/apt/lists/*
COPY services/control-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/control-api/app ./app
COPY services/control-api/tests ./tests
COPY --from=agent-build /out /opt/sentinel/artifacts
ENV SENTINEL_ARTIFACT_DIR=/opt/sentinel/artifacts
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
