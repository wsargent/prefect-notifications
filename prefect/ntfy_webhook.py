from prefect.blocks.notifications import AppriseNotificationBlock
from pydantic import HttpUrl

class NtfyWebHook(AppriseNotificationBlock):
    """
    Enables sending notifications via ntfy.sh service.
    
    Examples:
        Create and save a ntfy webhook:
        ```python
        from main import NtfyWebHook
        
        # Load and use it
        loaded_webhook = await NtfyWebHook.load("ntfy-default")
        await loaded_webhook.notify("Hello from Prefect!", subject="Test")
        ```
    """    
    _block_type_name = "Ntfy Webhook"
    _logo_url = HttpUrl("https://raw.githubusercontent.com/binwiederhier/ntfy/main/web/public/static/images/ntfy.png")
    _documentation_url = HttpUrl("https://docs.ntfy.sh/")

