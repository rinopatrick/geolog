FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir reportlab \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy application files
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY run.py ./run.py
COPY requirements.txt ./requirements.txt
# Needed at startup: backend/schema.py runs migrations, which read this file.
COPY alembic.ini ./alembic.ini

# Create writable SQLite data directory
RUN mkdir -p /app/backend/data

# Create non-root user and grant app ownership
RUN useradd -m -u 10001 borelia \
    && chown -R borelia:borelia /app
USER borelia

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status < 500 else 1)"

# Schema migrations are a deploy step, not a worker startup step. Set
# BORELIA_ENV=prod and run `alembic upgrade head` once before starting workers.
ENV BORELIA_ENV=prod
CMD ["sh", "-c", "python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers ${BORELIA_WORKERS:-2}"]
