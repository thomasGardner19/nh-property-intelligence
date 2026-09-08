FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PREFECT_HOME=/tmp/prefect \
    PREFECT_LOCAL_STORAGE_PATH=/tmp/prefect/storage \
    PREFECT_SERVER_ANALYTICS_ENABLED=false

WORKDIR /app

COPY . /app
RUN python -m pip install --upgrade pip \
    && python -m pip install -e . \
    && useradd --create-home --uid 10001 nhpi \
    && mkdir -p /tmp/prefect/storage \
    && chown -R nhpi:nhpi /tmp/prefect

USER nhpi

CMD ["python", "-m", "nh_property_intelligence.orchestration.refresh"]
