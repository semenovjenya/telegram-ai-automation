FROM python:3.15.0-alpine3.24@sha256:2699b90f4d562a22e2dd076c82f964032f64814204bff36d271a54ba4cc2c7e2

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

RUN apk add --no-cache font-dejavu font-liberation \
    && addgroup -S app \
    && adduser -S -D -H -u 10001 -G app app

COPY requirements.lock ./requirements.lock
RUN python -m pip install --require-hashes --requirement requirements.lock \
    && python -m pip uninstall --yes setuptools wheel \
    && rm -rf /usr/local/lib/python3.11/site-packages/pip* /usr/local/bin/pip*

COPY --chown=app:app . ./ai_brain

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"

CMD ["python", "-m", "uvicorn", "ai_brain.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
