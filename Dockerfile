FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 paygam \
    && chmod +x /app/scripts/entrypoint.sh \
    && chown -R paygam:paygam /app
USER paygam

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
