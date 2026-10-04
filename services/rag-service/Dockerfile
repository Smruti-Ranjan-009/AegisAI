FROM python:3.12-slim AS build

WORKDIR /build
COPY requirements.txt .
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8003

RUN addgroup --system --gid 10001 aegis \
    && adduser --system --uid 10001 --ingroup aegis --home /home/aegis aegis

WORKDIR /app
COPY --from=build /wheels /wheels
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels
COPY --chown=aegis:aegis app/ app/

USER aegis
EXPOSE 8003
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8003}"]
