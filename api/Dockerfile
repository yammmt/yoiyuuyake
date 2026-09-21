FROM python:3.13-slim

WORKDIR /app
ENV HOST=0.0.0.0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir --requirement api/requirements.txt

COPY api ./api/
COPY weather ./weather/
COPY terrain/scripts/astronomy.py terrain/scripts/dem_store.py terrain/scripts/horizon.py terrain/scripts/visibility.py ./terrain/scripts/

USER 65532:65532
EXPOSE 8080
CMD ["gunicorn", "--config", "api/gunicorn.conf.py", "api.wsgi:application"]
