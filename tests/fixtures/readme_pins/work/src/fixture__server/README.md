# Fixture server

Run it with `npx` from your client. This sentence mentions npx in prose and is not a command.

```json
{
  "mcpServers": {
    "fixture": {
      "command": "npx",
      "args": ["-y", "@fixture/server@latest"]
    },
    "pinned": {
      "command": "npx",
      "args": ["-y", "@fixture/server@1.4.2"]
    },
    "py": {
      "command": "uvx",
      "args": ["fixture-mcp"]
    },
    "img": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "TOKEN", "ghcr.io/fixture/server"]
    }
  }
}
```

```sh
claude mcp add fixture -- npx -y @fixture/server
uvx --from fixture-mcp==0.3.1 fixture-mcp serve
uvx fixture-tools@latest
docker run -i --rm ghcr.io/fixture/server@sha256:0123abcd
docker run -i --rm -v /data:/data ghcr.io/fixture/server:1.4.2
npx @modelcontextprotocol/inspector node dist/index.js
npx tsx src/index.ts
npx -y mcp-remote@^0.1 https://example.com/mcp
pipx run fixture-cli
```

```toml
[mcp_servers.fixture]
command = "npx"
args = ["-y", "@fixture/other@next"]
```
