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

# Run proto generation (if needed)
RUN python -c "from walstream_proto.generate import main; main()" || true

# Expose ports
EXPOSE 8000 9091

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
