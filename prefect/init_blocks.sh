#!/bin/bash
# Initialize MinIO blocks first
echo "Initializing MinIO blocks..."
python /app/prefect/init_minio_blocks.py

# Register the ntfy webhook block
echo "Registering ntfy webhook block..."
prefect block register --file /app/prefect/ntfy_webhook.py

# Create the default ntfy webhook block
echo "Creating default ntfy webhook block..."
python -c "
from ntfy_webhook import NtfyWebHook
import asyncio

async def create_block():
    webhook = NtfyWebHook(
        name='ntfy-default',
        url='ntfy://ntfy:80/default'
    )
    await webhook.save('ntfy-default', overwrite=True)
    print('Created ntfy-default block')

asyncio.run(create_block())
"

# Create the failure ntfy webhook block
echo "Creating failure ntfy webhook block..."
python -c "
from ntfy_webhook import NtfyWebHook
import asyncio

async def create_block():
    webhook = NtfyWebHook(
        name='ntfy-failure',
        url='ntfy://ntfy:80/failure'
    )
    await webhook.save('ntfy-failure', overwrite=True)
    print('Created ntfy-failure block')

asyncio.run(create_block())
"