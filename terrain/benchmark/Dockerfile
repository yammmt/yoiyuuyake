FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY terrain/scripts/benchmark_server.py terrain/scripts/dem_store.py terrain/scripts/horizon.py terrain/scripts/visibility.py terrain/scripts/validate_locations.py ./terrain/scripts/
COPY terrain/validation/locations-kanto.json ./terrain/validation/
USER 65532:65532
CMD ["python", "terrain/scripts/benchmark_server.py", "--host", "0.0.0.0"]
