FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*

# Copy and install Python deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p data/raw data/processed data/synthetic models

# Expose FastAPI port
EXPOSE 8000

# Startup: if no trained models, run the full pipeline first then start API
CMD ["sh", "-c", "\
  if [ ! -f models/module_a_lot_iso.joblib ]; then \
    echo '=== No trained models found. Running pipeline...' && \
    python scripts/run_pipeline.py && \
    echo '=== Pipeline complete. Starting API...'; \
  else \
    echo '=== Models found. Starting API...'; \
  fi && \
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 \
"]
