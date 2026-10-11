FROM python:3.12-slim AS build

WORKDIR /build
COPY services/rag-service/requirements.txt .
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8003 \
    PYTHONPATH=/app:/opt/aegis/ingestion:/opt/aegis/retrieval:/opt/aegis/reranking:/opt/aegis/generation

RUN addgroup --system --gid 10001 aegis \
    && adduser --system --uid 10001 --ingroup aegis --home /home/aegis aegis

WORKDIR /app
COPY --from=build /wheels /wheels
COPY services/rag-service/requirements.txt .
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels
COPY --chown=aegis:aegis services/rag-service/app/ app/
COPY --chown=aegis:aegis rag/ingestion/src/aegis_rag_ingestion/ /opt/aegis/ingestion/aegis_rag_ingestion/
COPY --chown=aegis:aegis rag/retrieval/src/aegis_rag_retrieval/ /opt/aegis/retrieval/aegis_rag_retrieval/
COPY --chown=aegis:aegis rag/reranking/src/aegis_rag_reranking/ /opt/aegis/reranking/aegis_rag_reranking/
COPY --chown=aegis:aegis rag/generation/src/aegis_rag_generation/ /opt/aegis/generation/aegis_rag_generation/
RUN python -c "import app.main"

USER aegis
EXPOSE 8003
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8003}"]
