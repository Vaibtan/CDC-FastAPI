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

# Generate proto files if not already present
RUN python -c "\
import os; \
pb2 = '/app/walstream-proto/walstream_proto/v1/walstream_pb2.py'; \
exec('from walstream_proto.generate import main; main()') if not os.path.exists(pb2) else None \
"

# Expose ports
EXPOSE 50051 9092

CMD ["python", "server.py"]
