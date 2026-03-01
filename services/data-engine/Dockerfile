FROM python:3.11-slim

WORKDIR /app

# Install data-engine dependencies
COPY services/data-engine/requirements.txt /app/data-engine/requirements.txt
RUN pip install --no-cache-dir -r /app/data-engine/requirements.txt

# Install test-harness dependencies
COPY services/test-harness/requirements.txt /app/test-harness/requirements.txt
RUN pip install --no-cache-dir -r /app/test-harness/requirements.txt || true

# Copy test-harness code (imported by data-engine)
COPY services/test-harness/ /app/test-harness/

# Copy data-engine code
COPY services/data-engine/ /app/data-engine/

# Copy baked-in promptsets
COPY data/promptsets/ /app/data/promptsets/

WORKDIR /app/data-engine

ENV PYTHONPATH=/app
ENV DATA_DIR=/app/data/promptsets

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
