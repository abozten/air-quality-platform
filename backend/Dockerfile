# backend/Dockerfile
# Use the desired Python 3.13 slim base image
FROM python:3.13-slim

WORKDIR /app
# Install build tools needed for C/C++ extensions like python-geohash
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    # Clean up apt cache to reduce image size
    rm -rf /var/lib/apt/lists/*

# Install build dependencies (gcc, etc.), create python user, then install requirements, then remove build deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir python-dotenv pydantic-settings # Pre-install some base packages if needed

# Copy requirements first to leverage Docker cache
COPY ./requirements.txt /app/requirements.txt

# Install application dependencies (now with build tools available)
RUN pip install --no-cache-dir -r requirements.txt

# No need to remove build-essential here if we install only gcc/libc-dev
# If you installed build-essential, you could remove it after pip install:
# RUN apt-get purge -y --auto-remove build-essential gcc libc-dev && rm -rf /var/lib/apt/lists/*

# Copy the rest of the application code
COPY ./app /app/app

# Default command can be overridden in docker-compose
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]