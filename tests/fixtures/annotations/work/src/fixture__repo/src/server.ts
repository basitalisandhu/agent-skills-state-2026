import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
const server = new McpServer({ name: "fixture-server", version: "1.0.0" });
server.registerTool("list_files", {
  title: "List files",
  inputSchema: { path: z.string() },
  annotations: { readOnlyHint: true, openWorldHint: false },
}, async () => ({ content: [] }));
server.tool("deleteFile", "Delete a file", { path: z.string() }, async () => ({ content: [] }));
server.registerTool("send_email", {
  inputSchema: { to: z.string() },
  annotations: { readOnlyHint: true },
}, async () => ({ content: [] }));
const DESTRUCTIVE = { destructiveHint: true } as const;
server.registerTool("purge_queue", { inputSchema: {}, annotations: DESTRUCTIVE }, async () => ({ content: [] }));
async function smoke(c) {
  const r = await c.tool("delete_everything", { confirm: true });
}
