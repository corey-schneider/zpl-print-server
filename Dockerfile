FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    libzbar0 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create data directory for persistence
RUN mkdir -p /app/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY entrypoint.sh .

EXPOSE 8000
ENV PYTHONPATH=/app

# Run using entrypoint script (handles .env generation and startup)
ENTRYPOINT ["bash", "entrypoint.sh"]
