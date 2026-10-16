const tools = [
  { name: "remove_user", description: "Remove a user", inputSchema: { type: "object" }, annotations: { destructiveHint: true } },
  { name: "get_user", description: "Get a user", inputSchema: { type: "object" } },
];
const config = { name: "not-a-tool", port: 8080 };
