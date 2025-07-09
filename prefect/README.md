# Prefect Notifications with ntfy

This project demonstrates how to integrate Prefect with the [ntfy.sh](https://ntfy.sh/) notification service. It includes scripts to initialize Prefect blocks, deploy flows, and send notifications.

## Overview

The integration works as follows:

1.  A custom `NtfyWebHook` block is registered with Prefect. This block is a specialized version of the `AppriseNotificationBlock` and is defined in [`ntfy_webhook.py`](ntfy_webhook.py).
2.  The [`init_blocks.sh`](init_blocks.sh) script initializes the necessary Prefect blocks. It first initializes MinIO blocks by running [`init_minio_blocks.py`](init_minio_blocks.py), then registers the `NtfyWebHook` block, and finally creates two instances of this block:
    *   `ntfy-default`: Sends notifications to the `default` topic in ntfy.
    *   `ntfy-failure`: Sends notifications to the `failure` topic in ntfy.
3.  The [`ntfy_flow.py`](ntfy_flow.py) file defines the `ntfy_default` flow. This flow loads the `ntfy-default` block and uses it to send a notification.
4.  The [`init_flow.sh`](init_flow.sh) script deploys all the flows found in the project using `prefect deploy --all`. This makes the `ntfy_default` flow available in the Prefect UI.

## Setup

To get started, you need to have Prefect and Docker installed.

### 1. Configure Prefect Server

Configure your Prefect client to communicate with the local Prefect server running in Docker:

```bash
prefect config set PREFECT_API_URL=http://localhost:4200/api
```

### 2. Initialize Blocks and Flows

The `docker-compose.yml` file is configured to automatically run the initialization scripts. When you start the services with `docker-compose up`, the `prefect-worker` service will execute the following scripts in order:

1.  **[`init_blocks.sh`](init_blocks.sh:1):**
    *   Registers the `NtfyWebHook` block from [`ntfy_webhook.py`](prefect/ntfy_webhook.py:1).
    *   Creates the `ntfy-default` and `ntfy-failure` notification blocks.

2.  **[`init_flow.sh`](init_flow.sh:1):**
    *   Deploys the `ntfy_default` flow from [`ntfy_flow.py`](prefect/ntfy_flow.py:1).

### 3. Sending Notifications

Once the services are running and the flow is deployed, you can trigger the `ntfy_default` flow from the Prefect UI or the command line. This will send a notification to the `default` topic in your ntfy instance.

## Scripts

*   **[`init_blocks.sh`](init_blocks.sh:1):** This script sets up the necessary notification blocks in Prefect. It registers the custom `NtfyWebHook` block and creates two instances, one for default notifications and one for failure notifications.
*   **[`init_flow.sh`](init_flow.sh:1):** This script deploys the Prefect flows. It uses `prefect deploy --all` to find and deploy all flows in the project.
*   **[`ntfy_webhook.py`](ntfy_webhook.py:1):** This Python script defines the custom `NtfyWebHook` block, which inherits from `AppriseNotificationBlock` to provide ntfy integration.
*   **[`ntfy_flow.py`](ntfy_flow.py:1):** This script contains the main Prefect flow, `ntfy_default`, which demonstrates how to load the `NtfyWebHook` block and send a notification.
*   **[`init_minio_blocks.py`](init_minio_blocks.py:1):** This script is responsible for setting up the MinIO storage blocks that Prefect uses for storing flow code.

## ntfy Integration

The integration with ntfy is handled by the `NtfyWebHook` block, which is built on top of Prefect's `AppriseNotificationBlock`. Apprise is a library that supports a wide variety of notification services, including ntfy.

The `url` provided when creating the `NtfyWebHook` block is an Apprise-compatible URL, for example: `ntfy://ntfy:80/default`.

*   `ntfy://`: The protocol for the ntfy service.
*   `ntfy:80`: The hostname and port of the nfy server.
*   `default`: The ntfy topic to which the notification will be sent.
