FROM python:3.12-slim AS build

WORKDIR /build
COPY services/ml-service/requirements.txt .
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8002 \
    PYTHONPATH=/app:/opt/aegis/anomaly:/opt/aegis/classifier

RUN addgroup --system --gid 10001 aegis \
    && adduser --system --uid 10001 --ingroup aegis --home /home/aegis aegis

WORKDIR /app
COPY --from=build /wheels /wheels
COPY services/ml-service/requirements.txt .
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels
COPY --chown=aegis:aegis services/ml-service/app/ app/
COPY --chown=aegis:aegis ml/anomaly_detection/src/aegis_anomaly/ /opt/aegis/anomaly/aegis_anomaly/
COPY --chown=aegis:aegis ml/incident_classification/src/aegis_classifier/ /opt/aegis/classifier/aegis_classifier/

USER aegis
EXPOSE 8002
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8002}"]
