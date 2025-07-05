#!/usr/bin/env python3
"""
Prefect flow for sending notifications via ntfy.
"""
from prefect import flow

from ntfy_webhook import NtfyWebHook
from prefect.logging import get_run_logger
from pathlib import Path

@flow
async def ntfy_default(body: str = "Test", subject: str = "Notification") -> dict:
    """
    Send a notification using the ntfy service.
    
    Args:
        body: The notification message body
        subject: The notification subject/title
        
    Returns:
        dict: Status of the notification
    """

    logger = get_run_logger()
    try:
        # Load the ntfy webhook block and send notification
        ntfy_block = await NtfyWebHook.load("ntfy-default")        

        # Send the notification
        await ntfy_block.notify(body, subject=subject)
        logger.debug("DEBUG level log message from a task.")

        return {
            "status": "success",
            "message": "Notification sent successfully",
            "body": body,
            "subject": subject
        }
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            "status": "error", 
            "error": str(e),
            "body": body,
            "subject": subject
        }
