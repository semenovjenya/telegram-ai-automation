FROM python:3.15.2-alpine3.24@sha256:0f9552bb28711333da16915ec146f5e6bb44a7fdac9ced15dc17c2e0206346dd

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
