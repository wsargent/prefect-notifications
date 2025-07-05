# Workflow Agent

This is an agent using Letta that can use Prefect as a workflow engine.

Right now, it can create a deployment to send to a local ntfy instance.

In the future, it will be able to set off a workflow that sends a message back to a letta agent after a period of time.

## Running

```
docker compose up --build
```

