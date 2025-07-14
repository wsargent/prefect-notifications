#!/usr/bin/env python3
"""
MCP server for doing stuff
"""
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "fastmcp>=2.10.2",
#     "prefect>=3.0.0",
#     "parsedatetime>=2.6"
# ]
# ///

import base64
import json
import traceback
from typing import Any, Dict, Optional
from uuid import UUID

import parsedatetime
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ResourceError
from fastmcp.utilities.logging import get_logger
from prefect import get_client
from prefect.client.schemas.filters import (
    DeploymentFilter,
    DeploymentFilterName,
    DeploymentFilterTags,
    FlowFilter,
    FlowFilterId,
    FlowFilterName,
    FlowFilterTags,
    FlowRunFilter,
    FlowRunFilterId,
    FlowRunFilterName,
    FlowRunFilterState,
    FlowRunFilterStateName,
    FlowRunFilterStateType,
)
from prefect.client.schemas.objects import FlowRun, StateType
from prefect.states import Cancelled

mcp = FastMCP("prefect-mcp")

# Enable debug logging
# os.environ["FASTMCP_LOG_LEVEL"] = "DEBUG"

logger = get_logger(__name__)

# ------------------------------------------------------------------------
# Core Infrastructure for Resources
# ------------------------------------------------------------------------


async def safe_prefect_operation(ctx: Context, operation_name: str, operation_func):
    """Wrapper for safe Prefect API operations with proper error handling."""
    await ctx.debug(f"{operation_name}: starting operation")
    try:
        result = await operation_func()
        await ctx.debug(f"{operation_name}: operation completed successfully")
        return result
    except Exception:
        await ctx.error(f"Failed {operation_name}: {traceback.format_exc()}", operation_name)
        raise ResourceError(f"Prefect API error in {operation_name}: {traceback.format_exc()}")


# ------------------------------------------------------------------------
# Flow Resources
# ------------------------------------------------------------------------

# MCP-compliant cursor-based pagination utilities


def encode_cursor(offset: int, limit: int) -> str:
    """Encode pagination info into an opaque cursor string."""
    cursor_data = {"offset": offset, "limit": limit}
    return base64.b64encode(json.dumps(cursor_data).encode()).decode()


def decode_cursor(cursor: str) -> tuple[int, int]:
    """Decode cursor string back to offset and limit."""
    try:
        cursor_data = json.loads(base64.b64decode(cursor.encode()).decode())
        return cursor_data["offset"], cursor_data["limit"]
    except Exception:
        raise ResourceError("Invalid cursor")


def parse_cursor_from_uri(uri: str) -> str | None:
    """Extract cursor from URI query parameters."""
    if "?cursor=" in uri:
        return uri.split("?cursor=")[1].split("&")[0]
    return None


@mcp.tool()
async def list_flows(
    ctx: Context,
    name: Optional[str] = None,
    tags: Optional[str] = None,
    cursor: Optional[str] = None    
) -> Dict[str, Any]:
    """List and search Prefect flows with filtering and pagination.
    
    Args:
        name: Filter flows by name (partial match).
        tags: Filter flows by tags (comma-separated).
        cursor: Pagination cursor for subsequent pages.        
    """
    await ctx.debug(f"list_flows tool: name={name}, tags={tags}, cursor={cursor}")

    async def operation():
        # Handle pagination
        if cursor:
            offset, cursor_page_size = decode_cursor(cursor)
            page_size_to_use = cursor_page_size
        else:
            offset = 0
            page_size_to_use = 20

        # Build filter based on search parameters
        name_filter = None
        if name:
            name_filter = FlowFilterName(like_=name)

        tags_filter = FlowFilterTags(all_=tags.split(",")) if tags else None

        flow_filter = None
        if name_filter or tags_filter:
            flow_filter = FlowFilter(
                name=name_filter,
                tags=tags_filter,
            )

        async with get_client() as client:
            flows = await client.read_flows(flow_filter=flow_filter, limit=page_size_to_use + 1, offset=offset)

            has_more = len(flows) > page_size_to_use
            if has_more:
                flows = flows[:page_size_to_use]
                next_cursor = encode_cursor(offset + page_size_to_use, page_size_to_use)
            else:
                next_cursor = None

            result = {
                "flows": [flow.model_dump() for flow in flows],
                "count": len(flows),
                "filters": {"name": name, "tags": tags.split(",") if tags else None},
                "has_more": has_more,
            }

            if next_cursor:
                result["nextCursor"] = next_cursor

            return result

    return await safe_prefect_operation(ctx, "list_flows_tool", operation)


@mcp.tool()
async def get_flow_by_id(ctx: Context, flow_id: str) -> Dict[str, Any]:
    """Get a specific flow by its ID.
    
    Args:
        flow_id: The ID of the flow to retrieve.
    """
    await ctx.debug(f"get_flow_by_id tool: flow_id={flow_id}")

    if not flow_id:
        return {"error": "Missing required parameter: flow_id"}

    async def operation():
        async with get_client() as client:
            flow = await client.read_flow(UUID(flow_id))
            return {"flow": flow.model_dump()}

    return await safe_prefect_operation(ctx, "get_flow_by_id_tool", operation)


@mcp.tool()
async def list_deployments(
    ctx: Context,
    name: Optional[str] = None,
    flow_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
    cursor: Optional[str] = None
) -> Dict[str, Any]:
    """List and search Prefect deployments with filtering and pagination.
    
    Args:
        name: Filter deployments by name (partial match).
        flow_id: Filter deployments by flow ID.
        tags: Filter deployments by status.
        cursor: Pagination cursor for subsequent pages.        
    """
    await ctx.debug(f"list_deployments tool: name={name}, flow_id={flow_id}, tags, cursor={cursor}")

    async def operation():
        # Handle pagination
        if cursor:
            offset, cursor_page_size = decode_cursor(cursor)
            page_size_to_use = cursor_page_size
        else:
            offset = 0
            page_size_to_use = 20

        # Build filter based on search parameters
        deployment_filter = None
        flow_filter = None
        filter_dict = {}

        if name:
            filter_dict["name"] = DeploymentFilterName(any_=[name])        
        if tags:
            filter_dict["tags"] = DeploymentFilterTags(any_=tags)

        if filter_dict:
            deployment_filter = DeploymentFilter(**filter_dict)

        if flow_id:
            flow_filter = FlowFilter(id=FlowFilterId(any_=[UUID(hex=flow_id)]))           

        async with get_client() as client:
            deployments = await client.read_deployments(flow_filter=flow_filter, deployment_filter=deployment_filter, limit=page_size_to_use + 1, offset=offset)

            has_more = len(deployments) > page_size_to_use
            if has_more:
                deployments = deployments[:page_size_to_use]
                next_cursor = encode_cursor(offset + page_size_to_use, page_size_to_use)
            else:
                next_cursor = None
           
            # Build deployment list with flow names
            deployment_list = []
            for deployment in deployments:
                deployment_info = deployment.model_dump()
                deployment_list.append(deployment_info)

            result = {
                "deployments": deployment_list, 
                "count": len(deployment_list),
                "has_more": has_more
            }

            if next_cursor:
                result["nextCursor"] = next_cursor

            return result

    return await safe_prefect_operation(ctx, "list_deployments_tool", operation)


@mcp.tool()
async def get_deployment_by_id(ctx: Context, deployment_id: str) -> Dict[str, Any]:
    """Get a specific deployment by its ID.
    
    Args:
        deployment_id: The ID of the deployment to retrieve.
    """
    await ctx.debug(f"get_deployment_by_id tool: deployment_id={deployment_id}")

    if not deployment_id:
        return {"error": "Missing required parameter: deployment_id"}

    async def operation():
        async with get_client() as client:
            deployment = await client.read_deployment(UUID(deployment_id))

            flow_name = "unknown"
            try:
                flow = await client.read_flow(deployment.flow_id)
                flow_name = flow.name
            except Exception:
                pass

            deployment_info = deployment.model_dump()
            deployment_info["flow_name"] = flow_name

            return {"deployment": deployment_info}

    return await safe_prefect_operation(ctx, "get_deployment_by_id_tool", operation)


@mcp.tool()
async def get_deployment_parameters(
    ctx: Context, 
    deployment_id: Optional[str] = None,
    name: Optional[str] = None
) -> Dict[str, Any]:
    """Get detailed parameter information for a specific deployment.
    
    Args:
        deployment_id (str, optional): The ID of the deployment to get parameters for.
        name (str, optional): The name of the deployment in format 'flow_name/deployment_name'.
    """
    await ctx.debug(f"get_deployment_parameters tool: deployment_id={deployment_id}, name={name}")

    if not deployment_id and not name:
        return {"error": "Must provide either deployment_id or name parameter"}

    async def operation():
        async with get_client() as client:
            # Handle both name and UUID formats
            if name:
                # Parse flow_name/deployment_name format
                if "/" not in name:
                    return {"error": "Name must be in format 'flow_name/deployment_name'"}
                               
                deployment = await client.read_deployment_by_name(name)
                
                if not deployment:
                    return {"error": f"Deployment not found: {name}"}
            else:                
                deployment = await client.read_deployment(UUID(deployment_id))

            parameter_schema = deployment.parameter_openapi_schema or {}
            default_parameters = deployment.parameters or {}

            parameters_info = {}

            if "properties" in parameter_schema:
                for param_name, param_info in parameter_schema["properties"].items():
                    parameters_info[param_name] = {
                        "type": param_info.get("type", "unknown"),
                        "title": param_info.get("title", param_name),
                        "description": param_info.get("description", "No description available"),
                        "default": param_info.get("default", default_parameters.get(param_name)),
                        "required": param_name in parameter_schema.get("required", []),
                        "position": param_info.get("position"),
                        "examples": param_info.get("examples", []),
                    }

            return {
                "deployment_id": str(deployment.id),
                "deployment_name": deployment.name,
                "flow_id": deployment.flow_id,
                "description": deployment.description or "No description",
                "parameters": parameters_info,
                "default_parameters": default_parameters,
                "required_parameters": parameter_schema.get("required", []),
                "parameter_count": len(parameters_info),
            }

    return await safe_prefect_operation(ctx, "get_deployment_parameters_tool", operation)


@mcp.tool()
async def list_flow_runs(
    ctx: Context,
    name: Optional[str] = None,
    flow_id: Optional[str] = None,
    deployment_id: Optional[str] = None,
    state_type: Optional[str] = None,
    state_name: Optional[str] = None,
    cursor: Optional[str] = None
) -> Dict[str, Any]:
    """List and search Prefect flow runs with filtering and pagination.
    
    Args:
        name: Filter flow runs by name (partial match).
        flow_id: Filter flow runs by flow ID.
        deployment_id: Filter flow runs by deployment ID.
        state_type: Filter flow runs by state type (COMPLETED, FAILED, etc.).
        state_name: Filter flow runs by state name.
        cursor: Pagination cursor for subsequent pages.
    """
    await ctx.debug(f"list_flow_runs tool: name={name}, flow_id={flow_id}, deployment_id={deployment_id}, state_type={state_type}, state_name={state_name}, cursor={cursor}")

    async def operation():
        # Handle pagination
        if cursor:
            offset, cursor_page_size = decode_cursor(cursor)
            page_size_to_use = cursor_page_size
        else:
            offset = 0
            page_size_to_use = 20

        # Build filter based on search parameters
        flow_run_filter = None

        if name or flow_id or deployment_id or state_type or state_name:
            filter_kwargs = {}

            if name:
                filter_kwargs["name"] = FlowRunFilterName(like_=name)
            if flow_id:
                filter_kwargs["flow_id"] = FlowRunFilterId(any_=[UUID(flow_id)])
            if deployment_id:
                filter_kwargs["deployment_id"] = FlowRunFilterId(any_=[UUID(deployment_id)])

            if state_type or state_name:
                state_filter = FlowRunFilterState()
                if state_type:
                    state_filter.type = FlowRunFilterStateType(any_=[StateType[state_type.upper()]])
                if state_name:
                    state_filter.name = FlowRunFilterStateName(any_=[state_name])
                filter_kwargs["state"] = state_filter

            flow_run_filter = FlowRunFilter(**filter_kwargs)

        async with get_client() as client:
            flow_runs = await client.read_flow_runs(flow_run_filter=flow_run_filter, limit=page_size_to_use + 1, offset=offset)

            has_more = len(flow_runs) > page_size_to_use
            if has_more:
                flow_runs = flow_runs[:page_size_to_use]
                next_cursor = encode_cursor(offset + page_size_to_use, page_size_to_use)
            else:
                next_cursor = None

            result = {
                "flow_runs": [flow_run.model_dump() for flow_run in flow_runs],
                "count": len(flow_runs),
                "filters": {"name": name, "flow_id": flow_id, "deployment_id": deployment_id, "state_type": state_type, "state_name": state_name},
                "has_more": has_more,
            }

            if next_cursor:
                result["nextCursor"] = next_cursor

            return result

    return await safe_prefect_operation(ctx, "list_flow_runs_tool", operation)


@mcp.tool()
async def get_flow_run_by_id(ctx: Context, flow_run_id: str) -> Dict[str, Any]:
    """Get a specific flow run by its ID.
    
    Args:
        flow_run_id: The ID of the flow run to retrieve.
    """
    await ctx.debug(f"get_flow_run_by_id tool: flow_run_id={flow_run_id}")

    if not flow_run_id:
        return {"error": "Missing required parameter: flow_run_id"}

    async def operation():
        async with get_client() as client:
            flow_run = await client.read_flow_run(UUID(flow_run_id))
            return {"flow_run": flow_run.model_dump()}

    return await safe_prefect_operation(ctx, "get_flow_run_by_id_tool", operation)

@mcp.tool()
async def bulk_cancel_flow_runs(ctx: Context):
    async def list_flow_runs_with_states(states: list[str]) -> list[FlowRun]:
        async with get_client() as client:
            return await client.read_flow_runs(
                flow_run_filter=FlowRunFilter(
                    state=FlowRunFilterState(
                        name=FlowRunFilterStateName(any_=states)
                    )
                )
            )
    
    async def cancel_flow_runs(flow_runs: list[FlowRun]):
        async with get_client() as client:
            for flow_run in flow_runs:
                if flow_run.state:
                    state = flow_run.state.model_copy(
                        update={"name": "Cancelled", "type": StateType.CANCELLED}
                    )
                    await client.set_flow_run_state(flow_run.id, state, force=True)

    await ctx.debug("bulk_cancel_flow_runs entry")

    states = ["Pending", "Running", "Scheduled", "Late"]
    flow_runs = await list_flow_runs_with_states(states)

    while flow_runs:
        print(f"Cancelling {len(flow_runs)} flow runs")
        await cancel_flow_runs(flow_runs)
        flow_runs = await list_flow_runs_with_states(states)

    await ctx.debug("bulk_cancel_flow_runs exit")
    result = {"success": True}
    return result

@mcp.tool()
async def cancel_flow_run(ctx: Context, flow_run_id: str) -> Dict[str, Any]:
    """Cancel a flow run.

    Args:
        flow_run_id: ID of the flow run to cancel.
    """
    await ctx.debug(f"cancel_flow_run entry: flow_run_id={flow_run_id}")
    if not flow_run_id:
        result = {"error": "Missing required argument: flow_run_id"}
        await ctx.debug(f"cancel_flow_run exit with validation error: result={result}")
        return result

    async with get_client() as client:
        try:
            cancel_result = await client.set_flow_run_state(
                flow_run_id=UUID(flow_run_id),
                state=Cancelled(),
            )
            result = {"success": True, "result": str(cancel_result)}
            await ctx.debug("cancel_flow_run exit: successfully cancelled flow run")
            return result
        except Exception:
            await ctx.error(f"Failed to cancel flow run: {traceback.format_exc()}", "cancel_flow_run")
            result = {"error": f"Failed to cancel flow run: {traceback.format_exc()}"}
            await ctx.debug(f"cancel_flow_run exit with error: result={result}")
            return result



@mcp.tool()
async def create_flow_run_from_deployment(
    ctx: Context,
    deployment_id: Optional[str] = None,
    name: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    scheduled_time: Optional[str] = None,   
    timeout: int = 0,
) -> Dict[str, Any]:
    """Create a new flow run for the specified deployment.

    Args:
        deployment_id (str, optional): ID of the deployment, should be a UUID.  This take priority over the name.
        name (str, optional): Optional name for the flow run in the format "flow-name/deployment-name", use this if you don't have deployment_id
        parameters: Dictionary with parameters for the flow run (optional).        
        scheduled_time: scheduled time, can be relative "5 minutes from now"
        timeout: Timeout in seconds, 0 means no waiting for completion (default 0).
    """
    await ctx.debug(f"create_flow_run_from_deployment entry: deployment_id={deployment_id}, parameters={parameters}, name={name}, scheduled_time={scheduled_time} timeout={timeout}")
    from prefect.deployments import run_deployment

    try:
        name_or_uuid: str | UUID = ""
        if deployment_id:
            name_or_uuid = UUID(hex=deployment_id)
        elif name:
            name_or_uuid = name
        else:
            raise ValueError("Neither deployment_id nor name were provided as inputs")
            
        scheduled_time_datetime = None
        if scheduled_time:            
            from datetime import datetime

            # Get system timezone the reliable way
            system_tz = datetime.now().astimezone().tzinfo

            cal = parsedatetime.Calendar()
            scheduled_time_datetime, parse_status = cal.parseDT(scheduled_time, tzinfo = system_tz)            
            await ctx.debug(f"create_flow_run_from_deployment: scheduled_time_datetime = {scheduled_time_datetime}, parse_status = {parse_status}")

        # pylance is wrong, using await is correct here but it doesn't understand @sync_compatible.
        run_result = await run_deployment(  # type: ignore
            name=name_or_uuid, 
            parameters=parameters or {}, 
            scheduled_time=scheduled_time_datetime,
            timeout=timeout, 
            flow_run_name=name
        )

        result = {"flow_run_id": str(run_result)}
        await ctx.debug(f"create_flow_run_from_deployment exit: flow_run_id={run_result}")
        return result
    except Exception:
        await ctx.error(f"Failed to create flow run: {traceback.format_exc()}", "create_flow_run_from_deployment")
        result = {"error": f"Failed to create flow run: {traceback.format_exc()}"}
        await ctx.debug(f"create_flow_run_from_deployment exit with error: result={result}")
        return result

if __name__ == "__main__":
    # Configure for I/O-bound workloads (Prefect API calls)
    uvicorn_config = {
        "workers": 1,  # Single worker - async handles concurrency better for I/O
        "limit_concurrency": 500,  # High concurrent connections for I/O operations
        "backlog": 8192,  # Large backlog for many pending connections
        "timeout_keep_alive": 30,  # Longer keep-alive for connection reuse
        "timeout_graceful_shutdown": 30,  # Graceful shutdown timeout
    }
    
    mcp.run(
        transport="sse",
        host="localhost", 
        port=8000, 
        log_level="DEBUG",
        uvicorn_config=uvicorn_config
    )
