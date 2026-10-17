FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

# Install runtime dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application package only (tests, venv, docs are excluded via .dockerignore).
COPY app ./app

EXPOSE 8000

# Factory pattern: app.main:create_app builds the FastAPI app.
# Shell form so $PORT (injected by Render/Cloud Run) is honored; falls back to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
