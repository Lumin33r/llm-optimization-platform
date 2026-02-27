FROM python:3.11-slim

WORKDIR /app

# Install shared library first
COPY shared/requirements.txt /app/shared/requirements.txt
RUN pip install --no-cache-dir -r /app/shared/requirements.txt

# Install eval-api dependencies
COPY eval-api/requirements.txt /app/eval-api/requirements.txt
RUN pip install --no-cache-dir -r /app/eval-api/requirements.txt

# Copy shared library
COPY shared/ /app/shared/

# Copy eval-api code
COPY eval-api/ /app/eval-api/

WORKDIR /app/eval-api

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
