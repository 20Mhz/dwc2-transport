# Build tools only; no third-party runtime library dependencies.
FROM debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake binutils-arm-linux-gnueabi gcc-arm-linux-gnueabi \
    libc6-dev-armel-cross qemu-user-static python3 file ca-certificates clang-format \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
