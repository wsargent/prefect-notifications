#!/usr/bin/env python3
"""
MCP server for doing stuff
"""
from typing import Any, Dict
import os

from fastmcp.utilities.logging import get_logger
from fastmcp import FastMCP, Context
from prefect import get_client
from prefect.client.schemas.filters import DeploymentFilter, DeploymentFilterName
import traceback

mcp = FastMCP("prefect-mcp")

# Enable debug logging
os.environ["FASTMCP_LOG_LEVEL"] = "DEBUG"

logger = get_logger(__name__)

async def execute_flow_deployment(deployment_name: str, parameters: str, ctx: Context) -> Dict[str, Any]:
    """
    Execute a Prefect flow deployment with the given parameters.
    
    Args:
        deployment_name: The name of the deployment to run
        parameters: JSON string of parameters to pass to the flow
        
    Returns:
        dict: Status of the flow run
    """
    try:
        import json
        
        # Parse parameters from JSON string
        try:
            flow_parameters = json.loads(parameters)
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "message": f"Invalid JSON in parameters: {str(e)}",
                "deployment": deployment_name,
                "parameters": parameters
            }
        
        # Use Prefect client to run the deployment
        async with get_client() as client:
            # First, get the deployment by name
            deployments = await client.read_deployments(
                deployment_filter=DeploymentFilter(name=DeploymentFilterName(any_=[deployment_name]))
            )
            
            if not deployments:
                return {
                    "status": "error",
                    "message": f"Deployment '{deployment_name}' not found",
                    "deployment": deployment_name
                }
            
            deployment = deployments[0]
            
            # Create a flow run from the deployment
            flow_run = await client.create_flow_run_from_deployment(
                deployment_id=deployment.id,
                parameters=flow_parameters,
                context=None,
                state=None,
                name=None,
                tags=None,
                idempotency_key=None,
                parent_task_run_id=None,
                work_queue_name=None,
                job_variables=None,
                labels=None
            )
            
            return {
                "status": "success",
                "message": "Flow run created successfully",
                "flow_run_id": str(flow_run.id),
                "flow_run_name": flow_run.name,
                "deployment": deployment_name,
                "parameters": flow_parameters,
                "flow_run_url": f"http://localhost:4200/runs/flow-run/{flow_run.id}"
            }
            
    except Exception as e:
        traceback.print_stack()
        await ctx.error(f"Failed to run deployment: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to run deployment: {str(e)}",
            "deployment": deployment_name,
            "parameters": parameters
        }

@mcp.tool()
async def run_prefect_flow(deployment_name: str, parameters: str, ctx: Context) -> Dict[str, Any]:
    """
    Run a Prefect flow deployment using the Prefect Python client.
    
    Args:
        deployment_name: The name of the deployment to run (default: "ntfy-default/ntfy-default-deployment")
        parameters: JSON string of parameters to pass to the flow (default: '{"body": "Test", "subject": "Notification"}')        

    Returns:
        dict: Status of the flow run
    """
    return await execute_flow_deployment(deployment_name, parameters, ctx)

@mcp.tool()
async def run_ntfy_notification(body: str, subject: str, deployment_name: str, ctx: Context) -> Dict[str, Any]:
    """
    Convenience function to run the ntfy notification flow with simple parameters.
    
    Args:
        body: The notification message body (default: "Test")
        subject: The notification subject/title (default: "Notification")
        deployment_name: The name of the deployment to run (default: "ntfy-default/ntfy-default-deployment")
        
    Returns:
        dict: Status of the flow run
    """
    import json
    
    # Convert to JSON parameters for the generic run_prefect_flow function
    parameters_json = json.dumps({"body": body, "subject": subject})
    
    # Call the shared execution method
    return await execute_flow_deployment(deployment_name, parameters_json, ctx)

@mcp.tool()
async def list_prefect_deployments(ctx: Context) -> Dict[str, Any]:
    """
    List all available Prefect deployments.
    
    Returns:
        dict: List of deployments with their details
    """
    try:        
        # Use Prefect client to list deployments
        async with get_client() as client:
            deployments = await client.read_deployments()
            
            deployment_list = []
            for deployment in deployments:
                # Get flow name from flow_id
                flow_name = "unknown"
                try:
                    flow = await client.read_flow(deployment.flow_id)
                    flow_name = flow.name
                except:
                    pass  # If we can't get flow name, use unknown
                    
                deployment_info = {
                    "id": str(deployment.id),
                    "name": deployment.name,
                    "flow_name": flow_name,
                    "work_pool_name": deployment.work_pool_name,
                    "status": deployment.status.value if deployment.status else "unknown",
                    "created": deployment.created.isoformat() if deployment.created else None,
                    "updated": deployment.updated.isoformat() if deployment.updated else None,
                    "description": deployment.description or "No description",
                    "tags": deployment.tags or [],
                    "parameters": deployment.parameters or {},
                    "url": f"http://localhost:4200/deployments/deployment/{deployment.id}"
                }
                deployment_list.append(deployment_info)
            
            return {
                "status": "success",
                "message": f"Found {len(deployment_list)} deployment(s)",
                "deployments": deployment_list,
                "count": len(deployment_list)
            }
            
    except Exception as e:
        traceback.print_stack()
        await ctx.error(f"Failed to list deployment: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to list deployments: {str(e)}"
        }

@mcp.tool()
async def get_deployment_parameters(deployment_name: str, ctx: Context) -> Dict[str, Any]:
    """
    Get detailed parameter information for a specific Prefect deployment.
    
    Args:
        deployment_name: The name of the deployment to get parameters for
        
    Returns:
        dict: Parameter schema and default values for the deployment
    """
    try:    
        # Use Prefect client to get deployment details
        async with get_client() as client:
            # Find the deployment by name
            deployments = await client.read_deployments(
                deployment_filter=DeploymentFilter(name=DeploymentFilterName(any_=[deployment_name]))
            )
            
            if not deployments:
                return {
                    "status": "error",
                    "message": f"Deployment '{deployment_name}' not found",
                    "deployment": deployment_name
                }
            
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
                        "examples": param_info.get("examples", [])
                    }        
            
            return {
                "status": "success",
                "deployment": deployment_name,
                "flow_name": flow_name,
                "description": deployment.description or "No description",
                "parameters": parameters_info,
                "default_parameters": default_parameters,
                "required_parameters": parameter_schema.get("required", []),
                "parameter_count": len(parameters_info)
            }
            
    except Exception as e:
        traceback.print_stack()
        await ctx.error(f"Failed to get deployment parameters: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to get deployment parameters: {str(e)}",
            "deployment": deployment_name
        }


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8000, log_level="DEBUG")