FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psutil
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
# Explicitly ensure utils directory is copied (in case of caching issues)
COPY app/utils/ ./app/utils/

# Set Python path
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Run the dispatcher
CMD ["python", "-m", "app.main"]

