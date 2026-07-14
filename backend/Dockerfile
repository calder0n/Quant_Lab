FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so source changes don't invalidate this layer.
COPY pyproject.toml ./
COPY src ./src
RUN pip install -e ".[dev]"

COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
COPY tests ./tests

EXPOSE 8000

CMD ["uvicorn", "quantlab.interfaces.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
