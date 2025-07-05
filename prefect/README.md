# Prefect Notifications

https://github.com/rpeden/prefect-docker-compose

## Set Prefect Server

Configure prefect to use this server:

```
(.venv) ❱ prefect config set PREFECT_API_URL=https://localhost:4200/api
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

## Creating a Flow

Once you have the block listed, you can create a flow:

```python
from prefect import flow
from typing import Optional

from datetime import datetime

from ntfy_webhook import NtfyWebHook

@flow
def ntfy_default(body: str, subject: Optional[str] = None):  
    """Flow that sends notifications via ntfy"""
    # Load the saved webhook
    ntfy_webhook = NtfyWebHook.load("ntfy-default")  
    # Send notification
    ntfy_webhook.notify(body, subject=subject)
```

## Deploying

You can create a deployment of the flow by creating a deployment, which will push the code to MinIO, a S3-compatible [blob storage](https://docs.prefect.io/v3/how-to-guides/deployments/store-flow-code#blob-storage) system.

https://docs.prefect.io/v3/how-to-guides/deployments/prefect-yaml

```
push:
- prefect_aws.deployments.steps.push_to_s3:
    requires: prefect-aws>=0.3.0
    bucket: my-bucket
    folder: project-name
    credentials: "{{ prefect.blocks.aws-credentials.dev-credentials }}"
```

