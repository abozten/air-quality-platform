# backend/Dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install build dependencies, then install requirements, then remove build deps
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir python-dotenv pydantic-settings \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app /app/app

# Default command can be overridden in docker-compose
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]