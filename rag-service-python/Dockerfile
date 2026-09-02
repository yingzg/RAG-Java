FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir numpy httpx pydantic-settings

COPY app/ app/
COPY config/ config/
COPY data/ data/
COPY frontend/ frontend/

RUN mkdir -p data/index data/traces

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
