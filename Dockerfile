FROM python:3.11-slim

WORKDIR /app

# Install OS dependencies needed for healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

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
RUN useradd -m geolog \
    && chown -R geolog:geolog /app
USER geolog

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
