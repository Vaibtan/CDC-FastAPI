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

# Copy and install control plane dependencies
COPY control/pyproject.toml /app/
RUN pip install --no-cache-dir .

# Copy control plane code
COPY control/app/ /app/app/
COPY control/alembic/ /app/alembic/
COPY control/alembic.ini /app/

# Generate proto files if not already present
RUN python -c "\
import os; \
pb2 = '/app/walstream-proto/walstream_proto/v1/walstream_pb2.py'; \
exec('from walstream_proto.generate import main; main()') if not os.path.exists(pb2) else None \
"

# Expose ports
EXPOSE 8000 9091

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
