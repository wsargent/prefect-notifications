#!/usr/bin/env python3
"""
Letta initialization script to create an agent and register Prefect tools using letta-client
"""
import os
import time
import subprocess
import sys
from typing import Dict, Any, Optional

def install_letta_client():
    """Install letta-client if not already installed"""
    try:
        import letta_client
        print("letta-client is already installed")
    except ImportError:
        print("Installing letta-client...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "letta-client"])
        print("letta-client installed successfully")

def install_prefect():
    """Install prefect if not already installed"""
    try:
        import prefect
        print("prefect is already installed")
    except ImportError:
        print("Installing prefect...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "prefect"])
        print("prefect installed successfully")


def wait_for_letta_service(base_url: str, timeout: int = 300) -> bool:
    """Wait for Letta service to be ready"""
    print("Waiting for Letta service to be ready...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            import urllib.request
            with urllib.request.urlopen(f"{base_url}/v1/health/", timeout=5) as response:
                if response.status == 200:
                    print("Letta service is ready!")
                    return True
        except Exception:
            pass
        
        print("Letta service not ready yet, waiting 5 seconds...")
        time.sleep(5)
    
    print("Timeout waiting for Letta service")
    return False

def create_prefect_tool(client) -> Optional[Any]:
    """Create Prefect workflow tool using letta-client"""
    try:
        
        def notify_default(body: str, subject: str):  
            """Send notifications via ntfy using Prefect client API.
            
            Args:
                body: The body of the message to send
                subject: The subject of the notification message
            """
            import asyncio
            from prefect import get_client
            
            async def run_notification():
                try:
                    async with get_client() as client:
                        # Find the ntfy_default flow deployment
                        try:
                            deployment = await client.read_deployment_by_name("ntfy_default/default")
                        except Exception:
                            # If deployment doesn't exist, try to find any deployment with ntfy_default
                            deployments = await client.read_deployments()
                            deployment = None
                            for d in deployments:
                                if d.flow_id and "ntfy" in d.name.lower():
                                    deployment = d
                                    break
                            
                            if not deployment:
                                # Run directly using the block if no deployment exists
                                from ntfy_webhook import NtfyWebHook
                                ntfy_webhook = await NtfyWebHook.load("ntfy-default")
                                await ntfy_webhook.notify(body, subject=subject)
                                return {"status": "success", "method": "direct"}
                        
                        # Create flow run from deployment
                        flow_run = await client.create_flow_run_from_deployment(
                            deployment.id,
                            parameters={"body": body, "subject": subject}
                        )
                        
                        return {
                            "status": "success", 
                            "flow_run_id": str(flow_run.id),
                            "method": "deployment"
                        }
                        
                except Exception as e:
                    # Fallback to direct execution
                    try:
                        from ntfy_webhook import NtfyWebHook
                        ntfy_webhook = await NtfyWebHook.load("ntfy-default")
                        await ntfy_webhook.notify(body, subject=subject)
                        return {"status": "success", "method": "fallback", "note": f"Deployment failed: {str(e)}"}
                    except Exception as fallback_error:
                        return {"status": "error", "error": str(fallback_error)}
            
            # Run the async function
            result = asyncio.run(run_notification())
            return result

        # Check if tool already exists
        try:
            existing_tools = client.tools.list()
            for tool in existing_tools:
                if tool.name == "notify_default":
                    print("Tool 'notify_default' already exists, skipping creation")
                    return tool
        except Exception as e:
            print(f"Could not check existing tools: {e}")
        
        tool = client.tools.upsert_from_function(
            func=notify_default
        )

        print(f"Created tool: {tool.name}")
        return tool
        
    except Exception as e:
        print(f"Error creating Prefect tool: {e}")
        return None

def create_letta_agent(client, model_name, embedding_name, tool_names: list) -> Optional[Any]:
    """Create a Letta agent with the Prefect tool"""
    try:
        from letta_client import CreateBlock

        agent_name = "prefect-notification-agent"
        
        # Check if agent already exists
        try:
            existing_agents = client.agents.list()
            for agent in existing_agents:
                if agent.name == agent_name:
                    print(f"Agent '{agent_name}' already exists, skipping creation")
                    return agent
        except Exception as e:
            print(f"Could not check existing agents: {e}")
        
        # Create the agent
        agent = client.agents.create(
            name=agent_name,
            memory_blocks=[
                CreateBlock(
                    value="You are a helpful assistant that can execute Prefect workflows and send notifications. You have access to tools that allow you to run notification flows, check flow status, and manage Prefect workflows.",
                    label="persona"
                ),
                CreateBlock(
                    value="The user wants to manage and execute Prefect notification workflows",
                    label="human",
                ),
            ],
            model=model_name,
            embedding=embedding_name,
            tools=tool_names
        )
        
        print(f"Created agent: {agent_name}")
        return agent
        
    except Exception as e:
        print(f"Error creating agent: {e}")
        return None

def main():
    """Main initialization function"""
    try:        
        install_letta_client()
        install_prefect()
        
        # Import letta-client after installation
        from letta_client import Letta
        
        # Configuration
        LETTA_URL = "http://letta:8283"
        
        # Wait for Letta service to be ready
        if not wait_for_letta_service(LETTA_URL):
            print("Letta service not ready, exiting...")
            return False
        
        # Give Letta a moment to fully initialize
        print("Waiting for Letta to fully initialize...")
        time.sleep(10)
        
        # Create Letta client
        client = Letta(base_url=LETTA_URL)
        
        # Create the Prefect tool
        tool = create_prefect_tool(client)
        if not tool:
            print("Failed to create Prefect tool, exiting...")
            return False
        
        model = os.getenv("LETTA_MODEL_NAME", "letta/letta-free")
        embedding_name = os.getenv("LETTA_EMBEDDING_MODEL_NAME", "letta/letta-free")
        
        # Create the agent with the tool
        agent = create_letta_agent(client, model, embedding_name, [tool.name])
        if not agent:
            print("Failed to create agent, exiting...")
            return False
        
        print("Letta initialization complete!")
        print(f"Agent '{agent.name}' is ready with Prefect workflow tools")
        print(f"Tool '{tool.name}' is attached to the agent")
        print(f"Access Letta at: {LETTA_URL}")
        
        return True
        
    except Exception as e:
        print(f"Error during Letta initialization: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)