from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations, Tool
mcp = FastMCP("fixture")

@mcp.tool(
    name="search_notes",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def search(query: str) -> str:
    return ""

@mcp.tool()
def drop_table(name: str) -> str:
    return ""

LOW = Tool(name="pay_invoice", description="Pay", inputSchema={}, annotations=None)

CATEGORY_ONLY = types.Tool(name="erase_disk", description="Erase", inputSchema={},
                           annotations=types.ToolAnnotations(**{"category": "DISK"}))

@mcp.tool(**CONTROL)
def set_voltage(volts: float) -> str:
    return ""

@netbox_tool(name="list_devices", annotations={"readOnlyHint": True})
def list_devices() -> str:
    return ""
