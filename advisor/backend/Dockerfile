FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY alembic.ini .
COPY migrations/ migrations/
COPY scanner_entrypoint.py .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
