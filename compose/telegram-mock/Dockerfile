FROM python:3.11.15-alpine3.24@sha256:25976e9d34a0fab1f278cae931f34c8303d97bf0c0d7f85b6b4dcf641d7702a4

WORKDIR /app

COPY server.py ./server.py

RUN python -m pip uninstall --yes setuptools wheel \
    && rm -rf /usr/local/lib/python3.11/site-packages/pip* /usr/local/bin/pip* \
    && addgroup -S app \
    && adduser -S -D -H -u 10001 -G app app
USER app

EXPOSE 8010

HEALTHCHECK --interval=10s --timeout=3s --start-period=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=2)"

CMD ["python", "server.py"]
