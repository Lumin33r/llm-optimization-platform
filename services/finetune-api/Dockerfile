FROM python:3.11-slim

WORKDIR /app

# Install shared library first
COPY shared/requirements.txt /app/shared/requirements.txt
RUN pip install --no-cache-dir -r /app/shared/requirements.txt

# Install finetune-api dependencies
COPY finetune-api/requirements.txt /app/finetune-api/requirements.txt
RUN pip install --no-cache-dir -r /app/finetune-api/requirements.txt

# Copy shared library
COPY shared/ /app/shared/

# Copy finetune-api code
COPY finetune-api/ /app/finetune-api/

WORKDIR /app/finetune-api

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
