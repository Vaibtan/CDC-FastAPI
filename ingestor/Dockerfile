FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy shared proto package first
COPY walstream-proto/ /app/walstream-proto/

# Install proto package
RUN pip install --no-cache-dir /app/walstream-proto/

# Install ingestor dependencies
COPY ingestor/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt || true

# Copy ingestor code
COPY ingestor/ /app/

# Run proto generation (if needed)
RUN python -c "from walstream_proto.generate import main; main()" || true

CMD ["python", "ingestor.py"]
