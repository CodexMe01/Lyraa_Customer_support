# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "fastmcp",
#   "mcp",
# ]
# ///
# Example implementation using a hypothetical MCP SDK or FastMCP.
# Note: The actual implementation will depend on your specific MCP framework.
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "Back_end"

for path in (PROJECT_ROOT, BACKEND_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from fastmcp import FastMCP
from Back_end.agent.bot import chat_with_agent

# Initialize the MCP Server
mcp = FastMCP("LyraaSupportServer")

@mcp.tool()
def ask_support_agent(query: str, user_id: str = "mcp-user") -> str:
    """
    Ask the RAG-powered customer support agent a question.
    """
    try:
        result = chat_with_agent(query)
        return result["response"]
    except Exception as e:
        return f"Error connecting to support agent: {str(e)}"

if __name__ == "__main__":
    print("Starting Lyraa MCP Server...")
    mcp.run()
