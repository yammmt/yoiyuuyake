FROM rust:1.99.1-bookworm AS build
WORKDIR /build
COPY recorder/Cargo.toml recorder/Cargo.lock recorder/rust-toolchain.toml recorder/
COPY recorder/src recorder/src
COPY recorder/tests recorder/tests
COPY weather/tests/fixtures/open_meteo_forecast.json weather/tests/fixtures/
WORKDIR /build/recorder
RUN cargo test --release --locked && cargo build --release --locked

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /build/recorder/target/release/forecast-recorder /usr/local/bin/forecast-recorder
USER 65532:65532
ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/forecast-recorder"]
