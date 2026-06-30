# SPDX-License-Identifier: MIT

FROM golang:1.24.1-bookworm AS builder

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=1 go build -o /out/packetrusher ./cmd/packetrusher.go

FROM debian:bookworm-slim AS packetrusher

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      iproute2 \
      iputils-ping \
      procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /packetrusher
COPY --from=builder /out/packetrusher /usr/local/bin/packetrusher
COPY config/config.yml /packetrusher/config/config.yml

ENTRYPOINT ["/usr/local/bin/packetrusher"]
