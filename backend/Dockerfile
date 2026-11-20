FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY . .

# Root olmayan kullanıcıyla çalış
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Açılışta migration'ları uygula, sonra API'yi başlat
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
