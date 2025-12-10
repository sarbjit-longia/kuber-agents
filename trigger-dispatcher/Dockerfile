FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Set Python path
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Run the dispatcher
CMD ["python", "-m", "app.main"]

