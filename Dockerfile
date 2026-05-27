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
COPY tests/ ./tests/
COPY run.py ./run.py
COPY requirements.txt ./requirements.txt

# Create writable SQLite data directory
RUN mkdir -p /app/backend/data

# Create non-root user and grant app ownership
RUN useradd -m -u 10001 geolog \
    && chown -R geolog:geolog /app
USER geolog

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status < 500 else 1)"

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
