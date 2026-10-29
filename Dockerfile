FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer ffmpeg fonts-liberation fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml alembic.ini ./
COPY bp_bot ./bp_bot
COPY migrations ./migrations
RUN useradd --create-home bot && chown -R bot:bot /app
USER bot
CMD ["python", "-m", "bp_bot"]
