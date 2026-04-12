# Development Dockerfile for Trading Platform Backend
# Includes development tools and hot-reload support

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    git \
    vim \
    # WeasyPrint dependencies
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libglib2.0-0 \
    libfontconfig1 \
    fonts-dejavu-core \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
COPY backend/requirements-dev.txt .
COPY signal-generator/requirements.txt /tmp/signal-generator-requirements.txt
COPY backend/scripts/patch_crewai_runtime.py /tmp/patch_crewai_runtime.py

RUN pip install --no-cache-dir -r requirements.txt
RUN python /tmp/patch_crewai_runtime.py
RUN pip install --no-cache-dir -r requirements-dev.txt
RUN pip install --no-cache-dir -r /tmp/signal-generator-requirements.txt

# Copy application code (will be mounted as volume for hot-reload)
COPY backend/ .
COPY signal-generator/app /opt/signal-generator/app
COPY signal-generator/config /opt/signal-generator/config

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Development command with hot-reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
