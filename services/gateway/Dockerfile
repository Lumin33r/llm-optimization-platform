FROM python:3.11-slim

WORKDIR /app

# Install shared library first
COPY shared/requirements.txt /app/shared/requirements.txt
RUN pip install --no-cache-dir -r /app/shared/requirements.txt

# Install gateway dependencies
COPY gateway/requirements.txt /app/gateway/requirements.txt
RUN pip install --no-cache-dir -r /app/gateway/requirements.txt

# Copy shared library
COPY shared/ /app/shared/

# Copy gateway code
COPY gateway/ /app/gateway/

WORKDIR /app/gateway

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
