#!/bin/bash
# Initialize MinIO blocks first
echo "Initializing MinIO blocks..."
python /app/prefect/init_minio_blocks.py

# Initialize ntfy webhook blocks
echo "Initializing ntfy webhook blocks..."
python /app/prefect/init_ntfy_blocks.py
