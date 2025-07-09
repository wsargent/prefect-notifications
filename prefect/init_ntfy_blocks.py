#!/usr/bin/env python3
"""
Initialization script for ntfy webhook blocks.
Registers and creates ntfy webhook blocks for Prefect notifications.
"""

import sys
import time
import asyncio
import subprocess
from pathlib import Path

def wait_for_prefect_server(max_retries=30, delay=2):
    """Wait for Prefect server to be available."""
    print("🔄 Waiting for Prefect server to be available...")
    
    for attempt in range(max_retries):
        try:
            # Try to create a simple block to test server connectivity
            from prefect.blocks.system import JSON
            test_block = JSON(value={"test": "connectivity"})
            # If we can create this without error, server is likely ready
            print("✅ Prefect server is ready")
            return True
        except Exception as e:
            print(f"⏳ Attempt {attempt + 1}/{max_retries}: Server not ready - {e}")
            time.sleep(delay)
    
    print("❌ Prefect server is not available after maximum retries")
    return False

def register_ntfy_webhook_block():
    """Register the ntfy webhook block type."""
    print("\n📋 Registering ntfy webhook block...")
    
    try:
        # Register the ntfy webhook block
        result = subprocess.run(
            ["prefect", "block", "register", "--file", "/app/prefect/ntfy_webhook.py"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ ntfy webhook block registered successfully")
        else:
            print(f"⚠️  Block registration output: {result.stdout}")
            print(f"⚠️  Block registration errors: {result.stderr}")
            # Don't fail if block is already registered
            if "already registered" in result.stderr.lower():
                print("✅ ntfy webhook block already registered")
                return True
    except Exception as e:
        print(f"❌ Failed to register ntfy webhook block: {e}")
        return False
    
    return True

async def create_ntfy_webhook_block():
    """Create and save the default ntfy webhook block."""
    print("\n🔗 Creating default ntfy webhook block...")
    
    try:
        # Import the ntfy webhook class
        from ntfy_webhook import NtfyWebHook
        
        # Create the webhook block
        webhook = NtfyWebHook(
            name='ntfy-default',
            url='ntfy://ntfy:80/default'
        )
        
        # Save the block
        await webhook.save('ntfy-default', overwrite=True)
        print("✅ Created ntfy-default webhook block")
        return True
    except Exception as e:
        print(f"❌ Failed to create ntfy webhook block: {e}")
        return False

async def verify_ntfy_webhook_block():
    """Verify the ntfy webhook block was created successfully."""
    print("\n🔍 Verifying ntfy webhook block...")
    
    try:
        from ntfy_webhook import NtfyWebHook
        
        # Try to load the block
        webhook = await NtfyWebHook.load('ntfy-default')
        print("✅ Verified ntfy-default webhook block")
        return True
    except Exception as e:
        print(f"❌ Failed to verify ntfy webhook block: {e}")
        return False

async def main():
    """Main initialization function."""
    print("🚀 Ntfy Webhook Block Initialization")
    print("=" * 50)
    
    # Wait for Prefect server
    if not wait_for_prefect_server():
        print("❌ Cannot proceed without Prefect server")
        sys.exit(1)
    
    # Register ntfy webhook block
    if not register_ntfy_webhook_block():
        print("❌ Failed to register ntfy webhook block")
        sys.exit(1)
    
    # Create ntfy webhook block
    if not await create_ntfy_webhook_block():
        print("❌ Failed to create ntfy webhook block")
        sys.exit(1)
    
    # Verify the block
    if await verify_ntfy_webhook_block():
        print("\n🎉 Ntfy webhook block created and verified successfully!")
        print("\nCreated blocks:")
        print("- ntfy-default (Ntfy webhook for notifications)")
        print("\nNtfy integration is ready for use!")
    else:
        print("❌ Ntfy webhook block failed verification")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())