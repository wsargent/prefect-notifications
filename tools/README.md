# Prefect Notifications

## Set Proxmox as Server

Configure prefect to use this server:

```
(.venv) ❱ prefect config set PREFECT_API_URL=https://prefect-proxmox.tail88e86.ts.net/api
```


## NTFY Block

https://docs.prefect.io/v3/concepts/blocks#blocks
https://docs.prefect.io/v3/advanced/custom-blocks 

To register the ntfy webhook block type:

```
(.venv) ❱ prefect block register --file ntfy_webhook.py
```

And then you can create a new block with

```
(.venv) ❱ prefect block create ntfy-webhook
Create a ntfy-webhook block: http://127.0.0.1:4200/blocks/catalog/ntfy-webhook/create
```

This will give you a link to the server URL which will have the ntfy endpoint and topic to use.

## Set up Topic

Because it's using apprise under the hood, you want this https://github.com/caronc/apprise/wiki/Notify_ntfy
to use the various options in the scheme i.e. 

```
Name: "ntfy-alerts"
Webhook URL: ntfys://ntfy-proxmox.mytailnet.ts.net/alerts
```

```
(.venv) ❱ prefect block ls
                                                 Blocks
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ID                                   ┃ Type         ┃ Name            ┃ Slug                         ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ d99fb3cf-a585-4307-8886-894e2fc33d94 │ Ntfy Webhook │ my-ntfy-webhook │ ntfy-webhook/my-ntfy-webhook │
└──────────────────────────────────────┴──────────────┴─────────────────┴──────────────────────────────┘
```

## Running

Once you have the block listed, you can load it and run `notify` on it.

```python
from prefect import flow
from typing import Optional

from datetime import datetime

from ntfy_webhook import NtfyWebHook

@flow
def ntfy_failure(body: str, subject: Optional[str] = None):  
    """Flow that sends notifications via ntfy"""
    # Load the saved webhook
    ntfy_webhook = NtfyWebHook.load("ntfy-failure")  
    # Send notification
    ntfy_webhook.notify(body, subject=subject)

@flow
def ntfy_alerts(body: str, subject: Optional[str] = None):  
    """Flow that sends notifications via ntfy"""
    # Load the saved webhook
    ntfy_webhook = NtfyWebHook.load("ntfy-alerts")  
    # Send notification
    ntfy_webhook.notify(body, subject=subject)


if __name__ == "__main__":    
    ntfy_alerts(f"Alert at {datetime.now()}", "Alert!!!")

    ntfy_failure(f"Failure at {datetime.now()}", "Failure!!!")
```