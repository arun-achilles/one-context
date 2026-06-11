FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 and git
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY hygiene/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Apply DB schema on first run via entrypoint, not here
# Schema is applied by: docker compose run api python db/connection.py

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
