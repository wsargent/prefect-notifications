#!/usr/bin/env python3
"""
Test suite for Prefect MCP Server resources.
"""

import json
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.exceptions import ResourceError
from mcp.shared.exceptions import McpError
from prefect.client.schemas.objects import Flow, Deployment, FlowRun, StateType
from prefect.client.schemas.filters import FlowFilter, FlowFilterName, FlowFilterTags

# Import the FastMCP server instance and related modules
from prefect_mcp.server import mcp


@pytest.fixture
def sample_flow():
    """Creates a sample Flow object for testing."""
    return Flow(id=uuid4(), name="test-flow", tags=["test", "sample"], created=datetime.now(timezone.utc), updated=datetime.now(timezone.utc))


@pytest.fixture
def sample_deployment():
    """Creates a sample Deployment object for testing."""
    flow_id = uuid4()
    return Deployment(id=uuid4(), name="test-deployment", flow_id=flow_id, description="Test deployment", tags=["test", "sample"], created=datetime.now(timezone.utc), updated=datetime.now(timezone.utc))


@pytest.fixture
def sample_flow_run():
    """Creates a sample FlowRun object for testing."""
    flow_id = uuid4()
    deployment_id = uuid4()
    return FlowRun(id=uuid4(), name="test-flow-run", flow_id=flow_id, deployment_id=deployment_id, created=datetime.now(timezone.utc), updated=datetime.now(timezone.utc))


@pytest.fixture
def mock_async_client():
    """Creates a mock Prefect async client."""
    client = AsyncMock()
    # This makes the mock usable in an `async with` block
    mock_get_client_cm = AsyncMock()
    mock_get_client_cm.__aenter__.return_value = client
    return client, mock_get_client_cm


class TestFlowResources:
    """Test Phase 1: Flow Resources."""

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_client")
    async def test_list_flows_resource_no_params(self, mock_get_client, sample_flow, mock_async_client):
        """Test prefect://flows resource with no query parameters using the client."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_client.read_flows.return_value = [sample_flow]
        mock_get_client.return_value = mock_get_client_cm

        async with Client(mcp) as client:
            result = await client.read_resource("prefect://flows")
            content = result[0]
            data = json.loads(content.text)

            assert "flows" in data
            assert data["count"] == 1
            mock_client.read_flows.assert_called_once()
            _, kwargs = mock_client.read_flows.call_args
            assert kwargs["offset"] == 0
            assert kwargs["limit"] == 21  # It requests one more to check for next page

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_request_uri")
    @patch("prefect_mcp.server.get_client")
    async def test_list_flows_resource_with_query(self, mock_get_client, mock_get_uri, sample_flow, mock_async_client):
        """Test list_flows_resource function with query parameter parsing."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_client.read_flows.return_value = [sample_flow]
        mock_get_client.return_value = mock_get_client_cm
        mock_get_uri.return_value = "prefect://flows?query=test"

        # Get the actual resource function from the FastMCP server
        resource_manager = mcp._resource_manager
        resource_func = None
        for resource in resource_manager._resources.values():
            if str(resource.uri) == "prefect://flows":
                resource_func = resource.fn
                break

        assert resource_func is not None, "Could not find flows resource function"

        # Create a mock context
        mock_ctx = AsyncMock()

        # Test the resource function directly
        data = await resource_func(mock_ctx)

        assert data["filters"]["query"] == "test"
        mock_client.read_flows.assert_called_once()
        _, kwargs = mock_client.read_flows.call_args
        assert isinstance(kwargs["flow_filter"], FlowFilter)
        assert kwargs["flow_filter"].name == FlowFilterName(like_="test")

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_request_uri")
    @patch("prefect_mcp.server.get_client")
    async def test_list_flows_resource_with_tags(self, mock_get_client, mock_get_uri, sample_flow, mock_async_client):
        """Test list_flows_resource function with tags parameter parsing."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_client.read_flows.return_value = [sample_flow]
        mock_get_client.return_value = mock_get_client_cm
        mock_get_uri.return_value = "prefect://flows?tags=foo,bar"

        # Get the actual resource function from the FastMCP server
        resource_manager = mcp._resource_manager
        resource_func = None
        for resource in resource_manager._resources.values():
            if str(resource.uri) == "prefect://flows":
                resource_func = resource.fn
                break

        assert resource_func is not None, "Could not find flows resource function"
        mock_ctx = AsyncMock()
        data = await resource_func(mock_ctx)

        assert data["filters"]["tags"] == ["foo", "bar"]
        mock_client.read_flows.assert_called_once()
        _, kwargs = mock_client.read_flows.call_args
        assert isinstance(kwargs["flow_filter"], FlowFilter)
        assert kwargs["flow_filter"].tags == FlowFilterTags(all_=["foo", "bar"])

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_request_uri")
    @patch("prefect_mcp.server.get_client")
    async def test_list_flows_pagination(self, mock_get_client, mock_get_uri, sample_flow, mock_async_client):
        """Test cursor-based pagination for list_flows_resource."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_get_client.return_value = mock_get_client_cm
        # Get the actual resource function from the FastMCP server
        resource_manager = mcp._resource_manager
        resource_func = None
        for resource in resource_manager._resources.values():
            if str(resource.uri) == "prefect://flows":
                resource_func = resource.fn
                break

        assert resource_func is not None, "Could not find flows resource function"
        mock_ctx = AsyncMock()

        # First page
        mock_get_uri.return_value = "prefect://flows"
        mock_client.read_flows.return_value = [sample_flow] * 21  # Full page + extra
        data1 = await resource_func(mock_ctx)

        assert "nextCursor" in data1
        assert len(data1["flows"]) == 20

        # Second page
        cursor = data1["nextCursor"]
        mock_get_uri.return_value = f"prefect://flows?cursor={cursor}"
        mock_client.read_flows.return_value = [sample_flow]  # Last item
        data2 = await resource_func(mock_ctx)

        assert "nextCursor" not in data2
        assert len(data2["flows"]) == 1
        assert data2["pagination"]["offset"] == 20

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_client")
    async def test_get_flow_by_id_resource(self, mock_get_client, sample_flow, mock_async_client):
        """Test get_flow_by_id_resource function."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_client.read_flow.return_value = sample_flow
        mock_get_client.return_value = mock_get_client_cm

        flow_id = str(sample_flow.id)

        async with Client(mcp) as client:
            result = await client.read_resource(f"prefect://flows/{flow_id}")
            content = result[0]
            data = json.loads(content.text)

            assert "flow" in data
            assert data["flow"]["id"] == flow_id
            mock_client.read_flow.assert_called_once_with(UUID(flow_id))

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_client")
    async def test_get_flow_by_id_resource_not_found(self, mock_get_client, mock_async_client):
        """Test get_flow_by_id_resource for a non-existent flow."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_client.read_flow.side_effect = ValueError("Flow not found")
        mock_get_client.return_value = mock_get_client_cm

        async with Client(mcp) as client:
            with pytest.raises(Exception):  # This will raise through the MCP client
                await client.read_resource(f"prefect://flows/{uuid4()}")

    @pytest.mark.asyncio
    async def test_flow_resources_listed(self):
        """Test that flow resources are properly registered."""
        async with Client(mcp) as client:
            resources = await client.list_resources()

            expected_uris = ["prefect://flows"]
            expected_templates = ["prefect://flows/{id}"]

            actual_uris = [str(r.uri) for r in resources]

            # Also check templates
            templates = await client.list_resource_templates()
            actual_templates = [str(t.uriTemplate) for t in templates]

            assert all(uri in actual_uris for uri in expected_uris), f"Missing URIs. Expected: {expected_uris}, Got: {actual_uris}"
            assert all(template in actual_templates for template in expected_templates), f"Missing templates. Expected: {expected_templates}, Got: {actual_templates}"

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_client")
    async def test_list_flows_resource_content_structure(self, mock_get_client, sample_flow, mock_async_client):
        """Test that flow list resource returns properly structured content."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_client.read_flows.return_value = [sample_flow]
        mock_get_client.return_value = mock_get_client_cm

        async with Client(mcp) as client:
            result = await client.read_resource("prefect://flows")
            content = result[0]
            data = json.loads(content.text)

            # Verify required fields are present
            assert "flows" in data
            assert "count" in data
            assert "filters" in data
            assert "pagination" in data

            # Verify flow structure
            assert len(data["flows"]) == 1
            flow_data = data["flows"][0]
            assert "id" in flow_data
            assert "name" in flow_data
            assert "tags" in flow_data

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_client")
    async def test_get_flow_by_id_invalid_uuid(self, mock_get_client, mock_async_client):
        """Test error handling for invalid UUID in flow resource."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_get_client.return_value = mock_get_client_cm

        async with Client(mcp) as client:
            with pytest.raises(Exception):  # Should raise an error for invalid UUID
                await client.read_resource("prefect://flows/invalid-uuid")


class TestDeploymentResources:
    """Test Phase 2: Deployment Resources."""

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_client")
    async def test_list_deployments_resource_no_params(self, mock_get_client, sample_deployment, sample_flow, mock_async_client):
        """Test prefect://deployments resource with no query parameters."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_client.read_deployments.return_value = [sample_deployment]
        mock_client.read_flow.return_value = sample_flow
        mock_get_client.return_value = mock_get_client_cm

        async with Client(mcp) as client:
            result = await client.read_resource("prefect://deployments")
            content = result[0]
            data = json.loads(content.text)

            assert "deployments" in data
            assert data["count"] == 1
            assert data["deployments"][0]["flow_name"] == "test-flow"
            mock_client.read_deployments.assert_called_once()

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_request_uri")
    @patch("prefect_mcp.server.get_client")
    async def test_list_deployments_resource_with_query(self, mock_get_client, mock_get_uri, sample_deployment, sample_flow, mock_async_client):
        """Test list_deployments_resource function with query parameter parsing."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_client.read_deployments.return_value = [sample_deployment]
        mock_client.read_flow.return_value = sample_flow
        mock_get_client.return_value = mock_get_client_cm
        mock_get_uri.return_value = "prefect://deployments?query=test"

        # Get the actual resource function from the FastMCP server
        resource_manager = mcp._resource_manager
        resource_func = None
        for resource in resource_manager._resources.values():
            if str(resource.uri) == "prefect://deployments":
                resource_func = resource.fn
                break

        assert resource_func is not None, "Could not find deployments resource function"
        mock_ctx = AsyncMock()
        data = await resource_func(mock_ctx)

        assert data["filters"]["query"] == "test"
        mock_client.read_deployments.assert_called_once()

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_client")
    async def test_get_deployment_by_id_resource(self, mock_get_client, sample_deployment, sample_flow, mock_async_client):
        """Test get_deployment_by_id_resource function."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_client.read_deployment.return_value = sample_deployment
        mock_client.read_flow.return_value = sample_flow
        mock_get_client.return_value = mock_get_client_cm

        deployment_id = str(sample_deployment.id)

        async with Client(mcp) as client:
            result = await client.read_resource(f"prefect://deployments/{deployment_id}")
            content = result[0]
            data = json.loads(content.text)

            assert "deployment" in data
            assert data["deployment"]["id"] == deployment_id
            assert data["deployment"]["flow_name"] == "test-flow"
            mock_client.read_deployment.assert_called_once_with(UUID(deployment_id))

    @pytest.mark.asyncio
    async def test_deployment_resources_listed(self):
        """Test that deployment resources are properly registered."""
        async with Client(mcp) as client:
            resources = await client.list_resources()
            templates = await client.list_resource_templates()

            expected_uris = ["prefect://flows", "prefect://deployments"]
            expected_templates = ["prefect://flows/{id}", "prefect://deployments/{id}"]

            actual_uris = [str(r.uri) for r in resources]
            actual_templates = [str(t.uriTemplate) for t in templates]

            assert all(uri in actual_uris for uri in expected_uris), f"Missing URIs. Expected: {expected_uris}, Got: {actual_uris}"
            assert all(template in actual_templates for template in expected_templates), f"Missing templates. Expected: {expected_templates}, Got: {actual_templates}"


class TestFlowRunResources:
    """Test Phase 3: Flow Run Resources."""

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_client")
    async def test_list_flow_runs_resource_no_params(self, mock_get_client, sample_flow_run, mock_async_client):
        """Test prefect://flow-runs resource with no query parameters."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_client.read_flow_runs.return_value = [sample_flow_run]
        mock_get_client.return_value = mock_get_client_cm

        async with Client(mcp) as client:
            result = await client.read_resource("prefect://flow-runs")
            content = result[0]
            data = json.loads(content.text)

            assert "flow_runs" in data
            assert data["count"] == 1
            mock_client.read_flow_runs.assert_called_once()

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_request_uri")
    @patch("prefect_mcp.server.get_client")
    async def test_list_flow_runs_resource_with_state_filter(self, mock_get_client, mock_get_uri, sample_flow_run, mock_async_client):
        """Test list_flow_runs_resource function with state filtering."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_client.read_flow_runs.return_value = [sample_flow_run]
        mock_get_client.return_value = mock_get_client_cm
        mock_get_uri.return_value = "prefect://flow-runs?state_type=COMPLETED"

        # Get the actual resource function from the FastMCP server
        resource_manager = mcp._resource_manager
        resource_func = None
        for resource in resource_manager._resources.values():
            if str(resource.uri) == "prefect://flow-runs":
                resource_func = resource.fn
                break

        assert resource_func is not None, "Could not find flow-runs resource function"
        mock_ctx = AsyncMock()
        data = await resource_func(mock_ctx)

        assert data["filters"]["state_type"] == "COMPLETED"
        mock_client.read_flow_runs.assert_called_once()

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_request_uri")
    @patch("prefect_mcp.server.get_client")
    async def test_list_flow_runs_resource_with_flow_id_filter(self, mock_get_client, mock_get_uri, sample_flow_run, mock_async_client):
        """Test list_flow_runs_resource function with flow_id filtering."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_client.read_flow_runs.return_value = [sample_flow_run]
        mock_get_client.return_value = mock_get_client_cm
        test_flow_id = str(uuid4())
        mock_get_uri.return_value = f"prefect://flow-runs?flow_id={test_flow_id}"

        # Get the actual resource function from the FastMCP server
        resource_manager = mcp._resource_manager
        resource_func = None
        for resource in resource_manager._resources.values():
            if str(resource.uri) == "prefect://flow-runs":
                resource_func = resource.fn
                break

        assert resource_func is not None, "Could not find flow-runs resource function"
        mock_ctx = AsyncMock()
        data = await resource_func(mock_ctx)

        assert data["filters"]["flow_id"] == test_flow_id
        mock_client.read_flow_runs.assert_called_once()

    @pytest.mark.asyncio
    @patch("prefect_mcp.server.get_client")
    async def test_get_flow_run_by_id_resource(self, mock_get_client, sample_flow_run, mock_async_client):
        """Test get_flow_run_by_id_resource function."""
        mock_client, mock_get_client_cm = mock_async_client
        mock_client.read_flow_run.return_value = sample_flow_run
        mock_get_client.return_value = mock_get_client_cm

        flow_run_id = str(sample_flow_run.id)

        async with Client(mcp) as client:
            result = await client.read_resource(f"prefect://flow-runs/{flow_run_id}")
            content = result[0]
            data = json.loads(content.text)

            assert "flow_run" in data
            assert data["flow_run"]["id"] == flow_run_id
            mock_client.read_flow_run.assert_called_once_with(UUID(flow_run_id))

    @pytest.mark.asyncio
    async def test_flow_run_resources_listed(self):
        """Test that flow run resources are properly registered."""
        async with Client(mcp) as client:
            resources = await client.list_resources()
            templates = await client.list_resource_templates()

            expected_uris = ["prefect://flows", "prefect://deployments", "prefect://flow-runs"]
            expected_templates = ["prefect://flows/{id}", "prefect://deployments/{id}", "prefect://flow-runs/{id}"]

            actual_uris = [str(r.uri) for r in resources]
            actual_templates = [str(t.uriTemplate) for t in templates]

            assert all(uri in actual_uris for uri in expected_uris), f"Missing URIs. Expected: {expected_uris}, Got: {actual_uris}"
            assert all(template in actual_templates for template in expected_templates), f"Missing templates. Expected: {expected_templates}, Got: {actual_templates}"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
