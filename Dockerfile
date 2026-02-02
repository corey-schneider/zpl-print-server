# Dockerfile
FROM python:3.11-slim

# Install system dependencies
# poppler-utils: required for pdf2image
# netcat-openbsd: used for network checking
RUN apt-get update && apt-get install -y \
    poppler-utils \
    netcat-openbsd \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create data directory for persistence
RUN mkdir -p /app/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Expose Web Port
EXPOSE 8000

# Run using Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
