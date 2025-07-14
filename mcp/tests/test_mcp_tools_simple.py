"""
Simple tests for MCP server tools using real FastMCP Client and Prefect test harness
"""
import pytest
import pytest_asyncio
from fastmcp import Client
from prefect.testing.utilities import prefect_test_harness

from main import mcp

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)

# Apply asyncio mark to all async functions
pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True, scope="session")
def prefect_test_fixture():
    with prefect_test_harness():
        yield


@pytest_asyncio.fixture
async def test_flow():
    """Create a test flow fixture."""
    from prefect import flow, get_client
    
    @flow(name="test-flow-fixture")
    def sample_test_flow(message: str = "hello"):
        return f"Flow says: {message}"
    
    # Register the flow with the database by calling it
    sample_test_flow()
    
    # Return the flow object for use in tests
    return sample_test_flow


@pytest_asyncio.fixture
async def test_deployment(test_flow):
    """Create a test deployment fixture."""
    from prefect import get_client
    
    async with get_client() as client:
        # First get the flow to create a deployment for
        flows = await client.read_flows()
        test_flow_obj = None
        for flow in flows:
            if flow.name == "test-flow-fixture":
                test_flow_obj = flow
                break
        
        if not test_flow_obj:
            raise ValueError("Test flow not found")
        
        # Create a deployment using the correct API
        deployment_id = await client.create_deployment(
            flow_id=test_flow_obj.id,
            name="test-deployment-fixture",
            parameters={"message": "test deployment"},
            tags=["test", "fixture"],
            description="Test deployment for fixture testing"
        )
        
        # Read the created deployment
        deployment = await client.read_deployment(deployment_id)
        
        # Return deployment data for tests
        return {
            "deployment": deployment,
            "flow": test_flow_obj
        }


@pytest_asyncio.fixture
async def test_flow_run(test_deployment):
    """Create a test flow run fixture."""
    from prefect import get_client
    
    async with get_client() as client:
        # Create a flow run from the test deployment
        flow_run = await client.create_flow_run_from_deployment(
            deployment_id=test_deployment["deployment"].id,
            parameters={"message": "test flow run"},
            tags=["test-run", "fixture"]
        )
        
        # Return flow run data for tests
        return {
            "flow_run": flow_run,
            "deployment": test_deployment["deployment"],
            "flow": test_deployment["flow"]
        }


class TestMcpTools:
    """Test MCP tool operations."""
    
    async def test_list_flows_empty(self):
        """Test listing flows when none exist."""
        async with Client(mcp) as client:
            result = await client.call_tool("list_flows", {})
            
            assert "flows" in result.data
            assert isinstance(result.data["flows"], list)
            assert result.data["count"] == 0
            assert result.data["has_more"] is False
    
    async def test_list_flows_with_filters(self):
        """Test listing flows with various filters."""
        async with Client(mcp) as client:
            # Test with name filter
            result = await client.call_tool("list_flows", {"name": "nonexistent"})
            assert "flows" in result.data
            assert result.data["count"] == 0
            
            # Test with tags filter
            result = await client.call_tool("list_flows", {"tags": "test,dev"})
            assert "flows" in result.data
            assert result.data["count"] == 0

    async def test_list_flows_with_actual_flow(self, test_flow):
        """Test listing flows with an actual flow in the database."""
        # test_flow fixture ensures the flow is registered
        _ = test_flow  # Fixture ensures flow is created
        async with Client(mcp) as client:
            result = await client.call_tool("list_flows", {})
            
            assert "flows" in result.data
            assert result.data["count"] >= 1
            
            # Check that our test flow is in the results
            flow_names = [f["name"] for f in result.data["flows"]]
            assert "test-flow-fixture" in flow_names
            
            # Test filtering by our flow's name
            result = await client.call_tool("list_flows", {"name": "test-flow-fixture"})
            assert "flows" in result.data
            assert result.data["count"] >= 1
            
            # All returned flows should match the filter
            for flow_data in result.data["flows"]:
                assert "test-flow-fixture" in flow_data["name"]

    async def test_get_flow_by_id_with_actual_flow(self, test_flow):
        """Test get_flow_by_id with an actual flow in the database."""
        # test_flow fixture ensures the flow is registered
        _ = test_flow  # Fixture ensures flow is created
        async with Client(mcp) as client:
            # First, get the list of flows to find our test flow's ID
            result = await client.call_tool("list_flows", {"name": "test-flow-fixture"})
            assert result.data["count"] >= 1
            
            test_flow_data = result.data["flows"][0]
            flow_id = test_flow_data["id"]
            
            # Now get the flow by ID
            result = await client.call_tool("get_flow_by_id", {"flow_id": flow_id})
            
            assert "flow" in result.data
            assert result.data["flow"]["id"] == flow_id
            assert result.data["flow"]["name"] == "test-flow-fixture"
    
    async def test_get_flow_by_id_missing_param(self):
        """Test get_flow_by_id with missing parameter."""
        async with Client(mcp) as client:
            result = await client.call_tool("get_flow_by_id", {"flow_id": ""})
            
            assert "error" in result.data
            assert "Missing required parameter" in result.data["error"]
    
    async def test_get_flow_by_id_invalid_uuid(self):
        """Test get_flow_by_id with invalid UUID."""
        async with Client(mcp) as client:
            # The tool raises a ToolError for invalid UUIDs, which is expected behavior
            from fastmcp.exceptions import ToolError
            
            try:
                result = await client.call_tool("get_flow_by_id", {"flow_id": "invalid-uuid"})
                # If we get here, check for error in the result
                assert "error" in result.data
            except ToolError as e:
                # This is the expected behavior - the tool raises an error for invalid UUIDs
                assert "badly formed hexadecimal UUID string" in str(e)
    
    async def test_list_deployments_empty(self):
        """Test listing deployments when none exist."""
        async with Client(mcp) as client:
            result = await client.call_tool("list_deployments", {})
            
            assert "deployments" in result.data
            assert isinstance(result.data["deployments"], list)
            assert result.data["count"] == 0

    async def test_list_deployments_with_actual_deployment(self, test_deployment):
        """Test listing deployments with an actual deployment in the database."""
        # test_deployment fixture ensures the deployment is registered
        _ = test_deployment  # Fixture ensures deployment is created
        async with Client(mcp) as client:
            result = await client.call_tool("list_deployments", {})
            
            assert "deployments" in result.data
            assert result.data["count"] >= 1
            
            # Check that our test deployment is in the results
            deployment_names = [d["name"] for d in result.data["deployments"]]
            assert "test-deployment-fixture" in deployment_names
            
            # Test filtering by deployment name
            result = await client.call_tool("list_deployments", {"name": "test-deployment-fixture"})
            assert "deployments" in result.data
            assert result.data["count"] >= 1
            
            # All returned deployments should match the filter
            for deployment_data in result.data["deployments"]:
                assert "test-deployment-fixture" in deployment_data["name"]
    
    async def test_get_deployment_by_id_with_actual_deployment(self, test_deployment):
        """Test get_deployment_by_id with an actual deployment in the database."""
        # test_deployment fixture ensures the deployment is registered
        _ = test_deployment  # Fixture ensures deployment is created
        async with Client(mcp) as client:
            # First, get the list of deployments to find our test deployment's ID
            result = await client.call_tool("list_deployments", {"name": "test-deployment-fixture"})
            assert result.data["count"] >= 1
            
            test_deployment_data = result.data["deployments"][0]
            deployment_id = test_deployment_data["id"]
            
            # Now get the deployment by ID
            result = await client.call_tool("get_deployment_by_id", {"deployment_id": deployment_id})
            
            assert "deployment" in result.data
            assert result.data["deployment"]["id"] == deployment_id
            assert result.data["deployment"]["name"] == "test-deployment-fixture"
            assert result.data["deployment"]["description"] == "Test deployment for fixture testing"

    async def test_get_deployment_by_id_missing_param(self):
        """Test get_deployment_by_id with missing parameter."""
        async with Client(mcp) as client:
            result = await client.call_tool("get_deployment_by_id", {"deployment_id": ""})
            
            assert "error" in result.data
            assert "Missing required parameter" in result.data["error"]
    
    async def test_get_deployment_parameters_missing_params(self):
        """Test get_deployment_parameters with missing parameters."""
        async with Client(mcp) as client:
            result = await client.call_tool("get_deployment_parameters", {})
            
            assert "error" in result.data
            assert "Must provide either deployment_id or name parameter" in result.data["error"]
    
    async def test_get_deployment_parameters_invalid_name_format(self):
        """Test get_deployment_parameters with invalid name format."""
        async with Client(mcp) as client:
            result = await client.call_tool("get_deployment_parameters", {"name": "invalid-name"})
            
            assert "error" in result.data
            assert "Name must be in format 'flow_name/deployment_name'" in result.data["error"]

    async def test_get_deployment_parameters_with_actual_deployment(self, test_deployment):
        """Test get_deployment_parameters with an actual deployment."""
        # test_deployment fixture ensures the deployment is registered
        _ = test_deployment  # Fixture ensures deployment is created
        async with Client(mcp) as client:
            # Test with deployment name format
            result = await client.call_tool("get_deployment_parameters", {
                "name": "test-flow-fixture/test-deployment-fixture"
            })
            
            assert "deployment_id" in result.data
            assert "deployment_name" in result.data
            assert "parameters" in result.data
            assert "default_parameters" in result.data
            assert result.data["deployment_name"] == "test-deployment-fixture"
            assert result.data["description"] == "Test deployment for fixture testing"
            assert result.data["default_parameters"]["message"] == "test deployment"

    async def test_list_deployments_with_flow_filter(self, test_deployment):
        """Test listing deployments with flow ID filter."""
        # test_deployment fixture ensures the deployment is registered
        flow_id = str(test_deployment["flow"].id)
        
        async with Client(mcp) as client:
            result = await client.call_tool("list_deployments", {"flow_id": flow_id})
            
            assert "deployments" in result.data
            assert result.data["count"] >= 1
            
            # All returned deployments should match the flow_id filter
            for deployment_data in result.data["deployments"]:
                assert deployment_data["flow_id"] == flow_id
    
    async def test_list_flow_runs_empty(self):
        """Test listing flow runs when none exist."""
        async with Client(mcp) as client:
            result = await client.call_tool("list_flow_runs", {})
            
            assert "flow_runs" in result.data
            assert isinstance(result.data["flow_runs"], list)
            assert result.data["count"] >= 0
            assert result.data["has_more"] is False

    async def test_list_flow_runs_with_actual_flow_run(self, test_flow_run):
        """Test listing flow runs with an actual flow run in the database."""
        # test_flow_run fixture ensures the flow run is registered
        _ = test_flow_run  # Fixture ensures flow run is created
        async with Client(mcp) as client:
            result = await client.call_tool("list_flow_runs", {})
            
            assert "flow_runs" in result.data
            assert result.data["count"] >= 1
            
            # Check that our test flow run is in the results
            flow_run_ids = [fr["id"] for fr in result.data["flow_runs"]]
            test_flow_run_id = str(test_flow_run["flow_run"].id)
            
            # Verify our test flow run is in the results
            assert test_flow_run_id in flow_run_ids
    
    async def test_get_flow_run_by_id_with_actual_flow_run(self, test_flow_run):
        """Test get_flow_run_by_id with an actual flow run in the database."""
        # test_flow_run fixture ensures the flow run is registered
        flow_run_id = str(test_flow_run["flow_run"].id)
        
        async with Client(mcp) as client:
            result = await client.call_tool("get_flow_run_by_id", {"flow_run_id": flow_run_id})
            
            assert "flow_run" in result.data
            assert result.data["flow_run"]["id"] == flow_run_id
            assert result.data["flow_run"]["deployment_id"] == str(test_flow_run["deployment"].id)
            assert result.data["flow_run"]["flow_id"] == str(test_flow_run["flow"].id)

    async def test_get_flow_run_by_id_missing_param(self):
        """Test get_flow_run_by_id with missing parameter."""
        async with Client(mcp) as client:
            result = await client.call_tool("get_flow_run_by_id", {"flow_run_id": ""})
            
            assert "error" in result.data
            assert "Missing required parameter" in result.data["error"]
    
    async def test_cancel_flow_run_with_actual_flow_run(self, test_flow_run):
        """Test cancel_flow_run with an actual flow run in the database."""
        # test_flow_run fixture ensures the flow run is registered
        flow_run_id = str(test_flow_run["flow_run"].id)
        
        async with Client(mcp) as client:
            result = await client.call_tool("cancel_flow_run", {"flow_run_id": flow_run_id})
            
            assert "success" in result.data
            assert result.data["success"] is True
            assert "result" in result.data

    async def test_bulk_cancel_flow_runs(self, test_deployment):
        """Test bulk_cancel_flow_runs with actual flow runs in the database."""
        # test_deployment fixture ensures the deployment is registered
        deployment_id = str(test_deployment["deployment"].id)
        
        async with Client(mcp) as client:
            # First, create multiple flow runs that can be cancelled
            flow_run_ids = []
            for i in range(3):
                result = await client.call_tool("create_flow_run_from_deployment", {
                    "deployment_id": deployment_id,
                    "parameters": {"message": f"bulk cancel test {i}"}
                })
                assert "flow_run_id" in result.data
                flow_run_ids.append(result.data["flow_run_id"])
            
            # Verify the flow runs exist
            for flow_run_id in flow_run_ids:
                result = await client.call_tool("get_flow_run_by_id", {"flow_run_id": flow_run_id})
                assert "flow_run" in result.data
                assert result.data["flow_run"]["id"] == flow_run_id
            
            # Now test bulk cancellation
            result = await client.call_tool("bulk_cancel_flow_runs", {})
            
            assert "success" in result.data
            assert result.data["success"] is True

    async def test_cancel_flow_run_missing_param(self):
        """Test cancel_flow_run with missing parameter."""
        async with Client(mcp) as client:
            result = await client.call_tool("cancel_flow_run", {"flow_run_id": ""})
            
            assert "error" in result.data
            assert "Missing required argument" in result.data["error"]
    
    async def test_cancel_flow_run_invalid_uuid(self):
        """Test cancel_flow_run with invalid UUID."""
        async with Client(mcp) as client:
            result = await client.call_tool("cancel_flow_run", {"flow_run_id": "invalid-uuid"})
            
            assert "error" in result.data
            assert "Failed to cancel flow run" in result.data["error"]
    
    async def test_create_flow_run_with_actual_deployment(self, test_deployment):
        """Test create_flow_run_from_deployment with an actual deployment."""
        # test_deployment fixture ensures the deployment is registered
        deployment_id = str(test_deployment["deployment"].id)
        
        async with Client(mcp) as client:
            result = await client.call_tool("create_flow_run_from_deployment", {
                "deployment_id": deployment_id,
                "parameters": {"message": "test run creation"}
            })
            
            assert "flow_run_id" in result.data
            assert result.data["flow_run_id"] is not None
            
            # Test with deployment name format
            result = await client.call_tool("create_flow_run_from_deployment", {
                "name": "test-flow-fixture/test-deployment-fixture",
                "parameters": {"message": "test run with name"}
            })
            
            assert "flow_run_id" in result.data
            assert result.data["flow_run_id"] is not None

    async def test_create_flow_run_missing_params(self):
        """Test create_flow_run_from_deployment with missing parameters."""
        async with Client(mcp) as client:
            result = await client.call_tool("create_flow_run_from_deployment", {})
            
            assert "error" in result.data
            assert "Neither deployment_id nor name were provided" in result.data["error"]
    
    async def test_create_flow_run_with_invalid_deployment_name(self):
        """Test create_flow_run_from_deployment with invalid deployment name."""
        async with Client(mcp) as client:
            result = await client.call_tool("create_flow_run_from_deployment", {
                "name": "nonexistent-flow/nonexistent-deployment"
            })
            
            assert "error" in result.data
            assert "Failed to create flow run" in result.data["error"]
    
    async def test_list_flows_pagination(self):
        """Test flow listing with pagination."""
        async with Client(mcp) as client:
            # Test with pagination cursor
            from main import encode_cursor
            cursor = encode_cursor(0, 10)
            result = await client.call_tool("list_flows", {"cursor": cursor})
            
            assert "flows" in result.data
            assert "has_more" in result.data
            assert "count" in result.data
    
    async def test_list_flow_runs_with_filters(self):
        """Test flow run listing with various filters."""
        async with Client(mcp) as client:
            result = await client.call_tool("list_flow_runs", {
                "state_type": "COMPLETED",
                "state_name": "Completed"
            })
            
            assert "flow_runs" in result.data
            assert "filters" in result.data
            assert result.data["filters"]["state_type"] == "COMPLETED"
            assert result.data["filters"]["state_name"] == "Completed"

    async def test_list_flow_runs_with_flow_filter(self, test_flow_run):
        """Test flow run listing with flow ID filter."""
        # test_flow_run fixture ensures the flow run is registered
        flow_id = str(test_flow_run["flow"].id)
        
        async with Client(mcp) as client:
            result = await client.call_tool("list_flow_runs", {"flow_id": flow_id})
            
            assert "flow_runs" in result.data
            assert result.data["count"] >= 1
            
            # All returned flow runs should match the flow_id filter
            for flow_run_data in result.data["flow_runs"]:
                assert flow_run_data["flow_id"] == flow_id