#!/usr/bin/env python3
"""
Initialization script for MinIO blocks and storage configuration.
Creates and registers all MinIO-related blocks with Prefect server.
"""

import sys
import time
import asyncio
from prefect import get_client
from prefect.blocks.core import Block
from prefect_aws import AwsCredentials
from prefect_aws.s3 import S3Bucket

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

def register_block_types():
    """Register required block types with Prefect."""
    print("\n📋 Registering block types...")
    
    try:
        # Register prefect-aws block types
        import subprocess
        result = subprocess.run(
            ["prefect", "block", "register", "-m", "prefect_aws"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ prefect-aws blocks registered successfully")
        else:
            print(f"⚠️  Block registration output: {result.stdout}")
            print(f"⚠️  Block registration errors: {result.stderr}")
    except Exception as e:
        print(f"❌ Failed to register block types: {e}")
        return False
    
    return True

def create_minio_credentials():
    """Create and save MinIO credentials block."""
    print("\n🔑 Creating MinIO credentials block...")
    
    try:
        # Create MinIO credentials using AWS credentials block
        minio_credentials = AwsCredentials(
            aws_access_key_id="minioadmin",
            aws_secret_access_key="minioadmin123",
            region_name="us-east-1"
        )
        
        # Configure endpoint for MinIO
        minio_credentials.aws_client_parameters = {
            "endpoint_url": "http://minio:9000"
        }
        
        # Save the credentials block
        minio_credentials.save("minio-credentials", overwrite=True)
        print("✅ MinIO credentials block created: minio-credentials")
        return minio_credentials
    except Exception as e:
        print(f"❌ Failed to create MinIO credentials: {e}")
        return None

def create_s3_bucket_blocks(credentials):
    """Create and save MinIO S3 bucket blocks."""
    print("\n🪣 Creating MinIO S3 bucket blocks...")
    
    # Define buckets to create
    buckets = [
        ("prefect-flows", "Prefect flows storage"),
        ("prefect-artifacts", "Prefect artifacts storage"), 
        ("prefect-results", "Prefect results storage")
    ]
    
    created_blocks = []
    
    for bucket_name, description in buckets:
        try:
            # Create S3 bucket block
            s3_bucket = S3Bucket(
                bucket_name=bucket_name,
                credentials=credentials
            )
            
            # Save the block
            block_name = f"minio-{bucket_name}"
            s3_bucket.save(block_name, overwrite=True)
            created_blocks.append(block_name)
            print(f"✅ Created S3 bucket block: {block_name}")
        except Exception as e:
            print(f"❌ Failed to create S3 bucket block {bucket_name}: {e}")
    
    return created_blocks

def create_result_storage_blocks(credentials):
    """Create result and artifacts storage blocks."""
    print("\n💾 Creating result storage blocks...")
    
    try:
        # Create result storage bucket block
        result_storage = S3Bucket(
            bucket_name="prefect-results",
            credentials=credentials,
            folder="flow-results"
        )
        result_storage.save("minio-result-storage", overwrite=True)
        print("✅ Result storage block created: minio-result-storage")
        
        # Create artifacts storage bucket block
        artifacts_storage = S3Bucket(
            bucket_name="prefect-artifacts",
            credentials=credentials,
            folder="flow-artifacts"
        )
        artifacts_storage.save("minio-artifacts-storage", overwrite=True)
        print("✅ Artifacts storage block created: minio-artifacts-storage")
        
        return True
    except Exception as e:
        print(f"❌ Failed to create result storage blocks: {e}")
        return False

def verify_blocks():
    """Verify that all blocks were created successfully."""
    print("\n🔍 Verifying created blocks...")
    
    expected_blocks = [
        "minio-credentials",
        "minio-prefect-flows",
        "minio-prefect-artifacts", 
        "minio-prefect-results",
        "minio-result-storage",
        "minio-artifacts-storage"
    ]
    
    verified_blocks = []
    
    for block_name in expected_blocks:
        try:
            # Try to load each block
            if "credentials" in block_name:
                block = AwsCredentials.load(block_name)
            else:
                block = S3Bucket.load(block_name)
            
            verified_blocks.append(block_name)
            print(f"✅ Verified block: {block_name}")
        except Exception as e:
            print(f"❌ Failed to verify block {block_name}: {e}")
    
    print(f"\n📊 Block verification complete: {len(verified_blocks)}/{len(expected_blocks)} blocks verified")
    return len(verified_blocks) == len(expected_blocks)

def main():
    """Main initialization function."""
    print("🚀 MinIO Blocks Initialization")
    print("=" * 50)
    
    # Wait for Prefect server
    if not wait_for_prefect_server():
        print("❌ Cannot proceed without Prefect server")
        sys.exit(1)
    
    # Register block types
    if not register_block_types():
        print("❌ Failed to register block types")
        sys.exit(1)
    
    # Create credentials
    credentials = create_minio_credentials()
    if not credentials:
        print("❌ Failed to create MinIO credentials")
        sys.exit(1)
    
    # Create S3 bucket blocks
    bucket_blocks = create_s3_bucket_blocks(credentials)
    if not bucket_blocks:
        print("❌ Failed to create S3 bucket blocks")
        sys.exit(1)
    
    # Create result storage blocks
    if not create_result_storage_blocks(credentials):
        print("❌ Failed to create result storage blocks")
        sys.exit(1)
    
    # Verify all blocks
    if verify_blocks():
        print("\n🎉 All MinIO blocks created and verified successfully!")
        print("\nCreated blocks:")
        print("- minio-credentials (AWS credentials for MinIO)")
        print("- minio-prefect-flows (S3 bucket for flow code)")
        print("- minio-prefect-artifacts (S3 bucket for artifacts)")
        print("- minio-prefect-results (S3 bucket for results)")
        print("- minio-result-storage (Configured result storage)")
        print("- minio-artifacts-storage (Configured artifacts storage)")
        print("\nMinIO integration is ready for use!")
    else:
        print("❌ Some blocks failed verification")
        sys.exit(1)

if __name__ == "__main__":
    main()