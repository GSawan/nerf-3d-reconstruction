FROM python:3.11-slim

# Install system dependencies (COLMAP requires certain libs if compiled from source,
# but usually we use a pre-built binary for deployment)
# For simplicity in this Dockerfile, we will install colmap from apt repository (if available) or assume a lightweight environment.
RUN apt-get update && apt-get install -y \
    colmap \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

# Ensure upload, output, and datasets directories exist
RUN mkdir -p uploads datasets outputs

# Set environment variables
ENV HOST=0.0.0.0
ENV PORT=8000

# Start server
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
