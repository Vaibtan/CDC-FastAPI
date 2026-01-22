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

# Install replayer dependencies
COPY replayer/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy replayer code
COPY replayer/ /app/

# Run proto generation (if needed)
RUN python -c "from walstream_proto.generate import main; main()" || true

# Expose ports
EXPOSE 50051 9092

CMD ["python", "server.py"]
