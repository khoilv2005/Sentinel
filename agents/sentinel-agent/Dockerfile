FROM golang:1.25-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY *.go ./
RUN go mod tidy \
    && go mod download all \
    && go mod verify \
    && go test ./...
RUN CGO_ENABLED=0 go build -mod=readonly -trimpath -ldflags="-s -w" -o /out/sentinel-agent .
FROM alpine:3.22
RUN apk add --no-cache ca-certificates
COPY --from=build /out/sentinel-agent /usr/local/bin/sentinel-agent
ENTRYPOINT ["/usr/local/bin/sentinel-agent"]
