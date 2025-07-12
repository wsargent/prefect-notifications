#!/usr/bin/env python3
"""
MCP server for doing stuff
"""
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "fastmcp>=2.10.2",
#     "prefect>=3.0.0"
# ]
# ///

from typing import Any, Dict
from typing import Optional

import os
import base64
import json

from fastmcp.utilities.logging import get_logger
from fastmcp import FastMCP, Context
from fastmcp.exceptions import ResourceError
from prefect import get_client
from prefect.client.schemas.filters import (
    DeploymentFilter,
    DeploymentFilterName,
    FlowFilter,
    FlowFilterName,
    FlowFilterTags,
    FlowRunFilter,
    FlowRunFilterId,
    FlowRunFilterState,
    FlowRunFilterStateName,
    FlowRunFilterStateType,
)
from prefect.client.schemas.objects import StateType
from prefect.states import Cancelled
import traceback

from uuid import UUID


mcp = FastMCP("prefect-mcp")

# Enable debug logging
os.environ["FASTMCP_LOG_LEVEL"] = "DEBUG"

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
    except Exception as e:
        await ctx.error(f"Failed {operation_name}: {str(e)}", operation_name)
        raise ResourceError(f"Prefect API error in {operation_name}: {str(e)}")


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


def get_request_uri(ctx: Context) -> str | None:
    """Try to get the original request URI with query parameters."""
    try:
        # Try to access the original URI from the request context
        request = ctx.request_context.request
        if request and hasattr(request, "uri"):
            return str(request.uri)
        elif request and hasattr(request, "method") and hasattr(request, "params"):
            # This is an MCP request - try to get the URI from params
            if hasattr(request.params, "uri"):
                return str(request.params.uri)
    except Exception:
        pass
    return None


@mcp.resource("prefect://flows", name="list_flows", description="List and search flows with query parameters")
async def list_flows_resource(ctx: Context):
    """List all available Prefect flows with filtering and cursor-based pagination.

    Supports:
    - prefect://flows - All flows, first page
    - prefect://flows?cursor=<cursor> - Subsequent pages
    - prefect://flows?query=<term> - Filter by name
    - prefect://flows?tags=<tag1,tag2> - Filter by tags
    - prefect://flows?query=<term>&cursor=<cursor> - Filtered + paginated
    """
    await ctx.debug("list_flows_resource: starting")

    # Parse query parameters from URI
    cursor = None
    query = None
    name = None
    tags = None

    try:
        original_uri = get_request_uri(ctx)
        if original_uri and "?" in original_uri:
            # Parse query parameters manually
            query_part = original_uri.split("?")[1]
            params = {}
            for param in query_part.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    params[key] = value

            cursor = params.get("cursor")
            query = params.get("query")
            name = params.get("name")
            tags = params.get("tags")
            await ctx.debug(f"Found params - cursor: {cursor}, query: {query}, name: {name}, tags: {tags}")
    except Exception as e:
        await ctx.debug(f"Could not parse URI parameters: {e}")

    async def operation():
        # Handle pagination
        page_size = 20
        if cursor:
            # Parse cursor for pagination
            offset, cursor_page_size = decode_cursor(cursor)
            page_size = cursor_page_size  # Use page size from cursor
        else:
            # First page
            offset = 0

        # Build filter based on search parameters
        name_filter = None
        if query:
            name_filter = FlowFilterName(like_=query)
        elif name:
            name_filter = FlowFilterName(any_=[name])

        tags_filter = FlowFilterTags(all_=tags.split(",")) if tags else None

        flow_filter = None
        if name_filter or tags_filter:
            flow_filter = FlowFilter(
                name=name_filter,
                tags=tags_filter,
            )

        async with get_client() as client:
            # Fetch one extra to determine if there are more results
            flows = await client.read_flows(flow_filter=flow_filter, limit=page_size + 1, offset=offset)

            # Check if there are more results
            has_more = len(flows) > page_size
            if has_more:
                flows = flows[:page_size]  # Remove the extra item
                next_cursor = encode_cursor(offset + page_size, page_size)
            else:
                next_cursor = None

            result = {
                "flows": [flow.model_dump() for flow in flows],
                "count": len(flows),
                "filters": {"query": query, "name": name, "tags": tags.split(",") if tags else None},
                "pagination": {"offset": offset, "page_size": page_size, "has_more": has_more},
            }

            # Add nextCursor if more results exist (MCP-compliant)
            if next_cursor:
                result["nextCursor"] = next_cursor

            return result

    return await safe_prefect_operation(ctx, "list_flows", operation)


@mcp.resource("prefect://flows/{id}")
async def get_flow_by_id_resource(ctx: Context, id: str):
    """Get a specific flow by its ID."""
    await ctx.debug(f"get_flow_by_id_resource: id={id}")

    if not id:
        raise ResourceError("Missing required parameter: id")

    async def operation():
        async with get_client() as client:
            flow = await client.read_flow(UUID(id))
            return {"flow": flow.model_dump()}

    return await safe_prefect_operation(ctx, "get_flow_by_id", operation)


# ------------------------------------------------------------------------
# Deployment Resources (Phase 2)
# ------------------------------------------------------------------------


@mcp.resource("prefect://deployments", name="list_deployments", description="List and search deployments with query parameters")
async def list_deployments_resource(ctx: Context):
    """List all available Prefect deployments with filtering and cursor-based pagination.

    Supports:
    - prefect://deployments - All deployments, first page
    - prefect://deployments?cursor=<cursor> - Subsequent pages
    - prefect://deployments?query=<term> - Filter by name
    - prefect://deployments?flow_id=<id> - Filter by flow ID
    - prefect://deployments?status=<status> - Filter by status
    """
    await ctx.debug("list_deployments_resource: starting")

    # Parse query parameters from URI
    cursor = None
    query = None
    flow_id = None
    status = None

    try:
        original_uri = get_request_uri(ctx)
        if original_uri and "?" in original_uri:
            # Parse query parameters manually
            query_part = original_uri.split("?")[1]
            params = {}
            for param in query_part.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    params[key] = value

            cursor = params.get("cursor")
            query = params.get("query")
            flow_id = params.get("flow_id")
            status = params.get("status")
            await ctx.debug(f"Found params - cursor: {cursor}, query: {query}, flow_id: {flow_id}, status: {status}")
    except Exception as e:
        await ctx.debug(f"Could not parse URI parameters: {e}")

    async def operation():
        # Handle pagination
        page_size = 20
        if cursor:
            # Parse cursor for pagination
            offset, cursor_page_size = decode_cursor(cursor)
            page_size = cursor_page_size  # Use page size from cursor
        else:
            # First page
            offset = 0

        # Build filter based on search parameters
        deployment_filter = None
        filter_dict = {}

        if query:
            filter_dict["name"] = {"like_": query}
        if flow_id:
            filter_dict["flow_id"] = {"equals": flow_id}
        if status:
            filter_dict["status"] = {"equals": status}

        if filter_dict:
            deployment_filter = DeploymentFilter(**filter_dict)

        async with get_client() as client:
            # Fetch one extra to determine if there are more results
            deployments = await client.read_deployments(deployment_filter=deployment_filter, limit=page_size + 1, offset=offset)

            # Check if there are more results
            has_more = len(deployments) > page_size
            if has_more:
                deployments = deployments[:page_size]  # Remove the extra item
                next_cursor = encode_cursor(offset + page_size, page_size)
            else:
                next_cursor = None

            # Enhance deployment data with flow names
            deployment_list = []
            for deployment in deployments:
                # Get flow name from flow_id
                flow_name = "unknown"
                try:
                    flow = await client.read_flow(deployment.flow_id)
                    flow_name = flow.name
                except:
                    pass  # If we can't get flow name, use unknown

                deployment_info = deployment.model_dump()
                deployment_info["flow_name"] = flow_name
                deployment_list.append(deployment_info)

            result = {"deployments": deployment_list, "count": len(deployment_list), "filters": {"query": query, "flow_id": flow_id, "status": status}, "pagination": {"offset": offset, "page_size": page_size, "has_more": has_more}}

            # Add nextCursor if more results exist (MCP-compliant)
            if next_cursor:
                result["nextCursor"] = next_cursor

            return result

    return await safe_prefect_operation(ctx, "list_deployments", operation)


@mcp.resource("prefect://deployments/{id}")
async def get_deployment_by_id_resource(ctx: Context, id: str):
    """Get a specific deployment by its ID."""
    await ctx.debug(f"get_deployment_by_id_resource: id={id}")

    if not id:
        raise ResourceError("Missing required parameter: id")

    async def operation():
        async with get_client() as client:
            deployment = await client.read_deployment(UUID(id))

            # Get flow name from flow_id
            flow_name = "unknown"
            try:
                flow = await client.read_flow(deployment.flow_id)
                flow_name = flow.name
            except:
                pass  # If we can't get flow name, use unknown

            deployment_info = deployment.model_dump()
            deployment_info["flow_name"] = flow_name

            return {"deployment": deployment_info}

    return await safe_prefect_operation(ctx, "get_deployment_by_id", operation)


# ------------------------------------------------------------------------
# Flow Run Resources (Phase 3)
# ------------------------------------------------------------------------


@mcp.resource("prefect://flow-runs", name="list_flow_runs", description="List and search flow runs with query parameters")
async def list_flow_runs_resource(ctx: Context):
    """List all available Prefect flow runs with filtering and cursor-based pagination.

    Supports:
    - prefect://flow-runs - All flow runs, first page
    - prefect://flow-runs?cursor=<cursor> - Subsequent pages
    - prefect://flow-runs?flow_id=<id> - Filter by flow ID
    - prefect://flow-runs?deployment_id=<id> - Filter by deployment ID
    - prefect://flow-runs?state_type=<type> - Filter by state type (COMPLETED, FAILED, etc.)
    - prefect://flow-runs?state_name=<name> - Filter by state name
    """
    await ctx.debug("list_flow_runs_resource: starting")

    # Parse query parameters from URI
    cursor = None
    flow_id = None
    deployment_id = None
    state_type = None
    state_name = None

    try:
        original_uri = get_request_uri(ctx)
        if original_uri and "?" in original_uri:
            # Parse query parameters manually
            query_part = original_uri.split("?")[1]
            params = {}
            for param in query_part.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    params[key] = value

            cursor = params.get("cursor")
            flow_id = params.get("flow_id")
            deployment_id = params.get("deployment_id")
            state_type = params.get("state_type")
            state_name = params.get("state_name")
            await ctx.debug(f"Found params - cursor: {cursor}, flow_id: {flow_id}, deployment_id: {deployment_id}, state_type: {state_type}, state_name: {state_name}")
    except Exception as e:
        await ctx.debug(f"Could not parse URI parameters: {e}")

    async def operation():
        # Handle pagination
        page_size = 20
        if cursor:
            # Parse cursor for pagination
            offset, cursor_page_size = decode_cursor(cursor)
            page_size = cursor_page_size  # Use page size from cursor
        else:
            # First page
            offset = 0

        # Build filter based on search parameters
        flow_run_filter = None

        if flow_id or deployment_id or state_type or state_name:
            filter_kwargs = {}

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
            # Fetch one extra to determine if there are more results
            flow_runs = await client.read_flow_runs(flow_run_filter=flow_run_filter, limit=page_size + 1, offset=offset)

            # Check if there are more results
            has_more = len(flow_runs) > page_size
            if has_more:
                flow_runs = flow_runs[:page_size]  # Remove the extra item
                next_cursor = encode_cursor(offset + page_size, page_size)
            else:
                next_cursor = None

            result = {
                "flow_runs": [flow_run.model_dump() for flow_run in flow_runs],
                "count": len(flow_runs),
                "filters": {"flow_id": flow_id, "deployment_id": deployment_id, "state_type": state_type, "state_name": state_name},
                "pagination": {"offset": offset, "page_size": page_size, "has_more": has_more},
            }

            # Add nextCursor if more results exist (MCP-compliant)
            if next_cursor:
                result["nextCursor"] = next_cursor

            return result

    return await safe_prefect_operation(ctx, "list_flow_runs", operation)


@mcp.resource("prefect://flow-runs/{id}")
async def get_flow_run_by_id_resource(ctx: Context, id: str):
    """Get a specific flow run by its ID."""
    await ctx.debug(f"get_flow_run_by_id_resource: id={id}")

    if not id:
        raise ResourceError("Missing required parameter: id")

    async def operation():
        async with get_client() as client:
            flow_run = await client.read_flow_run(UUID(id))
            return {"flow_run": flow_run.model_dump()}

    return await safe_prefect_operation(ctx, "get_flow_run_by_id", operation)


# ------------------------------------------------------------------------
# Action Tools (not covered by resources - these perform operations)
# ------------------------------------------------------------------------


@mcp.tool()
async def get_deployment_parameters(deployment_name: str, ctx: Context) -> Dict[str, Any]:
    """
    Get detailed parameter information for a specific Prefect deployment.

    Args:
        deployment_name: The name of the deployment to get parameters for

    Returns:
        dict: Parameter schema and default values for the deployment
    """
    await ctx.debug(f"get_deployment_parameters entry: deployment_name={deployment_name}")
    try:
        # Use Prefect client to get deployment details
        async with get_client() as client:
            # Find the deployment by name
            deployments = await client.read_deployments(deployment_filter=DeploymentFilter(name=DeploymentFilterName(any_=[deployment_name])))

            if not deployments:
                return {"status": "error", "message": f"Deployment '{deployment_name}' not found", "deployment": deployment_name}

            deployment = deployments[0]

            # Get flow name from flow_id
            flow_name = "unknown"
            try:
                flow = await client.read_flow(deployment.flow_id)
                flow_name = flow.name
            except:
                pass  # If we can't get flow name, use unknown

            # Get parameter schema from deployment
            parameter_schema = deployment.parameter_openapi_schema or {}
            default_parameters = deployment.parameters or {}

            # Extract parameter information
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

            result = {
                "status": "success",
                "deployment": deployment_name,
                "flow_name": flow_name,
                "description": deployment.description or "No description",
                "parameters": parameters_info,
                "default_parameters": default_parameters,
                "required_parameters": parameter_schema.get("required", []),
                "parameter_count": len(parameters_info),
            }
            await ctx.debug(f"get_deployment_parameters exit: parameter_count={len(parameters_info)}")
            return result

    except Exception as e:
        traceback.print_stack()
        await ctx.error(f"Failed to get deployment parameters: {str(e)}", "get_deployment_parameters")
        result = {"status": "error", "message": f"Failed to get deployment parameters: {str(e)}", "deployment": deployment_name}
        await ctx.debug(f"get_deployment_parameters exit with error: result={result}")
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
            await ctx.debug(f"cancel_flow_run exit: successfully cancelled flow run")
            return result
        except Exception as e:
            await ctx.error(f"Failed to cancel flow run: {str(e)}", "cancel_flow_run")
            result = {"error": f"Failed to cancel flow run: {str(e)}"}
            await ctx.debug(f"cancel_flow_run exit with error: result={result}")
            return result


@mcp.tool()
async def create_flow_run_from_deployment(
    ctx: Context,
    deployment_id: str,
    parameters: Optional[Dict[str, Any]] = None,
    name: Optional[str] = None,
    timeout: int = 0,
) -> Dict[str, Any]:
    """Create a new flow run for the specified deployment.

    Args:
        deployment_id: ID of the deployment or name in format 'flow_name/deployment_name'.
        parameters: Dictionary with parameters for the flow run (optional).
        name: Optional name for the flow run.
        timeout: Timeout in seconds, 0 means no waiting for completion (default 0).
    """
    await ctx.debug(f"create_flow_run_from_deployment entry: deployment_id={deployment_id}, parameters={parameters}, name={name}, timeout={timeout}")
    if not deployment_id:
        result = {"error": "Missing required argument: deployment_id"}
        await ctx.debug(f"create_flow_run_from_deployment exit with validation error: result={result}")
        return result

    from prefect.deployments import run_deployment

    try:
        # pylance is wrong, using await is correct here but it doesn't understand @sync_compatible.
        run_result = await run_deployment(name=deployment_id, parameters=parameters or {}, timeout=timeout, flow_run_name=name)

        result = {"flow_run_id": str(run_result)}
        await ctx.debug(f"create_flow_run_from_deployment exit: flow_run_id={run_result}")
        return result
    except Exception as e:
        await ctx.error(f"Failed to create flow run: {str(e)}", "create_flow_run_from_deployment")
        result = {"error": f"Failed to create flow run: {str(e)}"}
        await ctx.debug(f"create_flow_run_from_deployment exit with error: result={result}")
        return result


if __name__ == "__main__":
    mcp.run(transport="http", host="localhost", port=8000, log_level="DEBUG")
