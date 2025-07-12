# Prefect Deployment Scheduling Reference

## Overview
This document provides reference information for scheduling Prefect deployments and flow runs using the Python client.

## Key Classes and Imports

### Required Imports
```python
from prefect.client.orchestration import get_client
from prefect.client.schemas.actions import DeploymentScheduleCreate
from prefect.client.schemas.schedules import (
    IntervalSchedule, 
    CronSchedule, 
    RRuleSchedule, 
    NoSchedule
)
from prefect.states import Scheduled
from datetime import datetime, timedelta, timezone
from uuid import UUID
```

### Client Setup
```python
client = get_client()
```

## Scheduling Approaches

### 1. One-Time Future Runs
For scheduling a single run at a specific future time (e.g., "run in 5 minutes"):

```python
# Schedule a single run 5 minutes from now
future_time = datetime.now(timezone.utc) + timedelta(minutes=5)
flow_run = client.create_flow_run_from_deployment(
    deployment_id=deployment_id,
    state=Scheduled(scheduled_time=future_time)
)
```

**Key Points:**
- Use `create_flow_run_from_deployment()` with `Scheduled` state
- Set `scheduled_time` parameter to the desired future datetime
- Creates a single flow run that will be picked up by the scheduler
- NOT suitable for recurring schedules

### 2. Recurring Deployment Schedules
For ongoing scheduled runs attached to deployments:

#### A. Creating Deployment with Schedules
```python
from prefect.client.schemas.actions import DeploymentScheduleCreate

# Create schedule objects
schedule_create = DeploymentScheduleCreate(
    schedule=IntervalSchedule(interval=timedelta(hours=1)),
    active=True,
    max_scheduled_runs=None,
    parameters={},
    slug="hourly-schedule"
)

# Create deployment with schedules
deployment_id = client.create_deployment(
    flow_id=flow_id,
    name="my-deployment",
    schedules=[schedule_create]
)
```

#### B. Adding Schedules to Existing Deployment
```python
# Add schedules to existing deployment
schedules = [(IntervalSchedule(interval=timedelta(hours=1)), True)]
client.create_deployment_schedules(
    deployment_id=deployment_id,
    schedules=schedules
)
```

## Schedule Types

### 1. IntervalSchedule
For time-based intervals:
```python
IntervalSchedule(
    interval=timedelta(hours=1),  # Required: interval between runs
    anchor_date=datetime.now(timezone.utc),  # Optional: start time
    timezone="America/New_York"  # Optional: timezone
)
```

### 2. CronSchedule
For cron expressions:
```python
CronSchedule(
    cron="0 */6 * * *",  # Every 6 hours
    timezone="America/New_York",
    day_or=True  # How to handle day and day_of_week
)
```

### 3. RRuleSchedule
For complex calendar rules (RFC 5545):
```python
RRuleSchedule(
    rrule="FREQ=DAILY;BYHOUR=9;BYMINUTE=0",
    timezone="America/New_York"
)
```

### 4. NoSchedule
For no scheduling:
```python
NoSchedule()
```

## Important Notes

### Pydantic Models Required
- Cannot pass dictionaries - must use proper Pydantic models
- All schedule types inherit from `PrefectBaseModel`
- Use `DeploymentScheduleCreate` for creating deployment schedules

### One-time vs Recurring
- **One-time scheduling**: Use `create_flow_run_from_deployment()` with `Scheduled` state
- **Recurring scheduling**: Use deployment schedules with schedule types
- **Schedule types are NOT suitable for one-time runs**

### Timezone Handling
- All schedule types support timezone configuration
- Defaults to UTC if not specified
- DST handling varies by schedule type

## Tool Design Recommendation

For MCP tools, consider separate tools for each use case:

1. **`schedule_one_time_run`** - For single future runs using `Scheduled` state
2. **`create_interval_schedule`** - For `IntervalSchedule` 
3. **`create_cron_schedule`** - For `CronSchedule`
4. **`create_rrule_schedule`** - For `RRuleSchedule`
5. **`manage_deployment_schedules`** - For adding/updating deployment schedules

This separation makes the tools more focused and easier to use for specific scheduling needs.

## Handling Late Flow Runs

### Overview
Late flow runs occur when scheduled runs don't execute on time (e.g., work pool is inactive). Prefect provides methods to reschedule or cancel these runs.

### Additional Required Imports for Late Run Management
```python
from prefect.client.schemas.filters import FlowRunFilter, DeploymentFilter
from prefect.client.schemas.sorting import FlowRunSort
from prefect.client.schemas.objects import FlowRun
from prefect.states import Scheduled, StateType
```

### Rescheduling Late Flow Runs

**Strategy**: Delete late flow runs and create new ones with a delay.

```python
async def reschedule_late_flow_runs(
    deployment_name: str, 
    delay: timedelta, 
    most_recent_n: int, 
    delete_remaining: bool = True, 
    states: list[str] | None = None
) -> list[FlowRun]:
    """
    Reschedule late flow runs for a deployment.
    
    Args:
        deployment_name: Name of the deployment
        delay: How much to delay the rescheduled runs
        most_recent_n: Number of recent late runs to reschedule
        delete_remaining: Whether to delete other late runs
        states: List of states to consider (default: ["Late"])
    """
    states = states or ["Late"]
    
    async with get_client() as client:
        # Find late flow runs
        flow_runs = await client.read_flow_runs(
            flow_run_filter=FlowRunFilter(
                state=dict(name=dict(any_=states)),
                expected_start_time=dict(before_=datetime.now(timezone.utc)),
            ),
            deployment_filter=DeploymentFilter(name={'like_': deployment_name}),
            sort=FlowRunSort.START_TIME_DESC,
            limit=most_recent_n if not delete_remaining else None
        )
        
        rescheduled_flow_runs: list[FlowRun] = []
        
        for i, run in enumerate(flow_runs):
            # Delete the late run
            await client.delete_flow_run(flow_run_id=run.id)
            
            # Reschedule only the most recent N runs
            if i < most_recent_n:
                new_run = await client.create_flow_run_from_deployment(
                    deployment_id=run.deployment_id,
                    state=Scheduled(scheduled_time=run.expected_start_time + delay),
                )
                rescheduled_flow_runs.append(new_run)
        
        return rescheduled_flow_runs
```

### Example Usage
```python
# Reschedule the last 3 late runs to run 6 hours later
rescheduled_runs = await reschedule_late_flow_runs(
    deployment_name="healthcheck-storage-test",
    delay=timedelta(hours=6),
    most_recent_n=3,
    delete_remaining=True
)
```

### Cancelling Flow Runs in Bulk

**Strategy**: Find runs in specific states and transition them to Cancelled.

```python
async def list_flow_runs_with_states(states: list[str]) -> list[FlowRun]:
    """Get flow runs in specific states."""
    async with get_client() as client:
        return await client.read_flow_runs(
            flow_run_filter=FlowRunFilter(
                state=FlowRunFilterState(
                    name=FlowRunFilterStateName(any_=states)
                )
            )
        )

async def cancel_flow_runs(flow_runs: list[FlowRun]):
    """Cancel a list of flow runs."""
    async with get_client() as client:
        for flow_run in flow_runs:
            state = flow_run.state.copy(
                update={"name": "Cancelled", "type": StateType.CANCELLED}
            )
            await client.set_flow_run_state(flow_run.id, state, force=True)
```

### Example: Cancel All Active Runs
```python
# Cancel all pending, running, scheduled, or late flows
active_states = ["Pending", "Running", "Scheduled", "Late"]
active_runs = await list_flow_runs_with_states(active_states)
await cancel_flow_runs(active_runs)
```

### Key Points for Late Run Management

1. **Late runs occur when**: Work pools are inactive, resources unavailable, or scheduling delays
2. **Delete before reschedule**: Always delete the late run before creating a new scheduled run
3. **Use filters effectively**: Combine state filters, time filters, and deployment filters
4. **Batch operations**: Handle multiple runs efficiently using async operations
5. **State transitions**: Use `set_flow_run_state()` with `force=True` for bulk cancellations

### Common Late Run Scenarios

- **Inactive work pool**: Deployment scheduled to inactive work pool
- **Resource constraints**: Insufficient workers or resources
- **Infrastructure issues**: Network, storage, or compute problems
- **Dependency failures**: Upstream services or data unavailable

### Best Practices

- Monitor for late runs regularly
- Set up alerts for late run accumulation
- Consider adjusting schedules based on late run patterns
- Use deployment-specific filters to target specific issues
- Implement retry logic with appropriate delays