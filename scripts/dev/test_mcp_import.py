from mcp.server.mcpserver import MCPServer

mcp = MCPServer("career_page_reader")

@mcp.tool()
def ping() -> str:
    """Simple ping check tool."""
    return "pong"

print("MCPServer (mcp 2.x) loaded successfully!")
