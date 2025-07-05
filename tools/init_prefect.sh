#!/bin/bash

# Wait for Prefect server to be ready
echo "Waiting for Prefect server to be ready..."
until python -c "
import urllib.request
import json
try:
    with urllib.request.urlopen('http://prefect:4200/api/health') as response:
        data = json.loads(response.read().decode())
        if response.status == 200:
            exit(0)
except Exception as e:
    print(f'Health check failed: {e}')
    exit(1)
" > /dev/null 2>&1; do
    echo "Prefect server not ready yet, waiting 5 seconds..."
    sleep 5
done

echo "Prefect server is ready!"

# Set the API URL
export PREFECT_API_URL=http://prefect:4200/api

# Navigate to tools directory
cd /app/tools

# Register the ntfy webhook block
echo "Registering ntfy webhook block..."
prefect block register --file ntfy_webhook.py

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
    await webhook.save('ntfy-default')
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
    await webhook.save('ntfy-failure')
    print('Created ntfy-failure block')

asyncio.run(create_block())
"

echo "Prefect initialization complete!"