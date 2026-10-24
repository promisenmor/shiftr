FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY . .

RUN chmod +x docker-entrypoint.sh \
    && groupadd --system shiftr \
    && useradd --system --gid shiftr --home-dir /app shiftr \
    && chown -R shiftr:shiftr /app

USER shiftr

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/admin/login/', timeout=3)"

ENTRYPOINT ["./docker-entrypoint.sh"]
