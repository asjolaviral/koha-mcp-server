# Configuring the Koha MCP Server with Clients

Once the server is installed (see [INSTALLATION.md](INSTALLATION.md)), connect
it to the MCP client of your choice.

The server supports two transports:

- **stdio** — the default. The client spawns the server process and talks to it
  over stdin/stdout. Best for local/desktop clients (opencode, Claude Desktop).
- **SSE / Streamable HTTP** — the server runs as an HTTP service. Needed by
  clients that cannot spawn processes (e.g. **n8n**, remote setups).

---

## opencode

opencode reads MCP server configuration from an `opencode.json` file in the
project or from `~/.config/opencode/opencode.json` (user-global).

### stdio (recommended)

```json
{
  "mcp": {
    "koha": {
      "type": "stdio",
      "command": ["/home/<user>/koha-mcp-server/.venv/bin/python", "/home/<user>/koha-mcp-server/koha_mcp_server.py"]
    }
  }
}
```

### SSE (server must be started with the SSE transport)

Start the server first:

```bash
# in koha_mcp_server.py, use: mcp.run(transport="sse", host="0.0.0.0", port=8000)
/home/<user>/koha-mcp-server/.venv/bin/python /home/<user>/koha-mcp-server/koha_mcp_server.py
```

Then register it:

```json
{
  "mcp": {
    "koha": {
      "type": "sse",
      "url": "http://localhost:8000/sse"
    }
  }
}
```

After editing the config, restart opencode. The 24 Koha tools will appear and
you can ask, for example:

> *Search the catalogue for "advertising management" and list the results.*

---

## Claude Desktop

Add a server entry under `mcpServers` in the Claude Desktop configuration file:

| Platform | Config path                                                        |
|----------|--------------------------------------------------------------------|
| macOS    | `~/Library/Application Support/Claude/claude_desktop_config.json`  |
| Windows  | `%APPDATA%\Claude\claude_desktop_config.json`                      |
| Linux    | `~/.config/Claude/claude_desktop_config.json`                      |

```json
{
  "mcpServers": {
    "koha": {
      "command": "/home/<user>/koha-mcp-server/.venv/bin/python",
      "args": ["/home/<user>/koha-mcp-server/koha_mcp_server.py"],
      "env": {}
    }
  }
}
```

> The `command` must be an absolute path. After saving, quit and reopen Claude
> Desktop. Look for the 🛠 tools icon — the Koha tools will be listed there.

Example prompts:

- *Issue item 4 to patron 1.*
- *Renew the checkout for that item.*
- *Return the item with barcode TEST-0001.*
- *Add a new book titled "The Master of Gujarat" by K. Munshi, ISBN 9788172760595.*

---

## n8n

n8n cannot spawn local processes by default, so run the Koha MCP Server over
**SSE / Streamable HTTP** and connect with n8n's **MCP Server Tool** node.

### 1. Start the server over SSE

```bash
# run koha_mcp_server.py with the SSE transport, e.g.:
/home/<user>/koha-mcp-server/.venv/bin/python /home/<user>/koha-mcp-server/koha_mcp_server.py
```

(with the last line of `koha_mcp_server.py` set to
`mcp.run(transport="sse", host="0.0.0.0", port=8000)`.)

Verify it responds:

```bash
curl http://localhost:8000/sse
```

### 2. Add an MCP Server Tool node

1. Open your n8n workflow.
2. Add the **MCP Server Tool** node (available in n8n 1.x+).
3. Configure:
   - **Transport**: `SSE` (or `Streamable HTTP`, if supported by your n8n)
   - **URL**: `http://localhost:8000/sse` (or the server's LAN address, e.g.
     `http://192.168.29.214:8000/sse` if n8n runs on another host)
4. Click **Test connection**. The 24 Koha tools are discovered automatically.
5. Connect the node to your workflow. The **MCP Tool** node lets you select a
   specific Koha tool and pass its parameters from workflow fields.

### 3. Example n8n workflow idea

```
[Webhook] → [MCP Server Tool: search_catalogue] → [Set / Filter] → [HTTP: place_hold]
```

- Trigger on a webhook containing `{ query: "experiments" }`
- Call `search_catalogue(query=<webhook.query>, field="title")`
- Parse the JSON output, let the user (or an AI agent) pick a `biblio_id`
- Call `place_hold(patron_id, biblio_id, pickup_library_id)` to complete the flow

### Security note

Running the server over `0.0.0.0:8000` exposes the Koha API credentials to
anyone who can reach that port. For anything beyond a trusted LAN:

- Bind to `127.0.0.1` and use a reverse proxy (nginx/Caddy) with TLS and
  authentication, or
- Add an auth header / restrict the port with your firewall.

---

## Verifying a client connection

In any client, run a minimal tool to confirm the connection:

- opencode: type `@koha` (or ask a question about the catalogue).
- Claude Desktop: click the tools icon, confirm the Koha tools load, then ask a
  catalogue question.
- n8n: click **Test connection** on the MCP Server Tool node.

If tools do not appear, see [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md).
